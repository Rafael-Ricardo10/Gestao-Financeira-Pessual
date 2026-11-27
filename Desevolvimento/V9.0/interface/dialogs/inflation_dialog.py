# interface/dialogs/inflation_dialog.py
"""
Diálogo de Análise de Inflação
Inflação pessoal vs IPCA oficial do Banco Central
"""
import sqlite3
import threading
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas
)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QWidget, QGroupBox,
    QTextEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QFrame, QScrollArea, QComboBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor

from modulos.inflation_tracker import (
    create_inflation_tables,
    fetch_all_bcb_series,
    calculate_personal_inflation,
    compare_personal_vs_official,
    correlate_inflation_currency,
    get_accumulated_ipca,
    has_official_data,
)


class InflationDialog(QDialog):
    """
    Diálogo completo de análise de inflação.
    Compara inflação pessoal vs IPCA oficial.
    """

    # Sinal usado para avisar a thread principal quando o
    # worker em background termina de buscar dados do BCB.
    # IMPORTANTE: nunca chamar QTimer.singleShot() de dentro
    # de uma threading.Thread comum - o Qt só permite timers
    # em threads com event loop (QThread). Sinais, por outro
    # lado, são automaticamente entregues na thread principal
    # quando emitidos de outra thread (conexão em fila).
    bcb_fetch_done = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('📊 Análise de Inflação')
        self.setMinimumSize(1000, 700)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )
        self.db      = parent.db_connection
        self.user_id = parent.user_id
        self.db_path = self._find_db_path()

        # Garantir tabelas
        create_inflation_tables(self.db)

        self._build_ui()
        self.apply_theme()

        # Conectar sinal do worker de background (BCB)
        self.bcb_fetch_done.connect(self._on_bcb_fetch_done)

        self._fechado = False
        self.current_result = None

        # A janela abre primeiro (status "Carregando..."); os dados locais
        # e a busca no BCB começam logo depois, sem segurar a abertura.
        QTimer.singleShot(50, self._iniciar_carga)

        # Auto-refresh a cada 10 minutos
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._load_data)
        self.refresh_timer.start(600_000)

    def _iniciar_carga(self):
        if self._fechado:
            return
        self._load_data()          # dados locais
        self._start_bcb_fetch()    # BCB em background

    def _find_db_path(self) -> str:
        """Banco da conta ativa (cifrado: só abre com a chave da conta)"""
        from modulos import bd_seguro
        return bd_seguro.caminho_ativo()

    # ══════════════════════════════════════════════════════
    # INTERFACE
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Cabeçalho ────────────────────────────────────────
        header = QHBoxLayout()
        title  = QLabel('📊 Análise de Inflação Pessoal')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        header.addWidget(title)

        badge = QLabel('🏦 Dados: BCB + Histórico Pessoal')
        badge.setStyleSheet(
            'background-color: #2980b9; color: white;'
            'padding: 4px 8px; border-radius: 10px;'
            'font-size: 11px; font-weight: bold;'
        )
        header.addWidget(badge)
        header.addStretch()

        self.status_label = QLabel('Carregando...')
        self.status_label.setStyleSheet(
            'color: #7f8c8d; font-size: 11px;'
        )
        header.addWidget(self.status_label)

        self.refresh_btn = QPushButton('🔄 Atualizar BCB')
        self.refresh_btn.clicked.connect(self._force_bcb_fetch)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        # ── Barra de progresso ────────────────────────────────
        self.update_bar = QProgressBar()
        self.update_bar.setRange(0, 0)
        self.update_bar.setMaximumHeight(6)
        self.update_bar.setVisible(False)
        layout.addWidget(self.update_bar)

        # ── Cards de resumo ───────────────────────────────────
        self.cards_layout = QHBoxLayout()
        self.card_personal = self._make_card(
            '👤 Minha Inflação', '—%', '#e74c3c'
        )
        self.card_ipca = self._make_card(
            '🏦 IPCA Oficial', '—%', '#2980b9'
        )
        self.card_diff = self._make_card(
            '📊 Diferença', '—%', '#f39c12'
        )
        self.card_inpc = self._make_card(
            '👷 INPC', '—%', '#8e44ad'
        )
        self.card_igpm = self._make_card(
            '🏠 IGP-M', '—%', '#16a085'
        )

        for card in [
            self.card_personal, self.card_ipca,
            self.card_diff, self.card_inpc, self.card_igpm
        ]:
            self.cards_layout.addWidget(card)

        layout.addLayout(self.cards_layout)

        # ── Abas ─────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(
            self._build_overview_tab(), '📈 Visão Geral'
        )
        self.tabs.addTab(
            self._build_categories_tab(), '📂 Por Categoria'
        )
        self.tabs.addTab(
            self._build_ipca_tab(), '🏦 IPCA Histórico'
        )
        self.tabs.addTab(
            self._build_correlation_tab(), '🔗 Correlação'
        )
        self.tabs.addTab(
            self._build_insights_tab(), '💡 Insights'
        )
        layout.addWidget(self.tabs)

        # ── Rodapé ───────────────────────────────────────────
        footer = QHBoxLayout()
        self.footer_label = QLabel(
            '🏦 Dados do Banco Central: api.bcb.gov.br  '
            '| Gratuito | Sem registro'
        )
        self.footer_label.setStyleSheet(
            'color: #7f8c8d; font-size: 10px;'
        )
        footer.addWidget(self.footer_label)
        footer.addStretch()

        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

    def _make_card(
        self, title: str, value: str, color: str
    ) -> QFrame:
        """Cria card de métrica"""
        card = QFrame()
        card.setFrameStyle(QFrame.Box | QFrame.Raised)
        card.setMinimumWidth(160)
        card.setMaximumHeight(110)
        card.setStyleSheet(
            f'border: 2px solid {color}; border-radius: 8px;'
        )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(
            f'font-size: 11px; font-weight: bold; '
            f'color: {color}; border: none;'
        )
        t.setAlignment(Qt.AlignCenter)
        t.setObjectName('title')

        v = QLabel(value)
        v.setStyleSheet(
            f'font-size: 24px; font-weight: bold; '
            f'color: {color}; border: none;'
        )
        v.setAlignment(Qt.AlignCenter)
        v.setObjectName('value')

        sub = QLabel('')
        sub.setStyleSheet(
            'font-size: 10px; color: #7f8c8d; border: none;'
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setObjectName('sub')

        lay.addWidget(t)
        lay.addWidget(v)
        lay.addWidget(sub)
        return card

    def _update_card(
        self, card: QFrame, value: str,
        sub: str = '', color: str = None
    ):
        """Atualiza valores do card"""
        v = card.findChild(QLabel, 'value')
        s = card.findChild(QLabel, 'sub')
        if v:
            v.setText(value)
            if color:
                v.setStyleSheet(
                    f'font-size: 24px; font-weight: bold; '
                    f'color: {color}; border: none;'
                )
        if s:
            s.setText(sub)

    def _build_overview_tab(self) -> QWidget:
        """Aba de visão geral"""
        w = QWidget()
        l = QVBoxLayout(w)

        # Gráfico comparativo
        chart_group  = QGroupBox(
            '📈 Minha Inflação vs IPCA Oficial (por mês)'
        )
        chart_layout = QVBoxLayout()

        self.overview_figure = plt.figure(figsize=(9, 3.5), dpi=95)
        self.overview_canvas = FigureCanvas(self.overview_figure)
        self.overview_canvas.setMinimumHeight(240)
        chart_layout.addWidget(self.overview_canvas)
        chart_group.setLayout(chart_layout)
        l.addWidget(chart_group)

        # Resumo textual
        summary_group  = QGroupBox('📋 Resumo do Período')
        summary_layout = QVBoxLayout()

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(140)
        summary_layout.addWidget(self.summary_text)
        summary_group.setLayout(summary_layout)
        l.addWidget(summary_group)

        return w

    def _build_categories_tab(self) -> QWidget:
        """Aba por categoria"""
        w = QWidget()
        l = QVBoxLayout(w)

        hint = QLabel(
            '📂 Variação dos seus gastos por categoria '
            'comparando este ano com o ano anterior.'
        )
        hint.setStyleSheet(
            'color: #7f8c8d; font-style: italic;'
        )
        l.addWidget(hint)

        # Gráfico de barras horizontais
        self.cat_figure = plt.figure(figsize=(9, 3.5), dpi=95)
        self.cat_canvas = FigureCanvas(self.cat_figure)
        self.cat_canvas.setMinimumHeight(220)
        l.addWidget(self.cat_canvas)

        # Tabela detalhada
        self.cat_table = QTableWidget()
        self.cat_table.setColumnCount(6)
        self.cat_table.setHorizontalHeaderLabels([
            'Categoria',
            f'Média {datetime.now().year} (R$)',
            f'Média {datetime.now().year-1} (R$)',
            'Variação %',
            'vs IPCA',
            'Situação'
        ])
        self.cat_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cat_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cat_table.horizontalHeader().setStretchLastSection(True)
        self.cat_table.verticalHeader().setVisible(False)
        self.cat_table.setAlternatingRowColors(True)
        l.addWidget(self.cat_table)

        return w

    def _build_ipca_tab(self) -> QWidget:
        """Aba IPCA histórico"""
        w = QWidget()
        l = QVBoxLayout(w)

        controls = QHBoxLayout()
        controls.addWidget(QLabel('Índice:'))
        self.index_combo = QComboBox()
        self.index_combo.addItems([
            'IPCA (Inflação Oficial)',
            'INPC (Classe Baixa)',
            'IGP-M (Mercado)',
            'Selic (Juros)',
        ])
        self.index_combo.currentIndexChanged.connect(
            self._update_ipca_chart
        )
        controls.addWidget(self.index_combo)
        controls.addStretch()
        l.addLayout(controls)

        self.ipca_figure = plt.figure(figsize=(9, 3.5), dpi=95)
        self.ipca_canvas = FigureCanvas(self.ipca_figure)
        self.ipca_canvas.setMinimumHeight(240)
        l.addWidget(self.ipca_canvas)

        self.ipca_table = QTableWidget()
        self.ipca_table.setColumnCount(3)
        self.ipca_table.setHorizontalHeaderLabels([
            'Mês', 'Valor (%)', 'Acumulado Ano (%)'
        ])
        self.ipca_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ipca_table.horizontalHeader().setStretchLastSection(True)
        self.ipca_table.verticalHeader().setVisible(False)
        self.ipca_table.setMaximumHeight(200)
        l.addWidget(self.ipca_table)

        return w

    def _build_correlation_tab(self) -> QWidget:
        """Aba de correlação inflação × câmbio × gastos"""
        w = QWidget()
        l = QVBoxLayout(w)

        hint = QLabel(
            '🔗 Qual fator influencia mais seus gastos: '
            'a inflação oficial (IPCA) ou o câmbio (USD/BRL)?'
        )
        hint.setStyleSheet(
            'color: #2980b9; font-style: italic; padding: 4px;'
        )
        hint.setWordWrap(True)
        l.addWidget(hint)

        self.corr_figure = plt.figure(figsize=(9, 3.5), dpi=95)
        self.corr_canvas = FigureCanvas(self.corr_figure)
        self.corr_canvas.setMinimumHeight(220)
        l.addWidget(self.corr_canvas)

        result_group  = QGroupBox('📊 Resultado da Correlação Tripla')
        result_layout = QVBoxLayout()

        self.corr_result_text = QTextEdit()
        self.corr_result_text.setReadOnly(True)
        self.corr_result_text.setMaximumHeight(160)
        result_layout.addWidget(self.corr_result_text)
        result_group.setLayout(result_layout)
        l.addWidget(result_group)

        return w

    def _build_insights_tab(self) -> QWidget:
        """Aba de insights automáticos"""
        w = QWidget()
        l = QVBoxLayout(w)

        info_label = QLabel(
            'ℹ️ Insights gerados automaticamente comparando '
            'seus gastos pessoais com os índices oficiais do '
            'Banco Central do Brasil.'
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            'color: #2980b9; font-style: italic; padding: 5px;'
        )
        l.addWidget(info_label)

        self.insights_text = QTextEdit()
        self.insights_text.setReadOnly(True)
        l.addWidget(self.insights_text)

        return w

    # ══════════════════════════════════════════════════════
    # CARREGAMENTO DE DADOS
    # ══════════════════════════════════════════════════════

    def _load_data(self):
        """Carrega todos os dados e atualiza a interface"""
        try:
            result = compare_personal_vs_official(
                self.db, self.user_id
            )
            self.current_result = result

            self._update_cards(result)
            self._update_overview(result)
            self._update_categories(result)
            self._update_ipca_chart()
            self._update_correlation()
            self._update_insights(result)

        except Exception as e:
            print(f'[InflationDialog] Erro ao carregar: {e}')
            import traceback
            traceback.print_exc()

    def _update_cards(self, result: dict):
        """Atualiza os cards de resumo"""
        if not result.get('has_data'):
            return

        personal = result.get('personal_inflation', 0)
        ipca     = result.get('ipca_acum', 0)
        diff     = result.get('diff_vs_ipca', 0)
        inpc     = result.get('inpc_acum', 0)
        igpm     = result.get('igpm_acum', 0)
        year     = result.get('current_year', datetime.now().year)

        # Cor dinâmica para diferença
        diff_color = (
            '#e74c3c' if diff > 2 else
            '#27ae60' if diff < -2 else
            '#f39c12'
        )

        self._update_card(
            self.card_personal,
            f'{personal:+.1f}%',
            f'vs {result.get("prev_year",year-1)}',
            '#e74c3c' if personal > 0 else '#27ae60'
        )
        self._update_card(
            self.card_ipca,
            f'{ipca:.1f}%' if ipca > 0 else 'Sem dados',
            f'Acumulado {year}',
            '#2980b9'
        )
        self._update_card(
            self.card_diff,
            f'{diff:+.1f}%' if ipca > 0 else '—',
            'Pessoal vs IPCA',
            diff_color
        )
        self._update_card(
            self.card_inpc,
            f'{inpc:.1f}%' if inpc > 0 else 'Sem dados',
            f'Acumulado {year}',
            '#8e44ad'
        )
        self._update_card(
            self.card_igpm,
            f'{igpm:.1f}%' if igpm > 0 else 'Sem dados',
            f'Acumulado {year}',
            '#16a085'
        )

    def _update_overview(self, result: dict):
        """Atualiza aba de visão geral"""
        self.overview_figure.clear()
        ax = self.overview_figure.add_subplot(111)

        monthly_yoy = result.get('monthly_yoy', [])
        ipca_monthly = result.get('ipca_monthly', [])

        if not monthly_yoy:
            ax.text(
                0.5, 0.5,
                'Dados insuficientes.\n'
                'Necessário histórico de 2 anos.',
                ha='center', va='center',
                transform=ax.transAxes,
                color='gray', fontsize=12
            )
            self.overview_canvas.draw_idle()
        else:
            months       = [m['month']   for m in monthly_yoy]
            personal_pct = [m['yoy_pct'] for m in monthly_yoy]
            labels       = [m['label']   for m in monthly_yoy]

            x    = range(len(months))
            step = max(1, len(months) // 8)

            # Barras da inflação pessoal
            colors = [
                '#e74c3c' if v > 0 else '#27ae60'
                for v in personal_pct
            ]
            ax.bar(
                x, personal_pct,
                color=colors, alpha=0.7,
                label='Minha inflação (YoY%)'
            )

            # Linha IPCA
            ipca_map = {
                r['month']: r['value'] for r in ipca_monthly
            }
            ipca_vals = [
                ipca_map.get(m, None) for m in months
            ]

            if any(v is not None for v in ipca_vals):
                # Preencher gaps com None para linha tracejada
                ax.plot(
                    list(x),
                    [v if v is not None else float('nan')
                     for v in ipca_vals],
                    '--o', linewidth=2, markersize=4,
                    label='IPCA mensal (%)',
                    color='#2980b9'
                )

            ax.axhline(y=0, color='gray', linewidth=0.8, alpha=0.5)
            ax.set_xticks(list(x)[::step])
            ax.set_xticklabels(
                labels[::step],
                rotation=45, ha='right', fontsize=7
            )
            ax.set_ylabel('Variação % (vs mesmo mês ano ant.)')
            ax.set_title(
                'Variação dos Gastos vs IPCA Mensal'
            )
            ax.legend(fontsize=8)
            ax.grid(True, linestyle='--', alpha=0.3)

        self.overview_figure.tight_layout()
        self.overview_canvas.draw_idle()

        # Resumo textual
        if result.get('has_data'):
            personal   = result.get('personal_inflation', 0)
            ipca       = result.get('ipca_acum', 0)
            diff       = result.get('diff_vs_ipca', 0)
            year       = result.get('current_year', '')
            prev_year  = result.get('prev_year', '')
            total_curr = result.get('total_current_avg', 0)
            total_prev = result.get('total_prev_avg', 0)

            has_ipca = result.get('has_official_data', False)

            color_p = '#e74c3c' if personal > 0 else '#27ae60'
            color_d = '#e74c3c' if diff > 0 else '#27ae60'

            html = f'''
            <table width="100%" cellpadding="6">
                <tr>
                    <td><b>📅 Período analisado:</b></td>
                    <td>{prev_year} → {year}</td>
                    <td><b>💸 Gasto médio {prev_year}:</b></td>
                    <td>R$ {total_prev:,.2f}/mês</td>
                </tr>
                <tr>
                    <td><b>💸 Gasto médio {year}:</b></td>
                    <td>R$ {total_curr:,.2f}/mês</td>
                    <td><b>👤 Minha inflação:</b></td>
                    <td><b style="color:{color_p};">
                    {personal:+.1f}%</b></td>
                </tr>
            '''

            if has_ipca:
                html += f'''
                <tr>
                    <td><b>🏦 IPCA {year}:</b></td>
                    <td>{ipca:.2f}%</td>
                    <td><b>📊 Diferença:</b></td>
                    <td><b style="color:{color_d};">
                    {diff:+.2f}%</b></td>
                </tr>
                '''
            else:
                html += '''
                <tr>
                    <td colspan="4" style="color:#e67e22;">
                    ⚠️ Dados do IPCA não encontrados.
                    Clique em "Atualizar BCB" para buscar.
                    </td>
                </tr>
                '''

            html += '</table>'
            self.summary_text.setHtml(html)

    def _update_categories(self, result: dict):
        """Atualiza aba de categorias"""
        categories = result.get('categories_vs_ipca') or \
                     result.get('categories', [])

        ipca = result.get('ipca_acum', 0)

        # Gráfico de barras horizontais
        self.cat_figure.clear()
        ax = self.cat_figure.add_subplot(111)

        cats_with_prev = [
            c for c in categories if c.get('has_prev')
        ][:12]

        if cats_with_prev:
            names  = [
                c['category'][:20] for c in cats_with_prev
            ]
            values = [c['variation'] for c in cats_with_prev]
            colors = [
                '#e74c3c' if v > 0 else '#27ae60'
                for v in values
            ]

            y = range(len(names))
            ax.barh(y, values, color=colors, alpha=0.8)
            ax.set_yticks(list(y))
            ax.set_yticklabels(names, fontsize=8)
            ax.axvline(x=0, color='gray', linewidth=0.8)

            if ipca > 0:
                ax.axvline(
                    x=ipca, color='#2980b9',
                    linewidth=2, linestyle='--',
                    label=f'IPCA: {ipca:.1f}%'
                )
                ax.legend(fontsize=8)

            ax.set_xlabel('Variação % vs ano anterior')
            ax.set_title('Variação de Gastos por Categoria')
            ax.grid(True, axis='x', linestyle='--', alpha=0.4)
        else:
            ax.text(
                0.5, 0.5,
                'Sem dados comparativos por categoria.\n'
                'Necessário histórico de 2 anos.',
                ha='center', va='center',
                transform=ax.transAxes, color='gray'
            )

        self.cat_figure.tight_layout()
        self.cat_canvas.draw_idle()

        # Tabela
        self.cat_table.setRowCount(len(categories))

        for i, cat in enumerate(categories):
            variation   = cat.get('variation', 0)
            has_prev    = cat.get('has_prev', False)
            diff_ipca   = cat.get('diff_vs_ipca', None)

            # Cor
            if has_prev:
                row_color = (
                    QColor('#1B5E20') if (
                        variation < 0 and self.is_dark_mode
                    )
                    else QColor('#E8F5E9') if variation < 0
                    else QColor('#B71C1C') if self.is_dark_mode
                    else QColor('#FFEBEE')
                )
            else:
                row_color = QColor('transparent')

            # Situação
            if not has_prev:
                situacao = '🆕 Nova categoria'
                sit_color = '#7f8c8d'
            elif variation < 0:
                situacao = '✅ Deflação'
                sit_color = '#27ae60'
            elif diff_ipca is not None and diff_ipca < -2:
                situacao = '💚 Abaixo do IPCA'
                sit_color = '#2ecc71'
            elif diff_ipca is not None and diff_ipca > 5:
                situacao = '🚨 Muito acima do IPCA'
                sit_color = '#e74c3c'
            elif diff_ipca is not None and diff_ipca > 0:
                situacao = '⚠️ Acima do IPCA'
                sit_color = '#e67e22'
            else:
                situacao = 'ℹ️ Normal'
                sit_color = '#3498db'

            items = [
                QTableWidgetItem(cat['category']),
                QTableWidgetItem(
                    f"R$ {cat['current_avg']:,.2f}"
                ),
                QTableWidgetItem(
                    f"R$ {cat['prev_avg']:,.2f}"
                    if has_prev else '—'
                ),
                QTableWidgetItem(
                    f"{variation:+.1f}%"
                    if has_prev else '—'
                ),
                QTableWidgetItem(
                    f"{diff_ipca:+.1f}%"
                    if diff_ipca is not None and ipca > 0
                    else '—'
                ),
                QTableWidgetItem(situacao),
            ]

            for j, item in enumerate(items):
                item.setBackground(row_color)
                self.cat_table.setItem(i, j, item)

            # Colorir variação
            var_item = self.cat_table.item(i, 3)
            if var_item and has_prev:
                var_item.setForeground(
                    QColor('#27ae60') if variation < 0
                    else QColor('#e74c3c')
                )

            # Colorir situação
            sit_item = self.cat_table.item(i, 5)
            if sit_item:
                sit_item.setForeground(QColor(sit_color))

        self.cat_table.resizeColumnsToContents()

    def _update_ipca_chart(self):
        """Atualiza gráfico do IPCA histórico"""
        index_map = {
            0: 'IPCA',
            1: 'INPC',
            2: 'IGP_M',
            3: 'SELIC',
        }
        series_code = index_map.get(
            self.index_combo.currentIndex(), 'IPCA'
        )

        from modulos.inflation_tracker import BCB_SERIES
        series_label = BCB_SERIES.get(
            series_code, {}
        ).get('label', series_code)

        rows = self.db.execute(
            '''SELECT ref_date, value,
                      strftime('%Y-%m', ref_date) AS month
               FROM inflation_official
               WHERE series_code = ?
               ORDER BY ref_date DESC
               LIMIT 60''',
            (series_code,)
        ).fetchall()

        rows = list(reversed(rows))

        self.ipca_figure.clear()
        ax = self.ipca_figure.add_subplot(111)

        if not rows:
            ax.text(
                0.5, 0.5,
                f'Sem dados de {series_label}.\n'
                f'Clique em "Atualizar BCB".',
                ha='center', va='center',
                transform=ax.transAxes, color='gray', fontsize=12
            )
            self.ipca_canvas.draw_idle()
            self.ipca_table.setRowCount(0)
            return

        months = [r['month'] for r in rows]
        values = [r['value'] for r in rows]
        labels = []
        for m in months:
            try:
                dt = datetime.strptime(m, '%Y-%m')
                labels.append(dt.strftime('%b/%Y'))
            except Exception:
                labels.append(m)

        x    = range(len(months))
        step = max(1, len(months) // 10)

        colors = [
            '#e74c3c' if v > 0 else '#27ae60' for v in values
        ]
        ax.bar(x, values, color=colors, alpha=0.8)
        ax.axhline(y=0, color='gray', linewidth=0.8)

        # Média
        avg = sum(values) / len(values)
        ax.axhline(
            y=avg, color='#f39c12',
            linewidth=1.5, linestyle='--',
            label=f'Média: {avg:.2f}%'
        )

        ax.set_xticks(list(x)[::step])
        ax.set_xticklabels(
            labels[::step], rotation=45, ha='right', fontsize=7
        )
        ax.set_ylabel('Variação %')
        ax.set_title(f'{series_label} - Histórico Mensal')
        ax.legend(fontsize=8)
        ax.grid(True, axis='y', linestyle='--', alpha=0.4)

        self.ipca_figure.tight_layout()
        self.ipca_canvas.draw_idle()

        # Tabela com acumulado
        self.ipca_table.setRowCount(len(rows))
        acum = 1.0

        for i, row in enumerate(rows):
            acum *= (1 + row['value'] / 100)
            label = labels[i]
            val   = row['value']
            acum_pct = (acum - 1) * 100

            self.ipca_table.setItem(
                i, 0, QTableWidgetItem(label)
            )
            val_item = QTableWidgetItem(f'{val:.2f}%')
            val_item.setForeground(
                QColor('#e74c3c') if val > 0
                else QColor('#27ae60')
            )
            self.ipca_table.setItem(i, 1, val_item)
            self.ipca_table.setItem(
                i, 2,
                QTableWidgetItem(f'{acum_pct:.2f}%')
            )

        self.ipca_table.resizeColumnsToContents()

    def _update_correlation(self):
        """Atualiza aba de correlação tripla"""
        result = correlate_inflation_currency(
            self.db, self.user_id
        )

        self.corr_figure.clear()

        if not result.get('has_data'):
            ax = self.corr_figure.add_subplot(111)
            ax.text(
                0.5, 0.5,
                result.get('message', 'Dados insuficientes'),
                ha='center', va='center',
                transform=ax.transAxes,
                color='gray', fontsize=12
            )
            self.corr_canvas.draw_idle()
            self.corr_result_text.setHtml(
                f'<p style="color:gray;">'
                f'{result.get("message","Sem dados")}</p>'
            )
            return

        chart_data = result['chart_data']
        months     = [c['month']    for c in chart_data]
        expenses   = [c['expenses'] for c in chart_data]
        ipca_vals  = [c['ipca']     for c in chart_data]
        usd_vals   = [c['usd']      for c in chart_data]

        # 3 eixos: gastos (barras) + IPCA (linha) + USD (linha)
        ax1 = self.corr_figure.add_subplot(111)
        ax2 = ax1.twinx()

        x    = range(len(months))
        step = max(1, len(months) // 8)

        ax1.bar(
            x, expenses, alpha=0.4,
            color='#e74c3c', label='Gastos (R$)'
        )
        # NOTA: o formato '-o'/'--s' não deve mais incluir a
        # letra de cor (ex.: 'b-o'), pois isso conflita com o
        # argumento color= explícito e gera UserWarning do
        # matplotlib. A cor é definida só pelo color=.
        ax2.plot(
            x, ipca_vals, '-o',
            linewidth=2, markersize=4,
            label='IPCA (%)', color='#2980b9'
        )
        ax2.plot(
            x, usd_vals, '--s',
            linewidth=2, markersize=4,
            label='USD/BRL', color='#27ae60'
        )

        ax1.set_ylabel('Gastos (R$)', color='#e74c3c')
        ax2.set_ylabel('IPCA (%) / USD/BRL', color='#2980b9')

        ax1.set_xticks(list(x)[::step])
        ax1.set_xticklabels(
            months[::step], rotation=45, ha='right', fontsize=7
        )
        ax1.set_title('Gastos vs IPCA vs USD/BRL')

        lines1, lab1 = ax1.get_legend_handles_labels()
        lines2, lab2 = ax2.get_legend_handles_labels()
        ax1.legend(
            lines1 + lines2, lab1 + lab2,
            loc='upper left', fontsize=7
        )
        ax1.grid(True, linestyle='--', alpha=0.3)

        self.corr_figure.tight_layout()
        self.corr_canvas.draw_idle()

        # Resultado textual
        corr_ipca  = result['corr_ipca']
        corr_usd   = result['corr_usd']
        dominant   = result['dominant_label']
        months_n   = result['months_analyzed']

        def corr_color(c):
            if abs(c) > 0.5:
                return '#e74c3c'
            elif abs(c) > 0.3:
                return '#f39c12'
            return '#27ae60'

        html = f'''
        <h3>🔗 Correlação Tripla — {months_n} meses</h3>
        <table width="100%" cellpadding="6">
            <tr>
                <td><b>Correlação Gastos × IPCA:</b></td>
                <td><b style="color:{corr_color(corr_ipca)};">
                {corr_ipca:+.3f}</b></td>
                <td><b>Correlação Gastos × USD/BRL:</b></td>
                <td><b style="color:{corr_color(corr_usd)};">
                {corr_usd:+.3f}</b></td>
            </tr>
            <tr>
                <td colspan="4">
                    <b>🏆 Fator dominante:</b>
                    <span style="color:#2980b9; font-size:14px;">
                    {dominant}</span>
                </td>
            </tr>
        </table>
        <br>
        <div style="padding:8px; border-left:4px solid #2980b9;
            border-radius:4px;">
            <b>📝 Interpretação:</b><br>
            {'O IPCA influencia mais seus gastos que o câmbio.'
             if result['dominant'] == 'ipca'
             else 'O câmbio influencia mais seus gastos que o IPCA.'
             if result['dominant'] == 'usd'
             else 'IPCA e câmbio influenciam seus gastos igualmente.'}
            <br><br>
            <small>Correlação próxima de 1: forte relação positiva |
            Próxima de -1: relação inversa |
            Próxima de 0: sem relação</small>
        </div>
        '''
        self.corr_result_text.setHtml(html)

    def _update_insights(self, result: dict):
        """Atualiza aba de insights"""
        insights = result.get('insights', [])

        html = '<div style="font-size:13px;">'

        if not result.get('has_data'):
            html += (
                '<p style="color:gray; text-align:center;">'
                'ℹ️ Adicione transações de pelo menos 2 anos '
                'para gerar insights de inflação.</p>'
            )
        elif not insights:
            html += (
                '<p style="color:gray;">'
                'ℹ️ Sem insights disponíveis no momento.</p>'
            )
        else:
            for ins in insights:
                color_map = {
                    'positive':  '#27ae60',
                    'warning':   '#e67e22',
                    'attention': '#f39c12',
                    'critical':  '#e74c3c',
                    'info':      '#3498db'
                }
                bg_map = {
                    'positive':  '#eafaf1',
                    'warning':   '#fef9e7',
                    'attention': '#fef5e4',
                    'critical':  '#fdedec',
                    'info':      '#ebf5fb'
                }
                color = color_map.get(ins.get('type', 'info'), '#333')
                bg    = (
                    'transparent' if self.is_dark_mode
                    else bg_map.get(ins.get('type', 'info'), '#f9f9f9')
                )

                html += (
                    f'<div style="margin:6px 0; padding:10px; '
                    f'border-left: 4px solid {color}; '
                    f'background-color:{bg}; border-radius:4px;">'
                    f'<span style="font-size:16px;">'
                    f'{ins.get("emoji","")}</span> '
                    f'<span style="color:{color}; font-weight:bold;">'
                    f'{ins.get("message","")}</span>'
                    f'</div>'
                )

        html += '</div>'
        self.insights_text.setHtml(html)

    # ══════════════════════════════════════════════════════
    # BACKGROUND BCB
    # ══════════════════════════════════════════════════════

    def _start_bcb_fetch(self):
        """Inicia busca do BCB em background"""
        self.update_bar.setVisible(True)
        self.refresh_btn.setEnabled(False)
        self.status_label.setText('Buscando dados do BCB...')

        t = threading.Thread(
            target=self._bcb_worker, daemon=True
        )
        t.start()

    def _bcb_worker(self):
        """
        Worker em background para buscar dados do BCB.

        IMPORTANTE: esta função roda numa threading.Thread comum,
        sem event loop do Qt. Por isso, NUNCA deve chamar
        QTimer.singleShot() ou mexer diretamente em widgets daqui
        - ambos causam o erro "QObject::startTimer: Timers can
        only be used with threads started with QThread" e/ou
        crashes. Em vez disso, emitimos um sinal (bcb_fetch_done)
        no final; o Qt entrega esse sinal com segurança na thread
        principal (conexão em fila automática entre threads).
        """
        success = True
        try:
            if not self.db_path:
                success = False
            else:
                from modulos import bd_seguro

                thread_conn = bd_seguro.conectar_ativo()

                create_inflation_tables(thread_conn)

                # Data da primeira transação
                first = thread_conn.execute(
                    '''SELECT MIN(date) as first_date
                       FROM transactions WHERE user_id = ?''',
                    (self.user_id,)
                ).fetchone()

                since = (
                    first['first_date']
                    if first and first['first_date']
                    else '2020-01-01'
                )

                # Buscar todas as séries do BCB
                fetch_all_bcb_series(thread_conn, since_date=since)

                thread_conn.close()

        except Exception as e:
            print(f'[InflationDialog] Erro BCB worker: {e}')
            success = False

        try:
            self.bcb_fetch_done.emit(success)
        except RuntimeError:
            pass                    # diálogo já foi fechado/destruído

    def _on_bcb_fetch_done(self, success: bool):
        """
        Slot executado na thread principal (GUI) quando o
        worker de background termina - seguro para mexer em
        widgets, pois é chamado via sinal/slot do Qt.
        """
        if self._fechado:
            return
        self.update_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        if success:
            self.status_label.setText('✅ Dados do BCB atualizados')
        else:
            self.status_label.setText(
                '⚠️ Erro ou sem conexão com BCB'
            )
        self._load_data()

    def _force_bcb_fetch(self):
        """Força nova busca do BCB"""
        # Limpar cache para forçar atualização
        try:
            self.db.execute(
                'DELETE FROM inflation_cache'
            )
            self.db.commit()
        except Exception:
            pass
        self._start_bcb_fetch()

    # ══════════════════════════════════════════════════════
    # TEMA
    # ══════════════════════════════════════════════════════

    def apply_theme(self):
        """Aplica o tema"""
        if self.is_dark_mode:
            self.setStyleSheet('''
                QDialog {
                    background-color: #1e272e; color: #ecf0f1;
                }
                QLabel { color: #ecf0f1; }
                QComboBox {
                    padding: 6px; border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px; padding: 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #2980b9; color: white;
                }
                QPushButton:hover { background-color: #3498db; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                    alternate-background-color: #263238;
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                    padding: 5px; border: 1px solid #4b6584;
                }
                QTabWidget::pane {
                    border: 1px solid #4b6584;
                    background-color: #1e272e;
                }
                QTabBar::tab {
                    background-color: #2d3436; color: #ecf0f1;
                    padding: 8px 12px; border: 1px solid #4b6584;
                    border-bottom: none;
                }
                QTabBar::tab:selected { background-color: #2980b9; }
                QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 3px;
                    background-color: #2d3436;
                }
                QProgressBar::chunk { background-color: #2980b9; }
            ''')
            plt.style.use('dark_background')
        else:
            self.setStyleSheet('''
                QDialog { background-color: #f9f9f9; }
                QLabel { color: #333; }
                QComboBox {
                    padding: 6px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #2980b9; color: white;
                }
                QPushButton:hover { background-color: #3498db; }
                QTableWidget {
                    background-color: white;
                    alternate-background-color: #f8f9fa;
                }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc; font-weight: bold;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333;
                    padding: 8px 12px; border: 1px solid #ccc;
                    border-bottom: none;
                }
                QTabBar::tab:selected {
                    background-color: #2980b9; color: white;
                }
                QTextEdit {
                    background-color: white; border: 1px solid #ccc;
                    border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 3px;
                }
                QProgressBar::chunk { background-color: #2980b9; }
            ''')
            plt.style.use('default')

    def _limpar(self):
        """Para o timer e libera as figuras do matplotlib (idempotente)."""
        self._fechado = True
        try:
            self.refresh_timer.stop()
        except Exception:
            pass
        for nome in ('overview_figure', 'cat_figure', 'ipca_figure',
                     'corr_figure'):
            fig = getattr(self, nome, None)
            if fig is not None:
                try:
                    plt.close(fig)
                except Exception:
                    pass

    def done(self, resultado):
        # exec_() termina por aqui (nem sempre passa por closeEvent)
        self._limpar()
        super().done(resultado)

    def closeEvent(self, event):
        """Para timers ao fechar"""
        self._limpar()
        super().closeEvent(event)

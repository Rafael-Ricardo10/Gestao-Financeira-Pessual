"""
Diálogo de Tendências melhorado com IA
Filtros por categoria e descrição
Detecta padrões de alta/baixa automaticamente
"""
import numpy as np
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas
)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QGroupBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QSplitter, QFrame
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from modulos.ai import FinanceAIEngine, TrendAnalyzer


class TrendsDialog(QDialog):
    """
    Diálogo de análise de tendências com IA integrada.
    Filtros por categoria, descrição e tipo de transação.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('📈 Análise de Tendências com IA')
        self.setMinimumSize(950, 700)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )

        # Inicializar IA
        self.ai_engine = FinanceAIEngine(
            parent.db_connection, parent.user_id
        )
        self.analyzer  = TrendAnalyzer(
            parent.db_connection, parent.user_id, self.ai_engine
        )

        self._build_ui()
        self._load_filter_options()
        self.generate_analysis()
        self.apply_theme()

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout(self)

        # ── Cabeçalho ────────────────────────────────────────
        header = QHBoxLayout()
        title  = QLabel('📈 Análise de Tendências')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        header.addWidget(title)

        # Badge da IA
        ai_badge = QLabel('🤖 Powered by IA')
        ai_badge.setStyleSheet(
            'background-color: #3498db; color: white;'
            'padding: 4px 8px; border-radius: 10px;'
            'font-size: 11px; font-weight: bold;'
        )
        header.addWidget(ai_badge)
        header.addStretch()
        layout.addLayout(header)

        # ── Filtros ───────────────────────────────────────────
        filters_group  = QGroupBox('🔍 Filtros de Análise')
        filters_layout = QHBoxLayout()

        # Período
        filters_layout.addWidget(QLabel('Período:'))
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            '3 meses', '6 meses', '12 meses', 'Todo histórico'
        ])
        self.period_combo.setCurrentIndex(1)
        filters_layout.addWidget(self.period_combo)

        # Tipo de transação
        filters_layout.addWidget(QLabel('Tipo:'))
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            'Entrada e Saída', 'Apenas Entrada', 'Apenas Saída'
        ])
        filters_layout.addWidget(self.type_combo)

        # Categoria
        filters_layout.addWidget(QLabel('Categoria:'))
        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(180)
        filters_layout.addWidget(self.category_combo)

        # Descrição
        filters_layout.addWidget(QLabel('Descrição:'))
        self.description_combo = QComboBox()
        self.description_combo.setEditable(True)
        self.description_combo.setMinimumWidth(180)
        self.description_combo.lineEdit().setPlaceholderText(
            'Buscar por descrição...'
        )
        filters_layout.addWidget(self.description_combo)

        # Botão analisar
        self.analyze_btn = QPushButton('🔍 Analisar')
        self.analyze_btn.clicked.connect(self.generate_analysis)
        self.analyze_btn.setMinimumWidth(100)
        filters_layout.addWidget(self.analyze_btn)

        filters_group.setLayout(filters_layout)
        layout.addWidget(filters_group)

        # ── Cards de resumo ───────────────────────────────────
        self.summary_layout = QHBoxLayout()
        layout.addLayout(self.summary_layout)

        # ── Abas de conteúdo ──────────────────────────────────
        self.tabs = QTabWidget()

        self.tabs.addTab(
            self._build_chart_tab(), '📊 Gráficos'
        )
        self.tabs.addTab(
            self._build_details_tab(), '📋 Detalhes'
        )
        self.tabs.addTab(
            self._build_insights_tab(), '💡 Insights da IA'
        )
        self.tabs.addTab(
            self._build_categories_tab(), '📂 Por Categoria'
        )

        layout.addWidget(self.tabs)

        # ── Botões ────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        self.export_btn = QPushButton('📋 Exportar Análise')
        self.export_btn.clicked.connect(self.export_analysis)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addStretch()

        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _build_chart_tab(self) -> QWidget:
        """Aba de gráficos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Seletor de tipo de gráfico
        chart_selector = QHBoxLayout()
        chart_selector.addWidget(QLabel('Visualização:'))
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems([
            'Barras (Entrada vs Saída)',
            'Linha (Evolução do Saldo)',
            'Linha (Tendências)',
            'Área (Acumulado)',
        ])
        self.chart_type_combo.currentIndexChanged.connect(
            self._update_chart
        )
        chart_selector.addWidget(self.chart_type_combo)
        chart_selector.addStretch()
        layout.addLayout(chart_selector)

        # Canvas do gráfico
        self.figure = plt.figure(figsize=(9, 4), dpi=95)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(280)
        layout.addWidget(self.canvas)

        # Legenda de tendência
        self.trend_legend = QLabel()
        self.trend_legend.setAlignment(Qt.AlignCenter)
        self.trend_legend.setWordWrap(True)
        self.trend_legend.setStyleSheet(
            'padding: 8px; border-radius: 4px;'
            'font-size: 12px; font-weight: bold;'
        )
        layout.addWidget(self.trend_legend)

        return widget

    def _build_details_tab(self) -> QWidget:
        """Aba de detalhes numéricos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Tabela de dados mensais
        monthly_group  = QGroupBox('📅 Dados Mensais')
        monthly_layout = QVBoxLayout()

        self.monthly_table = QTableWidget()
        self.monthly_table.setColumnCount(7)
        self.monthly_table.setHorizontalHeaderLabels([
            'Mês', 'Entrada', 'Saída', 'Saldo',
            'Var. Entrada %', 'Var. Saída %', 'Tendência'
        ])
        self.monthly_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.monthly_table.horizontalHeader().setStretchLastSection(
            True
        )
        monthly_layout.addWidget(self.monthly_table)
        monthly_group.setLayout(monthly_layout)
        layout.addWidget(monthly_group)

        # Estatísticas
        stats_group  = QGroupBox('📊 Estatísticas do Período')
        stats_layout = QHBoxLayout()

        self.stats_income_text  = QTextEdit()
        self.stats_expense_text = QTextEdit()
        self.stats_balance_text = QTextEdit()

        for te in [
            self.stats_income_text,
            self.stats_expense_text,
            self.stats_balance_text
        ]:
            te.setReadOnly(True)
            te.setMaximumHeight(120)

        stats_layout.addWidget(self.stats_income_text)
        stats_layout.addWidget(self.stats_expense_text)
        stats_layout.addWidget(self.stats_balance_text)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        return widget

    def _build_insights_tab(self) -> QWidget:
        """Aba de insights da IA"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        ai_label = QLabel(
            '🤖 Insights gerados pela IA com base no seu '
            'histórico financeiro e filtros aplicados.'
        )
        ai_label.setWordWrap(True)
        ai_label.setStyleSheet(
            'color: #3498db; font-style: italic; padding: 5px;'
        )
        layout.addWidget(ai_label)

        self.insights_text = QTextEdit()
        self.insights_text.setReadOnly(True)
        layout.addWidget(self.insights_text)

        # Anomalias
        anomaly_group  = QGroupBox('🔍 Anomalias Detectadas')
        anomaly_layout = QVBoxLayout()

        self.anomaly_table = QTableWidget()
        self.anomaly_table.setColumnCount(4)
        self.anomaly_table.setHorizontalHeaderLabels([
            'Mês', 'Tipo', 'Valor', 'Desvio (Z-Score)'
        ])
        self.anomaly_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.anomaly_table.setMaximumHeight(150)
        self.anomaly_table.horizontalHeader().setStretchLastSection(
            True
        )
        anomaly_layout.addWidget(self.anomaly_table)
        anomaly_group.setLayout(anomaly_layout)
        layout.addWidget(anomaly_group)

        return widget

    def _build_categories_tab(self) -> QWidget:
        """Aba de tendências por categoria"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        hint = QLabel(
            '📂 Resumo das tendências de todas as categorias '
            'nos últimos 3 meses.'
        )
        hint.setStyleSheet('color: #7f8c8d; font-style: italic;')
        layout.addWidget(hint)

        self.categories_trend_table = QTableWidget()
        self.categories_trend_table.setColumnCount(6)
        self.categories_trend_table.setHorizontalHeaderLabels([
            'Categoria', 'Média Saída', 'Média Entrada',
            'Tend. Saída', 'Tend. Entrada', 'Insight'
        ])
        self.categories_trend_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.categories_trend_table.horizontalHeader().setStretchLastSection(
            True
        )
        layout.addWidget(self.categories_trend_table)

        return widget

    # ══════════════════════════════════════════════════════
    # CARREGAMENTO DE FILTROS
    # ══════════════════════════════════════════════════════

    def _load_filter_options(self):
        """Carrega opções nos combos de filtro"""
        # Categorias
        self.category_combo.clear()
        self.category_combo.addItem('Todas as categorias', None)
        categories = self.analyzer.get_categories()
        for cat in categories:
            self.category_combo.addItem(cat['name'], cat['id'])

        # Descrições
        self.description_combo.clear()
        self.description_combo.addItem('Todas as descrições', None)
        descriptions = self.analyzer.get_descriptions()
        for desc in descriptions:
            self.description_combo.addItem(desc['description'])

    # ══════════════════════════════════════════════════════
    # ANÁLISE PRINCIPAL
    # ══════════════════════════════════════════════════════

    def generate_analysis(self):
        """Gera análise completa com os filtros selecionados"""
        try:
            # Obter filtros
            period_map = {0: 3, 1: 6, 2: 12, 3: 60}
            months     = period_map.get(
                self.period_combo.currentIndex(), 6
            )

            type_map  = {0: None, 1: 'entrada', 2: 'saida'}
            trans_type = type_map.get(
                self.type_combo.currentIndex(), None
            )

            category_id = self.category_combo.currentData()

            desc_text = self.description_combo.currentText().strip()
            description = (
                desc_text
                if desc_text and desc_text != 'Todas as descrições'
                else None
            )

            # Executar análise
            self.current_result = self.analyzer.analyze(
                category_id=category_id,
                description=description,
                months=months,
                trans_type=trans_type
            )

            if not self.current_result.get('has_data'):
                self._show_no_data()
                return

            # Atualizar interface
            self._update_summary_cards()
            self._update_chart()
            self._update_details_table()
            self._update_insights()
            self._update_categories_tab()

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[TrendsDialog] Erro: {e}')

    def _show_no_data(self):
        """Exibe mensagem de sem dados"""
        self.insights_text.setHtml(
            '<p style="color:gray; text-align:center;">'
            'ℹ️ Não há dados suficientes para os filtros '
            'selecionados. Tente ajustar os filtros.</p>'
        )
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(
            0.5, 0.5,
            'Sem dados para os filtros selecionados',
            ha='center', va='center',
            transform=ax.transAxes, color='gray', fontsize=14
        )
        self.canvas.draw()

    def _update_summary_cards(self):
        """Atualiza os cards de resumo"""
        # Limpar cards anteriores
        while self.summary_layout.count():
            child = self.summary_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        r = self.current_result

        cards_data = [
            (
                '💰 Média de Entrada',
                f"R$ {r.get('avg_income', 0):,.2f}",
                r.get('income_direction', {}).get('color', '#2ecc71')
            ),
            (
                '💸 Média de Saída',
                f"R$ {r.get('avg_expense', 0):,.2f}",
                r.get('expense_direction', {}).get('color', '#e74c3c')
            ),
            (
                '📊 Saldo Médio',
                f"R$ {r.get('avg_balance', 0):,.2f}",
                '#3498db'
                if r.get('avg_balance', 0) >= 0
                else '#e74c3c'
            ),
            (
                '📈 Tend. Entrada',
                r.get('income_direction', {}).get('emoji', '➡️') +
                ' ' +
                r.get('income_direction', {}).get('label', 'Estável'),
                r.get('income_direction', {}).get('color', '#2ecc71')
            ),
            (
                '📉 Tend. Saída',
                r.get('expense_direction', {}).get('emoji', '➡️') +
                ' ' +
                r.get('expense_direction', {}).get('label', 'Estável'),
                r.get('expense_direction', {}).get('color', '#e74c3c')
            ),
        ]

        for title, value, color in cards_data:
            card = QFrame()
            card.setFrameStyle(QFrame.Box | QFrame.Raised)
            card.setLineWidth(1)
            card.setStyleSheet(
                f'border: 1px solid {color}; border-radius: 6px;'
            )
            card.setMinimumWidth(140)
            card.setMaximumHeight(80)

            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(8, 6, 8, 6)
            c_layout.setSpacing(2)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(
                'font-size: 10px; color: #7f8c8d; '
                'font-weight: bold; border: none;'
            )
            t_lbl.setAlignment(Qt.AlignCenter)

            v_lbl = QLabel(value)
            v_lbl.setStyleSheet(
                f'font-size: 13px; font-weight: bold; '
                f'color: {color}; border: none;'
            )
            v_lbl.setAlignment(Qt.AlignCenter)
            v_lbl.setWordWrap(True)

            c_layout.addWidget(t_lbl)
            c_layout.addWidget(v_lbl)
            self.summary_layout.addWidget(card)

    def _update_chart(self):
        """Atualiza o gráfico conforme tipo selecionado"""
        if not hasattr(self, 'current_result'):
            return
        if not self.current_result.get('has_data'):
            return

        r          = self.current_result
        months     = r.get('month_labels', [])
        income     = r.get('income_totals', [])
        expense    = r.get('expense_totals', [])
        balance    = r.get('balance_totals', [])
        chart_type = self.chart_type_combo.currentIndex()

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if self.is_dark_mode:
            plt.style.use('dark_background')
            income_color  = '#2ecc71'
            expense_color = '#e74c3c'
            balance_color = '#3498db'
        else:
            plt.style.use('default')
            income_color  = '#27ae60'
            expense_color = '#c0392b'
            balance_color = '#2980b9'

        x = np.arange(len(months))

        if chart_type == 0:
            # Barras agrupadas
            width = 0.35
            b1 = ax.bar(
                x - width/2, income, width,
                label='Entrada', color=income_color, alpha=0.8
            )
            b2 = ax.bar(
                x + width/2, expense, width,
                label='Saída', color=expense_color, alpha=0.8
            )
            ax.set_title('Entrada vs Saída por Mês')

            # Adicionar linha de tendência de saída
            if len(expense) >= 2:
                z   = np.polyfit(x, expense, 1)
                p   = np.poly1d(z)
                ax.plot(
                    x, p(x), '--',
                    color=expense_color, alpha=0.7,
                    label='Tend. Saída', linewidth=2
                )

        elif chart_type == 1:
            # Linha de saldo
            ax.plot(
                x, balance, 'o-',
                color=balance_color, linewidth=2.5,
                markersize=6, label='Saldo'
            )
            ax.fill_between(
                x, balance, 0,
                where=[b >= 0 for b in balance],
                color=income_color, alpha=0.2, label='Positivo'
            )
            ax.fill_between(
                x, balance, 0,
                where=[b < 0 for b in balance],
                color=expense_color, alpha=0.2, label='Negativo'
            )
            ax.axhline(y=0, color='gray', linestyle='-', alpha=0.4)
            ax.set_title('Evolução do Saldo Mensal')

        elif chart_type == 2:
            # Linhas com tendências
            ax.plot(
                x, income, 'o-',
                color=income_color, linewidth=2,
                markersize=5, label='Entrada'
            )
            ax.plot(
                x, expense, 's-',
                color=expense_color, linewidth=2,
                markersize=5, label='Saída'
            )

            # Linhas de tendência
            if len(income) >= 2:
                zi = np.polyfit(x, income, 1)
                pi = np.poly1d(zi)
                ax.plot(
                    x, pi(x), '--',
                    color=income_color, alpha=0.6,
                    linewidth=1.5, label='Tend. Entrada'
                )
            if len(expense) >= 2:
                ze = np.polyfit(x, expense, 1)
                pe = np.poly1d(ze)
                ax.plot(
                    x, pe(x), '--',
                    color=expense_color, alpha=0.6,
                    linewidth=1.5, label='Tend. Saída'
                )
            ax.set_title('Tendências de Entrada e Saída')

        elif chart_type == 3:
            # Área acumulada
            cumulative_income  = np.cumsum(income)
            cumulative_expense = np.cumsum(expense)
            ax.fill_between(
                x, cumulative_income, alpha=0.4,
                color=income_color, label='Entrada Acumulada'
            )
            ax.fill_between(
                x, cumulative_expense, alpha=0.4,
                color=expense_color, label='Saída Acumulada'
            )
            ax.plot(
                x, cumulative_income, color=income_color, linewidth=2
            )
            ax.plot(
                x, cumulative_expense, color=expense_color, linewidth=2
            )
            ax.set_title('Acumulado de Entradas e Saídas')

        # Configurações comuns
        ax.set_xticks(x)
        ax.set_xticklabels(
            months, rotation=45, ha='right', fontsize=8
        )
        ax.set_ylabel('Valores (R$)')
        ax.legend(fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(
                lambda val, _: f'R${val:,.0f}'
            )
        )

        # Marcar anomalias
        income_anomalies  = r.get('income_anomalies', [])
        expense_anomalies = r.get('expense_anomalies', [])

        all_months = r.get('month_labels', [])
        for anomaly in expense_anomalies:
            try:
                idx = r.get('months', []).index(anomaly['month'])
                ax.annotate(
                    f'⚠️',
                    xy=(idx, expense[idx]),
                    xytext=(0, 10),
                    textcoords='offset points',
                    ha='center', fontsize=10
                )
            except (ValueError, IndexError):
                pass

        self.figure.tight_layout()
        self.canvas.draw()

        # Atualizar legenda de tendência
        income_dir  = r.get('income_direction', {})
        expense_dir = r.get('expense_direction', {})
        balance_dir = r.get('balance_direction', {})

        legend_html = (
            f"<b>Entrada:</b> "
            f"<span style='color:{income_dir.get('color','#333')};'>"
            f"{income_dir.get('emoji','➡️')} "
            f"{income_dir.get('label','Estável')}</span>  |  "
            f"<b>Saída:</b> "
            f"<span style='color:{expense_dir.get('color','#333')};'>"
            f"{expense_dir.get('emoji','➡️')} "
            f"{expense_dir.get('label','Estável')}</span>  |  "
            f"<b>Saldo:</b> "
            f"<span style='color:{balance_dir.get('color','#333')};'>"
            f"{balance_dir.get('emoji','➡️')} "
            f"{balance_dir.get('label','Estável')}</span>"
        )
        self.trend_legend.setText(legend_html)
        self.trend_legend.setTextFormat(Qt.RichText)

    def _update_details_table(self):
        """Atualiza tabela de dados mensais"""
        r       = self.current_result
        months  = r.get('months', [])
        labels  = r.get('month_labels', [])
        income  = r.get('income_totals', [])
        expense = r.get('expense_totals', [])
        balance = r.get('balance_totals', [])
        i_mom   = r.get('income_mom', [])
        e_mom   = r.get('expense_mom', [])

        self.monthly_table.setRowCount(len(months))

        for i, (month, label) in enumerate(zip(months, labels)):
            inc = income[i]  if i < len(income)  else 0
            exp = expense[i] if i < len(expense) else 0
            bal = balance[i] if i < len(balance) else 0
            im  = i_mom[i]   if i < len(i_mom)   else 0
            em  = e_mom[i]   if i < len(e_mom)   else 0

            # Cor da linha
            if bal > 0:
                row_color = (
                    QColor('#1B5E20') if self.is_dark_mode
                    else QColor('#E8F5E9')
                )
            elif bal < 0:
                row_color = (
                    QColor('#B71C1C') if self.is_dark_mode
                    else QColor('#FFEBEE')
                )
            else:
                row_color = QColor('transparent')

            items = [
                QTableWidgetItem(label),
                QTableWidgetItem(f'R$ {inc:,.2f}'),
                QTableWidgetItem(f'R$ {exp:,.2f}'),
                QTableWidgetItem(f'R$ {bal:,.2f}'),
                QTableWidgetItem(
                    f'{im:+.1f}%' if im != 0 else '—'
                ),
                QTableWidgetItem(
                    f'{em:+.1f}%' if em != 0 else '—'
                ),
            ]

            # Tendência da linha
            if i >= 1:
                prev_bal = balance[i-1] if i-1 < len(balance) else 0
                if bal > prev_bal:
                    trend = '📈 Melhora'
                elif bal < prev_bal:
                    trend = '📉 Piora'
                else:
                    trend = '➡️ Igual'
            else:
                trend = '—'

            items.append(QTableWidgetItem(trend))

            for j, item in enumerate(items):
                item.setBackground(row_color)
                self.monthly_table.setItem(i, j, item)

            # Colorir variações
            if i < len(i_mom) and i_mom[i] != 0:
                color = (
                    QColor('#2ecc71') if i_mom[i] > 0
                    else QColor('#e74c3c')
                )
                self.monthly_table.item(i, 4).setForeground(color)

            if i < len(e_mom) and e_mom[i] != 0:
                color = (
                    QColor('#e74c3c') if e_mom[i] > 0
                    else QColor('#2ecc71')
                )
                self.monthly_table.item(i, 5).setForeground(color)

        self.monthly_table.resizeColumnsToContents()

        # Estatísticas
        r = self.current_result
        avg_i  = r.get('avg_income', 0)
        avg_e  = r.get('avg_expense', 0)
        avg_b  = r.get('avg_balance', 0)

        income_vals  = r.get('income_totals', [])
        expense_vals = r.get('expense_totals', [])

        max_i = max(income_vals)  if income_vals  else 0
        min_i = min(income_vals)  if income_vals  else 0
        max_e = max(expense_vals) if expense_vals else 0
        min_e = min(expense_vals) if expense_vals else 0

        self.stats_income_text.setHtml(f'''
            <b>💰 Estatísticas de Entrada</b><br>
            Média: <b>R$ {avg_i:,.2f}</b><br>
            Maior: <b>R$ {max_i:,.2f}</b><br>
            Menor: <b>R$ {min_i:,.2f}</b><br>
            Tendência: <b>
            {r.get('income_direction',{}).get('label','—')}</b>
        ''')

        self.stats_expense_text.setHtml(f'''
            <b>💸 Estatísticas de Saída</b><br>
            Média: <b>R$ {avg_e:,.2f}</b><br>
            Maior: <b>R$ {max_e:,.2f}</b><br>
            Menor: <b>R$ {min_e:,.2f}</b><br>
            Tendência: <b>
            {r.get('expense_direction',{}).get('label','—')}</b>
        ''')

        color = '#27ae60' if avg_b >= 0 else '#c0392b'
        self.stats_balance_text.setHtml(f'''
            <b>⚖️ Estatísticas de Saldo</b><br>
            Média: <b style="color:{color};">
            R$ {avg_b:,.2f}</b><br>
            Melhor mês: <b>R$ {max(r.get("balance_totals",[0])):,.2f}
            </b><br>
            Pior mês: <b>R$ {min(r.get("balance_totals",[0])):,.2f}
            </b><br>
            Tend. Saldo: <b>
            {r.get('balance_direction',{}).get('label','—')}</b>
        ''')

    def _update_insights(self):
        """Atualiza a aba de insights"""
        r        = self.current_result
        insights = r.get('insights', [])

        html = '<div style="font-size:13px;">'

        if not insights:
            html += (
                '<p style="color:gray;">'
                'ℹ️ Sem insights para os filtros selecionados.'
                '</p>'
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
                bg    = bg_map.get(ins.get('type', 'info'), '#f9f9f9')

                if self.is_dark_mode:
                    bg = 'transparent'

                html += (
                    f'<div style="margin:6px 0; padding:8px; '
                    f'border-left: 4px solid {color}; '
                    f'background-color:{bg}; border-radius:4px;">'
                    f'<span style="color:{color}; font-size:15px;">'
                    f'{ins.get("emoji","")}</span> '
                    f'<span style="color:{color}; font-weight:bold;">'
                    f'{ins.get("message","")}</span>'
                    f'</div>'
                )

        # Sazonalidade
        seasonality = r.get('seasonality', {})
        if seasonality.get('detected'):
            html += '<hr><b>🗓️ Sazonalidade Detectada:</b><br>'
            html += (
                f'• Mês com maior saída: '
                f'<b>{seasonality.get("peak_expense_label","N/A")}</b><br>'
            )
            html += (
                f'• Mês com maior entrada: '
                f'<b>{seasonality.get("peak_income_label","N/A")}</b>'
            )

        html += '</div>'
        self.insights_text.setHtml(html)

        # Anomalias
        all_anomalies = (
            r.get('income_anomalies', []) +
            r.get('expense_anomalies', [])
        )
        self.anomaly_table.setRowCount(len(all_anomalies))

        for i, anomaly in enumerate(all_anomalies):
            self.anomaly_table.setItem(
                i, 0, QTableWidgetItem(anomaly.get('label', ''))
            )
            tipo_item = QTableWidgetItem(
                '📈 Alta' if anomaly.get('type') == 'alto'
                else '📉 Baixa'
            )
            tipo_item.setForeground(
                QColor('#e74c3c') if anomaly.get('type') == 'alto'
                else QColor('#2ecc71')
            )
            self.anomaly_table.setItem(i, 1, tipo_item)
            self.anomaly_table.setItem(
                i, 2,
                QTableWidgetItem(
                    f"R$ {anomaly.get('value', 0):,.2f}"
                )
            )
            self.anomaly_table.setItem(
                i, 3,
                QTableWidgetItem(
                    str(anomaly.get('z_score', 0))
                )
            )

        self.anomaly_table.resizeColumnsToContents()

    def _update_categories_tab(self):
        """Atualiza aba de tendências por categoria"""
        summaries = self.analyzer.get_category_trend_summary()
        self.categories_trend_table.setRowCount(len(summaries))

        for i, cat in enumerate(summaries):
            self.categories_trend_table.setItem(
                i, 0, QTableWidgetItem(cat['category_name'])
            )
            self.categories_trend_table.setItem(
                i, 1,
                QTableWidgetItem(
                    f"R$ {cat.get('avg_expense', 0):,.2f}"
                )
            )
            self.categories_trend_table.setItem(
                i, 2,
                QTableWidgetItem(
                    f"R$ {cat.get('avg_income', 0):,.2f}"
                )
            )

            # Tendência saída
            exp_dir   = cat.get('expense_dir', {})
            exp_item  = QTableWidgetItem(
                f"{exp_dir.get('emoji','➡️')} "
                f"{exp_dir.get('label','Estável')}"
            )
            exp_item.setForeground(
                QColor(exp_dir.get('color', '#333'))
            )
            self.categories_trend_table.setItem(i, 3, exp_item)

            # Tendência entrada
            inc_dir  = cat.get('income_dir', {})
            inc_item = QTableWidgetItem(
                f"{inc_dir.get('emoji','➡️')} "
                f"{inc_dir.get('label','Estável')}"
            )
            inc_item.setForeground(
                QColor(inc_dir.get('color', '#333'))
            )
            self.categories_trend_table.setItem(i, 4, inc_item)

            # Insight resumido
            insights = cat.get('insights', [])
            insight_text = (
                insights[0].get('message', '')[:50]
                if insights else '—'
            )
            self.categories_trend_table.setItem(
                i, 5, QTableWidgetItem(insight_text)
            )

        self.categories_trend_table.resizeColumnsToContents()

    # ══════════════════════════════════════════════════════
    # EXPORTAR
    # ══════════════════════════════════════════════════════

    def export_analysis(self):
        """Exporta a análise atual para texto"""
        if not hasattr(self, 'current_result'):
            return
        if not self.current_result.get('has_data'):
            return

        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar Análise de Tendências',
            f'tendencias_{datetime.now().strftime("%Y%m%d")}.txt',
            'Arquivos de Texto (*.txt)'
        )
        if not file_path:
            return

        r      = self.current_result
        lines  = [
            'ANÁLISE DE TENDÊNCIAS FINANCEIRAS',
            f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}',
            '=' * 50,
            '',
            f'Média de Entrada: R$ {r.get("avg_income", 0):,.2f}',
            f'Média de Saída:   R$ {r.get("avg_expense", 0):,.2f}',
            f'Saldo Médio:      R$ {r.get("avg_balance", 0):,.2f}',
            '',
            f'Tendência Entrada: '
            f'{r.get("income_direction",{}).get("label","—")}',
            f'Tendência Saída:   '
            f'{r.get("expense_direction",{}).get("label","—")}',
            '',
            'DADOS MENSAIS:',
            '-' * 50
        ]

        months  = r.get('month_labels', [])
        income  = r.get('income_totals', [])
        expense = r.get('expense_totals', [])
        balance = r.get('balance_totals', [])

        for i, label in enumerate(months):
            inc = income[i]  if i < len(income)  else 0
            exp = expense[i] if i < len(expense) else 0
            bal = balance[i] if i < len(balance) else 0
            lines.append(
                f'{label}: Entrada R${inc:,.2f} | '
                f'Saída R${exp:,.2f} | Saldo R${bal:,.2f}'
            )

        lines += ['', 'INSIGHTS:', '-' * 50]
        for ins in r.get('insights', []):
            lines.append(f'• {ins.get("message", "")}')

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self, 'Sucesso',
                f'Análise exportada para:\n{file_path}'
            )
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 'Erro', f'Erro ao exportar: {str(e)}'
            )

    def apply_theme(self):
        """Aplica o tema"""
        if self.is_dark_mode:
            self.setStyleSheet('''
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QComboBox {
                    padding: 6px; border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
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
                }
                QTabBar::tab:selected { background-color: #3498db; }
                QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                }
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
                    background-color: #2196F3; color: white;
                }
                QPushButton:hover { background-color: #1976D2; }
                QTableWidget { background-color: white; }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc; background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333;
                    padding: 8px 12px; border: 1px solid #ccc;
                }
                QTabBar::tab:selected {
                    background-color: #2196F3; color: white;
                }
                QTextEdit {
                    background-color: white; border: 1px solid #ccc;
                    border-radius: 4px;
                }
            ''')
            plt.style.use('default')

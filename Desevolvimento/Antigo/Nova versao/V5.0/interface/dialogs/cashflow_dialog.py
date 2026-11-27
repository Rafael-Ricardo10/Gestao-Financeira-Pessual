"""
Diálogo de Fluxo de Caixa com IA integrada
Projeções inteligentes baseadas no histórico real
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
    QProgressBar, QFrame, QSlider, QSplitter
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from modulos.ai import FinanceAIEngine, FinanceForecaster


class CashFlowDialog(QDialog):
    """
    Diálogo de Fluxo de Caixa com IA integrada.
    Projeções inteligentes de entradas e saídas futuras.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('💰 Fluxo de Caixa com IA')
        self.setMinimumSize(1000, 720)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )

        # Inicializar IA
        self.ai_engine  = FinanceAIEngine(
            parent.db_connection, parent.user_id
        )
        self.forecaster = FinanceForecaster(
            parent.db_connection, parent.user_id, self.ai_engine
        )

        self._build_ui()
        self.generate_forecast()
        self.apply_theme()

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout(self)

        # ── Cabeçalho ────────────────────────────────────────
        header = QHBoxLayout()
        title  = QLabel('💰 Fluxo de Caixa')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        header.addWidget(title)

        ai_badge = QLabel('🤖 Projeções por IA')
        ai_badge.setStyleSheet(
            'background-color: #9b59b6; color: white;'
            'padding: 4px 8px; border-radius: 10px;'
            'font-size: 11px; font-weight: bold;'
        )
        header.addWidget(ai_badge)
        header.addStretch()
        layout.addLayout(header)

        # ── Controles ─────────────────────────────────────────
        controls_group  = QGroupBox('⚙️ Configurações da Projeção')
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel('Projetar:'))
        self.months_slider = QSlider(Qt.Horizontal)
        self.months_slider.setMinimum(1)
        self.months_slider.setMaximum(12)
        self.months_slider.setValue(3)
        self.months_slider.setTickPosition(QSlider.TicksBelow)
        self.months_slider.setTickInterval(1)
        self.months_slider.setMaximumWidth(200)
        self.months_slider.valueChanged.connect(
            self._update_slider_label
        )
        controls_layout.addWidget(self.months_slider)

        self.months_label = QLabel('3 meses')
        self.months_label.setMinimumWidth(70)
        controls_layout.addWidget(self.months_label)

        controls_layout.addWidget(QLabel('Visualização:'))
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems([
            'Barras (Entrada vs Saída)',
            'Linha (Saldo Projetado)',
            'Área (Acumulado)',
            'Detalhado por Categoria',
        ])
        controls_layout.addWidget(self.chart_type_combo)

        self.generate_btn = QPushButton('🔮 Gerar Projeção')
        self.generate_btn.clicked.connect(self.generate_forecast)
        controls_layout.addWidget(self.generate_btn)

        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # ── Cards de resumo ───────────────────────────────────
        self.summary_layout = QHBoxLayout()
        layout.addLayout(self.summary_layout)

        # ── Abas ─────────────────────────────────────────────
        self.tabs = QTabWidget()

        self.tabs.addTab(
            self._build_chart_tab(), '📊 Gráfico'
        )
        self.tabs.addTab(
            self._build_table_tab(), '📋 Tabela Detalhada'
        )
        self.tabs.addTab(
            self._build_predictions_tab(), '🔮 Previsões da IA'
        )
        self.tabs.addTab(
            self._build_category_tab(), '📂 Por Categoria'
        )

        layout.addWidget(self.tabs)

        # ── Confiança da IA ───────────────────────────────────
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel('Confiança da IA:'))

        self.confidence_bar = QProgressBar()
        self.confidence_bar.setMaximum(100)
        self.confidence_bar.setMinimumWidth(200)
        self.confidence_bar.setMaximumWidth(300)
        self.confidence_bar.setMaximumHeight(18)
        conf_layout.addWidget(self.confidence_bar)

        self.confidence_label = QLabel('0%')
        conf_layout.addWidget(self.confidence_label)
        conf_layout.addStretch()

        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(self.accept)
        conf_layout.addWidget(close_btn)
        layout.addLayout(conf_layout)

    def _build_chart_tab(self) -> QWidget:
        """Aba do gráfico principal"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.figure = plt.figure(figsize=(9, 4), dpi=95)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(300)
        layout.addWidget(self.canvas)

        # Resumo textual
        self.chart_summary = QTextEdit()
        self.chart_summary.setReadOnly(True)
        self.chart_summary.setMaximumHeight(100)
        layout.addWidget(self.chart_summary)

        return widget

    def _build_table_tab(self) -> QWidget:
        """Aba da tabela detalhada"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.forecast_table = QTableWidget()
        self.forecast_table.setColumnCount(6)
        self.forecast_table.setHorizontalHeaderLabels([
            'Mês', 'Entrada Prevista', 'Saída Prevista',
            'Saldo Previsto', 'Conf. Entrada %', 'Conf. Saída %'
        ])
        self.forecast_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.forecast_table.horizontalHeader().setStretchLastSection(
            True
        )
        layout.addWidget(self.forecast_table)

        # Totais
        totals_group  = QGroupBox('📊 Totais do Período Projetado')
        totals_layout = QHBoxLayout()

        self.total_income_label  = QLabel('Entrada Total: R$ 0,00')
        self.total_expense_label = QLabel('Saída Total: R$ 0,00')
        self.total_balance_label = QLabel('Saldo Final: R$ 0,00')

        for lbl in [
            self.total_income_label,
            self.total_expense_label,
            self.total_balance_label
        ]:
            lbl.setStyleSheet('font-weight: bold; font-size: 13px;')
            totals_layout.addWidget(lbl)

        totals_group.setLayout(totals_layout)
        layout.addWidget(totals_group)

        return widget

    def _build_predictions_tab(self) -> QWidget:
        """Aba de previsões específicas da IA"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        hint = QLabel(
            '🤖 Previsões específicas geradas pela IA '
            'baseadas nos padrões aprendidos do seu histórico.'
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            'color: #9b59b6; font-style: italic; padding: 5px;'
        )
        layout.addWidget(hint)

        self.ai_predictions_table = QTableWidget()
        self.ai_predictions_table.setColumnCount(5)
        self.ai_predictions_table.setHorizontalHeaderLabels([
            'Data Prevista', 'Tipo',
            'Categoria/Descrição', 'Valor Previsto', 'Confiança'
        ])
        self.ai_predictions_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.ai_predictions_table.horizontalHeader().setStretchLastSection(
            True
        )
        layout.addWidget(self.ai_predictions_table)

        # Acurácia histórica
        acc_group  = QGroupBox('🎯 Acurácia Histórica das Previsões')
        acc_layout = QVBoxLayout()

        self.acc_text = QTextEdit()
        self.acc_text.setReadOnly(True)
        self.acc_text.setMaximumHeight(100)
        acc_layout.addWidget(self.acc_text)
        acc_group.setLayout(acc_layout)
        layout.addWidget(acc_group)

        return widget

    def _build_category_tab(self) -> QWidget:
        """Aba de projeção por categoria"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        hint = QLabel(
            '📂 Projeção de gastos/receitas por categoria '
            'para o próximo mês.'
        )
        hint.setStyleSheet('color: #7f8c8d; font-style: italic;')
        layout.addWidget(hint)

        self.category_forecast_table = QTableWidget()
        self.category_forecast_table.setColumnCount(4)
        self.category_forecast_table.setHorizontalHeaderLabels([
            'Categoria', 'Tipo', 'Valor Previsto', 'Frequência'
        ])
        self.category_forecast_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.category_forecast_table.horizontalHeader().setStretchLastSection(
            True
        )
        layout.addWidget(self.category_forecast_table)

        return widget

    # ══════════════════════════════════════════════════════
    # SLIDER
    # ══════════════════════════════════════════════════════

    def _update_slider_label(self, value: int):
        """Atualiza label do slider"""
        self.months_label.setText(
            f'{value} {"mês" if value == 1 else "meses"}'
        )

    # ══════════════════════════════════════════════════════
    # GERAÇÃO DE PROJEÇÃO
    # ══════════════════════════════════════════════════════

    def generate_forecast(self):
        """Gera projeção completa com IA"""
        try:
            months = self.months_slider.value()
            result = self.forecaster.get_full_forecast(months)

            if not result.get('success'):
                self._show_error(result.get('error', 'Erro desconhecido'))
                return

            self.current_forecast = result

            self._update_summary_cards(result)
            self._update_chart(result)
            self._update_table(result)
            self._update_predictions_tab()
            self._update_category_tab(result)
            self._update_confidence(result)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(str(e))

    def _show_error(self, error: str):
        """Exibe mensagem de erro"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(
            0.5, 0.5,
            f'Erro ao gerar projeção:\n{error}',
            ha='center', va='center',
            transform=ax.transAxes,
            color='red', fontsize=12
        )
        self.canvas.draw()

    def _update_summary_cards(self, result: dict):
        """Atualiza cards de resumo"""
        while self.summary_layout.count():
            child = self.summary_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        total_income  = result.get('total_income', 0)
        total_expense = result.get('total_expense', 0)
        total_balance = result.get('total_balance', 0)
        months        = result.get('months_ahead', 1)
        confidence    = result.get('avg_confidence', 0)

        # Saldo atual
        transactions = self.parent().db_connection.execute(
            'SELECT * FROM transactions WHERE user_id = ?',
            (self.parent().user_id,)
        ).fetchall()
        current_balance = sum(
            t['amount'] if t['transaction_type'] == 'entrada'
            else -t['amount']
            for t in transactions
        )
        projected_final = current_balance + total_balance

        cards = [
            (
                '💰 Saldo Atual',
                f'R$ {current_balance:,.2f}',
                '#2ecc71' if current_balance >= 0 else '#e74c3c'
            ),
            (
                f'📈 Entradas ({months}m)',
                f'R$ {total_income:,.2f}',
                '#27ae60'
            ),
            (
                f'📉 Saídas ({months}m)',
                f'R$ {total_expense:,.2f}',
                '#c0392b'
            ),
            (
                f'⚖️ Saldo Projetado ({months}m)',
                f'R$ {total_balance:,.2f}',
                '#27ae60' if total_balance >= 0 else '#c0392b'
            ),
            (
                '🏁 Saldo Final Previsto',
                f'R$ {projected_final:,.2f}',
                '#2980b9' if projected_final >= 0 else '#e74c3c'
            ),
            (
                '🤖 Confiança IA',
                f'{confidence:.1f}%',
                '#9b59b6'
            ),
        ]

        for title, value, color in cards:
            card = QFrame()
            card.setFrameStyle(QFrame.Box | QFrame.Raised)
            card.setStyleSheet(
                f'border: 1px solid {color}; border-radius: 6px;'
            )
            card.setMinimumWidth(140)
            card.setMaximumHeight(80)

            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(8, 5, 8, 5)
            c_layout.setSpacing(2)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(
                'font-size: 10px; color: #7f8c8d; '
                'border: none; font-weight: bold;'
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

    def _update_chart(self, result: dict):
        """Atualiza o gráfico"""
        forecasts = result.get('forecasts', [])
        if not forecasts:
            return

        labels  = [f['month_label'] for f in forecasts]
        incomes = [f['predicted_income']  for f in forecasts]
        expenses= [f['predicted_expense'] for f in forecasts]
        balances= [f['predicted_balance'] for f in forecasts]

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if self.is_dark_mode:
            plt.style.use('dark_background')
            income_color  = '#2ecc71'
            expense_color = '#e74c3c'
            balance_color = '#3498db'
            bg_color      = '#1e272e'
        else:
            plt.style.use('default')
            income_color  = '#27ae60'
            expense_color = '#c0392b'
            balance_color = '#2980b9'
            bg_color      = 'white'

        x     = np.arange(len(labels))
        ctype = self.chart_type_combo.currentIndex()

        if ctype == 0:
            # Barras agrupadas
            width = 0.35
            bars1 = ax.bar(
                x - width/2, incomes, width,
                label='Entrada Prevista',
                color=income_color, alpha=0.8
            )
            bars2 = ax.bar(
                x + width/2, expenses, width,
                label='Saída Prevista',
                color=expense_color, alpha=0.8
            )

            # Valores nas barras
            for bar in bars1:
                h = bar.get_height()
                ax.annotate(
                    f'R${h:,.0f}',
                    xy=(bar.get_x() + bar.get_width()/2, h),
                    xytext=(0, 3), textcoords='offset points',
                    ha='center', va='bottom', fontsize=7
                )
            for bar in bars2:
                h = bar.get_height()
                ax.annotate(
                    f'R${h:,.0f}',
                    xy=(bar.get_x() + bar.get_width()/2, h),
                    xytext=(0, 3), textcoords='offset points',
                    ha='center', va='bottom', fontsize=7
                )

            ax.set_title('Projeção de Entrada vs Saída')

        elif ctype == 1:
            # Linha de saldo
            cumulative = [
                sum(balances[:i+1]) for i in range(len(balances))
            ]
            current_bal = sum(
                t['amount']
                if t['transaction_type'] == 'entrada'
                else -t['amount']
                for t in self.parent().db_connection.execute(
                    'SELECT * FROM transactions WHERE user_id = ?',
                    (self.parent().user_id,)
                ).fetchall()
            )
            cumulative = [
                current_bal + b for b in cumulative
            ]

            ax.plot(
                x, cumulative, 'o-',
                color=balance_color, linewidth=2.5,
                markersize=7, label='Saldo Projetado'
            )
            ax.fill_between(
                x, cumulative, current_bal,
                where=[c > current_bal for c in cumulative],
                color=income_color, alpha=0.2
            )
            ax.fill_between(
                x, cumulative, current_bal,
                where=[c <= current_bal for c in cumulative],
                color=expense_color, alpha=0.2
            )
            ax.axhline(
                y=current_bal, color='gray',
                linestyle='--', alpha=0.5,
                label=f'Saldo Atual R${current_bal:,.0f}'
            )
            ax.axhline(y=0, color='red', linestyle='-', alpha=0.3)

            # Anotar pontos
            for i, (xi, yi) in enumerate(zip(x, cumulative)):
                ax.annotate(
                    f'R${yi:,.0f}',
                    xy=(xi, yi), xytext=(0, 8),
                    textcoords='offset points',
                    ha='center', fontsize=8
                )

            ax.set_title('Evolução do Saldo Projetado')

        elif ctype == 2:
            # Área acumulada
            cum_income  = np.cumsum(incomes)
            cum_expense = np.cumsum(expenses)

            ax.fill_between(
                x, cum_income, alpha=0.5,
                color=income_color,
                label='Entradas Acumuladas'
            )
            ax.fill_between(
                x, cum_expense, alpha=0.5,
                color=expense_color,
                label='Saídas Acumuladas'
            )
            ax.plot(x, cum_income, color=income_color, linewidth=2)
            ax.plot(x, cum_expense, color=expense_color, linewidth=2)
            ax.set_title('Projeção Acumulada')

        elif ctype == 3:
            # Detalhado por categoria (stacked)
            if forecasts and forecasts[0].get('category_breakdown'):
                cats = {}
                for f in forecasts:
                    for cat in f.get('category_breakdown', []):
                        name = cat['category_name']
                        if name not in cats:
                            cats[name] = []
                        cats[name].append(cat['predicted_avg'])

                bottom = np.zeros(len(labels))
                colors = plt.cm.tab20.colors
                for ci, (cat_name, vals) in enumerate(
                    list(cats.items())[:10]
                ):
                    while len(vals) < len(labels):
                        vals.append(0)
                    ax.bar(
                        x, vals[:len(labels)],
                        bottom=bottom,
                        label=cat_name[:20],
                        color=colors[ci % len(colors)],
                        alpha=0.8
                    )
                    bottom += np.array(vals[:len(labels)])

                ax.set_title('Projeção por Categoria')
            else:
                ax.text(
                    0.5, 0.5,
                    'Dados insuficientes por categoria',
                    ha='center', va='center',
                    transform=ax.transAxes
                )

        # Config comum
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=9)
        ax.set_ylabel('Valores (R$)')
        ax.legend(fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f'R${v:,.0f}')
        )

        self.figure.tight_layout()
        self.canvas.draw()

        # Resumo textual
        total_i = result.get('total_income', 0)
        total_e = result.get('total_expense', 0)
        total_b = result.get('total_balance', 0)
        months  = result.get('months_ahead', 1)
        conf    = result.get('avg_confidence', 0)

        color_b = '#27ae60' if total_b >= 0 else '#c0392b'
        summary = (
            f'<b>Resumo dos próximos {months} meses:</b> '
            f'Entradas previstas: <b style="color:#27ae60;">'
            f'R$ {total_i:,.2f}</b> | '
            f'Saídas previstas: <b style="color:#c0392b;">'
            f'R$ {total_e:,.2f}</b> | '
            f'Saldo projetado: <b style="color:{color_b};">'
            f'R$ {total_b:,.2f}</b> | '
            f'Confiança da IA: <b style="color:#9b59b6;">'
            f'{conf:.1f}%</b>'
        )
        self.chart_summary.setHtml(summary)

    def _update_table(self, result: dict):
        """Atualiza tabela detalhada"""
        forecasts = result.get('forecasts', [])
        self.forecast_table.setRowCount(len(forecasts))

        for i, f in enumerate(forecasts):
            bal   = f['predicted_balance']
            color = (
                QColor('#1B5E20') if self.is_dark_mode
                else QColor('#E8F5E9')
            ) if bal >= 0 else (
                QColor('#B71C1C') if self.is_dark_mode
                else QColor('#FFEBEE')
            )

            items = [
                QTableWidgetItem(f['month_label']),
                QTableWidgetItem(
                    f"R$ {f['predicted_income']:,.2f}"
                ),
                QTableWidgetItem(
                    f"R$ {f['predicted_expense']:,.2f}"
                ),
                QTableWidgetItem(
                    f"R$ {f['predicted_balance']:,.2f}"
                ),
                QTableWidgetItem(
                    f"{f['income_confidence']*100:.0f}%"
                ),
                QTableWidgetItem(
                    f"{f['expense_confidence']*100:.0f}%"
                ),
            ]

            for j, item in enumerate(items):
                item.setBackground(color)
                self.forecast_table.setItem(i, j, item)

        self.forecast_table.resizeColumnsToContents()

        # Totais
        ti = result.get('total_income', 0)
        te = result.get('total_expense', 0)
        tb = result.get('total_balance', 0)

        self.total_income_label.setText(
            f'Entrada Total: R$ {ti:,.2f}'
        )
        self.total_income_label.setStyleSheet(
            'font-weight: bold; font-size: 13px; color: #27ae60;'
        )
        self.total_expense_label.setText(
            f'Saída Total: R$ {te:,.2f}'
        )
        self.total_expense_label.setStyleSheet(
            'font-weight: bold; font-size: 13px; color: #c0392b;'
        )
        color_b = '#27ae60' if tb >= 0 else '#c0392b'
        self.total_balance_label.setText(
            f'Saldo Final: R$ {tb:,.2f}'
        )
        self.total_balance_label.setStyleSheet(
            f'font-weight: bold; font-size: 13px; color: {color_b};'
        )

    def _update_predictions_tab(self):
        """Atualiza aba de previsões da IA"""
        predictions = self.forecaster.get_predictions_from_db()
        self.ai_predictions_table.setRowCount(len(predictions))

        for i, pred in enumerate(predictions):
            self.ai_predictions_table.setItem(
                i, 0,
                QTableWidgetItem(pred.get('target_date', ''))
            )

            type_map = {
                'entrada': '💰 Entrada',
                'saida':   '💸 Saída'
            }
            type_item = QTableWidgetItem(
                type_map.get(
                    pred.get('predicted_type', ''),
                    pred.get('predicted_type', '')
                )
            )
            type_item.setForeground(
                QColor('#2ecc71')
                if pred.get('predicted_type') == 'entrada'
                else QColor('#e74c3c')
            )
            self.ai_predictions_table.setItem(i, 1, type_item)

            ref = (
                pred.get('category_name') or
                pred.get('description') or
                'Desconhecido'
            )
            self.ai_predictions_table.setItem(
                i, 2, QTableWidgetItem(str(ref)[:40])
            )
            self.ai_predictions_table.setItem(
                i, 3,
                QTableWidgetItem(
                    f"R$ {pred.get('predicted_amount', 0):,.2f}"
                )
            )

            conf     = pred.get('confidence', 0)
            conf_pct = int(conf * 100)
            conf_bar = QProgressBar()
            conf_bar.setMaximum(100)
            conf_bar.setValue(conf_pct)
            conf_bar.setFormat(f'{conf_pct}%')
            if conf_pct >= 70:
                conf_bar.setStyleSheet(
                    'QProgressBar::chunk { background-color: #2ecc71; }'
                )
            elif conf_pct >= 40:
                conf_bar.setStyleSheet(
                    'QProgressBar::chunk { background-color: #f39c12; }'
                )
            else:
                conf_bar.setStyleSheet(
                    'QProgressBar::chunk { background-color: #e74c3c; }'
                )
            self.ai_predictions_table.setCellWidget(i, 4, conf_bar)

        self.ai_predictions_table.resizeColumnsToContents()

        # Acurácia histórica
        acc = self.forecaster.get_prediction_accuracy()
        total    = acc.get('total', 0)
        correct  = acc.get('correct', 0)
        accuracy = acc.get('accuracy', 0)
        avg_err  = acc.get('avg_error', 0)

        if total > 0:
            color = (
                '#27ae60' if accuracy >= 70 else
                '#f39c12' if accuracy >= 50 else '#e74c3c'
            )
            acc_html = (
                f'<b>Histórico de Precisão da IA:</b><br>'
                f'Total validadas: <b>{total}</b> | '
                f'Corretas: <b>{correct}</b> | '
                f'Acurácia: <b style="color:{color};">'
                f'{accuracy:.1f}%</b> | '
                f'Erro médio: <b>{avg_err:.1f}%</b>'
            )
        else:
            acc_html = (
                '<i style="color:gray;">Nenhuma previsão '
                'validada ainda. Continue usando o sistema '
                'para a IA aprender!</i>'
            )

        self.acc_text.setHtml(acc_html)

    def _update_category_tab(self, result: dict):
        """Atualiza aba de projeção por categoria"""
        forecasts = result.get('forecasts', [])
        if not forecasts:
            return

        # Usar o primeiro mês para o breakdown de categoria
        first_forecast = forecasts[0]
        breakdown      = first_forecast.get('category_breakdown', [])

        self.category_forecast_table.setRowCount(len(breakdown))

        for i, cat in enumerate(breakdown):
            trans_type = cat.get('trans_type', '')
            color = (
                QColor('#1B5E20') if (
                    trans_type == 'entrada' and self.is_dark_mode
                )
                else QColor('#E8F5E9') if trans_type == 'entrada'
                else QColor('#B71C1C') if self.is_dark_mode
                else QColor('#FFEBEE')
            )

            name_item = QTableWidgetItem(
                cat.get('category_name', '')
            )
            name_item.setBackground(color)
            self.category_forecast_table.setItem(i, 0, name_item)

            type_map  = {'entrada': '💰 Entrada', 'saida': '💸 Saída'}
            type_item = QTableWidgetItem(
                type_map.get(trans_type, trans_type)
            )
            type_item.setBackground(color)
            type_item.setForeground(
                QColor('#2ecc71') if trans_type == 'entrada'
                else QColor('#e74c3c')
            )
            self.category_forecast_table.setItem(i, 1, type_item)

            val_item = QTableWidgetItem(
                f"R$ {cat.get('predicted_avg', 0):,.2f}"
            )
            val_item.setBackground(color)
            self.category_forecast_table.setItem(i, 2, val_item)

            freq_item = QTableWidgetItem(
                f"{cat.get('frequency', 0)}x"
            )
            freq_item.setBackground(color)
            self.category_forecast_table.setItem(i, 3, freq_item)

        self.category_forecast_table.resizeColumnsToContents()

    def _update_confidence(self, result: dict):
        """Atualiza barra de confiança"""
        conf = result.get('avg_confidence', 0)
        self.confidence_bar.setValue(int(conf))
        self.confidence_bar.setFormat(f'{conf:.1f}%')
        self.confidence_label.setText(f'{conf:.1f}%')

        if conf >= 70:
            color = '#2ecc71'
            text  = 'Alta'
        elif conf >= 40:
            color = '#f39c12'
            text  = 'Média'
        else:
            color = '#e74c3c'
            text  = 'Baixa'

        self.confidence_bar.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {color}; }}'
        )
        self.confidence_label.setText(
            f'{conf:.1f}% ({text})'
        )
        self.confidence_label.setStyleSheet(f'color: {color};')

    def apply_theme(self):
        """Aplica o tema"""
        if self.is_dark_mode:
            self.setStyleSheet('''
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QComboBox, QSlider {
                    padding: 4px; border: 1px solid #4b6584;
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
                    background-color: #9b59b6; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #8e44ad; }
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
                QTabBar::tab:selected { background-color: #9b59b6; }
                QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 5px;
                    text-align: center; background-color: #2d3436;
                    color: #ecf0f1;
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
                    background-color: #9b59b6; color: white;
                }
                QPushButton:hover { background-color: #8e44ad; }
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
                    background-color: #9b59b6; color: white;
                }
                QTextEdit {
                    background-color: white; border: 1px solid #ccc;
                    border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 5px;
                    text-align: center;
                }
            ''')
            plt.style.use('default')

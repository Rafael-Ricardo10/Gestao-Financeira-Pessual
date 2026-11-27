"""
Diálogo de Fluxo de Caixa
Projeções baseadas em médias históricas reais
"""
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas
)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QGroupBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QFrame, QSlider
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class CashFlowDialog(QDialog):
    """
    Diálogo de Fluxo de Caixa.
    Projeções baseadas em médias e tendências históricas.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('💰 Fluxo de Caixa')
        self.setMinimumSize(1000, 720)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )
        self.db  = parent.db_connection
        self.uid = parent.user_id

        self._build_ui()
        self.generate_forecast()
        self.apply_theme()

    # ══════════════════════════════════════════════════════
    # INTERFACE
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout(self)

        # ── Cabeçalho ─────────────────────────────────────
        header = QHBoxLayout()
        title  = QLabel('💰 Fluxo de Caixa')
        title.setStyleSheet(
            'font-size: 18px; font-weight: bold;'
        )
        header.addWidget(title)

        badge = QLabel('📊 Projeções Estatísticas')
        badge.setStyleSheet(
            'background-color: #27ae60; color: white;'
            'padding: 4px 8px; border-radius: 10px;'
            'font-size: 11px; font-weight: bold;'
        )
        header.addWidget(badge)
        header.addStretch()
        layout.addLayout(header)

        # ── Controles ──────────────────────────────────────
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

        # ── Cards de resumo ───────────────────────────────
        self.summary_layout = QHBoxLayout()
        layout.addLayout(self.summary_layout)

        # ── Abas ──────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(
            self._build_chart_tab(), '📊 Gráfico'
        )
        self.tabs.addTab(
            self._build_table_tab(), '📋 Tabela Detalhada'
        )
        self.tabs.addTab(
            self._build_category_tab(), '📂 Por Categoria'
        )
        layout.addWidget(self.tabs)

        # ── Rodapé ────────────────────────────────────────
        footer_layout = QHBoxLayout()
        info_label    = QLabel(
            '💡 Projeções baseadas na média dos últimos 3 meses'
        )
        info_label.setStyleSheet(
            'color: #7f8c8d; font-style: italic; font-size: 11px;'
        )
        footer_layout.addWidget(info_label)
        footer_layout.addStretch()

        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(close_btn)
        layout.addLayout(footer_layout)

    def _build_chart_tab(self) -> QWidget:
        """Aba do gráfico principal"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.figure = plt.figure(figsize=(9, 4), dpi=95)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(300)
        layout.addWidget(self.canvas)

        self.chart_summary = QTextEdit()
        self.chart_summary.setReadOnly(True)
        self.chart_summary.setMaximumHeight(80)
        layout.addWidget(self.chart_summary)

        return widget

    def _build_table_tab(self) -> QWidget:
        """Aba da tabela detalhada"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.forecast_table = QTableWidget()
        self.forecast_table.setColumnCount(4)
        self.forecast_table.setHorizontalHeaderLabels([
            'Mês', 'Entrada Prevista',
            'Saída Prevista', 'Saldo Previsto'
        ])
        self.forecast_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.forecast_table.horizontalHeader(
        ).setStretchLastSection(True)
        layout.addWidget(self.forecast_table)

        totals_group  = QGroupBox('📊 Totais do Período Projetado')
        totals_layout = QHBoxLayout()

        self.total_income_label  = QLabel('Entrada Total: R$ 0,00')
        self.total_expense_label = QLabel('Saída Total:   R$ 0,00')
        self.total_balance_label = QLabel('Saldo Final:   R$ 0,00')

        for lbl in [
            self.total_income_label,
            self.total_expense_label,
            self.total_balance_label
        ]:
            lbl.setStyleSheet(
                'font-weight: bold; font-size: 13px;'
            )
            totals_layout.addWidget(lbl)

        totals_group.setLayout(totals_layout)
        layout.addWidget(totals_group)

        return widget

    def _build_category_tab(self) -> QWidget:
        """Aba de projeção por categoria"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        hint = QLabel(
            '📂 Média de gastos por categoria nos últimos 3 meses.'
        )
        hint.setStyleSheet(
            'color: #7f8c8d; font-style: italic;'
        )
        layout.addWidget(hint)

        self.category_forecast_table = QTableWidget()
        self.category_forecast_table.setColumnCount(4)
        self.category_forecast_table.setHorizontalHeaderLabels([
            'Categoria', 'Tipo', 'Média Mensal', 'Frequência'
        ])
        self.category_forecast_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.category_forecast_table.horizontalHeader(
        ).setStretchLastSection(True)
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
    # CÁLCULOS ESTATÍSTICOS
    # ══════════════════════════════════════════════════════

    def _get_monthly_data(self, months_back: int = 6) -> dict:
        """
        Busca dados mensais reais do banco de dados.

        Args:
            months_back: Quantos meses de histórico usar

        Returns:
            Dicionário com dados mensais de entrada e saída
        """
        since = (
            datetime.now() - relativedelta(months=months_back)
        ).strftime('%Y-%m-%d')

        rows = self.db.execute(
            '''SELECT
                strftime('%Y-%m', date) AS month,
                transaction_type,
                SUM(amount) AS total
               FROM transactions
               WHERE user_id = ? AND date >= ?
               GROUP BY month, transaction_type
               ORDER BY month''',
            (self.uid, since)
        ).fetchall()

        monthly = {}
        for row in rows:
            m = row['month']
            if m not in monthly:
                monthly[m] = {'entrada': 0.0, 'saida': 0.0}
            monthly[m][row['transaction_type']] = (
                float(row['total'])
            )

        return monthly

    def _calculate_forecast(self, months_ahead: int) -> dict:
        """
        Calcula projeção usando média ponderada dos últimos meses.

        Args:
            months_ahead: Quantos meses projetar

        Returns:
            Dicionário com resultado da projeção
        """
        monthly = self._get_monthly_data(months_back=6)

        if not monthly:
            return {'success': False, 'error': 'Sem dados históricos'}

        income_vals  = [v['entrada'] for v in monthly.values()]
        expense_vals = [v['saida']   for v in monthly.values()]

        # Média ponderada - meses mais recentes têm mais peso
        n = len(income_vals)
        weights = np.arange(1, n + 1, dtype=float)
        weights = weights / weights.sum()

        avg_income  = float(np.average(income_vals,  weights=weights))
        avg_expense = float(np.average(expense_vals, weights=weights))

        # Tendência linear
        if n >= 2:
            x = np.arange(n)
            income_trend  = np.polyfit(x, income_vals,  1)[0]
            expense_trend = np.polyfit(x, expense_vals, 1)[0]
        else:
            income_trend  = 0.0
            expense_trend = 0.0

        # Gerar projeção mês a mês
        forecasts = []
        for i in range(1, months_ahead + 1):
            future_date  = datetime.now() + relativedelta(months=i)
            month_label  = future_date.strftime('%b/%Y')

            # Aplicar tendência suavizada (50% da tendência)
            proj_income  = max(
                0, avg_income  + income_trend  * i * 0.5
            )
            proj_expense = max(
                0, avg_expense + expense_trend * i * 0.5
            )
            proj_balance = proj_income - proj_expense

            forecasts.append({
                'month_label':      month_label,
                'predicted_income':  proj_income,
                'predicted_expense': proj_expense,
                'predicted_balance': proj_balance,
            })

        total_income  = sum(f['predicted_income']  for f in forecasts)
        total_expense = sum(f['predicted_expense'] for f in forecasts)
        total_balance = sum(f['predicted_balance'] for f in forecasts)

        return {
            'success':       True,
            'forecasts':     forecasts,
            'total_income':  total_income,
            'total_expense': total_expense,
            'total_balance': total_balance,
            'months_ahead':  months_ahead,
            'avg_income':    avg_income,
            'avg_expense':   avg_expense,
        }

    def _get_category_forecast(self) -> list:
        """
        Calcula média mensal por categoria dos últimos 3 meses.

        Returns:
            Lista de categorias com médias mensais
        """
        since = (
            datetime.now() - relativedelta(months=3)
        ).strftime('%Y-%m-%d')

        rows = self.db.execute(
            '''SELECT
                c.name AS category_name,
                t.transaction_type,
                COUNT(*) AS frequency,
                AVG(t.amount) AS avg_amount
               FROM transactions t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ? AND t.date >= ?
               AND c.name IS NOT NULL
               GROUP BY c.name, t.transaction_type
               ORDER BY avg_amount DESC''',
            (self.uid, since)
        ).fetchall()

        return [dict(row) for row in rows]

    def _get_current_balance(self) -> float:
        """Retorna o saldo atual do usuário"""
        rows = self.db.execute(
            'SELECT transaction_type, SUM(amount) as total '
            'FROM transactions WHERE user_id = ? '
            'GROUP BY transaction_type',
            (self.uid,)
        ).fetchall()

        balance = 0.0
        for row in rows:
            if row['transaction_type'] == 'entrada':
                balance += float(row['total'] or 0)
            else:
                balance -= float(row['total'] or 0)
        return balance

    # ══════════════════════════════════════════════════════
    # GERAÇÃO DE PROJEÇÃO
    # ══════════════════════════════════════════════════════

    def generate_forecast(self):
        """Gera projeção completa"""
        try:
            months = self.months_slider.value()
            result = self._calculate_forecast(months)

            if not result.get('success'):
                self._show_error(
                    result.get('error', 'Erro desconhecido')
                )
                return

            self.current_forecast = result

            self._update_summary_cards(result)
            self._update_chart(result)
            self._update_table(result)
            self._update_category_tab()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(str(e))

    def _show_error(self, error: str):
        """Exibe mensagem de erro no gráfico"""
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

    # ══════════════════════════════════════════════════════
    # ATUALIZAÇÃO DA INTERFACE
    # ══════════════════════════════════════════════════════

    def _update_summary_cards(self, result: dict):
        """Atualiza cards de resumo"""
        while self.summary_layout.count():
            child = self.summary_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        total_income   = result.get('total_income',  0)
        total_expense  = result.get('total_expense', 0)
        total_balance  = result.get('total_balance', 0)
        months         = result.get('months_ahead',  1)
        current_balance = self._get_current_balance()
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
                f'⚖️ Resultado ({months}m)',
                f'R$ {total_balance:,.2f}',
                '#27ae60' if total_balance >= 0 else '#c0392b'
            ),
            (
                '🏁 Saldo Final Previsto',
                f'R$ {projected_final:,.2f}',
                '#2980b9' if projected_final >= 0 else '#e74c3c'
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
        """Atualiza o gráfico conforme tipo selecionado"""
        forecasts = result.get('forecasts', [])
        if not forecasts:
            return

        labels   = [f['month_label']      for f in forecasts]
        incomes  = [f['predicted_income']  for f in forecasts]
        expenses = [f['predicted_expense'] for f in forecasts]
        balances = [f['predicted_balance'] for f in forecasts]

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
            # Linha de saldo acumulado
            current_bal = self._get_current_balance()
            cumulative  = [
                current_bal + sum(balances[:i+1])
                for i in range(len(balances))
            ]

            ax.plot(
                x, cumulative, 'o-',
                color=balance_color, linewidth=2.5,
                markersize=7, label='Saldo Projetado'
            )
            ax.fill_between(
                x, cumulative, current_bal,
                where=[c >= current_bal for c in cumulative],
                color=income_color, alpha=0.2
            )
            ax.fill_between(
                x, cumulative, current_bal,
                where=[c < current_bal for c in cumulative],
                color=expense_color, alpha=0.2
            )
            ax.axhline(
                y=current_bal, color='gray',
                linestyle='--', alpha=0.5,
                label=f'Saldo Atual R${current_bal:,.0f}'
            )
            ax.axhline(
                y=0, color='red', linestyle='-', alpha=0.3
            )

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
            ax.plot(
                x, cum_income,
                color=income_color, linewidth=2
            )
            ax.plot(
                x, cum_expense,
                color=expense_color, linewidth=2
            )
            ax.set_title('Projeção Acumulada')

        elif ctype == 3:
            # Por categoria
            cats = self._get_category_forecast()
            if cats:
                cat_names = [
                    c['category_name'][:15] for c in cats[:8]
                ]
                cat_vals  = [
                    c['avg_amount'] for c in cats[:8]
                ]
                colors_list = [
                    income_color
                    if c['transaction_type'] == 'entrada'
                    else expense_color
                    for c in cats[:8]
                ]
                ax.barh(
                    cat_names, cat_vals,
                    color=colors_list, alpha=0.8
                )
                ax.set_title('Média Mensal por Categoria')
                ax.set_xlabel('Valor Médio (R$)')
            else:
                ax.text(
                    0.5, 0.5,
                    'Dados insuficientes por categoria',
                    ha='center', va='center',
                    transform=ax.transAxes
                )

        # Configurações comuns
        if ctype != 3:
            ax.set_xticks(x)
            ax.set_xticklabels(
                labels, rotation=30, ha='right', fontsize=9
            )
        ax.set_ylabel('Valores (R$)')
        ax.legend(fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f'R${v:,.0f}')
        )

        self.figure.tight_layout()
        self.canvas.draw()

        # Resumo textual
        ti     = result.get('total_income',  0)
        te     = result.get('total_expense', 0)
        tb     = result.get('total_balance', 0)
        months = result.get('months_ahead',  1)
        color_b = '#27ae60' if tb >= 0 else '#c0392b'

        summary = (
            f'<b>Resumo dos próximos {months} meses:</b> '
            f'Entradas previstas: <b style="color:#27ae60;">'
            f'R$ {ti:,.2f}</b> | '
            f'Saídas previstas: <b style="color:#c0392b;">'
            f'R$ {te:,.2f}</b> | '
            f'Saldo projetado: <b style="color:{color_b};">'
            f'R$ {tb:,.2f}</b>'
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
            ]

            for j, item in enumerate(items):
                item.setBackground(color)
                self.forecast_table.setItem(i, j, item)

        self.forecast_table.resizeColumnsToContents()

        ti = result.get('total_income',  0)
        te = result.get('total_expense', 0)
        tb = result.get('total_balance', 0)

        self.total_income_label.setText(
            f'Entrada Total: R$ {ti:,.2f}'
        )
        self.total_income_label.setStyleSheet(
            'font-weight: bold; font-size: 13px; color: #27ae60;'
        )
        self.total_expense_label.setText(
            f'Saída Total:   R$ {te:,.2f}'
        )
        self.total_expense_label.setStyleSheet(
            'font-weight: bold; font-size: 13px; color: #c0392b;'
        )
        color_b = '#27ae60' if tb >= 0 else '#c0392b'
        self.total_balance_label.setText(
            f'Saldo Final:   R$ {tb:,.2f}'
        )
        self.total_balance_label.setStyleSheet(
            f'font-weight: bold; font-size: 13px; color: {color_b};'
        )

    def _update_category_tab(self):
        """Atualiza aba de projeção por categoria"""
        cats = self._get_category_forecast()
        self.category_forecast_table.setRowCount(len(cats))

        for i, cat in enumerate(cats):
            trans_type = cat.get('transaction_type', '')
            color = (
                QColor('#1B5E20') if (
                    trans_type == 'entrada' and self.is_dark_mode
                )
                else QColor('#E8F5E9') if trans_type == 'entrada'
                else QColor('#B71C1C') if self.is_dark_mode
                else QColor('#FFEBEE')
            )

            name_item = QTableWidgetItem(
                cat.get('category_name', 'Sem categoria')
            )
            name_item.setBackground(color)
            self.category_forecast_table.setItem(i, 0, name_item)

            type_map  = {
                'entrada': '💰 Entrada',
                'saida':   '💸 Saída'
            }
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
                f"R$ {cat.get('avg_amount', 0):,.2f}"
            )
            val_item.setBackground(color)
            self.category_forecast_table.setItem(i, 2, val_item)

            freq_item = QTableWidgetItem(
                f"{cat.get('frequency', 0)}x"
            )
            freq_item.setBackground(color)
            self.category_forecast_table.setItem(i, 3, freq_item)

        self.category_forecast_table.resizeColumnsToContents()

    # ══════════════════════════════════════════════════════
    # TEMA
    # ══════════════════════════════════════════════════════

    def apply_theme(self):
        """Aplica o tema claro ou escuro"""
        if self.is_dark_mode:
            self.setStyleSheet('''
                QDialog {
                    background-color: #1e272e; color: #ecf0f1;
                }
                QLabel { color: #ecf0f1; }
                QComboBox, QSlider {
                    padding: 4px; border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QGroupBox {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    margin-top: 10px;
                    color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px; padding: 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #27ae60; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #219a52; }
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
                QTabBar::tab:selected {
                    background-color: #27ae60;
                }
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
                    background-color: #27ae60; color: white;
                }
                QPushButton:hover { background-color: #219a52; }
                QTableWidget { background-color: white; }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333;
                    padding: 8px 12px; border: 1px solid #ccc;
                }
                QTabBar::tab:selected {
                    background-color: #27ae60; color: white;
                }
                QTextEdit {
                    background-color: white;
                    border: 1px solid #ccc; border-radius: 4px;
                }
            ''')
            plt.style.use('default')

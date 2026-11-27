"""
Diálogos para relatórios, gráficos e análises financeiras
"""
import random
import numpy as np
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QSlider, QWidget, QCalendarWidget, QProgressBar, QMessageBox
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QTextCharFormat


class CalendarDialog(QDialog):
    """Diálogo para visualizar transações em formato de calendário"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calendário Financeiro")
        self.resize(800, 600)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(
            QCalendarWidget.NoVerticalHeader
        )
        self.calendar.setSelectionMode(QCalendarWidget.SingleSelection)
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

        self.transactions_label = QLabel("Transações do dia selecionado:")
        self.transactions_list = QTextEdit()
        self.transactions_list.setReadOnly(True)

        self.month_stats_label = QLabel("Estatísticas do Mês:")
        self.month_stats = QTextEdit()
        self.month_stats.setReadOnly(True)
        self.month_stats.setMaximumHeight(100)

        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        self.calendar.selectionChanged.connect(self.update_day_transactions)
        self.calendar.currentPageChanged.connect(self.update_calendar_data)

        layout = QVBoxLayout()
        layout.addWidget(self.calendar)

        split_layout = QHBoxLayout()

        trans_layout = QVBoxLayout()
        trans_layout.addWidget(self.transactions_label)
        trans_layout.addWidget(self.transactions_list)

        stats_layout = QVBoxLayout()
        stats_layout.addWidget(self.month_stats_label)
        stats_layout.addWidget(self.month_stats)

        split_layout.addLayout(trans_layout, 7)
        split_layout.addLayout(stats_layout, 3)

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)
        self.update_calendar_data()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QTextEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QCalendarWidget { background-color: #2d3436; color: #ecf0f1; }
                QCalendarWidget QAbstractItemView:enabled {
                    color: #ecf0f1; background-color: #2d3436;
                    selection-background-color: #3498db;
                    selection-color: #ecf0f1;
                }
                QCalendarWidget QToolButton {
                    color: #ecf0f1; background-color: #2d3436;
                }
            """)
            self.close_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QTextEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
                QCalendarWidget { background-color: white; }
                QCalendarWidget QAbstractItemView:enabled {
                    color: #333; selection-background-color: #4CAF50;
                    selection-color: white;
                }
            """)
            self.close_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def update_calendar_data(self):
        """Atualiza os dados do calendário para o mês exibido"""
        try:
            current_date = self.calendar.selectedDate()
            year = current_date.year()
            month = current_date.month()

            self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

            transactions = self.parent().db_connection.execute(
                '''SELECT t.*, c.name as category_name
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND strftime('%Y', t.date) = ?
                   AND strftime('%m', t.date) = ?
                   ORDER BY t.date''',
                (self.parent().user_id,
                 f"{year:04d}", f"{month:02d}")
            ).fetchall()

            day_balances = {}
            day_transactions = {}

            for t in transactions:
                date = QDate.fromString(t['date'], "yyyy-MM-dd")
                day_key = date.toString("yyyy-MM-dd")

                if day_key not in day_balances:
                    day_balances[day_key] = 0
                    day_transactions[day_key] = []

                amount = t['amount']
                if t['transaction_type'] == 'saida':
                    amount = -amount

                day_balances[day_key] += amount
                day_transactions[day_key].append(t)

            positive_format = QTextCharFormat()
            positive_format.setBackground(QColor(200, 255, 200))
            positive_format.setForeground(QColor(0, 100, 0))

            negative_format = QTextCharFormat()
            negative_format.setBackground(QColor(255, 200, 200))
            negative_format.setForeground(QColor(150, 0, 0))

            neutral_format = QTextCharFormat()
            neutral_format.setBackground(QColor(220, 220, 220))
            neutral_format.setForeground(QColor(50, 50, 50))

            for day_key, balance in day_balances.items():
                date = QDate.fromString(day_key, "yyyy-MM-dd")
                if balance > 0:
                    self.calendar.setDateTextFormat(date, positive_format)
                elif balance < 0:
                    self.calendar.setDateTextFormat(date, negative_format)
                else:
                    self.calendar.setDateTextFormat(date, neutral_format)

            total_income = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )
            total_expense = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'saida'
            )
            balance = total_income - total_expense
            active_days = len(day_balances)

            stats_text = (
                f"<b>Estatísticas de "
                f"{current_date.toString('MMMM yyyy').capitalize()}:</b><br>"
                f"Receitas: <span style='color:green;'>R$ {total_income:.2f}</span><br>"
                f"Despesas: <span style='color:red;'>R$ {total_expense:.2f}</span><br>"
            )

            if balance >= 0:
                stats_text += (
                    f"Saldo: <span style='color:green;'>R$ {balance:.2f}</span><br>"
                )
            else:
                stats_text += (
                    f"Saldo: <span style='color:red;'>R$ {balance:.2f}</span><br>"
                )

            stats_text += f"Dias com movimento: {active_days}"
            self.month_stats.setHtml(stats_text)
            self.update_day_transactions()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.month_stats.setText(f"Erro ao carregar estatísticas: {str(e)}")

    def update_day_transactions(self):
        """Atualiza a lista de transações do dia selecionado"""
        try:
            selected_date = self.calendar.selectedDate().toString("yyyy-MM-dd")

            transactions = self.parent().db_connection.execute(
                '''SELECT t.*, c.name as category_name
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ? AND t.date = ?
                   ORDER BY t.transaction_type, t.amount DESC''',
                (self.parent().user_id, selected_date)
            ).fetchall()

            if not transactions:
                self.transactions_list.setHtml(
                    "<i>Nenhuma transação neste dia.</i>"
                )
                return

            total_income = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )
            total_expense = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'saida'
            )
            day_balance = total_income - total_expense

            html = (
                f"<h3>Transações de "
                f"{self.calendar.selectedDate().toString('dd/MM/yyyy')}</h3>"
                f"<p>Receitas: <b style='color:green;'>R$ {total_income:.2f}</b> | "
                f"Despesas: <b style='color:red;'>R$ {total_expense:.2f}</b> | "
            )

            if day_balance >= 0:
                html += (
                    f"Saldo: <b style='color:green;'>R$ {day_balance:.2f}</b></p>"
                )
            else:
                html += (
                    f"Saldo: <b style='color:red;'>R$ {day_balance:.2f}</b></p>"
                )

            html += (
                "<table width='100%' cellspacing='0' cellpadding='4' "
                "style='border: 1px solid #ccc;'>"
                "<tr style='background-color: #f0f0f0;'>"
                "<th align='left'>Descrição</th>"
                "<th align='right'>Valor</th>"
                "<th align='left'>Tipo</th>"
                "<th align='left'>Categoria</th></tr>"
            )

            row1 = "background-color: #ffffff;"
            row2 = "background-color: #f9f9f9;"
            current_style = row1

            for t in transactions:
                html += f"<tr style='{current_style}'>"
                html += f"<td>{t['description']}</td>"

                if t['transaction_type'] == 'entrada':
                    html += (
                        f"<td align='right' style='color:green;'>"
                        f"R$ {t['amount']:.2f}</td>"
                        f"<td>Receita</td>"
                    )
                else:
                    html += (
                        f"<td align='right' style='color:red;'>"
                        f"R$ {t['amount']:.2f}</td>"
                        f"<td>Despesa</td>"
                    )

                html += (
                    f"<td>{t['category_name'] or 'Sem categoria'}</td>"
                    f"</tr>"
                )
                current_style = row2 if current_style == row1 else row1

            html += "</table>"
            self.transactions_list.setHtml(html)

        except Exception as e:
            self.transactions_list.setText(
                f"Erro ao carregar transações: {str(e)}"
            )


class CashFlowDialog(QDialog):
    """Diálogo para visualizar e projetar fluxo de caixa"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Previsão de Fluxo de Caixa")
        self.resize(800, 600)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.months_label = QLabel("Meses para projetar:")
        self.months_slider = QSlider(Qt.Horizontal)
        self.months_slider.setMinimum(1)
        self.months_slider.setMaximum(12)
        self.months_slider.setValue(3)
        self.months_slider.setTickPosition(QSlider.TicksBelow)
        self.months_slider.setTickInterval(1)
        self.months_value_label = QLabel("3 meses")

        self.generate_button = QPushButton("Gerar Projeção")
        self.generate_button.clicked.connect(self.generate_projection)

        self.figure = plt.figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)

        self.projection_table = QTableWidget()
        self.projection_table.setColumnCount(4)
        self.projection_table.setHorizontalHeaderLabels([
            "Mês", "Receitas", "Despesas", "Saldo"
        ])
        self.projection_table.horizontalHeader().setStretchLastSection(True)

        self.summary_label = QLabel("Resumo da Projeção:")
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(100)

        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        self.months_slider.valueChanged.connect(self.update_months_label)

        layout = QVBoxLayout()

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.months_label)
        controls_layout.addWidget(self.months_slider)
        controls_layout.addWidget(self.months_value_label)
        controls_layout.addWidget(self.generate_button)
        layout.addLayout(controls_layout)

        split_layout = QHBoxLayout()

        chart_layout = QVBoxLayout()
        chart_layout.addWidget(self.canvas)

        table_layout = QVBoxLayout()
        table_layout.addWidget(self.projection_table)
        table_layout.addWidget(self.summary_label)
        table_layout.addWidget(self.summary_text)

        split_layout.addLayout(chart_layout, 6)
        split_layout.addLayout(table_layout, 4)
        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)
        self.generate_projection()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QTextEdit, QTableWidget {
                    border: 1px solid #4b6584; border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                    padding: 5px; border: 1px solid #4b6584;
                }
            """)
            self.close_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
            self.generate_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            plt.style.use('dark_background')
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QTextEdit, QTableWidget {
                    border: 1px solid #ccc; border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.close_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )
            self.generate_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            plt.style.use('default')

    def update_months_label(self, value):
        """Atualiza o label com o valor do slider"""
        self.months_value_label.setText(
            f"{value} {'mês' if value == 1 else 'meses'}"
        )

    def generate_projection(self):
        """Gera a projeção de fluxo de caixa"""
        try:
            months_to_project = self.months_slider.value()
            today = datetime.now()
            current_month = today.month
            current_year = today.year

            six_months_ago = today.replace(day=1) - timedelta(days=1)
            for _ in range(5):
                six_months_ago = (
                    six_months_ago.replace(day=1) - timedelta(days=1)
                )
            six_months_ago_str = six_months_ago.strftime('%Y-%m-%d')

            monthly_stats = self.parent().db_connection.execute(
                '''SELECT
                       strftime('%Y-%m', date) as month,
                       SUM(CASE WHEN transaction_type='entrada'
                           THEN amount ELSE 0 END) as income,
                       SUM(CASE WHEN transaction_type='saida'
                           THEN amount ELSE 0 END) as expense
                   FROM transactions
                   WHERE user_id = ? AND date >= ?
                   GROUP BY month ORDER BY month''',
                (self.parent().user_id, six_months_ago_str)
            ).fetchall()

            if not monthly_stats:
                avg_income = 1000
                avg_expense = 800
            else:
                avg_income = (
                    sum(m['income'] for m in monthly_stats) /
                    len(monthly_stats)
                )
                avg_expense = (
                    sum(m['expense'] for m in monthly_stats) /
                    len(monthly_stats)
                )

            transactions = self.parent().db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?',
                (self.parent().user_id,)
            ).fetchall()

            entries_total = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )
            exits_total = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'saida'
            )
            current_balance = entries_total - exits_total

            months = []
            incomes = []
            expenses = []
            balances = []
            running_balance = current_balance

            for i in range(months_to_project):
                month_num = (current_month + i) % 12
                if month_num == 0:
                    month_num = 12
                year_num = current_year + (current_month + i - 1) // 12

                month_name = QDate(year_num, month_num, 1).toString("MMM yyyy")
                months.append(month_name)

                variation = 0.1
                month_income = avg_income * (
                    1 + (random.random() * variation - variation / 2)
                )
                month_expense = avg_expense * (
                    1 + (random.random() * variation - variation / 2)
                )

                incomes.append(month_income)
                expenses.append(month_expense)
                running_balance += month_income - month_expense
                balances.append(running_balance)

            # Atualizar tabela
            self.projection_table.setRowCount(months_to_project)
            for i in range(months_to_project):
                self.projection_table.setItem(
                    i, 0, QTableWidgetItem(months[i])
                )

                income_item = QTableWidgetItem(f"R$ {incomes[i]:.2f}")
                income_item.setForeground(QColor(0, 128, 0))
                self.projection_table.setItem(i, 1, income_item)

                expense_item = QTableWidgetItem(f"R$ {expenses[i]:.2f}")
                expense_item.setForeground(QColor(200, 0, 0))
                self.projection_table.setItem(i, 2, expense_item)

                balance_item = QTableWidgetItem(f"R$ {balances[i]:.2f}")
                balance_item.setForeground(
                    QColor(0, 128, 0) if balances[i] >= 0
                    else QColor(200, 0, 0)
                )
                self.projection_table.setItem(i, 3, balance_item)

            self.projection_table.resizeColumnsToContents()

            # Resumo
            final_balance = balances[-1]
            total_projected_income = sum(incomes)
            total_projected_expense = sum(expenses)
            monthly_avg_balance = sum(
                inc - exp for inc, exp in zip(incomes, expenses)
            ) / months_to_project

            summary_html = (
                f"<b>Resumo da Projeção:</b><br>"
                f"Saldo atual: <b>R$ {current_balance:.2f}</b><br>"
                f"Saldo projetado em {months_to_project} meses: "
                f"<b>R$ {final_balance:.2f}</b><br>"
                f"Receitas projetadas: "
                f"<b style='color:green;'>R$ {total_projected_income:.2f}</b><br>"
                f"Despesas projetadas: "
                f"<b style='color:red;'>R$ {total_projected_expense:.2f}</b><br>"
            )

            if monthly_avg_balance >= 0:
                summary_html += (
                    f"Saldo médio mensal: "
                    f"<b style='color:green;'>R$ {monthly_avg_balance:.2f}</b>"
                )
            else:
                summary_html += (
                    f"Saldo médio mensal: "
                    f"<b style='color:red;'>R$ {monthly_avg_balance:.2f}</b>"
                )

            self.summary_text.setHtml(summary_html)

            # Gráfico
            self.figure.clear()
            ax = self.figure.add_subplot(111)

            bar_width = 0.35
            x = np.arange(len(months))

            income_bars = ax.bar(
                x - bar_width/2, incomes, bar_width,
                label='Receitas', color='green', alpha=0.7
            )
            expense_bars = ax.bar(
                x + bar_width/2, expenses, bar_width,
                label='Despesas', color='red', alpha=0.7
            )
            ax.plot(
                x, balances, 'b-', marker='o', label='Saldo Acumulado'
            )
            ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)

            ax.set_xlabel('Mês')
            ax.set_ylabel('Valores (R$)')
            ax.set_title('Projeção de Fluxo de Caixa')
            ax.set_xticks(x)
            ax.set_xticklabels(months, rotation=45, ha='right')

            for bar in income_bars:
                height = bar.get_height()
                ax.annotate(
                    f'R${height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=8
                )

            for bar in expense_bars:
                height = bar.get_height()
                ax.annotate(
                    f'R${height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=8
                )

            ax.legend()
            self.figure.tight_layout()
            self.canvas.draw()

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível gerar a projeção: {str(e)}"
            )


class TrendsDialog(QDialog):
    """Diálogo para visualizar tendências de gastos"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tendências de Gastos")
        self.resize(900, 600)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.period_label = QLabel("Período de Análise:")
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            "Últimos 6 meses", "Último ano",
            "Últimos 2 anos", "Todo o histórico"
        ])

        self.trend_type_label = QLabel("Tipo de Análise:")
        self.trend_type_combo = QComboBox()
        self.trend_type_combo.addItems([
            "Gastos por Mês",
            "Gastos por Categoria",
            "Evolução do Saldo",
            "Top Categorias por Mês"
        ])

        self.generate_button = QPushButton("Gerar Análise")
        self.generate_button.clicked.connect(self.generate_trends)

        self.figure = plt.figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)

        self.analysis_label = QLabel("Análise de Tendências:")
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)

        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        layout = QVBoxLayout()

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.period_label)
        controls_layout.addWidget(self.period_combo)
        controls_layout.addWidget(self.trend_type_label)
        controls_layout.addWidget(self.trend_type_combo)
        controls_layout.addWidget(self.generate_button)
        layout.addLayout(controls_layout)

        split_layout = QVBoxLayout()
        split_layout.addWidget(self.canvas, 7)

        analysis_layout = QVBoxLayout()
        analysis_layout.addWidget(self.analysis_label)
        analysis_layout.addWidget(self.analysis_text)
        split_layout.addLayout(analysis_layout, 3)

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)
        self.generate_trends()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QTextEdit, QComboBox {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            self.close_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
            self.generate_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            plt.style.use('dark_background')
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QTextEdit, QComboBox {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
            """)
            self.close_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )
            self.generate_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            plt.style.use('default')

    def get_period_date(self):
        """Retorna a data de início do período"""
        today = datetime.now()
        period_index = self.period_combo.currentIndex()

        if period_index == 0:
            return (today - timedelta(days=180)).strftime('%Y-%m-%d')
        elif period_index == 1:
            return (today - timedelta(days=365)).strftime('%Y-%m-%d')
        elif period_index == 2:
            return (today - timedelta(days=730)).strftime('%Y-%m-%d')
        return None

    def generate_trends(self):
        """Gera a análise de tendências"""
        try:
            start_date = self.get_period_date()
            trend_type = self.trend_type_combo.currentIndex()

            if trend_type == 0:
                self.analyze_monthly_expenses(start_date)
            elif trend_type == 1:
                self.analyze_category_expenses(start_date)
            elif trend_type == 2:
                self.analyze_balance_evolution(start_date)
            elif trend_type == 3:
                self.analyze_top_categories_by_month(start_date)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível gerar a análise: {str(e)}"
            )

    def analyze_monthly_expenses(self, start_date):
        """Analisa gastos mensais ao longo do tempo"""
        query = '''SELECT
                       strftime('%Y-%m', date) as month,
                       SUM(CASE WHEN transaction_type='entrada'
                           THEN amount ELSE 0 END) as income,
                       SUM(CASE WHEN transaction_type='saida'
                           THEN amount ELSE 0 END) as expense
                   FROM transactions WHERE user_id = ?'''
        params = [self.parent().user_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        query += " GROUP BY month ORDER BY month"
        monthly_data = self.parent().db_connection.execute(
            query, params
        ).fetchall()

        if not monthly_data:
            self.analysis_text.setHtml(
                "<i>Não há dados suficientes para esta análise.</i>"
            )
            self.figure.clear()
            self.canvas.draw()
            return

        months = [
            datetime.strptime(m['month'], '%Y-%m').strftime('%b %Y')
            for m in monthly_data
        ]
        incomes = [m['income'] for m in monthly_data]
        expenses = [m['expense'] for m in monthly_data]
        balances = [inc - exp for inc, exp in zip(incomes, expenses)]

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        bar_width = 0.35
        x = np.arange(len(months))

        ax.bar(
            x - bar_width/2, incomes, bar_width,
            label='Receitas', color='green', alpha=0.7
        )
        ax.bar(
            x + bar_width/2, expenses, bar_width,
            label='Despesas', color='red', alpha=0.7
        )
        ax.plot(x, balances, 'b-', marker='o', label='Saldo Mensal')
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)

        ax.set_xlabel('Mês')
        ax.set_ylabel('Valores (R$)')
        ax.set_title('Evolução de Receitas e Despesas')
        ax.set_xticks(x)
        ax.set_xticklabels(months, rotation=45, ha='right')
        ax.legend()
        self.figure.tight_layout()
        self.canvas.draw()

        avg_income = sum(incomes) / len(incomes)
        avg_expense = sum(expenses) / len(expenses)
        avg_balance = sum(balances) / len(balances)

        income_trend = self.calculate_trend(incomes) if len(incomes) >= 3 else 0
        expense_trend = (
            self.calculate_trend(expenses) if len(expenses) >= 3 else 0
        )
        balance_trend = (
            self.calculate_trend(balances) if len(balances) >= 3 else 0
        )

        analysis_html = "<h3>Análise de Receitas e Despesas Mensais</h3>"
        analysis_html += (
            f"<p><b>Valores médios:</b><br>"
            f"Receita média: <span style='color:green;'>R$ {avg_income:.2f}</span><br>"
            f"Despesa média: <span style='color:red;'>R$ {avg_expense:.2f}</span><br>"
        )

        if avg_balance >= 0:
            analysis_html += (
                f"Saldo médio: "
                f"<span style='color:green;'>R$ {avg_balance:.2f}</span></p>"
            )
        else:
            analysis_html += (
                f"Saldo médio: "
                f"<span style='color:red;'>R$ {avg_balance:.2f}</span></p>"
            )

        def trend_text(trend, positive_good=True):
            if trend > 0:
                color = "green" if positive_good else "red"
                word = "aumentando"
            elif trend < 0:
                color = "red" if positive_good else "green"
                word = "diminuindo"
            else:
                color = "blue"
                word = "estável"
            return f"<span style='color:{color};'>{word}</span>"

        analysis_html += (
            f"<p><b>Tendências:</b><br>"
            f"Receitas: {trend_text(income_trend, True)}<br>"
            f"Despesas: {trend_text(expense_trend, False)}<br>"
            f"Saldo: {trend_text(balance_trend, True)}</p>"
        )

        self.analysis_text.setHtml(analysis_html)

    def analyze_category_expenses(self, start_date):
        """Analisa gastos por categoria"""
        expense_query = '''SELECT
                               strftime('%Y-%m', date) as month,
                               category_id,
                               SUM(amount) as total
                           FROM transactions
                           WHERE user_id = ? AND transaction_type = 'saida' '''
        params = [self.parent().user_id]

        if start_date:
            expense_query += " AND date >= ?"
            params.append(start_date)

        expense_query += " GROUP BY month, category_id ORDER BY month"

        expenses_data = self.parent().db_connection.execute(
            expense_query, params
        ).fetchall()

        categories = self.parent().db_connection.execute(
            'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
            (self.parent().user_id,)
        ).fetchall()

        if not expenses_data or not categories:
            self.analysis_text.setHtml(
                "<i>Não há dados suficientes para esta análise.</i>"
            )
            self.figure.clear()
            self.canvas.draw()
            return

        months = sorted(set(e['month'] for e in expenses_data))
        formatted_months = [
            datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months
        ]

        category_expenses = {
            cat['id']: [0] * len(months) for cat in categories
        }
        category_names = {cat['id']: cat['name'] for cat in categories}

        for expense in expenses_data:
            if expense['category_id'] in category_expenses:
                month_index = months.index(expense['month'])
                category_expenses[expense['category_id']][month_index] = (
                    expense['total']
                )

        category_totals = {
            cat_id: sum(exps)
            for cat_id, exps in category_expenses.items()
        }
        top_categories = sorted(
            category_totals.items(), key=lambda x: x[1], reverse=True
        )[:5]

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c',
            '#d62728', '#9467bd', '#8c564b'
        ]

        for i, (cat_id, _) in enumerate(top_categories):
            ax.plot(
                range(len(months)),
                category_expenses[cat_id],
                marker='o', linewidth=2,
                label=category_names[cat_id],
                color=colors[i % len(colors)]
            )

        ax.set_xlabel('Mês')
        ax.set_ylabel('Despesas (R$)')
        ax.set_title('Evolução de Despesas por Categoria')
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(formatted_months, rotation=45, ha='right')
        ax.legend()
        self.figure.tight_layout()
        self.canvas.draw()

        analysis_html = "<h3>Análise de Despesas por Categoria</h3>"
        analysis_html += "<p><b>Top 5 categorias com maior despesa:</b></p><ol>"

        for cat_id, total in top_categories:
            cat_name = category_names[cat_id]
            cat_data = category_expenses[cat_id]
            cat_avg = sum(cat_data) / len(cat_data) if cat_data else 0
            cat_trend = (
                self.calculate_trend(cat_data)
                if len(cat_data) >= 3 else 0
            )

            if cat_trend > 0:
                trend = "<span style='color:red;'>aumentando</span>"
            elif cat_trend < 0:
                trend = "<span style='color:green;'>diminuindo</span>"
            else:
                trend = "<span style='color:blue;'>estável</span>"

            analysis_html += (
                f"<li><b>{cat_name}</b>: Total R$ {total:.2f}, "
                f"média R$ {cat_avg:.2f} | Tendência: {trend}</li>"
            )

        analysis_html += "</ol>"
        self.analysis_text.setHtml(analysis_html)

    def analyze_balance_evolution(self, start_date):
        """Analisa a evolução do saldo ao longo do tempo"""
        query = '''SELECT date, transaction_type, amount
                   FROM transactions WHERE user_id = ?'''
        params = [self.parent().user_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        query += " ORDER BY date"
        transactions = self.parent().db_connection.execute(
            query, params
        ).fetchall()

        if not transactions:
            self.analysis_text.setHtml(
                "<i>Não há dados suficientes para esta análise.</i>"
            )
            self.figure.clear()
            self.canvas.draw()
            return

        dates = []
        balances = []
        cumulative_balance = 0

        for t in transactions:
            date = datetime.strptime(t['date'], '%Y-%m-%d')
            amount = t['amount']
            if t['transaction_type'] == 'saida':
                amount = -amount
            cumulative_balance += amount
            dates.append(date)
            balances.append(cumulative_balance)

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        ax.plot(dates, balances, 'b-', linewidth=2)
        ax.fill_between(
            dates, balances, 0,
            where=[b >= 0 for b in balances],
            color='green', alpha=0.3
        )
        ax.fill_between(
            dates, balances, 0,
            where=[b < 0 for b in balances],
            color='red', alpha=0.3
        )
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
        ax.set_xlabel('Data')
        ax.set_ylabel('Saldo (R$)')
        ax.set_title('Evolução do Saldo ao Longo do Tempo')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.xticks(rotation=45, ha='right')
        ax.grid(True, linestyle='--', alpha=0.7)
        self.figure.tight_layout()
        self.canvas.draw()

        initial_balance = balances[0]
        final_balance = balances[-1]
        total_variation = final_balance - initial_balance
        percentage = (
            (total_variation / abs(initial_balance) * 100)
            if initial_balance != 0 else 0
        )

        recent_trend = (
            self.calculate_trend(balances[-10:])
            if len(balances) >= 10
            else self.calculate_trend(balances)
        )

        analysis_html = (
            f"<h3>Análise da Evolução do Saldo</h3>"
            f"<p><b>Período:</b> "
            f"{dates[0].strftime('%d/%m/%Y')} a "
            f"{dates[-1].strftime('%d/%m/%Y')}</p>"
        )

        if final_balance >= 0:
            analysis_html += (
                f"<p>Saldo atual: "
                f"<span style='color:green;'>R$ {final_balance:.2f}</span></p>"
            )
        else:
            analysis_html += (
                f"<p>Saldo atual: "
                f"<span style='color:red;'>R$ {final_balance:.2f}</span></p>"
            )

        if total_variation >= 0:
            analysis_html += (
                f"<p>Variação: "
                f"<span style='color:green;'>+R$ {total_variation:.2f} "
                f"(+{percentage:.1f}%)</span></p>"
            )
        else:
            analysis_html += (
                f"<p>Variação: "
                f"<span style='color:red;'>-R$ {abs(total_variation):.2f} "
                f"({percentage:.1f}%)</span></p>"
            )

        if recent_trend > 0:
            analysis_html += (
                "<p>Tendência: "
                "<span style='color:green;'>crescimento</span> 📈</p>"
            )
        elif recent_trend < 0:
            analysis_html += (
                "<p>Tendência: "
                "<span style='color:red;'>queda</span> 📉</p>"
            )
        else:
            analysis_html += (
                "<p>Tendência: "
                "<span style='color:blue;'>estável</span></p>"
            )

        self.analysis_text.setHtml(analysis_html)

    def analyze_top_categories_by_month(self, start_date):
        """Analisa as principais categorias por mês"""
        query = '''SELECT
                       strftime('%Y-%m', t.date) as month,
                       c.name as category_name,
                       SUM(t.amount) as total
                   FROM transactions t
                   JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ? AND t.transaction_type = 'saida' '''
        params = [self.parent().user_id]

        if start_date:
            query += " AND t.date >= ?"
            params.append(start_date)

        query += " GROUP BY month, category_name ORDER BY month, total DESC"
        expenses_data = self.parent().db_connection.execute(
            query, params
        ).fetchall()

        if not expenses_data:
            self.analysis_text.setHtml(
                "<i>Não há dados suficientes para esta análise.</i>"
            )
            self.figure.clear()
            self.canvas.draw()
            return

        months = sorted(set(e['month'] for e in expenses_data))
        formatted_months = [
            datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months
        ]

        month_categories = {}
        for month in months:
            month_data = [e for e in expenses_data if e['month'] == month]
            month_categories[month] = sorted(
                month_data, key=lambda x: x['total'], reverse=True
            )[:5]

        self.figure.clear()
        n_months = len(months)
        if n_months <= 3:
            rows, cols = 1, n_months
        elif n_months <= 6:
            rows, cols = 2, 3
        else:
            rows, cols = (n_months + 3) // 4, 4

        colors = plt.cm.tab10.colors

        for i, month in enumerate(months):
            ax = self.figure.add_subplot(rows, cols, i + 1)
            cats = [c['category_name'] for c in month_categories[month]]
            vals = [c['total'] for c in month_categories[month]]

            wedges, texts, autotexts = ax.pie(
                vals, autopct='%1.1f%%',
                textprops={'fontsize': 8},
                colors=colors[:len(cats)]
            )
            for autotext in autotexts:
                autotext.set_fontsize(6)

            ax.set_title(formatted_months[i], fontsize=10)
            if cats:
                ax.legend(
                    wedges, cats, loc="center left",
                    bbox_to_anchor=(1, 0, 0.5, 1), fontsize=6
                )

        self.figure.tight_layout()
        self.canvas.draw()

        analysis_html = (
            "<h3>Análise das Principais Categorias por Mês</h3>"
        )
        for i, month in enumerate(months):
            month_total = sum(
                c['total'] for c in month_categories[month]
            )
            analysis_html += (
                f"<p><b>{formatted_months[i]}</b>: "
                f"Total R$ {month_total:.2f}<br>"
            )
            for j, cat in enumerate(month_categories[month]):
                pct = (cat['total'] / month_total * 100)
                analysis_html += (
                    f"{j+1}. {cat['category_name']}: "
                    f"R$ {cat['total']:.2f} ({pct:.1f}%)<br>"
                )
            analysis_html += "</p>"

        self.analysis_text.setHtml(analysis_html)

    def calculate_trend(self, values):
        """Calcula tendência de uma série de valores"""
        if len(values) < 2:
            return 0

        x = np.arange(len(values))
        y = np.array(values)
        valid = ~np.isnan(y)

        if not np.any(valid) or np.sum(valid) < 2:
            return 0

        try:
            slope, _ = np.polyfit(x[valid], y[valid], 1)
            avg = np.mean(y[valid])
            if avg != 0:
                normalized = slope / abs(avg)
            else:
                normalized = slope

            return 0 if abs(normalized) < 0.05 else normalized
        except Exception:
            return 0

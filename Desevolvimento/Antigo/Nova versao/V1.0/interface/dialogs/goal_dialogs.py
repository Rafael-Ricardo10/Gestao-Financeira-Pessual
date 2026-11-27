"""
Diálogos para gerenciamento de metas financeiras
"""
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QDateEdit, QTextEdit, QCheckBox, QProgressBar,
    QMessageBox, QInputDialog, QTableWidget,
    QTableWidgetItem, QWidget, QGroupBox
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor


class BudgetDialog(QDialog):
    """Diálogo para definir orçamentos mensais por categoria"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Definir Orçamento Mensal")
        self.setMinimumWidth(500)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.month_label = QLabel("Mês:")
        self.month_combo = QComboBox()
        self.month_combo.addItems([
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio",
            "Junho", "Julho", "Agosto", "Setembro", "Outubro",
            "Novembro", "Dezembro"
        ])
        self.month_combo.setCurrentIndex(datetime.now().month - 1)

        self.year_label = QLabel("Ano:")
        self.year_combo = QComboBox()
        current_year = datetime.now().year
        for year in range(current_year - 2, current_year + 3):
            self.year_combo.addItem(str(year))
        self.year_combo.setCurrentText(str(current_year))

        self.load_button = QPushButton("Carregar Orçamentos Existentes")
        self.load_button.clicked.connect(self.load_existing_budgets)

        self.budget_table = QTableWidget()
        self.budget_table.setColumnCount(3)
        self.budget_table.setHorizontalHeaderLabels([
            "Categoria", "Orçamento (R$)", "Gastos Médios (R$)"
        ])
        self.budget_table.horizontalHeader().setStretchLastSection(True)

        self.save_button = QPushButton("Salvar Orçamentos")
        self.save_button.clicked.connect(self.save_budgets)

        self.suggest_button = QPushButton("Sugerir com Base nos Gastos")
        self.suggest_button.clicked.connect(self.suggest_budgets)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()

        date_layout = QHBoxLayout()
        date_layout.addWidget(self.month_label)
        date_layout.addWidget(self.month_combo)
        date_layout.addWidget(self.year_label)
        date_layout.addWidget(self.year_combo)
        date_layout.addWidget(self.load_button)
        layout.addLayout(date_layout)

        layout.addWidget(self.budget_table)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.suggest_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.load_categories()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                    selection-background-color: #3498db;
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                    padding: 5px; border: 1px solid #4b6584;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
                QTableWidget {
                    background-color: white;
                    alternate-background-color: #f9f9f9;
                    selection-background-color: #e3f2fd;
                }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )
            self.suggest_button.setStyleSheet(
                "background-color: #2196F3; color: white;"
            )

    def load_categories(self):
        """Carrega as categorias para a tabela"""
        try:
            categories = self.parent().db_connection.execute(
                'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
                (self.parent().user_id,)
            ).fetchall()

            self.budget_table.setRowCount(len(categories))

            for i, category in enumerate(categories):
                category_item = QTableWidgetItem(category['name'])
                category_item.setData(Qt.UserRole, category['id'])

                budget_input = QLineEdit()
                budget_input.setPlaceholderText("0.00")

                avg_expense = self.calculate_average_expense(category['id'])
                avg_item = QTableWidgetItem(f"{avg_expense:.2f}")

                self.budget_table.setItem(i, 0, category_item)
                self.budget_table.setCellWidget(i, 1, budget_input)
                self.budget_table.setItem(i, 2, avg_item)

            self.budget_table.resizeColumnsToContents()

        except Exception as e:
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível carregar as categorias: {str(e)}"
            )

    def calculate_average_expense(self, category_id):
        """Calcula a média de gastos dos últimos 3 meses"""
        try:
            today = datetime.now()
            three_months_ago = today.replace(day=1)
            for _ in range(3):
                three_months_ago = (
                    three_months_ago - timedelta(days=1)
                ).replace(day=1)

            result = self.parent().db_connection.execute(
                '''SELECT SUM(amount) as total,
                          COUNT(DISTINCT strftime('%Y-%m', date)) as months
                   FROM transactions
                   WHERE user_id = ? AND category_id = ?
                   AND transaction_type = 'saida' AND date >= ?''',
                (self.parent().user_id, category_id,
                 three_months_ago.strftime('%Y-%m-%d'))
            ).fetchone()

            total = result['total'] or 0
            months = result['months'] or 1
            return total / months

        except Exception:
            return 0.0

    def load_existing_budgets(self):
        """Carrega orçamentos existentes para o mês/ano selecionado"""
        try:
            selected_month = self.month_combo.currentIndex() + 1
            selected_year = self.year_combo.currentText()

            budgets = self.parent().db_connection.execute(
                '''SELECT cb.category_id, cb.amount
                   FROM category_budgets cb
                   WHERE cb.user_id = ? AND cb.month = ? AND cb.year = ?''',
                (self.parent().user_id, selected_month, selected_year)
            ).fetchall()

            budget_map = {b['category_id']: b['amount'] for b in budgets}

            for i in range(self.budget_table.rowCount()):
                category_id = self.budget_table.item(i, 0).data(Qt.UserRole)
                if category_id in budget_map:
                    budget_input = self.budget_table.cellWidget(i, 1)
                    budget_input.setText(str(budget_map[category_id]))

            QMessageBox.information(
                self, "Sucesso",
                f"Orçamentos carregados para "
                f"{self.month_combo.currentText()} de {selected_year}."
            )

        except Exception as e:
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível carregar os orçamentos: {str(e)}"
            )

    def suggest_budgets(self):
        """Sugere orçamentos com base nos gastos médios"""
        try:
            for i in range(self.budget_table.rowCount()):
                avg_text = self.budget_table.item(i, 2).text()
                try:
                    avg = float(avg_text.replace(',', '.'))
                    suggested = avg * 1.1
                    budget_input = self.budget_table.cellWidget(i, 1)
                    budget_input.setText(f"{suggested:.2f}")
                except Exception:
                    continue
        except Exception as e:
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível sugerir orçamentos: {str(e)}"
            )

    def save_budgets(self):
        """Salva os orçamentos no banco de dados"""
        try:
            selected_month = self.month_combo.currentIndex() + 1
            selected_year = self.year_combo.currentText()

            self.parent().db_connection.execute("BEGIN TRANSACTION")
            self.parent().db_connection.execute(
                "DELETE FROM category_budgets "
                "WHERE user_id = ? AND month = ? AND year = ?",
                (self.parent().user_id, selected_month, selected_year)
            )

            count = 0
            for i in range(self.budget_table.rowCount()):
                category_id = self.budget_table.item(i, 0).data(Qt.UserRole)
                budget_input = self.budget_table.cellWidget(i, 1)
                budget_text = budget_input.text().strip()

                if budget_text:
                    try:
                        budget_amount = float(budget_text.replace(',', '.'))
                        if budget_amount > 0:
                            self.parent().db_connection.execute(
                                '''INSERT INTO category_budgets
                                   (user_id, category_id, month, year, amount)
                                   VALUES (?, ?, ?, ?, ?)''',
                                (self.parent().user_id, category_id,
                                 selected_month, selected_year, budget_amount)
                            )
                            count += 1
                    except ValueError:
                        continue

            self.parent().db_connection.commit()
            QMessageBox.information(
                self, "Sucesso",
                f"Foram salvos {count} orçamentos para "
                f"{self.month_combo.currentText()} de {selected_year}."
            )
            self.accept()

        except Exception as e:
            self.parent().db_connection.rollback()
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível salvar os orçamentos: {str(e)}"
            )


class SavingsGoalDialog(QDialog):
    """Diálogo para gerenciar metas de economia"""

    def __init__(self, parent=None, goal_id=None):
        super().__init__(parent)
        self.goal_id = goal_id
        self.is_edit_mode = goal_id is not None
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.setWindowTitle(
            "Meta de Economia" if self.is_edit_mode else "Nova Meta de Economia"
        )
        self.setMinimumWidth(450)

        # Widgets
        self.name_label = QLabel("Nome da Meta:")
        self.name_input = QLineEdit()

        self.target_label = QLabel("Valor Alvo (R$):")
        self.target_input = QLineEdit()

        self.current_label = QLabel("Valor Atual (R$):")
        self.current_input = QLineEdit()
        self.current_input.setPlaceholderText("0.00")

        self.has_deadline_check = QCheckBox("Definir prazo")
        self.has_deadline_check.toggled.connect(self.toggle_deadline)
        self.has_deadline_check.setChecked(False)

        self.deadline_label = QLabel("Prazo (opcional):")
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setDisplayFormat("yyyy-MM-dd")
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setDate(QDate.currentDate().addMonths(6))
        self.deadline_edit.setEnabled(False)

        self.category_label = QLabel("Categoria relacionada (opcional):")
        self.category_combo = QComboBox()
        self.category_combo.addItem("Nenhuma", None)

        if parent and hasattr(parent, 'db_connection'):
            categories = parent.db_connection.execute(
                'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
                (parent.user_id,)
            ).fetchall()
            for cat in categories:
                self.category_combo.addItem(cat['name'], cat['id'])

        self.notes_label = QLabel("Notas:")
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText(
            "Observações ou motivação para esta meta..."
        )
        self.notes_input.setMaximumHeight(100)

        # Progresso (modo edição)
        self.progress_label = QLabel("Progresso:")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)

        self.time_progress_label = QLabel("Progresso de tempo:")
        self.time_progress_bar = QProgressBar()
        self.time_progress_bar.setMaximum(100)
        self.time_progress_bar.setTextVisible(True)

        self.summary_label = QLabel()

        # Botões
        self.save_button = QPushButton(
            "Atualizar Meta" if self.is_edit_mode else "Criar Meta"
        )
        self.save_button.clicked.connect(self.save_goal)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        button_layout = QHBoxLayout()

        if self.is_edit_mode:
            self.deposit_button = QPushButton("Adicionar Depósito")
            self.deposit_button.clicked.connect(self.add_deposit)
            button_layout.addWidget(self.deposit_button)

        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        # Layout
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.addRow(self.name_label, self.name_input)
        form_layout.addRow(self.target_label, self.target_input)
        form_layout.addRow(self.current_label, self.current_input)
        form_layout.addRow(self.has_deadline_check)
        form_layout.addRow(self.deadline_label, self.deadline_edit)
        form_layout.addRow(self.category_label, self.category_combo)
        form_layout.addRow(self.notes_label, self.notes_input)
        layout.addLayout(form_layout)

        if self.is_edit_mode:
            layout.addWidget(self.progress_label)
            layout.addWidget(self.progress_bar)
            layout.addWidget(self.time_progress_label)
            layout.addWidget(self.time_progress_bar)
            layout.addWidget(self.summary_label)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        if self.is_edit_mode:
            self.load_goal_data()

        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QCheckBox { color: #ecf0f1; }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 5px;
                    text-align: center; background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71; width: 10px; margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            if hasattr(self, 'deposit_button'):
                self.deposit_button.setStyleSheet(
                    "background-color: #f39c12; color: #ecf0f1;"
                )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50; width: 10px; margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            if hasattr(self, 'deposit_button'):
                self.deposit_button.setStyleSheet(
                    "background-color: #FF9800; color: white;"
                )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def toggle_deadline(self, checked):
        """Ativa/desativa o campo de prazo"""
        self.deadline_edit.setEnabled(checked)
        if hasattr(self, 'time_progress_label'):
            self.time_progress_label.setVisible(checked)
            self.time_progress_bar.setVisible(checked)

    def load_goal_data(self):
        """Carrega os dados da meta existente"""
        try:
            goal = self.parent().db_connection.execute(
                'SELECT * FROM savings_goals WHERE id = ? AND user_id = ?',
                (self.goal_id, self.parent().user_id)
            ).fetchone()

            if not goal:
                QMessageBox.warning(self, "Erro", "Meta não encontrada.")
                self.reject()
                return

            self.name_input.setText(goal['name'])
            self.target_input.setText(str(goal['target_amount']))
            self.current_input.setText(str(goal['current_amount']))

            if goal['deadline']:
                self.has_deadline_check.setChecked(True)
                deadline_date = QDate.fromString(goal['deadline'], "yyyy-MM-dd")
                self.deadline_edit.setDate(deadline_date)

                start_date = datetime.strptime(
                    goal['start_date'], '%Y-%m-%d'
                ).date()
                deadline_dt = datetime.strptime(
                    goal['deadline'], '%Y-%m-%d'
                ).date()
                today = datetime.now().date()

                total_days = (deadline_dt - start_date).days
                days_passed = (today - start_date).days

                if total_days > 0:
                    time_progress = min(
                        100, int((days_passed / total_days) * 100)
                    )
                    self.time_progress_bar.setValue(time_progress)
                    days_left = (deadline_dt - today).days

                    if days_left > 0:
                        self.time_progress_bar.setFormat(
                            f"{time_progress}% ({days_left} dias restantes)"
                        )
                    else:
                        self.time_progress_bar.setFormat("Prazo expirado!")
                        self.time_progress_bar.setStyleSheet(
                            "QProgressBar::chunk { background-color: #e74c3c; }"
                        )
            else:
                self.time_progress_label.setVisible(False)
                self.time_progress_bar.setVisible(False)

            if goal['category_id']:
                index = self.category_combo.findData(goal['category_id'])
                if index >= 0:
                    self.category_combo.setCurrentIndex(index)

            if goal['notes']:
                self.notes_input.setText(goal['notes'])

            target = goal['target_amount']
            current = goal['current_amount']

            if target > 0:
                progress = min(100, int((current / target) * 100))
                self.progress_bar.setValue(progress)
                self.progress_bar.setFormat(
                    f"{progress}% (R$ {current:.2f} de R$ {target:.2f})"
                )
                remaining = target - current
                self.summary_label.setText(
                    f"Faltam R$ {remaining:.2f} para atingir a meta."
                )

        except Exception as e:
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível carregar os dados da meta: {str(e)}"
            )
            self.reject()

    def save_goal(self):
        """Salva ou atualiza a meta de economia"""
        try:
            name = self.name_input.text().strip()
            if not name:
                QMessageBox.warning(
                    self, "Erro", "O nome da meta não pode estar vazio."
                )
                return

            try:
                target_amount = float(
                    self.target_input.text().replace(',', '.')
                )
                if target_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro", "O valor alvo deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro", "O valor alvo deve ser um número válido."
                )
                return

            try:
                current_text = self.current_input.text().strip()
                current_amount = (
                    float(current_text.replace(',', '.'))
                    if current_text else 0
                )
                if current_amount < 0:
                    QMessageBox.warning(
                        self, "Erro", "O valor atual não pode ser negativo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro", "O valor atual deve ser um número válido."
                )
                return

            deadline = None
            if self.has_deadline_check.isChecked():
                deadline = self.deadline_edit.date().toString("yyyy-MM-dd")

            category_id = self.category_combo.currentData()
            notes = self.notes_input.toPlainText().strip()

            if self.is_edit_mode:
                self.parent().db_connection.execute(
                    '''UPDATE savings_goals
                       SET name=?, target_amount=?, current_amount=?,
                           deadline=?, category_id=?, notes=?
                       WHERE id=? AND user_id=?''',
                    (name, target_amount, current_amount, deadline,
                     category_id, notes, self.goal_id, self.parent().user_id)
                )
                message = "Meta de economia atualizada com sucesso!"
            else:
                start_date = datetime.now().strftime("%Y-%m-%d")
                self.parent().db_connection.execute(
                    '''INSERT INTO savings_goals
                       (user_id, name, target_amount, current_amount,
                        start_date, deadline, category_id, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (self.parent().user_id, name, target_amount,
                     current_amount, start_date, deadline, category_id, notes)
                )
                message = "Nova meta de economia criada com sucesso!"

            self.parent().db_connection.commit()
            QMessageBox.information(self, "Sucesso", message)
            self.accept()

        except Exception as e:
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível salvar a meta: {str(e)}"
            )

    def add_deposit(self):
        """Adiciona um depósito à meta de economia"""
        amount, ok = QInputDialog.getDouble(
            self, "Adicionar Depósito",
            "Informe o valor do depósito (R$):",
            0, 0, 1000000, 2
        )

        if ok and amount > 0:
            try:
                goal = self.parent().db_connection.execute(
                    'SELECT current_amount, target_amount FROM savings_goals WHERE id = ?',
                    (self.goal_id,)
                ).fetchone()

                new_amount = goal['current_amount'] + amount

                if new_amount > goal['target_amount']:
                    excess = new_amount - goal['target_amount']
                    new_amount = goal['target_amount']
                    QMessageBox.information(
                        self, "Aviso",
                        f"O depósito excede o valor alvo em R$ {excess:.2f}.\n"
                        f"O valor foi ajustado para o valor alvo."
                    )

                self.parent().db_connection.execute(
                    'UPDATE savings_goals SET current_amount = ? WHERE id = ?',
                    (new_amount, self.goal_id)
                )
                self.parent().db_connection.commit()

                self.current_input.setText(str(new_amount))

                progress = min(
                    100,
                    int((new_amount / goal['target_amount']) * 100)
                )
                self.progress_bar.setValue(progress)
                self.progress_bar.setFormat(
                    f"{progress}% "
                    f"(R$ {new_amount:.2f} de R$ {goal['target_amount']:.2f})"
                )

                remaining = goal['target_amount'] - new_amount
                self.summary_label.setText(
                    f"Faltam R$ {remaining:.2f} para atingir a meta."
                )

                QMessageBox.information(
                    self, "Sucesso",
                    f"Depósito de R$ {amount:.2f} adicionado com sucesso!"
                )

                if new_amount >= goal['target_amount']:
                    QMessageBox.information(
                        self, "Parabéns!",
                        "Você atingiu sua meta de economia! 🎉"
                    )

            except Exception as e:
                QMessageBox.warning(
                    self, "Erro",
                    f"Não foi possível adicionar o depósito: {str(e)}"
                )

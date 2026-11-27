"""
Diálogos para gerenciamento de categorias
"""
import sqlite3

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QRadioButton, QProgressBar, QMessageBox
)
from PyQt5.QtGui import QColor


class AddCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Categoria")
        self.setMinimumWidth(400)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()
        self.category_name_input.setPlaceholderText(
            "Digite o nome da categoria"
        )

        # Grupo de tipo de meta
        self.goal_group = QGroupBox("Tipo de Meta:")
        self.goal_layout = QVBoxLayout()

        self.no_goal_radio = QRadioButton("Sem Meta")
        self.payment_goal_radio = QRadioButton("Meta de Quitação")
        self.savings_goal_radio = QRadioButton("Meta de Guardar Dinheiro")

        self.no_goal_radio.setChecked(True)
        self.no_goal_radio.toggled.connect(self.toggle_goal_options)
        self.payment_goal_radio.toggled.connect(self.toggle_goal_options)
        self.savings_goal_radio.toggled.connect(self.toggle_goal_options)

        self.goal_layout.addWidget(self.no_goal_radio)
        self.goal_layout.addWidget(self.payment_goal_radio)
        self.goal_layout.addWidget(self.savings_goal_radio)
        self.goal_group.setLayout(self.goal_layout)

        self.total_amount_label = QLabel("Valor Total da Meta:")
        self.total_amount_input = QLineEdit()
        self.total_amount_input.setPlaceholderText(
            "Valor total da meta (ex: 20000.00)"
        )
        self.total_amount_input.setEnabled(False)

        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)
        layout.addWidget(self.goal_group)
        layout.addWidget(self.total_amount_label)
        layout.addWidget(self.total_amount_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QLineEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QRadioButton { color: #ecf0f1; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            self.add_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QLineEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def toggle_goal_options(self, checked):
        """Ativa/desativa campo de valor total"""
        self.total_amount_input.setEnabled(
            self.payment_goal_radio.isChecked() or
            self.savings_goal_radio.isChecked()
        )

    def add_category(self):
        """Adiciona uma nova categoria ao banco de dados"""
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(
                self, "Erro", "O nome da categoria não pode estar vazio."
            )
            return

        total_amount = 0
        is_payment_goal = 0
        is_savings_goal = 0

        if self.payment_goal_radio.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro", "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro", "O valor total deve ser um número válido."
                )
                return

        elif self.savings_goal_radio.isChecked():
            is_savings_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro", "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro", "O valor total deve ser um número válido."
                )
                return

        try:
            column_exists = self.parent().db_connection.execute(
                "SELECT COUNT(*) FROM pragma_table_info('categories') "
                "WHERE name='is_savings_goal'"
            ).fetchone()[0] > 0

            if column_exists:
                self.parent().db_connection.execute(
                    '''INSERT INTO categories
                       (user_id, name, total_amount,
                        is_payment_goal, is_savings_goal)
                       VALUES (?, ?, ?, ?, ?)''',
                    (self.parent().user_id, category_name,
                     total_amount, is_payment_goal, is_savings_goal)
                )
            else:
                self.parent().db_connection.execute(
                    '''INSERT INTO categories
                       (user_id, name, total_amount, is_payment_goal)
                       VALUES (?, ?, ?, ?)''',
                    (self.parent().user_id, category_name,
                     total_amount, is_payment_goal)
                )

            self.parent().db_connection.commit()
            QMessageBox.information(
                self, "Sucesso", "Categoria adicionada com sucesso!"
            )
            self.accept()

        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Erro",
                f"A categoria '{category_name}' já existe."
            )


class EditCategoryDialog(QDialog):
    def __init__(self, parent=None, category_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Categoria")
        self.setMinimumWidth(400)
        self.category_id = category_id
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()

        # Grupo de tipo de meta
        self.goal_group = QGroupBox("Tipo de Meta:")
        self.goal_layout = QVBoxLayout()

        self.no_goal_radio = QRadioButton("Sem Meta")
        self.payment_goal_radio = QRadioButton("Meta de Quitação")
        self.savings_goal_radio = QRadioButton("Meta de Guardar Dinheiro")

        self.no_goal_radio.toggled.connect(self.toggle_goal_options)
        self.payment_goal_radio.toggled.connect(self.toggle_goal_options)
        self.savings_goal_radio.toggled.connect(self.toggle_goal_options)

        self.goal_layout.addWidget(self.no_goal_radio)
        self.goal_layout.addWidget(self.payment_goal_radio)
        self.goal_layout.addWidget(self.savings_goal_radio)
        self.goal_group.setLayout(self.goal_layout)

        self.total_amount_label = QLabel("Valor Total da Meta:")
        self.total_amount_input = QLineEdit()
        self.total_amount_input.setPlaceholderText(
            "Valor total da meta (ex: 20000.00)"
        )

        self.progress_label = QLabel("Progresso da Meta:")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_info = QLabel()

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)
        layout.addWidget(self.goal_group)
        layout.addWidget(self.total_amount_label)
        layout.addWidget(self.total_amount_input)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_info)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.load_category_data()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QLineEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QRadioButton { color: #ecf0f1; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
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
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QLineEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
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
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def toggle_goal_options(self, checked):
        """Ativa/desativa campos de meta"""
        has_goal = (
            self.payment_goal_radio.isChecked() or
            self.savings_goal_radio.isChecked()
        )
        self.total_amount_input.setEnabled(has_goal)
        self.progress_bar.setVisible(has_goal)
        self.progress_label.setVisible(has_goal)
        self.progress_info.setVisible(has_goal)

    def load_category_data(self):
        """Carrega dados da categoria"""
        category = self.parent().db_connection.execute(
            'SELECT * FROM categories WHERE id = ?',
            (self.category_id,)
        ).fetchone()

        self.category_name_input.setText(category['name'])

        column_exists = self.parent().db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('categories') "
            "WHERE name='is_savings_goal'"
        ).fetchone()[0] > 0

        is_payment_goal = category['is_payment_goal'] == 1
        is_savings_goal = (
            category['is_savings_goal'] == 1
            if column_exists else False
        )

        if is_payment_goal:
            self.payment_goal_radio.setChecked(True)
        elif is_savings_goal:
            self.savings_goal_radio.setChecked(True)
        else:
            self.no_goal_radio.setChecked(True)

        total_amount = category['total_amount'] or 0
        self.total_amount_input.setText(str(total_amount))
        self.total_amount_input.setEnabled(is_payment_goal or is_savings_goal)

        has_goal = is_payment_goal or is_savings_goal
        self.progress_bar.setVisible(has_goal)
        self.progress_label.setVisible(has_goal)
        self.progress_info.setVisible(has_goal)

        if has_goal and total_amount > 0:
            if is_payment_goal:
                total_accumulated = self.parent().db_connection.execute(
                    """SELECT SUM(amount) FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'saida'""",
                    (self.parent().user_id, self.category_id)
                ).fetchone()[0] or 0
            else:
                total_accumulated = self.parent().db_connection.execute(
                    """SELECT SUM(amount) FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'entrada'""",
                    (self.parent().user_id, self.category_id)
                ).fetchone()[0] or 0

            progress_percentage = min(
                100, int((total_accumulated / total_amount) * 100)
            ) if total_amount > 0 else 0

            self.progress_bar.setValue(progress_percentage)
            remaining = total_amount - total_accumulated

            if is_payment_goal:
                self.progress_info.setText(
                    f"Pago: R$ {total_accumulated:.2f} de "
                    f"R$ {total_amount:.2f} ({progress_percentage}%)\n"
                    f"Restante: R$ {remaining:.2f}"
                )
            else:
                self.progress_info.setText(
                    f"Guardado: R$ {total_accumulated:.2f} de "
                    f"R$ {total_amount:.2f} ({progress_percentage}%)\n"
                    f"Restante: R$ {remaining:.2f}"
                )

    def save_category(self):
        """Salva as alterações na categoria"""
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(
                self, "Erro", "O nome da categoria não pode estar vazio."
            )
            return

        total_amount = 0
        is_payment_goal = 0
        is_savings_goal = 0

        if self.payment_goal_radio.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro", "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro", "O valor total deve ser um número válido."
                )
                return

        elif self.savings_goal_radio.isChecked():
            is_savings_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro", "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro", "O valor total deve ser um número válido."
                )
                return

        try:
            column_exists = self.parent().db_connection.execute(
                "SELECT COUNT(*) FROM pragma_table_info('categories') "
                "WHERE name='is_savings_goal'"
            ).fetchone()[0] > 0

            if column_exists:
                self.parent().db_connection.execute(
                    '''UPDATE categories
                       SET name=?, total_amount=?,
                           is_payment_goal=?, is_savings_goal=?
                       WHERE id=?''',
                    (category_name, total_amount,
                     is_payment_goal, is_savings_goal, self.category_id)
                )
            else:
                self.parent().db_connection.execute(
                    '''UPDATE categories
                       SET name=?, total_amount=?, is_payment_goal=?
                       WHERE id=?''',
                    (category_name, total_amount,
                     is_payment_goal, self.category_id)
                )

            self.parent().db_connection.commit()
            QMessageBox.information(
                self, "Sucesso", "Categoria atualizada com sucesso!"
            )
            self.accept()

        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Erro",
                f"A categoria '{category_name}' já existe."
            )

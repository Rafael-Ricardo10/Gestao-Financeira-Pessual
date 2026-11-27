"""
Diálogos para gerenciamento de transações
"""
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QDateEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor


class AddTransactionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Transação")
        self.setMinimumWidth(400)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        # Widgets
        self.amount_label = QLabel("Valor:")
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("Digite o valor (ex: 150.00)")

        self.description_label = QLabel("Descrição:")
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Digite a descrição")

        self.type_label = QLabel("Tipo:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["entrada", "saida"])
        self.type_combobox.setCurrentIndex(1)
        self.type_combobox.currentIndexChanged.connect(
            self.toggle_savings_category
        )

        self.date_label = QLabel("Data:")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)

        self.category_label = QLabel("Categoria:")
        self.category_combobox = QComboBox()
        self.category_combobox.setEditable(True)
        self.category_combobox.currentTextChanged.connect(
            self.check_category_type
        )

        self.savings_category_label = QLabel("Usar dinheiro guardado de:")
        self.savings_category_combobox = QComboBox()
        self.savings_category_combobox.addItem("Nenhuma", None)

        self.savings_info_label = QLabel("")
        self.savings_info_label.setVisible(False)
        self.savings_info_label.setStyleSheet(
            "color: #3498db; font-style: italic;"
        )

        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_transaction)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.amount_label)
        layout.addWidget(self.amount_input)
        layout.addWidget(self.description_label)
        layout.addWidget(self.description_input)
        layout.addWidget(self.type_label)
        layout.addWidget(self.type_combobox)
        layout.addWidget(self.date_label)
        layout.addWidget(self.date_edit)
        layout.addWidget(self.category_label)
        layout.addWidget(self.category_combobox)
        layout.addWidget(self.savings_category_label)
        layout.addWidget(self.savings_category_combobox)
        layout.addWidget(self.savings_info_label)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Carregar categorias
        self.categories = parent.db_connection.execute(
            '''SELECT id, name, is_payment_goal, is_savings_goal, total_amount
               FROM categories
               WHERE user_id = ? AND (is_hidden = 0 OR is_hidden IS NULL)
               ORDER BY name''',
            (parent.user_id,)
        ).fetchall()

        self.category_map = {}
        for category in self.categories:
            category_name = category['name']
            self.category_combobox.addItem(category_name)

            has_savings_column = 'is_savings_goal' in category.keys()

            self.category_map[category_name] = {
                'id': category['id'],
                'is_payment_goal': category['is_payment_goal'] == 1,
                'is_savings_goal': (
                    category['is_savings_goal'] == 1
                    if has_savings_column else False
                ),
                'total_amount': category['total_amount'] or 0
            }

            if has_savings_column and category['is_savings_goal'] == 1:
                amount_saved = parent.db_connection.execute(
                    """SELECT SUM(amount) FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'entrada'""",
                    (parent.user_id, category['id'])
                ).fetchone()[0] or 0

                if amount_saved > 0:
                    self.savings_category_combobox.addItem(
                        f"{category_name} (R$ {amount_saved:.2f})",
                        category['id']
                    )

        self.apply_theme(self.is_dark_mode)
        self.toggle_savings_category(self.type_combobox.currentIndex())
        self.check_category_type(self.category_combobox.currentText())

    def toggle_savings_category(self, index):
        """Mostra/oculta o seletor de categoria de guardar dinheiro"""
        is_expense = (index == 1)
        self.savings_category_label.setVisible(is_expense)
        self.savings_category_combobox.setVisible(is_expense)

    def check_category_type(self, category_name):
        """Verifica se a categoria é uma meta de guardar dinheiro"""
        if category_name in self.category_map:
            category_info = self.category_map[category_name]

            if category_info['is_savings_goal']:
                if 'guardar' not in [
                    self.type_combobox.itemText(i)
                    for i in range(self.type_combobox.count())
                ]:
                    self.type_combobox.addItem("guardar")

                self.type_combobox.setCurrentText("guardar")
                self.type_combobox.setEnabled(False)
                self.savings_info_label.setText(
                    "Esta categoria é uma meta de guardar dinheiro.\n"
                    "O valor será adicionado ao seu total guardado."
                )
                self.savings_info_label.setVisible(True)
                self.savings_category_label.setVisible(False)
                self.savings_category_combobox.setVisible(False)
            else:
                guardar_index = self.type_combobox.findText("guardar")
                if guardar_index >= 0:
                    self.type_combobox.removeItem(guardar_index)

                self.type_combobox.setEnabled(True)
                self.savings_info_label.setVisible(False)

                is_expense = (self.type_combobox.currentIndex() == 1)
                self.savings_category_label.setVisible(is_expense)
                self.savings_category_combobox.setVisible(is_expense)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
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
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
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

    def add_transaction(self):
        """Adiciona uma nova transação ao banco de dados"""
        try:
            amount = float(
                self.amount_input.text().replace(',', '.')
            )
            if amount <= 0:
                QMessageBox.warning(
                    self, "Erro", "O valor deve ser positivo."
                )
                return
        except ValueError:
            QMessageBox.warning(
                self, "Erro", "O valor deve ser um número válido."
            )
            return

        description = self.description_input.text().strip()
        if not description:
            QMessageBox.warning(
                self, "Erro", "A descrição não pode estar vazia."
            )
            return

        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText().strip()

        if not category_name:
            QMessageBox.warning(
                self, "Erro", "A categoria não pode estar vazia."
            )
            return

        category_id = None
        is_savings_goal = False

        if category_name in self.category_map:
            category_id = self.category_map[category_name]['id']
            is_savings_goal = self.category_map[category_name]['is_savings_goal']
        else:
            current_year = datetime.now().year
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name, year) VALUES (?, ?, ?)',
                (self.parent().user_id, category_name, current_year)
            )
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.parent().user_id, category_name)
            ).fetchone()['id']

        savings_category_id = None
        if (transaction_type == 'saida' and
                self.savings_category_combobox.currentIndex() > 0):
            savings_category_id = self.savings_category_combobox.currentData()

        if transaction_type == 'guardar':
            transaction_type = 'entrada'
            self.parent().db_connection.execute(
                '''INSERT INTO transactions
                   (user_id, amount, description, transaction_type,
                    date, category_id, is_saving_transaction)
                   VALUES (?, ?, ?, ?, ?, ?, 1)''',
                (self.parent().user_id, amount, description,
                 transaction_type, date, category_id)
            )
        else:
            if savings_category_id:
                self.parent().db_connection.execute(
                    '''INSERT INTO transactions
                       (user_id, amount, description, transaction_type,
                        date, category_id, savings_category_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (self.parent().user_id, amount, description,
                     transaction_type, date, category_id, savings_category_id)
                )
            else:
                self.parent().db_connection.execute(
                    '''INSERT INTO transactions
                       (user_id, amount, description, transaction_type,
                        date, category_id)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (self.parent().user_id, amount, description,
                     transaction_type, date, category_id)
                )

        self.parent().db_connection.commit()

        if savings_category_id:
            amount_saved = self.parent().db_connection.execute(
                """SELECT SUM(amount) FROM transactions
                   WHERE user_id = ? AND category_id = ?
                   AND transaction_type = 'entrada'""",
                (self.parent().user_id, savings_category_id)
            ).fetchone()[0] or 0

            amount_used = self.parent().db_connection.execute(
                """SELECT SUM(amount) FROM transactions
                   WHERE user_id = ? AND savings_category_id = ?""",
                (self.parent().user_id, savings_category_id)
            ).fetchone()[0] or 0

            if (amount_saved - amount_used) <= 0:
                self.parent().db_connection.execute(
                    "UPDATE categories SET is_hidden = 1 WHERE id = ?",
                    (savings_category_id,)
                )
                self.parent().db_connection.commit()
                QMessageBox.information(
                    self, "Categoria Ocultada",
                    "A categoria de guardar dinheiro foi ocultada "
                    "pois todo o valor guardado foi utilizado."
                )

        if is_savings_goal:
            QMessageBox.information(
                self, "Sucesso",
                f"Valor de R$ {amount:.2f} adicionado à sua meta!"
            )
        else:
            QMessageBox.information(
                self, "Sucesso", "Transação adicionada com sucesso!"
            )

        self.accept()


class EditTransactionDialog(QDialog):
    def __init__(self, parent=None, transaction_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Transação")
        self.setMinimumWidth(400)
        self.transaction_id = transaction_id
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.amount_label = QLabel("Valor:")
        self.amount_input = QLineEdit()

        self.description_label = QLabel("Descrição:")
        self.description_input = QLineEdit()

        self.type_label = QLabel("Tipo:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["entrada", "saida"])

        self.date_label = QLabel("Data:")
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)

        self.category_label = QLabel("Categoria:")
        self.category_combobox = QComboBox()
        self.category_combobox.setEditable(True)

        categories = parent.db_connection.execute(
            'SELECT name FROM categories WHERE user_id = ? ORDER BY name',
            (parent.user_id,)
        ).fetchall()
        self.category_combobox.addItems(
            [c['name'] for c in categories]
        )

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_transaction)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.amount_label)
        layout.addWidget(self.amount_input)
        layout.addWidget(self.description_label)
        layout.addWidget(self.description_input)
        layout.addWidget(self.type_label)
        layout.addWidget(self.type_combobox)
        layout.addWidget(self.date_label)
        layout.addWidget(self.date_edit)
        layout.addWidget(self.category_label)
        layout.addWidget(self.category_combobox)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.load_transaction_data()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
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
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def load_transaction_data(self):
        """Carrega dados da transação"""
        transaction = self.parent().db_connection.execute(
            'SELECT * FROM transactions WHERE id = ?',
            (self.transaction_id,)
        ).fetchone()

        self.amount_input.setText(str(transaction['amount']))
        self.description_input.setText(transaction['description'])
        self.type_combobox.setCurrentText(transaction['transaction_type'])

        date = datetime.strptime(transaction['date'], '%Y-%m-%d').date()
        self.date_edit.setDate(date)

        category_id = transaction['category_id']
        if category_id:
            cat = self.parent().db_connection.execute(
                'SELECT name FROM categories WHERE id = ?',
                (category_id,)
            ).fetchone()
            if cat:
                self.category_combobox.setCurrentText(cat['name'])

    def save_transaction(self):
        """Salva as alterações na transação"""
        try:
            amount = float(self.amount_input.text().replace(',', '.'))
            if amount <= 0:
                QMessageBox.warning(
                    self, "Erro", "O valor deve ser positivo."
                )
                return
        except ValueError:
            QMessageBox.warning(
                self, "Erro", "O valor deve ser um número válido."
            )
            return

        description = self.description_input.text().strip()
        if not description:
            QMessageBox.warning(
                self, "Erro", "A descrição não pode estar vazia."
            )
            return

        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText().strip()

        if not category_name:
            QMessageBox.warning(
                self, "Erro", "A categoria não pode estar vazia."
            )
            return

        cat = self.parent().db_connection.execute(
            'SELECT id FROM categories WHERE user_id = ? AND name = ?',
            (self.parent().user_id, category_name)
        ).fetchone()

        if cat:
            category_id = cat['id']
        else:
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name) VALUES (?, ?)',
                (self.parent().user_id, category_name)
            )
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.parent().user_id, category_name)
            ).fetchone()['id']

        self.parent().db_connection.execute(
            '''UPDATE transactions
               SET amount=?, description=?, transaction_type=?,
                   date=?, category_id=?
               WHERE id=?''',
            (amount, description, transaction_type,
             date, category_id, self.transaction_id)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(
            self, "Sucesso", "Transação atualizada com sucesso!"
        )
        self.accept()

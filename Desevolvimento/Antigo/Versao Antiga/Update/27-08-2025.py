import sys
import os
import sqlite3
import json
import socket
import subprocess
import threading
import re
import socks
from datetime import datetime, timedelta
import calendar
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np
import requests
import random

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
                            QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QDateEdit, QDialog,
                            QTabWidget, QGroupBox, QRadioButton, QTextEdit, QFileDialog, QScrollArea,
                            QFrame, QSplitter, QCalendarWidget, QProgressBar, QSystemTrayIcon, QMenu,
                            QAction, QCheckBox, QSpinBox, QDoubleSpinBox, QSlider, QGridLayout, QColorDialog,
                            QStyleFactory, QFormLayout, QMainWindow, QDockWidget, QShortcut, QListWidget,
                            QProgressDialog)
from PyQt5.QtCore import Qt, QDate, QSize, QRect, QTimer, QSettings, QPoint, QUrl, QThread, pyqtSignal
from PyQt5.QtGui import (QFont, QColor, QPalette, QIcon, QTextCharFormat, QTextCursor, QPixmap,
                        QDesktopServices, QKeySequence)
# Versão do banco de dados
DB_VERSION = 3

class DBUpdater:
    """Classe responsável por atualizar o esquema do banco de dados quando necessário"""

    @staticmethod
    def check_and_update(db_connection, username):
        """Verifica a versão do banco de dados e atualiza se necessário"""
        cursor = db_connection.cursor()

        # Verificar se a tabela de versão existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'")
        if not cursor.fetchone():
            # Criar tabela de versão se não existir
            cursor.execute('CREATE TABLE db_version (version INTEGER)')
            cursor.execute('INSERT INTO db_version VALUES (1)')
            db_connection.commit()
            current_version = 1
        else:
            # Verificar se a tabela contém registros
            version_record = cursor.execute('SELECT version FROM db_version').fetchone()
            if version_record is None:
                # A tabela existe mas está vazia, inserir versão 1
                cursor.execute('INSERT INTO db_version VALUES (1)')
                db_connection.commit()
                current_version = 1
            else:
                current_version = version_record[0]

        # Se a versão atual for menor que a versão esperada, atualizar
        if current_version < DB_VERSION:
            print(f"Atualizando banco de dados de versão {current_version} para versão {DB_VERSION}")

            # Atualização da versão 1 para 2
            if current_version == 1:
                try:
                    # Backup antes da atualização
                    db_path = os.path.join('dados', f'{username}.db')
                    backup_path = os.path.join('dados', f'{username}_backup_v1.db')
                    import shutil
                    shutil.copy2(db_path, backup_path)
                    print(f"Backup criado em: {backup_path}")

                    # Iniciar transação para garantir consistência
                    db_connection.execute("BEGIN TRANSACTION")

                    # Verificar se as colunas já existem (evitar erro)
                    cursor.execute("PRAGMA table_info(categories)")
                    columns = [info[1] for info in cursor.fetchall()]

                    # Adicionar coluna para valor de quitação às categorias se não existir
                    if 'total_amount' not in columns:
                        cursor.execute('ALTER TABLE categories ADD COLUMN total_amount REAL DEFAULT 0')

                    if 'is_payment_goal' not in columns:
                        cursor.execute('ALTER TABLE categories ADD COLUMN is_payment_goal INTEGER DEFAULT 0')

                    # Criar tabela de orçamentos mensais se não existir
                    cursor.execute('''CREATE TABLE IF NOT EXISTS category_budgets
                                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_id INTEGER NOT NULL,
                                    category_id INTEGER NOT NULL,
                                    month INTEGER NOT NULL,
                                    year INTEGER NOT NULL,
                                    amount REAL NOT NULL,
                                    FOREIGN KEY (user_id) REFERENCES users (id),
                                    FOREIGN KEY (category_id) REFERENCES categories (id),
                                    UNIQUE(user_id, category_id, month, year))''')

                    # Criar tabela de metas de economia se não existir
                    cursor.execute('''CREATE TABLE IF NOT EXISTS savings_goals
                                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_id INTEGER NOT NULL,
                                    name TEXT NOT NULL,
                                    target_amount REAL NOT NULL,
                                    current_amount REAL DEFAULT 0,
                                    start_date TEXT NOT NULL,
                                    deadline TEXT,
                                    category_id INTEGER,
                                    notes TEXT,
                                    FOREIGN KEY (user_id) REFERENCES users (id),
                                    FOREIGN KEY (category_id) REFERENCES categories (id))''')

                    # Criar tabela de configurações do usuário se não existir
                    cursor.execute('''CREATE TABLE IF NOT EXISTS user_settings
                                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_id INTEGER NOT NULL,
                                    setting_key TEXT NOT NULL,
                                    setting_value TEXT,
                                    FOREIGN KEY (user_id) REFERENCES users (id),
                                    UNIQUE(user_id, setting_key))''')

                    # Atualizar a versão no banco de dados
                    cursor.execute('UPDATE db_version SET version = 2')
                    db_connection.commit()

                    print("Banco de dados atualizado com sucesso para a versão 2")
                except Exception as e:
                    db_connection.rollback()
                    print(f"Erro ao atualizar banco de dados: {e}")
                    import traceback
                    traceback.print_exc()
                    return False

            # Adicionar mais atualizações para versões futuras aqui...

        return True

class AddTransactionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Transação")
        self.setMinimumWidth(400)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.amount_label = QLabel("Valor:")
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("Digite o valor (ex: 150.00)")

        self.description_label = QLabel("Descrição:")
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Digite a descrição da transação")

        self.type_label = QLabel("Tipo:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["entrada", "saida"])
        self.type_combobox.setCurrentIndex(1)  # Saída como padrão (mais comum)

        self.date_label = QLabel("Data:")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)

        self.category_label = QLabel("Categoria:")
        self.category_combobox = QComboBox()
        self.category_combobox.setEditable(True)  # Permitir criar nova categoria
        self.category_combobox.currentTextChanged.connect(self.check_category_type)

        # Carregar categorias do banco de dados
        self.categories = parent.db_connection.execute(
            'SELECT id, name, is_payment_goal, is_savings_goal FROM categories WHERE user_id = ? ORDER BY name',
            (parent.user_id,)
        ).fetchall()

        # Mapear categorias por nome para referência rápida
        self.category_map = {}
        for category in self.categories:
            category_name = category['name']
            self.category_combobox.addItem(category_name)

            # Verificar se a coluna is_savings_goal existe
            has_savings_column = 'is_savings_goal' in category.keys()

            # Criar um mapa de categorias com suas propriedades
            self.category_map[category_name] = {
                'id': category['id'],
                'is_payment_goal': category['is_payment_goal'] == 1,
                'is_savings_goal': category['is_savings_goal'] == 1 if has_savings_column else False
            }

        # Informação para metas de guardar dinheiro
        self.savings_info_label = QLabel("")
        self.savings_info_label.setVisible(False)
        self.savings_info_label.setStyleSheet("color: #3498db; font-style: italic;")

        # Botões
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
        layout.addWidget(self.savings_info_label)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

        # Verificar categoria inicial
        self.check_category_type(self.category_combobox.currentText())

    def check_category_type(self, category_name):
        """Verifica se a categoria selecionada é uma meta de guardar dinheiro e ajusta a interface"""
        if category_name in self.category_map:
            category_info = self.category_map[category_name]

            if category_info['is_savings_goal']:
                # Se for meta de guardar dinheiro, forçar tipo como "entrada" e desabilitar combobox
                self.type_combobox.setCurrentText("entrada")
                self.type_combobox.setEnabled(False)
                self.savings_info_label.setText("Esta categoria é uma meta de guardar dinheiro. \nO valor será adicionado ao seu total guardado.")
                self.savings_info_label.setVisible(True)
            else:
                # Caso contrário, habilitar combobox
                self.type_combobox.setEnabled(True)
                self.savings_info_label.setVisible(False)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.add_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def add_transaction(self):
        """
        Adiciona uma nova transação ao banco de dados
        Valida os dados antes de adicionar
        """
        try:
            amount = float(self.amount_input.text().replace(',', '.'))
            if amount <= 0:
                QMessageBox.warning(self, "Erro", "O valor da transação deve ser positivo.")
                return
        except ValueError:
            QMessageBox.warning(self, "Erro", "O valor da transação deve ser um número válido.")
            return

        description = self.description_input.text().strip()
        if not description:
            QMessageBox.warning(self, "Erro", "A descrição não pode estar vazia.")
            return

        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText().strip()

        if not category_name:
            QMessageBox.warning(self, "Erro", "A categoria não pode estar vazia.")
            return

        # Obter o ID da categoria ou criar uma nova
        category_id = None
        is_savings_goal = False

        if category_name in self.category_map:
            category_id = self.category_map[category_name]['id']
            is_savings_goal = self.category_map[category_name]['is_savings_goal']
        else:
            # Se a categoria não existir, adicioná-la
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name) VALUES (?, ?)',
                (self.parent().user_id, category_name)
            )
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.parent().user_id, category_name)
            ).fetchone()['id']

        # Inserir a transação
        self.parent().db_connection.execute(
            'INSERT INTO transactions (user_id, amount, description, transaction_type, date, category_id) VALUES (?, ?, ?, ?, ?, ?)',
            (self.parent().user_id, amount, description, transaction_type, date, category_id)
        )
        self.parent().db_connection.commit()

        # Mensagem específica para metas de guardar dinheiro
        if is_savings_goal:
            QMessageBox.information(self, "Sucesso", f"Valor de R$ {amount:.2f} adicionado à sua meta de guardar dinheiro!")
        else:
            QMessageBox.information(self, "Sucesso", "Transação adicionada com sucesso!")

        self.accept()

class EditTransactionDialog(QDialog):
    def __init__(self, parent=None, transaction_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Transação")
        self.setMinimumWidth(400)
        self.transaction_id = transaction_id
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
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
        self.category_combobox.setEditable(True)  # Permitir editar categoria

        # Carregar categorias do banco de dados
        categories = parent.db_connection.execute('SELECT name FROM categories WHERE user_id = ? ORDER BY name',
                                                (parent.user_id,)).fetchall()
        category_names = [category['name'] for category in categories]
        self.category_combobox.addItems(category_names)

        # Botões
        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_transaction)

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

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Carregar dados da transação
        self.load_transaction_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def load_transaction_data(self):
        """
        Carrega dados da transação do banco de dados para o formulário
        """
        transaction = self.parent().db_connection.execute(
            'SELECT * FROM transactions WHERE id = ?',
            (self.transaction_id,)
        ).fetchone()

        self.amount_input.setText(str(transaction['amount']))
        self.description_input.setText(transaction['description'])
        self.type_combobox.setCurrentText(transaction['transaction_type'])

        date = datetime.strptime(transaction['date'], '%Y-%m-%d').date()
        self.date_edit.setDate(date)

        # Definir a categoria selecionada no combobox
        category_id = transaction['category_id']
        if category_id:
            category_name = self.parent().db_connection.execute(
                'SELECT name FROM categories WHERE id = ?',
                (category_id,)
            ).fetchone()
            if category_name:
                self.category_combobox.setCurrentText(category_name['name'])

    def save_transaction(self):
        """
        Salva as alterações na transação
        """
        try:
            amount = float(self.amount_input.text().replace(',', '.'))
            if amount <= 0:
                QMessageBox.warning(self, "Erro", "O valor da transação deve ser positivo.")
                return
        except ValueError:
            QMessageBox.warning(self, "Erro", "O valor da transação deve ser um número válido.")
            return

        description = self.description_input.text().strip()
        if not description:
            QMessageBox.warning(self, "Erro", "A descrição não pode estar vazia.")
            return

        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText().strip()

        if not category_name:
            QMessageBox.warning(self, "Erro", "A categoria não pode estar vazia.")
            return

        # Obter o ID da categoria ou criar uma nova
        category_id = self.parent().db_connection.execute(
            'SELECT id FROM categories WHERE user_id = ? AND name = ?',
            (self.parent().user_id, category_name)
        ).fetchone()

        if category_id:
            category_id = category_id['id']
        else:
            # Se a categoria não existir, adicioná-la
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name) VALUES (?, ?)',
                (self.parent().user_id, category_name)
            )
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.parent().user_id, category_name)
            ).fetchone()['id']

        # Atualizar a transação
        self.parent().db_connection.execute(
            'UPDATE transactions SET amount = ?, description = ?, transaction_type = ?, date = ?, category_id = ? WHERE id = ?',
            (amount, description, transaction_type, date, category_id, self.transaction_id)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(self, "Sucesso", "Transação atualizada com sucesso!")
        self.accept()


class AddNoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Nota")
        self.setMinimumWidth(400)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()  # Usar QTextEdit para notas mais longas
        self.note_input.setMinimumHeight(150)
        self.note_input.setPlaceholderText("Digite sua nota aqui...")

        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.add_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def add_note(self):
        """
        Adiciona uma nova nota ao banco de dados
        """
        note = self.note_input.toPlainText().strip()
        if not note:
            QMessageBox.warning(self, "Erro", "A nota não pode estar vazia.")
            return

        self.parent().db_connection.execute(
            'INSERT INTO notes (user_id, note) VALUES (?, ?)',
            (self.parent().user_id, note)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(self, "Sucesso", "Nota adicionada com sucesso!")
        self.accept()


class EditNoteDialog(QDialog):
    def __init__(self, parent=None, note_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Nota")
        self.setMinimumWidth(400)
        self.note_id = note_id
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()
        self.note_input.setMinimumHeight(150)

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Carregar dados da nota
        self.load_note_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def load_note_data(self):
        """
        Carrega dados da nota do banco de dados para o formulário
        """
        note = self.parent().db_connection.execute(
            'SELECT * FROM notes WHERE id = ?',
            (self.note_id,)
        ).fetchone()

        self.note_input.setText(note['note'])

    def save_note(self):
        """
        Salva as alterações na nota
        """
        note = self.note_input.toPlainText().strip()
        if not note:
            QMessageBox.warning(self, "Erro", "A nota não pode estar vazia.")
            return

        self.parent().db_connection.execute(
            'UPDATE notes SET note = ? WHERE id = ?',
            (note, self.note_id)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(self, "Sucesso", "Nota atualizada com sucesso!")
        self.accept()


class AddCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Categoria")
        self.setMinimumWidth(400)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()
        self.category_name_input.setPlaceholderText("Digite o nome da categoria")

        # Adicionar grupo para tipos de meta
        self.goal_group = QGroupBox("Tipo de Meta:")
        self.goal_layout = QVBoxLayout()

        # Opções de meta
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
        self.total_amount_input.setPlaceholderText("Valor total da meta (ex: 20000.00)")
        self.total_amount_input.setEnabled(False)

        # Botões
        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
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

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCheckBox, QRadioButton {
                    color: #ecf0f1;
                }
                QGroupBox {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    margin-top: 10px;
                    color: #ecf0f1;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.add_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    margin-top: 10px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def toggle_goal_options(self, checked):
        """Ativa/desativa o campo de valor total de acordo com o radiobutton"""
        self.total_amount_input.setEnabled(
            self.payment_goal_radio.isChecked() or self.savings_goal_radio.isChecked()
        )

    def add_category(self):
        """
        Adiciona uma nova categoria ao banco de dados
        """
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(self, "Erro", "O nome da categoria não pode estar vazio.")
            return

        # Verificar o valor total se for meta de quitação ou guardar dinheiro
        total_amount = 0
        is_payment_goal = 0
        is_savings_goal = 0

        if self.payment_goal_radio.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(self.total_amount_input.text().replace(',', '.'))
                if total_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor total da meta deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor total deve ser um número válido.")
                return
        elif self.savings_goal_radio.isChecked():
            is_savings_goal = 1
            try:
                total_amount = float(self.total_amount_input.text().replace(',', '.'))
                if total_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor total da meta deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor total deve ser um número válido.")
                return

        try:
            # Verificar se a coluna is_savings_goal existe
            column_exists = self.parent().db_connection.execute(
                "SELECT COUNT(*) FROM pragma_table_info('categories') WHERE name='is_savings_goal'"
            ).fetchone()[0] > 0

            if column_exists:
                # Coluna existe, usar versão completa
                self.parent().db_connection.execute(
                    'INSERT INTO categories (user_id, name, total_amount, is_payment_goal, is_savings_goal) VALUES (?, ?, ?, ?, ?)',
                    (self.parent().user_id, category_name, total_amount, is_payment_goal, is_savings_goal)
                )
            else:
                # Coluna não existe, usar versão compatível
                self.parent().db_connection.execute(
                    'INSERT INTO categories (user_id, name, total_amount, is_payment_goal) VALUES (?, ?, ?, ?)',
                    (self.parent().user_id, category_name, total_amount, is_payment_goal)
                )

            self.parent().db_connection.commit()

            QMessageBox.information(self, "Sucesso", "Categoria adicionada com sucesso!")
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Erro", f"A categoria '{category_name}' já existe.")

class EditCategoryDialog(QDialog):
    def __init__(self, parent=None, category_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Categoria")
        self.setMinimumWidth(400)
        self.category_id = category_id
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()

        # Adicionar grupo para tipos de meta
        self.goal_group = QGroupBox("Tipo de Meta:")
        self.goal_layout = QVBoxLayout()

        # Opções de meta
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
        self.total_amount_input.setPlaceholderText("Valor total da meta (ex: 20000.00)")

        # Mostrar progresso
        self.progress_label = QLabel("Progresso da Meta:")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_info = QLabel()

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
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

        # Carregar dados da categoria
        self.load_category_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCheckBox, QRadioButton {
                    color: #ecf0f1;
                }
                QGroupBox {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    margin-top: 10px;
                    color: #ecf0f1;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QProgressBar {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    text-align: center;
                    background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    margin-top: 10px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QProgressBar {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def toggle_goal_options(self, checked):
        """Ativa/desativa o campo de valor total de acordo com o radiobutton"""
        has_goal = self.payment_goal_radio.isChecked() or self.savings_goal_radio.isChecked()
        self.total_amount_input.setEnabled(has_goal)
        self.progress_bar.setVisible(has_goal)
        self.progress_label.setVisible(has_goal)
        self.progress_info.setVisible(has_goal)

    def load_category_data(self):
        """
        Carrega dados da categoria do banco de dados para o formulário
        """
        category = self.parent().db_connection.execute(
            'SELECT * FROM categories WHERE id = ?',
            (self.category_id,)
        ).fetchone()

        self.category_name_input.setText(category['name'])

        # Verificar se a coluna is_savings_goal existe
        column_exists = self.parent().db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('categories') WHERE name='is_savings_goal'"
        ).fetchone()[0] > 0

        # Configurar opções de meta
        is_payment_goal = category['is_payment_goal'] == 1
        is_savings_goal = False

        if column_exists:
            # Se a coluna existir, verificar seu valor
            is_savings_goal = category['is_savings_goal'] == 1

        if is_payment_goal:
            self.payment_goal_radio.setChecked(True)
        elif is_savings_goal:
            self.savings_goal_radio.setChecked(True)
        else:
            self.no_goal_radio.setChecked(True)

        total_amount = category['total_amount'] or 0
        self.total_amount_input.setText(str(total_amount))
        self.total_amount_input.setEnabled(is_payment_goal or is_savings_goal)

        # Mostrar progresso se for meta
        has_goal = is_payment_goal or is_savings_goal
        self.progress_bar.setVisible(has_goal)
        self.progress_label.setVisible(has_goal)
        self.progress_info.setVisible(has_goal)

        if has_goal and total_amount > 0:
            # Calcular total já pago/guardado
            if is_payment_goal:
                # Para metas de quitação, soma transações de saída
                total_accumulated = self.parent().db_connection.execute(
                    "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'",
                    (self.parent().user_id, self.category_id)
                ).fetchone()[0] or 0
            else:
                # Para metas de guardar dinheiro, soma transações de entrada
                total_accumulated = self.parent().db_connection.execute(
                    "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'entrada'",
                    (self.parent().user_id, self.category_id)
                ).fetchone()[0] or 0

            # Atualizar barra de progresso
            progress_percentage = min(100, int((total_accumulated / total_amount) * 100)) if total_amount > 0 else 0
            self.progress_bar.setValue(progress_percentage)

            # Informações de progresso
            remaining = total_amount - total_accumulated if is_payment_goal else total_amount - total_accumulated

            if is_payment_goal:
                self.progress_info.setText(
                    f"Pago: R$ {total_accumulated:.2f} de R$ {total_amount:.2f} ({progress_percentage}%)\n"
                    f"Restante: R$ {remaining:.2f}"
                )
            else:
                self.progress_info.setText(
                    f"Guardado: R$ {total_accumulated:.2f} de R$ {total_amount:.2f} ({progress_percentage}%)\n"
                    f"Restante: R$ {remaining:.2f}"
                )

    def save_category(self):
        """
        Salva as alterações na categoria
        """
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(self, "Erro", "O nome da categoria não pode estar vazio.")
            return

        # Verificar o valor total se for meta
        total_amount = 0
        is_payment_goal = 0
        is_savings_goal = 0

        if self.payment_goal_radio.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(self.total_amount_input.text().replace(',', '.'))
                if total_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor total da meta deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor total deve ser um número válido.")
                return
        elif self.savings_goal_radio.isChecked():
            is_savings_goal = 1
            try:
                total_amount = float(self.total_amount_input.text().replace(',', '.'))
                if total_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor total da meta deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor total deve ser um número válido.")
                return

        try:
            # Verificar se a coluna is_savings_goal existe
            column_exists = self.parent().db_connection.execute(
                "SELECT COUNT(*) FROM pragma_table_info('categories') WHERE name='is_savings_goal'"
            ).fetchone()[0] > 0

            if column_exists:
                # Coluna existe, usar versão completa
                self.parent().db_connection.execute(
                    'UPDATE categories SET name = ?, total_amount = ?, is_payment_goal = ?, is_savings_goal = ? WHERE id = ?',
                    (category_name, total_amount, is_payment_goal, is_savings_goal, self.category_id)
                )
            else:
                # Coluna não existe, usar versão compatível
                self.parent().db_connection.execute(
                    'UPDATE categories SET name = ?, total_amount = ?, is_payment_goal = ? WHERE id = ?',
                    (category_name, total_amount, is_payment_goal, self.category_id)
                )

            self.parent().db_connection.commit()

            QMessageBox.information(self, "Sucesso", "Categoria atualizada com sucesso!")
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Erro", f"A categoria '{category_name}' já existe.")

class BudgetDialog(QDialog):
    """Diálogo para definir orçamentos mensais por categoria"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Definir Orçamento Mensal")
        self.setMinimumWidth(500)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.month_label = QLabel("Mês:")
        self.month_combo = QComboBox()
        self.month_combo.addItems(["Janeiro", "Fevereiro", "Março", "Abril", "Maio",
                                  "Junho", "Julho", "Agosto", "Setembro", "Outubro",
                                  "Novembro", "Dezembro"])
        # Definir mês atual
        current_month = datetime.now().month
        self.month_combo.setCurrentIndex(current_month - 1)

        self.year_label = QLabel("Ano:")
        self.year_combo = QComboBox()
        current_year = datetime.now().year
        # Adicionar anos (atual, próximo e anteriores)
        for year in range(current_year - 2, current_year + 3):
            self.year_combo.addItem(str(year))
        # Definir ano atual
        self.year_combo.setCurrentText(str(current_year))

        # Botão para carregar orçamentos existentes
        self.load_button = QPushButton("Carregar Orçamentos Existentes")
        self.load_button.clicked.connect(self.load_existing_budgets)

        # Tabela de categorias e orçamentos
        self.budget_table = QTableWidget()
        self.budget_table.setColumnCount(3)
        self.budget_table.setHorizontalHeaderLabels(["Categoria", "Orçamento (R$)", "Gastos Médios (R$)"])
        self.budget_table.horizontalHeader().setStretchLastSection(True)

        # Botões
        self.save_button = QPushButton("Salvar Orçamentos")
        self.save_button.clicked.connect(self.save_budgets)

        self.suggest_button = QPushButton("Sugerir com Base nos Gastos")
        self.suggest_button.clicked.connect(self.suggest_budgets)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()

        # Layout para mês e ano
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

        # Carregar categorias
        self.load_categories()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                    selection-background-color: #3498db;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    padding: 5px;
                    border: 1px solid #4b6584;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QTableWidget {
                    background-color: white;
                    alternate-background-color: #f9f9f9;
                    selection-background-color: #e3f2fd;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
            self.suggest_button.setStyleSheet("background-color: #2196F3; color: white;")

    def load_categories(self):
        """Carrega as categorias do usuário para a tabela"""
        try:
            categories = self.parent().db_connection.execute(
                'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
                (self.parent().user_id,)
            ).fetchall()

            self.budget_table.setRowCount(len(categories))

            for i, category in enumerate(categories):
                # Salvar o ID da categoria como dados do item
                category_item = QTableWidgetItem(category['name'])
                category_item.setData(Qt.UserRole, category['id'])

                # Adicionar campo de entrada para orçamento
                budget_input = QLineEdit()
                budget_input.setPlaceholderText("0.00")

                # Calcular média de gastos dos últimos 3 meses
                avg_expense = self.calculate_average_expense(category['id'])
                avg_expense_item = QTableWidgetItem(f"{avg_expense:.2f}")

                self.budget_table.setItem(i, 0, category_item)
                self.budget_table.setCellWidget(i, 1, budget_input)
                self.budget_table.setItem(i, 2, avg_expense_item)

            self.budget_table.resizeColumnsToContents()

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível carregar as categorias: {str(e)}")

    def calculate_average_expense(self, category_id):
        """Calcula a média de gastos dos últimos 3 meses para uma categoria"""
        try:
            # Obter data de 3 meses atrás
            today = datetime.now()
            three_months_ago = today.replace(day=1) - timedelta(days=1)
            three_months_ago = three_months_ago.replace(day=1) - timedelta(days=1)
            three_months_ago = three_months_ago.replace(day=1) - timedelta(days=1)
            three_months_ago = three_months_ago.replace(day=1)
            three_months_ago_str = three_months_ago.strftime('%Y-%m-%d')

            # Consultar gastos dos últimos 3 meses
            result = self.parent().db_connection.execute(
                '''
                SELECT SUM(amount) as total, COUNT(DISTINCT strftime('%Y-%m', date)) as months
                FROM transactions
                WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'
                AND date >= ?
                ''',
                (self.parent().user_id, category_id, three_months_ago_str)
            ).fetchone()

            total = result['total'] or 0
            months = result['months'] or 1  # Evitar divisão por zero

            return total / months

        except Exception as e:
            print(f"Erro ao calcular média de gastos: {e}")
            return 0.0

    def load_existing_budgets(self):
        """Carrega orçamentos existentes para o mês/ano selecionado"""
        try:
            selected_month = self.month_combo.currentIndex() + 1  # Mês começa em 1
            selected_year = self.year_combo.currentText()

            budgets = self.parent().db_connection.execute(
                '''
                SELECT cb.category_id, cb.amount
                FROM category_budgets cb
                WHERE cb.user_id = ? AND cb.month = ? AND cb.year = ?
                ''',
                (self.parent().user_id, selected_month, selected_year)
            ).fetchall()

            # Mapear orçamentos por ID de categoria
            budget_map = {b['category_id']: b['amount'] for b in budgets}

            # Preencher a tabela com os valores existentes
            for i in range(self.budget_table.rowCount()):
                category_id = self.budget_table.item(i, 0).data(Qt.UserRole)
                if category_id in budget_map:
                    budget_input = self.budget_table.cellWidget(i, 1)
                    budget_input.setText(str(budget_map[category_id]))

            QMessageBox.information(self, "Sucesso",
                                  f"Orçamentos carregados para {self.month_combo.currentText()} de {selected_year}.")

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível carregar os orçamentos: {str(e)}")

    def suggest_budgets(self):
        """Sugere orçamentos com base nos gastos médios"""
        try:
            for i in range(self.budget_table.rowCount()):
                avg_expense_text = self.budget_table.item(i, 2).text()
                try:
                    avg_expense = float(avg_expense_text.replace(',', '.'))
                    # Adicionar 10% de margem aos gastos médios
                    suggested_budget = avg_expense * 1.1
                    budget_input = self.budget_table.cellWidget(i, 1)
                    budget_input.setText(f"{suggested_budget:.2f}")
                except:
                    continue
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível sugerir orçamentos: {str(e)}")

    def save_budgets(self):
        """Salva os orçamentos definidos no banco de dados"""
        try:
            selected_month = self.month_combo.currentIndex() + 1  # Mês começa em 1
            selected_year = self.year_combo.currentText()

            # Começar uma transação
            self.parent().db_connection.execute("BEGIN TRANSACTION")

            # Deletar orçamentos existentes para este mês/ano
            self.parent().db_connection.execute(
                "DELETE FROM category_budgets WHERE user_id = ? AND month = ? AND year = ?",
                (self.parent().user_id, selected_month, selected_year)
            )

            # Inserir novos orçamentos
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
                                '''
                                INSERT INTO category_budgets
                                (user_id, category_id, month, year, amount)
                                VALUES (?, ?, ?, ?, ?)
                                ''',
                                (self.parent().user_id, category_id, selected_month, selected_year, budget_amount)
                            )
                            count += 1
                    except ValueError:
                        continue

            # Confirmar transação
            self.parent().db_connection.commit()

            QMessageBox.information(self, "Sucesso",
                                  f"Foram salvos {count} orçamentos para {self.month_combo.currentText()} de {selected_year}.")
            self.accept()

        except Exception as e:
            # Reverter em caso de erro
            self.parent().db_connection.rollback()
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar os orçamentos: {str(e)}")


class SavingsGoalDialog(QDialog):
    """Diálogo para gerenciar metas de economia"""
    def __init__(self, parent=None, goal_id=None):
        super().__init__(parent)
        self.goal_id = goal_id
        self.is_edit_mode = goal_id is not None
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        self.setWindowTitle("Meta de Economia" if self.is_edit_mode else "Nova Meta de Economia")
        self.setMinimumWidth(450)

        # Widgets
        self.name_label = QLabel("Nome da Meta:")
        self.name_input = QLineEdit()

        self.target_label = QLabel("Valor Alvo (R$):")
        self.target_input = QLineEdit()

        self.current_label = QLabel("Valor Atual (R$):")
        self.current_input = QLineEdit()
        self.current_input.setPlaceholderText("0.00")

        self.deadline_label = QLabel("Prazo (opcional):")
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setDisplayFormat("yyyy-MM-dd")
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setDate(QDate.currentDate().addMonths(6))  # Padrão: 6 meses a partir de hoje

        self.has_deadline_check = QCheckBox("Definir prazo")
        self.has_deadline_check.toggled.connect(self.toggle_deadline)
        self.has_deadline_check.setChecked(False)
        self.deadline_edit.setEnabled(False)

        self.category_label = QLabel("Categoria relacionada (opcional):")
        self.category_combo = QComboBox()
        self.category_combo.addItem("Nenhuma", None)

        # Carregar categorias
        if parent and hasattr(parent, 'db_connection') and hasattr(parent, 'user_id'):
            categories = parent.db_connection.execute(
                'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
                (parent.user_id,)
            ).fetchall()

            for category in categories:
                self.category_combo.addItem(category['name'], category['id'])

        self.notes_label = QLabel("Notas:")
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Observações, detalhes ou motivação para esta meta...")
        self.notes_input.setMaximumHeight(100)

        # Widgets de progresso (visíveis apenas no modo de edição)
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
        if self.is_edit_mode:
            self.save_button = QPushButton("Atualizar Meta")
            self.deposit_button = QPushButton("Adicionar Depósito")
            self.deposit_button.clicked.connect(self.add_deposit)

            button_layout = QHBoxLayout()
            button_layout.addWidget(self.deposit_button)
            button_layout.addWidget(self.save_button)
        else:
            self.save_button = QPushButton("Criar Meta")
            button_layout = QHBoxLayout()
            button_layout.addWidget(self.save_button)

        self.save_button.clicked.connect(self.save_goal)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

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

        # Adicionar widgets de progresso apenas no modo de edição
        if self.is_edit_mode:
            progress_layout = QVBoxLayout()
            progress_layout.addWidget(self.progress_label)
            progress_layout.addWidget(self.progress_bar)
            progress_layout.addWidget(self.time_progress_label)
            progress_layout.addWidget(self.time_progress_bar)
            progress_layout.addWidget(self.summary_label)

            layout.addLayout(progress_layout)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Se estamos editando, carregar dados da meta existente
        if self.is_edit_mode:
            self.load_goal_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCheckBox {
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QProgressBar {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    text-align: center;
                    background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            if hasattr(self, 'save_button'):
                self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            if hasattr(self, 'deposit_button'):
                self.deposit_button.setStyleSheet("background-color: #f39c12; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QProgressBar {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            if hasattr(self, 'save_button'):
                self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            if hasattr(self, 'deposit_button'):
                self.deposit_button.setStyleSheet("background-color: #FF9800; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

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
                '''
                SELECT * FROM savings_goals
                WHERE id = ? AND user_id = ?
                ''',
                (self.goal_id, self.parent().user_id)
            ).fetchone()

            if not goal:
                QMessageBox.warning(self, "Erro", "Meta não encontrada.")
                self.reject()
                return

            # Preencher campos com dados da meta
            self.name_input.setText(goal['name'])
            self.target_input.setText(str(goal['target_amount']))
            self.current_input.setText(str(goal['current_amount']))

            # Se tiver prazo, configurar
            if goal['deadline']:
                self.has_deadline_check.setChecked(True)
                deadline_date = QDate.fromString(goal['deadline'], "yyyy-MM-dd")
                self.deadline_edit.setDate(deadline_date)

                # Calcular progresso de tempo
                start_date = datetime.strptime(goal['start_date'], '%Y-%m-%d').date()
                deadline_date = datetime.strptime(goal['deadline'], '%Y-%m-%d').date()
                today = datetime.now().date()

                total_days = (deadline_date - start_date).days
                days_passed = (today - start_date).days

                if total_days > 0:
                    time_progress = min(100, int((days_passed / total_days) * 100))
                    self.time_progress_bar.setValue(time_progress)

                    days_left = (deadline_date - today).days
                    if days_left > 0:
                        self.time_progress_bar.setFormat(f"{time_progress}% ({days_left} dias restantes)")
                    else:
                        self.time_progress_bar.setFormat("Prazo expirado!")
                        self.time_progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #e74c3c; }")
            else:
                self.time_progress_label.setVisible(False)
                self.time_progress_bar.setVisible(False)

            # Configurar categoria se existir
            if goal['category_id']:
                index = self.category_combo.findData(goal['category_id'])
                if index >= 0:
                    self.category_combo.setCurrentIndex(index)

            # Notas
            if goal['notes']:
                self.notes_input.setText(goal['notes'])

            # Calcular progresso financeiro
            target = goal['target_amount']
            current = goal['current_amount']

            if target > 0:
                progress = min(100, int((current / target) * 100))
                self.progress_bar.setValue(progress)
                self.progress_bar.setFormat(f"{progress}% (R$ {current:.2f} de R$ {target:.2f})")

                remaining = target - current
                self.summary_label.setText(f"Faltam R$ {remaining:.2f} para atingir a meta.")

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível carregar os dados da meta: {str(e)}")
            self.reject()

    def save_goal(self):
        """Salva ou atualiza a meta de economia"""
        try:
            # Validar campos obrigatórios
            name = self.name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "Erro", "O nome da meta não pode estar vazio.")
                return

            # Validar valor alvo
            try:
                target_amount = float(self.target_input.text().replace(',', '.'))
                if target_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor alvo deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor alvo deve ser um número válido.")
                return

            # Validar valor atual
            try:
                current_text = self.current_input.text().strip()
                current_amount = float(current_text.replace(',', '.')) if current_text else 0
                if current_amount < 0:
                    QMessageBox.warning(self, "Erro", "O valor atual não pode ser negativo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor atual deve ser um número válido.")
                return

            # Obter prazo se configurado
            deadline = None
            if self.has_deadline_check.isChecked():
                deadline = self.deadline_edit.date().toString("yyyy-MM-dd")

            # Obter categoria selecionada
            category_id = self.category_combo.currentData()

            # Obter notas
            notes = self.notes_input.toPlainText().strip()

            # Salvar no banco de dados
            if self.is_edit_mode:
                # Atualizar meta existente
                self.parent().db_connection.execute(
                    '''
                    UPDATE savings_goals
                    SET name = ?, target_amount = ?, current_amount = ?,
                        deadline = ?, category_id = ?, notes = ?
                    WHERE id = ? AND user_id = ?
                    ''',
                    (name, target_amount, current_amount, deadline, category_id, notes,
                     self.goal_id, self.parent().user_id)
                )

                message = "Meta de economia atualizada com sucesso!"
            else:
                # Criar nova meta
                start_date = datetime.now().strftime("%Y-%m-%d")

                self.parent().db_connection.execute(
                    '''
                    INSERT INTO savings_goals
                    (user_id, name, target_amount, current_amount, start_date, deadline, category_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (self.parent().user_id, name, target_amount, current_amount,
                     start_date, deadline, category_id, notes)
                )

                message = "Nova meta de economia criada com sucesso!"

            self.parent().db_connection.commit()
            QMessageBox.information(self, "Sucesso", message)
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar a meta: {str(e)}")

    def add_deposit(self):
        """Adiciona um depósito à meta de economia"""
        # Mostrar diálogo para informar o valor do depósito
        amount, ok = QInputDialog.getDouble(
            self, "Adicionar Depósito",
            "Informe o valor do depósito (R$):",
            0, 0, 1000000, 2
        )

        if ok and amount > 0:
            try:
                # Atualizar valor atual
                goal = self.parent().db_connection.execute(
                    'SELECT current_amount, target_amount FROM savings_goals WHERE id = ?',
                    (self.goal_id,)
                ).fetchone()

                new_amount = goal['current_amount'] + amount

                # Não deixar ultrapassar o valor alvo
                if new_amount > goal['target_amount']:
                    excess = new_amount - goal['target_amount']
                    new_amount = goal['target_amount']
                    QMessageBox.information(
                        self, "Aviso",
                        f"O depósito excede o valor alvo em R$ {excess:.2f}. "
                        f"O valor atual foi ajustado para o valor alvo."
                    )

                # Atualizar no banco de dados
                self.parent().db_connection.execute(
                    'UPDATE savings_goals SET current_amount = ? WHERE id = ?',
                    (new_amount, self.goal_id)
                )
                self.parent().db_connection.commit()

                # Atualizar interface
                self.current_input.setText(str(new_amount))

                # Atualizar barra de progresso
                progress = min(100, int((new_amount / goal['target_amount']) * 100))
                self.progress_bar.setValue(progress)
                self.progress_bar.setFormat(f"{progress}% (R$ {new_amount:.2f} de R$ {goal['target_amount']:.2f})")

                # Atualizar resumo
                remaining = goal['target_amount'] - new_amount
                self.summary_label.setText(f"Faltam R$ {remaining:.2f} para atingir a meta.")

                QMessageBox.information(self, "Sucesso", f"Depósito de R$ {amount:.2f} adicionado com sucesso!")

                # Se atingiu a meta, celebrar!
                if new_amount >= goal['target_amount']:
                    QMessageBox.information(
                        self, "Parabéns!",
                        "Você atingiu sua meta de economia! 🎉"
                    )

            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Não foi possível adicionar o depósito: {str(e)}")


class CalendarDialog(QDialog):
    """Diálogo para visualizar transações em formato de calendário"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calendário Financeiro")
        self.resize(800, 600)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setSelectionMode(QCalendarWidget.SingleSelection)

        # Configurar formato personalizado para as datas
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

        # Lista de transações para o dia selecionado
        self.transactions_label = QLabel("Transações do dia selecionado:")
        self.transactions_list = QTextEdit()
        self.transactions_list.setReadOnly(True)

        # Estatísticas do mês
        self.month_stats_label = QLabel("Estatísticas do Mês:")
        self.month_stats = QTextEdit()
        self.month_stats.setReadOnly(True)
        self.month_stats.setMaximumHeight(100)

        # Botões
        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        # Conexão de sinais
        self.calendar.selectionChanged.connect(self.update_day_transactions)
        self.calendar.currentPageChanged.connect(self.update_calendar_data)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.calendar)

        # Layout dividido para transações e estatísticas
        split_layout = QHBoxLayout()

        # Layout para transações
        trans_layout = QVBoxLayout()
        trans_layout.addWidget(self.transactions_label)
        trans_layout.addWidget(self.transactions_list)

        # Layout para estatísticas
        stats_layout = QVBoxLayout()
        stats_layout.addWidget(self.month_stats_label)
        stats_layout.addWidget(self.month_stats)

        # Adicionar os layouts divididos
        split_layout.addLayout(trans_layout, 7)  # 70% para transações
        split_layout.addLayout(stats_layout, 3)  # 30% para estatísticas

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)

        # Carregar dados para o mês atual
        self.update_calendar_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QCalendarWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCalendarWidget QWidget {
                    alternate-background-color: #1e272e;
                }
                QCalendarWidget QAbstractItemView:enabled {
                    color: #ecf0f1;
                    background-color: #2d3436;
                    selection-background-color: #3498db;
                    selection-color: #ecf0f1;
                }
                QCalendarWidget QMenu {
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCalendarWidget QToolButton {
                    color: #ecf0f1;
                    background-color: #2d3436;
                }
            """)
            self.close_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QCalendarWidget {
                    background-color: white;
                }
                QCalendarWidget QAbstractItemView:enabled {
                    color: #333;
                    selection-background-color: #4CAF50;
                    selection-color: white;
                }
            """)
            self.close_button.setStyleSheet("background-color: #f44336; color: white;")

    def update_calendar_data(self):
        """Atualiza os dados do calendário para o mês exibido"""
        try:
            current_date = self.calendar.selectedDate()
            year = current_date.year()
            month = current_date.month()

            # Limpar formatos anteriores
            self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

            # Obter todas as transações do mês
            transactions = self.parent().db_connection.execute(
                '''
                SELECT t.*, c.name as category_name
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND strftime('%Y', t.date) = ? AND strftime('%m', t.date) = ?
                ORDER BY t.date
                ''',
                (self.parent().user_id, f"{year:04d}", f"{month:02d}")
            ).fetchall()

            # Calcular saldo por dia
            day_balances = {}
            day_transactions = {}

            for t in transactions:
                date = QDate.fromString(t['date'], "yyyy-MM-dd")
                day_key = date.toString("yyyy-MM-dd")

                # Inicializar se necessário
                if day_key not in day_balances:
                    day_balances[day_key] = 0
                    day_transactions[day_key] = []

                # Adicionar valor (positivo para entradas, negativo para saídas)
                amount = t['amount']
                if t['transaction_type'] == 'saida':
                    amount = -amount

                day_balances[day_key] += amount
                day_transactions[day_key].append(t)

            # Definir formato para cada dia com transações
            positive_format = QTextCharFormat()
            positive_format.setBackground(QColor(200, 255, 200))  # Verde claro
            positive_format.setForeground(QColor(0, 100, 0))      # Verde escuro

            negative_format = QTextCharFormat()
            negative_format.setBackground(QColor(255, 200, 200))  # Vermelho claro
            negative_format.setForeground(QColor(150, 0, 0))      # Vermelho escuro

            neutral_format = QTextCharFormat()
            neutral_format.setBackground(QColor(220, 220, 220))   # Cinza claro
            neutral_format.setForeground(QColor(50, 50, 50))      # Cinza escuro

            # Aplicar formato a cada dia
            for day_key, balance in day_balances.items():
                date = QDate.fromString(day_key, "yyyy-MM-dd")

                if balance > 0:
                    self.calendar.setDateTextFormat(date, positive_format)
                elif balance < 0:
                    self.calendar.setDateTextFormat(date, negative_format)
                else:
                    self.calendar.setDateTextFormat(date, neutral_format)

            # Calcular estatísticas do mês
            total_income = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
            total_expense = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
            balance = total_income - total_expense

            # Número de dias com transações
            active_days = len(day_balances)

            # Calcular dia com maior entrada e maior saída
            if transactions:
                max_income_day = max(
                    [t for t in transactions if t['transaction_type'] == 'entrada'],
                    key=lambda x: x['amount'],
                    default=None
                )

                max_expense_day = max(
                    [t for t in transactions if t['transaction_type'] == 'saida'],
                    key=lambda x: x['amount'],
                    default=None
                )
            else:
                max_income_day = None
                max_expense_day = None

            # Atualizar estatísticas do mês
            stats_text = f"<b>Estatísticas de {current_date.toString('MMMM yyyy').capitalize()}:</b><br>"
            stats_text += f"Total de receitas: <span style='color: green;'>R$ {total_income:.2f}</span><br>"
            stats_text += f"Total de despesas: <span style='color: red;'>R$ {total_expense:.2f}</span><br>"

            if balance >= 0:
                stats_text += f"Saldo do mês: <span style='color: green;'>R$ {balance:.2f}</span><br>"
            else:
                stats_text += f"Saldo do mês: <span style='color: red;'>R$ {balance:.2f}</span><br>"

            stats_text += f"Dias com movimento: {active_days}<br>"

            if max_income_day:
                stats_text += f"Maior receita: R$ {max_income_day['amount']:.2f} ({max_income_day['date']})<br>"

            if max_expense_day:
                stats_text += f"Maior despesa: R$ {max_expense_day['amount']:.2f} ({max_expense_day['date']})<br>"

            self.month_stats.setHtml(stats_text)

            # Atualizar transações do dia selecionado
            self.update_day_transactions()

        except Exception as e:
            import traceback
            print(f"Erro ao atualizar dados do calendário: {e}")
            print(traceback.format_exc())
            self.month_stats.setText(f"Erro ao carregar estatísticas: {str(e)}")

    def update_day_transactions(self):
        """Atualiza a lista de transações para o dia selecionado"""
        try:
            selected_date = self.calendar.selectedDate().toString("yyyy-MM-dd")

            transactions = self.parent().db_connection.execute(
                '''
                SELECT t.*, c.name as category_name
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.date = ?
                ORDER BY t.transaction_type, t.amount DESC
                ''',
                (self.parent().user_id, selected_date)
            ).fetchall()

            if not transactions:
                self.transactions_list.setHtml("<i>Nenhuma transação neste dia.</i>")
                return

            # Calcular totais do dia
            total_income = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
            total_expense = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
            day_balance = total_income - total_expense

            # Gerar HTML para a lista de transações
            html = f"<h3>Transações de {self.calendar.selectedDate().toString('dd/MM/yyyy')}</h3>"

            # Resumo do dia
            html += "<p>"
            html += f"Receitas: <b style='color: green;'>R$ {total_income:.2f}</b> | "
            html += f"Despesas: <b style='color: red;'>R$ {total_expense:.2f}</b> | "

            if day_balance >= 0:
                html += f"Saldo: <b style='color: green;'>R$ {day_balance:.2f}</b>"
            else:
                html += f"Saldo: <b style='color: red;'>R$ {day_balance:.2f}</b>"

            html += "</p>"

            # Tabela de transações
            html += "<table width='100%' cellspacing='0' cellpadding='4' style='border: 1px solid #ccc;'>"
            html += "<tr style='background-color: #f0f0f0;'>"
            html += "<th align='left'>Descrição</th>"
            html += "<th align='right'>Valor</th>"
            html += "<th align='left'>Tipo</th>"
            html += "<th align='left'>Categoria</th>"
            html += "</tr>"

            row_style1 = "background-color: #ffffff;"
            row_style2 = "background-color: #f9f9f9;"
            current_style = row_style1

            for t in transactions:
                html += f"<tr style='{current_style}'>"
                html += f"<td>{t['description']}</td>"

                if t['transaction_type'] == 'entrada':
                    html += f"<td align='right' style='color: green;'>R$ {t['amount']:.2f}</td>"
                    html += "<td>Receita</td>"
                else:
                    html += f"<td align='right' style='color: red;'>R$ {t['amount']:.2f}</td>"
                    html += "<td>Despesa</td>"

                html += f"<td>{t['category_name'] or 'Sem categoria'}</td>"
                html += "</tr>"

                # Alternar estilos de linha
                current_style = row_style2 if current_style == row_style1 else row_style1

            html += "</table>"

            self.transactions_list.setHtml(html)

        except Exception as e:
            self.transactions_list.setText(f"Erro ao carregar transações: {str(e)}")


class CashFlowDialog(QDialog):
    """Diálogo para visualizar e projetar fluxo de caixa"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Previsão de Fluxo de Caixa")
        self.resize(800, 600)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.months_label = QLabel("Meses para projetar:")
        self.months_slider = QSlider(Qt.Horizontal)
        self.months_slider.setMinimum(1)
        self.months_slider.setMaximum(12)
        self.months_slider.setValue(3)
        self.months_slider.setTickPosition(QSlider.TicksBelow)
        self.months_slider.setTickInterval(1)
        self.months_value_label = QLabel("3 meses")

        # Botão para gerar projeção
        self.generate_button = QPushButton("Gerar Projeção")
        self.generate_button.clicked.connect(self.generate_projection)

        # Área para o gráfico
        self.figure = plt.figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)

        # Tabela de projeção detalhada
        self.projection_table = QTableWidget()
        self.projection_table.setColumnCount(4)
        self.projection_table.setHorizontalHeaderLabels(["Mês", "Receitas", "Despesas", "Saldo"])
        self.projection_table.horizontalHeader().setStretchLastSection(True)

        # Textos de resumo
        self.summary_label = QLabel("Resumo da Projeção:")
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(100)

        # Botão para fechar
        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        # Conectar sinal do slider
        self.months_slider.valueChanged.connect(self.update_months_label)

        # Layout
        layout = QVBoxLayout()

        # Layout para controles
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.months_label)
        controls_layout.addWidget(self.months_slider)
        controls_layout.addWidget(self.months_value_label)
        controls_layout.addWidget(self.generate_button)

        layout.addLayout(controls_layout)

        # Layout dividido para gráfico e tabela
        split_layout = QHBoxLayout()

        # Layout para gráfico
        chart_layout = QVBoxLayout()
        chart_layout.addWidget(self.canvas)

        # Layout para tabela e resumo
        table_layout = QVBoxLayout()
        table_layout.addWidget(self.projection_table)
        table_layout.addWidget(self.summary_label)
        table_layout.addWidget(self.summary_text)

        # Adicionar os layouts divididos
        split_layout.addLayout(chart_layout, 6)  # 60% para gráfico
        split_layout.addLayout(table_layout, 4)  # 40% para tabela e resumo

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)

        # Gerar projeção inicial
        self.generate_projection()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QTableWidget {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QSlider {
                    background-color: transparent;
                }
                QSlider::groove:horizontal {
                    height: 8px;
                    background: #4b6584;
                    margin: 2px 0;
                }
                QSlider::handle:horizontal {
                    background: #3498db;
                    border: 1px solid #2980b9;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 9px;
                }
                QTableWidget {
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    padding: 5px;
                    border: 1px solid #4b6584;
                }
            """)
            self.close_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
            self.generate_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")

            # Configurar cores para o gráfico
            plt.style.use('dark_background')
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QTableWidget {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QSlider::groove:horizontal {
                    height: 8px;
                    background: #ccc;
                    margin: 2px 0;
                }
                QSlider::handle:horizontal {
                    background: #4CAF50;
                    border: 1px solid #3d8b40;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 9px;
                }
                QTableWidget {
                    gridline-color: #ccc;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.close_button.setStyleSheet("background-color: #f44336; color: white;")
            self.generate_button.setStyleSheet("background-color: #4CAF50; color: white;")

            # Configurar cores para o gráfico
            plt.style.use('default')

    def update_months_label(self, value):
        """Atualiza o label com o valor selecionado no slider"""
        self.months_value_label.setText(f"{value} {'mês' if value == 1 else 'meses'}")

    def generate_projection(self):
        """Gera a projeção de fluxo de caixa"""
        try:
            # Número de meses a projetar
            months_to_project = self.months_slider.value()

            # Obter mês e ano atuais
            today = datetime.now()
            current_month = today.month
            current_year = today.year

            # Calcular médias dos últimos 6 meses
            six_months_ago = today.replace(day=1) - timedelta(days=1)  # Último dia do mês anterior
            for _ in range(5):  # Voltar mais 5 meses (total 6)
                six_months_ago = six_months_ago.replace(day=1) - timedelta(days=1)

            six_months_ago_str = six_months_ago.strftime('%Y-%m-%d')

            # Obter receitas e despesas médias por mês dos últimos 6 meses
            monthly_stats = self.parent().db_connection.execute(
                '''
                SELECT
                    strftime('%Y-%m', date) as month,
                    SUM(CASE WHEN transaction_type = 'entrada' THEN amount ELSE 0 END) as income,
                    SUM(CASE WHEN transaction_type = 'saida' THEN amount ELSE 0 END) as expense
                FROM transactions
                WHERE user_id = ? AND date >= ?
                GROUP BY month
                ORDER BY month
                ''',
                (self.parent().user_id, six_months_ago_str)
            ).fetchall()

            # Se não houver dados suficientes, usar valores padrão
            if not monthly_stats:
                QMessageBox.warning(
                    self,
                    "Dados Insuficientes",
                    "Não há dados suficientes para uma projeção precisa. "
                    "Será mostrada uma estimativa baseada em valores fictícios."
                )
                avg_income = 1000
                avg_expense = 800
            else:
                # Calcular médias
                total_income = sum(month['income'] for month in monthly_stats)
                total_expense = sum(month['expense'] for month in monthly_stats)
                num_months = len(monthly_stats)

                avg_income = total_income / num_months
                avg_expense = total_expense / num_months

            # Obter saldo atual
            transactions = self.parent().db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?',
                (self.parent().user_id,)
            ).fetchall()

            entries_total = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
            exits_total = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
            current_balance = entries_total - exits_total

            # Gerar projeção
            months = []
            incomes = []
            expenses = []
            balances = []

            running_balance = current_balance

            for i in range(months_to_project):
                # Calcular mês e ano
                month_num = (current_month + i) % 12
                if month_num == 0:
                    month_num = 12
                year_num = current_year + (current_month + i - 1) // 12

                month_name = QDate(year_num, month_num, 1).toString("MMM yyyy")
                months.append(month_name)

                # Adicionar variação aleatória às médias (entre -5% e +5%)
                variation = 0.1  # 10% de variação máxima
                income_variation = 1 + (random.random() * variation - variation / 2)
                expense_variation = 1 + (random.random() * variation - variation / 2)

                month_income = avg_income * income_variation
                month_expense = avg_expense * expense_variation

                # Adicionar valores previstos
                incomes.append(month_income)
                expenses.append(month_expense)

                # Calcular saldo do mês
                month_balance = month_income - month_expense
                running_balance += month_balance
                balances.append(running_balance)

            # Atualizar tabela
            self.projection_table.setRowCount(months_to_project)

            for i in range(months_to_project):
                # Coluna do mês
                self.projection_table.setItem(i, 0, QTableWidgetItem(months[i]))

                # Coluna de receitas
                income_item = QTableWidgetItem(f"R$ {incomes[i]:.2f}")
                income_item.setForeground(QColor(0, 128, 0))  # Verde
                self.projection_table.setItem(i, 1, income_item)

                # Coluna de despesas
                expense_item = QTableWidgetItem(f"R$ {expenses[i]:.2f}")
                expense_item.setForeground(QColor(200, 0, 0))  # Vermelho
                self.projection_table.setItem(i, 2, expense_item)

                # Coluna de saldo
                balance = balances[i]
                balance_item = QTableWidgetItem(f"R$ {balance:.2f}")
                if balance >= 0:
                    balance_item.setForeground(QColor(0, 128, 0))  # Verde
                else:
                    balance_item.setForeground(QColor(200, 0, 0))  # Vermelho
                self.projection_table.setItem(i, 3, balance_item)

            self.projection_table.resizeColumnsToContents()

            # Gerar resumo
            final_balance = balances[-1]
            total_projected_income = sum(incomes)
            total_projected_expense = sum(expenses)
            monthly_avg_balance = sum(income - expense for income, expense in zip(incomes, expenses)) / months_to_project

            summary_html = "<b>Resumo da Projeção:</b><br>"
            summary_html += f"Saldo atual: <b>R$ {current_balance:.2f}</b><br>"
            summary_html += f"Saldo projetado em {months_to_project} meses: <b>R$ {final_balance:.2f}</b><br>"
            summary_html += f"Total de receitas projetadas: <b style='color:green;'>R$ {total_projected_income:.2f}</b><br>"
            summary_html += f"Total de despesas projetadas: <b style='color:red;'>R$ {total_projected_expense:.2f}</b><br>"

            if monthly_avg_balance >= 0:
                summary_html += f"Saldo médio mensal: <b style='color:green;'>R$ {monthly_avg_balance:.2f}</b>"
            else:
                summary_html += f"Saldo médio mensal: <b style='color:red;'>R$ {monthly_avg_balance:.2f}</b>"

            self.summary_text.setHtml(summary_html)

            # Criar gráfico
            self.figure.clear()
            ax = self.figure.add_subplot(111)

            # Configuração das barras
            bar_width = 0.35
            x = np.arange(len(months))

            # Criar barras
            income_bars = ax.bar(x - bar_width/2, incomes, bar_width, label='Receitas', color='green', alpha=0.7)
            expense_bars = ax.bar(x + bar_width/2, expenses, bar_width, label='Despesas', color='red', alpha=0.7)

            # Adicionar linha de saldo
            ax.plot(x, balances, 'b-', marker='o', label='Saldo Acumulado')

            # Adicionar linha do zero
            ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)

            # Rótulos e legenda
            ax.set_xlabel('Mês')
            ax.set_ylabel('Valores (R$)')
            ax.set_title('Projeção de Fluxo de Caixa')
            ax.set_xticks(x)
            ax.set_xticklabels(months, rotation=45, ha='right')

            # Adicionar valores nas barras
            for bar in income_bars:
                height = bar.get_height()
                ax.annotate(f'R${height:.0f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  # 3 pontos de deslocamento vertical
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=8)

            for bar in expense_bars:
                height = bar.get_height()
                ax.annotate(f'R${height:.0f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  # 3 pontos de deslocamento vertical
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=8)

            ax.legend()
            self.figure.tight_layout()

            # Atualizar o canvas
            self.canvas.draw()

        except Exception as e:
            import traceback
            print(f"Erro ao gerar projeção: {e}")
            print(traceback.format_exc())
            QMessageBox.warning(self, "Erro", f"Não foi possível gerar a projeção: {str(e)}")


class TrendsDialog(QDialog):
    """Diálogo para visualizar tendências de gastos ao longo do tempo"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tendências de Gastos")
        self.resize(900, 600)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.period_label = QLabel("Período de Análise:")
        self.period_combo = QComboBox()
        self.period_combo.addItems(["Últimos 6 meses", "Último ano", "Últimos 2 anos", "Todo o histórico"])
        self.period_combo.setCurrentIndex(0)

        self.trend_type_label = QLabel("Tipo de Análise:")
        self.trend_type_combo = QComboBox()
        self.trend_type_combo.addItems([
            "Gastos por Mês",
            "Gastos por Categoria",
            "Evolução do Saldo",
            "Top Categorias por Mês"
        ])

        # Botão para gerar análise
        self.generate_button = QPushButton("Gerar Análise")
        self.generate_button.clicked.connect(self.generate_trends)

        # Área para o gráfico
        self.figure = plt.figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)

        # Texto de análise
        self.analysis_label = QLabel("Análise de Tendências:")
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)

        # Botão para fechar
        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        # Layout
        layout = QVBoxLayout()

        # Layout para controles
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.period_label)
        controls_layout.addWidget(self.period_combo)
        controls_layout.addWidget(self.trend_type_label)
        controls_layout.addWidget(self.trend_type_combo)
        controls_layout.addWidget(self.generate_button)

        layout.addLayout(controls_layout)

        # Layout dividido para gráfico e análise
        split_layout = QVBoxLayout()
        split_layout.addWidget(self.canvas, 7)  # 70% para o gráfico

        analysis_layout = QVBoxLayout()
        analysis_layout.addWidget(self.analysis_label)
        analysis_layout.addWidget(self.analysis_text)

        split_layout.addLayout(analysis_layout, 3)  # 30% para a análise

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)

        # Gerar análise inicial
        self.generate_trends()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QComboBox {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.close_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
            self.generate_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")

            # Configurar cores para o gráfico
            plt.style.use('dark_background')
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QComboBox {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.close_button.setStyleSheet("background-color: #f44336; color: white;")
            self.generate_button.setStyleSheet("background-color: #4CAF50; color: white;")

            # Configurar cores para o gráfico
            plt.style.use('default')

    def get_period_date(self):
        """Retorna a data de início do período selecionado"""
        today = datetime.now()
        period_index = self.period_combo.currentIndex()

        if period_index == 0:  # Últimos 6 meses
            start_date = today - timedelta(days=180)
        elif period_index == 1:  # Último ano
            start_date = today - timedelta(days=365)
        elif period_index == 2:  # Últimos 2 anos
            start_date = today - timedelta(days=730)
        else:  # Todo o histórico
            return None

        return start_date.strftime('%Y-%m-%d')

    def generate_trends(self):
        """Gera a análise de tendências de gastos"""
        try:
            # Obter período selecionado
            start_date = self.get_period_date()

            # Tipo de análise selecionada
            trend_type = self.trend_type_combo.currentIndex()

            if trend_type == 0:  # Gastos por Mês
                self.analyze_monthly_expenses(start_date)
            elif trend_type == 1:  # Gastos por Categoria
                self.analyze_category_expenses(start_date)
            elif trend_type == 2:  # Evolução do Saldo
                self.analyze_balance_evolution(start_date)
            elif trend_type == 3:  # Top Categorias por Mês
                self.analyze_top_categories_by_month(start_date)

        except Exception as e:
            import traceback
            print(f"Erro ao gerar análise de tendências: {e}")
            print(traceback.format_exc())
            QMessageBox.warning(self, "Erro", f"Não foi possível gerar a análise: {str(e)}")

    def analyze_monthly_expenses(self, start_date):
        """Analisa gastos mensais ao longo do tempo"""
        # Construir a consulta SQL
        query = '''
            SELECT
                strftime('%Y-%m', date) as month,
                SUM(CASE WHEN transaction_type = 'entrada' THEN amount ELSE 0 END) as income,
                SUM(CASE WHEN transaction_type = 'saida' THEN amount ELSE 0 END) as expense
            FROM transactions
            WHERE user_id = ?
        '''

        params = [self.parent().user_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        query += " GROUP BY month ORDER BY month"

        # Executar consulta
        monthly_data = self.parent().db_connection.execute(query, params).fetchall()

        if not monthly_data:
            self.analysis_text.setHtml("<i>Não há dados suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Preparar dados para o gráfico
        months = [datetime.strptime(m['month'], '%Y-%m').strftime('%b %Y') for m in monthly_data]
        incomes = [m['income'] for m in monthly_data]
        expenses = [m['expense'] for m in monthly_data]
        balances = [inc - exp for inc, exp in zip(incomes, expenses)]

        # Criar gráfico
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Configuração das barras
        bar_width = 0.35
        x = np.arange(len(months))

        # Criar barras
        income_bars = ax.bar(x - bar_width/2, incomes, bar_width, label='Receitas', color='green', alpha=0.7)
        expense_bars = ax.bar(x + bar_width/2, expenses, bar_width, label='Despesas', color='red', alpha=0.7)

        # Adicionar linha de saldo
        ax.plot(x, balances, 'b-', marker='o', label='Saldo Mensal')

        # Adicionar linha do zero
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)

        # Rótulos e legenda
        ax.set_xlabel('Mês')
        ax.set_ylabel('Valores (R$)')
        ax.set_title('Evolução de Receitas e Despesas')
        ax.set_xticks(x)
        ax.set_xticklabels(months, rotation=45, ha='right')

        ax.legend()
        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        avg_income = sum(incomes) / len(incomes)
        avg_expense = sum(expenses) / len(expenses)
        avg_balance = sum(balances) / len(balances)

        # Calcular tendências
        if len(incomes) >= 3:
            income_trend = self.calculate_trend(incomes)
            expense_trend = self.calculate_trend(expenses)
            balance_trend = self.calculate_trend(balances)
        else:
            income_trend = expense_trend = balance_trend = 0

        # Mês com maior receita, despesa e saldo
        max_income_month = months[incomes.index(max(incomes))]
        max_expense_month = months[expenses.index(max(expenses))]
        max_balance_month = months[balances.index(max(balances))]
        min_balance_month = months[balances.index(min(balances))]

        # Texto da análise
        analysis_html = "<h3>Análise de Receitas e Despesas Mensais</h3>"

        analysis_html += "<p><b>Valores médios:</b><br>"
        analysis_html += f"Receita média mensal: <span style='color:green;'>R$ {avg_income:.2f}</span><br>"
        analysis_html += f"Despesa média mensal: <span style='color:red;'>R$ {avg_expense:.2f}</span><br>"

        if avg_balance >= 0:
            analysis_html += f"Saldo médio mensal: <span style='color:green;'>R$ {avg_balance:.2f}</span></p>"
        else:
            analysis_html += f"Saldo médio mensal: <span style='color:red;'>R$ {avg_balance:.2f}</span></p>"

        analysis_html += "<p><b>Destaques:</b><br>"
        analysis_html += f"Mês com maior receita: {max_income_month} (R$ {max(incomes):.2f})<br>"
        analysis_html += f"Mês com maior despesa: {max_expense_month} (R$ {max(expenses):.2f})<br>"
        analysis_html += f"Mês com melhor saldo: {max_balance_month} (R$ {max(balances):.2f})<br>"
        analysis_html += f"Mês com pior saldo: {min_balance_month} (R$ {min(balances):.2f})</p>"

        analysis_html += "<p><b>Tendências:</b><br>"

        if income_trend > 0:
            analysis_html += f"Suas receitas estão <span style='color:green;'>aumentando</span> ao longo do tempo.<br>"
        elif income_trend < 0:
            analysis_html += f"Suas receitas estão <span style='color:red;'>diminuindo</span> ao longo do tempo.<br>"
        else:
            analysis_html += f"Suas receitas estão <span style='color:blue;'>estáveis</span> ao longo do tempo.<br>"

        if expense_trend > 0:
            analysis_html += f"Suas despesas estão <span style='color:red;'>aumentando</span> ao longo do tempo.<br>"
        elif expense_trend < 0:
            analysis_html += f"Suas despesas estão <span style='color:green;'>diminuindo</span> ao longo do tempo.<br>"
        else:
            analysis_html += f"Suas despesas estão <span style='color:blue;'>estáveis</span> ao longo do tempo.<br>"

        if balance_trend > 0:
            analysis_html += f"Seu saldo mensal está <span style='color:green;'>melhorando</span> ao longo do tempo.</p>"
        elif balance_trend < 0:
            analysis_html += f"Seu saldo mensal está <span style='color:red;'>piorando</span> ao longo do tempo.</p>"
        else:
            analysis_html += f"Seu saldo mensal está <span style='color:blue;'>estável</span> ao longo do tempo.</p>"

        self.analysis_text.setHtml(analysis_html)

    def analyze_category_expenses(self, start_date):
        """Analisa gastos por categoria ao longo do tempo"""
        # Construir a consulta SQL para obter categorias
        category_query = '''
            SELECT id, name FROM categories
            WHERE user_id = ?
            ORDER BY name
        '''

        categories = self.parent().db_connection.execute(category_query, [self.parent().user_id]).fetchall()

        if not categories:
            self.analysis_text.setHtml("<i>Não há categorias definidas para análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Construir a consulta SQL para obter gastos por categoria e mês
        expense_query = '''
            SELECT
                strftime('%Y-%m', date) as month,
                category_id,
                SUM(amount) as total
            FROM transactions
            WHERE user_id = ? AND transaction_type = 'saida'
        '''

        params = [self.parent().user_id]

        if start_date:
            expense_query += " AND date >= ?"
            params.append(start_date)

        expense_query += " GROUP BY month, category_id ORDER BY month, category_id"

        # Executar consulta
        expenses_data = self.parent().db_connection.execute(expense_query, params).fetchall()

        if not expenses_data:
            self.analysis_text.setHtml("<i>Não há dados de despesas suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Organizar dados por mês e categoria
        months = sorted(set(e['month'] for e in expenses_data))
        formatted_months = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months]

        # Criar um dicionário para armazenar gastos por categoria e mês
        category_expenses = {cat['id']: [0] * len(months) for cat in categories}
        category_names = {cat['id']: cat['name'] for cat in categories}

        # Preencher os dados
        for expense in expenses_data:
            if expense['category_id'] in category_expenses:
                month_index = months.index(expense['month'])
                category_expenses[expense['category_id']][month_index] = expense['total']

        # Filtrar apenas as top 5 categorias por gasto total
        category_totals = {cat_id: sum(expenses) for cat_id, expenses in category_expenses.items()}
        top_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]

        # Criar gráfico
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Cores para as categorias
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

        # Criar linhas para cada categoria
        for i, (cat_id, _) in enumerate(top_categories):
            cat_name = category_names[cat_id]
            cat_data = category_expenses[cat_id]
            ax.plot(range(len(months)), cat_data, marker='o', linewidth=2, label=cat_name, color=colors[i % len(colors)])

        # Rótulos e legenda
        ax.set_xlabel('Mês')
        ax.set_ylabel('Despesas (R$)')
        ax.set_title('Evolução de Despesas por Categoria')
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(formatted_months, rotation=45, ha='right')

        ax.legend()
        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        analysis_html = "<h3>Análise de Despesas por Categoria</h3>"

        # Resumo das categorias principais
        analysis_html += "<p><b>Top 5 categorias com maior despesa:</b></p>"
        analysis_html += "<ol>"

        for cat_id, total in top_categories:
            cat_name = category_names[cat_id]
            cat_data = category_expenses[cat_id]

            # Calcular tendência
            if len(cat_data) >= 3:
                cat_trend = self.calculate_trend(cat_data)

                if cat_trend > 0:
                    trend_text = "<span style='color:red;'>aumentando</span>"
                elif cat_trend < 0:
                    trend_text = "<span style='color:green;'>diminuindo</span>"
                else:
                    trend_text = "<span style='color:blue;'>estável</span>"
            else:
                trend_text = "insuficiente para análise de tendência"

            # Calcular média mensal
            cat_avg = sum(cat_data) / len(cat_data)

            analysis_html += f"<li><b>{cat_name}</b>: Total de R$ {total:.2f}, média mensal de R$ {cat_avg:.2f}<br>"
            analysis_html += f"Tendência: {trend_text}</li>"

        analysis_html += "</ol>"

        # Recomendações
        analysis_html += "<p><b>Recomendações:</b></p><ul>"

        # Analisar categorias com tendência de aumento
        increasing_cats = []
        for cat_id, total in top_categories:
            cat_data = category_expenses[cat_id]
            if len(cat_data) >= 3 and self.calculate_trend(cat_data) > 0:
                increasing_cats.append(category_names[cat_id])

        if increasing_cats:
            analysis_html += f"<li>Considere reduzir gastos nas categorias com tendência de aumento: {', '.join(increasing_cats)}</li>"

        # Identificar categorias de maior impacto
        if top_categories:
            top_cat_id, _ = top_categories[0]
            top_cat_name = category_names[top_cat_id]
            analysis_html += f"<li>Sua maior categoria de despesa é <b>{top_cat_name}</b>. Foque em reduzir estes gastos para maior impacto no seu orçamento.</li>"

        analysis_html += "</ul>"

        self.analysis_text.setHtml(analysis_html)

    def analyze_balance_evolution(self, start_date):
        """Analisa a evolução do saldo ao longo do tempo"""
        # Construir a consulta SQL
        query = '''
            SELECT
                date,
                transaction_type,
                amount
            FROM transactions
            WHERE user_id = ?
        '''

        params = [self.parent().user_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        query += " ORDER BY date"

        # Executar consulta
        transactions = self.parent().db_connection.execute(query, params).fetchall()

        if not transactions:
            self.analysis_text.setHtml("<i>Não há dados suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Calcular saldo acumulado ao longo do tempo
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

        # Criar gráfico
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Criar linha do saldo
        ax.plot(dates, balances, 'b-', linewidth=2)

        # Adicionar área preenchida
        ax.fill_between(dates, balances, 0, where=[b >= 0 for b in balances], color='green', alpha=0.3)
        ax.fill_between(dates, balances, 0, where=[b < 0 for b in balances], color='red', alpha=0.3)

        # Adicionar linha do zero
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)

        # Rótulos e formatação
        ax.set_xlabel('Data')
        ax.set_ylabel('Saldo (R$)')
        ax.set_title('Evolução do Saldo ao Longo do Tempo')

        # Formatar eixo X para mostrar datas
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.xticks(rotation=45, ha='right')

        # Adicionar grade
        ax.grid(True, linestyle='--', alpha=0.7)

        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        analysis_html = "<h3>Análise da Evolução do Saldo</h3>"

        # Dados iniciais e finais
        initial_date = dates[0].strftime('%d/%m/%Y')
        final_date = dates[-1].strftime('%d/%m/%Y')
        initial_balance = balances[0]
        final_balance = balances[-1]

        # Calcular variação
        total_variation = final_balance - initial_balance
        percentage_variation = (total_variation / abs(initial_balance) * 100) if initial_balance != 0 else 0

        # Calcular tendência
        if len(balances) >= 10:
            # Usar os últimos 10 pontos para calcular a tendência recente
            recent_trend = self.calculate_trend(balances[-10:])
        else:
            recent_trend = self.calculate_trend(balances)

        # Identificar pontos de maior e menor saldo
        max_balance = max(balances)
        min_balance = min(balances)
        max_date = dates[balances.index(max_balance)].strftime('%d/%m/%Y')
        min_date = dates[balances.index(min_balance)].strftime('%d/%m/%Y')

        # Resumo geral
        analysis_html += "<p><b>Resumo:</b><br>"
        analysis_html += f"Período de análise: de {initial_date} a {final_date}<br>"

        if initial_balance >= 0:
            analysis_html += f"Saldo inicial: <span style='color:green;'>R$ {initial_balance:.2f}</span><br>"
        else:
            analysis_html += f"Saldo inicial: <span style='color:red;'>R$ {initial_balance:.2f}</span><br>"

        if final_balance >= 0:
            analysis_html += f"Saldo atual: <span style='color:green;'>R$ {final_balance:.2f}</span><br>"
        else:
            analysis_html += f"Saldo atual: <span style='color:red;'>R$ {final_balance:.2f}</span><br>"

        if total_variation >= 0:
            analysis_html += f"Variação total: <span style='color:green;'>+R$ {total_variation:.2f}</span> "
            analysis_html += f"(<span style='color:green;'>+{percentage_variation:.1f}%</span>)</p>"
        else:
            analysis_html += f"Variação total: <span style='color:red;'>-R$ {abs(total_variation):.2f}</span> "
            analysis_html += f"(<span style='color:red;'>{percentage_variation:.1f}%</span>)</p>"

                # Destaques
        analysis_html += "<p><b>Destaques:</b><br>"
        analysis_html += f"Maior saldo registrado: <span style='color:green;'>R$ {max_balance:.2f}</span> em {max_date}<br>"
        analysis_html += f"Menor saldo registrado: <span style='color:red;'>R$ {min_balance:.2f}</span> em {min_date}</p>"

        # Tendência
        analysis_html += "<p><b>Tendência atual:</b><br>"

        if recent_trend > 0:
            analysis_html += f"Seu saldo está com tendência de <span style='color:green;'>crescimento</span>.<br>"
            analysis_html += "Continue com o bom trabalho mantendo suas receitas acima das despesas!"
        elif recent_trend < 0:
            analysis_html += f"Seu saldo está com tendência de <span style='color:red;'>queda</span>.<br>"
            analysis_html += "Considere reduzir despesas ou aumentar receitas para reverter esta tendência."
        else:
            analysis_html += f"Seu saldo está <span style='color:blue;'>estável</span>.<br>"
            analysis_html += "Você está conseguindo manter um equilíbrio entre receitas e despesas."

        analysis_html += "</p>"

        # Períodos negativos
        negative_periods = []
        current_negative_start = None

        for i, balance in enumerate(balances):
            if balance < 0 and (i == 0 or balances[i-1] >= 0):
                current_negative_start = dates[i]
            elif balance >= 0 and i > 0 and balances[i-1] < 0 and current_negative_start:
                negative_periods.append((current_negative_start, dates[i-1]))
                current_negative_start = None

        # Se terminar em período negativo
        if balances[-1] < 0 and current_negative_start:
            negative_periods.append((current_negative_start, dates[-1]))

        if negative_periods:
            analysis_html += "<p><b>Períodos com saldo negativo:</b><ul>"

            for start, end in negative_periods:
                start_str = start.strftime('%d/%m/%Y')
                end_str = end.strftime('%d/%m/%Y')
                analysis_html += f"<li>De {start_str} a {end_str}</li>"

            analysis_html += "</ul></p>"

        self.analysis_text.setHtml(analysis_html)

    def analyze_top_categories_by_month(self, start_date):
        """Analisa as principais categorias de despesa por mês"""
        # Construir a consulta SQL
        query = '''
            SELECT
                strftime('%Y-%m', t.date) as month,
                c.name as category_name,
                SUM(t.amount) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND t.transaction_type = 'saida'
        '''

        params = [self.parent().user_id]

        if start_date:
            query += " AND t.date >= ?"
            params.append(start_date)

        query += " GROUP BY month, category_name ORDER BY month, total DESC"

        # Executar consulta
        expenses_data = self.parent().db_connection.execute(query, params).fetchall()

        if not expenses_data:
            self.analysis_text.setHtml("<i>Não há dados suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Organizar dados por mês
        months = sorted(set(e['month'] for e in expenses_data))
        formatted_months = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months]

        # Para cada mês, obter as top 5 categorias
        month_categories = {}

        for month in months:
            month_data = [e for e in expenses_data if e['month'] == month]
            # Ordenar por total e pegar as top 5
            top_categories = sorted(month_data, key=lambda x: x['total'], reverse=True)[:5]
            month_categories[month] = top_categories

        # Criar gráfico
        self.figure.clear()

        # Definir o número de linhas e colunas para os subplots
        n_months = len(months)
        if n_months <= 3:
            rows, cols = 1, n_months
        elif n_months <= 6:
            rows, cols = 2, 3
        else:
            rows, cols = (n_months + 3) // 4, 4

        # Cores para as categorias
        colors = plt.cm.tab10.colors

        # Criar um subplot para cada mês
        for i, month in enumerate(months):
            ax = self.figure.add_subplot(rows, cols, i+1)

            # Dados para o mês
            categories = [c['category_name'] for c in month_categories[month]]
            values = [c['total'] for c in month_categories[month]]

            # Criar gráfico de pizza
            wedges, texts, autotexts = ax.pie(
                values,
                autopct='%1.1f%%',
                textprops={'fontsize': 8},
                colors=colors[:len(categories)]
            )

            # Ajustar textos
            for autotext in autotexts:
                autotext.set_fontsize(6)

            ax.set_title(formatted_months[i], fontsize=10)

            # Legenda separada para cada gráfico
            if categories:
                ax.legend(
                    wedges, categories,
                    loc="center left",
                    bbox_to_anchor=(1, 0, 0.5, 1),
                    fontsize=6
                )

        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        analysis_html = "<h3>Análise das Principais Categorias de Despesa por Mês</h3>"

        # Resumo por mês
        analysis_html += "<p><b>Resumo das principais categorias de despesa:</b></p>"

        for i, month in enumerate(months):
            formatted_month = formatted_months[i]
            analysis_html += f"<p><b>{formatted_month}</b>:<br>"

            # Total do mês
            month_total = sum(c['total'] for c in month_categories[month])
            analysis_html += f"Total de despesas: R$ {month_total:.2f}<br>"

            # Listar principais categorias
            for j, category in enumerate(month_categories[month]):
                percentage = (category['total'] / month_total * 100)
                analysis_html += f"{j+1}. {category['category_name']}: R$ {category['total']:.2f} ({percentage:.1f}%)<br>"

            analysis_html += "</p>"

        # Análise de padrões
        analysis_html += "<p><b>Análise de Padrões:</b></p>"

        # Identificar categorias que aparecem consistentemente nos tops
        all_categories = set()
        for month_data in month_categories.values():
            for category in month_data:
                all_categories.add(category['category_name'])

        consistent_categories = []
        for category in all_categories:
            appearances = sum(1 for month_data in month_categories.values()
                             if any(c['category_name'] == category for c in month_data))

            # Se aparece em pelo menos 75% dos meses
            if appearances >= len(months) * 0.75:
                consistent_categories.append(category)

        if consistent_categories:
            analysis_html += "<p>Categorias que aparecem consistentemente entre as principais despesas:<ul>"
            for category in consistent_categories:
                analysis_html += f"<li>{category}</li>"
            analysis_html += "</ul></p>"

        # Categorias que tiveram mudanças significativas
        if len(months) >= 2:
            analysis_html += "<p>Mudanças significativas entre meses:</p><ul>"

            significant_changes = False

            for category in all_categories:
                monthly_values = []

                for month in months:
                    category_data = next((c for c in month_categories[month] if c['category_name'] == category), None)
                    if category_data:
                        monthly_values.append(category_data['total'])
                    else:
                        monthly_values.append(0)

                # Se tiver pelo menos 2 valores para comparar
                if len(monthly_values) >= 2 and sum(monthly_values) > 0:
                    max_value = max(monthly_values)
                    min_value = min(v for v in monthly_values if v > 0) if any(v > 0 for v in monthly_values) else 0

                    # Se a diferença for significativa (mais de 50%)
                    if min_value > 0 and max_value / min_value >= 1.5:
                        max_month = formatted_months[monthly_values.index(max_value)]
                        min_month = formatted_months[monthly_values.index(min_value)]

                        analysis_html += f"<li><b>{category}</b>: Variou de R$ {min_value:.2f} em {min_month} "
                        analysis_html += f"para R$ {max_value:.2f} em {max_month} "
                        analysis_html += f"(aumento de {(max_value/min_value - 1)*100:.1f}%)</li>"

                        significant_changes = True

            if not significant_changes:
                analysis_html += "<li>Não foram identificadas mudanças significativas entre os meses analisados.</li>"

            analysis_html += "</ul>"

        self.analysis_text.setHtml(analysis_html)

    def calculate_trend(self, values):
        """
        Calcula a tendência de uma série de valores
        Retorna um valor positivo se a tendência for de aumento, negativo se for de queda, ou zero se for estável
        """
        if len(values) < 2:
            return 0

        # Calcular coeficiente de inclinação da reta de tendência
        x = np.arange(len(values))
        y = np.array(values)

        # Remover valores NaN
        valid = ~np.isnan(y)
        if not np.any(valid) or np.sum(valid) < 2:
            return 0

        x = x[valid]
        y = y[valid]

        try:
            slope, _ = np.polyfit(x, y, 1)

            # Normalizar a inclinação em relação à média dos valores
            avg = np.mean(y)
            if avg != 0:
                normalized_slope = slope / abs(avg)
            else:
                normalized_slope = slope

            # Classificar a tendência
            if abs(normalized_slope) < 0.05:  # Se a variação for menor que 5% da média, considerar estável
                return 0
            else:
                return normalized_slope
        except:
            return 0

class ApiConfigDialog(QDialog):
    """Diálogo para configurar a conexão com a API de IA"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração da API de IA")
        self.setMinimumWidth(500)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.endpoint_type_label = QLabel("Tipo de conexão:")
        self.endpoint_type_combo = QComboBox()
        self.endpoint_type_combo.addItems(["API HTTP", "Rede Tor (Onion)"])
        self.endpoint_type_combo.currentIndexChanged.connect(self.toggle_endpoint_type)

        self.host_label = QLabel("Endereço do servidor:")
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("localhost ou endereço IP ou URL")

        self.port_label = QLabel("Porta:")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("ex: 11434")

        self.onion_label = QLabel("Endereço Onion:")
        self.onion_input = QLineEdit()
        self.onion_input.setPlaceholderText("endereço.onion")
        self.onion_input.setEnabled(False)

        self.onion_port_label = QLabel("Porta Onion:")
        self.onion_port_input = QLineEdit()
        self.onion_port_input.setPlaceholderText("ex: 11434")
        self.onion_port_input.setEnabled(False)

        self.api_key_label = QLabel("API Key (opcional):")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Deixe em branco se não for necessário")

        self.test_button = QPushButton("Testar Conexão")
        self.test_button.clicked.connect(self.test_connection)

        self.model_list_label = QLabel("Modelos disponíveis:")
        self.model_list = QListWidget()
        self.model_list.setSelectionMode(QListWidget.SingleSelection)

        self.selected_model_label = QLabel("Modelo selecionado:")
        self.selected_model_input = QLineEdit()
        self.selected_model_input.setReadOnly(True)

        self.save_button = QPushButton("Salvar Configurações")
        self.save_button.clicked.connect(self.save_config)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.addRow(self.endpoint_type_label, self.endpoint_type_combo)
        form_layout.addRow(self.host_label, self.host_input)
        form_layout.addRow(self.port_label, self.port_input)
        form_layout.addRow(self.onion_label, self.onion_input)
        form_layout.addRow(self.onion_port_label, self.onion_port_input)
        form_layout.addRow(self.api_key_label, self.api_key_input)

        layout.addLayout(form_layout)
        layout.addWidget(self.test_button)

        layout.addWidget(QLabel(""))  # Espaçador
        layout.addWidget(self.model_list_label)
        layout.addWidget(self.model_list)
        layout.addWidget(self.selected_model_label)
        layout.addWidget(self.selected_model_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Carregar configurações existentes
        self.load_config()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QListWidget {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
            self.test_button.setStyleSheet("background-color: #f39c12; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QListWidget {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
            self.test_button.setStyleSheet("background-color: #FF9800; color: white;")

    def toggle_endpoint_type(self, index):
        """Alterna entre conexão HTTP e Tor"""
        if index == 0:  # HTTP
            self.host_input.setEnabled(True)
            self.port_input.setEnabled(True)
            self.onion_input.setEnabled(False)
            self.onion_port_input.setEnabled(False)
        else:  # Tor
            self.host_input.setEnabled(False)
            self.port_input.setEnabled(False)
            self.onion_input.setEnabled(True)
            self.onion_port_input.setEnabled(True)

    def load_config(self):
        """Carrega as configurações da API salvas"""
        # Verificar se já existe configuração salva no banco de dados
        if hasattr(self.parent(), 'db_connection') and hasattr(self.parent(), 'user_id'):
            try:
                # Carregar configuração de endpoint
                endpoint_config = self.parent().db_connection.execute(
                    "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = 'ai_endpoint_config'",
                    (self.parent().user_id,)
                ).fetchone()

                if endpoint_config:
                    config = json.loads(endpoint_config[0])

                    # Preencher os campos
                    if config.get('type') == 'tor':
                        self.endpoint_type_combo.setCurrentIndex(1)
                        self.onion_input.setText(config.get('onion', ''))
                        self.onion_port_input.setText(str(config.get('onion_port', '')))
                    else:
                        self.endpoint_type_combo.setCurrentIndex(0)
                        self.host_input.setText(config.get('host', ''))
                        self.port_input.setText(str(config.get('port', '')))

                    self.api_key_input.setText(config.get('api_key', ''))

                # Carregar modelo selecionado
                selected_model = self.parent().db_connection.execute(
                    "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = 'ai_selected_model'",
                    (self.parent().user_id,)
                ).fetchone()

                if selected_model:
                    self.selected_model_input.setText(selected_model[0])
            except:
                pass

    def test_connection(self):
        """Testa a conexão com a API e obtém a lista de modelos disponíveis"""
        try:
            # Limpar lista de modelos
            self.model_list.clear()

            # Obter informações de conexão
            if self.endpoint_type_combo.currentIndex() == 0:  # HTTP
                host = self.host_input.text().strip()
                if not host:
                    QMessageBox.warning(self, "Erro", "Por favor, informe o endereço do servidor.")
                    return

                try:
                    port = int(self.port_input.text().strip())
                except:
                    QMessageBox.warning(self, "Erro", "Por favor, informe uma porta válida.")
                    return

                # Montar URL base
                base_url = f"http://{host}:{port}"
                use_tor = False
            else:  # Tor
                onion = self.onion_input.text().strip()
                if not onion:
                    QMessageBox.warning(self, "Erro", "Por favor, informe o endereço onion.")
                    return

                try:
                    onion_port = int(self.onion_port_input.text().strip())
                except:
                    QMessageBox.warning(self, "Erro", "Por favor, informe uma porta válida para o serviço onion.")
                    return

                # Montar URL base
                base_url = f"http://{onion}:{onion_port}"
                use_tor = True

            api_key = self.api_key_input.text().strip()

            # Mostrar diálogo de progresso
            progress = QProgressDialog("Testando conexão...", "Cancelar", 0, 0, self)
            progress.setWindowTitle("Teste de Conexão")
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            QApplication.processEvents()

            # Testar conexão com Ollama
            try:
                # Configurar conexão Tor se necessário
                session = requests.Session()
                if use_tor:
                    session.proxies = {
                        'http': 'socks5h://localhost:9050',
                        'https': 'socks5h://localhost:9050'
                    }

                # Adicionar API key se fornecida
                headers = {}
                if api_key:
                    headers['Authorization'] = f'Bearer {api_key}'

                # Fazer requisição para listar modelos
                response = session.get(f"{base_url}/api/tags", headers=headers, timeout=10)
                response.raise_for_status()  # Verificar por erros HTTP

                # Processar resposta
                models_data = response.json()

                # Verificar o formato da resposta e extrair os modelos
                if isinstance(models_data, dict) and 'models' in models_data:
                    # Formato Ollama
                    models = [model['name'] for model in models_data['models']]
                elif isinstance(models_data, list):
                    # Formato simples
                    models = [model['name'] if isinstance(model, dict) and 'name' in model else str(model)
                             for model in models_data]
                else:
                    # Formato desconhecido
                    raise ValueError("Formato de resposta não reconhecido")

                # Adicionar modelos à lista
                for model in models:
                    self.model_list.addItem(model)

                # Selecionar o modelo salvo anteriormente, se existir
                if self.selected_model_input.text():
                    matching_items = self.model_list.findItems(
                        self.selected_model_input.text(),
                        Qt.MatchExactly
                    )
                    if matching_items:
                        self.model_list.setCurrentItem(matching_items[0])

                QMessageBox.information(self, "Sucesso", f"Conexão estabelecida com sucesso!\n{len(models)} modelos encontrados.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Não foi possível conectar à API: {str(e)}")
            finally:
                progress.close()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao testar conexão: {str(e)}")

    def save_config(self):
        """Salva as configurações da API"""
        # Verificar se há um modelo selecionado
        selected_items = self.model_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione um modelo de IA.")
            return

        selected_model = selected_items[0].text()
        self.selected_model_input.setText(selected_model)

        # Montar objeto de configuração
        config = {}
        if self.endpoint_type_combo.currentIndex() == 0:  # HTTP
            config['type'] = 'http'
            config['host'] = self.host_input.text().strip()
            try:
                config['port'] = int(self.port_input.text().strip())
            except:
                QMessageBox.warning(self, "Erro", "Por favor, informe uma porta válida.")
                return
        else:  # Tor
            config['type'] = 'tor'
            config['onion'] = self.onion_input.text().strip()
            try:
                config['onion_port'] = int(self.onion_port_input.text().strip())
            except:
                QMessageBox.warning(self, "Erro", "Por favor, informe uma porta válida para o serviço onion.")
                return

        # Adicionar API key se fornecida
        api_key = self.api_key_input.text().strip()
        if api_key:
            config['api_key'] = api_key

        # Salvar no banco de dados
        if hasattr(self.parent(), 'db_connection') and hasattr(self.parent(), 'user_id'):
            try:
                # Salvar configuração de endpoint
                config_json = json.dumps(config)

                # Verificar se já existe configuração
                existing = self.parent().db_connection.execute(
                    "SELECT id FROM user_settings WHERE user_id = ? AND setting_key = 'ai_endpoint_config'",
                    (self.parent().user_id,)
                ).fetchone()

                if existing:
                    # Atualizar configuração existente
                    self.parent().db_connection.execute(
                        "UPDATE user_settings SET setting_value = ? WHERE user_id = ? AND setting_key = 'ai_endpoint_config'",
                        (config_json, self.parent().user_id)
                    )
                else:
                    # Criar nova configuração
                    self.parent().db_connection.execute(
                        "INSERT INTO user_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
                        (self.parent().user_id, 'ai_endpoint_config', config_json)
                    )

                # Salvar modelo selecionado
                existing = self.parent().db_connection.execute(
                    "SELECT id FROM user_settings WHERE user_id = ? AND setting_key = 'ai_selected_model'",
                    (self.parent().user_id,)
                ).fetchone()

                if existing:
                    # Atualizar configuração existente
                    self.parent().db_connection.execute(
                        "UPDATE user_settings SET setting_value = ? WHERE user_id = ? AND setting_key = 'ai_selected_model'",
                        (selected_model, self.parent().user_id)
                    )
                else:
                    # Criar nova configuração
                    self.parent().db_connection.execute(
                        "INSERT INTO user_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
                        (self.parent().user_id, 'ai_selected_model', selected_model)
                    )

                self.parent().db_connection.commit()
                QMessageBox.information(self, "Sucesso", "Configurações salvas com sucesso!")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao salvar configurações: {str(e)}")
        else:
            QMessageBox.warning(self, "Erro", "Não foi possível salvar as configurações.")

class ChatMessage:
    """Classe para representar uma mensagem no chat"""
    def __init__(self, text, is_user=True):
        self.text = text
        self.is_user = is_user
        self.timestamp = datetime.now()

    def formatted_html(self, dark_mode=False):
        """Retorna a mensagem formatada em HTML"""
        timestamp = self.timestamp.strftime("%H:%M:%S")

        if dark_mode:
            user_style = "background-color: #2c3e50; color: #ecf0f1; border-radius: 10px; padding: 10px; margin: 5px 0; margin-left: 20%;"
            ai_style = "background-color: #34495e; color: #ecf0f1; border-radius: 10px; padding: 10px; margin: 5px 0; margin-right: 20%;"
            time_style = "color: #7f8c8d; font-size: 10px; text-align: right; margin-top: 2px;"
        else:
            user_style = "background-color: #e3f2fd; color: #0d47a1; border-radius: 10px; padding: 10px; margin: 5px 0; margin-left: 20%;"
            ai_style = "background-color: #f1f8e9; color: #33691e; border-radius: 10px; padding: 10px; margin: 5px 0; margin-right: 20%;"
            time_style = "color: #757575; font-size: 10px; text-align: right; margin-top: 2px;"

        style = user_style if self.is_user else ai_style
        align = "right" if self.is_user else "left"
        name = "Você" if self.is_user else "Assistente IA"

        html = f"""
        <div style="text-align: {align};">
            <div style="{style}">
                <div><b>{name}</b></div>
                <div style="white-space: pre-wrap;">{self.text}</div>
                <div style="{time_style}">{timestamp}</div>
            </div>
        </div>
        """

        return html

##  Agete de IA Inicio

class AIAssistantThread(QThread):
    """Thread para processar requisições à API de IA em segundo plano"""
    update_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, config, model, prompt, parent=None):
        super().__init__(parent)
        self.config = config
        self.model = model
        self.prompt = prompt
        self.running = True

    def run(self):
        """Executa a consulta à API"""
        try:
            # Obter informações de conexão
            if self.config.get('type') == 'tor':
                base_url = f"http://{self.config.get('onion')}:{self.config.get('onion_port')}"
                use_tor = True
            else:
                base_url = f"http://{self.config.get('host')}:{self.config.get('port')}"
                use_tor = False

            api_key = self.config.get('api_key', '')

            # Configurar conexão
            session = requests.Session()
            if use_tor:
                session.proxies = {
                    'http': 'socks5h://localhost:9050',
                    'https': 'socks5h://localhost:9050'
                }

            # Adicionar API key se fornecida
            headers = {}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            headers['Content-Type'] = 'application/json'

            # Preparar payload
            payload = {
                "model": self.model,
                "prompt": self.prompt,
                "stream": True
            }

            # Fazer requisição para gerar resposta
            response = session.post(
                f"{base_url}/api/generate",
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            response.raise_for_status()

            # Processar resposta em streaming
            full_response = ""
            for line in response.iter_lines():
                if not self.running:
                    break

                if line:
                    try:
                        line_data = json.loads(line.decode('utf-8'))

                        # Verificar o formato da resposta
                        if 'response' in line_data:
                            # Formato Ollama
                            chunk = line_data.get('response', '')
                        elif 'choices' in line_data and len(line_data['choices']) > 0:
                            # Formato OpenAI-like
                            delta = line_data['choices'][0].get('delta', {})
                            chunk = delta.get('content', '')
                        else:
                            # Formato desconhecido, tentar extrair texto
                            chunk = line_data.get('text', '')

                        if chunk:
                            full_response += chunk
                            self.update_signal.emit(full_response)
                    except:
                        continue

            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit()

    def stop(self):
        """Para a thread"""
        self.running = False


class AIAssistantWidget(QWidget):
    """Widget principal do assistente de IA"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        self.messages = []
        self.api_thread = None

        # Carregar configurações
        self.load_config()

        # Inicializar UI
        self.init_ui()

        # Adicionar mensagem de boas-vindas
        welcome_message = "Olá! Sou seu assistente financeiro. Como posso ajudar você hoje?\n\n" + \
                         "Você pode me perguntar sobre:\n" + \
                         "• Análise dos seus gastos\n" + \
                         "• Sugestões para economizar\n" + \
                         "• Categorização de transações\n" + \
                         "• Previsões financeiras\n" + \
                         "• Explicações sobre termos financeiros"
        self.add_message(welcome_message, is_user=False)

    def init_ui(self):
        """Inicializa a interface do usuário"""
        # Layout principal
        layout = QVBoxLayout(self)

        # Área de título
        title_layout = QHBoxLayout()

        title_label = QLabel("Assistente Financeiro IA")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray; font-size: 18px;")

        config_button = QPushButton("⚙️")
        config_button.setToolTip("Configurar API")
        config_button.setFixedSize(30, 30)
        config_button.clicked.connect(self.show_config_dialog)

        title_layout.addWidget(self.status_indicator)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(config_button)

        layout.addLayout(title_layout)

        # Área de chat
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chat_area.setMinimumHeight(300)

        # Área de entrada
        self.input_area = QTextEdit()
        self.input_area.setPlaceholderText("Digite sua pergunta aqui...")
        self.input_area.setMaximumHeight(100)
        self.input_area.setAcceptRichText(False)

        # Botão de envio
        self.send_button = QPushButton("Enviar")
        self.send_button.clicked.connect(self.send_message)

        # Adicionar atalho de teclado para enviar (Ctrl+Enter)
        send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.input_area)
        send_shortcut.activated.connect(self.send_message)

        # Botão para limpar chat
        self.clear_button = QPushButton("Limpar Chat")
        self.clear_button.clicked.connect(self.clear_chat)

        # Layout para botões
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)

        # Adicionar widgets ao layout principal
        layout.addWidget(self.chat_area, 1)
        layout.addWidget(self.input_area, 0)
        layout.addLayout(button_layout)

        # Aplicar tema
        self.apply_theme()

    def apply_theme(self):
        """Aplica o tema claro ou escuro"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QWidget {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QTextEdit {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton {
                    background-color: #3498db;
                    color: #ecf0f1;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.send_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.clear_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QTextEdit {
                    background-color: white;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
            self.send_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.clear_button.setStyleSheet("background-color: #f44336; color: white;")

    def load_config(self):
        """Carrega as configurações da API"""
        self.api_config = None
        self.selected_model = None

        if hasattr(self.parent_window, 'db_connection') and hasattr(self.parent_window, 'user_id'):
            try:
                # Carregar configuração de endpoint
                endpoint_config = self.parent_window.db_connection.execute(
                    "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = 'ai_endpoint_config'",
                    (self.parent_window.user_id,)
                ).fetchone()

                if endpoint_config:
                    self.api_config = json.loads(endpoint_config[0])

                # Carregar modelo selecionado
                selected_model = self.parent_window.db_connection.execute(
                    "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = 'ai_selected_model'",
                    (self.parent_window.user_id,)
                ).fetchone()

                if selected_model:
                    self.selected_model = selected_model[0]

                # Atualizar indicador de status
                self.update_status_indicator()
            except:
                pass

    def update_status_indicator(self):
        """Atualiza o indicador de status"""
        if self.api_config and self.selected_model:
            self.status_indicator.setStyleSheet("color: green; font-size: 18px;")
            self.status_indicator.setToolTip("Conectado")
        else:
            self.status_indicator.setStyleSheet("color: gray; font-size: 18px;")
            self.status_indicator.setToolTip("Não configurado")

    def show_config_dialog(self):
        """Mostra o diálogo de configuração da API"""
        dialog = ApiConfigDialog(self.parent_window)
        if dialog.exec_() == QDialog.Accepted:
            self.load_config()

    def add_message(self, text, is_user=True):
        """Adiciona uma mensagem ao chat"""
        message = ChatMessage(text, is_user)
        self.messages.append(message)

        # Atualizar a visualização
        self.update_chat_view()

    def update_chat_view(self):
        """Atualiza a visualização do chat"""
        # Salvar posição de rolagem
        scrollbar = self.chat_area.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        # Criar HTML para todas as mensagens
        html = ""
        for message in self.messages:
            html += message.formatted_html(self.is_dark_mode)

        # Definir HTML na área de chat
        self.chat_area.setHtml(html)

        # Restaurar posição de rolagem ou ir para o final
        if was_at_bottom:
            QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum()))

    def send_message(self):
        """Envia a mensagem do usuário para a API"""
        text = self.input_area.toPlainText().strip()
        if not text:
            return

        # Verificar se a API está configurada
        if not self.api_config or not self.selected_model:
            QMessageBox.warning(
                self,
                "API não configurada",
                "Por favor, configure a API e selecione um modelo antes de enviar mensagens."
            )
            return

        # Adicionar mensagem do usuário
        self.add_message(text, is_user=True)

        # Limpar campo de entrada
        self.input_area.clear()

        # Adicionar espaço reservado para resposta da IA
        self.add_message("Gerando resposta...", is_user=False)

        # Construir prompt com contexto financeiro
        context = self.build_financial_context()

        # Verificar se a mensagem contém pedidos de análise de períodos específicos
        additional_context = ""

        # Analisar a mensagem para identificar períodos de tempo
        current_year = datetime.now().year
        current_month = datetime.now().month

        # Detectar menções a anos específicos
        mentioned_year = None
        if "ano passado" in text.lower():
            mentioned_year = current_year - 1
        elif "ano retrasado" in text.lower():
            mentioned_year = current_year - 2
        else:
            # Procurar anos explícitos (2020, 2021, 2022, etc.)
            for year in range(current_year-10, current_year+1):
                if str(year) in text:
                    mentioned_year = year
                    break

        # Detectar menções a meses específicos
        mentioned_month = None
        months = {
            'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4, 'maio': 5, 'junho': 6,
            'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
        }

        for month_name, month_num in months.items():
            if month_name.lower() in text.lower():
                mentioned_month = month_num
                break

        if "mês passado" in text.lower():
            mentioned_month = current_month - 1 if current_month > 1 else 12
            if mentioned_month == 12 and mentioned_year is None:
                mentioned_year = current_year - 1

        # Detectar menções a dias específicos
        mentioned_day = None
        # Procurar padrões como "dia 15" ou "15 de janeiro"
        day_patterns = [r'dia (\d{1,2})', r'(\d{1,2}) de']
        for pattern in day_patterns:
            matches = re.findall(pattern, text.lower())
            if matches:
                try:
                    mentioned_day = int(matches[0])
                    if 1 <= mentioned_day <= 31:  # Validar o dia
                        break
                except:
                    pass

        # Detectar intervalo de datas (ex: "de 10 a 20 de janeiro")
        start_day = None
        end_day = None
        date_range_pattern = r'de (\d{1,2}) (?:a|até) (\d{1,2})'
        date_range_matches = re.findall(date_range_pattern, text.lower())
        if date_range_matches:
            try:
                start_day = int(date_range_matches[0][0])
                end_day = int(date_range_matches[0][1])
            except:
                pass

        # Construir as datas com base nas informações coletadas
        try:
            # Definir ano padrão se não foi mencionado
            if mentioned_year is None:
                mentioned_year = current_year

            # Definir mês padrão se não foi mencionado
            if mentioned_month is None:
                mentioned_month = current_month

            # Agora podemos construir consultas específicas com base nos critérios detectados
            if start_day is not None and end_day is not None:
                # Intervalo de dias dentro de um mês
                try:
                    start_date = datetime(mentioned_year, mentioned_month, start_day).strftime('%Y-%m-%d')
                    end_date = datetime(mentioned_year, mentioned_month, end_day).strftime('%Y-%m-%d')
                    period_data = self.analyze_date_range(start_date, end_date)

                    if period_data:
                        month_name = datetime(mentioned_year, mentioned_month, 1).strftime('%B')
                        additional_context += f"\nDados para o período de {start_day} a {end_day} de {month_name} de {mentioned_year}:\n"
                        additional_context += f"Total de receitas: R$ {period_data['summary']['total_income']:.2f}\n"
                        additional_context += f"Total de despesas: R$ {period_data['summary']['total_expense']:.2f}\n"
                        additional_context += f"Saldo do período: R$ {period_data['summary']['net_change']:.2f}\n"

                        if period_data['top_categories']:
                            additional_context += "Principais categorias de despesa:\n"
                            for cat, amount in period_data['top_categories']:
                                additional_context += f"- {cat}: R$ {amount:.2f}\n"
                except:
                    pass

            elif mentioned_day is not None:
                # Dia específico
                try:
                    specific_date = datetime(mentioned_year, mentioned_month, mentioned_day).strftime('%Y-%m-%d')
                    period_data = self.analyze_date_range(specific_date, specific_date)

                    if period_data:
                        month_name = datetime(mentioned_year, mentioned_month, 1).strftime('%B')
                        additional_context += f"\nDados para o dia {mentioned_day} de {month_name} de {mentioned_year}:\n"
                        additional_context += f"Total de receitas: R$ {period_data['summary']['total_income']:.2f}\n"
                        additional_context += f"Total de despesas: R$ {period_data['summary']['total_expense']:.2f}\n"
                        additional_context += f"Saldo do dia: R$ {period_data['summary']['net_change']:.2f}\n"

                        if period_data['transactions']:
                            additional_context += "Transações do dia:\n"
                            for t in period_data['transactions']:
                                additional_context += f"- {t['description']} ({t['transaction_type']}): R$ {t['amount']:.2f}\n"
                except:
                    pass

            elif mentioned_month is not None:
                # Mês específico
                month_data = self.analyze_specific_month(mentioned_month, mentioned_year)
                if month_data:
                    month_name = datetime(mentioned_year, mentioned_month, 1).strftime('%B')
                    additional_context += f"\nDados para {month_name} de {mentioned_year}:\n"
                    additional_context += f"Total de receitas: R$ {month_data['summary']['total_income']:.2f}\n"
                    additional_context += f"Total de despesas: R$ {month_data['summary']['total_expense']:.2f}\n"
                    additional_context += f"Saldo do mês: R$ {month_data['summary']['net_change']:.2f}\n"

                    if month_data['top_categories']:
                        additional_context += "Principais categorias de despesa:\n"
                        for cat, amount in month_data['top_categories']:
                            additional_context += f"- {cat}: R$ {amount:.2f}\n"

            elif mentioned_year is not None:
                # Ano completo
                year_start = f"{mentioned_year}-01-01"
                year_end = f"{mentioned_year}-12-31"
                year_data = self.analyze_date_range(year_start, year_end)

                if year_data:
                    additional_context += f"\nDados para o ano de {mentioned_year}:\n"
                    additional_context += f"Total de receitas: R$ {year_data['summary']['total_income']:.2f}\n"
                    additional_context += f"Total de despesas: R$ {year_data['summary']['total_expense']:.2f}\n"
                    additional_context += f"Saldo do ano: R$ {year_data['summary']['net_change']:.2f}\n"

                    if year_data['top_categories']:
                        additional_context += "Principais categorias de despesa:\n"
                        for cat, amount in year_data['top_categories']:
                            additional_context += f"- {cat}: R$ {amount:.2f}\n"
        except Exception as e:
            print(f"Erro ao analisar período específico: {e}")

        # Adicionar o contexto adicional
        if additional_context:
            context += "\n\nAnálise de dados específicos solicitados pelo usuário:" + additional_context

        full_prompt = f"{context}\n\nUsuário: {text}\n\nAssistente:"

        # Iniciar thread para processar requisição
        if self.api_thread:
            self.api_thread.stop()

        self.api_thread = AIAssistantThread(self.api_config, self.selected_model, full_prompt, self)
        self.api_thread.update_signal.connect(self.update_ai_response)
        self.api_thread.error_signal.connect(self.handle_api_error)
        self.api_thread.finished_signal.connect(self.api_request_finished)

        # Desabilitar botão de envio
        self.send_button.setEnabled(False)

        # Iniciar thread
        self.api_thread.start()

    def update_ai_response(self, text):
        """Atualiza a resposta da IA em tempo real"""
        # Atualizar a última mensagem (que é da IA)
        self.messages[-1].text = text

        # Atualizar a visualização
        self.update_chat_view()

        # Rolar para o final
        scrollbar = self.chat_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def handle_api_error(self, error_message):
        """Trata erros da API"""
        # Atualizar a última mensagem (que é da IA) com o erro
        self.messages[-1].text = f"Erro ao gerar resposta: {error_message}"

        # Atualizar a visualização
        self.update_chat_view()

    def api_request_finished(self):
        """Chamado quando a requisição à API é finalizada"""
        # Reativar botão de envio
        self.send_button.setEnabled(True)

    def clear_chat(self):
        """Limpa o histórico de chat"""
        reply = QMessageBox.question(
            self,
            "Limpar Chat",
            "Tem certeza que deseja limpar todo o histórico de chat?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Manter apenas a mensagem de boas-vindas
            welcome_message = self.messages[0] if self.messages else None

            self.messages = []

            if welcome_message:
                self.messages.append(welcome_message)

            # Atualizar a visualização
            self.update_chat_view()

    def get_transactions_by_period(self, period_type, start_date=None, end_date=None):
        """
        Obtém transações para um período específico
        period_type: 'day', 'month', 'year', 'custom'
        start_date, end_date: Usados apenas quando period_type='custom'
        """
        if not hasattr(self.parent_window, 'db_connection') or not hasattr(self.parent_window, 'user_id'):
            return None

        try:
            today = datetime.now()

            if period_type == 'day':
                # Transações de hoje
                start_date = today.strftime('%Y-%m-%d')
                end_date = start_date
            elif period_type == 'yesterday':
                # Transações de ontem
                yesterday = today - timedelta(days=1)
                start_date = yesterday.strftime('%Y-%m-%d')
                end_date = start_date
            elif period_type == 'week':
                # Transações da semana atual
                start_of_week = today - timedelta(days=today.weekday())
                start_date = start_of_week.strftime('%Y-%m-%d')
                end_date = today.strftime('%Y-%m-%d')
            elif period_type == 'month':
                # Transações do mês atual
                start_date = today.strftime('%Y-%m-01')
                end_date = today.strftime('%Y-%m-%d')
            elif period_type == 'last_month':
                # Transações do mês anterior
                first_day_current = today.replace(day=1)
                last_day_previous = first_day_current - timedelta(days=1)
                first_day_previous = last_day_previous.replace(day=1)
                start_date = first_day_previous.strftime('%Y-%m-%d')
                end_date = last_day_previous.strftime('%Y-%m-%d')
            elif period_type == 'year':
                # Transações do ano atual
                start_date = f"{today.year}-01-01"
                end_date = today.strftime('%Y-%m-%d')
            elif period_type == 'last_year':
                # Transações do ano anterior
                start_date = f"{today.year - 1}-01-01"
                end_date = f"{today.year - 1}-12-31"

            # Buscar transações para o período especificado
            transactions = self.parent_window.db_connection.execute(
                '''
                SELECT t.amount, t.description, t.transaction_type, t.date, c.name as category
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.date BETWEEN ? AND ?
                ORDER BY t.date
                ''',
                (self.parent_window.user_id, start_date, end_date)
            ).fetchall()

            # Calcular estatísticas do período
            total_income = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
            total_expense = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
            net_change = total_income - total_expense

            # Agrupar por categoria
            categories = {}
            for t in transactions:
                if t['transaction_type'] == 'saida':
                    cat_name = t['category'] or "Sem categoria"
                    if cat_name not in categories:
                        categories[cat_name] = 0
                    categories[cat_name] += t['amount']

            # Ordenar categorias por valor
            top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)

            return {
                'period': {
                    'start': start_date,
                    'end': end_date,
                    'type': period_type
                },
                'summary': {
                    'total_income': total_income,
                    'total_expense': total_expense,
                    'net_change': net_change,
                    'transaction_count': len(transactions)
                },
                'top_categories': top_categories[:5],  # Top 5 categorias
                'transactions': transactions
            }

        except Exception as e:
            print(f"Erro ao consultar transações por período: {e}")
            return None

    def analyze_specific_month(self, month, year=None):
        """Analisa dados de um mês específico (1-12)"""
        if not year:
            year = datetime.now().year

        try:
            # Definir primeiro e último dia do mês
            first_day = datetime(year, month, 1)
            if month == 12:
                last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(year, month + 1, 1) - timedelta(days=1)

            start_date = first_day.strftime('%Y-%m-%d')
            end_date = last_day.strftime('%Y-%m-%d')

            # Buscar transações para o período
            return self.get_transactions_by_period('custom', start_date, end_date)

        except Exception as e:
            print(f"Erro ao analisar mês específico: {e}")
            return None

    def analyze_date_range(self, start_date, end_date):
        """Analisa dados entre duas datas específicas"""
        try:
            return self.get_transactions_by_period('custom', start_date, end_date)
        except Exception as e:
            print(f"Erro ao analisar intervalo de datas: {e}")
            return None

    def send_message(self):
        """Envia a mensagem do usuário para a API"""
        text = self.input_area.toPlainText().strip()
        if not text:
            return

        # Verificar se a API está configurada
        if not self.api_config or not self.selected_model:
            QMessageBox.warning(
                self,
                "API não configurada",
                "Por favor, configure a API e selecione um modelo antes de enviar mensagens."
            )
            return

        # Adicionar mensagem do usuário
        self.add_message(text, is_user=True)

        # Limpar campo de entrada
        self.input_area.clear()

        # Adicionar espaço reservado para resposta da IA
        self.add_message("Gerando resposta...", is_user=False)

        # Construir prompt com contexto financeiro
        context = self.build_financial_context()

        # Verificar se a mensagem contém pedidos de análise de períodos específicos
        additional_context = ""

        # Termos que indicam análise de períodos específicos
        time_indicators = {
            'ontem': 'yesterday',
            'semana': 'week',
            'mês atual': 'month',
            'mês passado': 'last_month',
            'ano atual': 'year',
            'ano passado': 'last_year'
        }

        for indicator, period_type in time_indicators.items():
            if indicator.lower() in text.lower():
                period_data = self.get_transactions_by_period(period_type)
                if period_data:
                    additional_context += f"\nDados para {indicator}:\n"
                    additional_context += f"Período: {period_data['period']['start']} a {period_data['period']['end']}\n"
                    additional_context += f"Total de receitas: R$ {period_data['summary']['total_income']:.2f}\n"
                    additional_context += f"Total de despesas: R$ {period_data['summary']['total_expense']:.2f}\n"
                    additional_context += f"Saldo do período: R$ {period_data['summary']['net_change']:.2f}\n"

                    if period_data['top_categories']:
                        additional_context += "Principais categorias de despesa:\n"
                        for cat, amount in period_data['top_categories']:
                            additional_context += f"- {cat}: R$ {amount:.2f}\n"

        # Verificar menções a meses específicos
        months = {
            'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4, 'maio': 5, 'junho': 6,
            'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
        }

        current_year = datetime.now().year
        for month_name, month_num in months.items():
            if month_name.lower() in text.lower():
                # Verificar se um ano específico é mencionado
                year = current_year
                for year_mention in range(current_year-5, current_year+1):
                    if str(year_mention) in text:
                        year = year_mention
                        break

                month_data = self.analyze_specific_month(month_num, year)
                if month_data:
                    additional_context += f"\nDados para {month_name} de {year}:\n"
                    additional_context += f"Total de receitas: R$ {month_data['summary']['total_income']:.2f}\n"
                    additional_context += f"Total de despesas: R$ {month_data['summary']['total_expense']:.2f}\n"
                    additional_context += f"Saldo do período: R$ {month_data['summary']['net_change']:.2f}\n"

                    if month_data['top_categories']:
                        additional_context += "Principais categorias de despesa:\n"
                        for cat, amount in month_data['top_categories']:
                            additional_context += f"- {cat}: R$ {amount:.2f}\n"

        # Adicionar o contexto adicional
        if additional_context:
            context += "\n\nAnálise de dados específicos solicitados pelo usuário:" + additional_context

        full_prompt = f"{context}\n\nUsuário: {text}\n\nAssistente:"

        # Iniciar thread para processar requisição
        if self.api_thread:
            self.api_thread.stop()

        self.api_thread = AIAssistantThread(self.api_config, self.selected_model, full_prompt, self)
        self.api_thread.update_signal.connect(self.update_ai_response)
        self.api_thread.error_signal.connect(self.handle_api_error)
        self.api_thread.finished_signal.connect(self.api_request_finished)

        # Desabilitar botão de envio
        self.send_button.setEnabled(False)

        # Iniciar thread
        self.api_thread.start()

    def build_financial_context(self):
        """Constrói um contexto financeiro com base nos dados do usuário"""
        context = "Você é um assistente financeiro inteligente. "

        if hasattr(self.parent_window, 'db_connection') and hasattr(self.parent_window, 'user_id'):
            try:
                # Obter saldo atual
                transactions = self.parent_window.db_connection.execute(
                    'SELECT * FROM transactions WHERE user_id = ?',
                    (self.parent_window.user_id,)
                ).fetchall()

                entries_total = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
                exits_total = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
                balance = entries_total - exits_total

                # Verificar se a coluna is_savings_goal existe
                column_exists = self.parent_window.db_connection.execute(
                    "SELECT COUNT(*) FROM pragma_table_info('categories') WHERE name='is_savings_goal'"
                ).fetchone()[0] > 0

                # Calcular saldo disponível (deduzindo valores guardados)
                available_balance = balance
                total_savings = 0
                savings_categories_info = []

                if column_exists:
                    # Obter categorias com meta de guardar dinheiro
                    savings_categories = self.parent_window.db_connection.execute(
                        'SELECT id, name, total_amount FROM categories WHERE user_id = ? AND is_savings_goal = 1',
                        (self.parent_window.user_id,)
                    ).fetchall()

                    for category in savings_categories:
                        # Calcular quanto já foi guardado
                        amount_saved = self.parent_window.db_connection.execute(
                            "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'entrada'",
                            (self.parent_window.user_id, category['id'])
                        ).fetchone()[0] or 0

                        total_savings += amount_saved

                        # Calcular progresso
                        progress = 0
                        if category['total_amount'] > 0:
                            progress = min(100, int((amount_saved / category['total_amount']) * 100))

                        savings_categories_info.append({
                            'name': category['name'],
                            'saved': amount_saved,
                            'target': category['total_amount'],
                            'progress': progress
                        })

                    available_balance = balance - total_savings

                # Obter categorias com meta de quitação
                payment_categories_info = []
                payment_categories = self.parent_window.db_connection.execute(
                    'SELECT id, name, total_amount FROM categories WHERE user_id = ? AND is_payment_goal = 1',
                    (self.parent_window.user_id,)
                ).fetchall()

                for category in payment_categories:
                    # Calcular quanto já foi pago
                    amount_paid = self.parent_window.db_connection.execute(
                        "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'",
                        (self.parent_window.user_id, category['id'])
                    ).fetchone()[0] or 0

                    # Calcular progresso
                    progress = 0
                    if category['total_amount'] > 0:
                        progress = min(100, int((amount_paid / category['total_amount']) * 100))

                    payment_categories_info.append({
                        'name': category['name'],
                        'paid': amount_paid,
                        'target': category['total_amount'],
                        'progress': progress
                    })

                # Obter gastos por categoria nos últimos 3 meses
                three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

                category_expenses = self.parent_window.db_connection.execute(
                    '''
                    SELECT c.name, SUM(t.amount) as total
                    FROM transactions t
                    JOIN categories c ON t.category_id = c.id
                    WHERE t.user_id = ? AND t.transaction_type = 'saida' AND t.date >= ?
                    GROUP BY c.name
                    ORDER BY total DESC
                    LIMIT 5
                    ''',
                    (self.parent_window.user_id, three_months_ago)
                ).fetchall()

                # Obter metas de economia
                savings_goals = self.parent_window.db_connection.execute(
                    '''
                    SELECT name, target_amount, current_amount,
                           (current_amount / target_amount * 100) as progress
                    FROM savings_goals
                    WHERE user_id = ?
                    ''',
                    (self.parent_window.user_id,)
                ).fetchall()

                # Obter orçamentos mensais
                current_month = datetime.now().month
                current_year = datetime.now().year

                budgets = self.parent_window.db_connection.execute(
                    '''
                    SELECT c.name, cb.amount
                    FROM category_budgets cb
                    JOIN categories c ON cb.category_id = c.id
                    WHERE cb.user_id = ? AND cb.month = ? AND cb.year = ?
                    ''',
                    (self.parent_window.user_id, current_month, current_year)
                ).fetchall()

                # Construir contexto
                context += f"O usuário tem um saldo geral de R$ {balance:.2f}. "

                if total_savings > 0:
                    context += f"Deste valor, R$ {total_savings:.2f} está guardado em metas, "
                    context += f"deixando um saldo disponível de R$ {available_balance:.2f}. "

                if category_expenses:
                    context += "Nos últimos 3 meses, as principais categorias de despesa foram: "
                    categories_text = ", ".join([f"{c['name']} (R$ {c['total']:.2f})" for c in category_expenses])
                    context += f"{categories_text}. "

                if budgets:
                    context += "Para o mês atual, o usuário definiu os seguintes orçamentos: "
                    budgets_text = ", ".join([f"{b['name']} (R$ {b['amount']:.2f})" for b in budgets])
                    context += f"{budgets_text}. "

                if savings_goals:
                    context += "O usuário tem as seguintes metas de economia: "
                    goals_text = ", ".join([
                        f"{g['name']} (Meta: R$ {g['target_amount']:.2f}, Atual: R$ {g['current_amount']:.2f}, Progresso: {g['progress']:.1f}%)"
                        for g in savings_goals
                    ])
                    context += f"{goals_text}. "

                if savings_categories_info:
                    context += "O usuário também tem as seguintes categorias com metas de guardar dinheiro: "
                    savings_text = ", ".join([
                        f"{s['name']} (Meta: R$ {s['target']:.2f}, Guardado: R$ {s['saved']:.2f}, Progresso: {s['progress']}%)"
                        for s in savings_categories_info
                    ])
                    context += f"{savings_text}. "

                if payment_categories_info:
                    context += "O usuário está quitando as seguintes dívidas/financiamentos: "
                    payment_text = ", ".join([
                        f"{p['name']} (Total: R$ {p['target']:.2f}, Já Pago: R$ {p['paid']:.2f}, Progresso: {p['progress']}%)"
                        for p in payment_categories_info
                    ])
                    context += f"{payment_text}. "

                # Adicionar informações sobre transações recentes
                recent_transactions = self.parent_window.db_connection.execute(
                    '''
                    SELECT t.amount, t.description, t.transaction_type, t.date, c.name as category
                    FROM transactions t
                    LEFT JOIN categories c ON t.category_id = c.id
                    WHERE t.user_id = ?
                    ORDER BY t.date DESC
                    LIMIT 5
                    ''',
                    (self.parent_window.user_id,)
                ).fetchall()

                if recent_transactions:
                    context += "Transações mais recentes: "
                    transactions_text = ", ".join([
                        f"{t['description']} ({t['transaction_type']}, R$ {t['amount']:.2f}, {t['category'] or 'Sem categoria'}, {t['date']})"
                        for t in recent_transactions
                    ])
                    context += f"{transactions_text}. "

            except Exception as e:
                print(f"Erro ao construir contexto financeiro: {e}")
                pass

        context += "Use essas informações para fornecer conselhos personalizados e relevantes. "
        context += "Seja conciso, específico e prático em suas recomendações."

        return context

##  Agete de IA Fim

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestão Financeira Pessoal")
        self.setGeometry(100, 100, 800, 600)

        # Configurações de tema
        self.settings = QSettings("FinanceApp", "FinanceTracker")
        self.is_dark_mode = self.settings.value("dark_mode", False, type=bool)

        # Criar pasta 'dados' se não existir
        if not os.path.exists('dados'):
            os.makedirs('dados')

        self.db_connection = None
        self.user_id = None
        self.selected_year = datetime.now().year

        # Criar ícone para a aplicação
        self.app_icon = QIcon('finance_icon.png')
        self.setWindowIcon(self.app_icon)

        # Inicializar system tray icon
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("Gestão Financeira Pessoal")

        # Menu para o ícone da bandeja
        tray_menu = QMenu()

        # Ações do menu
        show_action = QAction("Abrir", self)
        show_action.triggered.connect(self.show)

        hide_action = QAction("Minimizar", self)
        hide_action.triggered.connect(self.hide)

        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self.close_application)

        # Adicionar ações ao menu
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)

        # Configurar menu
        self.tray_icon.setContextMenu(tray_menu)

        # Evento ao clicar no ícone
        self.tray_icon.activated.connect(self.tray_icon_activated)

        # Ativar o ícone da bandeja
        self.tray_icon.show()

        # Widget central
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Widgets para login
        self.username_label = QLabel("Usuário:")
        self.username_input = QLineEdit()
        self.password_label = QLabel("Senha:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.login_button = QPushButton("Login")
        self.register_button = QPushButton("Registrar")
        self.save_login_button = QPushButton("Salvar Login")

        # Widgets para dashboard
        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(6)
        self.transactions_table.setHorizontalHeaderLabels(["ID", "Descrição", "Valor", "Tipo", "Data", "Categoria"])

        self.add_transaction_button = QPushButton("Adicionar Transação")
        self.edit_transaction_button = QPushButton("Editar Transação")
        self.delete_transaction_button = QPushButton("Excluir Transação")

        self.notes_table = QTableWidget()
        self.notes_table.setColumnCount(2)
        self.notes_table.setHorizontalHeaderLabels(["ID", "Nota"])

        self.add_note_button = QPushButton("Adicionar Nota")
        self.edit_note_button = QPushButton("Editar Nota")
        self.delete_note_button = QPushButton("Excluir Nota")

        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(2)
        self.categories_table.setHorizontalHeaderLabels(["ID", "Nome"])

        self.add_category_button = QPushButton("Adicionar Categoria")
        self.edit_category_button = QPushButton("Editar Categoria")
        self.delete_category_button = QPushButton("Excluir Categoria")

        self.balance_label = QLabel("Saldo: R$ 0.00")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Pesquisar por descrição ou categoria...")
        self.search_input.textChanged.connect(self.load_transactions)

        self.year_buttons_layout = QHBoxLayout()

        self.logout_button = QPushButton("Sair")
        self.logout_button.clicked.connect(self.logout)

        # Botão de modo escuro
        self.dark_mode_button = QPushButton("Modo Escuro: Desativado" if not self.is_dark_mode else "Modo Escuro: Ativado")
        self.dark_mode_button.clicked.connect(self.toggle_dark_mode)

        # Botões para funcionalidades
        self.budget_button = QPushButton("Orçamento Mensal")
        self.budget_button.clicked.connect(self.show_budget_dialog)

        self.cashflow_button = QPushButton("Fluxo de Caixa")
        self.cashflow_button.clicked.connect(self.show_cashflow_dialog)

        self.calendar_button = QPushButton("Calendário Financeiro")
        self.calendar_button.clicked.connect(self.show_calendar_dialog)

        self.trends_button = QPushButton("Tendências")
        self.trends_button.clicked.connect(self.show_trends_dialog)

        self.savings_goals_button = QPushButton("Metas de Economia")
        self.savings_goals_button.clicked.connect(self.show_savings_goals)

        # Inicializar o assistente de IA (atributo declarado mas inicializado no load_dashboard)
        self.ai_assistant_button = None

        # Criar o layout de login inicialmente
        self.login_layout = self.create_login_layout()
        self.main_layout.addLayout(self.login_layout)

        # Carregar login salvo ao iniciar o aplicativo
        self.load_saved_login()

        # Conectar sinais aos slots
        self.login_button.clicked.connect(self.login)
        self.register_button.clicked.connect(self.register)
        self.add_transaction_button.clicked.connect(self.show_add_transaction_dialog)
        self.edit_transaction_button.clicked.connect(self.show_edit_transaction_dialog)
        self.delete_transaction_button.clicked.connect(self.delete_transaction)
        self.add_note_button.clicked.connect(self.show_add_note_dialog)
        self.edit_note_button.clicked.connect(self.show_edit_note_dialog)
        self.delete_note_button.clicked.connect(self.delete_note)
        self.add_category_button.clicked.connect(self.show_add_category_dialog)
        self.edit_category_button.clicked.connect(self.show_edit_category_dialog)
        self.delete_category_button.clicked.connect(self.delete_category)
        self.save_login_button.clicked.connect(self.save_login)

        # Aplicar tema inicial
        self.apply_theme()

        # Definir comportamento ao fechar a janela
        self.setMinimizeToTray()

        # Definir flag para iniciar minimizado
        self.start_minimized = True

    def closeEvent(self, event):
        """Controla o comportamento ao fechar a janela"""
        # Minimizar para a bandeja em vez de fechar
        if self.minimizeToTray:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Gestão Financeira",
                "Aplicativo minimizado para a bandeja do sistema.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            # Salvar configurações
            self.settings.setValue("dark_mode", self.is_dark_mode)

            # Se houver conexão com banco de dados, fechá-la
            if self.db_connection:
                self.db_connection.close()

            event.accept()

    def tray_icon_activated(self, reason):
        """Gerencia os eventos do ícone da bandeja"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()

    def close_application(self):
        """Fecha a aplicação completamente"""
        self.minimizeToTray = False
        self.close()

    def setMinimizeToTray(self):
        """Define se o aplicativo minimiza para a bandeja"""
        self.minimizeToTray = True

    def toggle_dark_mode(self):
        """Alterna entre modo claro e escuro"""
        self.is_dark_mode = not self.is_dark_mode

        # Atualizar texto do botão
        self.dark_mode_button.setText("Modo Escuro: Ativado" if self.is_dark_mode else "Modo Escuro: Desativado")

        # Aplicar o tema
        self.apply_theme()

        # Salvar configuração
        self.settings.setValue("dark_mode", self.is_dark_mode)

    def apply_theme(self):
        """Aplica o tema (claro ou escuro) a toda a aplicação"""
        if self.is_dark_mode:
            # Tema escuro
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)

            self.setPalette(palette)

            # Estilo para controles
            self.setStyleSheet("""
                QMainWindow, QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                    selection-background-color: #3498db;
                    selection-color: white;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    padding: 5px;
                    border: 1px solid #4b6584;
                }
                QTabWidget::pane {
                    border: 1px solid #4b6584;
                    background-color: #1e272e;
                }
                QTabBar::tab {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    padding: 8px 12px;
                    border: 1px solid #4b6584;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #3498db;
                }
            """)
        else:
            # Tema claro
            palette = QPalette()
            self.setPalette(palette)

            # Estilo para controles
            self.setStyleSheet("""
                QMainWindow, QDialog {
                    background-color: #f9f9f9;
                    color: #333333;
                }
                QLabel {
                    color: #333333;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: white;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QTableWidget {
                    background-color: white;
                    color: #333333;
                    gridline-color: #ddd;
                    selection-background-color: #e3f2fd;
                    selection-color: #333333;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    color: #333333;
                    padding: 5px;
                    border: 1px solid #ccc;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0;
                    color: #333333;
                    padding: 8px 12px;
                    border: 1px solid #ccc;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #4CAF50;
                    color: white;
                }
            """)

    def create_login_layout(self):
        """
        Cria o layout da tela de login
        Retorna: QVBoxLayout com os widgets de login
        """
        login_layout = QVBoxLayout()

        # Criar container para melhor organização
        login_container = QWidget()
        container_layout = QVBoxLayout(login_container)

        # Título
        title_label = QLabel("Sistema de Gestão Financeira")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 20px;")
        title_label.setAlignment(Qt.AlignCenter)

        # Adicionar widgets ao layout do container
        container_layout.addWidget(title_label)
        container_layout.addWidget(self.username_label)
        container_layout.addWidget(self.username_input)
        container_layout.addWidget(self.password_label)
        container_layout.addWidget(self.password_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.register_button)
        container_layout.addLayout(button_layout)
        container_layout.addWidget(self.save_login_button)

        # Centralizar o container no layout principal
        login_layout.addStretch(1)
        login_layout.addWidget(login_container, 0, Qt.AlignCenter)
        login_layout.addStretch(1)

        return login_layout

    def get_db_path(self, username):
        """
        Retorna o caminho para o banco de dados do usuário
        """
        return os.path.join('dados', f'{username}.db')

    def create_tables(self):
        """
        Cria as tabelas necessárias no banco de dados se não existirem
        """
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS users
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         username TEXT UNIQUE NOT NULL,
                         password TEXT NOT NULL)''')

        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS transactions
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         amount REAL NOT NULL,
                         description TEXT NOT NULL,
                         transaction_type TEXT NOT NULL,
                         date TEXT NOT NULL,
                         category_id INTEGER,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         FOREIGN KEY (category_id) REFERENCES categories (id))''')

        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS notes
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         note TEXT NOT NULL,
                         FOREIGN KEY (user_id) REFERENCES users (id))''')

        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS categories
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         name TEXT NOT NULL,
                         total_amount REAL DEFAULT 0,
                         is_payment_goal INTEGER DEFAULT 0,
                         FOREIGN KEY (user_id) REFERENCES users (id))''')

        # Tabela para orçamentos mensais
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS category_budgets
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         category_id INTEGER NOT NULL,
                         month INTEGER NOT NULL,
                         year INTEGER NOT NULL,
                         amount REAL NOT NULL,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         FOREIGN KEY (category_id) REFERENCES categories (id),
                         UNIQUE(user_id, category_id, month, year))''')

        # Tabela para metas de economia
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS savings_goals
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         name TEXT NOT NULL,
                         target_amount REAL NOT NULL,
                         current_amount REAL DEFAULT 0,
                         start_date TEXT NOT NULL,
                         deadline TEXT,
                         category_id INTEGER,
                         notes TEXT,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         FOREIGN KEY (category_id) REFERENCES categories (id))''')

        # Tabela de configurações do usuário
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS user_settings
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         setting_key TEXT NOT NULL,
                         setting_value TEXT,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         UNIQUE(user_id, setting_key))''')

        # Tabela de versão do banco de dados
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS db_version
                        (version INTEGER)''')

    def login(self):
        """
        Realiza o login do usuário
        Verifica credenciais e carrega o dashboard se autenticado
        """
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Erro", "Por favor, preencha todos os campos.")
            return

        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        # Criar tabelas se não existirem
        self.create_tables()

        # Verificar e atualizar esquema do banco de dados se necessário
        if not DBUpdater.check_and_update(self.db_connection, username):
            QMessageBox.critical(self, "Erro", "Não foi possível atualizar o banco de dados. Contate o suporte.")
            self.db_connection.close()
            return

        user = self.db_connection.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                            (username, password)).fetchone()
        if user:
            self.user_id = user['id']

            # Forçar atualização do banco de dados (adicionado)
            self.force_db_update()

            # Remover o layout de login
            self.clear_layout(self.main_layout)
            self.load_dashboard()

            # Carregar preferências do usuário
            self.load_user_preferences()
        else:
            QMessageBox.warning(self, "Erro", "Usuário ou senha incorretos.")
            self.db_connection.close()

    def force_db_update(self):
        """Força a atualização do banco de dados para adicionar a coluna is_savings_goal"""
        try:
            # Verificar se a coluna já existe
            column_exists = self.db_connection.execute(
                "SELECT COUNT(*) FROM pragma_table_info('categories') WHERE name='is_savings_goal'"
            ).fetchone()[0] > 0

            if not column_exists:
                # Adicionar a coluna
                self.db_connection.execute('ALTER TABLE categories ADD COLUMN is_savings_goal INTEGER DEFAULT 0')
                self.db_connection.commit()

                # Atualizar a versão do banco de dados
                self.db_connection.execute('UPDATE db_version SET version = 3')
                self.db_connection.commit()

                print("Banco de dados atualizado manualmente para a versão 3")
                return True
            return True
        except Exception as e:
            print(f"Erro ao atualizar manualmente o banco de dados: {e}")
            return False

    def load_user_preferences(self):
        """Carrega preferências do usuário do banco de dados"""
        try:
            # Carregar tema
            theme_setting = self.db_connection.execute(
                "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = 'dark_mode'",
                (self.user_id,)
            ).fetchone()

            if theme_setting:
                self.is_dark_mode = theme_setting['setting_value'].lower() == 'true'
                self.dark_mode_button.setText("Modo Escuro: Ativado" if self.is_dark_mode else "Modo Escuro: Desativado")
                self.apply_theme()
        except:
            pass

    def save_user_preferences(self):
        """Salva preferências do usuário no banco de dados"""
        try:
            # Verificar se já existe uma configuração
            existing = self.db_connection.execute(
                "SELECT id FROM user_settings WHERE user_id = ? AND setting_key = 'dark_mode'",
                (self.user_id,)
            ).fetchone()

            if existing:
                # Atualizar configuração existente
                self.db_connection.execute(
                    "UPDATE user_settings SET setting_value = ? WHERE user_id = ? AND setting_key = 'dark_mode'",
                    (str(self.is_dark_mode), self.user_id)
                )
            else:
                # Criar nova configuração
                self.db_connection.execute(
                    "INSERT INTO user_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
                    (self.user_id, 'dark_mode', str(self.is_dark_mode))
                )

            self.db_connection.commit()
        except:
            pass

    def register(self):
        """
        Registra um novo usuário
        Cria um novo banco de dados para o usuário
        """
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Erro", "Por favor, preencha todos os campos.")
            return

        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        self.create_tables()

        # Definir versão do banco de dados
        self.db_connection.execute('INSERT INTO db_version VALUES (?)', (DB_VERSION,))

        try:
            self.db_connection.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                     (username, password))
            self.db_connection.commit()
            QMessageBox.information(self, "Sucesso", "Usuário registrado com sucesso.")
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Erro", "Nome de usuário já existe.")
        finally:
            self.db_connection.close()

    def init_ai_assistant(self):
        """Inicializa o assistente de IA"""
        # Botão para o assistente de IA no dashboard
        self.ai_assistant_button = QPushButton("🤖 Assistente IA")
        self.ai_assistant_button.clicked.connect(self.show_ai_assistant)

        # Estilizar botão do assistente
        if self.is_dark_mode:
            self.ai_assistant_button.setStyleSheet("""
                background-color: #8e44ad;
                color: white;
                font-weight: bold;
            """)
        else:
            self.ai_assistant_button.setStyleSheet("""
                background-color: #9c27b0;
                color: white;
                font-weight: bold;
            """)

    def show_ai_assistant(self):
        """Mostra o assistente de IA"""
        # Criar diálogo para o assistente
        assistant_dialog = QDialog(self)
        assistant_dialog.setWindowTitle("Assistente Financeiro IA")
        assistant_dialog.resize(600, 600)

        # Layout
        layout = QVBoxLayout()

        # Adicionar widget do assistente
        assistant_widget = AIAssistantWidget(self)
        layout.addWidget(assistant_widget)

        assistant_dialog.setLayout(layout)

        # Aplicar tema
        if self.is_dark_mode:
            assistant_dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
            """)

        assistant_dialog.exec_()

    def load_dashboard(self):
        """
        Carrega o dashboard principal com todos os widgets e dados
        """
        # Layout principal
        dashboard_layout = QVBoxLayout()

        # Adicionar um título
        title_label = QLabel(f"Gestão Financeira - {self.username_input.text()}")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px 0;")
        dashboard_layout.addWidget(title_label)

        # Saldo e pesquisa em um layout horizontal
        top_layout = QHBoxLayout()

        # Estilizar o label de saldo
        self.balance_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            padding: 10px;
            border-radius: 4px;
        """)

        top_layout.addWidget(self.balance_label)

        # Estilizar o campo de pesquisa
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_icon_label = QLabel("🔍")
        search_layout.addWidget(search_icon_label)
        search_layout.addWidget(self.search_input)

        top_layout.addWidget(search_container)
        dashboard_layout.addLayout(top_layout)

        # Adicionar botões de ano
        year_group = QGroupBox("Filtrar por Ano:")
        dashboard_layout.addLayout(self.year_buttons_layout)

        # Inicializar o assistente de IA
        self.init_ai_assistant()

        # Layout para botões de ferramentas
        tools_layout = QHBoxLayout()

        # Adicionar os botões
        tools_layout.addWidget(self.budget_button)
        tools_layout.addWidget(self.cashflow_button)
        tools_layout.addWidget(self.calendar_button)
        tools_layout.addWidget(self.trends_button)
        tools_layout.addWidget(self.savings_goals_button)
        tools_layout.addWidget(self.ai_assistant_button)  # Adicionado o botão de IA

        dashboard_layout.addLayout(tools_layout)

        # Transações
        transactions_group = QGroupBox("Transações")
        transactions_layout = QVBoxLayout()
        transactions_layout.addWidget(self.transactions_table)

        transaction_button_layout = QHBoxLayout()
        transaction_button_layout.addWidget(self.add_transaction_button)
        transaction_button_layout.addWidget(self.edit_transaction_button)
        transaction_button_layout.addWidget(self.delete_transaction_button)

        transactions_layout.addLayout(transaction_button_layout)
        transactions_group.setLayout(transactions_layout)

        dashboard_layout.addWidget(transactions_group)

        # Categorias e Notas em um layout horizontal
        bottom_layout = QHBoxLayout()

        # Categorias
        categories_group = QGroupBox("Categorias")
        categories_layout = QVBoxLayout()
        categories_layout.addWidget(self.categories_table)

        category_button_layout = QHBoxLayout()
        category_button_layout.addWidget(self.add_category_button)
        category_button_layout.addWidget(self.edit_category_button)
        category_button_layout.addWidget(self.delete_category_button)

        categories_layout.addLayout(category_button_layout)
        categories_group.setLayout(categories_layout)

        # Notas
        notes_group = QGroupBox("Notas")
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(self.notes_table)

        note_button_layout = QHBoxLayout()
        note_button_layout.addWidget(self.add_note_button)
        note_button_layout.addWidget(self.edit_note_button)
        note_button_layout.addWidget(self.delete_note_button)

        notes_layout.addLayout(note_button_layout)
        notes_group.setLayout(notes_layout)

        bottom_layout.addWidget(categories_group)
        bottom_layout.addWidget(notes_group)

        dashboard_layout.addLayout(bottom_layout)

        # Botões de relatórios e gráficos
        report_layout = QHBoxLayout()

        # Botões para relatórios e gráficos
        report_button = QPushButton("📊 Gerar Relatório")
        report_button.clicked.connect(self.generate_category_report)

        graph_button = QPushButton("📈 Gerar Gráfico")
        graph_button.clicked.connect(self.generate_category_graph)

        export_report_button = QPushButton("📋 Exportar Relatório")
        export_report_button.clicked.connect(self.export_report)

        report_layout.addWidget(report_button)
        report_layout.addWidget(graph_button)
        report_layout.addWidget(export_report_button)

        dashboard_layout.addLayout(report_layout)

        # Layout para botões de modo e logout
        action_layout = QHBoxLayout()
        action_layout.addWidget(self.dark_mode_button)
        action_layout.addStretch()
        action_layout.addWidget(self.logout_button)

        dashboard_layout.addLayout(action_layout)

        # Adicionar o layout do dashboard ao layout principal
        self.main_layout.addLayout(dashboard_layout)

        # Carregar dados
        self.load_transactions()
        self.load_notes()
        self.load_categories()
        self.update_balance()
        self.update_year_buttons()  # Atualizar botões de ano

    def export_report(self):
        """
        Exporta um relatório financeiro completo para um arquivo de texto ou CSV
        """
        # Obter transações do usuário para o ano selecionado
        transactions = self.db_connection.execute(
            """
            SELECT t.*, c.name AS category_name
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            ORDER BY t.date ASC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not transactions:
            QMessageBox.information(self, "Informação", "Não há transações para exportar no período selecionado.")
            return

        # Perguntar ao usuário qual formato deseja exportar
        format_dialog = QDialog(self)
        format_dialog.setWindowTitle("Escolher Formato de Exportação")
        format_dialog.setFixedSize(400, 150)

        layout = QVBoxLayout()

        # Título e instruções
        title_label = QLabel("Escolha o formato de exportação:")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Botões de formato
        buttons_layout = QHBoxLayout()

        txt_button = QPushButton("Texto (.txt)")
        txt_button.clicked.connect(lambda: format_dialog.done(1))  # 1 para TXT

        csv_button = QPushButton("Excel (.csv)")
        csv_button.clicked.connect(lambda: format_dialog.done(2))  # 2 para CSV

        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(format_dialog.reject)

        buttons_layout.addWidget(txt_button)
        buttons_layout.addWidget(csv_button)
        buttons_layout.addWidget(cancel_button)

        layout.addLayout(buttons_layout)
        format_dialog.setLayout(layout)

        # Mostrar diálogo e obter escolha
        result = format_dialog.exec_()

        if result == 0:  # Cancelado
            return

        # Determinar o formato e extensão
        if result == 1:  # TXT
            file_extension = "txt"
            file_filter = "Arquivos de Texto (*.txt)"
        else:  # CSV
            file_extension = "csv"
            file_filter = "Arquivos CSV (*.csv)"

        # Abrir diálogo para salvar arquivo
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório",
            f"relatorio_{self.selected_year}.{file_extension}",
            file_filter
        )

        if not file_path:
            return

        try:
            if result == 1:  # TXT
                self.export_txt_report(file_path, transactions)
            else:  # CSV
                self.export_csv_report(file_path, transactions)

            QMessageBox.information(self, "Sucesso", f"Relatório exportado com sucesso!\nArquivo: {file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível exportar o relatório.\nErro: {str(e)}")

    def export_txt_report(self, file_path, transactions):
        """
        Exporta o relatório em formato de texto
        """
        # Montar o conteúdo do relatório
        report_lines = []
        report_lines.append(f"RELATÓRIO DE TRANSAÇÕES - Ano: {self.selected_year}")
        report_lines.append("=" * 50)
        report_lines.append("ID | Descrição | Valor | Tipo | Data | Categoria")
        report_lines.append("-" * 50)

        for t in transactions:
            line = f"{t['id']} | {t['description']} | R$ {t['amount']:.2f} | {t['transaction_type']} | {t['date']} | {t['category_name']}"
            report_lines.append(line)

        report_lines.append("=" * 50)
        report_lines.append("RESUMO POR CATEGORIA")

        # Consultar o resumo de gastos por categoria para o ano selecionado
        categories = self.db_connection.execute(
            """
            SELECT c.name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            GROUP BY c.name
            ORDER BY total_spent DESC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        for cat in categories:
            report_lines.append(f"{cat[0]}: R$ {cat[1]:.2f}")

        report_lines.append("=" * 50)

        # Informações de saldo geral
        transactions_all = self.db_connection.execute(
            'SELECT * FROM transactions WHERE user_id = ?', (self.user_id,)
        ).fetchall()
        entries_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'entrada')
        exits_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'saida')
        balance = entries_total - exits_total
        report_lines.append(f"Saldo Total: R$ {balance:.2f}")

        # Converter a lista de linhas em uma única string
        report_content = "\n".join(report_lines)

        # Escrever no arquivo
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    def export_csv_report(self, file_path, transactions):
        """
        Exporta o relatório em formato CSV para Excel
        """
        import csv

        # Abrir arquivo CSV para escrita
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as csv_file:
            # Criar escritor CSV
            csv_writer = csv.writer(csv_file, delimiter=';')  # Usar ponto e vírgula como delimitador para melhor compatibilidade com Excel brasileiro

            # Escrever cabeçalho do relatório
            csv_writer.writerow([f"RELATÓRIO DE TRANSAÇÕES - Ano: {self.selected_year}"])
            csv_writer.writerow([])  # Linha em branco

            # Escrever cabeçalho das transações
            csv_writer.writerow(["ID", "Descrição", "Valor (R$)", "Tipo", "Data", "Categoria"])

            # Escrever dados das transações
            for t in transactions:
                csv_writer.writerow([
                    t['id'],
                    t['description'],
                    f"{t['amount']:.2f}".replace('.', ','),  # Usar vírgula como separador decimal para Excel brasileiro
                    t['transaction_type'],
                    t['date'],
                    t['category_name'] or ""
                ])

            csv_writer.writerow([])  # Linha em branco
            csv_writer.writerow(["RESUMO POR CATEGORIA"])

            # Consultar o resumo de gastos por categoria
            categories = self.db_connection.execute(
                """
                SELECT c.name, SUM(t.amount) AS total_spent
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
                GROUP BY c.name
                ORDER BY total_spent DESC
                """,
                (self.user_id, str(self.selected_year))
            ).fetchall()

            # Escrever resumo por categoria
            csv_writer.writerow(["Categoria", "Total Gasto (R$)"])
            for cat in categories:
                csv_writer.writerow([
                    cat[0],
                    f"{cat[1]:.2f}".replace('.', ',')
                ])

            csv_writer.writerow([])  # Linha em branco

            # Informações de saldo geral
            transactions_all = self.db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?', (self.user_id,)
            ).fetchall()
            entries_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'entrada')
            exits_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'saida')
            balance = entries_total - exits_total

            # Escrever saldo geral
            csv_writer.writerow(["RESUMO GERAL"])
            csv_writer.writerow(["Total de Entradas (R$)", f"{entries_total:.2f}".replace('.', ',')])
            csv_writer.writerow(["Total de Saídas (R$)", f"{exits_total:.2f}".replace('.', ',')])
            csv_writer.writerow(["Saldo Total (R$)", f"{balance:.2f}".replace('.', ',')])

    def update_year_buttons(self):
        """
        Atualiza os botões de ano com base nas transações existentes
        """
        # Limpar botões existentes
        while self.year_buttons_layout.count():
            child = self.year_buttons_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Obter anos disponíveis
        years = self.db_connection.execute(
            '''
            SELECT DISTINCT strftime('%Y', date) as year
            FROM transactions
            WHERE user_id = ?
            ORDER BY year DESC
            ''', (self.user_id,)
        ).fetchall()

        # Adicionar botão para cada ano
        for year in years:
            year_button = QPushButton(year['year'])
            year_button.setCheckable(True)
            year_button.setChecked(year['year'] == str(self.selected_year))
            year_button.toggled.connect(lambda checked, y=year['year']: self.toggle_year(y, checked))
            self.year_buttons_layout.addWidget(year_button)

    def toggle_year(self, year, checked):
        """
        Alterna o ano selecionado para filtrar transações
        """
        if checked:
            self.selected_year = int(year)
            self.load_transactions()
        else:
            # Verificar se algum botão está marcado
            any_checked = False
            for i in range(self.year_buttons_layout.count()):
                button = self.year_buttons_layout.itemAt(i).widget()
                if button and button.isChecked():
                    any_checked = True
                    break

            # Se nenhum botão estiver marcado, voltar para o ano atual
            if not any_checked:
                self.selected_year = datetime.now().year
                self.load_transactions()

    def load_transactions(self):
        """
        Carrega as transações do usuário com filtragem por ano e texto de pesquisa
        """
        search_text = self.search_input.text().lower()
        query = '''
            SELECT t.*, c.name AS category_name
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?'''

        if search_text:
            query += " AND (LOWER(t.description) LIKE ? OR LOWER(c.name) LIKE ?)"
            transactions = self.db_connection.execute(query, (self.user_id, str(self.selected_year), f'%{search_text}%', f'%{search_text}%')).fetchall()
        else:
            transactions = self.db_connection.execute(query, (self.user_id, str(self.selected_year))).fetchall()

        # Configurar a tabela
        self.transactions_table.setRowCount(len(transactions))
        for i, transaction in enumerate(transactions):
            # Definir cor de fundo com base no tipo (entrada/saída)
            entry_color = QColor("#E8F5E9")  # Verde claro para entradas
            exit_color = QColor("#FFEBEE")   # Vermelho claro para saídas

            # Ajustar cores para o tema escuro
            if self.is_dark_mode:
                entry_color = QColor("#1B5E20")  # Verde escuro para entradas
                exit_color = QColor("#B71C1C")   # Vermelho escuro para saídas

            # Criar itens da tabela
            id_item = QTableWidgetItem(str(transaction['id']))
            desc_item = QTableWidgetItem(transaction['description'])

            # Formatar valor com 2 casas decimais
            amount_text = f"R$ {transaction['amount']:.2f}"
            amount_item = QTableWidgetItem(amount_text)

            type_item = QTableWidgetItem(transaction['transaction_type'])
            date_item = QTableWidgetItem(transaction['date'])
            category_item = QTableWidgetItem(transaction['category_name'] or "")

            # Definir cor de fundo com base no tipo
            row_color = entry_color if transaction['transaction_type'] == 'entrada' else exit_color

            # Aplicar cor aos itens
            for item in [id_item, desc_item, amount_item, type_item, date_item, category_item]:
                item.setBackground(row_color)

            # Adicionar itens à tabela
            self.transactions_table.setItem(i, 0, id_item)
            self.transactions_table.setItem(i, 1, desc_item)
            self.transactions_table.setItem(i, 2, amount_item)
            self.transactions_table.setItem(i, 3, type_item)
            self.transactions_table.setItem(i, 4, date_item)
            self.transactions_table.setItem(i, 5, category_item)

        # Ajustar largura das colunas
        self.transactions_table.resizeColumnsToContents()

    def load_notes(self):
        """
        Carrega as notas do usuário
        """
        notes = self.db_connection.execute('SELECT * FROM notes WHERE user_id = ?', (self.user_id,)).fetchall()
        self.notes_table.setRowCount(len(notes))
        for i, note in enumerate(notes):
            id_item = QTableWidgetItem(str(note['id']))
            note_item = QTableWidgetItem(note['note'])

            # Adicionar itens à tabela
            self.notes_table.setItem(i, 0, id_item)
            self.notes_table.setItem(i, 1, note_item)

        # Ajustar largura das colunas
        self.notes_table.resizeColumnsToContents()

    def load_categories(self):
        """
        Carrega as categorias do usuário
        """
        categories = self.db_connection.execute('SELECT * FROM categories WHERE user_id = ?', (self.user_id,)).fetchall()
        self.categories_table.setRowCount(len(categories))
        for i, category in enumerate(categories):
            id_item = QTableWidgetItem(str(category['id']))
            name_item = QTableWidgetItem(category['name'])

            # Destacar visualmente categorias com metas
            if category['is_payment_goal'] == 1:
                payment_color = QColor("#E8F5FE") if not self.is_dark_mode else QColor("#01579B")
                id_item.setBackground(payment_color)
                name_item.setBackground(payment_color)
                # Incluir indicador visual de meta de quitação
                name_item.setText(f"{category['name']} 🎯")
            # Verificar se a coluna is_savings_goal existe
            elif 'is_savings_goal' in category.keys() and category['is_savings_goal'] == 1:
                savings_color = QColor("#E8FFF0") if not self.is_dark_mode else QColor("#1B5E20")
                id_item.setBackground(savings_color)
                name_item.setBackground(savings_color)
                # Incluir indicador visual de meta de guardar dinheiro
                name_item.setText(f"{category['name']} 💰")

            # Adicionar itens à tabela
            self.categories_table.setItem(i, 0, id_item)
            self.categories_table.setItem(i, 1, name_item)

        # Ajustar largura das colunas
        self.categories_table.resizeColumnsToContents()

    def update_balance(self):
        """
        Atualiza o saldo total do usuário e informações sobre metas
        """
        transactions = self.db_connection.execute('SELECT * FROM transactions WHERE user_id = ?', (self.user_id,)).fetchall()
        entries_total = sum(transaction['amount'] for transaction in transactions if transaction['transaction_type'] == 'entrada')
        exits_total = sum(transaction['amount'] for transaction in transactions if transaction['transaction_type'] == 'saida')
        balance = entries_total - exits_total

        # Verificar se a coluna is_savings_goal existe
        column_exists = self.db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('categories') WHERE name='is_savings_goal'"
        ).fetchone()[0] > 0

        total_savings = 0
        savings_goals_info = []

        if column_exists:
            # Calcular o total guardado em metas de guardar dinheiro
            savings_categories = self.db_connection.execute(
                'SELECT id, name, total_amount FROM categories WHERE user_id = ? AND is_savings_goal = 1',
                (self.user_id,)
            ).fetchall()

            for category in savings_categories:
                category_entries = self.db_connection.execute(
                    "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'entrada'",
                    (self.user_id, category['id'])
                ).fetchone()[0] or 0

                total_savings += category_entries

                # Verificar se meta foi alcançada para mostrar notificação
                if category_entries >= category['total_amount'] and category['total_amount'] > 0:
                    savings_goals_info.append({
                        'name': category['name'],
                        'amount': category_entries,
                        'target': category['total_amount'],
                        'completed': True
                    })
                else:
                    savings_goals_info.append({
                        'name': category['name'],
                        'amount': category_entries,
                        'target': category['total_amount'],
                        'completed': False
                    })

        # Criar texto para o saldo com informações adicionais
        balance_text = f"Saldo Geral: R$ {balance:.2f}"

        if total_savings > 0:
            balance_text += f"\nGuardado em Metas: R$ {total_savings:.2f}"
            balance_text += f"\nSaldo Disponível: R$ {(balance - total_savings):.2f}"

        # Definir cor com base no saldo (positivo ou negativo)
        if self.is_dark_mode:
            if balance >= 0:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #4CAF50;
                    background-color: #263238;
                    padding: 10px;
                    border-radius: 4px;
                """)
            else:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #F44336;
                    background-color: #263238;
                    padding: 10px;
                    border-radius: 4px;
                """)
        else:
            if balance >= 0:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #2e7d32;
                    background-color: #e8f5e9;
                    padding: 10px;
                    border-radius: 4px;
                """)
            else:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #c62828;
                    background-color: #ffebee;
                    padding: 10px;
                    border-radius: 4px;
                """)

        self.balance_label.setText(balance_text)

        # Mostrar notificações para metas alcançadas
        for goal in savings_goals_info:
            if goal['completed']:
                self.tray_icon.showMessage(
                    "Meta Alcançada!",
                    f"Parabéns! Você atingiu sua meta de guardar R$ {goal['target']:.2f} para '{goal['name']}'!",
                    QSystemTrayIcon.Information,
                    5000
                )

    def show_add_transaction_dialog(self):
        """
        Mostra diálogo para adicionar uma nova transação
        """
        dialog = AddTransactionDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_transactions()
            self.update_balance()
            self.update_year_buttons()

    def show_edit_transaction_dialog(self):
        """
        Mostra diálogo para editar uma transação existente
        """
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(self.transactions_table.item(selected_row, 0).text())
            dialog = EditTransactionDialog(self, transaction_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma transação para editar.")

    def delete_transaction(self):
        """
        Exclui a transação selecionada
        """
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(self.transactions_table.item(selected_row, 0).text())

            # Pedir confirmação
            reply = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                "Tem certeza que deseja excluir esta transação?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.db_connection.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
                self.db_connection.commit()
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma transação para excluir.")

    def show_add_note_dialog(self):
        """
        Mostra diálogo para adicionar uma nova nota
        """
        dialog = AddNoteDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_notes()

    def show_edit_note_dialog(self):
        """
        Mostra diálogo para editar uma nota existente
        """
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())
            dialog = EditNoteDialog(self, note_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_notes()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma nota para editar.")

    def delete_note(self):
        """
        Exclui a nota selecionada
        """
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())

            # Pedir confirmação
            reply = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                "Tem certeza que deseja excluir esta nota?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.db_connection.execute('DELETE FROM notes WHERE id = ?', (note_id,))
                self.db_connection.commit()
                self.load_notes()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma nota para excluir.")

    def show_add_category_dialog(self):
        """
        Mostra diálogo para adicionar uma nova categoria
        """
        dialog = AddCategoryDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_categories()

    def show_edit_category_dialog(self):
        """
        Mostra diálogo para editar uma categoria existente
        """
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(self.categories_table.item(selected_row, 0).text())
            dialog = EditCategoryDialog(self, category_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_categories()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma categoria para editar.")

    def delete_category(self):
        """
        Exclui a categoria selecionada se não houver transações associadas
        """
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(self.categories_table.item(selected_row, 0).text())
            category_name = self.categories_table.item(selected_row, 1).text()

            # Verificar se há transações usando esta categoria
            transactions = self.db_connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE category_id = ?",
                (category_id,)
            ).fetchone()

            if transactions[0] > 0:
                QMessageBox.warning(
                    self,
                    "Erro",
                    f"Não é possível excluir a categoria '{category_name}' pois existem {transactions[0]} transações vinculadas a ela."
                )
                return

            # Pedir confirmação
            reply = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                f"Tem certeza que deseja excluir a categoria '{category_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.db_connection.execute('DELETE FROM categories WHERE id = ?', (category_id,))
                self.db_connection.commit()
                self.load_categories()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma categoria para excluir.")

    def save_login(self):
        """
        Salva as credenciais de login em um arquivo local
        """
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Erro", "Por favor, preencha todos os campos.")
            return

        with open("login.txt", "w") as f:
            f.write(f"{username},{password}")

        QMessageBox.information(self, "Sucesso", "Login salvo com sucesso.")

    def load_saved_login(self):
        """
        Carrega as credenciais de login salvas
        """
        if os.path.exists("login.txt"):
            with open("login.txt", "r") as f:
                try:
                    username, password = f.read().split(",")
                    self.username_input.setText(username)
                    self.password_input.setText(password)
                except:
                    pass  # Ignora erros de formato no arquivo

    def generate_category_report(self):
        """
        Gera um relatório de gastos por categoria
        """
        categories = self.db_connection.execute(
            """
            SELECT c.name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            GROUP BY c.name
            ORDER BY total_spent DESC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not categories:
            QMessageBox.information(self, "Informação", "Não há dados de categorias para o período selecionado.")
            return

        report_dialog = QDialog(self)
        report_dialog.setWindowTitle(f"Relatório de Gastos por Categoria - {self.selected_year}")
        report_dialog.setMinimumSize(500, 400)
        report_layout = QVBoxLayout()

        # Título
        title_label = QLabel(f"Relatório de Gastos por Categoria - {self.selected_year}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignCenter)
        report_layout.addWidget(title_label)

        # Tabela de relatório
        report_table = QTableWidget(report_dialog)
        report_table.setColumnCount(3)
        report_table.setHorizontalHeaderLabels(["Categoria", "Total Gasto", "Porcentagem"])

        report_table.setAlternatingRowColors(True)
        report_table.setEditTriggers(QTableWidget.NoEditTriggers)
        report_table.setSelectionBehavior(QTableWidget.SelectRows)
        report_table.horizontalHeader().setStretchLastSection(True)

        # Calcular total geral
        total_amount = sum(category[1] for category in categories)

        # Preencher tabela
        report_table.setRowCount(len(categories))
        for i, category in enumerate(categories):
            name_item = QTableWidgetItem(category[0])
            amount_item = QTableWidgetItem(f"R$ {category[1]:.2f}")

            # Calcular porcentagem
            percentage = (category[1] / total_amount * 100) if total_amount > 0 else 0
            percentage_item = QTableWidgetItem(f"{percentage:.2f}%")

            report_table.setItem(i, 0, name_item)
            report_table.setItem(i, 1, amount_item)
            report_table.setItem(i, 2, percentage_item)

        report_layout.addWidget(report_table)

        # Botão de fechar
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(report_dialog.accept)

        report_layout.addWidget(close_button, 0, Qt.AlignCenter)

        report_dialog.setLayout(report_layout)

        # Aplicar tema
        if self.is_dark_mode:
            report_dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                }
                QPushButton {
                    background-color: #3498db;
                    color: #ecf0f1;
                    padding: 8px 15px;
                    border-radius: 4px;
                }
            """)

        report_dialog.exec_()

    def generate_category_graph(self):
        """
        Gera um gráfico de gastos por categoria
        """
        categories = self.db_connection.execute(
            """
            SELECT c.name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            GROUP BY c.name
            ORDER BY total_spent DESC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not categories:
            QMessageBox.information(self, "Informação", "Não há dados de categorias para o período selecionado.")
            return

        # Limitar a 10 categorias para melhor visualização
        if len(categories) > 10:
            top_categories = categories[:9]
            # Agrupar o restante como "Outros"
            others_total = sum(category[1] for category in categories[9:])
            categories = top_categories + [("Outros", others_total)]

        category_names = [category[0] for category in categories]
        total_spent = [category[1] for category in categories]

        # Configurar o gráfico
        plt.figure(figsize=(10, 6))

        # Configurar o estilo baseado no tema
        if self.is_dark_mode:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        # Gráfico de barras
        bars = plt.bar(category_names, total_spent, color='#4CAF50')

        # Adicionar valores acima das barras
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'R${height:.2f}', ha='center', va='bottom', rotation=0)

        plt.xlabel("Categoria")
        plt.ylabel("Total Gasto (R$)")
        plt.title(f"Gastos por Categoria - {self.selected_year}")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        # Adicionar grade para facilitar leitura
        plt.grid(axis='y', linestyle='--', alpha=0.7)

        plt.show()

    def show_budget_dialog(self):
        """Mostra o diálogo de orçamento mensal"""
        dialog = BudgetDialog(self)
        dialog.exec_()

    def show_cashflow_dialog(self):
        """Mostra o diálogo de projeção de fluxo de caixa"""
        dialog = CashFlowDialog(self)
        dialog.exec_()

    def show_calendar_dialog(self):
        """Mostra o diálogo de calendário financeiro"""
        dialog = CalendarDialog(self)
        dialog.exec_()

    def show_trends_dialog(self):
        """Mostra o diálogo de análise de tendências"""
        dialog = TrendsDialog(self)
        dialog.exec_()

    def show_savings_goals(self):
        """Mostra o gerenciador de metas de economia e metas de categorias"""
        # Criar diálogo
        goals_dialog = QDialog(self)
        goals_dialog.setWindowTitle("Gerenciador de Metas")
        goals_dialog.resize(750, 500)

        # Layout
        layout = QVBoxLayout()

        # Criar tabs para separar tipos de metas
        tabs = QTabWidget()

        # Tab para metas de economia
        savings_tab = QWidget()
        savings_layout = QVBoxLayout(savings_tab)

        # Tab para metas de categorias
        categories_tab = QWidget()
        categories_layout = QVBoxLayout(categories_tab)

        # -------- Tab de Metas de Economia --------

        # Título
        savings_title = QLabel("Minhas Metas de Economia")
        savings_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        savings_layout.addWidget(savings_title)

        # Carregar metas de economia
        goals = self.db_connection.execute(
            '''
            SELECT id, name, target_amount, current_amount,
                (current_amount / target_amount * 100) as progress
            FROM savings_goals
            WHERE user_id = ?
            ORDER BY deadline IS NULL, deadline, progress DESC
            ''',
            (self.user_id,)
        ).fetchall()

        # Tabela de metas de economia
        savings_table = QTableWidget()
        savings_table.setColumnCount(5)
        savings_table.setHorizontalHeaderLabels(["Nome", "Meta (R$)", "Atual (R$)", "Progresso", "Ações"])
        savings_table.horizontalHeader().setStretchLastSection(True)
        savings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        savings_table.setSelectionBehavior(QTableWidget.SelectRows)

        # Preencher tabela de metas de economia
        savings_table.setRowCount(len(goals))
        for i, goal in enumerate(goals):
            name_item = QTableWidgetItem(goal['name'])
            target_item = QTableWidgetItem(f"R$ {goal['target_amount']:.2f}")
            current_item = QTableWidgetItem(f"R$ {goal['current_amount']:.2f}")

            # Criar barra de progresso
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_bar = QProgressBar()
            progress_bar.setMaximum(100)
            progress_value = int(goal['progress'])
            progress_bar.setValue(progress_value)
            progress_bar.setFormat(f"{progress_value}%")
            progress_layout.addWidget(progress_bar)
            progress_layout.setContentsMargins(4, 4, 4, 4)

            # Botões de ação
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)

            edit_button = QPushButton("✏️")
            edit_button.setToolTip("Editar Meta")
            edit_button.clicked.connect(lambda _, goal_id=goal['id']: self.edit_savings_goal(goal_id))

            delete_button = QPushButton("🗑️")
            delete_button.setToolTip("Excluir Meta")
            delete_button.clicked.connect(lambda _, goal_id=goal['id']: self.delete_savings_goal(goal_id, savings_table))

            action_layout.addWidget(edit_button)
            action_layout.addWidget(delete_button)
            action_layout.setContentsMargins(2, 2, 2, 2)

            # Adicionar itens à tabela
            savings_table.setItem(i, 0, name_item)
            savings_table.setItem(i, 1, target_item)
            savings_table.setItem(i, 2, current_item)
            savings_table.setCellWidget(i, 3, progress_widget)
            savings_table.setCellWidget(i, 4, action_widget)

        savings_layout.addWidget(savings_table)

        # Botão para adicionar nova meta de economia
        add_savings_button = QPushButton("Nova Meta de Economia")
        add_savings_button.clicked.connect(self.add_savings_goal)
        savings_layout.addWidget(add_savings_button)

        # -------- Tab de Metas de Categorias --------

        # Título
        categories_title = QLabel("Metas de Categorias")
        categories_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        categories_layout.addWidget(categories_title)

        # Verificar se a coluna is_savings_goal existe
        column_exists = self.db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('categories') WHERE name='is_savings_goal'"
        ).fetchone()[0] > 0

        # Buscar categorias com metas
        if column_exists:
            categories_with_goals = self.db_connection.execute(
                '''
                SELECT id, name, total_amount, is_payment_goal, is_savings_goal
                FROM categories
                WHERE user_id = ? AND (is_payment_goal = 1 OR is_savings_goal = 1)
                ORDER BY name
                ''',
                (self.user_id,)
            ).fetchall()
        else:
            # Versão compatível com banco de dados anterior
            categories_with_goals = self.db_connection.execute(
                '''
                SELECT id, name, total_amount, is_payment_goal, 0 as is_savings_goal
                FROM categories
                WHERE user_id = ? AND is_payment_goal = 1
                ORDER BY name
                ''',
                (self.user_id,)
            ).fetchall()

        # Tabela de metas de categorias
        categories_table = QTableWidget()
        categories_table.setColumnCount(6)
        categories_table.setHorizontalHeaderLabels(["Nome", "Tipo", "Meta (R$)", "Atual (R$)", "Progresso", "Ações"])
        categories_table.horizontalHeader().setStretchLastSection(True)
        categories_table.setEditTriggers(QTableWidget.NoEditTriggers)
        categories_table.setSelectionBehavior(QTableWidget.SelectRows)

        # Preencher tabela de metas de categorias
        categories_table.setRowCount(len(categories_with_goals))
        for i, category in enumerate(categories_with_goals):
            name_item = QTableWidgetItem(category['name'])

            if category['is_payment_goal'] == 1:
                type_item = QTableWidgetItem("Meta de Quitação 🎯")
                # Para metas de quitação, somar transações de saída
                amount_accumulated = self.db_connection.execute(
                    "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'",
                    (self.user_id, category['id'])
                ).fetchone()[0] or 0
            elif column_exists and category['is_savings_goal'] == 1:
                type_item = QTableWidgetItem("Meta de Guardar Dinheiro 💰")
                # Para metas de guardar dinheiro, somar transações de entrada
                amount_accumulated = self.db_connection.execute(
                    "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'entrada'",
                    (self.user_id, category['id'])
                ).fetchone()[0] or 0
            else:
                # Caso inesperado, tratar como meta de quitação
                type_item = QTableWidgetItem("Meta de Quitação 🎯")
                amount_accumulated = self.db_connection.execute(
                    "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'",
                    (self.user_id, category['id'])
                ).fetchone()[0] or 0

            target_item = QTableWidgetItem(f"R$ {category['total_amount']:.2f}")
            current_item = QTableWidgetItem(f"R$ {amount_accumulated:.2f}")

            # Calcular progresso
            progress_value = 0
            if category['total_amount'] > 0:
                progress_value = min(100, int((amount_accumulated / category['total_amount']) * 100))

            # Criar barra de progresso
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_bar = QProgressBar()
            progress_bar.setMaximum(100)
            progress_bar.setValue(progress_value)
            progress_bar.setFormat(f"{progress_value}%")
            progress_layout.addWidget(progress_bar)
            progress_layout.setContentsMargins(4, 4, 4, 4)

            # Botões de ação
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)

            edit_button = QPushButton("✏️")
            edit_button.setToolTip("Editar Categoria")
            edit_button.clicked.connect(lambda _, cat_id=category['id']: self.show_edit_category_dialog_and_refresh(cat_id, categories_table))

            action_layout.addWidget(edit_button)
            action_layout.setContentsMargins(2, 2, 2, 2)

            # Adicionar itens à tabela
            categories_table.setItem(i, 0, name_item)
            categories_table.setItem(i, 1, type_item)
            categories_table.setItem(i, 2, target_item)
            categories_table.setItem(i, 3, current_item)
            categories_table.setCellWidget(i, 4, progress_widget)
            categories_table.setCellWidget(i, 5, action_widget)

        categories_layout.addWidget(categories_table)

        # Botão para adicionar nova categoria com meta
        add_category_button = QPushButton("Nova Categoria com Meta")
        add_category_button.clicked.connect(lambda: self.show_add_category_dialog_and_refresh(categories_table))
        categories_layout.addWidget(add_category_button)

        # Adicionar tabs ao layout
        tabs.addTab(savings_tab, "Metas de Economia")
        tabs.addTab(categories_tab, "Metas de Categorias")

        layout.addWidget(tabs)

        # Botão para fechar
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(goals_dialog.accept)
        layout.addWidget(close_button, 0, Qt.AlignRight)

        goals_dialog.setLayout(layout)

        # Aplicar tema
        if self.is_dark_mode:
            goals_dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                }
                QPushButton {
                    background-color: #3498db;
                    color: #ecf0f1;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    text-align: center;
                    background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71;
                    width: 10px;
                    margin: 0.5px;
                }
                QTabWidget::pane {
                    border: 1px solid #4b6584;
                    background-color: #1e272e;
                }
                QTabBar::tab {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    padding: 8px 12px;
                    border: 1px solid #4b6584;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #3498db;
                }
            """)

        goals_dialog.exec_()

    def show_add_category_dialog_and_refresh(self, table):
        """Abre o diálogo para adicionar categoria e atualiza a tabela de metas"""
        dialog = AddCategoryDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_categories()
            self.show_savings_goals()  # Recarregar a tela de metas

    def show_edit_category_dialog_and_refresh(self, category_id, table):
        """Abre o diálogo para editar categoria e atualiza a tabela de metas"""
        dialog = EditCategoryDialog(self, category_id)
        if dialog.exec_() == QDialog.Accepted:
            self.load_categories()
            self.show_savings_goals()  # Recarregar a tela de metas

    def add_savings_goal(self):
        """Adiciona uma nova meta de economia"""
        dialog = SavingsGoalDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.show_savings_goals()  # Recarregar a lista

    def edit_savings_goal(self, goal_id):
        """Edita uma meta de economia existente"""
        dialog = SavingsGoalDialog(self, goal_id)
        if dialog.exec_() == QDialog.Accepted:
            self.show_savings_goals()  # Recarregar a lista

    def delete_savings_goal(self, goal_id, table):
        """Exclui uma meta de economia"""
        # Confirmar exclusão
        reply = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            "Tem certeza que deseja excluir esta meta de economia?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Excluir a meta
            self.db_connection.execute(
                "DELETE FROM savings_goals WHERE id = ? AND user_id = ?",
                (goal_id, self.user_id)
            )
            self.db_connection.commit()

            # Recarregar a lista
            self.show_savings_goals()

    def logout(self):
        """
        Realiza o logout do usuário
        """
        # Salvar configurações do usuário
        self.save_user_preferences()

        if self.db_connection:
            self.db_connection.close()

        self.user_id = None

        # Limpar o layout do dashboard e voltar para o layout de login
        self.clear_layout(self.main_layout)

        self.login_layout = self.create_login_layout()
        self.main_layout.addLayout(self.login_layout)

    def clear_layout(self, layout):
        """
        Limpa todos os widgets de um layout
        """
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self.clear_layout(child.layout())


if __name__ == '__main__':
    import sys
    import random

    app = QApplication(sys.argv)

    # Verificar se existe o ícone, caso contrário, criar um padrão
    if not os.path.exists('finance_icon.png'):
        # Criar um ícone temporário básico
        from PyQt5.QtGui import QPainter, QPixmap

        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))  # Transparente

        painter = QPainter(pixmap)
        painter.setPen(QColor(0, 128, 0))  # Verde
        painter.setBrush(QColor(0, 128, 0, 100))  # Verde com transparência

        # Desenhar símbolo de cifrão
        painter.drawEllipse(5, 5, 54, 54)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 40, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "$")

        painter.end()

        # Salvar o ícone
        pixmap.save('finance_icon.png')

    # Iniciar a janela principal
    main_window = MainWindow()

    # Iniciar minimizado
    if hasattr(main_window, 'start_minimized') and main_window.start_minimized:
        main_window.hide()
        main_window.tray_icon.showMessage(
            "Gestão Financeira",
            "Aplicativo iniciado e minimizado na bandeja do sistema.",
            QSystemTrayIcon.Information,
            2000
        )
    else:
        main_window.show()

    sys.exit(app.exec_())

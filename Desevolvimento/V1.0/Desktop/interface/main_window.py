"""
Janela principal do sistema de gestão financeira
Versão Desktop - compatível com conversão futura para mobile
"""
import os
import csv
import sqlite3
import threading
from datetime import datetime, timedelta

import matplotlib.pyplot as plt

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QMessageBox, QComboBox, QDateEdit, QDialog, QGroupBox,
    QTextEdit, QFileDialog, QCheckBox, QSystemTrayIcon,
    QMenu, QAction, QProgressBar, QApplication, QTabWidget,
    QFrame, QScrollArea, QSizePolicy, QSplitter
)
from PyQt5.QtCore import Qt, QDate, QSettings, QTimer
from PyQt5.QtGui import QColor, QPalette, QIcon, QFont

from modulos.database import DBManager, DBUpdater
from interface.dialogs.transaction_dialogs import (
    AddTransactionDialog, EditTransactionDialog
)
from interface.dialogs.note_dialogs import (
    AddNoteDialog, EditNoteDialog
)
from interface.dialogs.category_dialogs import (
    AddCategoryDialog, EditCategoryDialog,
    CategoryTransactionsDialog
)
from interface.dialogs.goal_dialogs import (
    BudgetDialog, SavingsGoalDialog
)
from interface.dialogs.loan_dialogs import LoansManagerDialog
from interface.dialogs.sync_dialog import SyncBridge, SyncDialog
from modulos import sync_core
from modulos.sync_cliente import GerenciadorSync


class ImportExtratoDialog(QDialog):
    """Diálogo para importar extratos bancários em PDF"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Importar Extrato Bancário (PDF)')
        self.setMinimumSize(900, 600)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )
        self.transacoes_extraidas = []
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        """Inicializa a interface"""
        layout = QVBoxLayout()

        header_label = QLabel(
            'Importacao de Extrato Bancario\n\n'
            'Selecione um arquivo PDF. O sistema ira:\n'
            '  Extrair transacoes automaticamente\n'
            '  Verificar duplicatas\n'
            '  Permitir revisar antes de importar'
        )
        header_label.setWordWrap(True)
        header_label.setStyleSheet(
            'padding: 10px; background-color: #e3f2fd;'
            'border-radius: 5px;'
        )
        layout.addWidget(header_label)

        file_layout = QHBoxLayout()
        self.file_label      = QLabel('Nenhum arquivo selecionado')
        self.select_file_btn = QPushButton('Selecionar PDF')
        self.select_file_btn.clicked.connect(self.selecionar_arquivo)
        file_layout.addWidget(QLabel('Arquivo:'))
        file_layout.addWidget(self.file_label, 1)
        file_layout.addWidget(self.select_file_btn)
        layout.addLayout(file_layout)

        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        preview_label = QLabel('Preview das Transacoes:')
        preview_label.setStyleSheet(
            'font-weight: bold; margin-top: 10px;'
        )
        layout.addWidget(preview_label)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(6)
        self.preview_table.setHorizontalHeaderLabels([
            'Sel', 'Data', 'Descricao', 'Tipo', 'Valor', 'Status'
        ])
        self.preview_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.preview_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.preview_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        layout.addWidget(self.preview_table)

        self.stats_label = QLabel('')
        layout.addWidget(self.stats_label)

        cat_layout = QHBoxLayout()
        cat_layout.addWidget(
            QLabel('Categoria padrao para importacao:')
        )
        self.category_combo = QComboBox()
        self.category_combo.addItem('Sem categoria', None)

        if hasattr(self.parent(), 'db_connection'):
            categories = self.parent().db_connection.execute(
                '''SELECT id, name FROM categories
                   WHERE user_id = ? ORDER BY name''',
                (self.parent().user_id,)
            ).fetchall()
            for cat in categories:
                self.category_combo.addItem(cat['name'], cat['id'])

        cat_layout.addWidget(self.category_combo)
        cat_layout.addStretch()
        layout.addLayout(cat_layout)

        button_layout = QHBoxLayout()

        self.select_all_btn = QPushButton('Selecionar Todas')
        self.select_all_btn.clicked.connect(self.selecionar_todas)
        self.select_all_btn.setEnabled(False)

        self.deselect_all_btn = QPushButton('Desmarcar Todas')
        self.deselect_all_btn.clicked.connect(self.desmarcar_todas)
        self.deselect_all_btn.setEnabled(False)

        self.import_btn = QPushButton('Importar Selecionadas')
        self.import_btn.clicked.connect(self.importar_transacoes)
        self.import_btn.setEnabled(False)

        self.cancel_btn = QPushButton('Cancelar')
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.select_all_btn)
        button_layout.addWidget(self.deselect_all_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.import_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def apply_theme(self):
        """Aplica o tema ao dialogo"""
        if self.is_dark_mode:
            self.setStyleSheet('''
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QPushButton {
                    background-color: #3498db; color: #ecf0f1;
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #2980b9; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                }
                QComboBox {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                    padding: 5px;
                }
            ''')
            self.import_btn.setStyleSheet(
                'background-color: #2ecc71; color: #ecf0f1;'
            )
            self.cancel_btn.setStyleSheet(
                'background-color: #e74c3c; color: #ecf0f1;'
            )
        else:
            self.setStyleSheet('''
                QDialog { background-color: #f9f9f9; }
                QLabel { color: #333; }
                QPushButton {
                    background-color: #2196F3; color: white;
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1976D2; }
                QTableWidget { background-color: white; }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc;
                }
            ''')
            self.import_btn.setStyleSheet(
                'background-color: #4CAF50; color: white;'
            )
            self.cancel_btn.setStyleSheet(
                'background-color: #f44336; color: white;'
            )

    def selecionar_arquivo(self):
        """Abre dialogo para selecionar PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Selecionar Extrato Bancario', '',
            'Arquivos PDF (*.pdf)'
        )
        if file_path:
            self.file_label.setText(os.path.basename(file_path))
            self.processar_pdf(file_path)

    def processar_pdf(self, file_path):
        """Processa o PDF e extrai as transacoes"""
        try:
            from modulos.pdf_parser import (
                processar_pdf_extrato, gerar_hash_transacao
            )

            self.status_label.setText('Processando PDF...')
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            QApplication.processEvents()

            with open(file_path, 'rb') as f:
                arquivo_bytes = f.read()

            sucesso, transacoes, mensagem = processar_pdf_extrato(
                arquivo_bytes
            )

            self.progress_bar.setVisible(False)

            if not sucesso:
                self.status_label.setText(f'Erro: {mensagem}')
                self.status_label.setStyleSheet('color: red;')
                return

            self.transacoes_extraidas = transacoes
            self.status_label.setText(f'{mensagem}')
            self.status_label.setStyleSheet('color: green;')

            self.verificar_duplicatas()
            self.mostrar_preview()

        except ImportError:
            QMessageBox.critical(
                self, 'Erro',
                'Modulo pdfplumber nao instalado.\n\n'
                'Instale com: pip install pdfplumber'
            )
        except Exception as e:
            self.status_label.setText(
                f'Erro ao processar: {str(e)}'
            )
            self.status_label.setStyleSheet('color: red;')
            import traceback
            traceback.print_exc()

    def verificar_duplicatas(self):
        """Verifica duplicatas em dois niveis"""
        try:
            from modulos.pdf_parser import (
                gerar_hash_transacao, gerar_hash_fuzzy
            )
        except ImportError:
            return

        transacoes_db = self.parent().db_connection.execute(
            '''SELECT id, transaction_type, amount, date, description
               FROM transactions WHERE user_id = ?''',
            (self.parent().user_id,)
        ).fetchall()

        hashes_exatos = set()
        hashes_fuzzy  = {}

        for t in transacoes_db:
            h_exato = gerar_hash_transacao(
                t['transaction_type'], t['amount'],
                t['date'], t['description']
            )
            hashes_exatos.add(h_exato)
            h_fuzzy = gerar_hash_fuzzy(
                t['transaction_type'], t['amount'], t['date']
            )
            if h_fuzzy not in hashes_fuzzy:
                hashes_fuzzy[h_fuzzy] = t['description']

        for transacao in self.transacoes_extraidas:
            if transacao['hash'] in hashes_exatos:
                transacao['duplicada']           = True
                transacao['duplicata_tipo']      = 'exata'
                transacao['duplicata_descricao'] = None
                continue

            h_fuzzy = gerar_hash_fuzzy(
                transacao['tipo'],
                transacao['valor'],
                transacao['data']
            )

            if h_fuzzy in hashes_fuzzy:
                transacao['duplicada']           = True
                transacao['duplicata_tipo']      = 'fuzzy'
                transacao['duplicata_descricao'] = (
                    hashes_fuzzy[h_fuzzy]
                )
            else:
                transacao['duplicada']           = False
                transacao['duplicata_tipo']      = None
                transacao['duplicata_descricao'] = None

    def mostrar_preview(self):
        """Mostra preview das transacoes na tabela"""
        self.preview_table.setRowCount(
            len(self.transacoes_extraidas)
        )

        novas             = 0
        duplicadas_exatas = 0
        duplicadas_fuzzy  = 0
        genericas         = 0

        for i, trans in enumerate(self.transacoes_extraidas):
            checkbox        = QCheckBox()
            checkbox.setChecked(not trans['duplicada'])
            checkbox_widget = QWidget()
            cb_layout       = QHBoxLayout(checkbox_widget)
            cb_layout.addWidget(checkbox)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.preview_table.setCellWidget(i, 0, checkbox_widget)

            self.preview_table.setItem(
                i, 1, QTableWidgetItem(trans['data'])
            )

            desc_texto = trans['descricao'][:80]
            desc_item  = QTableWidgetItem(desc_texto)

            if 'bloco_original' in trans:
                desc_item.setToolTip(
                    f"Bloco original:\n{trans['bloco_original']}"
                )

            if 'Transacao #' in trans['descricao']:
                desc_item.setBackground(QColor('#FFF3CD'))
                genericas += 1

            self.preview_table.setItem(i, 2, desc_item)

            tipo_item = QTableWidgetItem(trans['tipo'].upper())
            tipo_item.setForeground(
                QColor('green') if trans['tipo'] == 'entrada'
                else QColor('red')
            )
            self.preview_table.setItem(i, 3, tipo_item)
            self.preview_table.setItem(
                i, 4,
                QTableWidgetItem(f"R$ {trans['valor']:,.2f}")
            )

            if not trans['duplicada']:
                status_item = QTableWidgetItem('Nova')
                status_item.setForeground(QColor('green'))
                novas += 1
            elif trans.get('duplicata_tipo') == 'exata':
                status_item = QTableWidgetItem('DUPLICADA')
                status_item.setForeground(QColor('orange'))
                duplicadas_exatas += 1
            elif trans.get('duplicata_tipo') == 'fuzzy':
                status_item = QTableWidgetItem('PROVAVEL DUPLICATA')
                status_item.setForeground(QColor('#FF8C00'))
                duplicadas_fuzzy += 1
            else:
                status_item = QTableWidgetItem('Nova')
                status_item.setForeground(QColor('green'))
                novas += 1

            self.preview_table.setItem(i, 5, status_item)

        self.preview_table.resizeColumnsToContents()

        stats_parts = [
            f"{len(self.transacoes_extraidas)} total",
            f"{novas} novas",
        ]
        if duplicadas_exatas > 0:
            stats_parts.append(
                f"{duplicadas_exatas} duplicatas exatas"
            )
        if duplicadas_fuzzy > 0:
            stats_parts.append(
                f"{duplicadas_fuzzy} provaveis duplicatas"
            )
        if genericas > 0:
            stats_parts.append(
                f"{genericas} descricao generica"
            )

        self.stats_label.setText(' | '.join(stats_parts))

        self.select_all_btn.setEnabled(True)
        self.deselect_all_btn.setEnabled(True)
        self.import_btn.setEnabled(True)

    def selecionar_todas(self):
        """Seleciona todas as transacoes"""
        for i in range(self.preview_table.rowCount()):
            w  = self.preview_table.cellWidget(i, 0)
            cb = w.findChild(QCheckBox)
            if cb:
                cb.setChecked(True)

    def desmarcar_todas(self):
        """Desmarca todas as transacoes"""
        for i in range(self.preview_table.rowCount()):
            w  = self.preview_table.cellWidget(i, 0)
            cb = w.findChild(QCheckBox)
            if cb:
                cb.setChecked(False)

    def importar_transacoes(self):
        """Importa as transacoes selecionadas"""
        transacoes_selecionadas = []
        for i in range(self.preview_table.rowCount()):
            w  = self.preview_table.cellWidget(i, 0)
            cb = w.findChild(QCheckBox)
            if cb and cb.isChecked():
                transacoes_selecionadas.append(
                    self.transacoes_extraidas[i]
                )

        if not transacoes_selecionadas:
            QMessageBox.warning(
                self, 'Aviso',
                'Selecione pelo menos uma transacao para importar.'
            )
            return

        reply = QMessageBox.question(
            self, 'Confirmar Importacao',
            f'Deseja importar {len(transacoes_selecionadas)} '
            f'transacao(oes)?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        category_id  = self.category_combo.currentData()
        importadas   = 0
        erros        = 0

        try:
            for trans in transacoes_selecionadas:
                try:
                    self.parent().db_connection.execute(
                        '''INSERT INTO transactions
                           (user_id, amount, description,
                            transaction_type, date, category_id)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (
                            self.parent().user_id,
                            trans['valor'],
                            trans['descricao'],
                            trans['tipo'],
                            trans['data'],
                            category_id
                        )
                    )
                    importadas += 1
                except Exception as e:
                    print(f'Erro ao importar: {e}')
                    erros += 1

            self.parent().db_connection.commit()

            # ── NOVO: Aplicar regras de categoria automaticamente ──
            categorizadas = 0
            try:
                from interface.dialogs.category_dialogs import (
                    apply_category_rules
                )
                categorizadas = apply_category_rules(
                    self.parent().db_connection,
                    self.parent().user_id
                )
                if categorizadas > 0:
                    self.parent().db_connection.commit()
                    print(
                        f'[Importacao] {categorizadas} transacao(oes)'
                        f' categorizadas automaticamente.'
                    )
            except Exception as e:
                print(f'[Importacao] Erro ao aplicar regras: {e}')

            self.parent().load_transactions()
            self.parent().update_balance()
            self.parent().update_year_buttons()

            # ── Montar mensagem final com info de categorização ──
            msg = (
                f'{importadas} transacao(oes) importada(s)!\n'
            )
            if categorizadas > 0:
                msg += (
                    f'✅ {categorizadas} transacao(oes) '
                    f'categorizadas automaticamente!\n'
                )
            if erros > 0:
                msg += f'⚠️ {erros} erro(s) durante importacao.'

            QMessageBox.information(
                self, 'Importacao Concluida', msg
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao importar transacoes: {str(e)}'
            )


# ══════════════════════════════════════════════════════════════
# JANELA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Janela principal do sistema"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle('RRFS Finanças')
        self.setGeometry(100, 100, 1100, 750)

        self.settings     = QSettings('FinanceApp', 'FinanceTracker')
        self.is_dark_mode = self.settings.value(
            'dark_mode', False, type=bool
        )

        if not os.path.exists('dados'):
            os.makedirs('dados')

        self.db_connection  = None
        self.user_id        = None
        self.selected_year  = datetime.now().year
        self.start_minimized = True

        self._setup_icon()
        self._setup_tray()
        self._setup_widgets()
        self._setup_connections()

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.apply_theme()
        self.setMinimizeToTray()

        # Sem tela de login: abre direto o banco local (offline-first)
        self._abrir_local()

    # ══════════════════════════════════════════════════════
    # SETUP INICIAL
    # ══════════════════════════════════════════════════════

    def _setup_icon(self):
        """Configura o icone da aplicacao"""
        self.app_icon = QIcon('finance_icon.png')
        self.setWindowIcon(self.app_icon)

    def _setup_tray(self):
        """Configura o icone da bandeja do sistema"""
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip('Gestao Financeira Pessoal')

        tray_menu = QMenu()

        show_action = QAction('Abrir', self)
        show_action.triggered.connect(self.show)

        hide_action = QAction('Minimizar', self)
        hide_action.triggered.connect(self.hide)

        exit_action = QAction('Sair', self)
        exit_action.triggered.connect(self.close_application)

        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def _setup_widgets(self):
        """Inicializa todos os widgets"""
        # Login
        self.username_label    = QLabel('Usuario:')
        self.username_input    = QLineEdit()
        self.password_label    = QLabel('Senha:')
        self.password_input    = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.login_button      = QPushButton('Login')
        self.register_button   = QPushButton('Registrar')
        self.save_login_button = QPushButton('Salvar Login')

        # Transacoes
        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(6)
        self.transactions_table.setHorizontalHeaderLabels([
            'ID', 'Data', 'Descricao', 'Valor', 'Tipo', 'Categoria'
        ])
        self.transactions_table.setAlternatingRowColors(True)
        self.transactions_table.setSortingEnabled(True)
        self.transactions_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.transactions_table.verticalHeader().setVisible(False)
        self.transactions_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.transactions_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.add_transaction_button    = QPushButton('Adicionar')
        self.edit_transaction_button   = QPushButton('Editar')
        self.delete_transaction_button = QPushButton('Excluir')

        # Notas
        self.notes_table = QTableWidget()
        self.notes_table.setColumnCount(2)
        self.notes_table.setHorizontalHeaderLabels(['ID', 'Nota'])
        self.notes_table.horizontalHeader().setStretchLastSection(True)
        self.notes_table.verticalHeader().setVisible(False)
        self.notes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.notes_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.add_note_button    = QPushButton('Adicionar')
        self.edit_note_button   = QPushButton('Editar')
        self.delete_note_button = QPushButton('Excluir')

        # Categorias
        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(3)
        self.categories_table.setHorizontalHeaderLabels([
            'ID', 'Nome', 'Acao'
        ])
        self.categories_table.horizontalHeader().setStretchLastSection(
            True
        )
        self.categories_table.verticalHeader().setVisible(False)
        self.categories_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.categories_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.add_category_button    = QPushButton('Adicionar')
        self.edit_category_button   = QPushButton('Editar')
        self.delete_category_button = QPushButton('Excluir')

        # Saldo
        self.balance_label = QLabel('Saldo: R$ 0.00')

        # Busca
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            'Pesquisar... '
            '(ex: "entrada", "saida", descricao, categoria, valor)'
        )
        self.search_input.textChanged.connect(self.load_transactions)

        # Filtro rapido de tipo
        self.type_filter_combo = QComboBox()
        self.type_filter_combo.addItems(['Todos', 'Entrada', 'Saida'])
        self.type_filter_combo.currentIndexChanged.connect(
            self.load_transactions
        )

        self.year_buttons_layout = QHBoxLayout()

        # Botoes de controle
        self.logout_button = QPushButton('Servidor / Sincronização')
        self.logout_button.clicked.connect(self.show_sync_dialog)

        self.dark_mode_button = QPushButton(
            'Modo Escuro: Ativado'
            if self.is_dark_mode
            else 'Modo Claro'
        )
        self.dark_mode_button.clicked.connect(self.toggle_dark_mode)

        # Ferramentas
        self.budget_button = QPushButton('Orcamento')
        self.budget_button.clicked.connect(self.show_budget_dialog)

        self.cashflow_button = QPushButton('Fluxo de Caixa')
        self.cashflow_button.clicked.connect(
            self.show_cashflow_dialog
        )

        self.calendar_button = QPushButton('Calendario')
        self.calendar_button.clicked.connect(
            self.show_calendar_dialog
        )

        self.trends_button = QPushButton('Tendencias')
        self.trends_button.clicked.connect(self.show_trends_dialog)

        self.savings_goals_button = QPushButton('Metas')
        self.savings_goals_button.clicked.connect(
            self.show_savings_goals
        )

        self.import_extrato_button = QPushButton('Importar PDF')
        self.import_extrato_button.clicked.connect(
            self.show_import_extrato_dialog
        )

        self.loans_button = QPushButton('Emprestimos')
        self.loans_button.clicked.connect(self.show_loans_dialog)

        # Botao de cotacoes
        self.currency_button = QPushButton('Cotacoes')
        self.currency_button.clicked.connect(
            self.show_currency_dialog
        )
        self.currency_button.setStyleSheet(
            'background-color: #16a085; color: white;'
            'font-weight: bold; padding: 6px 12px;'
            'border-radius: 4px;'
        )

        # ── Botao de Inflacao ──────────────────────────────────
        self.inflation_button = QPushButton('📊 Inflacao')
        self.inflation_button.clicked.connect(
            self.show_inflation_dialog
        )
        self.inflation_button.setStyleSheet(
            'background-color: #2980b9; color: white;'
            'font-weight: bold; padding: 6px 12px;'
            'border-radius: 4px;'
        )

        # ── Botao de doacao ────────────────────────────────────
        self.donate_button = QPushButton('☕ Cafe')
        self.donate_button.setToolTip(
            'Me pague um cafe! Ajude a manter o projeto.'
        )
        self.donate_button.setFixedHeight(32)
        self.donate_button.setStyleSheet(
            'background-color: transparent; '
            'color: #f39c12; '
            'border: 1px solid #f39c12; '
            'border-radius: 4px; '
            'font-size: 14px; '
            'font-weight: bold; '
            'padding: 4px 10px;'
        )
        self.donate_button.clicked.connect(self.show_donate_dialog)

    def _setup_connections(self):
        """Configura as conexoes de sinais"""
        self.login_button.clicked.connect(self.login)
        self.register_button.clicked.connect(self.register)
        self.add_transaction_button.clicked.connect(
            self.show_add_transaction_dialog
        )
        self.edit_transaction_button.clicked.connect(
            self.show_edit_transaction_dialog
        )
        self.delete_transaction_button.clicked.connect(
            self.delete_transaction
        )
        self.add_note_button.clicked.connect(
            self.show_add_note_dialog
        )
        self.edit_note_button.clicked.connect(
            self.show_edit_note_dialog
        )
        self.delete_note_button.clicked.connect(self.delete_note)
        self.add_category_button.clicked.connect(
            self.show_add_category_dialog
        )
        self.edit_category_button.clicked.connect(
            self.show_edit_category_dialog
        )
        self.delete_category_button.clicked.connect(
            self.delete_category
        )
        self.save_login_button.clicked.connect(self.save_login)

    # ══════════════════════════════════════════════════════
    # INICIALIZACAO DE MODULOS (Cotacoes / Inflacao)
    # ══════════════════════════════════════════════════════

    def _init_currency(self):
        """Inicializa o sistema de cotacoes em background."""
        try:
            from modulos.currency_tracker import create_currency_tables
            create_currency_tables(self.db_connection)

            t = threading.Thread(
                target=self._fetch_currency_history_background,
                daemon=True
            )
            t.start()

        except Exception as e:
            print(f'[Currency] Erro ao inicializar: {e}')

    def _fetch_currency_history_background(self):
        """Baixa historico de cotacoes em background."""
        try:
            import sqlite3 as sq
            import os

            db_path = None
            dados_dir = 'dados'
            if os.path.exists(dados_dir):
                for fname in os.listdir(dados_dir):
                    if fname.endswith('.db'):
                        test_path = os.path.join(dados_dir, fname)
                        test_conn = sq.connect(test_path)
                        test_conn.row_factory = sq.Row
                        try:
                            user = test_conn.execute(
                                'SELECT id FROM users WHERE id = ?',
                                (self.user_id,)
                            ).fetchone()
                            if user:
                                db_path = test_path
                                test_conn.close()
                                break
                        except Exception:
                            pass
                        test_conn.close()

            if not db_path:
                return

            thread_conn = sq.connect(db_path)
            thread_conn.row_factory = sq.Row

            from modulos.currency_tracker import (
                create_currency_tables,
                fetch_history_since,
                fetch_and_save_latest,
                CURRENCY_PAIRS
            )
            create_currency_tables(thread_conn)

            first = thread_conn.execute(
                '''SELECT MIN(date) as first_date
                   FROM transactions WHERE user_id = ?''',
                (self.user_id,)
            ).fetchone()

            if first and first['first_date']:
                since_date = first['first_date']
                print(
                    f'[Currency] Baixando historico desde '
                    f'{since_date}...'
                )
                # USD e EUR normalmente
                for pair in ['USDBRL', 'EURBRL']:
                    fetch_history_since(
                        thread_conn, pair, since_date
                    )

                # BTC via conversao USD
                from interface.dialogs.currency_dialog import (
                    _fetch_btc_history_via_usd,
                    _get_btc_brl_via_usd
                )
                _fetch_btc_history_via_usd(
                    thread_conn, since_date
                )

            # Atualizar cotacao de hoje
            for pair in ['USDBRL', 'EURBRL']:
                fetch_and_save_latest(thread_conn, pair)

            from interface.dialogs.currency_dialog import (
                _get_btc_brl_via_usd
            )
            _get_btc_brl_via_usd(thread_conn)

            thread_conn.close()
            print('[Currency] Historico de cotacoes atualizado.')

        except Exception as e:
            print(f'[Currency] Erro no background: {e}')
            import traceback
            traceback.print_exc()

    def _init_inflation(self):
        """Inicializa tabelas de inflacao em background."""
        try:
            from modulos.inflation_tracker import (
                create_inflation_tables
            )
            create_inflation_tables(self.db_connection)
            print('[Inflation] Tabelas de inflacao inicializadas.')
        except Exception as e:
            print(f'[Inflation] Erro ao inicializar: {e}')

    def show_currency_dialog(self):
        """Abre o dialogo de cotacoes e analise cambial"""
        try:
            from interface.dialogs.currency_dialog import (
                CurrencyDialog
            )
            dialog = CurrencyDialog(self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir cotacoes:\n{str(e)}'
            )

    def show_inflation_dialog(self):
        """Abre o dialogo de analise de inflacao"""
        try:
            from interface.dialogs.inflation_dialog import (
                InflationDialog
            )
            dialog = InflationDialog(self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir Inflacao:\n{str(e)}'
            )

    # ══════════════════════════════════════════════════════
    # TEMA
    # ══════════════════════════════════════════════════════

    def toggle_dark_mode(self):
        """Alterna entre modo claro e escuro"""
        self.is_dark_mode = not self.is_dark_mode
        self.dark_mode_button.setText(
            'Modo Escuro: Ativado'
            if self.is_dark_mode
            else 'Modo Claro'
        )
        self.apply_theme()
        self.settings.setValue('dark_mode', self.is_dark_mode)

    def apply_theme(self):
        """Aplica o tema a aplicacao"""
        if self.is_dark_mode:
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(
                QPalette.AlternateBase, QColor(53, 53, 53)
            )
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(
                QPalette.Highlight, QColor(42, 130, 218)
            )
            palette.setColor(QPalette.HighlightedText, Qt.black)
            self.setPalette(palette)
            self.setStyleSheet('''
                QMainWindow, QDialog {
                    background-color: #1e272e; color: #ecf0f1;
                }
                QLabel { color: #ecf0f1; }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #3498db; color: white;
                    border: none; border-radius: 4px;
                    padding: 6px 12px; font-weight: bold;
                }
                QPushButton:hover { background-color: #2980b9; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                    selection-background-color: #3498db;
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
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected { background-color: #3498db; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QCheckBox { color: #ecf0f1; }
                QScrollBar:vertical {
                    background: #2d3436; width: 10px;
                }
                QScrollBar::handle:vertical {
                    background: #4b6584; border-radius: 5px;
                }
            ''')
        else:
            self.setPalette(QPalette())
            self.setStyleSheet('''
                QMainWindow, QDialog {
                    background-color: #f5f6fa; color: #333333;
                }
                QLabel { color: #333333; }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: white; color: #333333;
                    border: 1px solid #dcdde1; border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #4CAF50; color: white;
                    border: none; border-radius: 4px;
                    padding: 6px 12px; font-weight: bold;
                }
                QPushButton:hover { background-color: #45a049; }
                QTableWidget {
                    background-color: white; color: #333333;
                    gridline-color: #dcdde1;
                    selection-background-color: #e8f4fd;
                    alternate-background-color: #f8f9fa;
                }
                QHeaderView::section {
                    background-color: #f0f0f0; color: #333333;
                    padding: 5px; border: 1px solid #dcdde1;
                    font-weight: bold;
                }
                QTabWidget::pane {
                    border: 1px solid #dcdde1;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333333;
                    padding: 8px 12px; border: 1px solid #dcdde1;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #4CAF50; color: white;
                }
                QGroupBox {
                    border: 1px solid #dcdde1; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                    background-color: white;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QScrollBar:vertical {
                    background: #f0f0f0; width: 10px;
                }
                QScrollBar::handle:vertical {
                    background: #bdc3c7; border-radius: 5px;
                }
            ''')

    # ══════════════════════════════════════════════════════
    # TRAY
    # ══════════════════════════════════════════════════════

    def closeEvent(self, event):
        """Controla o comportamento ao fechar"""
        if self.minimizeToTray:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                'Gestao Financeira',
                'Aplicativo minimizado para a bandeja.',
                QSystemTrayIcon.Information, 2000
            )
        else:
            self.settings.setValue('dark_mode', self.is_dark_mode)
            if hasattr(self, 'transactions_table'):
                self.save_table_state()
            if hasattr(self, 'sync'):
                self.sync.parar_sync()
            if self.db_connection:
                self.db_connection.close()
            event.accept()

    def tray_icon_activated(self, reason):
        """Gerencia eventos do icone da bandeja"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()

    def close_application(self):
        """Fecha a aplicacao completamente"""
        self.minimizeToTray = False
        self.close()
        QApplication.quit()

    def setMinimizeToTray(self):
        """Define se minimiza para a bandeja"""
        self.minimizeToTray = True

    # ══════════════════════════════════════════════════════
    # LOGIN
    # ══════════════════════════════════════════════════════

    def create_login_layout(self):
        """Cria o layout da tela de login"""
        login_layout = QVBoxLayout()

        login_container = QWidget()
        login_container.setMaximumWidth(400)
        container_layout = QVBoxLayout(login_container)

        title_label = QLabel(
        f'RRFS Finanças  —  {self.username_input.text()}'
        )
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)

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

        login_layout.addStretch(1)
        login_layout.addWidget(login_container, 0, Qt.AlignCenter)
        login_layout.addStretch(1)

        return login_layout

    def _abrir_local(self):
        """Abre o banco local direto, sem senha, e liga a sincronizacao."""
        username = 'local'
        db_path  = self.get_db_path(username)

        self.db_connection = sqlite3.connect(db_path, timeout=30)
        self.db_connection.row_factory = sqlite3.Row
        try:
            self.db_connection.execute('PRAGMA journal_mode=WAL')
        except Exception:
            pass

        db_manager            = DBManager(username)
        db_manager.connection = self.db_connection
        db_manager.create_tables()

        if not DBUpdater.check_and_update(self.db_connection, username):
            QMessageBox.critical(
                self, 'Erro',
                'Nao foi possivel atualizar o banco de dados.'
            )
            return
        self._force_db_update()

        user = self.db_connection.execute(
            'SELECT * FROM users ORDER BY id LIMIT 1'
        ).fetchone()
        if not user:
            self.db_connection.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, '-')
            )
            self.db_connection.commit()
            user = self.db_connection.execute(
                'SELECT * FROM users ORDER BY id LIMIT 1'
            ).fetchone()
        self.user_id = user['id']

        # triggers que registram toda mudanca para sincronizar
        sync_core.preparar(self.db_connection)

        self.sync_bridge = SyncBridge(self)
        self.sync = GerenciadorSync(
            os.getcwd(), db_path,
            ao_alterar=self.sync_bridge.alterado.emit,
            ao_estado=self.sync_bridge.estado.emit
        )
        self.sync_bridge.alterado.connect(self._sync_agendar_refresh)
        self.sync_bridge.estado.connect(self._sync_atualizar_label)
        self.sync_label = QLabel('⚪ Modo local')
        self._sync_refresh_pendente = False
        self.username_input.setText(self.sync.config.get('conta', ''))

        self._check_new_year()
        self.clear_layout(self.main_layout)
        self.load_dashboard()
        self.load_user_preferences()
        self.restore_table_state()

        self.sync.iniciar()
        self._sync_atualizar_label()
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_atualizar_label)
        self._sync_timer.start(5000)

    # ── Sincronizacao com o servidor ─────────────────────

    def show_sync_dialog(self):
        """Pareamento, status e sincronizacao manual"""
        SyncDialog(self, self.sync).exec_()
        self._sync_atualizar_label()

    def _sync_atualizar_label(self):
        try:
            e = self.sync.estado()
        except Exception:
            return
        if not e['pareado']:
            txt = '⚪ Modo local'
        elif not e['aprovado']:
            txt = '🟡 Aguardando aprovacao no servidor'
        elif not e['servidor_online']:
            txt = (f"🟠 Offline · {e['pendentes']} pendente(s)"
                   if e['pendentes'] else '🟠 Offline')
        elif e['pendentes']:
            txt = f"🔄 Sincronizando… ({e['pendentes']})"
        else:
            txt = '🟢 Sincronizado'
        self.sync_label.setText(txt)

    def _sync_agendar_refresh(self):
        """Chegaram dados do servidor: atualiza as telas (com debounce)"""
        if self._sync_refresh_pendente:
            return
        self._sync_refresh_pendente = True
        QTimer.singleShot(600, self._sync_refrescar)

    def _sync_refrescar(self):
        self._sync_refresh_pendente = False
        if self.db_connection is None or self.user_id is None:
            return
        try:
            self.load_transactions()
            self.load_categories()
            self.update_balance()
            self.update_year_buttons()
        except Exception as e:
            print(f'[sync] Erro ao atualizar telas: {e}')

    def get_db_path(self, username):
        """Retorna o caminho para o banco de dados"""
        return os.path.join('dados', f'{username}.db')

    def login(self):
        """Realiza o login do usuario"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(
                self, 'Erro',
                'Por favor, preencha todos os campos.'
            )
            return

        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        db_manager            = DBManager(username)
        db_manager.connection = self.db_connection
        db_manager.create_tables()

        if not DBUpdater.check_and_update(
            self.db_connection, username
        ):
            QMessageBox.critical(
                self, 'Erro',
                'Nao foi possivel atualizar o banco de dados.'
            )
            self.db_connection.close()
            return

        self._force_db_update()

        user = self.db_connection.execute(
            'SELECT * FROM users WHERE username = ? AND password = ?',
            (username, password)
        ).fetchone()

        if user:
            self.user_id = user['id']
            self._check_new_year()
            self.clear_layout(self.main_layout)
            self.load_dashboard()
            self.load_user_preferences()
            self.restore_table_state()
        else:
            QMessageBox.warning(
                self, 'Erro', 'Usuario ou senha incorretos.'
            )
            self.db_connection.close()

    def _force_db_update(self):
        """Forca atualizacao do banco de dados"""
        try:
            columns_to_check = [
                ('categories', 'is_savings_goal',
                 'INTEGER DEFAULT 0'),
                ('categories', 'is_hidden',
                 'INTEGER DEFAULT 0'),
                ('categories', 'year',
                 f'INTEGER DEFAULT {datetime.now().year}'),
                ('transactions', 'savings_category_id',
                 'INTEGER'),
                ('transactions', 'is_saving_transaction',
                 'INTEGER DEFAULT 0'),
            ]
            for table, column, col_type in columns_to_check:
                exists = self.db_connection.execute(
                    f"SELECT COUNT(*) FROM pragma_table_info('{table}')"
                    f" WHERE name='{column}'"
                ).fetchone()[0] > 0
                if not exists:
                    self.db_connection.execute(
                        f'ALTER TABLE {table} ADD COLUMN '
                        f'{column} {col_type}'
                    )
            self.db_connection.commit()
            return True
        except Exception as e:
            print(f'Erro ao atualizar BD: {e}')
            return False

    def _check_new_year(self):
        """Verifica se e um novo ano e oculta categorias antigas"""
        try:
            last_year    = self.settings.value(
                'last_year_check', None
            )
            current_year = datetime.now().year

            if last_year is None or int(last_year) < current_year:
                col_exists = self.db_connection.execute(
                    "SELECT COUNT(*) FROM pragma_table_info"
                    "('categories') WHERE name='year'"
                ).fetchone()[0] > 0

                if col_exists:
                    self.db_connection.execute(
                        'UPDATE categories SET is_hidden = 1 '
                        'WHERE user_id = ? AND year < ?',
                        (self.user_id, current_year)
                    )
                    self.db_connection.commit()

                self.settings.setValue(
                    'last_year_check', current_year
                )

                if last_year is not None:
                    QMessageBox.information(
                        self, 'Novo Ano',
                        f'Bem-vindo a {current_year}! '
                        f'As categorias do ano anterior '
                        f'foram ocultadas.'
                    )
        except Exception as e:
            print(f'Erro ao verificar novo ano: {e}')

    def register(self):
        """Registra um novo usuario"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(
                self, 'Erro',
                'Por favor, preencha todos os campos.'
            )
            return

        db_path = self.get_db_path(username)
        conn    = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        db_manager            = DBManager(username)
        db_manager.connection = conn
        db_manager.create_tables()

        try:
            conn.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, password)
            )
            conn.execute('INSERT INTO db_version VALUES (?)', (5,))
            conn.commit()
            QMessageBox.information(
                self, 'Sucesso',
                'Usuario registrado com sucesso.'
            )
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, 'Erro', 'Nome de usuario ja existe.'
            )
        finally:
            conn.close()

    def save_login(self):
        """Salva as credenciais de login"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(
                self, 'Erro',
                'Por favor, preencha todos os campos.'
            )
            return

        with open('login.txt', 'w') as f:
            f.write(f'{username},{password}')

        QMessageBox.information(
            self, 'Sucesso', 'Login salvo com sucesso.'
        )

    def load_saved_login(self):
        """Carrega as credenciais salvas"""
        if os.path.exists('login.txt'):
            with open('login.txt', 'r') as f:
                try:
                    username, password = f.read().split(',')
                    self.username_input.setText(username)
                    self.password_input.setText(password)
                except Exception:
                    pass

    def load_user_preferences(self):
        """Carrega preferencias do usuario"""
        try:
            theme_setting = self.db_connection.execute(
                '''SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'dark_mode' ''',
                (self.user_id,)
            ).fetchone()

            if theme_setting:
                self.is_dark_mode = (
                    theme_setting['setting_value'].lower() == 'true'
                )
                self.dark_mode_button.setText(
                    'Modo Escuro: Ativado'
                    if self.is_dark_mode else 'Modo Claro'
                )
                self.apply_theme()
        except Exception:
            pass

    def save_user_preferences(self):
        """Salva preferencias do usuario"""
        try:
            existing = self.db_connection.execute(
                '''SELECT id FROM user_settings
                   WHERE user_id = ? AND setting_key = 'dark_mode' ''',
                (self.user_id,)
            ).fetchone()

            if existing:
                self.db_connection.execute(
                    '''UPDATE user_settings SET setting_value = ?
                       WHERE user_id = ?
                       AND setting_key = 'dark_mode' ''',
                    (str(self.is_dark_mode), self.user_id)
                )
            else:
                self.db_connection.execute(
                    '''INSERT INTO user_settings
                       (user_id, setting_key, setting_value)
                       VALUES (?, 'dark_mode', ?)''',
                    (self.user_id, str(self.is_dark_mode))
                )
            self.db_connection.commit()
        except Exception:
            pass

    def logout(self):
        """Realiza o logout"""
        self.save_user_preferences()
        if self.db_connection:
            self.db_connection.close()

        self.user_id = None

        self.clear_layout(self.main_layout)
        self.login_layout = self.create_login_layout()
        self.main_layout.addLayout(self.login_layout)

    def clear_layout(self, layout):
        """Limpa todos os widgets de um layout"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self.clear_layout(child.layout())

    # ══════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════

    def load_dashboard(self):
        """Carrega o dashboard principal"""
        dashboard_layout = QVBoxLayout()

        title_label = QLabel(
            f'Gestao Financeira  {self.username_input.text()}'
        )
        title_label.setStyleSheet(
            'font-size: 17px; font-weight: bold; margin: 8px 0;'
        )
        dashboard_layout.addWidget(title_label)

        top_layout = QHBoxLayout()

        self.balance_label.setStyleSheet(
            'font-size: 14px; font-weight: bold; padding: 8px;'
            'border-radius: 4px; min-width: 300px;'
        )
        top_layout.addWidget(self.balance_label)

        search_container = QWidget()
        search_layout    = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(QLabel('Tipo:'))
        search_layout.addWidget(self.type_filter_combo)
        top_layout.addWidget(search_container, 1)
        dashboard_layout.addLayout(top_layout)

        dashboard_layout.addLayout(self.year_buttons_layout)

        month_filter_layout = QHBoxLayout()
        month_label         = QLabel('Filtrar mes:')
        self.month_combo    = QComboBox()
        self.month_combo.addItem('Todos os meses', 0)
        for month in range(1, 13):
            month_name = QDate(
                2000, month, 1
            ).toString('MMMM').capitalize()
            self.month_combo.addItem(month_name, month)
        self.month_combo.currentIndexChanged.connect(
            self.load_transactions
        )
        month_filter_layout.addWidget(month_label)
        month_filter_layout.addWidget(self.month_combo)
        month_filter_layout.addStretch()
        dashboard_layout.addLayout(month_filter_layout)

        # ── Barra de ferramentas ──────────────────────────────
        tools_layout = QHBoxLayout()
        tools_layout.addWidget(self.budget_button)
        tools_layout.addWidget(self.cashflow_button)
        tools_layout.addWidget(self.calendar_button)
        tools_layout.addWidget(self.trends_button)
        tools_layout.addWidget(self.savings_goals_button)
        tools_layout.addWidget(self.import_extrato_button)
        tools_layout.addWidget(self.loans_button)
        tools_layout.addWidget(self.currency_button)
        tools_layout.addWidget(self.inflation_button)
        dashboard_layout.addLayout(tools_layout)

        # Transacoes
        transactions_group  = QGroupBox('Transacoes')
        transactions_layout = QVBoxLayout()
        transactions_layout.addWidget(self.transactions_table)

        transaction_button_layout = QHBoxLayout()
        transaction_button_layout.addWidget(
            self.add_transaction_button
        )
        transaction_button_layout.addWidget(
            self.edit_transaction_button
        )
        transaction_button_layout.addWidget(
            self.delete_transaction_button
        )
        transaction_button_layout.addStretch()
        transactions_layout.addLayout(transaction_button_layout)
        transactions_group.setLayout(transactions_layout)
        dashboard_layout.addWidget(transactions_group, 3)

        # Categorias + Anotacoes
        bottom_layout = QHBoxLayout()

        self.categories_group  = QGroupBox('Categorias')
        categories_layout      = QVBoxLayout()
        categories_layout.addWidget(self.categories_table)

        category_button_layout = QHBoxLayout()
        category_button_layout.addWidget(self.add_category_button)
        category_button_layout.addWidget(self.edit_category_button)
        category_button_layout.addWidget(
            self.delete_category_button
        )
        category_button_layout.addStretch()
        categories_layout.addLayout(category_button_layout)
        self.categories_group.setLayout(categories_layout)
        self.add_category_options_to_interface()

        notes_group  = QGroupBox('Anotacoes')
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(self.notes_table)

        note_button_layout = QHBoxLayout()
        note_button_layout.addWidget(self.add_note_button)
        note_button_layout.addWidget(self.edit_note_button)
        note_button_layout.addWidget(self.delete_note_button)
        note_button_layout.addStretch()
        notes_layout.addLayout(note_button_layout)
        notes_group.setLayout(notes_layout)

        bottom_layout.addWidget(self.categories_group, 1)
        bottom_layout.addWidget(notes_group, 1)
        dashboard_layout.addLayout(bottom_layout, 2)

        # Relatorios
        report_layout = QHBoxLayout()

        report_button = QPushButton('Relatorio por Categoria')
        report_button.clicked.connect(self.generate_category_report)

        graph_button = QPushButton('Grafico de Categorias')
        graph_button.clicked.connect(self.generate_category_graph)

        export_button = QPushButton('Exportar')
        export_button.clicked.connect(self.export_report)

        report_layout.addWidget(report_button)
        report_layout.addWidget(graph_button)
        report_layout.addWidget(export_button)
        report_layout.addStretch()
        dashboard_layout.addLayout(report_layout)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.dark_mode_button)
        action_layout.addWidget(self.donate_button)
        action_layout.addStretch()
        action_layout.addWidget(self.sync_label)
        action_layout.addWidget(self.logout_button)
        dashboard_layout.addLayout(action_layout)

        self.main_layout.addLayout(dashboard_layout)

        # ── Inicializacoes pos-login ──────────────────────────
        self._init_currency()
        self._init_inflation()

        self.load_transactions()
        self.load_notes()
        self.load_categories()
        self.update_balance()
        self.update_year_buttons()
        self.restore_table_state()

    # ══════════════════════════════════════════════════════
    # DADOS
    # ══════════════════════════════════════════════════════

    def update_year_buttons(self):
        """Atualiza os botoes de ano"""
        while self.year_buttons_layout.count():
            child = self.year_buttons_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        years = self.db_connection.execute(
            '''SELECT DISTINCT strftime('%Y', date) as year
               FROM transactions WHERE user_id = ?
               ORDER BY year DESC''',
            (self.user_id,)
        ).fetchall()

        for year in years:
            year_button = QPushButton(year['year'])
            year_button.setCheckable(True)
            year_button.setChecked(
                year['year'] == str(self.selected_year)
            )
            year_button.toggled.connect(
                lambda checked, y=year['year']:
                self.toggle_year(y, checked)
            )
            self.year_buttons_layout.addWidget(year_button)

    def toggle_year(self, year, checked):
        """Alterna o ano selecionado"""
        if checked:
            self.selected_year = int(year)
            self.load_transactions()
        else:
            any_checked = any(
                self.year_buttons_layout.itemAt(i).widget().isChecked()
                for i in range(self.year_buttons_layout.count())
                if self.year_buttons_layout.itemAt(i).widget()
            )
            if not any_checked:
                self.selected_year = datetime.now().year
                self.load_transactions()

    def load_transactions(self):
        """Carrega transacoes com busca e filtro melhorados"""
        search_text    = self.search_input.text().lower().strip()
        selected_month = (
            self.month_combo.currentData()
            if hasattr(self, 'month_combo') else 0
        )

        type_filter = None
        if hasattr(self, 'type_filter_combo'):
            idx = self.type_filter_combo.currentIndex()
            if idx == 1:
                type_filter = 'entrada'
            elif idx == 2:
                type_filter = 'saida'

        if search_text in ('entrada', 'entradas'):
            type_filter = 'entrada'
            search_text = ''
        elif search_text in (
            'saida', 'saída', 'saidas', 'saídas'
        ):
            type_filter = 'saida'
            search_text = ''

        query  = '''
            SELECT t.*, c.name AS category_name,
                t.is_saving_transaction
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
            AND strftime('%Y', t.date) = ?
        '''
        params = [self.user_id, str(self.selected_year)]

        if selected_month and selected_month > 0:
            query  += " AND strftime('%m', t.date) = ?"
            params.append(f'{selected_month:02d}')

        if type_filter:
            query  += ' AND t.transaction_type = ?'
            params.append(type_filter)

        if search_text:
            query += '''
                AND (
                    LOWER(t.description) LIKE ?
                    OR LOWER(COALESCE(c.name, '')) LIKE ?
                    OR CAST(t.amount AS TEXT) LIKE ?
                    OR t.date LIKE ?
                )
            '''
            params.extend([
                f'%{search_text}%',
                f'%{search_text}%',
                f'%{search_text}%',
                f'%{search_text}%',
            ])

        query += ' ORDER BY t.date DESC, t.id DESC'

        transactions = self.db_connection.execute(
            query, params
        ).fetchall()

        # ── Configurar colunas com larguras mínimas fixas ────────
        self.transactions_table.setColumnCount(6)
        self.transactions_table.setHorizontalHeaderLabels([
            'ID', 'Data', 'Descricao', 'Valor', 'Tipo', 'Categoria'
        ])

        # Desabilitar sorting durante o preenchimento
        self.transactions_table.setSortingEnabled(False)

        self.transactions_table.setRowCount(len(transactions))

        # Definir larguras mínimas para cada coluna
        col_min_widths = [40, 90, 250, 100, 80, 120]
        for col, width in enumerate(col_min_widths):
            self.transactions_table.setColumnWidth(col, width)

        for i, transaction in enumerate(transactions):
            if self.is_dark_mode:
                entry_color  = QColor('#1B5E20')
                exit_color   = QColor('#B71C1C')
                saving_color = QColor('#0D47A1')
            else:
                entry_color  = QColor('#E8F5E9')
                exit_color   = QColor('#FFEBEE')
                saving_color = QColor('#E3F2FD')

            is_saving = (
                'is_saving_transaction' in transaction.keys() and
                transaction['is_saving_transaction'] == 1
            )

            display_type = transaction['transaction_type']
            if is_saving:
                display_type = 'guardar'

            row_color = (
                saving_color if is_saving else
                entry_color
                if transaction['transaction_type'] == 'entrada'
                else exit_color
            )

            items = [
                QTableWidgetItem(str(transaction['id'])),
                QTableWidgetItem(transaction['date']),
                QTableWidgetItem(transaction['description']),
                QTableWidgetItem(
                    f"R$ {transaction['amount']:.2f}"
                ),
                QTableWidgetItem(display_type),
                QTableWidgetItem(
                    transaction['category_name'] or ''
                ),
            ]

            for j, item in enumerate(items):
                # Alinhar colunas específicas ao centro
                if j in (0, 1, 3, 4):
                    item.setTextAlignment(
                        Qt.AlignCenter | Qt.AlignVCenter
                    )
                else:
                    item.setTextAlignment(
                        Qt.AlignLeft | Qt.AlignVCenter
                    )
                item.setBackground(row_color)
                self.transactions_table.setItem(i, j, item)

        # Ajustar coluna de descrição para ocupar o espaço restante
        header = self.transactions_table.horizontalHeader()
        header.setSectionResizeMode(
            0, header.ResizeToContents   # ID
        )
        header.setSectionResizeMode(
            1, header.ResizeToContents   # Data
        )
        header.setSectionResizeMode(
            2, header.Stretch            # Descricao - ocupa resto
        )
        header.setSectionResizeMode(
            3, header.ResizeToContents   # Valor
        )
        header.setSectionResizeMode(
            4, header.ResizeToContents   # Tipo
        )
        header.setSectionResizeMode(
            5, header.ResizeToContents   # Categoria
        )

        # Reabilitar sorting após preenchimento
        self.transactions_table.setSortingEnabled(True)

    def load_notes(self):
        """Carrega as notas do usuario"""
        notes = self.db_connection.execute(
            'SELECT * FROM notes WHERE user_id = ?',
            (self.user_id,)
        ).fetchall()

        self.notes_table.setRowCount(len(notes))
        for i, note in enumerate(notes):
            id_item   = QTableWidgetItem(str(note['id']))
            note_item = QTableWidgetItem(note['note'])
            self.notes_table.setItem(i, 0, id_item)
            self.notes_table.setItem(i, 1, note_item)
        self.notes_table.resizeColumnsToContents()

    def load_categories(self):
        """Carrega as categorias do usuario"""
        show_hidden = self.settings.value(
            'show_hidden_categories', False, type=bool
        )
        show_previous_years = self.settings.value(
            'show_previous_years_categories', False, type=bool
        )
        current_year = datetime.now().year

        loans_table_exists = self.db_connection.execute(
            '''SELECT COUNT(*) FROM sqlite_master
               WHERE type='table' AND name='loans' '''
        ).fetchone()[0] > 0

        loan_category_ids = set()
        if loans_table_exists:
            loans = self.db_connection.execute(
                '''SELECT category_id FROM loans
                   WHERE user_id = ? AND category_id IS NOT NULL''',
                (self.user_id,)
            ).fetchall()
            loan_category_ids = {
                l['category_id'] for l in loans
            }

        query  = 'SELECT * FROM categories WHERE user_id = ?'
        params = [self.user_id]

        if not show_hidden:
            query += ' AND (is_hidden = 0 OR is_hidden IS NULL)'

        if not show_previous_years:
            query += ' AND (year = ? OR year IS NULL)'
            params.append(current_year)

        query += ' ORDER BY name'

        all_categories = self.db_connection.execute(
            query, params
        ).fetchall()

        categories = [
            c for c in all_categories
            if c['id'] not in loan_category_ids
        ]

        self.categories_table.setRowCount(len(categories))

        for i, category in enumerate(categories):
            id_item   = QTableWidgetItem(str(category['id']))
            name_item = QTableWidgetItem(category['name'])

            if category['is_payment_goal'] == 1:
                color = (
                    QColor('#01579B') if self.is_dark_mode
                    else QColor('#E8F5FE')
                )
                id_item.setBackground(color)
                name_item.setBackground(color)
                name_item.setText(f"{category['name']} [Meta]")

            elif (
                'is_savings_goal' in category.keys() and
                category['is_savings_goal'] == 1
            ):
                color = (
                    QColor('#1B5E20') if self.is_dark_mode
                    else QColor('#E8FFF0')
                )
                id_item.setBackground(color)
                name_item.setBackground(color)
                name_item.setText(
                    f"{category['name']} [Poupanca]"
                )

            if (
                'is_hidden' in category.keys() and
                category['is_hidden'] == 1
            ):
                name_item.setText(
                    f"{name_item.text()} [Oculta]"
                )

            if (
                'year' in category.keys() and
                category['year'] is not None and
                category['year'] < current_year
            ):
                name_item.setText(
                    f"{name_item.text()} ({category['year']})"
                )

            self.categories_table.setItem(i, 0, id_item)
            self.categories_table.setItem(i, 1, name_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)

            view_button = QPushButton('Ver')
            view_button.setToolTip('Ver Transacoes')
            view_button.setMaximumWidth(50)
            view_button.clicked.connect(
                lambda _, cid=category['id'],
                cname=category['name']:
                self.show_category_transactions(cid, cname)
            )
            action_layout.addWidget(view_button)
            self.categories_table.setCellWidget(
                i, 2, action_widget
            )

        self.categories_table.resizeColumnsToContents()

    def update_balance(self):
        """Atualiza o saldo total"""
        transactions = self.db_connection.execute(
            'SELECT * FROM transactions WHERE user_id = ?',
            (self.user_id,)
        ).fetchall()

        saving_col = self.db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('transactions')"
            " WHERE name='is_saving_transaction'"
        ).fetchone()[0] > 0

        if saving_col:
            entries_total = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada' and
                (t['is_saving_transaction'] != 1 or
                 t['is_saving_transaction'] is None)
            )
        else:
            entries_total = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )

        exits_total = sum(
            t['amount'] for t in transactions
            if t['transaction_type'] == 'saida'
        )
        balance = entries_total - exits_total

        savings_col = self.db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('categories')"
            " WHERE name='is_savings_goal'"
        ).fetchone()[0] > 0

        total_savings = 0
        if savings_col:
            savings_cats = self.db_connection.execute(
                '''SELECT id, name, total_amount FROM categories
                   WHERE user_id = ? AND is_savings_goal = 1''',
                (self.user_id,)
            ).fetchall()

            for cat in savings_cats:
                amount_saved = self.db_connection.execute(
                    '''SELECT SUM(amount) FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'entrada' ''',
                    (self.user_id, cat['id'])
                ).fetchone()[0] or 0
                total_savings += amount_saved

                if (
                    amount_saved >= cat['total_amount'] and
                    cat['total_amount'] > 0
                ):
                    self.tray_icon.showMessage(
                        'Meta Alcancada!',
                        f"Meta '{cat['name']}' atingida!",
                        QSystemTrayIcon.Information, 5000
                    )

        available_balance = balance - total_savings
        balance_text      = f'Saldo: R$ {balance:.2f}'

        if total_savings > 0:
            balance_text += (
                f' | Guardado: R$ {total_savings:.2f}'
            )
            balance_text += (
                f' | Disponivel: R$ {available_balance:.2f}'
            )

        if self.is_dark_mode:
            color = (
                '#4CAF50' if available_balance >= 0
                else '#F44336'
            )
            self.balance_label.setStyleSheet(
                f'font-size: 14px; font-weight: bold; '
                f'color: {color};'
                f'background-color: #263238; padding: 8px;'
                f'border-radius: 4px;'
            )
        else:
            if available_balance >= 0:
                self.balance_label.setStyleSheet(
                    'font-size: 14px; font-weight: bold;'
                    'color: #2e7d32; background-color: #e8f5e9;'
                    'padding: 8px; border-radius: 4px;'
                )
            else:
                self.balance_label.setStyleSheet(
                    'font-size: 14px; font-weight: bold;'
                    'color: #c62828; background-color: #ffebee;'
                    'padding: 8px; border-radius: 4px;'
                )

        self.balance_label.setText(balance_text)

    # ══════════════════════════════════════════════════════
    # TRANSACOES
    # ══════════════════════════════════════════════════════

    def show_add_transaction_dialog(self):
        """Mostra dialogo para adicionar transacao"""
        dialog = AddTransactionDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_transactions()
            self.update_balance()
            self.update_year_buttons()

    def show_edit_transaction_dialog(self):
        """Mostra dialogo para editar transacao"""
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(
                self.transactions_table.item(
                    selected_row, 0
                ).text()
            )
            dialog = EditTransactionDialog(self, transaction_id)
            if dialog.exec_() == QDialog.Accepted:
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()
        else:
            QMessageBox.warning(
                self, 'Aviso',
                'Selecione uma transacao para editar.'
            )

    def delete_transaction(self):
        """Exclui a transacao selecionada"""
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(
                self.transactions_table.item(
                    selected_row, 0
                ).text()
            )
            reply = QMessageBox.question(
                self, 'Confirmar Exclusao',
                'Tem certeza que deseja excluir esta transacao?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.db_connection.execute(
                    'DELETE FROM transactions WHERE id = ?',
                    (transaction_id,)
                )
                self.db_connection.commit()
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()
        else:
            QMessageBox.warning(
                self, 'Aviso',
                'Selecione uma transacao para excluir.'
            )

    # ══════════════════════════════════════════════════════
    # NOTAS
    # ══════════════════════════════════════════════════════

    def show_add_note_dialog(self):
        """Mostra dialogo para adicionar nota"""
        dialog = AddNoteDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_notes()

    def show_edit_note_dialog(self):
        """Mostra dialogo para editar nota"""
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(
                self.notes_table.item(selected_row, 0).text()
            )
            dialog = EditNoteDialog(self, note_id)
            if dialog.exec_() == QDialog.Accepted:
                self.load_notes()
        else:
            QMessageBox.warning(
                self, 'Aviso',
                'Selecione uma nota para editar.'
            )

    def delete_note(self):
        """Exclui a nota selecionada"""
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(
                self.notes_table.item(selected_row, 0).text()
            )
            reply = QMessageBox.question(
                self, 'Confirmar Exclusao',
                'Tem certeza que deseja excluir esta nota?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.db_connection.execute(
                    'DELETE FROM notes WHERE id = ?', (note_id,)
                )
                self.db_connection.commit()
                self.load_notes()
        else:
            QMessageBox.warning(
                self, 'Aviso',
                'Selecione uma nota para excluir.'
            )

    # ══════════════════════════════════════════════════════
    # CATEGORIAS
    # ══════════════════════════════════════════════════════

    def show_add_category_dialog(self):
        """Mostra dialogo para adicionar categoria"""
        dialog = AddCategoryDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_categories()

    def show_edit_category_dialog(self):
        """Mostra dialogo para editar categoria"""
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(
                self.categories_table.item(
                    selected_row, 0
                ).text()
            )
            dialog = EditCategoryDialog(self, category_id)
            if dialog.exec_() == QDialog.Accepted:
                self.load_categories()
        else:
            QMessageBox.warning(
                self, 'Aviso',
                'Selecione uma categoria para editar.'
            )

    def delete_category(self):
        """Exclui a categoria selecionada"""
        selected_row = self.categories_table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(
                self, 'Aviso',
                'Selecione uma categoria para excluir.'
            )
            return

        category_id   = int(
            self.categories_table.item(selected_row, 0).text()
        )
        category_name = self.categories_table.item(
            selected_row, 1
        ).text()

        count = self.db_connection.execute(
            '''SELECT COUNT(*) FROM transactions
               WHERE category_id = ? AND user_id = ?''',
            (category_id, self.user_id)
        ).fetchone()[0]

        if count > 0:
            reply = QMessageBox.question(
                self, 'Categoria com Transacoes',
                f"A categoria '{category_name}' possui {count} "
                f"transacao(oes).\n\n"
                f'Deseja desvincular as transacoes e excluir?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.db_connection.execute(
                    '''UPDATE transactions SET category_id = NULL
                       WHERE category_id = ? AND user_id = ?''',
                    (category_id, self.user_id)
                )
                self.db_connection.commit()
            else:
                return

        loans_table_exists = self.db_connection.execute(
            '''SELECT COUNT(*) FROM sqlite_master
               WHERE type='table' AND name='loans' '''
        ).fetchone()[0] > 0

        if loans_table_exists:
            is_loan_cat = self.db_connection.execute(
                '''SELECT COUNT(*) FROM loans
                   WHERE category_id = ? AND user_id = ?''',
                (category_id, self.user_id)
            ).fetchone()[0] > 0

            if is_loan_cat:
                QMessageBox.warning(
                    self, 'Categoria de Emprestimo',
                    'Esta categoria pertence a um emprestimo e '
                    'nao pode ser excluida diretamente.\n\n'
                    'Acesse o modulo de Emprestimos para excluir.'
                )
                return

        reply = QMessageBox.question(
            self, 'Confirmar Exclusao',
            f"Excluir a categoria '{category_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                rules_table_exists = self.db_connection.execute(
                    '''SELECT COUNT(*) FROM sqlite_master
                       WHERE type='table'
                       AND name='category_rules' '''
                ).fetchone()[0] > 0

                if rules_table_exists:
                    self.db_connection.execute(
                        '''DELETE FROM category_rules
                           WHERE category_id = ? AND user_id = ?''',
                        (category_id, self.user_id)
                    )

                self.db_connection.execute(
                    '''DELETE FROM categories
                       WHERE id = ? AND user_id = ?''',
                    (category_id, self.user_id)
                )
                self.db_connection.commit()
                self.load_categories()
                self.load_transactions()

            except Exception as e:
                QMessageBox.critical(
                    self, 'Erro',
                    f'Nao foi possivel excluir: {str(e)}'
                )

    def add_category_options_to_interface(self):
        """Adiciona opcoes para mostrar/ocultar categorias"""
        options_widget = QWidget()
        options_layout = QHBoxLayout(options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)

        self.show_hidden_check = QCheckBox(
            'Mostrar Categorias Ocultas'
        )
        self.show_hidden_check.setChecked(
            self.settings.value(
                'show_hidden_categories', False, type=bool
            )
        )
        self.show_hidden_check.stateChanged.connect(
            self.toggle_hidden_categories
        )

        self.show_previous_years_check = QCheckBox(
            'Anos Anteriores'
        )
        self.show_previous_years_check.setChecked(
            self.settings.value(
                'show_previous_years_categories',
                False, type=bool
            )
        )
        self.show_previous_years_check.stateChanged.connect(
            self.toggle_previous_years_categories
        )

        options_layout.addWidget(self.show_hidden_check)
        options_layout.addWidget(self.show_previous_years_check)

        categories_layout = self.categories_group.layout()
        categories_layout.insertWidget(0, options_widget)

    def toggle_hidden_categories(self, state):
        """Alterna visibilidade de categorias ocultas"""
        self.settings.setValue(
            'show_hidden_categories', state == Qt.Checked
        )
        self.load_categories()

    def toggle_previous_years_categories(self, state):
        """Alterna visibilidade de categorias de anos anteriores"""
        self.settings.setValue(
            'show_previous_years_categories',
            state == Qt.Checked
        )
        self.load_categories()

    def show_category_transactions(
        self, category_id, category_name
    ):
        """Mostra transacoes de uma categoria especifica"""
        dialog = CategoryTransactionsDialog(
            self, category_id, category_name
        )
        dialog.exec_()
        self.load_transactions()
        self.update_balance()

    # ══════════════════════════════════════════════════════
    # METAS
    # ══════════════════════════════════════════════════════

    def show_savings_goals(self):
        """Mostra o gerenciador de metas"""
        goals_dialog = QDialog(self)
        goals_dialog.setWindowTitle('Gerenciador de Metas')
        goals_dialog.resize(750, 500)

        layout = QVBoxLayout()
        tabs   = QTabWidget()

        savings_tab    = QWidget()
        savings_layout = QVBoxLayout(savings_tab)

        savings_title = QLabel('Minhas Metas de Economia')
        savings_title.setStyleSheet(
            'font-size: 16px; font-weight: bold;'
        )
        savings_layout.addWidget(savings_title)

        goals = self.db_connection.execute(
            '''SELECT id, name, target_amount, current_amount,
                      (current_amount / target_amount * 100)
                      as progress
               FROM savings_goals WHERE user_id = ?
               ORDER BY deadline IS NULL, deadline,
               progress DESC''',
            (self.user_id,)
        ).fetchall()

        savings_table = QTableWidget()
        savings_table.setColumnCount(5)
        savings_table.setHorizontalHeaderLabels([
            'Nome', 'Meta (R$)', 'Atual (R$)',
            'Progresso', 'Acoes'
        ])
        savings_table.horizontalHeader().setStretchLastSection(True)
        savings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        savings_table.verticalHeader().setVisible(False)
        savings_table.setRowCount(len(goals))

        for i, goal in enumerate(goals):
            savings_table.setItem(
                i, 0, QTableWidgetItem(goal['name'])
            )
            savings_table.setItem(
                i, 1,
                QTableWidgetItem(
                    f"R$ {goal['target_amount']:.2f}"
                )
            )
            savings_table.setItem(
                i, 2,
                QTableWidgetItem(
                    f"R$ {goal['current_amount']:.2f}"
                )
            )

            progress_widget = QWidget()
            p_layout        = QHBoxLayout(progress_widget)
            p_bar           = QProgressBar()
            p_bar.setMaximum(100)
            p_bar.setValue(int(goal['progress'] or 0))
            p_bar.setFormat(f"{int(goal['progress'] or 0)}%")
            p_layout.addWidget(p_bar)
            p_layout.setContentsMargins(4, 4, 4, 4)
            savings_table.setCellWidget(i, 3, progress_widget)

            action_widget = QWidget()
            a_layout      = QHBoxLayout(action_widget)
            edit_btn      = QPushButton('Editar')
            edit_btn.clicked.connect(
                lambda _, gid=goal['id']:
                self.edit_savings_goal(gid)
            )
            del_btn = QPushButton('Excluir')
            del_btn.clicked.connect(
                lambda _, gid=goal['id']:
                self.delete_savings_goal(gid)
            )
            a_layout.addWidget(edit_btn)
            a_layout.addWidget(del_btn)
            a_layout.setContentsMargins(2, 2, 2, 2)
            savings_table.setCellWidget(i, 4, action_widget)

        savings_layout.addWidget(savings_table)

        add_savings_btn = QPushButton('Nova Meta de Economia')
        add_savings_btn.clicked.connect(self.add_savings_goal)
        savings_layout.addWidget(add_savings_btn)

        tabs.addTab(savings_tab, 'Metas de Economia')

        close_button = QPushButton('Fechar')
        close_button.clicked.connect(goals_dialog.accept)

        layout.addWidget(tabs)
        layout.addWidget(close_button, 0, Qt.AlignRight)
        goals_dialog.setLayout(layout)

        if self.is_dark_mode:
            goals_dialog.setStyleSheet('''
                QDialog {
                    background-color: #1e272e; color: #ecf0f1;
                }
                QLabel { color: #ecf0f1; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                }
                QPushButton {
                    background-color: #3498db; color: #ecf0f1;
                    padding: 6px 12px; border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #4b6584;
                    border-radius: 5px; text-align: center;
                    background-color: #2d3436;
                }
                QProgressBar::chunk { background-color: #2ecc71; }
                QTabBar::tab {
                    background-color: #2d3436; color: #ecf0f1;
                    padding: 8px 12px;
                }
                QTabBar::tab:selected {
                    background-color: #3498db;
                }
            ''')

        goals_dialog.exec_()

    def add_savings_goal(self):
        """Adiciona uma nova meta de economia"""
        dialog = SavingsGoalDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.show_savings_goals()

    def edit_savings_goal(self, goal_id):
        """Edita uma meta de economia"""
        dialog = SavingsGoalDialog(self, goal_id)
        if dialog.exec_() == QDialog.Accepted:
            self.show_savings_goals()

    def delete_savings_goal(self, goal_id):
        """Exclui uma meta de economia"""
        reply = QMessageBox.question(
            self, 'Confirmar Exclusao',
            'Tem certeza que deseja excluir esta meta?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.db_connection.execute(
                '''DELETE FROM savings_goals
                   WHERE id = ? AND user_id = ?''',
                (goal_id, self.user_id)
            )
            self.db_connection.commit()
            self.show_savings_goals()

    # ══════════════════════════════════════════════════════
    # FERRAMENTAS E RELATORIOS
    # ══════════════════════════════════════════════════════

    def show_budget_dialog(self):
        """Mostra o dialogo de orcamento"""
        BudgetDialog(self).exec_()

    def show_cashflow_dialog(self):
        """Mostra o fluxo de caixa"""
        try:
            from interface.dialogs.cashflow_dialog import (
                CashFlowDialog
            )
            CashFlowDialog(self).exec_()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir Fluxo de Caixa:\n{str(e)}'
            )

    def show_calendar_dialog(self):
        """Mostra o calendario financeiro"""
        try:
            from interface.dialogs.report_dialogs import (
                CalendarDialog
            )
            CalendarDialog(self).exec_()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir Calendario:\n{str(e)}'
            )

    def show_trends_dialog(self):
        """Mostra analise de tendencias"""
        try:
            from interface.dialogs.trends_dialog import TrendsDialog
            TrendsDialog(self).exec_()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir Tendencias:\n{str(e)}'
            )

    def show_import_extrato_dialog(self):
        """Mostra o dialogo de importacao de extrato"""
        try:
            ImportExtratoDialog(self).exec_()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir importacao:\n{str(e)}\n\n'
                'Verifique se pdfplumber esta instalado:\n'
                'pip install pdfplumber'
            )

    def show_loans_dialog(self):
        """Mostra o gerenciador de emprestimos"""
        try:
            from modulos.loans import create_loans_tables
            create_loans_tables(self.db_connection)
            LoansManagerDialog(self).exec_()
            self.load_categories()
            self.load_transactions()
            self.update_balance()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir Emprestimos:\n{str(e)}'
            )

    def show_donate_dialog(self):
        """Abre o dialogo de doacao - Me pague um cafe"""
        try:
            from interface.dialogs.donate_dialog import DonateDialog
            dialog = DonateDialog(self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(
                self, 'Erro',
                f'Erro ao abrir dialogo de doacao:\n{str(e)}'
            )

    def generate_category_report(self):
        """Gera relatorio de gastos por categoria"""
        categories = self.db_connection.execute(
            '''SELECT c.name, SUM(t.amount) AS total_spent
               FROM transactions t
               JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ?
               AND strftime('%Y', t.date) = ?
               GROUP BY c.name ORDER BY total_spent DESC''',
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not categories:
            QMessageBox.information(
                self, 'Informacao',
                'Nao ha dados de categorias para o '
                'periodo selecionado.'
            )
            return

        report_dialog = QDialog(self)
        report_dialog.setWindowTitle(
            f'Relatorio por Categoria  {self.selected_year}'
        )
        report_dialog.setMinimumSize(500, 400)
        report_layout = QVBoxLayout()

        title_label = QLabel(
            f'Relatorio por Categoria  {self.selected_year}'
        )
        title_label.setStyleSheet(
            'font-size: 16px; font-weight: bold; '
            'margin-bottom: 10px;'
        )
        title_label.setAlignment(Qt.AlignCenter)
        report_layout.addWidget(title_label)

        report_table = QTableWidget(report_dialog)
        report_table.setColumnCount(3)
        report_table.setHorizontalHeaderLabels([
            'Categoria', 'Total Gasto', 'Porcentagem'
        ])
        report_table.setAlternatingRowColors(True)
        report_table.setEditTriggers(QTableWidget.NoEditTriggers)
        report_table.horizontalHeader().setStretchLastSection(True)
        report_table.verticalHeader().setVisible(False)

        total_amount = sum(c[1] for c in categories)
        report_table.setRowCount(len(categories))

        for i, category in enumerate(categories):
            percentage = (
                category[1] / total_amount * 100
                if total_amount > 0 else 0
            )
            report_table.setItem(
                i, 0, QTableWidgetItem(category[0])
            )
            report_table.setItem(
                i, 1,
                QTableWidgetItem(f'R$ {category[1]:.2f}')
            )
            report_table.setItem(
                i, 2,
                QTableWidgetItem(f'{percentage:.2f}%')
            )

        report_layout.addWidget(report_table)

        close_button = QPushButton('Fechar')
        close_button.clicked.connect(report_dialog.accept)
        report_layout.addWidget(close_button, 0, Qt.AlignCenter)
        report_dialog.setLayout(report_layout)

        if self.is_dark_mode:
            report_dialog.setStyleSheet('''
                QDialog {
                    background-color: #1e272e; color: #ecf0f1;
                }
                QLabel { color: #ecf0f1; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                }
                QPushButton {
                    background-color: #3498db; color: #ecf0f1;
                    padding: 8px 15px; border-radius: 4px;
                }
            ''')

        report_dialog.exec_()

    def generate_category_graph(self):
        """Gera grafico de gastos por categoria"""
        categories = self.db_connection.execute(
            '''SELECT c.name, SUM(t.amount) AS total_spent
               FROM transactions t
               JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ?
               AND strftime('%Y', t.date) = ?
               GROUP BY c.name ORDER BY total_spent DESC''',
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not categories:
            QMessageBox.information(
                self, 'Informacao',
                'Nao ha dados de categorias para o '
                'periodo selecionado.'
            )
            return

        if len(categories) > 10:
            top          = list(categories[:9])
            others_total = sum(c[1] for c in categories[9:])
            categories   = top + [('Outros', others_total)]

        names  = [c[0] for c in categories]
        values = [c[1] for c in categories]

        fig, ax = plt.subplots(figsize=(10, 6))

        if self.is_dark_mode:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        bars = ax.bar(
            names, values, color='#4CAF50', alpha=0.8
        )

        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width()/2., height + 0.1,
                f'R${height:.2f}', ha='center', va='bottom',
                fontsize=8
            )

        ax.set_xlabel('Categoria')
        ax.set_ylabel('Total Gasto (R$)')
        ax.set_title(
            f'Gastos por Categoria  {self.selected_year}'
        )
        plt.xticks(rotation=45, ha='right')
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        fig.tight_layout()
        plt.show()

    def export_report(self):
        """Exporta relatorio financeiro"""
        transactions = self.db_connection.execute(
            '''SELECT t.*, c.name AS category_name
               FROM transactions t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ?
               AND strftime('%Y', t.date) = ?
               ORDER BY t.date ASC''',
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not transactions:
            QMessageBox.information(
                self, 'Informacao',
                'Nao ha transacoes para exportar no '
                'periodo selecionado.'
            )
            return

        format_dialog  = QDialog(self)
        format_dialog.setWindowTitle('Escolher Formato')
        format_dialog.setFixedSize(400, 150)

        layout      = QVBoxLayout()
        title_label = QLabel('Escolha o formato de exportacao:')
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        buttons_layout = QHBoxLayout()
        txt_button     = QPushButton('Texto (.txt)')
        txt_button.clicked.connect(lambda: format_dialog.done(1))

        csv_button = QPushButton('Excel (.csv)')
        csv_button.clicked.connect(lambda: format_dialog.done(2))

        cancel_button = QPushButton('Cancelar')
        cancel_button.clicked.connect(format_dialog.reject)

        buttons_layout.addWidget(txt_button)
        buttons_layout.addWidget(csv_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)
        format_dialog.setLayout(layout)

        result = format_dialog.exec_()
        if result == 0:
            return

        ext         = 'txt' if result == 1 else 'csv'
        file_filter = (
            'Arquivos de Texto (*.txt)'
            if result == 1 else 'Arquivos CSV (*.csv)'
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Salvar Relatorio',
            f'relatorio_{self.selected_year}.{ext}',
            file_filter
        )

        if not file_path:
            return

        try:
            if result == 1:
                self._export_txt(file_path, transactions)
            else:
                self._export_csv(file_path, transactions)

            QMessageBox.information(
                self, 'Sucesso',
                f'Relatorio exportado!\nArquivo: {file_path}'
            )
        except Exception as e:
            QMessageBox.warning(
                self, 'Erro',
                f'Nao foi possivel exportar.\nErro: {str(e)}'
            )

    def _export_txt(self, file_path, transactions):
        """Exporta relatorio em formato TXT"""
        lines = [
            f'RELATORIO DE TRANSACOES  Ano: {self.selected_year}',
            '=' * 60,
            'ID | Data | Descricao | Valor | Tipo | Categoria',
            '-' * 60
        ]

        for t in transactions:
            lines.append(
                f"{t['id']} | {t['date']} | "
                f"{t['description']} | "
                f"R$ {t['amount']:.2f} | "
                f"{t['transaction_type']} | "
                f"{t['category_name'] or ''}"
            )

        all_trans = self.db_connection.execute(
            'SELECT * FROM transactions WHERE user_id = ?',
            (self.user_id,)
        ).fetchall()

        entries = sum(
            t['amount'] for t in all_trans
            if t['transaction_type'] == 'entrada'
        )
        exits = sum(
            t['amount'] for t in all_trans
            if t['transaction_type'] == 'saida'
        )

        lines += [
            '=' * 60,
            f'Total Entradas: R$ {entries:.2f}',
            f'Total Saidas:   R$ {exits:.2f}',
            f'Saldo Total:    R$ {entries - exits:.2f}'
        ]

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def _export_csv(self, file_path, transactions):
        """Exporta relatorio em formato CSV"""
        with open(
            file_path, 'w', newline='', encoding='utf-8-sig'
        ) as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                f'RELATORIO DE TRANSACOES  '
                f'Ano: {self.selected_year}'
            ])
            writer.writerow([])
            writer.writerow([
                'ID', 'Data', 'Descricao', 'Valor (R$)',
                'Tipo', 'Categoria'
            ])

            for t in transactions:
                writer.writerow([
                    t['id'], t['date'], t['description'],
                    f"{t['amount']:.2f}".replace('.', ','),
                    t['transaction_type'],
                    t['category_name'] or ''
                ])

            all_trans = self.db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?',
                (self.user_id,)
            ).fetchall()

            entries = sum(
                t['amount'] for t in all_trans
                if t['transaction_type'] == 'entrada'
            )
            exits = sum(
                t['amount'] for t in all_trans
                if t['transaction_type'] == 'saida'
            )

            writer.writerow([])
            writer.writerow(['RESUMO GERAL'])
            writer.writerow([
                'Total Entradas (R$)',
                f"{entries:.2f}".replace('.', ',')
            ])
            writer.writerow([
                'Total Saidas (R$)',
                f"{exits:.2f}".replace('.', ',')
            ])
            writer.writerow([
                'Saldo Total (R$)',
                f"{entries - exits:.2f}".replace('.', ',')
            ])

    # ══════════════════════════════════════════════════════
    # ESTADO DAS TABELAS
    # ══════════════════════════════════════════════════════

    def save_table_state(self):
        """Salva o estado das tabelas"""
        self.settings.setValue(
            'transactions_table_state',
            self.transactions_table.horizontalHeader().saveState()
        )
        self.settings.setValue(
            'categories_table_state',
            self.categories_table.horizontalHeader().saveState()
        )
        self.settings.setValue(
            'notes_table_state',
            self.notes_table.horizontalHeader().saveState()
        )

    def restore_table_state(self):
        """Restaura o estado das tabelas"""
        trans_state = self.settings.value(
            'transactions_table_state'
        )
        if trans_state:
            self.transactions_table.horizontalHeader(
            ).restoreState(trans_state)

        cat_state = self.settings.value('categories_table_state')
        if cat_state:
            self.categories_table.horizontalHeader(
            ).restoreState(cat_state)

        notes_state = self.settings.value('notes_table_state')
        if notes_state:
            self.notes_table.horizontalHeader(
            ).restoreState(notes_state)

"""
Janela principal do sistema de gestão financeira
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
    QMenu, QAction, QProgressBar, QApplication, QTabWidget
)
from PyQt5.QtCore import Qt, QDate, QSettings, QTimer
from PyQt5.QtGui import QColor, QPalette, QIcon

from modulos.database import DBManager, DBUpdater
from interface.dialogs.transaction_dialogs import (
    AddTransactionDialog, EditTransactionDialog
)
from interface.dialogs.note_dialogs import AddNoteDialog, EditNoteDialog
from interface.dialogs.category_dialogs import (
    AddCategoryDialog, EditCategoryDialog
)
from interface.dialogs.goal_dialogs import BudgetDialog, SavingsGoalDialog
from interface.dialogs.report_dialogs import (
    CalendarDialog, CashFlowDialog, TrendsDialog
)
from interface.dialogs.ai_dialogs import ApiConfigDialog
from interface.dialogs.loan_dialogs import LoansManagerDialog


class ImportExtratoDialog(QDialog):
    """Diálogo para importar extratos bancários em PDF"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importar Extrato Bancário (PDF)")
        self.setMinimumSize(900, 600)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )
        self.transacoes_extraidas = []

        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        """Inicializa a interface"""
        layout = QVBoxLayout()

        header_label = QLabel(
            "📄 Importação de Extrato Bancário\n\n"
            "Selecione um arquivo PDF. O sistema irá:\n"
            "• Extrair transações automaticamente\n"
            "• Verificar duplicatas\n"
            "• Permitir revisar antes de importar"
        )
        header_label.setWordWrap(True)
        header_label.setStyleSheet(
            "padding: 10px; background-color: #e3f2fd; border-radius: 5px;"
        )
        layout.addWidget(header_label)

        file_layout = QHBoxLayout()
        self.file_label = QLabel("Nenhum arquivo selecionado")
        self.select_file_btn = QPushButton("📁 Selecionar PDF")
        self.select_file_btn.clicked.connect(self.selecionar_arquivo)
        file_layout.addWidget(QLabel("Arquivo:"))
        file_layout.addWidget(self.file_label, 1)
        file_layout.addWidget(self.select_file_btn)
        layout.addLayout(file_layout)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        preview_label = QLabel("Preview das Transações:")
        preview_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(preview_label)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(6)
        self.preview_table.setHorizontalHeaderLabels([
            "✓", "Data", "Descrição", "Tipo", "Valor", "Status"
        ])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.preview_table)

        self.stats_label = QLabel("")
        layout.addWidget(self.stats_label)

        cat_layout = QHBoxLayout()
        cat_layout.addWidget(QLabel("Categoria padrão para importação:"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("Sem categoria", None)

        if hasattr(self.parent(), 'db_connection'):
            categories = self.parent().db_connection.execute(
                'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
                (self.parent().user_id,)
            ).fetchall()
            for cat in categories:
                self.category_combo.addItem(cat['name'], cat['id'])

        cat_layout.addWidget(self.category_combo)
        cat_layout.addStretch()
        layout.addLayout(cat_layout)

        button_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("✓ Selecionar Todas")
        self.select_all_btn.clicked.connect(self.selecionar_todas)
        self.select_all_btn.setEnabled(False)

        self.deselect_all_btn = QPushButton("✗ Desmarcar Todas")
        self.deselect_all_btn.clicked.connect(self.desmarcar_todas)
        self.deselect_all_btn.setEnabled(False)

        self.import_btn = QPushButton("💾 Importar Selecionadas")
        self.import_btn.clicked.connect(self.importar_transacoes)
        self.import_btn.setEnabled(False)

        self.cancel_btn = QPushButton("✖ Cancelar")
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.select_all_btn)
        button_layout.addWidget(self.deselect_all_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.import_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def apply_theme(self):
        """Aplica o tema ao diálogo"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QPushButton {
                    background-color: #3498db; color: #ecf0f1;
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
                QPushButton:hover { background-color: #2980b9; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                }
            """)
            self.import_btn.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.cancel_btn.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.import_btn.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_btn.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def selecionar_arquivo(self):
        """Abre diálogo para selecionar PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Extrato Bancário", "",
            "Arquivos PDF (*.pdf)"
        )
        if file_path:
            self.file_label.setText(os.path.basename(file_path))
            self.processar_pdf(file_path)

    def processar_pdf(self, file_path):
        """Processa o PDF e extrai as transações"""
        try:
            from modulos.pdf_parser import (
                processar_pdf_extrato, gerar_hash_transacao
            )

            self.status_label.setText("⏳ Processando PDF...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            QApplication.processEvents()

            with open(file_path, 'rb') as f:
                arquivo_bytes = f.read()

            sucesso, transacoes, mensagem = processar_pdf_extrato(arquivo_bytes)

            self.progress_bar.setVisible(False)

            if not sucesso:
                self.status_label.setText(f"❌ Erro: {mensagem}")
                self.status_label.setStyleSheet("color: red;")
                return

            self.transacoes_extraidas = transacoes
            self.status_label.setText(f"✅ {mensagem}")
            self.status_label.setStyleSheet("color: green;")

            self.verificar_duplicatas()
            self.mostrar_preview()

        except ImportError:
            QMessageBox.critical(
                self, "Erro",
                "Módulo pdfplumber não instalado.\n\n"
                "Instale com: pip install pdfplumber"
            )
        except Exception as e:
            self.status_label.setText(f"❌ Erro ao processar: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
            import traceback
            traceback.print_exc()

    def verificar_duplicatas(self):
        """
        Verifica duplicatas em dois níveis:
        Nível 1 - Hash exato: tipo + valor + data + descrição (30 chars)
        Nível 2 - Hash fuzzy: tipo + valor + data (sem descrição)
                  Detecta duplicata mesmo se a descrição mudou levemente
        """
        from modulos.pdf_parser import gerar_hash_transacao, gerar_hash_fuzzy

        transacoes_db = self.parent().db_connection.execute(
            '''SELECT id, transaction_type, amount, date, description
               FROM transactions WHERE user_id = ?''',
            (self.parent().user_id,)
        ).fetchall()

        # Nível 1 - hashes exatos
        hashes_exatos = set()

        # Nível 2 - hashes fuzzy (sem descrição)
        hashes_fuzzy = {}

        for t in transacoes_db:
            # Hash exato
            h_exato = gerar_hash_transacao(
                t['transaction_type'],
                t['amount'],
                t['date'],
                t['description']
            )
            hashes_exatos.add(h_exato)

            # Hash fuzzy - guarda descrição original para mostrar ao usuário
            h_fuzzy = gerar_hash_fuzzy(
                t['transaction_type'],
                t['amount'],
                t['date']
            )
            if h_fuzzy not in hashes_fuzzy:
                hashes_fuzzy[h_fuzzy] = t['description']

        for transacao in self.transacoes_extraidas:
            # Nível 1 - verificar hash exato
            if transacao['hash'] in hashes_exatos:
                transacao['duplicada'] = True
                transacao['duplicata_tipo'] = 'exata'
                transacao['duplicata_descricao'] = None
                continue

            # Nível 2 - verificar hash fuzzy
            h_fuzzy = gerar_hash_fuzzy(
                transacao['tipo'],
                transacao['valor'],
                transacao['data']
            )

            if h_fuzzy in hashes_fuzzy:
                transacao['duplicada'] = True
                transacao['duplicata_tipo'] = 'fuzzy'
                transacao['duplicata_descricao'] = hashes_fuzzy[h_fuzzy]
            else:
                transacao['duplicada'] = False
                transacao['duplicata_tipo'] = None
                transacao['duplicata_descricao'] = None

    def mostrar_preview(self):
        """Mostra preview das transações na tabela"""
        from PyQt5.QtWidgets import QCheckBox

        self.preview_table.setRowCount(len(self.transacoes_extraidas))

        novas = 0
        duplicadas_exatas = 0
        duplicadas_fuzzy = 0
        genericas = 0

        for i, trans in enumerate(self.transacoes_extraidas):
            checkbox = QCheckBox()
            checkbox.setChecked(not trans['duplicada'])
            checkbox_widget = QWidget()
            cb_layout = QHBoxLayout(checkbox_widget)
            cb_layout.addWidget(checkbox)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.preview_table.setCellWidget(i, 0, checkbox_widget)

            self.preview_table.setItem(
                i, 1, QTableWidgetItem(trans['data'])
            )

            desc_texto = trans['descricao'][:80]
            desc_item = QTableWidgetItem(desc_texto)

            if 'bloco_original' in trans:
                desc_item.setToolTip(
                    f"Bloco original:\n{trans['bloco_original']}"
                )

            if 'Transação #' in trans['descricao']:
                desc_item.setBackground(QColor('#FFF3CD'))
                desc_item.setToolTip(
                    f"⚠️ Descrição genérica - revisar\n\n"
                    f"Bloco original:\n{trans.get('bloco_original', 'N/A')}"
                )
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

            # Status com tipo de duplicata detalhado
            if not trans['duplicada']:
                status_item = QTableWidgetItem("✓ Nova")
                status_item.setForeground(QColor('green'))
                novas += 1

            elif trans.get('duplicata_tipo') == 'exata':
                status_item = QTableWidgetItem("⚠️ DUPLICADA")
                status_item.setForeground(QColor('orange'))
                status_item.setToolTip(
                    "Duplicata exata - mesma descrição, valor, data e tipo"
                )
                duplicadas_exatas += 1

            elif trans.get('duplicata_tipo') == 'fuzzy':
                desc_original = trans.get('duplicata_descricao', '')
                status_item = QTableWidgetItem("🔶 PROVÁVEL DUPLICATA")
                status_item.setForeground(QColor('#FF8C00'))
                status_item.setToolTip(
                    f"Mesmo valor, data e tipo já existem no sistema.\n"
                    f"Descrição salva anteriormente:\n"
                    f"'{desc_original}'\n\n"
                    f"Descrição atual:\n"
                    f"'{trans['descricao']}'\n\n"
                    f"Verifique se é realmente uma transação diferente."
                )
                duplicadas_fuzzy += 1

            self.preview_table.setItem(i, 5, status_item)

        self.preview_table.resizeColumnsToContents()

        # Estatísticas atualizadas
        stats_parts = [
            f"📊 {len(self.transacoes_extraidas)} total",
            f"✅ {novas} novas",
        ]

        if duplicadas_exatas > 0:
            stats_parts.append(f"⚠️ {duplicadas_exatas} duplicatas exatas")

        if duplicadas_fuzzy > 0:
            stats_parts.append(
                f"🔶 {duplicadas_fuzzy} prováveis duplicatas"
            )

        if genericas > 0:
            stats_parts.append(f"❓ {genericas} descrição genérica")

        self.stats_label.setText(" | ".join(stats_parts))

        has_warning = genericas > 0 or duplicadas_fuzzy > 0
        self.stats_label.setStyleSheet(
            "color: orange; font-weight: bold;"
            if has_warning else
            "font-weight: bold;"
        )

        self.select_all_btn.setEnabled(True)
        self.deselect_all_btn.setEnabled(True)
        self.import_btn.setEnabled(True)

    def selecionar_todas(self):
        """Seleciona todas as transações"""
        from PyQt5.QtWidgets import QCheckBox
        for i in range(self.preview_table.rowCount()):
            w = self.preview_table.cellWidget(i, 0)
            cb = w.findChild(QCheckBox)
            if cb:
                cb.setChecked(True)

    def desmarcar_todas(self):
        """Desmarca todas as transações"""
        from PyQt5.QtWidgets import QCheckBox
        for i in range(self.preview_table.rowCount()):
            w = self.preview_table.cellWidget(i, 0)
            cb = w.findChild(QCheckBox)
            if cb:
                cb.setChecked(False)

    def importar_transacoes(self):
        """Importa as transações selecionadas"""
        from PyQt5.QtWidgets import QCheckBox

        transacoes_selecionadas = []
        for i in range(self.preview_table.rowCount()):
            w = self.preview_table.cellWidget(i, 0)
            cb = w.findChild(QCheckBox)
            if cb and cb.isChecked():
                transacoes_selecionadas.append(self.transacoes_extraidas[i])

        if not transacoes_selecionadas:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione pelo menos uma transação para importar."
            )
            return

        reply = QMessageBox.question(
            self, "Confirmar Importação",
            f"Deseja importar {len(transacoes_selecionadas)} transação(ões)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply != QMessageBox.Yes:
            return

        category_id = self.category_combo.currentData()
        importadas = erros = 0

        try:
            for trans in transacoes_selecionadas:
                try:
                    self.parent().db_connection.execute(
                        '''INSERT INTO transactions
                           (user_id, amount, description,
                            transaction_type, date, category_id)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (self.parent().user_id, trans['valor'],
                         trans['descricao'], trans['tipo'],
                         trans['data'], category_id)
                    )
                    importadas += 1
                except Exception as e:
                    print(f"Erro ao importar: {e}")
                    erros += 1

            self.parent().db_connection.commit()
            self.parent().load_transactions()
            self.parent().update_balance()
            self.parent().update_year_buttons()

            QMessageBox.information(
                self, "Importação Concluída",
                f"✅ {importadas} transação(ões) importada(s)!\n"
                + (f"⚠️ {erros} erro(s)." if erros > 0 else "")
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro",
                f"Erro ao importar transações: {str(e)}"
            )


class MainWindow(QMainWindow):
    """Janela principal do sistema"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestão Financeira Pessoal")
        self.setGeometry(100, 100, 1000, 700)

        self.settings = QSettings("FinanceApp", "FinanceTracker")
        self.is_dark_mode = self.settings.value(
            "dark_mode", False, type=bool
        )

        if not os.path.exists('dados'):
            os.makedirs('dados')

        self.db_connection = None
        self.user_id = None
        self.selected_year = datetime.now().year

        self._setup_icon()
        self._setup_tray()
        self._setup_widgets()
        self._setup_connections()

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.login_layout = self.create_login_layout()
        self.main_layout.addLayout(self.login_layout)

        self.load_saved_login()
        self.apply_theme()
        self.setMinimizeToTray()
        self.start_minimized = True

    def _setup_icon(self):
        """Configura o ícone da aplicação"""
        self.app_icon = QIcon('finance_icon.png')
        self.setWindowIcon(self.app_icon)

    def _setup_tray(self):
        """Configura o ícone da bandeja do sistema"""
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("Gestão Financeira Pessoal")

        tray_menu = QMenu()

        show_action = QAction("Abrir", self)
        show_action.triggered.connect(self.show)

        hide_action = QAction("Minimizar", self)
        hide_action.triggered.connect(self.hide)

        exit_action = QAction("Sair", self)
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
        self.username_label  = QLabel("Usuário:")
        self.username_input  = QLineEdit()
        self.password_label  = QLabel("Senha:")
        self.password_input  = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.login_button    = QPushButton("Login")
        self.register_button = QPushButton("Registrar")
        self.save_login_button = QPushButton("Salvar Login")

        # Dashboard - Tabela de transações
        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(6)
        self.transactions_table.setHorizontalHeaderLabels([
            "ID", "Descrição", "Valor", "Tipo", "Data", "Categoria"
        ])

        self.add_transaction_button    = QPushButton("Adicionar Transação")
        self.edit_transaction_button   = QPushButton("Editar Transação")
        self.delete_transaction_button = QPushButton("Excluir Transação")

        # Dashboard - Tabela de notas
        self.notes_table = QTableWidget()
        self.notes_table.setColumnCount(2)
        self.notes_table.setHorizontalHeaderLabels(["ID", "Nota"])

        self.add_note_button    = QPushButton("Adicionar Nota")
        self.edit_note_button   = QPushButton("Editar Nota")
        self.delete_note_button = QPushButton("Excluir Nota")

        # Dashboard - Tabela de categorias
        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(3)
        self.categories_table.setHorizontalHeaderLabels([
            "ID", "Nome", "Ações"
        ])

        self.add_category_button    = QPushButton("Adicionar Categoria")
        self.edit_category_button   = QPushButton("Editar Categoria")
        self.delete_category_button = QPushButton("Excluir Categoria")

        # Saldo
        self.balance_label = QLabel("Saldo: R$ 0.00")

        # ── Campo de busca atualizado ────────────────────────
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "🔍 Pesquisar por descrição, categoria ou valor..."
        )
        self.search_input.textChanged.connect(self.load_transactions)

        # Layout de botões de ano
        self.year_buttons_layout = QHBoxLayout()

        # Botões de ação
        self.logout_button = QPushButton("Sair")
        self.logout_button.clicked.connect(self.logout)

        self.dark_mode_button = QPushButton(
            "Modo Escuro: Ativado"
            if self.is_dark_mode else "Modo Escuro: Desativado"
        )
        self.dark_mode_button.clicked.connect(self.toggle_dark_mode)

        # Ferramentas
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

        self.import_extrato_button = QPushButton("📄 Importar Extrato PDF")
        self.import_extrato_button.clicked.connect(
            self.show_import_extrato_dialog
        )

        # Empréstimos
        self.loans_button = QPushButton("💳 Empréstimos")
        self.loans_button.clicked.connect(self.show_loans_dialog)

        self.ai_assistant_button = None

    def _setup_connections(self):
        """Configura as conexões de sinais"""
        self.login_button.clicked.connect(self.login)
        self.register_button.clicked.connect(self.register)
        self.add_transaction_button.clicked.connect(
            self.show_add_transaction_dialog
        )
        self.edit_transaction_button.clicked.connect(
            self.show_edit_transaction_dialog
        )
        self.delete_transaction_button.clicked.connect(self.delete_transaction)
        self.add_note_button.clicked.connect(self.show_add_note_dialog)
        self.edit_note_button.clicked.connect(self.show_edit_note_dialog)
        self.delete_note_button.clicked.connect(self.delete_note)
        self.add_category_button.clicked.connect(self.show_add_category_dialog)
        self.edit_category_button.clicked.connect(
            self.show_edit_category_dialog
        )
        self.delete_category_button.clicked.connect(self.delete_category)
        self.save_login_button.clicked.connect(self.save_login)

    # ==================== TEMA ====================

    def toggle_dark_mode(self):
        """Alterna entre modo claro e escuro"""
        self.is_dark_mode = not self.is_dark_mode
        self.dark_mode_button.setText(
            "Modo Escuro: Ativado"
            if self.is_dark_mode else "Modo Escuro: Desativado"
        )
        self.apply_theme()
        self.settings.setValue("dark_mode", self.is_dark_mode)

    def apply_theme(self):
        """Aplica o tema à aplicação"""
        if self.is_dark_mode:
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)
            self.setPalette(palette)

            self.setStyleSheet("""
                QMainWindow, QDialog {
                    background-color: #1e272e; color: #ecf0f1;
                }
                QLabel { color: #ecf0f1; }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px; padding: 5px;
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
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                    padding: 5px; border: 1px solid #4b6584;
                }
                QTabWidget::pane {
                    border: 1px solid #4b6584; background-color: #1e272e;
                }
                QTabBar::tab {
                    background-color: #2d3436; color: #ecf0f1;
                    padding: 8px 12px; border: 1px solid #4b6584;
                    border-bottom: none; border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected { background-color: #3498db; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QCheckBox { color: #ecf0f1; }
            """)
        else:
            self.setPalette(QPalette())
            self.setStyleSheet("""
                QMainWindow, QDialog {
                    background-color: #f9f9f9; color: #333333;
                }
                QLabel { color: #333333; }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: white; color: #333333;
                    border: 1px solid #ccc; border-radius: 4px; padding: 5px;
                }
                QPushButton {
                    background-color: #4CAF50; color: white;
                    border: none; border-radius: 4px;
                    padding: 6px 12px; font-weight: bold;
                }
                QPushButton:hover { background-color: #45a049; }
                QTableWidget {
                    background-color: white; color: #333333;
                    gridline-color: #ddd;
                    selection-background-color: #e3f2fd;
                }
                QHeaderView::section {
                    background-color: #f0f0f0; color: #333333;
                    padding: 5px; border: 1px solid #ccc;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc; background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333333;
                    padding: 8px 12px; border: 1px solid #ccc;
                    border-bottom: none; border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #4CAF50; color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
            """)

    # ==================== TRAY ====================

    def closeEvent(self, event):
        """Controla o comportamento ao fechar"""
        if self.minimizeToTray:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Gestão Financeira",
                "Aplicativo minimizado para a bandeja.",
                QSystemTrayIcon.Information, 2000
            )
        else:
            self.settings.setValue("dark_mode", self.is_dark_mode)
            if hasattr(self, 'transactions_table'):
                self.save_table_state()
            if self.db_connection:
                self.db_connection.close()
            event.accept()

    def tray_icon_activated(self, reason):
        """Gerencia eventos do ícone da bandeja"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()

    def close_application(self):
        """Fecha a aplicação completamente"""
        self.minimizeToTray = False
        self.close()

    def setMinimizeToTray(self):
        """Define se minimiza para a bandeja"""
        self.minimizeToTray = True

    # ==================== LOGIN ====================

    def create_login_layout(self):
        """Cria o layout da tela de login"""
        login_layout = QVBoxLayout()

        login_container = QWidget()
        container_layout = QVBoxLayout(login_container)

        title_label = QLabel("Sistema de Gestão Financeira")
        title_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; margin-bottom: 20px;"
        )
        title_label.setAlignment(Qt.AlignCenter)

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

    def get_db_path(self, username):
        """Retorna o caminho para o banco de dados"""
        return os.path.join('dados', f'{username}.db')

    def login(self):
        """Realiza o login do usuário"""
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(
                self, "Erro", "Por favor, preencha todos os campos."
            )
            return

        import sqlite3
        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        db_manager = DBManager(username)
        db_manager.connection = self.db_connection
        db_manager.create_tables()

        if not DBUpdater.check_and_update(self.db_connection, username):
            QMessageBox.critical(
                self, "Erro",
                "Não foi possível atualizar o banco de dados."
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
                self, "Erro", "Usuário ou senha incorretos."
            )
            self.db_connection.close()

    def _force_db_update(self):
        """Força atualização do banco de dados"""
        try:
            columns_to_check = [
                ('categories', 'is_savings_goal', 'INTEGER DEFAULT 0'),
                ('categories', 'is_hidden', 'INTEGER DEFAULT 0'),
                ('categories', 'year', f'INTEGER DEFAULT {datetime.now().year}'),
                ('transactions', 'savings_category_id', 'INTEGER'),
                ('transactions', 'is_saving_transaction', 'INTEGER DEFAULT 0'),
            ]

            for table, column, col_type in columns_to_check:
                exists = self.db_connection.execute(
                    f"SELECT COUNT(*) FROM pragma_table_info('{table}') "
                    f"WHERE name='{column}'"
                ).fetchone()[0] > 0

                if not exists:
                    self.db_connection.execute(
                        f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'
                    )

            self.db_connection.commit()
            return True
        except Exception as e:
            print(f"Erro ao atualizar BD: {e}")
            return False

    def _check_new_year(self):
        """Verifica se é um novo ano e oculta categorias antigas"""
        try:
            last_year = self.settings.value("last_year_check", None)
            current_year = datetime.now().year

            if last_year is None or int(last_year) < current_year:
                col_exists = self.db_connection.execute(
                    "SELECT COUNT(*) FROM pragma_table_info('categories') "
                    "WHERE name='year'"
                ).fetchone()[0] > 0

                if col_exists:
                    self.db_connection.execute(
                        "UPDATE categories SET is_hidden = 1 "
                        "WHERE user_id = ? AND year < ?",
                        (self.user_id, current_year)
                    )
                    self.db_connection.commit()

                self.settings.setValue("last_year_check", current_year)

                if last_year is not None:
                    QMessageBox.information(
                        self, "Novo Ano",
                        f"Bem-vindo a {current_year}! "
                        f"As categorias do ano anterior foram ocultadas."
                    )
        except Exception as e:
            print(f"Erro ao verificar novo ano: {e}")

    def register(self):
        """Registra um novo usuário"""
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(
                self, "Erro", "Por favor, preencha todos os campos."
            )
            return

        import sqlite3
        db_path = self.get_db_path(username)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        db_manager = DBManager(username)
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
                self, "Sucesso", "Usuário registrado com sucesso."
            )
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Erro", "Nome de usuário já existe."
            )
        finally:
            conn.close()

    def save_login(self):
        """Salva as credenciais de login"""
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(
                self, "Erro", "Por favor, preencha todos os campos."
            )
            return

        with open("login.txt", "w") as f:
            f.write(f"{username},{password}")

        QMessageBox.information(self, "Sucesso", "Login salvo com sucesso.")

    def load_saved_login(self):
        """Carrega as credenciais salvas"""
        if os.path.exists("login.txt"):
            with open("login.txt", "r") as f:
                try:
                    username, password = f.read().split(",")
                    self.username_input.setText(username)
                    self.password_input.setText(password)
                except Exception:
                    pass

    def load_user_preferences(self):
        """Carrega preferências do usuário"""
        try:
            theme_setting = self.db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'dark_mode'""",
                (self.user_id,)
            ).fetchone()

            if theme_setting:
                self.is_dark_mode = (
                    theme_setting['setting_value'].lower() == 'true'
                )
                self.dark_mode_button.setText(
                    "Modo Escuro: Ativado"
                    if self.is_dark_mode else "Modo Escuro: Desativado"
                )
                self.apply_theme()
        except Exception:
            pass

    def save_user_preferences(self):
        """Salva preferências do usuário"""
        try:
            existing = self.db_connection.execute(
                """SELECT id FROM user_settings
                   WHERE user_id = ? AND setting_key = 'dark_mode'""",
                (self.user_id,)
            ).fetchone()

            if existing:
                self.db_connection.execute(
                    """UPDATE user_settings SET setting_value = ?
                       WHERE user_id = ? AND setting_key = 'dark_mode'""",
                    (str(self.is_dark_mode), self.user_id)
                )
            else:
                self.db_connection.execute(
                    """INSERT INTO user_settings
                       (user_id, setting_key, setting_value)
                       VALUES (?, ?, ?)""",
                    (self.user_id, 'dark_mode', str(self.is_dark_mode))
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

    # ==================== DASHBOARD ====================

    def load_dashboard(self):
        """Carrega o dashboard principal"""
        dashboard_layout = QVBoxLayout()

        title_label = QLabel(
            f"Gestão Financeira - {self.username_input.text()}"
        )
        title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; margin: 10px 0;"
        )
        dashboard_layout.addWidget(title_label)

        top_layout = QHBoxLayout()
        self.balance_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 10px; "
            "border-radius: 4px;"
        )
        top_layout.addWidget(self.balance_label)

        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(QLabel("🔍"))
        search_layout.addWidget(self.search_input)
        top_layout.addWidget(search_container)
        dashboard_layout.addLayout(top_layout)

        dashboard_layout.addLayout(self.year_buttons_layout)

        month_filter_layout = QHBoxLayout()
        month_label = QLabel("Filtrar por mês:")
        self.month_combo = QComboBox()
        self.month_combo.addItem("Todos os meses", 0)

        for month in range(1, 13):
            month_name = QDate(2000, month, 1).toString("MMMM").capitalize()
            self.month_combo.addItem(month_name, month)

        self.month_combo.setCurrentIndex(0)
        self.month_combo.currentIndexChanged.connect(self.load_transactions)

        month_filter_layout.addWidget(month_label)
        month_filter_layout.addWidget(self.month_combo)
        month_filter_layout.addStretch()
        dashboard_layout.addLayout(month_filter_layout)

        self.init_ai_assistant()

        tools_layout = QHBoxLayout()
        tools_layout.addWidget(self.budget_button)
        tools_layout.addWidget(self.cashflow_button)
        tools_layout.addWidget(self.calendar_button)
        tools_layout.addWidget(self.trends_button)
        tools_layout.addWidget(self.savings_goals_button)
        tools_layout.addWidget(self.import_extrato_button)
        # ── NOVO: Botão de Empréstimos ──────────────────────
        tools_layout.addWidget(self.loans_button)
        if self.ai_assistant_button:
            tools_layout.addWidget(self.ai_assistant_button)
        dashboard_layout.addLayout(tools_layout)

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

        bottom_layout = QHBoxLayout()

        self.categories_group = QGroupBox("Categorias")
        categories_layout = QVBoxLayout()
        categories_layout.addWidget(self.categories_table)

        category_button_layout = QHBoxLayout()
        category_button_layout.addWidget(self.add_category_button)
        category_button_layout.addWidget(self.edit_category_button)
        category_button_layout.addWidget(self.delete_category_button)
        categories_layout.addLayout(category_button_layout)
        self.categories_group.setLayout(categories_layout)

        self.add_category_options_to_interface()

        notes_group = QGroupBox("Notas")
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(self.notes_table)

        note_button_layout = QHBoxLayout()
        note_button_layout.addWidget(self.add_note_button)
        note_button_layout.addWidget(self.edit_note_button)
        note_button_layout.addWidget(self.delete_note_button)
        notes_layout.addLayout(note_button_layout)
        notes_group.setLayout(notes_layout)

        bottom_layout.addWidget(self.categories_group)
        bottom_layout.addWidget(notes_group)
        dashboard_layout.addLayout(bottom_layout)

        report_layout = QHBoxLayout()

        report_button = QPushButton("📊 Gerar Relatório")
        report_button.clicked.connect(self.generate_category_report)

        graph_button = QPushButton("📈 Gerar Gráfico")
        graph_button.clicked.connect(self.generate_category_graph)

        export_button = QPushButton("📋 Exportar Relatório")
        export_button.clicked.connect(self.export_report)

        report_layout.addWidget(report_button)
        report_layout.addWidget(graph_button)
        report_layout.addWidget(export_button)
        dashboard_layout.addLayout(report_layout)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.dark_mode_button)
        action_layout.addStretch()
        action_layout.addWidget(self.logout_button)
        dashboard_layout.addLayout(action_layout)

        self.main_layout.addLayout(dashboard_layout)

        self.load_transactions()
        self.load_notes()
        self.load_categories()
        self.update_balance()
        self.update_year_buttons()
        self.restore_table_state()

    def init_ai_assistant(self):
        """Inicializa o botão do assistente de IA"""
        self.ai_assistant_button = QPushButton("🤖 Assistente IA")
        self.ai_assistant_button.clicked.connect(self.show_ai_assistant)

        style = (
            "background-color: #8e44ad; color: white; font-weight: bold;"
            if self.is_dark_mode else
            "background-color: #9c27b0; color: white; font-weight: bold;"
        )
        self.ai_assistant_button.setStyleSheet(style)

    def show_ai_assistant(self):
        """Mostra o assistente de IA"""
        try:
            from interface.widgets.ai_widget import AIAssistantWidget
        except ImportError as e:
            QMessageBox.critical(
                self, "Erro",
                f"Módulo AI Widget não encontrado.\n\nDetalhes: {str(e)}"
            )
            return

        # Iniciar integração com servidor de IA em background
        try:
            from modulos.financial_ai import FinancialAI

            ai = FinancialAI(self.db_connection, self.user_id)

            if not ai.api_key:
                QMessageBox.warning(
                    self, "API Key não configurada",
                    "Configure a API Key nas configurações do Assistente IA\n"
                    "antes de iniciar. Clique em ⚙️ dentro do assistente."
                )
            else:
                threading.Thread(
                    target=ai.start,
                    daemon=True,
                    name="FinancialAI-Start"
                ).start()

        except Exception as e:
            print(f"[MainWindow] Aviso: FinancialAI não iniciado - {e}")

        # Abrir janela do assistente
        assistant_dialog = QDialog(self)
        assistant_dialog.setWindowTitle("Assistente Financeiro IA")
        assistant_dialog.resize(650, 650)

        layout = QVBoxLayout()
        assistant_widget = AIAssistantWidget(self)
        layout.addWidget(assistant_widget)
        assistant_dialog.setLayout(layout)

        if self.is_dark_mode:
            assistant_dialog.setStyleSheet(
                "QDialog { background-color: #1e272e; color: #ecf0f1; }"
            )

        assistant_dialog.exec_()

    # ==================== DADOS ====================

    def update_year_buttons(self):
        """Atualiza os botões de ano"""
        while self.year_buttons_layout.count():
            child = self.year_buttons_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        years = self.db_connection.execute(
            """SELECT DISTINCT strftime('%Y', date) as year
               FROM transactions WHERE user_id = ?
               ORDER BY year DESC""",
            (self.user_id,)
        ).fetchall()

        for year in years:
            year_button = QPushButton(year['year'])
            year_button.setCheckable(True)
            year_button.setChecked(year['year'] == str(self.selected_year))
            year_button.toggled.connect(
                lambda checked, y=year['year']: self.toggle_year(y, checked)
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
        """Carrega as transações do usuário"""
        search_text   = self.search_input.text().lower().strip()
        selected_month = (
            self.month_combo.currentData()
            if hasattr(self, 'month_combo') else 0
        )

        query = '''SELECT t.*, c.name AS category_name,
                          t.is_saving_transaction
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND strftime('%Y', t.date) = ?'''
        params = [self.user_id, str(self.selected_year)]

        if selected_month > 0:
            query += " AND strftime('%m', t.date) = ?"
            params.append(f"{selected_month:02d}")

        if search_text:
            query += """ AND (
                LOWER(t.description) LIKE ?
                OR LOWER(c.name)    LIKE ?
                OR CAST(t.amount AS TEXT) LIKE ?
            )"""
            params.extend([
                f'%{search_text}%',
                f'%{search_text}%',
                f'%{search_text}%'
            ])

        query += " ORDER BY t.date DESC"

        transactions = self.db_connection.execute(
            query, params
        ).fetchall()

        self.transactions_table.setRowCount(len(transactions))

        for i, transaction in enumerate(transactions):
            if self.is_dark_mode:
                entry_color  = QColor("#1B5E20")
                exit_color   = QColor("#B71C1C")
                saving_color = QColor("#0D47A1")
            else:
                entry_color  = QColor("#E8F5E9")
                exit_color   = QColor("#FFEBEE")
                saving_color = QColor("#E3F2FD")

            is_saving = (
                'is_saving_transaction' in transaction.keys() and
                transaction['is_saving_transaction'] == 1
            )

            display_type = transaction['transaction_type']
            if is_saving:
                display_type = "guardar"

            row_color = (
                saving_color if is_saving else
                entry_color  if transaction['transaction_type'] == 'entrada'
                else exit_color
            )

            items = [
                QTableWidgetItem(str(transaction['id'])),
                QTableWidgetItem(transaction['description']),
                QTableWidgetItem(f"R$ {transaction['amount']:.2f}"),
                QTableWidgetItem(display_type),
                QTableWidgetItem(transaction['date']),
                QTableWidgetItem(transaction['category_name'] or ""),
            ]

            for j, item in enumerate(items):
                item.setBackground(row_color)
                self.transactions_table.setItem(i, j, item)

        self.transactions_table.resizeColumnsToContents()

    def load_notes(self):
        """Carrega as notas do usuário"""
        notes = self.db_connection.execute(
            'SELECT * FROM notes WHERE user_id = ?',
            (self.user_id,)
        ).fetchall()

        self.notes_table.setRowCount(len(notes))
        for i, note in enumerate(notes):
            self.notes_table.setItem(i, 0, QTableWidgetItem(str(note['id'])))
            self.notes_table.setItem(i, 1, QTableWidgetItem(note['note']))

        self.notes_table.resizeColumnsToContents()

    def load_categories(self):
        """Carrega as categorias do usuário"""
        show_hidden = self.settings.value(
            "show_hidden_categories", False, type=bool
        )
        show_previous_years = self.settings.value(
            "show_previous_years_categories", False, type=bool
        )
        current_year = datetime.now().year

        # Verificar se tabela de loans existe
        loans_table_exists = self.db_connection.execute(
            """SELECT COUNT(*) FROM sqlite_master
               WHERE type='table' AND name='loans'"""
        ).fetchone()[0] > 0

        # IDs de categorias de empréstimo (não mostrar aqui)
        loan_category_ids = set()
        if loans_table_exists:
            loans = self.db_connection.execute(
                """SELECT category_id FROM loans
                   WHERE user_id = ? AND category_id IS NOT NULL""",
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

        # Filtrar categorias de empréstimo
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
                    QColor("#01579B") if self.is_dark_mode
                    else QColor("#E8F5FE")
                )
                id_item.setBackground(color)
                name_item.setBackground(color)
                name_item.setText(f"{category['name']} 🎯")

            elif (
                'is_savings_goal' in category.keys() and
                category['is_savings_goal'] == 1
            ):
                color = (
                    QColor("#1B5E20") if self.is_dark_mode
                    else QColor("#E8FFF0")
                )
                id_item.setBackground(color)
                name_item.setBackground(color)
                name_item.setText(f"{category['name']} 💰")

            if (
                'is_hidden' in category.keys() and
                category['is_hidden'] == 1
            ):
                name_item.setText(f"{name_item.text()} 🔒")

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

            view_button = QPushButton("👁️")
            view_button.setToolTip("Ver Transações")
            view_button.clicked.connect(
                lambda _, cat_id=category['id'],
                cat_name=category['name']:
                self.show_category_transactions(cat_id, cat_name)
            )
            action_layout.addWidget(view_button)
            self.categories_table.setCellWidget(i, 2, action_widget)

        self.categories_table.resizeColumnsToContents()

    def update_balance(self):
        """Atualiza o saldo total"""
        transactions = self.db_connection.execute(
            'SELECT * FROM transactions WHERE user_id = ?',
            (self.user_id,)
        ).fetchall()

        saving_col = self.db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('transactions') "
            "WHERE name='is_saving_transaction'"
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
            "SELECT COUNT(*) FROM pragma_table_info('categories') "
            "WHERE name='is_savings_goal'"
        ).fetchone()[0] > 0

        total_savings = 0
        if savings_col:
            savings_cats = self.db_connection.execute(
                'SELECT id, name, total_amount FROM categories '
                'WHERE user_id = ? AND is_savings_goal = 1',
                (self.user_id,)
            ).fetchall()

            for cat in savings_cats:
                amount_saved = self.db_connection.execute(
                    """SELECT SUM(amount) FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'entrada'""",
                    (self.user_id, cat['id'])
                ).fetchone()[0] or 0
                total_savings += amount_saved

                if (
                    amount_saved >= cat['total_amount'] and
                    cat['total_amount'] > 0
                ):
                    self.tray_icon.showMessage(
                        "Meta Alcançada!",
                        f"Parabéns! Meta '{cat['name']}' atingida! 🎉",
                        QSystemTrayIcon.Information, 5000
                    )

        available_balance = balance - total_savings
        balance_text = f"Saldo Geral: R$ {balance:.2f}"

        if total_savings > 0:
            balance_text += f"\nGuardado: R$ {total_savings:.2f}"
            balance_text += f"\nDisponível: R$ {available_balance:.2f}"

        if self.is_dark_mode:
            color = "#4CAF50" if available_balance >= 0 else "#F44336"
            self.balance_label.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {color}; "
                f"background-color: #263238; padding: 10px; border-radius: 4px;"
            )
        else:
            if available_balance >= 0:
                self.balance_label.setStyleSheet(
                    "font-size: 16px; font-weight: bold; color: #2e7d32; "
                    "background-color: #e8f5e9; padding: 10px; border-radius: 4px;"
                )
            else:
                self.balance_label.setStyleSheet(
                    "font-size: 16px; font-weight: bold; color: #c62828; "
                    "background-color: #ffebee; padding: 10px; border-radius: 4px;"
                )

        self.balance_label.setText(balance_text)

    # ==================== TRANSAÇÕES ====================

    def show_add_transaction_dialog(self):
        """Mostra diálogo para adicionar transação"""
        dialog = AddTransactionDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_transactions()
            self.update_balance()
            self.update_year_buttons()

    def show_edit_transaction_dialog(self):
        """Mostra diálogo para editar transação"""
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(
                self.transactions_table.item(selected_row, 0).text()
            )
            dialog = EditTransactionDialog(self, transaction_id)
            if dialog.exec_() == QDialog.Accepted:
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()
        else:
            QMessageBox.warning(
                self, "Aviso", "Selecione uma transação para editar."
            )

    def delete_transaction(self):
        """Exclui a transação selecionada"""
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(
                self.transactions_table.item(selected_row, 0).text()
            )
            reply = QMessageBox.question(
                self, "Confirmar Exclusão",
                "Tem certeza que deseja excluir esta transação?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
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
                self, "Aviso", "Selecione uma transação para excluir."
            )

    # ==================== NOTAS ====================

    def show_add_note_dialog(self):
        """Mostra diálogo para adicionar nota"""
        dialog = AddNoteDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_notes()

    def show_edit_note_dialog(self):
        """Mostra diálogo para editar nota"""
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())
            dialog = EditNoteDialog(self, note_id)
            if dialog.exec_() == QDialog.Accepted:
                self.load_notes()
        else:
            QMessageBox.warning(
                self, "Aviso", "Selecione uma nota para editar."
            )

    def delete_note(self):
        """Exclui a nota selecionada"""
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())
            reply = QMessageBox.question(
                self, "Confirmar Exclusão",
                "Tem certeza que deseja excluir esta nota?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.db_connection.execute(
                    'DELETE FROM notes WHERE id = ?', (note_id,)
                )
                self.db_connection.commit()
                self.load_notes()
        else:
            QMessageBox.warning(
                self, "Aviso", "Selecione uma nota para excluir."
            )

    # ==================== CATEGORIAS ====================

    def show_add_category_dialog(self):
        """Mostra diálogo para adicionar categoria"""
        dialog = AddCategoryDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_categories()

    def show_edit_category_dialog(self):
        """Mostra diálogo para editar categoria"""
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(
                self.categories_table.item(selected_row, 0).text()
            )
            dialog = EditCategoryDialog(self, category_id)
            if dialog.exec_() == QDialog.Accepted:
                self.load_categories()
        else:
            QMessageBox.warning(
                self, "Aviso", "Selecione uma categoria para editar."
            )

    def delete_category(self):
        """Exclui a categoria selecionada"""
        selected_row = self.categories_table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione uma categoria para excluir."
            )
            return

        category_id = int(
            self.categories_table.item(selected_row, 0).text()
        )
        category_name = self.categories_table.item(
            selected_row, 1
        ).text()

        # Verificar transações vinculadas de forma mais precisa
        # Contar transações que realmente têm esta categoria
        count = self.db_connection.execute(
            """SELECT COUNT(*) FROM transactions
               WHERE category_id = ?
               AND user_id = ?""",
            (category_id, self.user_id)
        ).fetchone()[0]

        if count > 0:
            # Oferecer opção de desvincular ao invés de bloquear
            reply = QMessageBox.question(
                self, "Categoria com Transações",
                f"A categoria '{category_name}' possui {count} "
                f"transação(ões) vinculada(s).\n\n"
                f"Deseja desvincular as transações e excluir "
                f"a categoria?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # Desvincular transações antes de excluir
                self.db_connection.execute(
                    """UPDATE transactions
                       SET category_id = NULL
                       WHERE category_id = ?
                       AND user_id = ?""",
                    (category_id, self.user_id)
                )
                self.db_connection.commit()
            else:
                return

        # Verificar se é categoria de empréstimo
        loans_table_exists = self.db_connection.execute(
            """SELECT COUNT(*) FROM sqlite_master
               WHERE type='table' AND name='loans'"""
        ).fetchone()[0] > 0

        if loans_table_exists:
            is_loan_cat = self.db_connection.execute(
                """SELECT COUNT(*) FROM loans
                   WHERE category_id = ? AND user_id = ?""",
                (category_id, self.user_id)
            ).fetchone()[0] > 0

            if is_loan_cat:
                QMessageBox.warning(
                    self, "Categoria de Empréstimo",
                    "Esta categoria pertence a um empréstimo e não "
                    "pode ser excluída diretamente.\n\n"
                    "Para excluir, acesse o módulo de Empréstimos."
                )
                return

        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Excluir a categoria '{category_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Remover regras de categorização
                rules_table_exists = self.db_connection.execute(
                    """SELECT COUNT(*) FROM sqlite_master
                       WHERE type='table' AND name='category_rules'"""
                ).fetchone()[0] > 0

                if rules_table_exists:
                    self.db_connection.execute(
                        """DELETE FROM category_rules
                           WHERE category_id = ? AND user_id = ?""",
                        (category_id, self.user_id)
                    )

                # Remover a categoria
                self.db_connection.execute(
                    'DELETE FROM categories WHERE id = ? AND user_id = ?',
                    (category_id, self.user_id)
                )
                self.db_connection.commit()
                self.load_categories()
                self.load_transactions()

            except Exception as e:
                QMessageBox.critical(
                    self, "Erro",
                    f"Não foi possível excluir: {str(e)}"
                )

    def add_category_options_to_interface(self):
        """Adiciona opções para mostrar/ocultar categorias"""
        options_widget = QWidget()
        options_layout = QHBoxLayout(options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)

        self.show_hidden_check = QCheckBox("Mostrar Categorias Ocultas")
        self.show_hidden_check.setChecked(
            self.settings.value("show_hidden_categories", False, type=bool)
        )
        self.show_hidden_check.stateChanged.connect(
            self.toggle_hidden_categories
        )

        self.show_previous_years_check = QCheckBox(
            "Mostrar Categorias de Anos Anteriores"
        )
        self.show_previous_years_check.setChecked(
            self.settings.value(
                "show_previous_years_categories", False, type=bool
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
            "show_hidden_categories", state == Qt.Checked
        )
        self.load_categories()

    def toggle_previous_years_categories(self, state):
        """Alterna visibilidade de categorias de anos anteriores"""
        self.settings.setValue(
            "show_previous_years_categories", state == Qt.Checked
        )
        self.load_categories()

    def show_category_transactions(self, category_id, category_name):
        """Mostra transações de uma categoria específica"""
        from interface.dialogs.category_dialogs import (
            CategoryTransactionsDialog
        )
        dialog = CategoryTransactionsDialog(
            self, category_id, category_name
        )
        dialog.exec_()
        self.load_transactions()
        self.update_balance()

    # ==================== METAS ====================

    def show_savings_goals(self):
        """Mostra o gerenciador de metas"""
        goals_dialog = QDialog(self)
        goals_dialog.setWindowTitle("Gerenciador de Metas")
        goals_dialog.resize(750, 500)

        layout = QVBoxLayout()
        tabs = QTabWidget()

        savings_tab = QWidget()
        savings_layout = QVBoxLayout(savings_tab)

        savings_title = QLabel("Minhas Metas de Economia")
        savings_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        savings_layout.addWidget(savings_title)

        goals = self.db_connection.execute(
            '''SELECT id, name, target_amount, current_amount,
                      (current_amount / target_amount * 100) as progress
               FROM savings_goals WHERE user_id = ?
               ORDER BY deadline IS NULL, deadline, progress DESC''',
            (self.user_id,)
        ).fetchall()

        savings_table = QTableWidget()
        savings_table.setColumnCount(5)
        savings_table.setHorizontalHeaderLabels([
            "Nome", "Meta (R$)", "Atual (R$)", "Progresso", "Ações"
        ])
        savings_table.horizontalHeader().setStretchLastSection(True)
        savings_table.setEditTriggers(QTableWidget.NoEditTriggers)

        savings_table.setRowCount(len(goals))
        for i, goal in enumerate(goals):
            savings_table.setItem(i, 0, QTableWidgetItem(goal['name']))
            savings_table.setItem(
                i, 1,
                QTableWidgetItem(f"R$ {goal['target_amount']:.2f}")
            )
            savings_table.setItem(
                i, 2,
                QTableWidgetItem(f"R$ {goal['current_amount']:.2f}")
            )

            progress_widget = QWidget()
            p_layout = QHBoxLayout(progress_widget)
            p_bar = QProgressBar()
            p_bar.setMaximum(100)
            p_bar.setValue(int(goal['progress']))
            p_bar.setFormat(f"{int(goal['progress'])}%")
            p_layout.addWidget(p_bar)
            p_layout.setContentsMargins(4, 4, 4, 4)
            savings_table.setCellWidget(i, 3, progress_widget)

            action_widget = QWidget()
            a_layout = QHBoxLayout(action_widget)
            edit_btn = QPushButton("✏️")
            edit_btn.clicked.connect(
                lambda _, gid=goal['id']: self.edit_savings_goal(gid)
            )
            del_btn = QPushButton("🗑️")
            del_btn.clicked.connect(
                lambda _, gid=goal['id']: self.delete_savings_goal(gid)
            )
            a_layout.addWidget(edit_btn)
            a_layout.addWidget(del_btn)
            a_layout.setContentsMargins(2, 2, 2, 2)
            savings_table.setCellWidget(i, 4, action_widget)

        savings_layout.addWidget(savings_table)

        add_savings_btn = QPushButton("Nova Meta de Economia")
        add_savings_btn.clicked.connect(self.add_savings_goal)
        savings_layout.addWidget(add_savings_btn)

        tabs.addTab(savings_tab, "Metas de Economia")

        close_button = QPushButton("Fechar")
        close_button.clicked.connect(goals_dialog.accept)

        layout.addWidget(tabs)
        layout.addWidget(close_button, 0, Qt.AlignRight)
        goals_dialog.setLayout(layout)

        if self.is_dark_mode:
            goals_dialog.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
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
                    border: 1px solid #4b6584; border-radius: 5px;
                    text-align: center; background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71; width: 10px; margin: 0.5px;
                }
                QTabBar::tab {
                    background-color: #2d3436; color: #ecf0f1;
                    padding: 8px 12px;
                }
                QTabBar::tab:selected { background-color: #3498db; }
            """)

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
            self, "Confirmar Exclusão",
            "Tem certeza que deseja excluir esta meta?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.db_connection.execute(
                "DELETE FROM savings_goals WHERE id = ? AND user_id = ?",
                (goal_id, self.user_id)
            )
            self.db_connection.commit()
            self.show_savings_goals()

    # ==================== RELATÓRIOS ====================

    def show_budget_dialog(self):
        """Mostra o diálogo de orçamento"""
        BudgetDialog(self).exec_()

    def show_cashflow_dialog(self):
        """Mostra o diálogo de fluxo de caixa"""
        CashFlowDialog(self).exec_()

    def show_calendar_dialog(self):
        """Mostra o calendário financeiro"""
        CalendarDialog(self).exec_()

    def show_trends_dialog(self):
        """Mostra o diálogo de tendências"""
        TrendsDialog(self).exec_()

    def show_import_extrato_dialog(self):
        """Mostra o diálogo de importação de extrato"""
        try:
            ImportExtratoDialog(self).exec_()
        except Exception as e:
            QMessageBox.critical(
                self, "Erro",
                f"Erro ao abrir importação:\n{str(e)}\n\n"
                "Verifique se pdfplumber está instalado:\n"
                "pip install pdfplumber"
            )

    # ── NOVO ────────────────────────────────────────────────
    def show_loans_dialog(self):
        """Mostra o gerenciador de empréstimos"""
        from modulos.loans import create_loans_tables
        from interface.dialogs.loan_dialogs import LoansManagerDialog
        create_loans_tables(self.db_connection)
        LoansManagerDialog(self).exec_()
        self.load_categories()
        self.load_transactions()
        self.update_balance()

    def generate_category_report(self):
        """Gera relatório de gastos por categoria"""
        categories = self.db_connection.execute(
            """SELECT c.name, SUM(t.amount) AS total_spent
               FROM transactions t
               JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
               GROUP BY c.name ORDER BY total_spent DESC""",
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not categories:
            QMessageBox.information(
                self, "Informação",
                "Não há dados de categorias para o período selecionado."
            )
            return

        report_dialog = QDialog(self)
        report_dialog.setWindowTitle(
            f"Relatório de Gastos por Categoria - {self.selected_year}"
        )
        report_dialog.setMinimumSize(500, 400)
        report_layout = QVBoxLayout()

        title_label = QLabel(
            f"Relatório de Gastos por Categoria - {self.selected_year}"
        )
        title_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; margin-bottom: 10px;"
        )
        title_label.setAlignment(Qt.AlignCenter)
        report_layout.addWidget(title_label)

        report_table = QTableWidget(report_dialog)
        report_table.setColumnCount(3)
        report_table.setHorizontalHeaderLabels([
            "Categoria", "Total Gasto", "Porcentagem"
        ])
        report_table.setAlternatingRowColors(True)
        report_table.setEditTriggers(QTableWidget.NoEditTriggers)
        report_table.horizontalHeader().setStretchLastSection(True)

        total_amount = sum(c[1] for c in categories)
        report_table.setRowCount(len(categories))

        for i, category in enumerate(categories):
            percentage = (
                category[1] / total_amount * 100
                if total_amount > 0 else 0
            )
            report_table.setItem(i, 0, QTableWidgetItem(category[0]))
            report_table.setItem(
                i, 1, QTableWidgetItem(f"R$ {category[1]:.2f}")
            )
            report_table.setItem(
                i, 2, QTableWidgetItem(f"{percentage:.2f}%")
            )

        report_layout.addWidget(report_table)

        close_button = QPushButton("Fechar")
        close_button.clicked.connect(report_dialog.accept)
        report_layout.addWidget(close_button, 0, Qt.AlignCenter)
        report_dialog.setLayout(report_layout)

        if self.is_dark_mode:
            report_dialog.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
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
            """)

        report_dialog.exec_()

    def generate_category_graph(self):
        """Gera gráfico de gastos por categoria"""
        categories = self.db_connection.execute(
            """SELECT c.name, SUM(t.amount) AS total_spent
               FROM transactions t
               JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
               GROUP BY c.name ORDER BY total_spent DESC""",
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not categories:
            QMessageBox.information(
                self, "Informação",
                "Não há dados de categorias para o período selecionado."
            )
            return

        if len(categories) > 10:
            top = list(categories[:9])
            others_total = sum(c[1] for c in categories[9:])
            categories = top + [("Outros", others_total)]

        names = [c[0] for c in categories]
        values = [c[1] for c in categories]

        plt.figure(figsize=(10, 6))
        if self.is_dark_mode:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        bars = plt.bar(names, values, color='#4CAF50')

        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width()/2., height + 0.1,
                f'R${height:.2f}', ha='center', va='bottom', rotation=0
            )

        plt.xlabel("Categoria")
        plt.ylabel("Total Gasto (R$)")
        plt.title(f"Gastos por Categoria - {self.selected_year}")
        plt.xticks(rotation=45, ha="right")
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.show()

    def export_report(self):
        """Exporta relatório financeiro"""
        transactions = self.db_connection.execute(
            """SELECT t.*, c.name AS category_name
               FROM transactions t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
               ORDER BY t.date ASC""",
            (self.user_id, str(self.selected_year))
        ).fetchall()

        if not transactions:
            QMessageBox.information(
                self, "Informação",
                "Não há transações para exportar no período selecionado."
            )
            return

        format_dialog = QDialog(self)
        format_dialog.setWindowTitle("Escolher Formato")
        format_dialog.setFixedSize(400, 150)

        layout = QVBoxLayout()
        title_label = QLabel("Escolha o formato de exportação:")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        buttons_layout = QHBoxLayout()
        txt_button = QPushButton("Texto (.txt)")
        txt_button.clicked.connect(lambda: format_dialog.done(1))

        csv_button = QPushButton("Excel (.csv)")
        csv_button.clicked.connect(lambda: format_dialog.done(2))

        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(format_dialog.reject)

        buttons_layout.addWidget(txt_button)
        buttons_layout.addWidget(csv_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)
        format_dialog.setLayout(layout)

        result = format_dialog.exec_()
        if result == 0:
            return

        ext = "txt" if result == 1 else "csv"
        file_filter = (
            "Arquivos de Texto (*.txt)"
            if result == 1 else "Arquivos CSV (*.csv)"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Relatório",
            f"relatorio_{self.selected_year}.{ext}",
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
                self, "Sucesso",
                f"Relatório exportado com sucesso!\nArquivo: {file_path}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Erro",
                f"Não foi possível exportar o relatório.\nErro: {str(e)}"
            )

    def _export_txt(self, file_path, transactions):
        """Exporta relatório em formato TXT"""
        lines = [
            f"RELATÓRIO DE TRANSAÇÕES - Ano: {self.selected_year}",
            "=" * 50,
            "ID | Descrição | Valor | Tipo | Data | Categoria",
            "-" * 50
        ]

        for t in transactions:
            lines.append(
                f"{t['id']} | {t['description']} | "
                f"R$ {t['amount']:.2f} | {t['transaction_type']} | "
                f"{t['date']} | {t['category_name'] or ''}"
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
            "=" * 50,
            f"Total Entradas: R$ {entries:.2f}",
            f"Total Saídas: R$ {exits:.2f}",
            f"Saldo Total: R$ {entries - exits:.2f}"
        ]

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _export_csv(self, file_path, transactions):
        """Exporta relatório em formato CSV"""
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                f"RELATÓRIO DE TRANSAÇÕES - Ano: {self.selected_year}"
            ])
            writer.writerow([])
            writer.writerow([
                "ID", "Descrição", "Valor (R$)",
                "Tipo", "Data", "Categoria"
            ])

            for t in transactions:
                writer.writerow([
                    t['id'], t['description'],
                    f"{t['amount']:.2f}".replace('.', ','),
                    t['transaction_type'], t['date'],
                    t['category_name'] or ""
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
            writer.writerow(["RESUMO GERAL"])
            writer.writerow([
                "Total Entradas (R$)",
                f"{entries:.2f}".replace('.', ',')
            ])
            writer.writerow([
                "Total Saídas (R$)",
                f"{exits:.2f}".replace('.', ',')
            ])
            writer.writerow([
                "Saldo Total (R$)",
                f"{entries - exits:.2f}".replace('.', ',')
            ])

    # ==================== ESTADO DAS TABELAS ====================

    def save_table_state(self):
        """Salva o estado das tabelas"""
        self.settings.setValue(
            "transactions_table_state",
            self.transactions_table.horizontalHeader().saveState()
        )
        self.settings.setValue(
            "categories_table_state",
            self.categories_table.horizontalHeader().saveState()
        )
        self.settings.setValue(
            "notes_table_state",
            self.notes_table.horizontalHeader().saveState()
        )

    def restore_table_state(self):
        """Restaura o estado das tabelas"""
        trans_state = self.settings.value("transactions_table_state")
        if trans_state:
            self.transactions_table.horizontalHeader().restoreState(
                trans_state
            )

        cat_state = self.settings.value("categories_table_state")
        if cat_state:
            self.categories_table.horizontalHeader().restoreState(cat_state)

        notes_state = self.settings.value("notes_table_state")
        if notes_state:
            self.notes_table.horizontalHeader().restoreState(notes_state)

"""
Diálogos para gerenciamento de empréstimos
"""
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTextEdit, QTableWidget, QTableWidgetItem,
    QMessageBox, QGroupBox, QWidget, QProgressBar,
    QTabWidget, QDoubleSpinBox, QSpinBox, QHeaderView
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor

from modulos.loans import (
    calculate_loan, get_loan_status,
    check_and_complete_loans, sync_loan_payments
)


class AddLoanDialog(QDialog):
    """Diálogo para adicionar um novo empréstimo"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo Empréstimo")
        self.setMinimumWidth(550)
        self.setMinimumHeight(600)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )
        self.selected_transaction_id = None
        self.selected_category_id    = None

        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout()

        # ── Informações básicas ──────────────────────────────
        info_group = QGroupBox("Informações do Empréstimo")
        info_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ex: Empréstimo Banco X")
        info_layout.addRow("Nome:", self.name_input)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText(
            "Descrição do empréstimo..."
        )
        info_layout.addRow("Descrição:", self.description_input)

        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText(
            "Motivo do empréstimo (ex: reforma, viagem, emergência...)"
        )
        self.reason_input.setMaximumHeight(80)
        info_layout.addRow("Motivo:", self.reason_input)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # ── Valores ──────────────────────────────────────────
        values_group = QGroupBox("Valores")
        values_layout = QFormLayout()

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0.01, 9999999.99)
        self.amount_input.setDecimals(2)
        self.amount_input.setPrefix("R$ ")
        self.amount_input.valueChanged.connect(self.update_calculation)
        values_layout.addRow("Valor do Empréstimo:", self.amount_input)

        self.interest_input = QDoubleSpinBox()
        self.interest_input.setRange(0, 100)
        self.interest_input.setDecimals(2)
        self.interest_input.setSuffix(" % ao mês")
        self.interest_input.valueChanged.connect(self.update_calculation)
        values_layout.addRow("Taxa de Juros:", self.interest_input)

        self.installments_input = QSpinBox()
        self.installments_input.setRange(1, 360)
        self.installments_input.setValue(12)
        self.installments_input.setSuffix(" parcelas")
        self.installments_input.valueChanged.connect(self.update_calculation)
        values_layout.addRow("Número de Parcelas:", self.installments_input)

        self.discount_input = QDoubleSpinBox()
        self.discount_input.setRange(0, 9999999.99)
        self.discount_input.setDecimals(2)
        self.discount_input.setPrefix("R$ ")
        self.discount_input.valueChanged.connect(self.update_calculation)
        values_layout.addRow("Desconto Final:", self.discount_input)

        values_group.setLayout(values_layout)
        layout.addWidget(values_group)

        # ── Resumo do cálculo ────────────────────────────────
        calc_group = QGroupBox("Resumo do Cálculo")
        calc_layout = QVBoxLayout()

        self.total_interest_label = QLabel("Total com juros: R$ 0,00")
        self.installment_label    = QLabel("Valor da parcela: R$ 0,00")
        self.final_label          = QLabel("Valor final a pagar: R$ 0,00")
        self.final_label.setStyleSheet(
            "font-weight: bold; font-size: 14px;"
        )

        calc_layout.addWidget(self.total_interest_label)
        calc_layout.addWidget(self.installment_label)
        calc_layout.addWidget(self.final_label)
        calc_group.setLayout(calc_layout)
        layout.addWidget(calc_group)

        # ── Transação de recebimento (OBRIGATÓRIO) ───────────
        trans_group = QGroupBox(
            "⚠️ Transação de Recebimento — OBRIGATÓRIO"
        )
        trans_layout = QVBoxLayout()

        hint = QLabel(
            "🔴 Obrigatório: Busque e selecione a transação de ENTRADA\n"
            "onde você recebeu o dinheiro do empréstimo.\n"
            "O empréstimo só será criado após vincular esta transação."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: #e74c3c; font-style: italic; font-weight: bold;"
        )
        trans_layout.addWidget(hint)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Buscar por descrição, valor ou data..."
        )
        self.search_btn = QPushButton("🔍 Buscar")
        self.search_btn.clicked.connect(self.search_transactions)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        trans_layout.addLayout(search_layout)

        self.trans_table = QTableWidget()
        self.trans_table.setColumnCount(4)
        self.trans_table.setHorizontalHeaderLabels([
            "Data", "Descrição", "Valor", "Tipo"
        ])
        self.trans_table.setMaximumHeight(150)
        self.trans_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.trans_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.trans_table.horizontalHeader().setStretchLastSection(True)
        self.trans_table.clicked.connect(self.select_transaction)
        trans_layout.addWidget(self.trans_table)

        # ── Status da vinculação ─────────────────────────────
        self.selected_trans_label = QLabel(
            "🔴 Nenhuma transação vinculada — vincule para continuar"
        )
        self.selected_trans_label.setStyleSheet(
            "color: #e74c3c; font-weight: bold; padding: 5px;"
            "border: 1px solid #e74c3c; border-radius: 4px;"
        )
        self.selected_trans_label.setWordWrap(True)
        trans_layout.addWidget(self.selected_trans_label)

        trans_group.setLayout(trans_layout)
        layout.addWidget(trans_group)

        # ── Botões ───────────────────────────────────────────
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Confirmar e Criar Empréstimo")
        self.save_btn.clicked.connect(self.save_loan)

        # Começa desabilitado até vincular a transação
        self.save_btn.setEnabled(False)
        self.save_btn.setToolTip(
            "Vincule a transação de recebimento para habilitar"
        )

        self.cancel_btn = QPushButton("✖ Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.update_calculation()

    def update_calculation(self):
        """Atualiza o resumo do cálculo"""
        result = calculate_loan(
            self.amount_input.value(),
            self.interest_input.value(),
            self.installments_input.value(),
            self.discount_input.value()
        )
        self.total_interest_label.setText(
            f"Total com juros: R$ {result['total_with_interest']:,.2f}"
        )
        self.installment_label.setText(
            f"Valor da parcela: R$ {result['installment_amount']:,.2f}"
        )
        self.final_label.setText(
            f"Valor final a pagar: R$ {result['final_amount']:,.2f}"
        )

    def search_transactions(self):
        """Busca transações para vincular"""
        search_text = self.search_input.text().strip()
        if not search_text:
            return

        transactions = self.parent().db_connection.execute(
            """SELECT t.id, t.date, t.description,
                      t.amount, t.transaction_type
               FROM transactions t
               WHERE t.user_id = ?
               AND (
                   LOWER(t.description) LIKE ?
                   OR CAST(t.amount AS TEXT) LIKE ?
                   OR t.date LIKE ?
               )
               ORDER BY t.date DESC
               LIMIT 20""",
            (
                self.parent().user_id,
                f'%{search_text.lower()}%',
                f'%{search_text}%',
                f'%{search_text}%'
            )
        ).fetchall()

        self.trans_table.setRowCount(len(transactions))
        for i, t in enumerate(transactions):
            date_item = QTableWidgetItem(t['date'])
            date_item.setData(Qt.UserRole, t['id'])
            self.trans_table.setItem(i, 0, date_item)
            self.trans_table.setItem(
                i, 1, QTableWidgetItem(t['description'])
            )
            self.trans_table.setItem(
                i, 2, QTableWidgetItem(f"R$ {t['amount']:,.2f}")
            )
            tipo_item = QTableWidgetItem(t['transaction_type'])
            tipo_item.setForeground(
                QColor('green') if t['transaction_type'] == 'entrada'
                else QColor('red')
            )
            self.trans_table.setItem(i, 3, tipo_item)

        self.trans_table.resizeColumnsToContents()

        if not transactions:
            QMessageBox.information(
                self, "Busca", "Nenhuma transação encontrada."
            )

    def select_transaction(self):
        """Seleciona a transação clicada e habilita o botão salvar"""
        row = self.trans_table.currentRow()
        if row >= 0:
            item  = self.trans_table.item(row, 0)
            self.selected_transaction_id = item.data(Qt.UserRole)
            date  = item.text()
            desc  = self.trans_table.item(row, 1).text()
            value = self.trans_table.item(row, 2).text()
            tipo  = self.trans_table.item(row, 3).text()

            # ── Atualizar label com visual de confirmado ─────
            self.selected_trans_label.setText(
                f"✅ Transação vinculada:\n"
                f"📅 {date}  |  📝 {desc}  |  💰 {value}  |  {tipo}"
            )
            self.selected_trans_label.setStyleSheet(
                "color: #27ae60; font-weight: bold; padding: 5px;"
                "border: 1px solid #27ae60; border-radius: 4px;"
            )

            # ── Habilitar botão de salvar ────────────────────
            self.save_btn.setEnabled(True)
            self.save_btn.setToolTip("")
            self.save_btn.setStyleSheet(
                "background-color: #2ecc71; color: white;"
                if not self.is_dark_mode else
                "background-color: #27ae60; color: #ecf0f1;"
            )

    def save_loan(self):
        """Salva o empréstimo no banco de dados"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Erro", "O nome do empréstimo é obrigatório."
            )
            return

        if self.amount_input.value() <= 0:
            QMessageBox.warning(
                self, "Erro", "O valor do empréstimo deve ser positivo."
            )
            return

        # ── OBRIGATÓRIO: transação de recebimento ────────────
        if not self.selected_transaction_id:
            QMessageBox.warning(
                self, "Erro",
                "É obrigatório vincular a transação de recebimento "
                "do empréstimo.\n\n"
                "Busque e selecione a transação de ENTRADA onde "
                "você recebeu o dinheiro."
            )
            return

        result = calculate_loan(
            self.amount_input.value(),
            self.interest_input.value(),
            self.installments_input.value(),
            self.discount_input.value()
        )

        try:
            current_year = datetime.now().year

            # Criar categoria para o empréstimo
            self.parent().db_connection.execute(
                '''INSERT INTO categories
                   (user_id, name, total_amount,
                    is_payment_goal, year)
                   VALUES (?, ?, ?, 1, ?)''',
                (
                    self.parent().user_id,
                    f"Empréstimo: {name}",
                    result['final_amount'],
                    current_year
                )
            )
            self.parent().db_connection.commit()

            category = self.parent().db_connection.execute(
                'SELECT id FROM categories '
                'WHERE user_id = ? AND name = ?',
                (self.parent().user_id, f"Empréstimo: {name}")
            ).fetchone()
            category_id = category['id']

            # ── Mover a transação de recebimento para a
            #    categoria do empréstimo ─────────────────────
            self.parent().db_connection.execute(
                '''UPDATE transactions
                   SET category_id = ?
                   WHERE id = ?''',
                (category_id, self.selected_transaction_id)
            )
            self.parent().db_connection.commit()

            # Salvar empréstimo
            self.parent().db_connection.execute(
                '''INSERT INTO loans
                   (user_id, name, description, reason,
                    total_amount, interest_rate, num_installments,
                    discount, final_amount, installment_amount,
                    start_date, status, transaction_id, category_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, 'ativo', ?, ?)''',
                (
                    self.parent().user_id,
                    name,
                    self.description_input.text().strip(),
                    self.reason_input.toPlainText().strip(),
                    result['total_amount'],
                    result['interest_rate'],
                    result['num_installments'],
                    result['discount'],
                    result['final_amount'],
                    result['installment_amount'],
                    datetime.now().strftime('%Y-%m-%d'),
                    self.selected_transaction_id,
                    category_id
                )
            )
            self.parent().db_connection.commit()

            QMessageBox.information(
                self, "Sucesso",
                f"Empréstimo '{name}' criado com sucesso!\n\n"
                f"✅ A transação de recebimento foi movida para "
                f"a categoria 'Empréstimo: {name}'.\n\n"
                f"📌 Como registrar pagamentos:\n"
                f"Ao importar o extrato ou adicionar transações,\n"
                f"selecione a categoria 'Empréstimo: {name}'\n"
                f"nas transações de SAÍDA (pagamentos).\n"
                f"O sistema registrará automaticamente como parcelas."
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro",
                f"Não foi possível salvar o empréstimo:\n{str(e)}"
            )

    def apply_theme(self):
        """Aplica o tema ao diálogo"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QLineEdit, QTextEdit, QDoubleSpinBox, QSpinBox {
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
                    padding: 0 3px 0 3px;
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
            """)
            self.save_btn.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.cancel_btn.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { color: #333; }
                QLineEdit, QTextEdit, QDoubleSpinBox, QSpinBox {
                    padding: 6px; border: 1px solid #ccc;
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
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                }
                QTableWidget { background-color: white; }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.save_btn.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_btn.setStyleSheet(
                "background-color: #f44336; color: white;"
            )


class LoanDetailDialog(QDialog):
    """Diálogo para ver detalhes e histórico de um empréstimo"""

    def __init__(self, parent=None, loan_id=None):
        super().__init__(parent)
        self.loan_id      = loan_id
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )
        self.setWindowTitle("Detalhes do Empréstimo")
        self.setMinimumSize(700, 600)

        self._build_ui()
        self.load_data()
        self.apply_theme()

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout()

        # ── Cabeçalho ────────────────────────────────────────
        self.title_label = QLabel()
        self.title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(self.title_label)

        # ── Progresso ────────────────────────────────────────
        progress_group = QGroupBox("Progresso")
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimumHeight(25)
        progress_layout.addWidget(self.progress_bar)

        info_layout = QHBoxLayout()
        self.paid_label         = QLabel()
        self.remaining_label    = QLabel()
        self.installments_label = QLabel()
        info_layout.addWidget(self.paid_label)
        info_layout.addWidget(self.remaining_label)
        info_layout.addWidget(self.installments_label)
        progress_layout.addLayout(info_layout)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # ── Detalhes ─────────────────────────────────────────
        details_group = QGroupBox("Detalhes")
        details_layout = QFormLayout()

        self.reason_label           = QLabel()
        self.reason_label.setWordWrap(True)
        self.amount_label           = QLabel()
        self.interest_label         = QLabel()
        self.installment_value_label = QLabel()
        self.discount_label         = QLabel()
        self.final_label            = QLabel()
        self.start_date_label       = QLabel()
        self.status_label           = QLabel()

        details_layout.addRow("Motivo:",          self.reason_label)
        details_layout.addRow("Valor original:",  self.amount_label)
        details_layout.addRow("Juros:",           self.interest_label)
        details_layout.addRow("Valor da parcela:", self.installment_value_label)
        details_layout.addRow("Desconto:",        self.discount_label)
        details_layout.addRow("Valor final:",     self.final_label)
        details_layout.addRow("Data de início:",  self.start_date_label)
        details_layout.addRow("Status:",          self.status_label)

        details_group.setLayout(details_layout)
        layout.addWidget(details_group)

        # ── Histórico de pagamentos ───────────────────────────
        history_group = QGroupBox("Histórico de Pagamentos")
        history_layout = QVBoxLayout()

        # Info sobre como registrar pagamentos
        hint = QLabel(
            "💡 Os pagamentos são registrados automaticamente quando você\n"
            "vincula uma transação de SAÍDA à categoria deste empréstimo."
        )
        hint.setStyleSheet("color: #2196F3; font-style: italic;")
        history_layout.addWidget(hint)

        self.payments_table = QTableWidget()
        self.payments_table.setColumnCount(4)
        self.payments_table.setHorizontalHeaderLabels([
            "Parcela", "Data", "Valor Pago", "Descrição"
        ])
        self.payments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.payments_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.payments_table.horizontalHeader().setStretchLastSection(True)
        self.payments_table.setMinimumHeight(180)
        history_layout.addWidget(self.payments_table)

        history_group.setLayout(history_layout)
        layout.addWidget(history_group)

        # ── Botões ───────────────────────────────────────────
        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 Atualizar Pagamentos")
        self.refresh_btn.clicked.connect(self.load_data)

        self.desconto_btn = QPushButton("💵 Registrar valor descontado")
        self.desconto_btn.clicked.connect(self.registrar_desconto)

        self.close_btn = QPushButton("Fechar")
        self.close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.desconto_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def registrar_desconto(self):
        """Valor já descontado do que o usuário recebeu (sem nova despesa)"""
        from interface.dialogs.desconto_dialog import DescontoDialog
        p = self.parent()
        if DescontoDialog(self, p.db_connection, p.user_id,
                          self.loan_id).exec_():
            self.load_data()

    def load_data(self):
        """Carrega os dados do empréstimo sincronizando pagamentos"""
        # Sincronizar pagamentos antes de carregar
        sync_loan_payments(
            self.parent().db_connection, self.loan_id
        )

        status = get_loan_status(
            self.parent().db_connection, self.loan_id
        )
        if not status:
            return

        loan = status['loan']
        self.title_label.setText(f"💳 {loan['name']}")

        # Progresso
        progress = int(status['progress'])
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"{progress}%")

        if progress >= 100:
            self.progress_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #2ecc71; }"
            )
        elif progress >= 50:
            self.progress_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #f39c12; }"
            )
        else:
            self.progress_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #e74c3c; }"
            )

        self.paid_label.setText(
            f"✅ Pago: R$ {status['total_paid']:,.2f}"
        )
        self.remaining_label.setText(
            f"⏳ Restante: R$ {status['remaining_amount']:,.2f}"
        )
        self.installments_label.setText(
            f"📋 Parcelas: {status['installments_paid']}/"
            f"{loan['num_installments']}"
        )

        # Detalhes
        self.reason_label.setText(loan['reason'] or "Não informado")
        self.amount_label.setText(f"R$ {loan['total_amount']:,.2f}")
        self.interest_label.setText(
            f"{loan['interest_rate']:.2f}% ao mês"
        )
        self.installment_value_label.setText(
            f"R$ {loan['installment_amount']:,.2f}"
        )
        self.discount_label.setText(f"R$ {loan['discount']:,.2f}")
        self.final_label.setText(f"R$ {loan['final_amount']:,.2f}")
        self.start_date_label.setText(loan['start_date'])

        status_text = (
            "✅ Quitado" if loan['status'] == 'quitado'
            else "🔄 Ativo"
        )
        self.status_label.setText(status_text)

        # ── Histórico completo:
        #    1) Transação de RECEBIMENTO no topo
        #    2) Transações de PAGAMENTO abaixo ───────────────
        rows = []

        # 1) Buscar transação de recebimento vinculada
        if loan['transaction_id']:
            recebimento = self.parent().db_connection.execute(
                """SELECT id, date, amount,
                          description, transaction_type
                   FROM transactions
                   WHERE id = ?""",
                (loan['transaction_id'],)
            ).fetchone()

            if recebimento:
                rows.append({
                    'tipo':        'recebimento',
                    'numero':      '—',
                    'data':        recebimento['date'],
                    'valor':       recebimento['amount'],
                    'descricao':   recebimento['description'],
                    'trans_type':  recebimento['transaction_type']
                })

        # 2) Buscar pagamentos registrados
        payments = self.parent().db_connection.execute(
            """SELECT lp.installment_number,
                      lp.payment_date,
                      lp.amount,
                      lp.notes,
                      t.description  AS trans_desc,
                      t.transaction_type
               FROM loan_payments lp
               LEFT JOIN transactions t
                      ON lp.transaction_id = t.id
               WHERE lp.loan_id = ?
               ORDER BY lp.installment_number ASC""",
            (self.loan_id,)
        ).fetchall()

        for p in payments:
            rows.append({
                'tipo':       'pagamento',
                'numero':     f"Parcela {p['installment_number']}",
                'data':       p['payment_date'],
                'valor':      p['amount'],
                'descricao':  p['notes'] or p['trans_desc'] or "",
                'trans_type': p['transaction_type']
            })

        # ── Preencher tabela ──────────────────────────────────
        self.payments_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            if row['tipo'] == 'recebimento':
                # Verde = entrada (dinheiro recebido)
                row_color = (
                    QColor("#1B5E20") if self.is_dark_mode
                    else QColor("#E8F5E9")
                )
                numero_item = QTableWidgetItem("📥 Recebimento")
                valor_item  = QTableWidgetItem(
                    f"R$ {row['valor']:,.2f}"
                )
                valor_item.setForeground(QColor('#2ecc71'))
            else:
                # Vermelho = saída (pagamento de parcela)
                row_color = (
                    QColor("#B71C1C") if self.is_dark_mode
                    else QColor("#FFEBEE")
                )
                numero_item = QTableWidgetItem(row['numero'])
                valor_item  = QTableWidgetItem(
                    f"R$ {row['valor']:,.2f}"
                )
                valor_item.setForeground(QColor('#e74c3c'))

            date_item = QTableWidgetItem(row['data'])
            desc_item = QTableWidgetItem(row['descricao'])

            for item in [numero_item, date_item,
                         valor_item, desc_item]:
                item.setBackground(row_color)

            self.payments_table.setItem(i, 0, numero_item)
            self.payments_table.setItem(i, 1, date_item)
            self.payments_table.setItem(i, 2, valor_item)
            self.payments_table.setItem(i, 3, desc_item)

        self.payments_table.resizeColumnsToContents()

        if not rows:
            self.payments_table.setRowCount(1)
            msg_item = QTableWidgetItem(
                "Nenhum dado encontrado. "
                "Vincule transações de SAÍDA à categoria "
                "do empréstimo para registrar pagamentos."
            )
            msg_item.setForeground(QColor('gray'))
            self.payments_table.setItem(0, 0, msg_item)
            self.payments_table.setSpan(0, 0, 1, 4)

    def apply_theme(self):
        """Aplica o tema ao diálogo"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
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
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 5px;
                    text-align: center; background-color: #2d3436;
                    color: #ecf0f1;
                }
            """)
            self.close_btn.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
            self.refresh_btn.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { color: #333; }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
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
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 5px;
                    text-align: center;
                }
            """)
            self.close_btn.setStyleSheet(
                "background-color: #f44336; color: white;"
            )
            self.refresh_btn.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )


class LoansManagerDialog(QDialog):
    """Diálogo principal para gerenciar todos os empréstimos"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciador de Empréstimos")
        self.setMinimumSize(800, 550)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self._build_ui()
        self.load_loans()
        self.apply_theme()

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout()

        # ── Cabeçalho ────────────────────────────────────────
        header_layout = QHBoxLayout()
        title = QLabel("💳 Gerenciador de Empréstimos")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.new_loan_btn = QPushButton("➕ Novo Empréstimo")
        self.new_loan_btn.clicked.connect(self.add_loan)
        header_layout.addWidget(self.new_loan_btn)
        layout.addLayout(header_layout)

        # ── Resumo geral ──────────────────────────────────────
        self.summary_group = QGroupBox("Resumo Geral")
        summary_layout = QHBoxLayout()

        self.total_active_label = QLabel("Empréstimos ativos: 0")
        self.total_debt_label   = QLabel("Dívida restante: R$ 0,00")
        self.total_paid_label   = QLabel("Total pago: R$ 0,00")

        summary_layout.addWidget(self.total_active_label)
        summary_layout.addWidget(self.total_debt_label)
        summary_layout.addWidget(self.total_paid_label)
        self.summary_group.setLayout(summary_layout)
        layout.addWidget(self.summary_group)

        # ── Abas ─────────────────────────────────────────────
        self.tabs = QTabWidget()

        self.active_tab    = QWidget()
        active_layout      = QVBoxLayout(self.active_tab)
        self.active_table  = self._create_loan_table()
        active_layout.addWidget(self.active_table)
        self.tabs.addTab(self.active_tab, "🔄 Em Andamento")

        self.completed_tab   = QWidget()
        completed_layout     = QVBoxLayout(self.completed_tab)
        self.completed_table = self._create_loan_table()
        completed_layout.addWidget(self.completed_table)
        self.tabs.addTab(self.completed_tab, "✅ Quitados")

        layout.addWidget(self.tabs)

        # ── Botões de ação ────────────────────────────────────
        action_layout = QHBoxLayout()

        self.view_btn = QPushButton("👁️ Ver Detalhes")
        self.view_btn.clicked.connect(self.view_loan)

        self.delete_btn = QPushButton("🗑️ Excluir")
        self.delete_btn.clicked.connect(self.delete_loan)

        self.close_btn = QPushButton("Fechar")
        self.close_btn.clicked.connect(self.accept)

        action_layout.addWidget(self.view_btn)
        action_layout.addWidget(self.delete_btn)
        action_layout.addStretch()
        action_layout.addWidget(self.close_btn)
        layout.addLayout(action_layout)

        self.setLayout(layout)

    def _create_loan_table(self) -> QTableWidget:
        """Cria uma tabela padrão para empréstimos"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Nome", "Valor Total", "Pago",
            "Restante", "Parcelas", "Progresso"
        ])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.doubleClicked.connect(self.view_loan)
        return table

    def load_loans(self):
        """Carrega todos os empréstimos sincronizando pagamentos"""
        # Verificar empréstimos quitados
        completed = check_and_complete_loans(
            self.parent().db_connection,
            self.parent().user_id
        )
        if completed:
            for loan in completed:
                QMessageBox.information(
                    self, "Empréstimo Quitado! 🎉",
                    f"Parabéns! O empréstimo '{loan['name']}' "
                    f"foi quitado!\n"
                    f"Ele foi movido para a aba 'Quitados'."
                )

        active_loans = self.parent().db_connection.execute(
            "SELECT * FROM loans WHERE user_id = ? AND status = 'ativo' "
            "ORDER BY name",
            (self.parent().user_id,)
        ).fetchall()

        completed_loans = self.parent().db_connection.execute(
            "SELECT * FROM loans WHERE user_id = ? AND status = 'quitado' "
            "ORDER BY name",
            (self.parent().user_id,)
        ).fetchall()

        self._populate_table(self.active_table, active_loans)
        self._populate_table(self.completed_table, completed_loans)

        # Atualizar resumo
        total_debt   = 0
        total_paid_s = 0

        for loan in active_loans:
            status = get_loan_status(
                self.parent().db_connection, loan['id']
            )
            total_debt   += status.get('remaining_amount', 0)
            total_paid_s += status.get('total_paid', 0)

        self.total_active_label.setText(
            f"Empréstimos ativos: {len(active_loans)}"
        )
        self.total_debt_label.setText(
            f"Dívida restante: R$ {total_debt:,.2f}"
        )
        self.total_paid_label.setText(
            f"Total pago: R$ {total_paid_s:,.2f}"
        )

    def _populate_table(self, table, loans):
        """Preenche uma tabela com os empréstimos"""
        table.setRowCount(len(loans))

        for i, loan in enumerate(loans):
            status = get_loan_status(
                self.parent().db_connection, loan['id']
            )

            name_item = QTableWidgetItem(loan['name'])
            name_item.setData(Qt.UserRole, loan['id'])
            table.setItem(i, 0, name_item)

            table.setItem(
                i, 1,
                QTableWidgetItem(f"R$ {loan['final_amount']:,.2f}")
            )
            table.setItem(
                i, 2,
                QTableWidgetItem(f"R$ {status['total_paid']:,.2f}")
            )
            table.setItem(
                i, 3,
                QTableWidgetItem(
                    f"R$ {status['remaining_amount']:,.2f}"
                )
            )
            table.setItem(
                i, 4,
                QTableWidgetItem(
                    f"{status['installments_paid']}/"
                    f"{loan['num_installments']}"
                )
            )

            # Barra de progresso
            progress_widget = QWidget()
            p_layout        = QHBoxLayout(progress_widget)
            p_bar           = QProgressBar()
            p_bar.setMaximum(100)
            p_bar.setValue(int(status['progress']))
            p_bar.setFormat(f"{int(status['progress'])}%")
            p_layout.addWidget(p_bar)
            p_layout.setContentsMargins(4, 4, 4, 4)
            table.setCellWidget(i, 5, progress_widget)

        table.resizeColumnsToContents()

    def get_selected_loan_id(self):
        """Retorna o ID do empréstimo selecionado na aba atual"""
        current_table = (
            self.active_table
            if self.tabs.currentIndex() == 0
            else self.completed_table
        )
        row = current_table.currentRow()
        if row >= 0:
            item = current_table.item(row, 0)
            if item:
                return item.data(Qt.UserRole)
        return None

    def view_loan(self):
        """Abre os detalhes do empréstimo selecionado"""
        loan_id = self.get_selected_loan_id()
        if loan_id:
            dialog = LoanDetailDialog(self.parent(), loan_id)
            dialog.exec_()
            self.load_loans()
        else:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione um empréstimo para ver os detalhes."
            )

    def add_loan(self):
        """Abre o diálogo para adicionar empréstimo"""
        dialog = AddLoanDialog(self.parent())
        if dialog.exec_() == QDialog.Accepted:
            self.load_loans()
            self.parent().load_categories()

    def delete_loan(self):
        """Exclui o empréstimo selecionado"""
        loan_id = self.get_selected_loan_id()
        if not loan_id:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione um empréstimo para excluir."
            )
            return

        loan = self.parent().db_connection.execute(
            'SELECT * FROM loans WHERE id = ?', (loan_id,)
        ).fetchone()

        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Excluir o empréstimo '{loan['name']}'?\n\n"
            f"⚠️ Os pagamentos vinculados serão removidos.\n"
            f"As transações do banco NÃO serão afetadas.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.parent().db_connection.execute(
                    'DELETE FROM loan_payments WHERE loan_id = ?',
                    (loan_id,)
                )
                if loan['category_id']:
                    self.parent().db_connection.execute(
                        'DELETE FROM categories WHERE id = ?',
                        (loan['category_id'],)
                    )
                self.parent().db_connection.execute(
                    'DELETE FROM loans WHERE id = ?', (loan_id,)
                )
                self.parent().db_connection.commit()
                self.load_loans()
                self.parent().load_categories()

            except Exception as e:
                QMessageBox.critical(
                    self, "Erro",
                    f"Não foi possível excluir: {str(e)}"
                )

    def apply_theme(self):
        """Aplica o tema ao diálogo"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
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
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 5px;
                    text-align: center; background-color: #2d3436;
                }
                QProgressBar::chunk { background-color: #2ecc71; }
            """)
            self.new_loan_btn.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.delete_btn.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { color: #333; }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                }
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
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk { background-color: #4CAF50; }
            """)
            self.new_loan_btn.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.delete_btn.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

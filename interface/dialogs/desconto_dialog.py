"""
Registrar valor descontado de um empréstimo (ex.: parcela já descontada do
salário). Abate o empréstimo sem criar uma despesa nova.
"""
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QDoubleSpinBox, QDateEdit, QPushButton, QMessageBox
)
from PyQt5.QtCore import QDate

from modulos.loans import get_loan_status, check_and_complete_loans


class DescontoDialog(QDialog):

    def __init__(self, parent, db, user_id, loan_id):
        super().__init__(parent)
        self.db, self.user_id, self.loan_id = db, user_id, loan_id
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)
        self.setWindowTitle('Registrar valor descontado')
        self.setMinimumWidth(480)

        self.loan = db.execute('SELECT * FROM loans WHERE id=?',
                               (loan_id,)).fetchone()
        lay = QVBoxLayout(self)
        hint = QLabel(
            'Use quando o valor que você recebe já vem com a parcela '
            'descontada.\nEscolha a entrada recebida e informe quanto foi '
            'descontado. O empréstimo é abatido sem criar uma nova despesa.')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #2196F3; font-style: italic;')
        lay.addWidget(hint)

        form = QFormLayout()
        self.combo = QComboBox()
        self.combo.addItem('Sem vincular a uma transação', None)
        for t in db.execute(
                "SELECT id, date, description, amount FROM transactions "
                "WHERE user_id=? AND transaction_type='entrada' "
                "ORDER BY date DESC, id DESC LIMIT 120", (user_id,)):
            self.combo.addItem(
                f"{t['date'][8:10]}/{t['date'][5:7]}/{t['date'][:4]} · "
                f"{t['description'][:38]} · R$ {t['amount']:,.2f}", dict(t))
        if self.combo.count() > 1:
            self.combo.setCurrentIndex(1)
        self.combo.currentIndexChanged.connect(self._ao_escolher)
        self.valor = QDoubleSpinBox()
        self.valor.setRange(0.01, 99999999)
        self.valor.setDecimals(2)
        self.valor.setPrefix('R$ ')
        self.valor.setValue(float(self.loan['installment_amount'] or 0.01))
        self.data = QDateEdit(QDate.currentDate())
        self.data.setCalendarPopup(True)
        self.data.setDisplayFormat('dd/MM/yyyy')
        form.addRow('Transação recebida:', self.combo)
        form.addRow('Valor descontado:', self.valor)
        form.addRow('Data do desconto:', self.data)
        lay.addLayout(form)
        self._ao_escolher()

        row = QHBoxLayout()
        ok = QPushButton('Registrar desconto')
        ok.clicked.connect(self.salvar)
        cancel = QPushButton('Cancelar')
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.apply_theme()

    def _ao_escolher(self):
        t = self.combo.currentData()
        if t:
            self.data.setDate(QDate.fromString(t['date'], 'yyyy-MM-dd'))

    def salvar(self):
        if self.loan['status'] == 'quitado':
            QMessageBox.information(self, 'Aviso', 'Empréstimo já quitado.')
            return
        v = round(self.valor.value(), 2)
        t = self.combo.currentData()
        data = self.data.date().toString('yyyy-MM-dd')
        nota = 'Desconto informado manualmente'
        if t:
            marca = f"(tx #{t['id']})"
            if self.db.execute(
                    'SELECT 1 FROM loan_payments WHERE loan_id=? AND notes '
                    'LIKE ?', (self.loan_id, f'%{marca}%')).fetchone():
                QMessageBox.warning(
                    self, 'Aviso', 'Esse recebimento já tem desconto '
                    'registrado neste empréstimo.')
                return
            nota = f"Desconto em: {t['description'][:80]} {marca}"
        st = get_loan_status(self.db, self.loan_id)
        if v > st['remaining_amount'] + 0.01:
            QMessageBox.warning(
                self, 'Aviso', f"Valor maior que o restante "
                f"(R$ {st['remaining_amount']:,.2f}).")
            return
        n = self.db.execute(
            'SELECT COALESCE(MAX(installment_number),0) FROM loan_payments '
            'WHERE loan_id=?', (self.loan_id,)).fetchone()[0] + 1
        self.db.execute(
            'INSERT INTO loan_payments(loan_id, transaction_id, payment_date, '
            'amount, installment_number, notes) VALUES(?,NULL,?,?,?,?)',
            (self.loan_id, data, v, n, nota))
        self.db.commit()
        check_and_complete_loans(self.db, self.user_id)
        self.accept()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QComboBox, QDoubleSpinBox, QDateEdit {
                    background: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; padding: 4px; }
                QPushButton { background: #3498db; color: white;
                    border-radius: 4px; padding: 7px 14px; font-weight: bold; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton { background: #4CAF50; color: white;
                    border-radius: 4px; padding: 7px 14px; font-weight: bold; }
            """)

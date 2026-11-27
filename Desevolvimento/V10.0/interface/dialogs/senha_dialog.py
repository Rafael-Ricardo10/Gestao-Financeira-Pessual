"""
Diálogo "Alterar senha": pede a senha atual e a nova (duas vezes).
A troca em si é feita por modulos.troca_senha (os dados são mantidos).
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox
)

from modulos import identidade


class AlterarSenhaDialog(QDialog):

    def __init__(self, parent, usuario):
        super().__init__(parent)
        self.usuario = usuario
        self.atual = self.nova = ''
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)
        self.setWindowTitle('Alterar senha')
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)

        info = QLabel(
            'Seus dados são mantidos. A senha gera as chaves da conta, então '
            'o aplicativo vai migrar os dados para as chaves novas e '
            'reiniciar.\n\n'
            'Os OUTROS aparelhos não mudam sozinhos (a senha nova nunca '
            'viaja pela rede antiga). Em cada um deles, use "Alterar senha" '
            'com a mesma senha nova, ou saia da conta e entre com a nova: '
            'os dados chegam por sincronização.\n\n'
            f'Usuário: {usuario}')
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        self.e_atual = QLineEdit()
        self.e_nova = QLineEdit()
        self.e_conf = QLineEdit()
        for w in (self.e_atual, self.e_nova, self.e_conf):
            w.setEchoMode(QLineEdit.Password)
            w.setMinimumHeight(30)
        form.addRow('Senha atual:', self.e_atual)
        form.addRow('Senha nova:', self.e_nova)
        form.addRow('Confirmar senha nova:', self.e_conf)
        lay.addLayout(form)

        dica = QLabel('Use uma senha LONGA: uma frase de 4 palavras ou '
                      f'{identidade.MIN_SENHA}+ caracteres. Não existe '
                      'recuperação de senha: guarde-a e mantenha um backup.')
        dica.setWordWrap(True)
        dica.setStyleSheet('color: #f39c12; font-size: 11px;')
        lay.addWidget(dica)

        row = QHBoxLayout()
        ok = QPushButton('Alterar senha')
        ok.clicked.connect(self._confirmar)
        cancel = QPushButton('Cancelar')
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.apply_theme()

    def _confirmar(self):
        atual, nova = self.e_atual.text(), self.e_nova.text()
        if not atual or not nova:
            QMessageBox.warning(self, 'Alterar senha',
                                'Preencha a senha atual e a senha nova.')
            return
        if nova != self.e_conf.text():
            QMessageBox.warning(self, 'Alterar senha',
                                'A confirmação não confere com a senha nova.')
            return
        if nova == atual:
            QMessageBox.warning(self, 'Alterar senha',
                                'A senha nova precisa ser diferente.')
            return
        erro = identidade.validar(self.usuario, nova)
        if erro:
            QMessageBox.warning(self, 'Alterar senha', erro)
            return
        self.atual, self.nova = atual, nova
        self.accept()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QLineEdit { background: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; padding: 4px; }
                QPushButton { background: #3498db; color: white;
                    border-radius: 4px; padding: 7px 14px; font-weight: bold; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton { background: #4CAF50; color: white;
                    border-radius: 4px; padding: 7px 14px; font-weight: bold; }
            """)

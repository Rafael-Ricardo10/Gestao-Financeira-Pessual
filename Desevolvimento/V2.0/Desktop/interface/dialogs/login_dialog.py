"""
Login do app: usuário + senha, e pronto.

Não há "cadastro": o usuário e a senha geram as chaves da conta, iguais em
qualquer aparelho. Primeiro acesso neste aparelho = confirmar a senha; se a
conta já existe em outro aparelho, os dados chegam por sincronização.
"""
import os
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QMessageBox, QFileDialog, QInputDialog, QApplication
)
from PyQt5.QtCore import Qt

from modulos import identidade, bd_seguro


def _contas_path(pasta):
    return os.path.join(pasta, 'contas.json')


def contas_locais(pasta):
    try:
        with open(_contas_path(pasta), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def lembrar_conta(pasta, chaves):
    """Guarda só o NOME (nunca a senha) para distinguir 'senha errada' de
    'primeiro acesso'."""
    d = contas_locais(pasta)
    d[identidade.normalizar_usuario(chaves.usuario)] = chaves.net_id
    with open(_contas_path(pasta), 'w', encoding='utf-8') as f:
        json.dump(d, f)


class LoginDialog(QDialog):

    def __init__(self, pasta='dados', parent=None):
        super().__init__(parent)
        self.pasta = pasta
        self.chaves = None
        self.manter = True
        self.novo = False
        self.backup = None            # (bytes, frase)
        self.setWindowTitle('RRFS Finanças · Entrar')
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)

        t = QLabel('RRFS Finanças')
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet('font-size: 24px; font-weight: bold;')
        lay.addWidget(t)
        sub = QLabel('Entre com seu usuário e senha. Funciona offline e '
                     'sincroniza com seus outros aparelhos.')
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet('color: gray;')
        lay.addWidget(sub)

        self.e_user = QLineEdit()
        self.e_user.setPlaceholderText('Usuário')
        self.e_senha = QLineEdit()
        self.e_senha.setPlaceholderText('Senha')
        self.e_senha.setEchoMode(QLineEdit.Password)
        self.e_conf = QLineEdit()
        self.e_conf.setPlaceholderText('Confirme a senha')
        self.e_conf.setEchoMode(QLineEdit.Password)
        self.e_conf.hide()
        for w in (self.e_user, self.e_senha, self.e_conf):
            w.setMinimumHeight(32)
            w.returnPressed.connect(self.entrar)
            lay.addWidget(w)

        self.l_info = QLabel()
        self.l_info.setWordWrap(True)
        self.l_info.setStyleSheet('color: #f39c12;')
        self.l_info.hide()
        lay.addWidget(self.l_info)

        self.c_manter = QCheckBox('Manter conectado neste aparelho')
        self.c_manter.setChecked(True)
        lay.addWidget(self.c_manter)

        self.b_ok = QPushButton('Entrar')
        self.b_ok.setMinimumHeight(36)
        self.b_ok.clicked.connect(self.entrar)
        lay.addWidget(self.b_ok)

        row = QHBoxLayout()
        b_bk = QPushButton('Tenho um backup (.rrfs)…')
        b_bk.setFlat(True)
        b_bk.clicked.connect(self.escolher_backup)
        b_sair = QPushButton('Sair')
        b_sair.setFlat(True)
        b_sair.clicked.connect(self.reject)
        row.addWidget(b_bk)
        row.addStretch()
        row.addWidget(b_sair)
        lay.addLayout(row)

        self.l_cripto = QLabel()
        self.l_cripto.setWordWrap(True)
        self.l_cripto.setStyleSheet('color: gray; font-size: 11px;')
        self.l_cripto.setText(
            '🔒 Dados em disco cifrados (AES-256).' if bd_seguro.CRIPTO_REPOUSO
            else '⚠ SQLCipher não instalado: os dados ficam legíveis no '
                 'disco. Instale com: pip install sqlcipher3-binary')
        lay.addWidget(self.l_cripto)

        users = list(contas_locais(pasta))
        if users:
            self.e_user.setText(users[-1])
            self.e_senha.setFocus()

    def escolher_backup(self):
        arq, _ = QFileDialog.getOpenFileName(
            self, 'Backup do RRFS', '', 'Backup RRFS (*.rrfs)')
        if not arq:
            return
        frase, ok = QInputDialog.getText(
            self, 'Backup', 'Frase do backup:', QLineEdit.Password)
        if not ok:
            return
        try:
            with open(arq, 'rb') as f:
                blob = f.read()
            identidade.abrir_backup(blob, frase)       # valida agora
        except Exception as e:
            QMessageBox.warning(self, 'Backup', str(e))
            return
        self.backup = (blob, frase)
        self.l_info.setText('✔ Backup carregado: será importado ao entrar. '
                            'Use o usuário e a senha que quiser (pode ser '
                            'um login novo).')
        self.l_info.show()

    def entrar(self):
        u, s = self.e_user.text().strip(), self.e_senha.text()
        if not u or not s:
            QMessageBox.warning(self, 'Entrar', 'Informe usuário e senha.')
            return
        self.setCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            ch = identidade.derivar(u, s)
        finally:
            self.unsetCursor()
        existe = os.path.exists(os.path.join(self.pasta, f'{ch.net_id}.db'))
        if existe:
            return self._concluir(ch, False)
        conhecida = contas_locais(self.pasta).get(
            identidade.normalizar_usuario(u))
        if conhecida and conhecida != ch.net_id:
            QMessageBox.warning(self, 'Entrar', 'Senha incorreta.')
            return
        # primeiro acesso neste aparelho
        erro = identidade.validar(u, s)
        if erro:
            QMessageBox.warning(self, 'Entrar', erro)
            return
        if self.e_conf.isHidden():
            self.e_conf.show()
            self.e_conf.setFocus()
            self.b_ok.setText('Continuar')
            self.l_info.setText(
                'Primeiro acesso neste aparelho. Confirme a senha.\n'
                'Se você já tem conta em outro aparelho, use o MESMO '
                'usuário e senha: seus dados chegam por sincronização.\n'
                'Não existe recuperação de senha (ela gera a chave dos '
                'dados): guarde-a e faça backup.')
            self.l_info.show()
            return
        if self.e_conf.text() != s:
            QMessageBox.warning(self, 'Entrar', 'As senhas não conferem.')
            return
        self._concluir(ch, True)

    def _concluir(self, ch, novo):
        self.chaves, self.novo = ch, novo
        self.manter = self.c_manter.isChecked()
        self.accept()

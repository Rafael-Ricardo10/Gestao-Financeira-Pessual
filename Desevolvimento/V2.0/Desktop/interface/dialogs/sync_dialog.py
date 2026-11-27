"""
Rede de aparelhos: situação, aparelhos da conta, backup e nó manual.
"""
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QMessageBox, QGroupBox, QFormLayout, QInputDialog, QLineEdit,
    QFileDialog
)
from PyQt5.QtCore import Qt, QObject, QTimer, pyqtSignal

from modulos import backup


class SyncBridge(QObject):
    """Leva avisos das threads de rede para a thread da interface."""
    alterado = pyqtSignal()    # chegaram dados novos de outro aparelho
    estado = pyqtSignal()      # conexão / pendências mudaram


class SyncDialog(QDialog):

    def __init__(self, parent, rede):
        super().__init__(parent)
        self.rede = rede
        self.pai = parent
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)
        self.setWindowTitle('Rede de aparelhos')
        self.setMinimumWidth(560)
        self._build()
        self.apply_theme()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)

    def _build(self):
        lay = QVBoxLayout(self)
        g = QGroupBox('Situação')
        f = QFormLayout()
        self.l_conta, self.l_nome = QLabel(), QLabel()
        self.l_rede, self.l_pares = QLabel(), QLabel()
        self.l_pend, self.l_ultimo = QLabel(), QLabel()
        self.l_cripto = QLabel()
        self.l_pares.setStyleSheet('font-weight: bold;')
        f.addRow('Conta:', self.l_conta)
        f.addRow('Este aparelho:', self.l_nome)
        f.addRow('Rede Tox:', self.l_rede)
        f.addRow('Aparelhos online:', self.l_pares)
        f.addRow('Pendentes de envio:', self.l_pend)
        f.addRow('Última sincronização:', self.l_ultimo)
        f.addRow('Segurança:', self.l_cripto)
        g.setLayout(f)
        lay.addWidget(g)

        dica = QLabel('Entre com o mesmo usuário e senha em outro aparelho '
                      '(app ou servidor): eles se encontram sozinhos, pela '
                      'internet ou pela rede local, mesmo sem o servidor.')
        dica.setWordWrap(True)
        dica.setStyleSheet('color: gray;')
        lay.addWidget(dica)

        self.lista = QListWidget()
        self.lista.setMinimumHeight(110)
        lay.addWidget(QLabel('Aparelhos da conta:'))
        lay.addWidget(self.lista)

        r1 = QHBoxLayout()
        for txt, fn in (('Sincronizar agora', self.sincronizar),
                        ('Renomear este aparelho', self.renomear),
                        ('Nó manual…', self.no_manual)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            r1.addWidget(b)
        lay.addLayout(r1)
        r2 = QHBoxLayout()
        for txt, fn in (('Exportar backup…', self.exportar),
                        ('Importar backup…', self.importar_backup)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            r2.addWidget(b)
        lay.addLayout(r2)

        self.l_eventos = QLabel()
        self.l_eventos.setStyleSheet('color: gray; font-size: 11px;')
        self.l_eventos.setWordWrap(True)
        lay.addWidget(self.l_eventos)

        r3 = QHBoxLayout()
        b_sair = QPushButton('Sair desta conta')
        b_sair.clicked.connect(self.sair_conta)
        b_fechar = QPushButton('Fechar')
        b_fechar.clicked.connect(self.accept)
        r3.addWidget(b_sair)
        r3.addStretch()
        r3.addWidget(b_fechar)
        lay.addLayout(r3)

    # ── ações ────────────────────────────────────────────────

    def sincronizar(self):
        self.rede.sincronizar_agora()

    def renomear(self):
        n, ok = QInputDialog.getText(self, 'Nome do aparelho', 'Nome:',
                                     QLineEdit.Normal, self.rede.config['nome'])
        if ok and n.strip():
            self.rede.renomear(n)
            self.refresh()

    def no_manual(self):
        meu = self.rede.meu_bootstrap()
        msg = ('Para redes isoladas ou sub-redes: informe o IP e a chave de '
               'um aparelho alcançável da sua conta.\n\n')
        if meu:
            msg += (f"Este aparelho como nó:\nporta {meu['porta']}\n"
                    f"chave {meu['dht']}\n\n")
        msg += 'Formato: IP:PORTA:CHAVE'
        t, ok = QInputDialog.getText(self, 'Nó manual', msg)
        if not ok or not t.strip():
            return
        try:
            ip, porta, dht = t.strip().split(':')
        except ValueError:
            QMessageBox.warning(self, 'Nó manual', 'Use IP:PORTA:CHAVE')
            return
        r = self.rede.adicionar_no(ip, porta, dht)
        if not r.get('sucesso'):
            QMessageBox.warning(self, 'Nó manual', r.get('erro', 'Erro'))

    def exportar(self):
        frase, ok = QInputDialog.getText(
            self, 'Exportar backup',
            'Escolha uma frase para cifrar o backup (mín. 8 caracteres).\n'
            'Guarde-a: sem ela o arquivo não abre.', QLineEdit.Password)
        if not ok:
            return
        try:
            blob, n = backup.exportar(self.pai.db_connection, frase)
        except ValueError as e:
            QMessageBox.warning(self, 'Backup', str(e))
            return
        nome = 'rrfs-backup-' + datetime.now().strftime('%Y%m%d-%H%M') + '.rrfs'
        arq, _ = QFileDialog.getSaveFileName(self, 'Salvar backup', nome,
                                             'Backup RRFS (*.rrfs)')
        if arq:
            with open(arq, 'wb') as f:
                f.write(blob)
            QMessageBox.information(self, 'Backup',
                                    f'Backup salvo ({n} registros).')

    def importar_backup(self):
        arq, _ = QFileDialog.getOpenFileName(
            self, 'Importar backup', '', 'Backup RRFS (*.rrfs)')
        if not arq:
            return
        frase, ok = QInputDialog.getText(self, 'Importar backup',
                                         'Frase do backup:', QLineEdit.Password)
        if not ok:
            return
        try:
            with open(arq, 'rb') as f:
                n = backup.importar(self.pai.db_connection, f.read(), frase)
        except Exception as e:
            QMessageBox.warning(self, 'Backup', str(e))
            return
        self.pai._sync_refrescar()
        QMessageBox.information(self, 'Backup',
                                f'Backup importado ({n} registros).')

    def sair_conta(self):
        if QMessageBox.question(
                self, 'Sair da conta',
                'Sair desta conta neste aparelho?\n\nOs dados continuam '
                'cifrados no disco e voltam ao entrar de novo.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) == QMessageBox.Yes:
            self.accept()
            self.pai.sair_da_conta()

    # ── tela ─────────────────────────────────────────────────

    def refresh(self):
        e = self.rede.estado()
        self.l_conta.setText(self.rede.chaves.usuario or '—')
        self.l_nome.setText(e['nome'])
        self.l_rede.setText(e['rede'] if e['rodando'] else (
            'libtoxcore não encontrada' if not e['lib_ok'] else 'Desligado'))
        n = e['pares_online']
        self.l_pares.setText(f'{n} online' if n else 'nenhum (trabalhando offline)')
        self.l_pares.setStyleSheet(
            f"font-weight: bold; color: {'#2ecc71' if n else '#f39c12'};")
        self.l_pend.setText(str(e['pendentes']))
        self.l_ultimo.setText(
            datetime.fromtimestamp(e['ultimo_sync']).strftime('%d/%m/%Y %H:%M:%S')
            if e['ultimo_sync'] else '—')
        self.l_cripto.setText(
            'Rede cifrada ponta a ponta · dados em disco ' +
            ('cifrados (AES-256)' if e['cripto_repouso']
             else 'SEM criptografia (instale sqlcipher3-binary)'))
        self.lista.clear()
        for d in e['dispositivos']:
            self.lista.addItem(f"{'🟢' if d['online'] else '⚪'} {d['nome']}")
        if not e['dispositivos']:
            self.lista.addItem('Nenhum outro aparelho visto ainda.')
        self.l_eventos.setText('\n'.join(e['eventos']))

    def done(self, r):
        self.timer.stop()
        super().done(r)

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QGroupBox { border: 1px solid #4b6584; margin-top: 10px;
                            padding-top: 10px; color: #ecf0f1; }
                QListWidget { background: #2d3436; color: #ecf0f1;
                              border: 1px solid #4b6584; }
                QPushButton { background: #3498db; color: white;
                              border-radius: 4px; padding: 7px 14px;
                              font-weight: bold; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton { background: #4CAF50; color: white;
                              border-radius: 4px; padding: 7px 14px;
                              font-weight: bold; }
            """)

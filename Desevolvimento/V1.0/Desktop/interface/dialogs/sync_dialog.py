"""
Conexão com o servidor: colar a chave, acompanhar o status e sincronizar.
"""
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QMessageBox, QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt, QObject, QTimer, pyqtSignal


class SyncBridge(QObject):
    """Leva avisos das threads de sincronização para a thread da interface."""
    alterado = pyqtSignal()    # chegaram dados novos do servidor
    estado = pyqtSignal()      # conexão / pendências mudaram


class SyncDialog(QDialog):

    def __init__(self, parent, sync):
        super().__init__(parent)
        self.sync = sync
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)
        self.setWindowTitle('Conexão com o servidor')
        self.setMinimumWidth(560)
        self._build()
        self.apply_theme()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)

    def _build(self):
        lay = QVBoxLayout(self)

        self.status_group = QGroupBox('Situação')
        form = QFormLayout()
        self.l_status = QLabel()
        self.l_status.setStyleSheet('font-weight: bold;')
        self.l_conta = QLabel()
        self.l_rede = QLabel()
        self.l_pend = QLabel()
        self.l_ultimo = QLabel()
        form.addRow('Servidor:', self.l_status)
        form.addRow('Conta:', self.l_conta)
        form.addRow('Rede Tox:', self.l_rede)
        form.addRow('Pendentes de envio:', self.l_pend)
        form.addRow('Última sincronização:', self.l_ultimo)
        self.status_group.setLayout(form)
        lay.addWidget(self.status_group)

        # ── não pareado ──
        self.box_parear = QGroupBox('Conectar a um servidor')
        v = QVBoxLayout(self.box_parear)
        v.addWidget(QLabel(
            '1) No servidor (web): Configurações > copie a sua chave.\n'
            '2) Cole a chave abaixo e clique em Conectar.\n'
            '3) No servidor, aceite o dispositivo que aparecer como pendente.\n\n'
            'A mesma chave serve para todos os seus aplicativos.\n'
            'Enquanto isso o app continua funcionando offline normalmente.'))
        self.t_chave = QPlainTextEdit()
        self.t_chave.setPlaceholderText('RRFS1-…')
        self.t_chave.setFixedHeight(70)
        v.addWidget(self.t_chave)
        self.b_conectar = QPushButton('Conectar')
        self.b_conectar.clicked.connect(self.conectar)
        v.addWidget(self.b_conectar)
        lay.addWidget(self.box_parear)

        # ── pareado ──
        self.box_ok = QGroupBox('Sincronização')
        h = QHBoxLayout(self.box_ok)
        self.b_sync = QPushButton('Sincronizar agora')
        self.b_sync.clicked.connect(self.sincronizar)
        self.b_desc = QPushButton('Desconectar do servidor')
        self.b_desc.clicked.connect(self.desconectar)
        h.addWidget(self.b_sync)
        h.addStretch()
        h.addWidget(self.b_desc)
        lay.addWidget(self.box_ok)

        self.l_eventos = QLabel()
        self.l_eventos.setStyleSheet('color: gray; font-size: 11px;')
        self.l_eventos.setWordWrap(True)
        lay.addWidget(self.l_eventos)

        close = QPushButton('Fechar')
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignRight)

    # ── ações ────────────────────────────────────────────────

    def conectar(self):
        self.b_conectar.setEnabled(False)
        try:
            r = self.sync.parear(self.t_chave.toPlainText())
        finally:
            self.b_conectar.setEnabled(True)
        if r.get('sucesso'):
            self.t_chave.clear()
            QMessageBox.information(self, 'Pedido enviado', r['mensagem'])
        else:
            QMessageBox.warning(self, 'Não foi possível conectar',
                                r.get('erro', 'Erro desconhecido'))
        self.refresh()

    def sincronizar(self):
        self.sync.sincronizar_agora()

    def desconectar(self):
        if QMessageBox.question(
                self, 'Desconectar',
                'Desconectar deste servidor?\n\nSeus dados locais continuam '
                'no app, mas deixam de sincronizar.\n(Remova também o '
                'dispositivo na interface web do servidor.)',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) == QMessageBox.Yes:
            self.sync.desparear()
            self.refresh()

    # ── tela ─────────────────────────────────────────────────

    def refresh(self):
        e = self.sync.estado()
        if not e['lib_ok']:
            txt, cor = 'libtoxcore não encontrada neste computador', '#e74c3c'
        elif not e['pareado']:
            txt, cor = 'Não conectado (modo local)', '#888'
        elif not e['aprovado']:
            txt, cor = 'Aguardando aprovação no servidor…', '#f39c12'
        elif e['servidor_online']:
            txt, cor = 'Online', '#2ecc71'
        else:
            txt, cor = 'Offline (será sincronizado ao voltar)', '#f39c12'
        self.l_status.setText(txt)
        self.l_status.setStyleSheet(f'font-weight: bold; color: {cor};')
        self.l_conta.setText(e['conta'] or '—')
        self.l_rede.setText(e['rede'] if e['rodando'] else 'Desligado')
        self.l_pend.setText(str(e['pendentes']) if e['pareado'] else '—')
        self.l_ultimo.setText(
            datetime.fromtimestamp(e['ultimo_sync']).strftime('%d/%m/%Y %H:%M:%S')
            if e['ultimo_sync'] else '—')
        self.box_parear.setVisible(not e['pareado'])
        self.box_ok.setVisible(e['pareado'])
        self.b_sync.setEnabled(e['servidor_online'])
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
                QGroupBox::title { subcontrol-origin: margin; left: 8px; }
                QPlainTextEdit { background: #2d3436; color: #ecf0f1;
                                 border: 1px solid #4b6584; }
                QPushButton { background: #3498db; color: white;
                              border-radius: 4px; padding: 7px 14px;
                              font-weight: bold; }
                QPushButton:disabled { background: #4b6584; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton { background: #4CAF50; color: white;
                              border-radius: 4px; padding: 7px 14px;
                              font-weight: bold; }
                QPushButton:disabled { background: #bbb; }
            """)

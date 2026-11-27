"""
Rede de aparelhos: situação, aparelhos da conta (latência, IP local,
desconexão remota), diagnóstico de portas/firewall, backup e nó manual.
"""
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QGroupBox, QFormLayout, QInputDialog,
    QLineEdit, QFileDialog, QApplication
)
from PyQt5.QtCore import Qt, QObject, QTimer, pyqtSignal

from modulos import backup


class SyncBridge(QObject):
    """Leva avisos das threads de rede para a thread da interface."""
    alterado = pyqtSignal()    # chegaram dados novos de outro aparelho
    estado = pyqtSignal()      # conexão / pendências mudaram
    sair = pyqtSignal(str)     # outro aparelho mandou este sair da conta


def _idade(t):
    if not t:
        return ''
    s = max(0, int(datetime.now().timestamp() - t))
    if s < 90:
        return 'agora'
    if s < 5400:
        return f'há {s // 60} min'
    if s < 172800:
        return f'há {s // 3600} h'
    return f'há {s // 86400} dias'


class SyncDialog(QDialog):

    def __init__(self, parent, rede):
        super().__init__(parent)
        self.rede = rede
        self.pai = parent
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)
        self.setWindowTitle('Rede de aparelhos')
        self.setMinimumWidth(640)
        self._cmd = ''
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
        self.l_local = QLabel()
        self.l_pend, self.l_ultimo = QLabel(), QLabel()
        self.l_cripto, self.l_bk = QLabel(), QLabel()
        self.l_local.setWordWrap(True)
        self.l_pares.setStyleSheet('font-weight: bold;')
        f.addRow('Conta:', self.l_conta)
        f.addRow('Este aparelho:', self.l_nome)
        f.addRow('Rede local:', self.l_local)
        f.addRow('Rede Tox:', self.l_rede)
        f.addRow('Aparelhos online:', self.l_pares)
        f.addRow('Pendentes de envio:', self.l_pend)
        f.addRow('Última sincronização:', self.l_ultimo)
        f.addRow('Último backup:', self.l_bk)
        f.addRow('Segurança:', self.l_cripto)
        g.setLayout(f)
        lay.addWidget(g)

        # diagnóstico de conexão / firewall
        self.l_diag = QLabel()
        self.l_diag.setWordWrap(True)
        self.l_diag.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.l_diag)
        self.b_cmd = QPushButton('Copiar comando para liberar a porta')
        self.b_cmd.clicked.connect(self.copiar_comando)
        self.b_cmd.hide()
        lay.addWidget(self.b_cmd)

        dica = QLabel('Entre com o mesmo usuário e senha em outro aparelho: '
                      'eles se encontram sozinhos, pela internet ou pela '
                      'rede local (mesmo sem internet e entre sub-redes).')
        dica.setWordWrap(True)
        dica.setStyleSheet('color: gray;')
        lay.addWidget(dica)

        self.lista = QListWidget()
        self.lista.setMinimumHeight(130)
        lay.addWidget(QLabel('Aparelhos da conta (selecione um):'))
        lay.addWidget(self.lista)

        r0 = QHBoxLayout()
        self.b_desc = QPushButton('Desconectar aparelho selecionado')
        self.b_desc.clicked.connect(self.desconectar)
        self.b_esq = QPushButton('Esquecer aparelho')
        self.b_esq.clicked.connect(self.esquecer)
        r0.addWidget(self.b_desc)
        r0.addWidget(self.b_esq)
        lay.addLayout(r0)

        r1 = QHBoxLayout()
        for txt, fn in (('Sincronizar agora', self.sincronizar),
                        ('Renomear este aparelho', self.renomear),
                        ('Nó manual…', self.no_manual)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            r1.addWidget(b)
        lay.addLayout(r1)
        r1b = QHBoxLayout()
        self.b_varrer = QPushButton('Procurar em sub-redes vizinhas')
        self.b_varrer.setToolTip(
            'Varre 192.168.x.x, 10.0.x.x e 172.16.x.x procurando aparelhos '
            'da conta atrás/acima de roteadores (NAT). Só responde quem tem '
            'o mesmo usuário e senha.')
        self.b_varrer.clicked.connect(self.varrer)
        b_lat = QPushButton('Medir latência agora')
        b_lat.clicked.connect(self.rede.medir_latencia_agora)
        b_id = QPushButton('Trocar identidade deste aparelho')
        b_id.setToolTip('Use se um aparelho seu ligado nunca aparece: pode '
                        'ter sorteado a mesma identidade que este.')
        b_id.clicked.connect(self.trocar_identidade)
        for b in (self.b_varrer, b_lat, b_id):
            r1b.addWidget(b)
        lay.addLayout(r1b)

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
        b_senha = QPushButton('Alterar senha…')
        b_senha.clicked.connect(self.alterar_senha)
        b_fechar = QPushButton('Fechar')
        b_fechar.clicked.connect(self.accept)
        r3.addWidget(b_sair)
        r3.addWidget(b_senha)
        r3.addStretch()
        r3.addWidget(b_fechar)
        lay.addLayout(r3)

    # ── ações ────────────────────────────────────────────────

    def _dev_sel(self):
        it = self.lista.currentItem()
        return it.data(Qt.UserRole) if it else None

    def sincronizar(self):
        self.rede.sincronizar_agora()

    def desconectar(self):
        dev = self._dev_sel()
        if not dev:
            QMessageBox.information(self, 'Desconectar',
                                    'Selecione um aparelho na lista.')
            return
        nome = self.lista.currentItem().data(Qt.UserRole + 1)
        if dev in self.rede.estado().get('sair_pendente', {}):
            if QMessageBox.question(
                    self, 'Desconectar',
                    f"A desconexão de '{nome}' já está pendente.\n"
                    'Cancelar o pedido?') == QMessageBox.Yes:
                self.rede.cancelar_desconexao(dev)
                self.refresh()
            return
        if QMessageBox.question(
                self, 'Desconectar aparelho',
                f"Desconectar '{nome}'?\n\nEle sai da conta e volta para a "
                'tela de login (precisa de usuário e senha para entrar de '
                'novo). Se estiver desligado ou sem rede, o comando é '
                'entregue quando ele aparecer online.\n\n'
                'Os dados nele continuam cifrados no disco.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) == QMessageBox.Yes:
            self.rede.desconectar_dispositivo(dev)
            self.refresh()

    def esquecer(self):
        dev = self._dev_sel()
        if not dev:
            QMessageBox.information(self, 'Esquecer',
                                    'Selecione um aparelho na lista.')
            return
        nome = self.lista.currentItem().data(Qt.UserRole + 1)
        if QMessageBox.question(
                self, 'Esquecer aparelho',
                f"Remover '{nome}' da lista?\n(Use para aparelhos que não "
                'existem mais. Se ele voltar à rede, reaparece.)',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) == QMessageBox.Yes:
            self.rede.esquecer_dispositivo(dev)
            self.refresh()

    def renomear(self):
        n, ok = QInputDialog.getText(self, 'Nome do aparelho', 'Nome:',
                                     QLineEdit.Normal, self.rede.config['nome'])
        if ok and n.strip():
            self.rede.renomear(n)
            self.refresh()

    def varrer(self):
        if QMessageBox.question(
                self, 'Sub-redes vizinhas',
                'Procurar seus aparelhos nas redes privadas vizinhas '
                '(192.168.x.x, 10.0.x.x, 172.16.x.x)?\n\nEnvia ~65 mil '
                'pacotes pequenos e cifrados em ~1,5 minuto. Só aparelhos '
                'com o mesmo usuário e senha respondem.',
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            if not self.rede.varrer_sub_redes():
                QMessageBox.information(self, 'Sub-redes',
                                        'Uma varredura já está em andamento.')

    def trocar_identidade(self):
        if QMessageBox.question(
                self, 'Trocar identidade',
                'Sortear outra identidade de rede para este aparelho?\n'
                '(Seus dados não mudam. Use só se outro aparelho seu, '
                'ligado e com internet, nunca aparece aqui.)',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) == QMessageBox.Yes:
            self.rede.trocar_identidade()

    def copiar_comando(self):
        if self._cmd:
            QApplication.clipboard().setText(self._cmd)
            QMessageBox.information(
                self, 'Comando copiado',
                'Cole no terminal (Linux) ou no Prompt de Comando como '
                'Administrador (Windows).')

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
            'Escolha uma frase para cifrar o backup (mín. 12 caracteres).\n'
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
            self.rede.registrar_backup()
            self.refresh()
            QMessageBox.information(
                self, 'Backup',
                f'Backup salvo ({n} registros).\n\nGuarde o arquivo em outro '
                'lugar (nuvem, pen drive). Para recuperar: instale o app, '
                'crie um login e use "Importar backup" ou '
                '"Tenho um backup" na tela de login.')

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

    def alterar_senha(self):
        self.accept()
        self.pai.alterar_senha()

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
        ips = ', '.join(i['ip'] for i in e.get('interfaces', []))
        self.l_nome.setText(e['nome'] + (f'  ({ips})' if ips else ''))
        redes = '; '.join(f"{i['nome']} {i['ip']}/{i['prefixo']}"
                          for i in e.get('interfaces', []))
        if e.get('gateway'):
            redes += f"  ·  gateway {e['gateway']}"
        v = e.get('varredura') or {}
        if v.get('ativa'):
            redes += (f"  ·  varrendo sub-redes… "
                      f"{v['feito'] * 100 // max(1, v['total'])}%")
        self.l_local.setText(redes or 'sem interface de rede ativa')
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
        ub = e.get('ultimo_backup')
        self.l_bk.setText(
            datetime.fromtimestamp(ub).strftime('%d/%m/%Y %H:%M') if ub else
            'nunca neste aparelho: faça um backup!')
        self.l_bk.setStyleSheet('' if ub else 'color: #f39c12; font-weight: bold;')
        self.l_cripto.setText(
            'Rede cifrada ponta a ponta · dados em disco ' +
            ('cifrados (AES-256)' if e['cripto_repouso']
             else 'SEM criptografia (instale sqlcipher3-binary)'))

        d = e.get('diag') or {}
        cor = {'ok': '#2ecc71', 'info': '#3498db',
               'aviso': '#f39c12'}.get(d.get('nivel'), '#3498db')
        if d.get('titulo'):
            self.l_diag.setText(
                f"<b style='color:{cor}'>● {d['titulo']}</b><br>"
                f"{d.get('texto', '')}")
        self._cmd = d.get('comando') or ''
        self.b_cmd.setVisible(bool(self._cmd))

        sel = self._dev_sel()
        self.lista.clear()
        pend = e.get('sair_pendente', {})
        for dv in e['dispositivos']:
            partes = [('🟢' if dv['online'] else '⚪') + ' ' + (dv['nome'] or '?')]
            if dv.get('lat_ms') is not None:
                partes.append(f"{dv['lat_ms']} ms ({_idade(dv.get('lat_em'))})")
            if dv.get('ips'):
                partes.append(', '.join(dv['ips'][:3]))
            if not dv['online'] and dv.get('visto'):
                partes.append('visto ' + _idade(dv['visto']))
            if dv['dev'] in pend:
                partes.append('⏳ desconexão pendente')
            it = QListWidgetItem('  ·  '.join(partes))
            it.setData(Qt.UserRole, dv['dev'])
            it.setData(Qt.UserRole + 1, dv['nome'] or '?')
            self.lista.addItem(it)
            if dv['dev'] == sel:
                self.lista.setCurrentItem(it)
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

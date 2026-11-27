"""
GerenciadorSync = lado APP da sincronização offline-first com o servidor.

  * O app SEMPRE trabalha no banco local (dados/local.db), com ou sem rede.
  * Pareamento: o usuário cola a chave gerada no servidor
    (RRFS1-<endereço Tox>-<token>); o app envia um pedido de amizade Tox com
    "RRFS-PAIR:<token>" e o servidor fica aguardando o usuário ACEITAR na
    interface web. Depois de aceito, a conexão sobe sozinha.
  * Sempre que o servidor está online: o app envia o que mudou localmente e
    recebe o que mudou no servidor (mesmo protocolo `sync_*` do sync_tox.py).
  * Offline: nada se perde. As mudanças ficam em `sync_changes` e seguem
    quando o servidor voltar (marca d'água por par, em `sync_peers`).
"""
import re
import socket
import time
import sqlite3
import logging
import threading

from modulos.tox_financeiro import ToxFinanceiro
from modulos import sync_core

logger = logging.getLogger('RRFS.SyncApp')

RE_CHAVE = re.compile(r'^RRFS1-([0-9A-Fa-f]{76})-([0-9A-Fa-f]{16,64})$')
TAM_LOTE = 100
INTERVALO = 4          # s entre verificações de pendências
TIMEOUT_ACK = 120      # s esperando ack antes de reenviar

ERROS_AMIGO = {
    2: 'Mensagem de pedido longa demais.',
    4: 'Esta chave pertence a este próprio aplicativo.',
    6: 'Chave inválida (checksum). Copie a chave completa do servidor.',
}


def abrir_db(caminho):
    c = sqlite3.connect(caminho, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=OFF')
    return c


class GerenciadorSync(ToxFinanceiro):

    def __init__(self, base_dir, db_path, ao_alterar=None, ao_estado=None):
        super().__init__(base_dir)
        self.db_path = db_path
        self._cb_alterar = ao_alterar      # dados locais mudaram (veio do servidor)
        self._cb_estado = ao_estado        # status mudou (conexão, pendências…)
        self._inflight = None
        self._hello_pend = False
        self._forcar = False
        self._falha_rx = False
        self._acordar = threading.Event()
        self._sync_thread = None

    # ── avisos para a interface ─────────────────────────────

    def _avisar_estado(self):
        try:
            if self._cb_estado:
                self._cb_estado()
        except Exception:
            logger.exception('cb_estado')

    def _avisar_alterado(self):
        try:
            if self._cb_alterar:
                self._cb_alterar()
        except Exception:
            logger.exception('cb_alterar')

    # ── ciclo de vida ───────────────────────────────────────

    def iniciar(self):
        """Chamar ao abrir o app: só liga o Tox se já houver servidor pareado."""
        if self.config.get('srv_pub'):
            self.restaurar()

    def _iniciar_no(self):
        super()._iniciar_no()
        if not (self._sync_thread and self._sync_thread.is_alive()):
            self._sync_thread = threading.Thread(
                target=self._loop_sync, daemon=True, name='SyncApp-Loop')
            self._sync_thread.start()

    def parar_sync(self):
        """Para o Tox ao fechar o app, sem 'desativar' a configuração."""
        no, self._no = self._no, None
        self._acordar.set()
        if no:
            try:
                no.parar()
            except Exception:
                logger.exception('parar')

    # ── pareamento ──────────────────────────────────────────

    def esta_pareado(self):
        return bool(self.config.get('srv_pub'))

    def parear(self, chave):
        m = RE_CHAVE.match((chave or '').strip())
        if not m:
            return {'sucesso': False,
                    'erro': 'Chave inválida. Cole a chave completa gerada em '
                            'Configurações > Conectar aplicativo desktop '
                            '(começa com RRFS1-).'}
        addr, token = m.group(1).upper(), m.group(2).lower()
        if self.esta_pareado():
            self.desparear()
        r = self.ativar()
        if not r.get('sucesso'):
            return r
        pub = addr[:64]
        antigo = self._numero_de(pub)
        if antigo is not None:             # amizade antiga: refaz com o token novo
            self._no.remover_amigo(antigo)
        try:                               # o servidor mostra este nome ao usuário
            nome = ' '.join(socket.gethostname().replace(':', ' ').split())[:40]
        except Exception:
            nome = ''
        num, cod = self._no.adicionar_amigo(
            bytes.fromhex(addr), f'RRFS-PAIR:{token}:{nome}')
        if num is None:
            return {'sucesso': False,
                    'erro': ERROS_AMIGO.get(cod, f'Falha ao enviar o pedido '
                                                 f'(código {cod}).')}
        self.config.update(srv_addr=addr, srv_pub=pub, aprovado=False,
                           conta='', pareado_em=time.time())
        self._salvar()
        self._log('Pedido enviado ao servidor. Aguardando aprovação')
        self._avisar_estado()
        return {'sucesso': True,
                'mensagem': 'Pedido enviado. Aceite o dispositivo na '
                            'interface web do servidor.'}

    def desparear(self):
        """Desconecta do servidor. Os dados locais permanecem."""
        try:
            n = self._numero_de(self.config.get('srv_pub', ''))
            if n is not None and self._no:
                self._no.remover_amigo(n)
        except Exception:
            logger.exception('desparear')
        for k in ('srv_addr', 'srv_pub', 'aprovado', 'conta', 'pareado_em'):
            self.config.pop(k, None)
        self._inflight = None
        self.desativar()
        self._avisar_estado()
        return {'sucesso': True}

    def sincronizar_agora(self):
        """Pede ao servidor o que mudou e reenvia o que está pendente."""
        self._hello_pend = True
        self._acordar.set()

    # ── amigos ──────────────────────────────────────────────

    def _amigos(self):
        try:
            return self._no.listar_amigos() if self._no else []
        except Exception:
            return []

    def _numero_de(self, pub):
        for a in self._amigos():
            if (a['chave_publica'] or '').upper() == (pub or '').upper():
                return a['numero']
        return None

    def _pub_de(self, numero):
        for a in self._amigos():
            if a['numero'] == numero:
                return (a['chave_publica'] or '').upper()
        return None

    def _servidor(self):
        """(numero, conectado) do amigo-servidor."""
        pub = (self.config.get('srv_pub') or '').upper()
        for a in self._amigos():
            if (a['chave_publica'] or '').upper() == pub:
                return a['numero'], a['conectado']
        return None, False

    # ── ganchos do Tox ──────────────────────────────────────

    def _ao_amigo(self, numero, status):
        # Roda dentro de tox_iterate: NÃO enviar daqui, só sinalizar.
        pub = (self.config.get('srv_pub') or '').upper()
        if not pub or self._pub_de(numero) != pub:
            return
        if status != 0:
            if not self.config.get('aprovado'):
                self.config['aprovado'] = True
                self._salvar()
            self._log('Servidor conectado')
            self._hello_pend = True
            self._acordar.set()
        else:
            self._inflight = None
            self._log('Servidor desconectado (trabalhando offline)')
        self._avisar_estado()

    def _ao_mensagem(self, numero, msg):
        tipo = msg.get('tipo') if isinstance(msg, dict) else None
        if not (isinstance(tipo, str) and tipo.startswith('sync_')):
            return
        pub = (self.config.get('srv_pub') or '').upper()
        if not pub or self._pub_de(numero) != pub:
            return                              # só o servidor pareado
        try:
            self._tratar(numero, pub, tipo, msg)
        except Exception:
            logger.exception('sync %s', tipo)

    def _tratar(self, numero, pub, tipo, msg):
        if tipo == 'sync_info':
            self.config['conta'] = str(msg.get('conta') or '')
            self._salvar()

        elif tipo == 'sync_lote':
            conn = abrir_db(self.db_path)
            try:
                antes = conn.total_changes
                sync_core.aplicar(conn, msg.get('registros') or [])
                mudou = conn.total_changes > antes
            except Exception:
                self._falha_rx = True
                raise
            finally:
                conn.close()
            if mudou:
                self._avisar_alterado()

        elif tipo == 'sync_fim':
            if self._falha_rx:
                self._falha_rx = False
                return                          # sem ack: o servidor reenvia
            self._enviar(numero, {'tipo': 'sync_ack',
                                  'ate_seq': int(msg.get('ate_seq', 0))})
            self._marcar_sync()

        elif tipo == 'sync_ack':
            conn = abrir_db(self.db_path)
            try:
                sync_core.set_enviado(conn, pub, int(msg.get('ate_seq', 0)))
            finally:
                conn.close()
            self._inflight = None
            self._marcar_sync()

    def _marcar_sync(self):
        self.config['ultimo_sync'] = time.time()
        self._salvar()
        self._avisar_estado()

    # ── envio ───────────────────────────────────────────────

    def _empurrar(self, numero, forcar=False):
        pub = (self.config.get('srv_pub') or '').upper()
        t0 = self._inflight
        if t0 and not forcar and time.time() - t0 < TIMEOUT_ACK:
            return
        conn = abrir_db(self.db_path)
        try:
            desde = sync_core.get_enviado(conn, pub)
            regs, ate = sync_core.coletar(conn, desde)
            if not regs:
                if ate > desde:
                    sync_core.set_enviado(conn, pub, ate)
                return
        finally:
            conn.close()
        self._inflight = time.time()
        try:
            for i in range(0, len(regs), TAM_LOTE):
                self._enviar(numero, {'tipo': 'sync_lote',
                                      'registros': regs[i:i + TAM_LOTE]})
            self._enviar(numero, {'tipo': 'sync_fim', 'ate_seq': ate})
        except Exception as e:
            self._inflight = None
            logger.warning('envio sync: %s', e)

    def _ciclo(self):
        num, on = self._servidor()
        if num is None or not on:
            self._inflight = None
            return
        forcar = False
        if self._hello_pend:
            self._hello_pend = False
            self._enviar(num, {'tipo': 'sync_hello',
                               'hora': sync_core.agora()})
            forcar = True
        self._empurrar(num, forcar=forcar)

    def _loop_sync(self):
        while self._no is not None:
            try:
                if self.esta_pareado():
                    self._ciclo()
            except Exception:
                logger.exception('loop sync')
            self._acordar.wait(INTERVALO)
            self._acordar.clear()

    # ── estado para a interface ─────────────────────────────

    def estado(self):
        s = self.obter_status()
        pareado = self.esta_pareado()
        num, on = self._servidor() if pareado else (None, False)
        pend = 0
        if pareado:
            try:
                conn = abrir_db(self.db_path)
                try:
                    desde = sync_core.get_enviado(
                        conn, self.config['srv_pub'].upper())
                    pend = conn.execute(
                        'SELECT COUNT(*) FROM (SELECT DISTINCT tabela, uid '
                        'FROM sync_changes WHERE seq>?)', (desde,)
                    ).fetchone()[0]
                finally:
                    conn.close()
            except Exception:
                pass
        return {'pareado': pareado, 'aprovado': bool(self.config.get('aprovado')),
                'servidor_online': bool(on), 'conta': self.config.get('conta', ''),
                'rede': s.get('rede_texto', 'Offline'),
                'lib_ok': s.get('lib_ok', False), 'rodando': s.get('rodando', False),
                'pendentes': pend, 'ultimo_sync': self.config.get('ultimo_sync'),
                'eventos': (s.get('eventos') or [])[-6:]}

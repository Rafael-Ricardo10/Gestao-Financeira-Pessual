"""
ToxManagerSync = ToxFinanceiro (modulos/tox_financeiro.py, Tox próprio) +
  * pareamento de dispositivos (pedido de amizade com "RRFS-PAIR:<token>"
    fica PENDENTE até o usuário aceitar na interface web);
  * sincronização bidirecional offline-first.

Protocolo (JSON sobre o canal Tox já existente), mensagens `sync_*`:
  app -> servidor : sync_hello | sync_pedir | sync_lote | sync_fim | sync_ack
  servidor -> app : sync_info  | sync_lote  | sync_fim  | sync_ack
  sync_lote {registros:[...]}   lote de mudanças (ordenado por dependência)
  sync_fim  {ate_seq}           fim da rajada; o receptor responde sync_ack
  sync_ack  {ate_seq}           o remetente avança a marca d'água
"""
import time
import logging
import threading

from modulos.tox_financeiro import ToxFinanceiro
from modulos import contas, sync_core

logger = logging.getLogger('RRFS.Sync')

TAM_LOTE = 100
INTERVALO = 4          # s entre verificações de pendências
TIMEOUT_ACK = 120      # s esperando ack antes de reenviar


class ToxManagerSync(ToxFinanceiro):

    def __init__(self, base_dir):
        super().__init__(base_dir)
        self._inflight = {}
        self._falha_rx = {}
        self._sync_thread = None

    def _iniciar_no(self):
        super()._iniciar_no()
        if not (self._sync_thread and self._sync_thread.is_alive()):
            self._sync_thread = threading.Thread(
                target=self._loop_sync, daemon=True, name='Sync-Loop')
            self._sync_thread.start()

    # ── amigos <-> chave pública ────────────────────────────────

    def _amigos(self):
        try:
            return self._no.listar_amigos() if self._no else []
        except Exception:
            return []

    def _pubkey(self, numero):
        for a in self._amigos():
            if a['numero'] == numero:
                return (a['chave_publica'] or '').upper()
        return None

    def _numero(self, pubkey):
        for a in self._amigos():
            if (a['chave_publica'] or '').upper() == pubkey.upper():
                return a['numero'], a['conectado']
        return None, False

    # ── pareamento ──────────────────────────────────────────────

    def _ao_pedido(self, chave_bytes, texto):
        if (texto or '').startswith('RRFS-PAIR:'):
            # formato: RRFS-PAIR:<token>[:<nome do dispositivo>]
            partes = texto[len('RRFS-PAIR:'):].split(':', 1)
            token = partes[0].strip()
            nome = partes[1] if len(partes) > 1 else ''
            r = contas.consumir_pareamento(token, chave_bytes.hex(), nome)
            if r and r.get('ja_aprovado'):
                # mesma identidade já aprovada antes: refaz a amizade
                self._log(f"Dispositivo '{r['nome']}' reconectando")
                self.aprovar_pedido(chave_bytes.hex().upper())
            elif r:
                self._log(f"Dispositivo '{r['nome']}' aguardando aprovação")
            else:
                self._log('Pedido de pareamento ignorado (chave inválida)')
            return
        super()._ao_pedido(chave_bytes, texto)

    def chave(self, username, renovar=False):
        end = self.obter_status().get('endereco')
        if not end:
            return {'erro': 'O Tox do servidor ainda não está disponível. '
                            'Aguarde alguns segundos ou verifique a '
                            'libtoxcore no servidor.'}
        k = contas.chave_pareamento(username, end, renovar)
        return {'chave': k} if k else {'erro': 'Conta não encontrada'}

    def renomear_dispositivo(self, username, pubkey, nome):
        if not self._dono(username, pubkey):
            return {'sucesso': False, 'erro': 'Dispositivo não encontrado'}
        if not contas.renomear_dispositivo(pubkey, nome):
            return {'sucesso': False, 'erro': 'Nome inválido'}
        return {'sucesso': True}

    def estado_dispositivos(self, username):
        online = {a['chave_publica'].upper(): a['conectado']
                  for a in self._amigos()}
        lista = contas.listar_dispositivos(username)
        for d in lista:
            d['online'] = bool(online.get(d['pubkey'], False))
        return lista

    def _dono(self, username, pubkey):
        d = contas.dispositivo(pubkey)
        return d if d and d['username'] == username else None

    def aceitar_dispositivo(self, username, pubkey):
        if not self._dono(username, pubkey):
            return {'sucesso': False, 'erro': 'Dispositivo não encontrado'}
        r = self.aprovar_pedido(pubkey)
        if r.get('sucesso'):
            contas.definir_status(pubkey, 'aprovado')
        return r

    def recusar_dispositivo(self, username, pubkey):
        if not self._dono(username, pubkey):
            return {'sucesso': False, 'erro': 'Dispositivo não encontrado'}
        contas.remover_dispositivo(pubkey)
        self.rejeitar_pedido(pubkey)
        return {'sucesso': True}

    def remover_dispositivo(self, username, pubkey):
        if not self._dono(username, pubkey):
            return {'sucesso': False, 'erro': 'Dispositivo não encontrado'}
        num, _ = self._numero(pubkey)
        if num is not None and self._no:
            self.remover_amigo(num)
        contas.remover_dispositivo(pubkey)
        return {'sucesso': True}

    # ── despacho ────────────────────────────────────────────────

    def _ao_mensagem(self, numero, msg):
        tipo = msg.get('tipo') if isinstance(msg, dict) else None
        if isinstance(tipo, str) and tipo.startswith('sync_'):
            try:
                self._tratar_sync(numero, tipo, msg)
            except Exception:
                logger.exception('sync %s', tipo)
            return
        super()._ao_mensagem(numero, msg)

    def _tratar_sync(self, numero, tipo, msg):
        pub = self._pubkey(numero)
        disp = contas.dispositivo(pub) if pub else None
        if not disp or disp['status'] != 'aprovado':
            return                      # só dispositivos aprovados
        user = disp['username']

        if tipo == 'sync_hello':
            self._enviar(numero, {'tipo': 'sync_info', 'conta': user,
                                  'nome': disp['nome'],
                                  'hora': sync_core.agora()})
            self._empurrar(numero, disp, forcar=True)

        elif tipo == 'sync_pedir':
            self._empurrar(numero, disp, forcar=True)

        elif tipo == 'sync_lote':
            conn = contas.abrir_db(user)
            try:
                sync_core.aplicar(conn, msg.get('registros') or [])
            except Exception:
                self._falha_rx[pub] = True
                raise
            finally:
                conn.close()

        elif tipo == 'sync_fim':
            if self._falha_rx.pop(pub, False):
                return                  # não confirma: o app reenvia
            self._enviar(numero, {'tipo': 'sync_ack',
                                  'ate_seq': int(msg.get('ate_seq', 0))})

        elif tipo == 'sync_ack':
            conn = contas.abrir_db(user)
            try:
                sync_core.set_enviado(conn, pub, int(msg.get('ate_seq', 0)))
            finally:
                conn.close()
            self._inflight.pop(pub, None)

        contas.tocar_visto(pub)

    # ── envio ───────────────────────────────────────────────────

    def _empurrar(self, numero, disp, forcar=False):
        pub = disp['pubkey']
        t0 = self._inflight.get(pub)
        if t0 and not forcar and time.time() - t0 < TIMEOUT_ACK:
            return
        conn = contas.abrir_db(disp['username'])
        try:
            desde = sync_core.get_enviado(conn, pub)
            regs, ate = sync_core.coletar(conn, desde)
            if not regs:
                if ate > desde:
                    sync_core.set_enviado(conn, pub, ate)
                return
        finally:
            conn.close()
        self._inflight[pub] = time.time()
        try:
            for i in range(0, len(regs), TAM_LOTE):
                self._enviar(numero, {'tipo': 'sync_lote',
                                      'registros': regs[i:i + TAM_LOTE]})
            self._enviar(numero, {'tipo': 'sync_fim', 'ate_seq': ate})
        except Exception as e:
            self._inflight.pop(pub, None)
            logger.warning('sync envio %s: %s', disp.get('nome'), e)

    def _loop_sync(self):
        while self._no is not None:
            try:
                for d in contas.dispositivos_aprovados():
                    if self._no is None:
                        break
                    num, on = self._numero(d['pubkey'])
                    if num is None or not on:
                        self._inflight.pop(d['pubkey'], None)
                        continue
                    self._empurrar(num, d)
            except Exception:
                logger.exception('loop sync')
            for _ in range(INTERVALO):
                if self._no is None:
                    return
                time.sleep(1)

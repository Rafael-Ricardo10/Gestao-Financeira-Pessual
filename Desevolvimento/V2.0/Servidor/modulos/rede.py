"""
RedeConta = um aparelho (app desktop OU servidor) participando da rede de uma
conta. Todos os aparelhos são PARES: não existe "o servidor" no protocolo.

Como os aparelhos se encontram (sem cadastro central, sem digitar chave)
  * A conta tem N_SLOTS identidades Tox derivadas do login (identidade.py).
    Cada aparelho assume UM slot e adiciona os outros como "amigos". Para o
    Tox só conecta quem prova ter a chave secreta do slot, e essa chave só
    sai de usuário+senha: ter a senha é a autenticação.
  * Mesma rede local, sem internet: a descoberta local do Tox acha os amigos.
  * Internet / NAT: DHT + relays TCP do Tox (atravessa NAT sozinho).
  * Redes isoladas / sub-redes: `adicionar_no()` aponta um aparelho acessível.

Sincronização (offline-first, mesh): cada aparelho mantém uma marca d'água
por par (sync_peers) e reenvia o que mudou. Mudanças recebidas de A são
repassadas a B, então A e B sincronizam mesmo sem se verem.

Mensagens (JSON sobre o canal Tox, já cifrado ponta a ponta):
  rede_hello {dev,nome,slot,criado}  apresentação ao conectar
  rede_conflito {slot,devs}          dois aparelhos escolheram o mesmo slot
  sync_lote / sync_fim / sync_ack    iguais ao protocolo anterior
"""
import os
import time
import uuid
import socket
import logging
import secrets
import threading

from modulos.tox_financeiro import ToxFinanceiro
from modulos import sync_core, bd_seguro
from modulos.identidade import N_SLOTS

logger = logging.getLogger('RRFS.Rede')

TAM_LOTE = 100
INTERVALO = 4
TIMEOUT_ACK = 120


class RedeConta(ToxFinanceiro):

    def __init__(self, base_dir, chaves, db_path, ao_alterar=None,
                 ao_estado=None):
        self.chaves = chaves
        self.db_path = db_path
        pasta = os.path.join(base_dir, 'dados', 'redes', chaves.net_id)
        super().__init__(base_dir, pasta=pasta)
        self._cb_alterar, self._cb_estado = ao_alterar, ao_estado
        c = self.config
        c.setdefault('dev', uuid.uuid4().hex)
        c.setdefault('criado', time.time())
        c.setdefault('dispositivos', {})
        c.setdefault('nos_extra', [])
        if c.get('slot') is None:
            c['slot'] = secrets.randbelow(N_SLOTS)
        try:
            c['nome'] = c.get('nome') or ' '.join(
                socket.gethostname().split())[:40] or 'Dispositivo'
        except Exception:
            c['nome'] = 'Dispositivo'
        self._salvar()
        self._slots = chaves.slots_publicas()          # n -> pubkey hex
        self._slot_de_pub = {v: k for k, v in self._slots.items()}
        self._dev_de = {}            # numero do amigo -> dev
        self._hello_enviado = set()
        self._inflight = {}          # dev -> t0
        self._falha_rx = {}          # dev -> True
        self._visto_slot = {}        # slot -> (dev, t)
        self._acordar = threading.Event()
        self._thread = None
        self._troca = threading.Lock()

    # ── identidade ──────────────────────────────────────────

    @property
    def dev(self):
        return self.config['dev']

    @property
    def slot(self):
        return self.config['slot']

    def _segredo(self):
        return self.chaves.slot_secreta(self.slot)

    def abrir_db(self):
        c = bd_seguro.conectar(self.db_path, self.chaves.chave_bd)
        c.execute('PRAGMA foreign_keys=OFF')
        return c

    def _avisar(self, cb):
        try:
            if cb:
                cb()
        except Exception:
            logger.exception('callback')

    # ── ciclo de vida ───────────────────────────────────────

    def iniciar(self):
        # Se o slot mudou (conflito), o savedata antigo tem a identidade velha
        marca = os.path.join(self.dir, 'slot_do_savedata')
        atual = str(self.slot)
        try:
            ant = open(marca).read().strip()
        except OSError:
            ant = None
        if ant is not None and ant != atual and os.path.exists(self.save_path):
            os.remove(self.save_path)
        r = self.ativar()
        if r.get('sucesso'):
            with open(marca, 'w') as f:
                f.write(atual)
        return r

    def _iniciar_no(self):
        super()._iniciar_no()
        self._amigos_slots()
        if not (self._thread and self._thread.is_alive()):
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name='Rede-Loop')
            self._thread.start()

    def _amigos_slots(self):
        """Adiciona os outros slots da conta como amigos (sem pedido: o Tox só
        conecta se o outro lado provar ter a chave secreta do slot)."""
        no = self._no
        if not no:
            return
        novos = 0
        for n, pub in self._slots.items():
            if n == self.slot:
                continue
            num, _ = no.aceitar_chave(bytes.fromhex(pub), salvar=False)
            novos += num is not None
        if novos:
            no.salvar()

    def _bootstrap_inicial(self):
        try:
            nos = list(self.config.get('nos_extra', []))
            nos += self._carregar_nos() or self.atualizar_nos_online()
            if self._no and nos:
                self._log(f'Bootstrap enviado a {self._no.bootstrap(nos)}/'
                          f'{len(nos)} nós')
            elif not nos:
                self._log('Sem internet: só descoberta na rede local')
        except Exception as e:
            logger.error('bootstrap inicial: %s', e)

    def parar(self):
        self._acordar.set()
        no, self._no = self._no, None
        if no:
            try:
                no.parar()
            except Exception:
                logger.exception('parar')

    # ── nós manuais (sub-redes / LAN sem internet) ──────────

    def meu_bootstrap(self):
        if not self._no:
            return None
        dht, porta = self._no.info_bootstrap()
        return {'dht': dht, 'porta': porta} if dht else None

    def adicionar_no(self, ip, porta, dht_hex):
        try:
            porta = int(porta)
            bytes.fromhex(dht_hex)
            if len(dht_hex) != 64 or not 0 < porta < 65536 or not ip:
                raise ValueError
        except ValueError:
            return {'sucesso': False, 'erro': 'Dados do nó inválidos'}
        no = {'ip': ip.strip(), 'porta': porta,
              'chave_publica': dht_hex.upper(), 'tcp_ports': [porta]}
        self.config['nos_extra'] = [
            x for x in self.config['nos_extra']
            if x['chave_publica'] != no['chave_publica']] + [no]
        self._salvar()
        if self._no:
            self._no.bootstrap([no])
        return {'sucesso': True}

    # ── eventos do Tox (não enviar daqui: só sinalizar) ─────

    def _ao_pedido(self, chave_bytes, texto):
        self._log('Pedido de amizade ignorado (a rede não usa pedidos)')

    def _ao_amigo(self, numero, status):
        if status == 0:
            self._hello_enviado.discard(numero)
            d = self._dev_de.get(numero)
            if d:
                self._inflight.pop(d, None)
        self._acordar.set()
        self._avisar(self._cb_estado)

    def _ao_mensagem(self, numero, msg):
        tipo = msg.get('tipo') if isinstance(msg, dict) else None
        if not isinstance(tipo, str):
            return
        if tipo.startswith('rede_') or tipo.startswith('sync_'):
            try:
                self._tratar(numero, tipo, msg)
            except Exception:
                logger.exception('rede %s', tipo)

    # ── protocolo ───────────────────────────────────────────

    def _pub(self, numero):
        for a in self._amigos():
            if a['numero'] == numero:
                return (a['chave_publica'] or '').upper()
        return None

    def _amigos(self):
        try:
            return self._no.listar_amigos() if self._no else []
        except Exception:
            return []

    def _tratar(self, numero, tipo, msg):
        pub = self._pub(numero)
        if pub not in self._slot_de_pub:       # só slots desta conta
            return
        if tipo == 'rede_hello':
            self._ao_hello(numero, pub, msg)
            return
        if tipo == 'rede_conflito':
            self._ao_conflito(msg)
            return
        dev = self._dev_de.get(numero)
        if not dev:
            return                               # ainda sem apresentação
        if tipo == 'sync_lote':
            conn = self.abrir_db()
            try:
                antes = conn.total_changes
                sync_core.aplicar(conn, msg.get('registros') or [])
                mudou = conn.total_changes > antes
            except Exception:
                self._falha_rx[dev] = True
                raise
            finally:
                conn.close()
            if mudou:
                self._avisar(self._cb_alterar)
        elif tipo == 'sync_fim':
            if self._falha_rx.pop(dev, False):
                return                           # sem ack: o par reenvia
            self._enviar(numero, {'tipo': 'sync_ack',
                                  'ate_seq': int(msg.get('ate_seq', 0))})
            self._marcar()
        elif tipo == 'sync_ack':
            conn = self.abrir_db()
            try:
                sync_core.set_enviado(conn, dev, int(msg.get('ate_seq', 0)))
            finally:
                conn.close()
            self._inflight.pop(dev, None)
            self._marcar()

    def _marcar(self):
        self.config['ultimo_sync'] = time.time()
        self._salvar()
        self._avisar(self._cb_estado)

    def _ao_hello(self, numero, pub, msg):
        dev = str(msg.get('dev') or '')[:64]
        if not dev or dev == self.dev:
            return
        slot = self._slot_de_pub[pub]
        ant = self._visto_slot.get(slot)
        if ant and ant[0] != dev and time.time() - ant[1] < 600:
            # dois aparelhos usam o mesmo slot: o de dev "maior" troca
            try:
                self._enviar(numero, {'tipo': 'rede_conflito', 'slot': slot,
                                      'devs': sorted([ant[0], dev])})
            except Exception:
                pass
        self._visto_slot[slot] = (dev, time.time())
        self._dev_de[numero] = dev
        self.config['dispositivos'][dev] = {
            'nome': str(msg.get('nome') or 'Dispositivo')[:40],
            'slot': slot, 'visto': time.time()}
        self._salvar()
        self._acordar.set()
        self._avisar(self._cb_estado)

    def _ao_conflito(self, msg):
        devs = msg.get('devs') or []
        if (self.dev in devs and len(devs) == 2
                and self.dev != min(devs)
                and msg.get('slot') == self.slot):
            threading.Thread(target=self._trocar_slot, daemon=True).start()

    def _trocar_slot(self):
        if not self._troca.acquire(blocking=False):
            return
        try:
            usados = {d.get('slot') for d in
                      self.config['dispositivos'].values()} | {self.slot}
            livres = [n for n in range(N_SLOTS) if n not in usados]
            self.config['slot'] = secrets.choice(livres or range(N_SLOTS))
            self._salvar()
            self._log(f'Slot em conflito: mudando para {self.slot}')
            self.parar()
            self._dev_de.clear()
            self._hello_enviado.clear()
            self.iniciar()
        finally:
            self._troca.release()

    # ── envio ───────────────────────────────────────────────

    def _empurrar(self, numero, dev, forcar=False):
        t0 = self._inflight.get(dev)
        if t0 and not forcar and time.time() - t0 < TIMEOUT_ACK:
            return
        conn = self.abrir_db()
        try:
            desde = sync_core.get_enviado(conn, dev)
            regs, ate = sync_core.coletar(conn, desde)
            if not regs:
                if ate > desde:
                    sync_core.set_enviado(conn, dev, ate)
                return
        finally:
            conn.close()
        self._inflight[dev] = time.time()
        try:
            for i in range(0, len(regs), TAM_LOTE):
                self._enviar(numero, {'tipo': 'sync_lote',
                                      'registros': regs[i:i + TAM_LOTE]})
            self._enviar(numero, {'tipo': 'sync_fim', 'ate_seq': ate})
        except Exception as e:
            self._inflight.pop(dev, None)
            logger.warning('envio sync: %s', e)

    def _loop(self):
        while self._no is not None:
            try:
                for a in self._amigos():
                    num = a['numero']
                    if not a['conectado']:
                        continue
                    novo = num not in self._hello_enviado
                    if novo:
                        self._enviar(num, {
                            'tipo': 'rede_hello', 'dev': self.dev,
                            'nome': self.config['nome'], 'slot': self.slot,
                            'criado': self.config['criado']})
                        self._hello_enviado.add(num)
                    dev = self._dev_de.get(num)
                    if dev:
                        self._empurrar(num, dev, forcar=novo)
            except Exception:
                logger.exception('loop rede')
            self._acordar.wait(INTERVALO)
            self._acordar.clear()

    def sincronizar_agora(self):
        self._hello_enviado.clear()
        self._inflight.clear()
        self._acordar.set()

    def renomear(self, nome):
        nome = ' '.join((nome or '').split())[:40]
        if nome:
            self.config['nome'] = nome
            self._salvar()
            self._hello_enviado.clear()
            self._acordar.set()
        return bool(nome)

    # ── estado para a interface ─────────────────────────────

    def estado(self):
        s = self.obter_status()
        on = {}
        for a in self._amigos():
            if a['conectado']:
                on[a['chave_publica'].upper()] = True
        online_dev = {d for n, d in self._dev_de.items()
                      if self._pub(n) in on}
        devs = []
        for dev, d in self.config['dispositivos'].items():
            devs.append({'dev': dev, 'nome': d.get('nome'),
                         'slot': d.get('slot'), 'visto': d.get('visto'),
                         'online': dev in online_dev})
        devs.sort(key=lambda x: (not x['online'], x.get('nome') or ''))
        pend = 0
        try:
            conn = self.abrir_db()
            try:
                for dev in self.config['dispositivos']:
                    desde = sync_core.get_enviado(conn, dev)
                    pend = max(pend, conn.execute(
                        'SELECT COUNT(*) FROM (SELECT DISTINCT tabela, uid '
                        'FROM sync_changes WHERE seq>?)', (desde,)
                    ).fetchone()[0])
            finally:
                conn.close()
        except Exception:
            pass
        return {'rodando': s.get('rodando', False),
                'lib_ok': s.get('lib_ok', False),
                'rede': s.get('rede_texto', 'Offline'),
                'rede_status': s.get('rede_status', 0),
                'nome': self.config['nome'], 'slot': self.slot,
                'dispositivos': devs, 'pares_online': len(online_dev),
                'pendentes': pend, 'ultimo_sync': self.config.get('ultimo_sync'),
                'cripto_repouso': bd_seguro.CRIPTO_REPOUSO,
                'eventos': (s.get('eventos') or [])[-6:]}

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
  rede_ping / rede_pong {id}         mede a latência (a cada 1 h)
  rede_sair {alvo,cmd,de} / _ok      desconecta (desloga) um aparelho à distância
  (mensagens novas são ignoradas por versões antigas: continuam compatíveis)
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
from modulos import sync_core, bd_seguro, descoberta_lan, diagnostico_rede
from modulos.descoberta_lan import DescobertaLAN
from modulos.enlace_tcp import EnlaceTCP, BASE_NUM
from modulos.identidade import N_SLOTS

logger = logging.getLogger('RRFS.Rede')

TAM_LOTE = 100
INTERVALO = 4
TIMEOUT_ACK = 120
INTERVALO_PING = 3600          # latência medida a cada 1 h
VALIDADE_SAIR = 60 * 86400     # comando de desconexão pendente expira em 60 dias


class RedeConta(ToxFinanceiro):

    def __init__(self, base_dir, chaves, db_path, ao_alterar=None,
                 ao_estado=None, ao_sair=None):
        self.chaves = chaves
        self._cb_sair = ao_sair
        self.db_path = db_path
        self._lib_cache = None       # (ok, quando): evita find_library a cada chamada
        pasta = os.path.join(base_dir, 'dados', 'redes', chaves.net_id)
        super().__init__(base_dir, pasta=pasta)
        self._cb_alterar, self._cb_estado = ao_alterar, ao_estado
        c = self.config
        c.setdefault('dev', uuid.uuid4().hex)
        c.setdefault('criado', time.time())
        c.setdefault('dispositivos', {})
        c.setdefault('nos_extra', [])
        c.setdefault('sair_pendente', {})   # dev -> {cmd, em, nome}
        c.setdefault('cmds_feitos', [])
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
        self._ciclo = threading.RLock()   # iniciar/parar nunca se sobrepõem
        # Conexões de banco persistentes, UMA por thread (abrir uma conexão
        # cifrada a cada ciclo é caro e começa com o cache frio)
        self._tl = threading.local()
        # O estado mostrado na interface é calculado numa thread própria:
        # a thread da interface só lê este cache e nunca espera banco/rede
        self._est_ev = threading.Event()
        self._est_lock = threading.Lock()
        self._est_thread = None
        self._est = self._estado_inicial()
        self._ult_compactar = time.time()
        self._t_inicio = time.time()
        self._ult_boot = time.time()
        self._sair_enviado = {}      # dev -> t
        self._ping_pend = {}         # id -> (dev, t0)
        self._ping_ult = {}          # dev -> t
        self._lan = None
        self._tcp = None
        self._tcp_pub = {}           # numero virtual -> pubkey do slot
        self._diag = {'nivel': 'info', 'titulo': 'Iniciando', 'texto': '',
                      'comando': ''}
        self._diag_ev = threading.Event()
        self._diag_thread = None
        self._lan_vistos = set()

    # ── identidade ──────────────────────────────────────────

    @property
    def dev(self):
        return self.config['dev']

    @property
    def slot(self):
        return self.config['slot']

    def _segredo(self):
        return self.chaves.slot_secreta(self.slot)

    def _senha_arquivo(self):
        """Cifra o identidade.tox com chave derivada do login."""
        return self.chaves.chave_tox

    def abrir_db(self):
        c = bd_seguro.conectar(self.db_path, self.chaves.chave_bd)
        c.execute('PRAGMA foreign_keys=OFF')
        return c

    def _conn(self):
        """Conexão persistente da thread atual."""
        c = getattr(self._tl, 'c', None)
        if c is None:
            c = self.abrir_db()
            self._tl.c = c
        return c

    def _descartar_conn(self):
        c = getattr(self._tl, 'c', None)
        self._tl.c = None
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def _lib_ok(self):
        """Com cache: find_library() é lento (roda subprocessos no Linux) e
        falhava de novo a cada chamada quando a libtoxcore não existe."""
        c = self._lib_cache
        agora = time.time()
        if c and (c[0] or agora - c[1] < 60):
            return c[0]
        ok = super()._lib_ok()
        self._lib_cache = (ok, agora)
        return ok

    def _avisar(self, cb):
        try:
            if cb:
                cb()
        except Exception:
            logger.exception('callback')

    # ── ciclo de vida ───────────────────────────────────────

    def iniciar(self):
        with self._ciclo:
            return self._iniciar()

    def _iniciar(self):
        self._garantir_estado()
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
        self._iniciar_lan()
        self._garantir_diag()
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

    # ── descoberta em rede local / sub-redes ────────────────

    def _info_beacon(self):
        no = self._no
        if not no:
            return None
        dht, porta = no.info_bootstrap()
        if not dht or not porta:
            return None
        return {'dev': self.dev, 'slot': self.slot,
                'nome': self.config['nome'], 'dht': dht, 'tp': porta}

    def _iniciar_lan(self):
        if self._lan is not None:
            return
        try:
            self._lan = DescobertaLAN(
                self.chaves.chave_beacon, self._info_beacon,
                self._ao_achar_lan, sem_pares=self._sem_pares)
            self._lan.iniciar()
        except Exception:
            logger.exception('descoberta LAN')
            self._lan = None
        try:
            self._tcp = EnlaceTCP(
                self.chaves.chave_beacon, self._info_beacon,
                self._ao_mensagem, self._ao_tcp)
            self._tcp.iniciar()
        except Exception:
            logger.exception('enlace TCP')
            self._tcp = None

    def _parar_lan(self):
        tcp, self._tcp = self._tcp, None
        if tcp:
            tcp.parar()
        lan, self._lan = self._lan, None
        if lan:
            lan.parar()

    def _online_por_tox(self, dev):
        on = {a['chave_publica'].upper() for a in self._amigos()
              if a['conectado'] and a['numero'] < BASE_NUM}
        return any(self._pub(n) in on and d == dev
                   for n, d in list(self._dev_de.items()) if n < BASE_NUM)

    def _ao_tcp(self, numero, dev, slot, conectado):
        if conectado:
            pub = self._slots.get(slot)
            if not pub:
                return
            self._tcp_pub[numero] = pub.upper()
            self._log(f"Enlace TCP direto com '{dev[:6]}' (slot {slot})")
            self._ao_amigo(numero, 1)
        else:
            self._ao_amigo(numero, 0)
            self._tcp_pub.pop(numero, None)

    def _enviar(self, numero, msg):
        if numero >= BASE_NUM:
            t = self._tcp
            if t:
                t.enviar(numero, msg)
            return
        super()._enviar(numero, msg)

    def _sem_pares(self):
        try:
            return not any(a['conectado'] for a in self._amigos())
        except Exception:
            return True

    def _ao_achar_lan(self, d, ip):
        dev = str(d.get('dev') or '')[:64]
        dht = str(d.get('dht') or '').upper()
        try:
            porta = int(d.get('tp'))
            bytes.fromhex(dht)
        except (TypeError, ValueError):
            return
        if not dev or len(dht) != 64 or not 0 < porta < 65536:
            return
        if d.get('slot') == self.slot and dev != self.dev:
            # mesma identidade Tox em dois aparelhos: nunca se enxergariam.
            # O de dev "maior" troca de slot.
            if self.dev > dev:
                threading.Thread(target=self._trocar_slot,
                                 daemon=True).start()
            return
        # enlace TCP direto (atravessa NAT: quem está dentro abre a conexão)
        if self._tcp and not self._online_por_tox(dev):
            self._tcp.conectar(ip, dev)
        if self._no:
            self._no.bootstrap([{'ip': ip, 'porta': porta,
                                 'chave_publica': dht, 'tcp_ports': [porta]}])
        if (dev, ip) not in self._lan_vistos:
            self._lan_vistos.add((dev, ip))
            self._log(f"Aparelho '{str(d.get('nome') or dev)[:30]}' "
                      f'encontrado em {ip}')
        self._acordar.set()

    def varrer_sub_redes(self):
        """Botão: procura aparelhos em sub-redes privadas vizinhas."""
        return bool(self._lan and self._lan.varrer_vizinhas())

    def trocar_identidade(self):
        """Botão: sorteia outro slot (resolve colisão de identidade)."""
        threading.Thread(target=self._trocar_slot, daemon=True).start()

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
        with self._ciclo:
            self._parar_lan()
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
        self._diag_ev.set()
        self._est_ev.set()           # a thread de estado recalcula e avisa

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
            res = self._no.listar_amigos() if self._no else []
        except Exception:
            res = []
        t = self._tcp
        if t:
            for n, l in t.lista():
                pub = self._tcp_pub.get(n)
                if pub:
                    res = res + [{'numero': n, 'chave_publica': pub,
                                  'conectado': True}]
        return res

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
        if tipo == 'rede_ping':
            self._enviar(numero, {'tipo': 'rede_pong',
                                  'id': str(msg.get('id') or '')[:32]})
            return
        if tipo == 'rede_pong':
            self._ao_pong(msg)
            return
        if tipo == 'rede_sair':
            self._ao_sair(numero, msg)
            return
        if tipo == 'rede_sair_ok':
            self._ao_sair_ok(msg)
            return
        dev = self._dev_de.get(numero)
        if not dev:
            return                               # ainda sem apresentação
        if tipo == 'sync_lote':
            try:
                conn = self._conn()
                antes = conn.total_changes
                sync_core.aplicar(conn, msg.get('registros') or [])
                mudou = conn.total_changes > antes
            except Exception:
                self._falha_rx[dev] = True
                self._descartar_conn()
                raise
            if mudou:
                self._avisar(self._cb_alterar)
        elif tipo == 'sync_fim':
            if self._falha_rx.pop(dev, False):
                return                           # sem ack: o par reenvia
            self._enviar(numero, {'tipo': 'sync_ack',
                                  'ate_seq': int(msg.get('ate_seq', 0))})
            self._marcar()
        elif tipo == 'sync_ack':
            try:
                sync_core.set_enviado(self._conn(), dev,
                                      int(msg.get('ate_seq', 0)))
            except Exception:
                self._descartar_conn()
                raise
            self._inflight.pop(dev, None)
            self._marcar()

    def _marcar(self):
        self.config['ultimo_sync'] = time.time()
        self._salvar()
        self._est_ev.set()

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
            'slot': slot, 'visto': time.time(),
            'ips': [str(x)[:45] for x in (msg.get('ips') or [])[:6]],
            'lat_ms': self.config['dispositivos'].get(dev, {}).get('lat_ms'),
            'lat_em': self.config['dispositivos'].get(dev, {}).get('lat_em')}
        # esquece aparelhos que não aparecem há 90 dias (reinstalações
        # deixavam entradas mortas que nunca ficavam em dia)
        lim = time.time() - 90 * 86400
        for k in [k for k, v in list(self.config['dispositivos'].items())
                  if k != dev and (v.get('visto') or 0) < lim]:
            self.config['dispositivos'].pop(k, None)
        self._salvar()
        self._acordar.set()
        self._est_ev.set()

    def _ao_conflito(self, msg):
        devs = msg.get('devs') or []
        if (self.dev in devs and len(devs) == 2
                and self.dev != min(devs)
                and msg.get('slot') == self.slot):
            threading.Thread(target=self._trocar_slot, daemon=True).start()

    # ── latência ─────────────────────────────────────────────

    def _enviar_ping(self, numero, dev):
        pid = secrets.token_hex(6)
        self._ping_pend[pid] = (dev, time.monotonic())
        self._ping_ult[dev] = time.time()
        if len(self._ping_pend) > 50:
            for k in list(self._ping_pend)[:25]:
                self._ping_pend.pop(k, None)
        self._enviar(numero, {'tipo': 'rede_ping', 'id': pid})

    def _ao_pong(self, msg):
        p = self._ping_pend.pop(str(msg.get('id') or ''), None)
        if not p:
            return
        dev, t0 = p
        d = self.config['dispositivos'].get(dev)
        if d is not None:
            d['lat_ms'] = round((time.monotonic() - t0) * 1000)
            d['lat_em'] = time.time()
            self._salvar()
            self._est_ev.set()

    def medir_latencia_agora(self):
        self._ping_ult.clear()
        self._acordar.set()

    # ── desconectar aparelho à distância ─────────────────────

    def desconectar_dispositivo(self, dev):
        """Manda o aparelho `dev` sair da conta (volta à tela de login).
        Se estiver offline, o comando fica guardado e é entregue quando ele
        aparecer na rede."""
        if not dev or dev == self.dev:
            return False
        d = self.config['dispositivos'].get(dev, {})
        self.config['sair_pendente'][dev] = {
            'cmd': secrets.token_hex(8), 'em': time.time(),
            'nome': d.get('nome') or 'Dispositivo'}
        self._sair_enviado.pop(dev, None)
        self._salvar()
        self._acordar.set()
        self._est_ev.set()
        return True

    def cancelar_desconexao(self, dev):
        self.config['sair_pendente'].pop(dev, None)
        self._salvar()
        self._est_ev.set()

    def _ao_sair(self, numero, msg):
        if msg.get('alvo') != self.dev:
            return
        cmd = str(msg.get('cmd') or '')[:32]
        if not cmd:
            return
        feitos = self.config['cmds_feitos']
        repetido = cmd in feitos
        if not repetido:
            feitos.append(cmd)
            del feitos[:-30]
            self._salvar()
        try:
            self._enviar(numero, {'tipo': 'rede_sair_ok', 'cmd': cmd,
                                  'alvo': self.dev})
        except Exception:
            pass
        if repetido:
            return                       # já cumprido: só confirma de novo
        quem = self.config['dispositivos'].get(
            self._dev_de.get(numero), {}).get('nome') or 'outro aparelho'
        self._log(f'Desconexão remota pedida por {quem}')
        if self._cb_sair:
            # pequeno atraso: deixa o "ok" sair antes de fechar a rede
            threading.Timer(1.0, self._avisar_sair, args=(quem,)).start()

    def _avisar_sair(self, quem):
        try:
            self._cb_sair(quem)
        except Exception:
            logger.exception('cb_sair')

    def _ao_sair_ok(self, msg):
        dev = msg.get('alvo')
        p = self.config['sair_pendente'].get(dev)
        if p and p.get('cmd') == msg.get('cmd'):
            self.config['sair_pendente'].pop(dev, None)
            self._sair_enviado.pop(dev, None)
            self._salvar()
            self._log(f"Aparelho '{p.get('nome')}' foi desconectado")
            self._est_ev.set()

    def esquecer_dispositivo(self, dev):
        """Remove da lista um aparelho que não existe mais."""
        self.config['dispositivos'].pop(dev, None)
        self.config['sair_pendente'].pop(dev, None)
        self._salvar()
        self._est_ev.set()

    def registrar_backup(self):
        self.config['ultimo_backup'] = time.time()
        self._salvar()

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
        try:
            conn = self._conn()
            desde = sync_core.get_enviado(conn, dev)
            regs, ate = sync_core.coletar(conn, desde)
            if not regs:
                if ate > desde:
                    sync_core.set_enviado(conn, dev, ate)
                return
        except Exception:
            self._descartar_conn()
            raise
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
                            'criado': self.config['criado'],
                            'ips': descoberta_lan.ips_locais()[:6],
                            'v': 3})
                        self._hello_enviado.add(num)
                    dev = self._dev_de.get(num)
                    if dev:
                        self._empurrar(num, dev, forcar=novo)
                        self._tarefas_do_par(num, dev)
                self._reanimar()
            except Exception:
                logger.exception('loop rede')
            if time.time() - self._ult_compactar > 1800:
                self._ult_compactar = time.time()
                try:
                    sync_core.compactar(self._conn())
                except Exception:
                    logger.exception('compactar')
                    self._descartar_conn()
            self._acordar.wait(INTERVALO)
            self._acordar.clear()

    def _tarefas_do_par(self, num, dev):
        agora = time.time()
        p = self.config['sair_pendente'].get(dev)
        if p:
            if agora - (p.get('em') or 0) > VALIDADE_SAIR:
                self.config['sair_pendente'].pop(dev, None)
                self._salvar()
            elif agora - self._sair_enviado.get(dev, 0) > 30:
                self._sair_enviado[dev] = agora
                self._enviar(num, {'tipo': 'rede_sair', 'alvo': dev,
                                   'cmd': p['cmd'], 'de': self.dev})
        if agora - self._ping_ult.get(dev, 0) > INTERVALO_PING:
            self._enviar_ping(num, dev)

    def _reanimar(self):
        """Offline há mais de 2 min: refaz o bootstrap (mudou de Wi-Fi,
        acordou do suspend...). Só lê arquivos locais: nunca bloqueia."""
        no = self._no
        if not no or time.time() - self._ult_boot < 120:
            return
        self._ult_boot = time.time()
        if no.status_rede() == 0:
            nos = list(self.config.get('nos_extra', [])) + \
                (self._carregar_nos() or [])
            if nos:
                no.bootstrap(nos)
            if self._lan:
                self._lan.anunciar_agora()

    def sincronizar_agora(self):
        self._hello_enviado.clear()
        self._inflight.clear()
        if self._lan:
            self._lan.anunciar_agora()
        self._acordar.set()
        self._est_ev.set()

    def renomear(self, nome):
        nome = ' '.join((nome or '').split())[:40]
        if nome:
            self.config['nome'] = nome
            self._salvar()
            self._hello_enviado.clear()
            self._acordar.set()
        return bool(nome)

    # ── estado para a interface ─────────────────────────────

    def _estado_inicial(self):
        return {'rodando': False, 'lib_ok': True, 'rede': 'Iniciando…',
                'rede_status': 0, 'nome': self.config['nome'],
                'slot': self.slot, 'dispositivos': [], 'pares_online': 0,
                'pendentes': 0, 'ultimo_sync': self.config.get('ultimo_sync'),
                'cripto_repouso': bd_seguro.CRIPTO_REPOUSO, 'eventos': [],
                'diag': dict(getattr(self, '_diag', {})), 'interfaces': [],
                'gateway': '',
                'varredura': {'ativa': False, 'feito': 0, 'total': 0},
                'ultimo_backup': self.config.get('ultimo_backup'),
                'escutando_lan': False, 'sair_pendente': {}}

    # ── diagnóstico (internet / firewall / portas) ──────────

    def _garantir_diag(self):
        if self._diag_thread and self._diag_thread.is_alive():
            return
        self._diag_thread = threading.Thread(
            target=self._loop_diag, daemon=True, name='Rede-Diag')
        self._diag_thread.start()

    def _loop_diag(self):
        fw, t_fw = ('desconhecido', ''), 0
        internet, t_net = False, 0
        while self._no is not None:
            try:
                s = self.obter_status()
                if time.time() - t_net > 20:      # teste de internet é lento
                    internet, t_net = diagnostico_rede.tem_internet(), time.time()
                if time.time() - t_fw > 600:
                    fw, t_fw = diagnostico_rede.firewall(), time.time()
                ifs = descoberta_lan.interfaces()
                porta = self._no.info_bootstrap()[1] if self._no else 0
                online = sum(1 for a in self._amigos() if a['conectado'])
                novo = diagnostico_rede.avaliar(
                    s.get('rede_status', 0), internet, fw, porta,
                    time.time() - self._t_inicio, online,
                    len(self.config['dispositivos']), bool(ifs))
                self._diag = novo
                self._ifs = ifs
                self._gw = descoberta_lan.gateway_padrao()
                self._est_ev.set()
            except Exception:
                logger.exception('diag')
            self._diag_ev.wait(20 if self._sem_pares() else 60)
            self._diag_ev.clear()

    def _garantir_estado(self):
        if self._est_thread and self._est_thread.is_alive():
            return
        self._est_thread = threading.Thread(
            target=self._loop_estado, daemon=True, name='Rede-Estado')
        self._est_thread.start()

    def _loop_estado(self):
        while True:
            try:
                novo = self._calcular_estado()
                with self._est_lock:
                    mudou = novo != self._est
                    self._est = novo
                if mudou:
                    self._avisar(self._cb_estado)
            except Exception:
                logger.exception('estado')
                self._descartar_conn()
            self._est_ev.wait(3)
            self._est_ev.clear()

    def _calcular_estado(self):
        """Roda na thread 'Rede-Estado' (pode esperar banco/Tox à vontade)."""
        s = self.obter_status()
        on = {}
        for a in self._amigos():
            if a['conectado']:
                on[a['chave_publica'].upper()] = True
        online_dev = {d for n, d in list(self._dev_de.items())
                      if self._pub(n) in on}
        agora = time.time()
        devs, recentes = [], []
        for dev, d in list(self.config['dispositivos'].items()):
            devs.append({'dev': dev, 'nome': d.get('nome'),
                         'slot': d.get('slot'), 'visto': d.get('visto'),
                         'online': dev in online_dev,
                         'ips': list(d.get('ips') or []),
                         'lat_ms': d.get('lat_ms'),
                         'lat_em': d.get('lat_em'),
                         'sair_pendente': dev in self.config['sair_pendente']})
            # aparelho que sumiu há muito tempo não conta como "pendente"
            if dev in online_dev or agora - (d.get('visto') or 0) < 30 * 86400:
                recentes.append(dev)
        devs.sort(key=lambda x: (not x['online'], x.get('nome') or ''))
        pend = 0
        try:
            conn = self._conn()
            for dev in recentes:
                desde = sync_core.get_enviado(conn, dev)
                pend = max(pend, sync_core.contar_pendentes(conn, desde))
        except Exception:
            self._descartar_conn()
        return {'rodando': s.get('rodando', False),
                'lib_ok': s.get('lib_ok', False),
                'rede': s.get('rede_texto', 'Offline'),
                'rede_status': s.get('rede_status', 0),
                'nome': self.config['nome'], 'slot': self.slot,
                'dispositivos': devs, 'pares_online': len(online_dev),
                'pendentes': pend, 'ultimo_sync': self.config.get('ultimo_sync'),
                'cripto_repouso': bd_seguro.CRIPTO_REPOUSO,
                'eventos': (s.get('eventos') or [])[-6:],
                'diag': dict(self._diag),
                'interfaces': list(getattr(self, '_ifs', [])),
                'gateway': getattr(self, '_gw', ''),
                'varredura': dict(self._lan.varredura) if self._lan else
                {'ativa': False, 'feito': 0, 'total': 0},
                'escutando_lan': bool(self._lan and self._lan.escutando),
                'ultimo_backup': self.config.get('ultimo_backup'),
                'sair_pendente': {k: dict(v) for k, v in
                                  self.config['sair_pendente'].items()}}

    def estado(self):
        """Chamado pela interface: devolve o último estado calculado, sem
        tocar em banco, Tox nem disco (nunca trava a tela)."""
        self._garantir_estado()
        with self._est_lock:
            e = dict(self._est)
        e['dispositivos'] = [dict(d) for d in e['dispositivos']]
        e['eventos'] = list(e['eventos'])
        e['nome'] = self.config['nome']
        return e

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tox_financeiro.py - Tox próprio do RRFS Gestão Financeira (libtoxcore via ctypes)

INDEPENDENTE de qualquer outro sistema Tox no mesmo host (ex.: RRFS
Servidores). Para não haver conflito:
  * identidade própria:  dados/tox_financeiro/identidade.tox
  * portas UDP próprias: 33700-33799 (o outro sistema usa 33445-33545);
    ajustável por RRFS_TOX_PORTA_INI / RRFS_TOX_PORTA_FIM
  * servidor TCP do Tox desligado (só usa relays como cliente)
  * anti-censura: além das portas padrão, usa relays TCP pela porta 443
    (e qualquer outra porta que o nó informe) e aceita nós próprios em
    dados/tox_financeiro/nos_proprios.json (ex.: nó seu escutando em
    UDP 53 / TCP 443). Se a rede bloquear UDP, o Tox cai para TCP sozinho.
  * pacote lossless com ID próprio (161)
  * não mexe em UFW, serviços, SSH nem em arquivos do outro sistema
"""
import os
import json
import time
import math
import queue
import struct
import ctypes
import logging
import secrets
import threading
import ctypes.util
import urllib.request
from datetime import datetime

logger = logging.getLogger('RRFS.ToxFin')

TOX_ADDRESS_SIZE = 38
TOX_PUBLIC_KEY_SIZE = 32
SAVEDATA_NONE, SAVEDATA_SAVE, SAVEDATA_SECRET = 0, 1, 2
PACOTE_ID = 161                 # faixa lossless 160-191 (outro sistema: 160)
MAX_FRAGMENTO = 1200
MAX_FRAGMENTOS_MSG = 4000
ERRO_SENDQ = 7
TIMEOUT_FRAGMENTOS = 600
PORTA_INI = int(os.environ.get('RRFS_TOX_PORTA_INI', '33700'))
PORTA_FIM = int(os.environ.get('RRFS_TOX_PORTA_FIM', '33799'))

_LIB = None


def _hex_ok(s, n):
    return isinstance(s, str) and len(s) == n and all(
        c in '0123456789abcdefABCDEF' for c in s)


def _portas_tcp(no):
    """Portas TCP a tentar num nó: 443 primeiro (raramente bloqueada), mais
    uma outra porta informada pelo nó. Sem lista, usa a porta do nó."""
    brutas = no.get('tcp_ports') or [no.get('porta')]
    portas = []
    for p in brutas:
        try:
            p = int(p)
        except (TypeError, ValueError):
            continue
        if 0 < p < 65536 and p not in portas:
            portas.append(p)
    portas.sort(key=lambda p: p != 443)      # 443 na frente (sort estável)
    return portas[:2]


def _candidatas_lib():
    """Procura primeiro a libtoxcore EMBUTIDA no executável / ao lado dele,
    depois as do sistema."""
    import sys
    if sys.platform == 'win32':
        nomes = ['libtox.dll', 'toxcore.dll', 'libtoxcore.dll']
    elif sys.platform == 'darwin':
        nomes = ['libtoxcore.dylib', 'libtoxcore.2.dylib']
    else:
        nomes = ['libtoxcore.so.2', 'libtoxcore.so', 'libtoxcore.so.1',
                 'libtoxcore.so.0']
    from modulos import recursos
    pastas = []
    for p in (recursos.pasta_recursos(), recursos.pasta_base(), os.getcwd()):
        if p and p not in pastas:
            pastas.append(p)
    cand = [os.path.join(p, n) for p in pastas for n in nomes
            if os.path.exists(os.path.join(p, n))]
    achado = ctypes.util.find_library('toxcore')
    if achado:
        cand.append(achado)
    return cand + nomes


def carregar_libtoxcore():
    global _LIB
    if _LIB is not None:
        return _LIB
    erro = None
    for nome in _candidatas_lib():
        try:
            _LIB = ctypes.CDLL(nome)
            _assinaturas(_LIB)
            return _LIB
        except (OSError, AttributeError) as e:
            _LIB, erro = None, e
    raise RuntimeError(f'libtoxcore não encontrada/compatível: {erro}')


def _assinaturas(lib):
    vp, ci = ctypes.c_void_p, ctypes.c_int
    u8p = ctypes.POINTER(ctypes.c_uint8)
    u32, u16 = ctypes.c_uint32, ctypes.c_uint16
    st, cb, cp = ctypes.c_size_t, ctypes.c_bool, ctypes.c_char_p
    eri = ctypes.POINTER(ci)

    def fn(nome, rt, at):
        f = getattr(lib, nome)
        f.restype, f.argtypes = rt, at

    fn('tox_options_new', vp, [eri])
    fn('tox_options_free', None, [vp])
    fn('tox_options_set_ipv6_enabled', None, [vp, cb])
    fn('tox_options_set_udp_enabled', None, [vp, cb])
    fn('tox_options_set_local_discovery_enabled', None, [vp, cb])
    fn('tox_options_set_start_port', None, [vp, u16])
    fn('tox_options_set_end_port', None, [vp, u16])
    fn('tox_options_set_tcp_port', None, [vp, u16])
    fn('tox_options_set_savedata_type', None, [vp, ci])
    fn('tox_options_set_savedata_data', None, [vp, u8p, st])
    fn('tox_new', vp, [vp, eri])
    fn('tox_kill', None, [vp])
    fn('tox_bootstrap', cb, [vp, cp, u16, u8p, eri])
    fn('tox_add_tcp_relay', cb, [vp, cp, u16, u8p, eri])
    fn('tox_iteration_interval', u32, [vp])
    fn('tox_iterate', None, [vp, vp])
    fn('tox_self_get_address', None, [vp, u8p])
    fn('tox_self_get_connection_status', ci, [vp])
    fn('tox_get_savedata_size', st, [vp])
    fn('tox_get_savedata', None, [vp, u8p])
    fn('tox_friend_add', u32, [vp, u8p, u8p, st, eri])
    fn('tox_friend_add_norequest', u32, [vp, u8p, eri])
    fn('tox_friend_delete', cb, [vp, u32, eri])
    fn('tox_friend_get_public_key', cb, [vp, u32, u8p, eri])
    fn('tox_self_get_dht_id', None, [vp, u8p])
    fn('tox_self_get_udp_port', u16, [vp, eri])
    fn('tox_friend_send_lossless_packet', cb, [vp, u32, u8p, st, eri])
    fn('tox_self_get_friend_list_size', st, [vp])
    fn('tox_self_get_friend_list', None, [vp, ctypes.POINTER(u32)])
    fn('tox_callback_self_connection_status', None, [vp, vp])
    fn('tox_callback_friend_request', None, [vp, vp])
    fn('tox_callback_friend_connection_status', None, [vp, vp])
    fn('tox_callback_friend_lossless_packet', None, [vp, vp])


# ══════════════════════════════════════════════════════════
# Nó Tox (baixo nível). libtoxcore NÃO é thread-safe: tudo sob RLock.
# ══════════════════════════════════════════════════════════

class _NoTox:

    def __init__(self, caminho, cb_pedido, cb_msg, cb_amigo, log_fn,
                 chave_secreta=None):
        self.lib = carregar_libtoxcore()
        self.chave_secreta = chave_secreta     # 32 bytes: identidade derivada
        self.caminho = caminho
        self.cb_pedido, self.cb_msg, self.cb_amigo = cb_pedido, cb_msg, cb_amigo
        self.log = log_fn
        self.tox = None
        self._rodando = False
        self._trava = threading.RLock()
        self._amigos = {}
        self._frag = {}
        self._refs = []
        self._fila = queue.Queue()
        self._criar()

    def _criar(self):
        L = self.lib
        dados = b''
        if os.path.exists(self.caminho):
            with open(self.caminho, 'rb') as f:
                dados = f.read()
        with self._trava:
            for ipv6 in (True, False):      # hosts sem IPv6 falham com True
                e = ctypes.c_int(0)
                op = L.tox_options_new(ctypes.byref(e))
                if not op:
                    raise RuntimeError('Falha ao criar Tox_Options')
                L.tox_options_set_ipv6_enabled(op, ipv6)
                L.tox_options_set_udp_enabled(op, True)
                L.tox_options_set_local_discovery_enabled(op, True)
                L.tox_options_set_start_port(op, PORTA_INI)
                L.tox_options_set_end_port(op, PORTA_FIM)
                L.tox_options_set_tcp_port(op, 0)   # sem servidor TCP local
                buf = None
                if dados:
                    L.tox_options_set_savedata_type(op, SAVEDATA_SAVE)
                    buf = (ctypes.c_uint8 * len(dados)).from_buffer_copy(dados)
                    L.tox_options_set_savedata_data(op, buf, len(dados))
                elif self.chave_secreta:
                    # primeira vez: a identidade Tox nasce da chave derivada
                    # do login (depois disso vale o savedata completo)
                    buf = (ctypes.c_uint8 * 32).from_buffer_copy(
                        self.chave_secreta)
                    L.tox_options_set_savedata_type(op, SAVEDATA_SECRET)
                    L.tox_options_set_savedata_data(op, buf, 32)
                else:
                    L.tox_options_set_savedata_type(op, SAVEDATA_NONE)
                e2 = ctypes.c_int(0)
                self.tox = L.tox_new(op, ctypes.byref(e2))
                L.tox_options_free(op)
                if self.tox:
                    break
            if not self.tox:
                raise RuntimeError(
                    f'Falha ao criar instância Tox (código {e2.value}; '
                    f'portas {PORTA_INI}-{PORTA_FIM} livres?)')
            self._callbacks()
            self._carregar_amigos()
            self._salvar_sem_trava()
        self.log(f'Identidade pronta: {self.endereco_hex()[:16]}...')

    def _callbacks(self):
        vp, u8p = ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8)
        CB_SELF = ctypes.CFUNCTYPE(None, vp, ctypes.c_int, vp)
        CB_REQ = ctypes.CFUNCTYPE(None, vp, u8p, u8p, ctypes.c_size_t, vp)
        CB_CONN = ctypes.CFUNCTYPE(None, vp, ctypes.c_uint32, ctypes.c_int, vp)
        CB_PKT = ctypes.CFUNCTYPE(None, vp, ctypes.c_uint32, u8p,
                                  ctypes.c_size_t, vp)

        def ao_rede(tox, status, ud):
            self.log('Rede Tox: ' + {0: 'Offline', 1: 'Conectado (TCP)',
                                     2: 'Conectado (UDP)'}.get(status, str(status)))

        def ao_pedido(tox, chave_ptr, msg_ptr, tam, ud):
            try:
                chave = bytes(ctypes.cast(
                    chave_ptr, ctypes.POINTER(
                        ctypes.c_uint8 * TOX_PUBLIC_KEY_SIZE)).contents)
                texto = ''
                if tam and msg_ptr:
                    n = min(int(tam), 1016)
                    texto = bytes(ctypes.cast(
                        msg_ptr, ctypes.POINTER(ctypes.c_uint8 * n)
                    ).contents).decode('utf-8', errors='replace')
                self.cb_pedido(chave, texto)
            except Exception as e:
                logger.error('ao_pedido: %s', e)

        def ao_amigo(tox, numero, status, ud):
            self._amigos.setdefault(numero, {})['status'] = status
            try:
                self.cb_amigo(numero, status)
            except Exception as e:
                logger.error('ao_amigo: %s', e)

        def ao_pacote(tox, numero, ptr, tam, ud):
            try:
                bruto = bytes(ctypes.cast(
                    ptr, ctypes.POINTER(ctypes.c_uint8 * tam)).contents)
            except Exception:
                return
            self._fragmento(numero, bruto)

        self._refs = [CB_SELF(ao_rede), CB_REQ(ao_pedido),
                      CB_CONN(ao_amigo), CB_PKT(ao_pacote)]
        L = self.lib
        L.tox_callback_self_connection_status(self.tox, self._refs[0])
        L.tox_callback_friend_request(self.tox, self._refs[1])
        L.tox_callback_friend_connection_status(self.tox, self._refs[2])
        L.tox_callback_friend_lossless_packet(self.tox, self._refs[3])

    def _carregar_amigos(self):
        tam = self.lib.tox_self_get_friend_list_size(self.tox)
        if tam == 0:
            return
        buf = (ctypes.c_uint32 * tam)()
        self.lib.tox_self_get_friend_list(self.tox, buf)
        for numero in buf:
            e = ctypes.c_int(0)
            kb = (ctypes.c_uint8 * TOX_PUBLIC_KEY_SIZE)()
            ok = self.lib.tox_friend_get_public_key(self.tox, numero, kb,
                                                    ctypes.byref(e))
            self._amigos[numero] = {
                'chave_publica': bytes(kb).hex().upper() if ok else '',
                'status': 0}

    # ── fragmentação (mensagens JSON > 1 pacote) ────────────

    def _fragmento(self, numero, bruto):
        if len(bruto) < 9 or bruto[0] != PACOTE_ID:
            return
        fid = bruto[1:5]
        idx = struct.unpack('>H', bruto[5:7])[0]
        total = struct.unpack('>H', bruto[7:9])[0]
        if total < 1 or total > MAX_FRAGMENTOS_MSG or idx >= total:
            return
        k = (numero, fid)
        reg = self._frag.setdefault(
            k, {'t': time.time(), 'total': total, 'partes': {}})
        if reg['total'] != total:
            self._frag.pop(k, None)
            return
        reg['t'] = time.time()
        reg['partes'][idx] = bruto[9:]
        if len(reg['partes']) < total:
            return
        completo = b''.join(reg['partes'][i] for i in range(total))
        self._frag.pop(k, None)
        try:
            msg = json.loads(completo.decode('utf-8'))
        except Exception:
            return
        self._fila.put((numero, msg))

    def _limpar_fragmentos(self):
        agora = time.time()
        for k in [k for k, v in self._frag.items()
                  if agora - v['t'] > TIMEOUT_FRAGMENTOS]:
            self._frag.pop(k, None)

    def enviar(self, numero, mensagem):
        """Fragmenta e envia (lossless: confiável e ordenado). Fila cheia =
        espera. Levanta exceção só se o amigo desconectar ou o Tox parar."""
        if self._amigos.get(numero, {}).get('status', 0) == 0:
            raise RuntimeError('Dispositivo desconectado')
        bruto = json.dumps(mensagem, ensure_ascii=False).encode('utf-8')
        fid = secrets.token_bytes(4)
        total = max(1, math.ceil(len(bruto) / MAX_FRAGMENTO))
        if total > MAX_FRAGMENTOS_MSG:
            raise RuntimeError('Mensagem grande demais')
        for idx in range(total):
            pedaco = bruto[idx * MAX_FRAGMENTO:(idx + 1) * MAX_FRAGMENTO]
            pkt = (bytes([PACOTE_ID]) + fid + struct.pack('>H', idx) +
                   struct.pack('>H', total) + pedaco)
            buf = (ctypes.c_uint8 * len(pkt)).from_buffer_copy(pkt)
            tent = 0
            while True:
                erro = ctypes.c_int(0)
                with self._trava:
                    if not self.tox:
                        raise RuntimeError('Tox parado')
                    ok = self.lib.tox_friend_send_lossless_packet(
                        self.tox, numero, buf, len(pkt), ctypes.byref(erro))
                if ok:
                    break
                if erro.value == ERRO_SENDQ:
                    if self._amigos.get(numero, {}).get('status', 0) == 0:
                        raise RuntimeError('Dispositivo desconectou no envio')
                    tent += 1
                    time.sleep(min(0.05 * (1 + tent // 10), 0.5))
                    continue
                raise RuntimeError(f'Falha ao enviar pacote (código {erro.value})')

    # ── loops ───────────────────────────────────────────────

    def iniciar_loop(self):
        self._rodando = True
        for alvo, nome in ((self._loop, 'ToxFin-Loop'),
                           (self._loop_salvar, 'ToxFin-Save'),
                           (self._loop_msgs, 'ToxFin-Dispatch')):
            threading.Thread(target=alvo, daemon=True, name=nome).start()

    def _loop(self):
        ult = time.time()
        while self._rodando:
            with self._trava:
                if not self._rodando or not self.tox:
                    break
                self.lib.tox_iterate(self.tox, None)
                intervalo = self.lib.tox_iteration_interval(self.tox)
            if time.time() - ult > 15:
                self._limpar_fragmentos()
                ult = time.time()
            time.sleep(max(intervalo, 10) / 1000.0)

    def _loop_msgs(self):
        while self._rodando:
            try:
                numero, msg = self._fila.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.cb_msg(numero, msg)
            except Exception as e:
                logger.error('despacho: %s', e)

    def _loop_salvar(self):
        while self._rodando:
            for _ in range(20):
                if not self._rodando:
                    return
                time.sleep(1)
            try:
                self.salvar()
            except Exception as e:
                logger.error('salvar periódico: %s', e)

    # ── bootstrap / persistência / consultas ────────────────

    def bootstrap(self, nos):
        total = 0
        for no in nos:
            try:
                chave = bytes.fromhex(no['chave_publica'])
                if len(chave) != TOX_PUBLIC_KEY_SIZE:
                    continue
                buf = (ctypes.c_uint8 * len(chave)).from_buffer_copy(chave)
                host = no['ip'].encode()
                with self._trava:
                    if not self.tox:
                        return total
                    if no.get('udp', True):
                        e = ctypes.c_int(0)
                        if self.lib.tox_bootstrap(self.tox, host,
                                                  int(no['porta']), buf,
                                                  ctypes.byref(e)):
                            total += 1
                    for tcp in _portas_tcp(no):
                        e2 = ctypes.c_int(0)
                        if self.lib.tox_add_tcp_relay(self.tox, host, tcp,
                                                      buf, ctypes.byref(e2)):
                            if not no.get('udp', True):
                                total += 1
                # solta a trava entre nós: sem isso esta thread reassumia a
                # trava na hora e a interface (ativar/endereco_hex) esperava
                time.sleep(0.02)
            except Exception as e:
                logger.error('bootstrap %s: %s', no.get('ip'), e)
        return total

    def salvar(self):
        with self._trava:
            self._salvar_sem_trava()

    def _salvar_sem_trava(self):
        if not self.tox:
            return
        tam = self.lib.tox_get_savedata_size(self.tox)
        buf = (ctypes.c_uint8 * tam)()
        self.lib.tox_get_savedata(self.tox, buf)
        tmp = self.caminho + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(bytes(buf))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.caminho)

    def endereco_hex(self):
        buf = (ctypes.c_uint8 * TOX_ADDRESS_SIZE)()
        with self._trava:
            if not self.tox:
                return ''
            self.lib.tox_self_get_address(self.tox, buf)
        return bytes(buf).hex().upper()

    def status_rede(self):
        with self._trava:
            if not self.tox:
                return 0
            return self.lib.tox_self_get_connection_status(self.tox)

    def aceitar_chave(self, chave_bytes, salvar=True):
        for i in self._amigos.values():
            if i.get('chave_publica') == chave_bytes.hex().upper():
                return None, -3                 # já é amigo
        buf = (ctypes.c_uint8 * TOX_PUBLIC_KEY_SIZE).from_buffer_copy(chave_bytes)
        erro = ctypes.c_int(0)
        with self._trava:
            numero = self.lib.tox_friend_add_norequest(self.tox, buf,
                                                       ctypes.byref(erro))
        if erro.value != 0:
            return None, erro.value
        self._amigos[numero] = {'chave_publica': chave_bytes.hex().upper(),
                                'status': 0}
        if salvar:
            self.salvar()
        return numero, 0

    def info_bootstrap(self):
        """(dht_id_hex, porta_udp): permite que OUTRO aparelho use este como
        ponto de entrada (redes locais isoladas / sub-redes)."""
        buf = (ctypes.c_uint8 * TOX_PUBLIC_KEY_SIZE)()
        e = ctypes.c_int(0)
        with self._trava:
            if not self.tox:
                return '', 0
            self.lib.tox_self_get_dht_id(self.tox, buf)
            porta = self.lib.tox_self_get_udp_port(self.tox, ctypes.byref(e))
        return bytes(buf).hex().upper(), int(porta)

    def adicionar_amigo(self, endereco, texto):
        """Envia pedido de amizade (usado pelo app para parear com o servidor).
        endereco = 38 bytes (endereço Tox completo). Retorna (numero, codigo)."""
        if len(endereco) != TOX_ADDRESS_SIZE:
            return None, -1
        msg = (texto or 'RRFS').encode('utf-8')[:200]
        ab = (ctypes.c_uint8 * TOX_ADDRESS_SIZE).from_buffer_copy(endereco)
        mb = (ctypes.c_uint8 * len(msg)).from_buffer_copy(msg)
        erro = ctypes.c_int(0)
        with self._trava:
            if not self.tox:
                return None, -2
            numero = self.lib.tox_friend_add(self.tox, ab, mb, len(msg),
                                             ctypes.byref(erro))
        if erro.value != 0:
            return None, erro.value
        self._amigos[numero] = {
            'chave_publica': endereco[:TOX_PUBLIC_KEY_SIZE].hex().upper(),
            'status': 0}
        self.salvar()
        return numero, 0

    def listar_amigos(self):
        return [{'numero': n, 'chave_publica': i.get('chave_publica', ''),
                 'conectado': i.get('status', 0) != 0}
                for n, i in sorted(self._amigos.items())]

    def remover_amigo(self, numero):
        erro = ctypes.c_int(0)
        with self._trava:
            if self.tox:
                self.lib.tox_friend_delete(self.tox, numero, ctypes.byref(erro))
        self._amigos.pop(numero, None)
        self.salvar()

    def parar(self):
        self._rodando = False
        with self._trava:
            if self.tox:
                try:
                    self._salvar_sem_trava()
                except Exception as e:
                    logger.error('parar/salvar: %s', e)
                self.lib.tox_kill(self.tox)
                self.tox = None


# ══════════════════════════════════════════════════════════
# Gerenciador (API usada pelo servidor.py / sync_tox.py)
# ══════════════════════════════════════════════════════════

class ToxFinanceiro:

    def __init__(self, base_dir, pasta=None):
        self.dir = pasta or os.path.join(base_dir, 'dados', 'tox_financeiro')
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        self.cfg_path = os.path.join(self.dir, 'config.json')
        self.nos_path = os.path.join(self.dir, 'nos_bootstrap.json')
        self.save_path = os.path.join(self.dir, 'identidade.tox')
        self._no = None
        self._lock = threading.RLock()
        self._eventos = []
        self.config = self._carregar()

    # config
    def _carregar(self):
        try:
            if os.path.exists(self.cfg_path):
                with open(self.cfg_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error('carregar config: %s', e)
        return {'ativo': False}

    def _salvar(self):
        try:
            tmp = self.cfg_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.cfg_path)
        except Exception as e:
            logger.error('salvar config: %s', e)

    def _log(self, msg):
        self._eventos.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        del self._eventos[:-40]

    def _lib_ok(self):
        try:
            carregar_libtoxcore()
            return True
        except Exception:
            return False

    # ganchos para subclasses
    def _ao_pedido(self, chave_bytes, texto):
        self._log(f'Pedido ignorado: {chave_bytes.hex().upper()[:16]}...')

    def _ao_mensagem(self, numero, msg):
        pass

    def _ao_amigo(self, numero, status):
        pass

    def _segredo(self):
        """Subclasses devolvem 32 bytes para fixar a identidade Tox."""
        return None

    def _enviar(self, numero, msg):
        no = self._no
        if no:
            no.enviar(numero, msg)

    # ativar / desativar
    def _iniciar_no(self):
        with self._lock:
            if self._no is not None:
                return
            self._no = _NoTox(self.save_path, self._ao_pedido,
                              self._ao_mensagem, self._ao_amigo, self._log,
                              chave_secreta=self._segredo())
            self._no.iniciar_loop()
        threading.Thread(target=self._bootstrap_inicial, daemon=True,
                         name='ToxFin-Bootstrap').start()
        threading.Thread(target=self._bootstrap_periodico, daemon=True,
                         name='ToxFin-BootstrapLoop').start()

    def ativar(self):
        try:
            if not self._lib_ok():
                return {'sucesso': False,
                        'erro': 'libtoxcore não encontrada '
                                '(sudo apt install libtoxcore-dev).'}
            self._iniciar_no()
            no = self._no
            if no is None:
                raise RuntimeError('Tox parado durante a inicialização')
            self.config['ativo'] = True
            self._salvar()
            return {'sucesso': True, 'endereco': no.endereco_hex(),
                    'mensagem': 'Tox ativado! Aguardando conexão à rede...'}
        except Exception as e:
            logger.error('ativar: %s', e)
            self._no = None
            return {'sucesso': False, 'erro': str(e)}

    def restaurar(self):
        try:
            if self.config.get('ativo') and self._no is None:
                r = self.ativar()
                if not r.get('sucesso'):
                    logger.error('restaurar: %s', r.get('erro'))
        except Exception as e:
            logger.error('restaurar: %s', e)

    def desativar(self):
        try:
            with self._lock:
                no, self._no = self._no, None
            if no:
                no.parar()
            self.config['ativo'] = False
            self._salvar()
            return {'sucesso': True, 'mensagem': 'Tox desativado'}
        except Exception as e:
            logger.error('desativar: %s', e)
            return {'sucesso': False, 'erro': str(e)}

    def obter_status(self):
        try:
            rodando = self._no is not None
            rede = self._no.status_rede() if rodando else 0
            return {
                'lib_ok': self._lib_ok(), 'ativo': self.config.get('ativo', False),
                'rodando': rodando, 'rede_status': rede,
                'rede_texto': {0: 'Offline', 1: 'Conectado (TCP)',
                               2: 'Conectado (UDP)'}.get(rede, '?'),
                'endereco': self._no.endereco_hex() if rodando else '',
                'portas_udp': f'{PORTA_INI}-{PORTA_FIM}',
                'eventos': list(self._eventos)}
        except Exception as e:
            logger.error('obter_status: %s', e)
            return {'lib_ok': False, 'ativo': False, 'rodando': False,
                    'eventos': []}

    # amigos / dispositivos
    def aprovar_pedido(self, chave_hex):
        if self._no is None:
            return {'sucesso': False, 'erro': 'Tox não está ativo'}
        chave_hex = (chave_hex or '').upper()
        if not _hex_ok(chave_hex, 64):
            return {'sucesso': False, 'erro': 'Chave inválida'}
        num, cod = self._no.aceitar_chave(bytes.fromhex(chave_hex))
        if num is None:
            return {'sucesso': False, 'erro': f'Falha ao aceitar (código {cod})'}
        return {'sucesso': True, 'mensagem': 'Dispositivo aprovado'}

    def rejeitar_pedido(self, chave_hex):
        return {'sucesso': True}

    def remover_amigo(self, numero):
        if self._no is None:
            return {'sucesso': False, 'erro': 'Tox não está ativo'}
        self._no.remover_amigo(int(numero))
        return {'sucesso': True}

    # bootstrap (lista própria, baixada de nodes.tox.chat)
    def _nos_proprios(self):
        """Nós do próprio usuário (arquivo opcional nos_proprios.json):
        [{"ip": "...", "porta": 53, "chave_publica": "<64 hex>",
          "tcp_ports": [443], "udp": true}]"""
        caminho = os.path.join(self.dir, 'nos_proprios.json')
        try:
            if os.path.exists(caminho):
                with open(caminho, 'r', encoding='utf-8') as f:
                    return [n for n in json.load(f)
                            if _hex_ok(str(n.get('chave_publica', '')), 64)
                            and n.get('ip') and n.get('porta')]
        except Exception as e:
            logger.error('carregar nós próprios: %s', e)
        return []

    def _carregar_nos(self):
        """Cache dos nós públicos + nós próprios. Sem cache devolve [] para
        que o chamador baixe a lista online (que já inclui os próprios)."""
        try:
            if os.path.exists(self.nos_path):
                with open(self.nos_path, 'r', encoding='utf-8') as f:
                    cache = [n for n in json.load(f)
                             if _hex_ok(n.get('chave_publica', ''), 64)]
                if cache:
                    return cache + self._nos_proprios()
        except Exception as e:
            logger.error('carregar nós: %s', e)
        return []

    def atualizar_nos_online(self):
        try:
            req = urllib.request.Request('https://nodes.tox.chat/json',
                                         headers={'User-Agent': 'RRFS-Financeiro'})
            with urllib.request.urlopen(req, timeout=10) as r:
                dados = json.loads(r.read().decode('utf-8'))
            nos = []
            for it in dados.get('nodes', []):
                ip = it.get('ipv4')
                chave = (it.get('public_key') or '').upper()
                udp = bool(it.get('status_udp'))
                tcp = bool(it.get('status_tcp')) and bool(it.get('tcp_ports'))
                if ((not udp and not tcp) or not ip or ip == '-'
                        or not _hex_ok(chave, 64)):
                    continue            # aceita nós só-TCP (porta 443)
                nos.append({'ip': ip, 'porta': int(it.get('port', 33445)),
                            'chave_publica': chave, 'udp': udp,
                            'tcp_ports': it.get('tcp_ports') or []})
            if nos:
                with open(self.nos_path, 'w', encoding='utf-8') as f:
                    json.dump(nos, f, indent=2)
            return nos + self._nos_proprios()
        except Exception as e:
            logger.error('atualizar nós: %s', e)
            return self._nos_proprios()

    def _bootstrap_inicial(self):
        try:
            nos = self._carregar_nos() or self.atualizar_nos_online()
            if self._no and nos:
                self._log(f'Bootstrap enviado a {self._no.bootstrap(nos)}/'
                          f'{len(nos)} nós')
            elif not nos:
                self._log('Sem nós de bootstrap (verifique a internet)')
        except Exception as e:
            logger.error('bootstrap inicial: %s', e)

    def _bootstrap_periodico(self):
        while self._no is not None:
            for _ in range(1800):
                if self._no is None:
                    return
                time.sleep(1)
            try:
                if self._no and self._no.status_rede() == 0:
                    nos = self.atualizar_nos_online() or self._carregar_nos()
                    self._no.bootstrap(nos)
            except Exception as e:
                logger.error('bootstrap periódico: %s', e)

"""
Enlace TCP direto entre aparelhos da conta (sem Tox, sem internet).

Serve para o que o Tox sozinho não resolve sem internet: aparelhos em
sub-redes diferentes, ou atrás de NAT. Quem está DENTRO do NAT abre a
conexão (saída é sempre permitida) e o outro aceita. O canal é cifrado e
autenticado com a chave da conta (ChaCha20-Poly1305): sem usuário+senha não
há handshake. Cada conexão usa chave de sessão nova (sem replay).

  frame   = 4 bytes (tamanho) + dados
  1º frame (cliente): MAGIA + ni(16) + nonce(12) + AEAD(chave_conta, info)
  2º frame (servidor): MAGIA + nr(16) + nonce(12) + AEAD(chave_conta, info)
  depois: AEAD(HKDF(chave_conta, ni+nr), contador) com as mensagens JSON
          do mesmo protocolo da rede (rede_hello, sync_lote, ...).
"""
import json
import socket
import struct
import logging
import threading
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from modulos.descoberta_lan import PORTA

logger = logging.getLogger('RRFS.TCP')
MAGIA = b'RRFST1'
MAX_FRAME = 8 * 1024 * 1024
BASE_NUM = 1_000_000          # "número de amigo" virtual (Tox usa números baixos)


def _sessao(chave, ni, nr):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=ni + nr,
                info=b'rrfs-tcp-sessao').derive(chave)


def _ler_exato(sock, n):
    buf = b''
    while len(buf) < n:
        p = sock.recv(n - len(buf))
        if not p:
            raise ConnectionError('fechado')
        buf += p
    return buf


def _ler_frame(sock):
    (n,) = struct.unpack('>I', _ler_exato(sock, 4))
    if n < 16 or n > MAX_FRAME:
        raise ValueError('frame inválido')
    return _ler_exato(sock, n)


def _enviar_frame(sock, dados):
    sock.sendall(struct.pack('>I', len(dados)) + dados)


class _Link:

    def __init__(self, sock, aead, dev, info, iniciou, numero):
        self.sock, self.aead, self.dev, self.info = sock, aead, dev, info
        self.iniciou, self.numero = iniciou, numero
        self.ip = sock.getpeername()[0]
        self._tx = self._rx = 0
        self._lock = threading.Lock()
        self.vivo = True

    @staticmethod
    def _nonce(dirc, n):
        return dirc + struct.pack('>Q', n)

    def enviar(self, msg):
        dados = json.dumps(msg, ensure_ascii=False).encode()
        if len(dados) > MAX_FRAME - 64:
            raise RuntimeError('Mensagem grande demais')
        with self._lock:
            ct = self.aead.encrypt(
                self._nonce(b'I\0\0\0' if self.iniciou else b'R\0\0\0',
                            self._tx), dados, None)
            self._tx += 1
            try:
                _enviar_frame(self.sock, ct)
            except OSError as e:
                self.fechar()
                raise RuntimeError('Dispositivo desconectado') from e

    def ler(self):
        ct = _ler_frame(self.sock)
        dirc = b'R\0\0\0' if self.iniciou else b'I\0\0\0'
        pt = self.aead.decrypt(self._nonce(dirc, self._rx), ct, None)
        self._rx += 1
        return json.loads(pt)

    def fechar(self):
        self.vivo = False
        try:
            self.sock.close()
        except OSError:
            pass


class EnlaceTCP:

    def __init__(self, chave32, info_fn, ao_msg, ao_estado, porta=PORTA):
        """info_fn() -> {'dev','slot','nome',...}; ao_msg(numero, msg);
        ao_estado(numero, dev, slot, conectado)."""
        self.chave = chave32
        self._aead = ChaCha20Poly1305(chave32)
        self._info, self._ao_msg, self._ao_estado = info_fn, ao_msg, ao_estado
        self.porta = porta
        self.links = {}                  # dev -> _Link
        self.por_numero = {}             # numero -> _Link
        self._discando = set()
        self._trava = threading.Lock()
        self._seq = 0
        self._rodando = False
        self._srv = None
        self._sem = threading.Semaphore(16)     # handshakes simultâneos
        self.escutando = False

    # ciclo de vida ------------------------------------------------------
    def iniciar(self):
        self._rodando = True
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            s.bind(('', self.porta))
            s.listen(16)
            s.settimeout(1.0)
            self._srv, self.escutando = s, True
            threading.Thread(target=self._aceitar, daemon=True,
                             name='TCP-Aceitar').start()
        except OSError as e:
            logger.warning('TCP %s indisponível para escuta: %s',
                           self.porta, e)
            s.close()

    def parar(self):
        self._rodando = False
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
        for l in list(self.links.values()):
            l.fechar()

    # handshake ----------------------------------------------------------
    def _info_json(self):
        i = self._info()
        return json.dumps(i).encode() if i else None

    def _aceitar(self):
        while self._rodando:
            try:
                c, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._como_servidor, args=(c,),
                             daemon=True, name='TCP-Servidor').start()

    def _como_servidor(self, c):
        if not self._sem.acquire(blocking=False):
            c.close()
            return
        try:
            c.settimeout(6)
            f = _ler_frame(c)
            if not f.startswith(MAGIA) or len(f) < len(MAGIA) + 28:
                raise ValueError('não é RRFS')
            n = len(MAGIA)
            ni, nonce, ct = f[n:n + 16], f[n + 16:n + 28], f[n + 28:]
            info = json.loads(self._aead.decrypt(nonce, ct, MAGIA + ni))
            meu = self._info_json()
            if not meu:
                raise ValueError('Tox ainda não pronto')
            nr, nonce2 = secrets.token_bytes(16), secrets.token_bytes(12)
            _enviar_frame(c, MAGIA + nr + nonce2 + self._aead.encrypt(
                nonce2, meu, MAGIA + ni + nr))
            aead = ChaCha20Poly1305(_sessao(self.chave, ni, nr))
            self._registrar(c, aead, info, iniciou=False)
        except Exception:
            try:
                c.close()
            except OSError:
                pass
        finally:
            self._sem.release()

    def conectar(self, ip, dev):
        """Abre conexão de SAÍDA (atravessa NAT). Idempotente."""
        with self._trava:
            if dev in self.links or (dev, ip) in self._discando:
                return
            self._discando.add((dev, ip))
        threading.Thread(target=self._como_cliente, args=(ip, dev),
                         daemon=True, name='TCP-Cliente').start()

    def _como_cliente(self, ip, dev):
        c = None
        try:
            meu = self._info_json()
            if not meu:
                return
            c = socket.create_connection((ip, self.porta), timeout=5)
            c.settimeout(6)
            ni, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
            _enviar_frame(c, MAGIA + ni + nonce + self._aead.encrypt(
                nonce, meu, MAGIA + ni))
            f = _ler_frame(c)
            n = len(MAGIA)
            if not f.startswith(MAGIA):
                raise ValueError('resposta inválida')
            nr, nonce2, ct = f[n:n + 16], f[n + 16:n + 28], f[n + 28:]
            info = json.loads(self._aead.decrypt(nonce2, ct,
                                                 MAGIA + ni + nr))
            aead = ChaCha20Poly1305(_sessao(self.chave, ni, nr))
            self._registrar(c, aead, info, iniciou=True)
        except Exception:
            if c:
                try:
                    c.close()
                except OSError:
                    pass
        finally:
            with self._trava:
                self._discando.discard((dev, ip))

    # registro / leitura -------------------------------------------------
    def _registrar(self, sock, aead, info, iniciou):
        dev = str(info.get('dev') or '')[:64]
        meu = self._info() or {}
        if not dev or dev == meu.get('dev') or info.get('slot') == meu.get(
                'slot'):
            sock.close()
            return
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for opt, v in (('TCP_KEEPIDLE', 20), ('TCP_KEEPINTVL', 10),
                       ('TCP_KEEPCNT', 3)):
            if hasattr(socket, opt):
                try:
                    sock.setsockopt(socket.IPPROTO_TCP,
                                    getattr(socket, opt), v)
                except OSError:
                    pass
        sock.settimeout(None)
        with self._trava:
            self._seq += 1
            numero = BASE_NUM + self._seq
            link = _Link(sock, aead, dev, info, iniciou, numero)
            ant = self.links.get(dev)
            if ant and ant.vivo:
                # duas conexões ao mesmo tempo: fica a iniciada pelo menor dev
                menor = min(dev, meu.get('dev', ''))
                nova_do_menor = (link.iniciou == (menor == meu.get('dev')))
                if not nova_do_menor:
                    link.fechar()
                    return
                ant.fechar()
            self.links[dev] = link
            self.por_numero[numero] = link
        self._ao_estado(numero, dev, int(info.get('slot', -1)), True)
        threading.Thread(target=self._ler, args=(link,), daemon=True,
                         name='TCP-Leitor').start()

    def _ler(self, link):
        try:
            while self._rodando and link.vivo:
                msg = link.ler()
                if isinstance(msg, dict):
                    self._ao_msg(link.numero, msg)
        except Exception:
            pass
        finally:
            link.fechar()
            with self._trava:
                if self.links.get(link.dev) is link:
                    self.links.pop(link.dev, None)
                self.por_numero.pop(link.numero, None)
            self._ao_estado(link.numero, link.dev, 0, False)

    # API usada pela rede ------------------------------------------------
    def enviar(self, numero, msg):
        l = self.por_numero.get(numero)
        if not l or not l.vivo:
            raise RuntimeError('Dispositivo desconectado')
        l.enviar(msg)

    def lista(self):
        return [(n, l) for n, l in list(self.por_numero.items()) if l.vivo]

"""
Descoberta de aparelhos SEM internet e SEM servidor.

Cada aparelho da conta anuncia (UDP, porta 33698) um pacote CIFRADO com uma
chave derivada do login (ChaCha20-Poly1305). Só quem tem o mesmo usuário e
senha consegue ler ou responder; os demais veem bytes aleatórios.

  * broadcast em cada interface (mesma rede local);
  * varredura unicast das próprias sub-redes (quando o broadcast é filtrado);
  * varredura "estendida" opcional em sub-redes privadas vizinhas, para o
    caso de um aparelho atrás de um roteador/NAT achar os da rede acima:
    quem está DENTRO do NAT inicia o contato (o NAT deixa a resposta voltar).

Ao achar um par, entrega (IP, chave DHT, porta) para o Tox fazer o
bootstrap direto: a conexão Tox sobe sem DHT público nem internet.
"""
import os
import json
import time
import socket
import logging
import ipaddress
import threading
import secrets

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from modulos import recursos

logger = logging.getLogger('RRFS.LAN')

PORTA = int(os.environ.get('RRFS_BEACON_PORTA', '33698'))
MAGIA = b'RRFSB1'
MAX_HOSTS_VARREDURA = 1022
IGNORAR = ('docker', 'veth', 'br-', 'virbr', 'vmnet', 'vboxnet', 'lo')


# ── interfaces / rede local ─────────────────────────────────────────

def _ip_saida():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))       # não envia nada
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ''


def _add(res, nome, ip, mascara):
    try:
        ifc = ipaddress.ip_interface(f'{ip}/{mascara}')
    except ValueError:
        return
    a = ifc.ip
    if a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified:
        return
    rede = ifc.network
    res.append({'nome': nome, 'ip': str(a), 'mascara': str(rede.netmask),
                'rede': str(rede), 'prefixo': rede.prefixlen,
                'broadcast': str(rede.broadcast_address),
                'privada': a.is_private})


def interfaces():
    """Interfaces IPv4 ativas (sem loopback, link-local, docker/VM)."""
    res = []
    try:
        import psutil
        stats = psutil.net_if_stats()
        for nome, ends in psutil.net_if_addrs().items():
            st = stats.get(nome)
            if (st and not st.isup) or nome.lower().startswith(IGNORAR):
                continue
            for e in ends:
                if e.family == socket.AF_INET and e.netmask:
                    _add(res, nome, e.address, e.netmask)
    except Exception:
        pass
    if not res:                                  # sem psutil: só o IP de saída
        ip = _ip_saida()
        if ip:
            _add(res, 'padrao', ip, '255.255.255.0')
    return res


def ips_locais():
    return [i['ip'] for i in interfaces()]


def gateway_padrao():
    """IP do gateway padrão (melhor esforço)."""
    try:
        if os.path.exists('/proc/net/route'):
            with open('/proc/net/route') as f:
                next(f)
                for lin in f:
                    c = lin.split()
                    if c[1] == '00000000' and int(c[3], 16) & 2:
                        b = bytes.fromhex(c[2])[::-1]
                        return socket.inet_ntoa(b)
        elif os.name == 'nt':
            import subprocess
            out = subprocess.run(['route', 'print', '-4', '0.0.0.0'],
                                 capture_output=True, text=True, timeout=5,
                                 env=recursos.env_limpo()).stdout
            for lin in out.splitlines():
                p = lin.split()
                if len(p) >= 3 and p[0] == '0.0.0.0' and p[1] == '0.0.0.0':
                    return p[2]
    except Exception:
        pass
    return ''


# ── descoberta ──────────────────────────────────────────────────────

class DescobertaLAN:

    def __init__(self, chave32, info_fn, ao_achar, sem_pares=None,
                 porta=PORTA):
        """info_fn() -> dict com dev/slot/nome/dht/tp (ou None se o Tox ainda
        não subiu). ao_achar(dict, ip) é chamado ao achar OUTRO aparelho.
        sem_pares() -> True quando nenhum aparelho está online."""
        self._aead = ChaCha20Poly1305(chave32)
        self._info, self._achou = info_fn, ao_achar
        self._sem_pares = sem_pares or (lambda: True)
        self.porta = porta
        self._sock = None
        self._rodando = False
        self._acordar = threading.Event()
        self._ult_ifs = None
        self._visto = {}                       # (dev, ip) -> t (limita avisos)
        self.varredura = {'ativa': False, 'feito': 0, 'total': 0}
        self.escutando = False

    # pacote ----------------------------------------------------------
    def _empacotar(self, tipo):
        d = self._info()
        if not d:
            return None
        d = dict(d, t=tipo)
        nonce = secrets.token_bytes(12)
        ct = self._aead.encrypt(nonce, json.dumps(d).encode(), MAGIA)
        return MAGIA + nonce + ct

    def _abrir(self, pkt):
        if len(pkt) < len(MAGIA) + 12 + 16 or not pkt.startswith(MAGIA):
            return None
        n = len(MAGIA)
        try:
            d = json.loads(self._aead.decrypt(pkt[n:n + 12], pkt[n + 12:],
                                              MAGIA))
        except Exception:
            return None
        return d if isinstance(d, dict) else None

    # ciclo de vida -----------------------------------------------------
    def iniciar(self):
        if self._rodando:
            return
        self._rodando = True
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            s.bind(('', self.porta))
            self.escutando = True
        except OSError as e:
            logger.warning('porta %s UDP indisponível para escuta: %s',
                           self.porta, e)
        s.settimeout(1.0)
        self._sock = s
        threading.Thread(target=self._ouvir, daemon=True,
                         name='LAN-Ouvir').start()
        threading.Thread(target=self._anunciar, daemon=True,
                         name='LAN-Anunciar').start()

    def parar(self):
        self._rodando = False
        self._acordar.set()
        s, self._sock = self._sock, None
        if s:
            try:
                s.close()
            except OSError:
                pass

    def anunciar_agora(self):
        self._acordar.set()

    # envio -------------------------------------------------------------
    def _enviar(self, pkt, ip):
        s = self._sock
        if s and pkt:
            try:
                s.sendto(pkt, (ip, self.porta))
            except OSError:
                pass

    def _broadcast(self):
        pkt = self._empacotar('q')
        if not pkt:
            return
        for i in interfaces():
            self._enviar(pkt, i['broadcast'])
        self._enviar(pkt, '255.255.255.255')

    def _varrer_redes(self, redes, meus):
        pkt_total = sum(min(r.num_addresses, MAX_HOSTS_VARREDURA)
                        for r in redes)
        self.varredura = {'ativa': True, 'feito': 0, 'total': pkt_total}
        try:
            for r in redes:
                n = 0
                for h in r.hosts():
                    if not self._rodando:
                        return
                    n += 1
                    if n > MAX_HOSTS_VARREDURA:
                        break
                    ip = str(h)
                    self.varredura['feito'] += 1
                    if ip in meus:
                        continue
                    self._enviar(self._empacotar('q'), ip)
                    if self.varredura['feito'] % 25 == 0:
                        time.sleep(0.03)             # ~800 pacotes/s
        finally:
            self.varredura['ativa'] = False

    def varrer_proprias(self):
        ifs = interfaces()
        meus = {i['ip'] for i in ifs}
        redes = []
        for i in ifs:
            r = ipaddress.ip_network(i['rede'], strict=False)
            if r.prefixlen < 22:           # redes enormes: só o /24 do aparelho
                r = ipaddress.ip_network(f"{i['ip']}/24", strict=False)
            redes.append(r)
        self._varrer_redes(redes, meus)

    def varrer_vizinhas(self):
        """Opcional (botão): procura em 192.168.0-255.x, 10.0.0-3.x e
        172.16.0-1.x, para achar aparelhos na rede 'acima' de um NAT."""
        if self.varredura['ativa']:
            return False
        meus = {i['ip'] for i in interfaces()}
        redes = [ipaddress.ip_network(f'192.168.{n}.0/24') for n in range(256)]
        redes += [ipaddress.ip_network(f'10.0.{n}.0/24') for n in range(4)]
        redes += [ipaddress.ip_network(f'172.16.{n}.0/24') for n in range(2)]
        threading.Thread(target=self._varrer_redes, args=(redes, meus),
                         daemon=True, name='LAN-Varredura').start()
        return True

    # loops -------------------------------------------------------------
    def _anunciar(self):
        ult_varr = 0.0
        t_inicio = time.time()
        while self._rodando:
            try:
                ifs = sorted(i['ip'] for i in interfaces())
                mudou = ifs != self._ult_ifs
                self._ult_ifs = ifs
                self._broadcast()
                agora = time.time()
                # sem nenhum par online: varre as próprias sub-redes a cada
                # 5 min (e logo no começo / quando a rede muda)
                if self._sem_pares() and (
                        mudou or agora - ult_varr > 300) and \
                        not self.varredura['ativa'] and \
                        agora - t_inicio > 8:
                    ult_varr = agora
                    self.varrer_proprias()
            except Exception:
                logger.exception('anunciar')
            self._acordar.wait(30 if not self._sem_pares() else 12)
            self._acordar.clear()

    def _ouvir(self):
        while self._rodando:
            s = self._sock
            if not s:
                break
            try:
                pkt, (ip, porta) = s.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                if self._rodando:
                    time.sleep(1)
                continue
            d = self._abrir(pkt)
            if not d:
                continue
            meu = self._info() or {}
            if d.get('dev') == meu.get('dev'):
                continue                              # eco do próprio
            try:
                if d.get('t') == 'q':
                    r = self._empacotar('r')
                    if r:
                        s.sendto(r, (ip, porta))
                k = (d.get('dev'), ip)
                agora = time.time()
                if agora - self._visto.get(k, 0) > 20:
                    self._visto[k] = agora
                    self._achou(d, ip)
            except Exception:
                logger.exception('ouvir')

"""
Identidade da conta DERIVADA do login (usuário + senha).

Não existe cadastro central: o mesmo usuário+senha, em qualquer aparelho do
mundo, gera exatamente as mesmas chaves. Isso é o que permite criar a conta
num app, entrar noutro aparelho e os dois se encontrarem sozinhos.

  mestra   = scrypt(senha, sal = "rrfs-v2|" + usuário normalizado)
  net_id   = HKDF(mestra, "net-id")      nome público da rede (16 bytes)
  chave_bd = HKDF(mestra, "bd")          cifra o banco em disco (SQLCipher)
  slot_sk  = HKDF(mestra, "slot", n)     chave secreta Tox do slot n

Só quem conhece a senha consegue produzir a chave secreta de um slot; como o
Tox só conecta com quem prova ter a chave secreta, a posse da senha É a
autenticação de pertencer à rede.
"""
import os
import re
import json
import time
import gzip
import hmac
import base64
import hashlib
import secrets
import unicodedata

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

N_SLOTS = 40                       # identidades Tox possíveis por conta
SCRYPT_N = 2 ** 15                 # ~100 ms; 2**17 é mais forte e mais lento
RE_USER = re.compile(r'^[\w.@-]{3,64}$', re.UNICODE)
MAGIA_BACKUP = b'RRFSBK2\n'


def normalizar_usuario(u):
    return unicodedata.normalize('NFKC', (u or '').strip()).casefold()


def validar(usuario, senha):
    """Devolve mensagem de erro ou ''."""
    if not RE_USER.match(unicodedata.normalize('NFKC', (usuario or '').strip())):
        return 'Usuário: 3 a 64 caracteres (letras, números, . _ - @)'
    if len(senha or '') < 8:
        return 'A senha precisa ter pelo menos 8 caracteres'
    if (senha or '').casefold() in ('12345678', 'password', 'senha123',
                                    '123456789', 'qwertyui'):
        return 'Senha muito fácil de adivinhar. Escolha outra'
    return ''


def _hkdf(mestra, info, n=32):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=None,
                info=b'rrfs2|' + info).derive(mestra)


class Chaves:
    """Todas as chaves de uma conta, derivadas da chave mestra."""

    def __init__(self, mestra, usuario=''):
        self.mestra = mestra
        self.usuario = usuario
        self.net_id = _hkdf(mestra, b'net-id', 16).hex()
        self.chave_bd = _hkdf(mestra, b'bd').hex()
        self._backup = _hkdf(mestra, b'backup')

    def slot_secreta(self, n):
        return _hkdf(self.mestra, b'slot|%d' % n)

    def slot_publica(self, n):
        sk = X25519PrivateKey.from_private_bytes(self.slot_secreta(n))
        return sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def slots_publicas(self):
        return {n: self.slot_publica(n).hex().upper() for n in range(N_SLOTS)}

    def exportar(self):
        """Representação guardável de 'manter conectado'."""
        return json.dumps({'u': self.usuario, 'm': self.mestra.hex()})

    @staticmethod
    def importar(texto):
        d = json.loads(texto)
        return Chaves(bytes.fromhex(d['m']), d.get('u', ''))


def derivar(usuario, senha):
    sal = b'rrfs-v2|' + normalizar_usuario(usuario).encode('utf-8')
    mestra = hashlib.scrypt(senha.encode('utf-8'), salt=sal, n=SCRYPT_N,
                            r=8, p=1, dklen=32, maxmem=256 * 1024 * 1024)
    return Chaves(mestra, (usuario or '').strip())


# ── backup exportável (independe do login) ──────────────────────────

def _chave_frase(frase, sal):
    return hashlib.scrypt(frase.encode('utf-8'), salt=sal, n=2 ** 15, r=8,
                          p=1, dklen=32, maxmem=256 * 1024 * 1024)


def cifrar_backup(dados, frase):
    """dados: objeto JSON. Retorna bytes: magia+sal+nonce+ciphertext."""
    bruto = gzip.compress(json.dumps(dados, ensure_ascii=False).encode('utf-8'))
    sal, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    ct = ChaCha20Poly1305(_chave_frase(frase, sal)).encrypt(
        nonce, bruto, MAGIA_BACKUP)
    return MAGIA_BACKUP + sal + nonce + ct


def abrir_backup(blob, frase):
    if not blob.startswith(MAGIA_BACKUP) or len(blob) < 8 + 28 + 16:
        raise ValueError('Arquivo não é um backup do RRFS')
    sal, nonce = blob[8:24], blob[24:36]
    try:
        bruto = ChaCha20Poly1305(_chave_frase(frase, sal)).decrypt(
            nonce, blob[36:], MAGIA_BACKUP)
    except Exception:
        raise ValueError('Frase incorreta ou arquivo corrompido')
    return json.loads(gzip.decompress(bruto).decode('utf-8'))


# ── "manter conectado" ──────────────────────────────────────────────

def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def guardar_sessao(pasta, chaves):
    """Guarda as chaves derivadas (NUNCA a senha). Usa o cofre do sistema
    (keyring) quando existe; senão um arquivo 0600."""
    kr = _keyring()
    if kr:
        try:
            kr.set_password('RRFS-Financas', 'sessao', chaves.exportar())
            return 'cofre do sistema'
        except Exception:
            pass
    p = os.path.join(pasta, 'sessao.json')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(chaves.exportar())
    os.chmod(p, 0o600)
    return 'arquivo protegido'


def carregar_sessao(pasta):
    kr = _keyring()
    try:
        if kr:
            t = kr.get_password('RRFS-Financas', 'sessao')
            if t:
                return Chaves.importar(t)
    except Exception:
        pass
    p = os.path.join(pasta, 'sessao.json')
    try:
        with open(p, encoding='utf-8') as f:
            return Chaves.importar(f.read())
    except Exception:
        return None


def esquecer_sessao(pasta):
    kr = _keyring()
    if kr:
        try:
            kr.delete_password('RRFS-Financas', 'sessao')
        except Exception:
            pass
    try:
        os.remove(os.path.join(pasta, 'sessao.json'))
    except OSError:
        pass

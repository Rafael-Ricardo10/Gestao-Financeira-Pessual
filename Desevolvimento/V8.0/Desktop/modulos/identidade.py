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
import gzip
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
MAGIA_BACKUP = b'RRFSBK2\n'        # formato antigo (ainda lido)
MAGIA_BACKUP3 = b'RRFSBK3\n'       # formato atual: custo do scrypt no cabeçalho
LOG2N_BACKUP = 17                   # scrypt 2**17 (~128 MB, ~0,5 s) p/ backups
LOG2N_MIN, LOG2N_MAX = 14, 18       # limites aceitos ao ABRIR (evita abuso)
# Tamanho mínimo. Atenção: a senha só é checada ao entrar pela 1ª vez num
# aparelho; quem já tem conta com senha menor continua entrando onde já
# está logado, mas num aparelho NOVO será pedida uma senha com este tamanho.
MIN_SENHA = 12
MIN_FRASE = 12


def normalizar_usuario(u):
    return unicodedata.normalize('NFKC', (u or '').strip()).casefold()


_COMUNS = {'12345678', '123456789', '1234567890', '12345678910',
           'password', 'password123', 'senha123', 'senha1234', 'qwertyui',
           'qwertyuiop', 'abcdefgh', 'abc12345', 'iloveyou', 'admin123',
           'brasil123', 'mudar123', '11111111', '00000000'}


def _fraca(texto):
    """Padrões óbvios: um só caractere repetido, sequência numérica/alfabética
    ou item da lista de senhas comuns."""
    t = (texto or '').casefold()
    if len(set(t)) <= 3:
        return True
    if t in _COMUNS or t.rstrip('0123456789') in _COMUNS:
        return True
    seq = '0123456789 abcdefghijklmnopqrstuvwxyz qwertyuiop asdfghjkl zxcvbnm'
    return any(t in s_ or t in s_[::-1] for s_ in seq.split())


def validar(usuario, senha):
    """Devolve mensagem de erro ou ''."""
    if not RE_USER.match(unicodedata.normalize('NFKC', (usuario or '').strip())):
        return 'Usuário: 3 a 64 caracteres (letras, números, . _ - @)'
    senha = senha or ''
    if len(senha) < MIN_SENHA:
        return (f'A senha precisa ter pelo menos {MIN_SENHA} caracteres. '
                'Dica: uma frase de 4 palavras, como "cafe verde chuva '
                'tijolo"')
    u = normalizar_usuario(usuario)
    if _fraca(senha) or (len(u) >= 4 and u in senha.casefold()):
        return 'Senha muito fácil de adivinhar. Escolha outra'
    return ''


def validar_frase(frase):
    """Frase do backup (o arquivo pode ir para a nuvem: precisa ser forte)."""
    frase = frase or ''
    if len(frase) < MIN_FRASE:
        return (f'A frase do backup precisa ter pelo menos {MIN_FRASE} '
                'caracteres')
    if _fraca(frase):
        return 'Frase muito fácil de adivinhar. Escolha outra'
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
        # chave da descoberta em rede local (derivação NOVA: não altera
        # nenhuma chave existente, então contas atuais seguem iguais)
        self.chave_beacon = _hkdf(mestra, b'beacon')

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

def _chave_frase(frase, sal, log2n=15):
    return hashlib.scrypt(frase.encode('utf-8'), salt=sal, n=2 ** log2n, r=8,
                          p=1, dklen=32, maxmem=512 * 1024 * 1024)


def cifrar_backup(dados, frase):
    """dados: objeto JSON. Retorna bytes:
    magia(8) + log2n(1) + sal(16) + nonce(12) + ciphertext.
    O cabeçalho (magia + custo) é autenticado junto com os dados."""
    bruto = gzip.compress(json.dumps(dados, ensure_ascii=False).encode('utf-8'))
    sal, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    cab = MAGIA_BACKUP3 + bytes([LOG2N_BACKUP])
    ct = ChaCha20Poly1305(_chave_frase(frase, sal, LOG2N_BACKUP)).encrypt(
        nonce, bruto, cab + sal)
    return cab + sal + nonce + ct


def abrir_backup(blob, frase):
    if blob.startswith(MAGIA_BACKUP3) and len(blob) >= 9 + 28 + 16:
        log2n = blob[8]
        if not LOG2N_MIN <= log2n <= LOG2N_MAX:
            raise ValueError('Backup com parâmetros inválidos')
        cab, sal, nonce = blob[:9], blob[9:25], blob[25:37]
        corpo = blob[37:]
        aad = cab + sal
    elif blob.startswith(MAGIA_BACKUP) and len(blob) >= 8 + 28 + 16:
        log2n, sal, nonce = 15, blob[8:24], blob[24:36]    # formato antigo
        corpo, aad = blob[36:], MAGIA_BACKUP
    else:
        raise ValueError('Arquivo não é um backup do RRFS')
    try:
        bruto = ChaCha20Poly1305(_chave_frase(frase, sal, log2n)).decrypt(
            nonce, corpo, aad)
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
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(chaves.exportar())
    try:
        os.chmod(p, 0o600)       # arquivo já existente com permissão antiga
    except OSError:
        pass
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

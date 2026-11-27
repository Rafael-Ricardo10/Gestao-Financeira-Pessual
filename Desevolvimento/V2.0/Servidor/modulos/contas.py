"""
Contas do SERVIDOR (que é só mais um par da rede de cada conta).

  dados/<net_id>.db           banco da conta, CIFRADO (SQLCipher) com chave
                              derivada do login; o nome do arquivo não revela
                              o usuário
  dados/redes/<net_id>/       identidade Tox e estado de sincronização
  dados/servidor.db           (legado) contas antigas com senha em hash

Chaves ficam SÓ EM MEMÓRIA enquanto a conta está ativa. Sem as chaves o
servidor não consegue ler nem sincronizar a conta. Opcional ("manter ativa
após reiniciar"): cofre em disco cifrado com o segredo do servidor.
"""
import os
import time
import json
import threading
import hashlib
import sqlite3 as _sqlite_plano
from werkzeug.security import check_password_hash

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from modulos import identidade, sync_core, bd_seguro
from modulos.database import DBManager, DB_VERSION
from modulos.currency_tracker import create_currency_tables
from modulos.rede import RedeConta

DIR = 'dados'
LEGADO = os.path.join(DIR, 'servidor.db')
ATIVAS = {}                  # net_id -> {'chaves', 'rede'}
_trava = threading.RLock()
_base = os.getcwd()


def iniciar(base):
    global _base
    _base = base
    os.makedirs(DIR, exist_ok=True)
    os.makedirs(os.path.join(DIR, 'redes'), exist_ok=True)


def caminho_db(net_id):
    return os.path.join(DIR, f'{net_id}.db')


def abrir_db(net_id):
    a = ATIVAS.get(net_id)
    if not a:
        raise PermissionError('Conta bloqueada neste servidor')
    c = bd_seguro.conectar(caminho_db(net_id), a['chaves'].chave_bd)
    c.execute('PRAGMA foreign_keys=OFF')
    return c


def user_id(conn):
    return conn.execute('SELECT id FROM users ORDER BY id LIMIT 1'
                        ).fetchone()['id']


def chaves_de(net_id):
    a = ATIVAS.get(net_id)
    return a['chaves'] if a else None


def rede_de(net_id):
    a = ATIVAS.get(net_id)
    return a['rede'] if a else None


# ── criação / entrada ───────────────────────────────────────────────

def _criar_db(chaves):
    m = DBManager(chaves.net_id, chaves.chave_bd)
    c = m.connect()
    try:
        m.create_tables()
        c.execute('INSERT INTO users(username, password) VALUES(?,?)',
                  (chaves.usuario, '-'))
        c.execute('DELETE FROM db_version')
        c.execute('INSERT INTO db_version VALUES(?)', (DB_VERSION,))
        c.commit()
        create_currency_tables(c)
        sync_core.preparar(c)
    finally:
        c.close()


def _legado(usuario, senha):
    """Conta do formato antigo (usuário/senha em hash + dados/<usuario>.db)."""
    if not os.path.exists(LEGADO):
        return None
    try:
        m = _sqlite_plano.connect(LEGADO)
        r = m.execute('SELECT senha_hash FROM contas WHERE username=?',
                      (usuario,)).fetchone()
        m.close()
    except Exception:
        return None
    arq = os.path.join(DIR, f'{usuario}.db')
    if r and os.path.exists(arq) and check_password_hash(r[0], senha):
        return arq
    return None


def entrar(usuario, senha, criar=False):
    """Devolve (net_id, erro). `criar` permite abrir conta nova (ou entrar
    numa rede que existe só em outros aparelhos)."""
    erro = identidade.validar(usuario, senha)
    if erro and (criar or len(senha or '') < 1):
        return None, erro
    chaves = identidade.derivar(usuario, senha or '')
    nid = chaves.net_id
    with _trava:
        existe = os.path.exists(caminho_db(nid))
        if not existe:
            leg = _legado(usuario.strip(), senha)
            if leg:
                _criar_db(chaves)
                _importar_legado(chaves, leg, senha)
                existe = True
        if not existe:
            if not criar:
                return None, ('Usuário ou senha incorretos. Se esta conta '
                              'ainda não existe neste servidor, use '
                              '"Primeiro acesso".')
            if erro:
                return None, erro
            _criar_db(chaves)
        _ativar(chaves)
    return nid, ''


def _importar_legado(chaves, arquivo, senha):
    from modulos.importar_db import importar
    c = bd_seguro.conectar(caminho_db(chaves.net_id), chaves.chave_bd)
    try:
        importar(arquivo, senha, c, user_id(c), False, manter_uid=True)
    finally:
        c.close()
    os.replace(arquivo, arquivo + '.migrado')


def _ativar(chaves):
    if chaves.net_id in ATIVAS:
        return
    rede = RedeConta(_base, chaves, caminho_db(chaves.net_id))
    ATIVAS[chaves.net_id] = {'chaves': chaves, 'rede': rede}
    rede.iniciar()


def bloquear(net_id):
    """Esquece as chaves e desliga a rede da conta neste servidor."""
    with _trava:
        a = ATIVAS.pop(net_id, None)
    if a:
        a['rede'].parar()
    try:
        os.remove(_cofre_path(net_id))
    except OSError:
        pass


# ── "manter ativa após reiniciar" (opt-in) ──────────────────────────

def _segredo():
    with open(os.path.join(DIR, 'secret.key'), 'rb') as f:
        return hashlib.sha256(b'cofre|' + f.read()).digest()


def _cofre_path(net_id):
    return os.path.join(DIR, 'redes', net_id, 'cofre.bin')


def cofre_ativo(net_id):
    return os.path.exists(_cofre_path(net_id))


def cofre_definir(net_id, ligado):
    if not ligado:
        try:
            os.remove(_cofre_path(net_id))
        except OSError:
            pass
        return
    a = ATIVAS.get(net_id)
    if not a:
        return
    nonce = os.urandom(12)
    ct = ChaCha20Poly1305(_segredo()).encrypt(
        nonce, a['chaves'].exportar().encode(), b'cofre')
    os.makedirs(os.path.dirname(_cofre_path(net_id)), exist_ok=True)
    p = _cofre_path(net_id)
    with open(p, 'wb') as f:
        f.write(nonce + ct)
    os.chmod(p, 0o600)


def restaurar_cofres(log=None):
    base = os.path.join(DIR, 'redes')
    for nid in (os.listdir(base) if os.path.isdir(base) else []):
        p = _cofre_path(nid)
        if not os.path.exists(p):
            continue
        try:
            blob = open(p, 'rb').read()
            ch = identidade.Chaves.importar(ChaCha20Poly1305(_segredo()).decrypt(
                blob[:12], blob[12:], b'cofre').decode())
            if ch.net_id == nid and os.path.exists(caminho_db(nid)):
                with _trava:
                    _ativar(ch)
        except Exception as e:
            if log:
                log.warning('cofre de %s inválido: %s', nid, e)


# ── troca de senha = nova identidade (os dados migram) ──────────────

def trocar_senha(net_id, senha_atual, nova):
    a = ATIVAS.get(net_id)
    if not a:
        return None, 'Conta bloqueada'
    atual = a['chaves']
    if identidade.derivar(atual.usuario, senha_atual or '').net_id != net_id:
        return None, 'Senha atual incorreta'
    erro = identidade.validar(atual.usuario, nova)
    if erro:
        return None, erro
    novas = identidade.derivar(atual.usuario, nova)
    if novas.net_id == net_id:
        return None, 'A nova senha é igual à atual'
    with _trava:
        if os.path.exists(caminho_db(novas.net_id)):
            return None, 'Já existe uma conta com esses dados'
        _criar_db(novas)
        o = abrir_db(net_id)
        n = bd_seguro.conectar(caminho_db(novas.net_id), novas.chave_bd)
        n.execute('PRAGMA foreign_keys=OFF')
        try:
            sync_core.aplicar(n, sync_core.snapshot(o))
        finally:
            o.close()
            n.close()
        manter = cofre_ativo(net_id)
        bloquear(net_id)
        antigas = os.path.join(DIR, 'antigas')
        os.makedirs(antigas, exist_ok=True)
        for suf in ('', '-wal', '-shm'):
            f = caminho_db(net_id) + suf
            if os.path.exists(f):
                os.replace(f, os.path.join(antigas, os.path.basename(f)))
        _ativar(novas)
        if manter:
            cofre_definir(novas.net_id, True)
    return novas.net_id, ''

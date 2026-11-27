"""
Contas web, dispositivos (apps desktop) e pareamento.

  dados/servidor.db   -> contas, dispositivos, pareamentos
  dados/<usuario>.db  -> dados financeiros de cada conta (mesmo esquema
                         do sistema RRFS Gestão Financeira)
"""
import os
import re
import time
import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

from modulos.database import DBManager, DB_VERSION
from modulos.currency_tracker import create_currency_tables
from modulos import sync_core

DIR = 'dados'
MASTER = os.path.join(DIR, 'servidor.db')
RE_USER = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
RE_PUB = re.compile(r'^[0-9A-F]{64}$')
MAX_PENDENTES = 10           # pedidos aguardando aprovação por conta
RE_TOKEN = re.compile(r'^[0-9a-f]{16,64}$')


def _conectar(path):
    c = sqlite3.connect(path, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def master():
    return _conectar(MASTER)


def iniciar():
    os.makedirs(DIR, exist_ok=True)
    c = master()
    c.executescript('''
CREATE TABLE IF NOT EXISTS contas(
    username TEXT PRIMARY KEY, senha_hash TEXT NOT NULL, criado REAL);
CREATE TABLE IF NOT EXISTS dispositivos(
    pubkey TEXT PRIMARY KEY, username TEXT NOT NULL, nome TEXT,
    status TEXT NOT NULL DEFAULT 'pendente', criado REAL, ultimo_visto REAL);
CREATE TABLE IF NOT EXISTS pareamentos(
    token TEXT PRIMARY KEY, username TEXT NOT NULL, nome TEXT,
    expira REAL NOT NULL, usado INTEGER NOT NULL DEFAULT 0);
''')
    # chave de pareamento permanente (uma por conta, serve para vários apps)
    if 'token' not in {r[1] for r in c.execute('PRAGMA table_info(contas)')}:
        c.execute('ALTER TABLE contas ADD COLUMN token TEXT')
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_contas_token '
              'ON contas(token)')
    c.commit()
    c.close()


def listar_contas():
    c = master()
    try:
        return [r['username'] for r in c.execute('SELECT username FROM contas')]
    finally:
        c.close()


# ── contas ──────────────────────────────────────────────────────────

def abrir_db(username):
    if not RE_USER.match(username or ''):
        raise ValueError('usuário inválido')
    c = _conectar(os.path.join(DIR, f'{username}.db'))
    c.execute('PRAGMA foreign_keys=OFF')
    return c


def user_id(conn):
    r = conn.execute('SELECT id FROM users ORDER BY id LIMIT 1').fetchone()
    return r['id']


def _inicializar_db(username, senha_hash):
    m = DBManager(username)
    c = m.connect()
    try:
        m.create_tables()
        c.execute('INSERT INTO users(username, password) VALUES(?,?)',
                  (username, senha_hash))
        c.execute('DELETE FROM db_version')
        c.execute('INSERT INTO db_version VALUES(?)', (DB_VERSION,))
        c.commit()
        create_currency_tables(c)
        sync_core.preparar(c)
    finally:
        c.close()


def criar_conta(username, senha):
    username = (username or '').strip()
    if not RE_USER.match(username):
        return False, 'Usuário: 3 a 32 caracteres (letras, números, . _ -)'
    if len(senha or '') < 6:
        return False, 'A senha deve ter pelo menos 6 caracteres'
    if os.path.exists(os.path.join(DIR, f'{username}.db')):
        return False, 'Já existe um banco com esse nome. Escolha outro usuário'
    c = master()
    try:
        if c.execute('SELECT 1 FROM contas WHERE username=? COLLATE NOCASE',
                     (username,)).fetchone():
            return False, 'Usuário já existe'
        h = generate_password_hash(senha)
        _inicializar_db(username, h)
        c.execute('INSERT INTO contas(username, senha_hash, criado) '
                  'VALUES(?,?,?)', (username, h, time.time()))
        c.commit()
        return True, ''
    finally:
        c.close()


def verificar(username, senha):
    c = master()
    try:
        r = c.execute('SELECT senha_hash FROM contas WHERE username=?',
                      (username or '',)).fetchone()
    finally:
        c.close()
    return bool(r and check_password_hash(r['senha_hash'], senha or ''))


def trocar_senha(username, atual, nova):
    if len(nova or '') < 6:
        return False, 'A nova senha deve ter pelo menos 6 caracteres'
    if not verificar(username, atual):
        return False, 'Senha atual incorreta'
    h = generate_password_hash(nova)
    c = master()
    c.execute('UPDATE contas SET senha_hash=? WHERE username=?', (h, username))
    c.commit()
    c.close()
    d = abrir_db(username)
    d.execute('UPDATE users SET password=?', (h,))
    d.commit()
    d.close()
    return True, ''


# ── pareamento / dispositivos ───────────────────────────────────────

def chave_pareamento(username, endereco_tox, renovar=False):
    """Chave PERMANENTE da conta: RRFS1-<endereço Tox>-<token>.
    Vale por tempo indeterminado e serve para conectar quantos apps o usuário
    quiser (cada app novo ainda precisa ser aceito na interface web).
    Só muda quando o usuário pede para renová-la."""
    c = master()
    try:
        r = c.execute('SELECT token FROM contas WHERE username=?',
                      (username,)).fetchone()
        if not r:
            return None
        tok = r['token']
        if renovar or not tok:
            tok = secrets.token_hex(16)
            c.execute('UPDATE contas SET token=? WHERE username=?',
                      (tok, username))
            c.commit()
        return f'RRFS1-{endereco_tox}-{tok}'
    finally:
        c.close()


def consumir_pareamento(token, pubkey, nome=None):
    """Chamado quando chega um pedido de amizade com a chave da conta.
    Cria o dispositivo como PENDENTE (o usuário aprova na interface web).
    Devolve dict (com 'ja_aprovado' se a identidade já havia sido aprovada)
    ou None se o pedido deve ser ignorado."""
    pubkey = (pubkey or '').upper()
    token = (token or '').strip().lower()
    if not RE_PUB.match(pubkey) or not RE_TOKEN.match(token):
        return None
    nome = ' '.join((nome or '').split())[:40]
    c = master()
    try:
        conta = c.execute('SELECT username FROM contas WHERE token=?',
                          (token,)).fetchone()
        if not conta:
            return None
        user = conta['username']
        ex = c.execute('SELECT username, nome, status FROM dispositivos '
                       'WHERE pubkey=?', (pubkey,)).fetchone()
        if ex:
            if ex['username'] != user:
                return None            # identidade já pertence a outra conta
            if ex['status'] == 'aprovado':   # não rebaixa um aprovado
                return {'username': user, 'nome': ex['nome'],
                        'ja_aprovado': True}
            if nome:
                c.execute('UPDATE dispositivos SET nome=? WHERE pubkey=?',
                          (nome, pubkey))
                c.commit()
            return {'username': user, 'nome': nome or ex['nome']}
        total, pend = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(status='pendente'),0) FROM "
            "dispositivos WHERE username=?", (user,)).fetchone()
        if pend >= MAX_PENDENTES:
            return None                # evita enchente de pedidos
        nome = nome or f'Dispositivo {total + 1}'
        c.execute('INSERT INTO dispositivos(pubkey,username,nome,status,criado)'
                  " VALUES(?,?,?,'pendente',?)",
                  (pubkey, user, nome, time.time()))
        c.commit()
        return {'username': user, 'nome': nome}
    finally:
        c.close()


def renomear_dispositivo(pubkey, nome):
    nome = ' '.join((nome or '').split())[:40]
    if not nome:
        return False
    c = master()
    c.execute('UPDATE dispositivos SET nome=? WHERE pubkey=?',
              (nome, pubkey.upper()))
    c.commit()
    c.close()
    return True


def listar_dispositivos(username):
    c = master()
    try:
        return [dict(r) for r in c.execute(
            'SELECT * FROM dispositivos WHERE username=? ORDER BY criado',
            (username,))]
    finally:
        c.close()


def dispositivos_aprovados():
    c = master()
    try:
        return [dict(r) for r in c.execute(
            "SELECT * FROM dispositivos WHERE status='aprovado'")]
    finally:
        c.close()


def dispositivo(pubkey):
    c = master()
    try:
        r = c.execute('SELECT * FROM dispositivos WHERE pubkey=?',
                      ((pubkey or '').upper(),)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


def definir_status(pubkey, status):
    c = master()
    c.execute('UPDATE dispositivos SET status=? WHERE pubkey=?',
              (status, pubkey.upper()))
    c.commit()
    c.close()


def remover_dispositivo(pubkey):
    c = master()
    c.execute('DELETE FROM dispositivos WHERE pubkey=?', (pubkey.upper(),))
    c.commit()
    c.close()


def tocar_visto(pubkey):
    try:
        c = master()
        c.execute('UPDATE dispositivos SET ultimo_visto=? WHERE pubkey=?',
                  (time.time(), pubkey.upper()))
        c.commit()
        c.close()
    except Exception:
        pass

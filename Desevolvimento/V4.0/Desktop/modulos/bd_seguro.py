"""
Acesso ao SQLite com CRIPTOGRAFIA EM REPOUSO (SQLCipher, AES-256).

  pip install sqlcipher3-binary

Sem o SQLCipher o sistema continua funcionando, mas os arquivos .db ficam
legíveis no disco (CRIPTO_REPOUSO = False); a interface avisa o usuário.
`sqlite3` exportado aqui é o MESMO módulo usado pela conexão (para que
`except sqlite3.IntegrityError` etc. funcionem em qualquer um dos casos).
"""
try:
    import sqlcipher3.dbapi2 as sqlite3
    CRIPTO_REPOUSO = True
except ImportError:                       # sem SQLCipher: SQLite comum
    import sqlite3
    CRIPTO_REPOUSO = False

import sqlite3 as _sqlite_plano           # para ler bancos antigos/planos


def conectar(caminho, chave_hex=None, timeout=30):
    """Abre (ou cria) o banco. `chave_hex` = 64 hex (32 bytes) da conta."""
    c = sqlite3.connect(caminho, timeout=timeout, check_same_thread=True)
    if CRIPTO_REPOUSO and chave_hex:
        c.execute(f"PRAGMA key = \"x'{chave_hex}'\"")
    c.row_factory = sqlite3.Row
    try:
        c.execute('SELECT count(*) FROM sqlite_master').fetchone()
    except sqlite3.DatabaseError:
        c.close()
        raise PermissionError('Banco ilegível: chave incorreta ou arquivo '
                              'corrompido')
    try:
        # só troca para WAL se ainda não estiver (evita lock a cada conexão)
        modo = str(c.execute('PRAGMA journal_mode').fetchone()[0]).lower()
        if modo != 'wal':
            c.execute('PRAGMA journal_mode=WAL')
        # em WAL, NORMAL não faz fsync a cada commit: gravações bem mais
        # rápidas e continua seguro contra corrupção
        c.execute('PRAGMA synchronous=NORMAL')
        c.execute('PRAGMA temp_store=MEMORY')
        c.execute('PRAGMA journal_size_limit=67108864')
    except Exception:
        pass
    return c


def conectar_plano(caminho, timeout=30):
    """Banco SQLite comum (legado), somente para migração."""
    c = _sqlite_plano.connect(caminho, timeout=timeout)
    c.row_factory = _sqlite_plano.Row
    return c


def e_plano(caminho):
    """True se o arquivo é um SQLite sem criptografia."""
    try:
        with open(caminho, 'rb') as f:
            return f.read(16) == b'SQLite format 3\x00'
    except OSError:
        return False


# ── conta ativa do app desktop ──────────────────────────────────────
# Os diálogos que abrem o banco em threads próprias usam conectar_ativo()
# em vez de sqlite3.connect(caminho) (que não lê um banco cifrado).
ATIVO = {'caminho': '', 'chave': None}


def definir_ativo(caminho, chave_hex):
    ATIVO['caminho'], ATIVO['chave'] = caminho, chave_hex


def caminho_ativo():
    return ATIVO['caminho']


def conectar_ativo(timeout=30):
    return conectar(ATIVO['caminho'], ATIVO['chave'], timeout)

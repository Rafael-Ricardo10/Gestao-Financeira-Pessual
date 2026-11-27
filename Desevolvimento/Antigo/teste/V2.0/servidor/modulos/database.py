"""
Banco de dados por usuário
Suporte a JSON (fase 1-2) e PostgreSQL (fase 3+)
Sharding de 4 níveis para bilhões de usuários
Lock granular por usuário (sem lock global no login)
"""

import os
import json
import uuid
import threading
import secrets as secrets_module
from pathlib import Path
from datetime import datetime, timedelta
from modulos.crypto import (
    criptografar_dados, descriptografar_dados,
    gerar_salt, hash_senha, verificar_senha,
    derivar_chave_usuario
)
from modulos.logs import registrar_log
import hashlib

DADOS_DIR   = Path("dados")
USUARIOS_DIR = DADOS_DIR / "usuarios"
SISTEMA_DIR  = DADOS_DIR / "sistema"

# ==================== LOCKS GRANULARES ====================
_lock_criar_usuario = threading.Lock()
_locks_usuario      = {}
_lock_locks         = threading.Lock()

def _get_lock_usuario(user_id: str) -> threading.Lock:
    with _lock_locks:
        if user_id not in _locks_usuario:
            _locks_usuario[user_id] = threading.Lock()
        return _locks_usuario[user_id]

# ==================== SHARDING 4 NÍVEIS ====================
def _caminho_usuario(user_id: str) -> Path:
    uid    = user_id if len(user_id) >= 8 else user_id.ljust(8, '0')
    shard1 = uid[0:2]
    shard2 = uid[2:4]
    shard3 = uid[4:6]
    return USUARIOS_DIR / shard1 / shard2 / shard3 / user_id

# ==================== BACKEND JSON ====================
def _json_carregar_indice() -> dict:
    path = SISTEMA_DIR / "indice_usuarios.json"
    try:
        if not path.exists():
            return {}
        with open(path, 'r') as f:
            conteudo = f.read().strip()
            if not conteudo:
                return {}
            return json.loads(conteudo)
    except Exception as e:
        registrar_log("database", f"Erro ao carregar indice: {str(e)}")
        return {}

def _json_salvar_indice(indice: dict):
    path     = SISTEMA_DIR / "indice_usuarios.json"
    path_tmp = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path_tmp, 'w') as f:
        json.dump(indice, f, indent=2, ensure_ascii=False)
    path_tmp.replace(path)

def _json_buscar_por_username(username: str) -> dict | None:
    indice = _json_carregar_indice()
    for meta in indice.values():
        if meta.get('username', '').lower() == username.lower():
            return meta
    return None

def _json_buscar_por_id(user_id: str) -> dict | None:
    indice = _json_carregar_indice()
    return indice.get(user_id)

# ==================== ABSTRAÇÃO DE BACKEND ====================
DB_BACKEND = os.environ.get('DB_BACKEND', 'json')

def _carregar_indice_usuarios() -> dict:
    if DB_BACKEND == 'postgres':
        return _pg_carregar_todos()
    return _json_carregar_indice()

def _salvar_indice_usuarios(indice: dict):
    if DB_BACKEND == 'postgres':
        return _pg_salvar_todos(indice)
    return _json_salvar_indice(indice)

def _buscar_usuario_por_username(username: str) -> dict | None:
    if DB_BACKEND == 'postgres':
        return _pg_buscar_por_username(username)
    return _json_buscar_por_username(username)

def _buscar_usuario_por_id(user_id: str) -> dict | None:
    if DB_BACKEND == 'postgres':
        return _pg_buscar_por_id(user_id)
    return _json_buscar_por_id(user_id)

def _salvar_usuario_unico(meta: dict):
    if DB_BACKEND == 'postgres':
        return _pg_salvar_usuario(meta)
    indice = _json_carregar_indice()
    indice[meta['user_id']] = meta
    _json_salvar_indice(indice)

def _username_existe(username: str) -> bool:
    return _buscar_usuario_por_username(username) is not None

# ==================== POSTGRESQL (fase 3+) ====================
_pg_pool = None
_pg_lock = threading.Lock()

def _get_pg_conn():
    global _pg_pool
    if _pg_pool is None:
        with _pg_lock:
            if _pg_pool is None:
                try:
                    import psycopg2.pool
                    _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                        minconn=2, maxconn=20,
                        dsn=os.environ.get('DATABASE_URL')
                    )
                except Exception as e:
                    registrar_log("database", f"Erro pool PostgreSQL: {str(e)}")
                    raise
    return _pg_pool.getconn()

def _release_pg_conn(conn):
    if _pg_pool:
        _pg_pool.putconn(conn)

def _pg_buscar_por_username(username: str) -> dict | None:
    conn = None
    try:
        import psycopg2.extras
        conn = _get_pg_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM usuarios WHERE LOWER(username)=LOWER(%s)", (username,))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        if conn: _release_pg_conn(conn)

def _pg_buscar_por_id(user_id: str) -> dict | None:
    conn = None
    try:
        import psycopg2.extras
        conn = _get_pg_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM usuarios WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        if conn: _release_pg_conn(conn)

def _pg_carregar_todos() -> dict:
    conn = None
    try:
        import psycopg2.extras
        conn = _get_pg_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM usuarios")
        return {r['user_id']: dict(r) for r in cur.fetchall()}
    except Exception:
        return {}
    finally:
        if conn: _release_pg_conn(conn)

def _pg_salvar_usuario(meta: dict):
    conn = None
    try:
        conn = _get_pg_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO usuarios (
                user_id, username, hash_senha, salt, salt_chave,
                is_admin, ativo, suspenso, criado_em, ultimo_acesso,
                deve_trocar_senha
            ) VALUES (
                %(user_id)s, %(username)s, %(hash_senha)s,
                %(salt)s, %(salt_chave)s, %(is_admin)s,
                %(ativo)s, %(suspenso)s, %(criado_em)s,
                %(ultimo_acesso)s, %(deve_trocar_senha)s
            )
            ON CONFLICT (user_id) DO UPDATE SET
                hash_senha=EXCLUDED.hash_senha,
                salt_chave=EXCLUDED.salt_chave,
                ultimo_acesso=EXCLUDED.ultimo_acesso,
                suspenso=EXCLUDED.suspenso,
                ativo=EXCLUDED.ativo,
                deve_trocar_senha=EXCLUDED.deve_trocar_senha
        """, meta)
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        registrar_log("database", f"Erro PG salvar usuario")
    finally:
        if conn: _release_pg_conn(conn)

def _pg_salvar_todos(indice: dict):
    for meta in indice.values():
        _pg_salvar_usuario(meta)

SQL_CRIAR_TABELA_POSTGRES = """
CREATE TABLE IF NOT EXISTS usuarios (
    user_id           VARCHAR(64)  PRIMARY KEY,
    username          VARCHAR(50)  UNIQUE NOT NULL,
    hash_senha        TEXT         NOT NULL,
    salt              VARCHAR(128),
    salt_chave        VARCHAR(128) NOT NULL,
    is_admin          BOOLEAN      DEFAULT FALSE,
    ativo             BOOLEAN      DEFAULT TRUE,
    suspenso          BOOLEAN      DEFAULT FALSE,
    criado_em         TIMESTAMPTZ,
    ultimo_acesso     TIMESTAMPTZ,
    deve_trocar_senha BOOLEAN      DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_username_lower ON usuarios(LOWER(username));
CREATE INDEX IF NOT EXISTS idx_ultimo_acesso  ON usuarios(ultimo_acesso);
"""

# ==================== INICIALIZAÇÃO ====================
def inicializar_db():
    DADOS_DIR.mkdir(exist_ok=True)
    USUARIOS_DIR.mkdir(exist_ok=True)
    SISTEMA_DIR.mkdir(exist_ok=True)

    if DB_BACKEND == 'json':
        path = SISTEMA_DIR / "indice_usuarios.json"
        if not path.exists():
            _json_salvar_indice({})

    _criar_admin_padrao()

def _estrutura_dados_inicial() -> dict:
    return {
        "transacoes"   : [],
        "categorias"   : [],
        "configuracoes": {"moeda": "BRL", "tema": "dark"},
        "historico_ia" : [],
        "ultimo_acesso": datetime.now().isoformat()
    }

def _salvar_dados_usuario_enc(user_id: str, dados: dict, chave: bytes):
    caminho     = _caminho_usuario(user_id)
    caminho.mkdir(parents=True, exist_ok=True)
    arquivo     = caminho / "dados.enc"
    arquivo_tmp = arquivo.with_suffix('.tmp')
    dados_enc   = criptografar_dados(dados, chave)
    with open(arquivo_tmp, 'wb') as f:
        f.write(dados_enc)
    arquivo_tmp.replace(arquivo)

def _carregar_dados_usuario_enc(user_id: str, chave: bytes) -> dict:
    arquivo = _caminho_usuario(user_id) / "dados.enc"
    if not arquivo.exists():
        return _estrutura_dados_inicial()
    with open(arquivo, 'rb') as f:
        dados_enc = f.read()
    return descriptografar_dados(dados_enc, chave)

def _criar_admin_padrao():
    """
    Cria admin padrão com senha admin/admin.
    Força troca de senha no primeiro acesso.
    A senha 'admin' é apenas para o PRIMEIRO login.
    """
    # Verifica se já existe
    existente = _buscar_usuario_por_username('admin')
    if existente:
        return  # Já existe, não recria

    # Senha inicial SIMPLES para primeiro acesso = "admin"
    # O sistema força troca imediata (deve_trocar_senha=True)
    SENHA_INICIAL = "admin"

    admin_id   = "admin_" + hashlib.sha256(b"admin_financeia_v1").hexdigest()[:16]
    salt_chave = gerar_salt()
    hash_pw    = hash_senha(SENHA_INICIAL)
    chave      = derivar_chave_usuario(SENHA_INICIAL, salt_chave)

    meta_admin = {
        "user_id"          : admin_id,
        "username"         : "admin",
        "hash_senha"       : hash_pw,
        "salt"             : gerar_salt().hex(),
        "salt_chave"       : salt_chave.hex(),
        "is_admin"         : True,
        "ativo"            : True,
        "suspenso"         : False,
        "criado_em"        : datetime.now().isoformat(),
        "ultimo_acesso"    : None,
        "deve_trocar_senha": True   # Força troca no primeiro acesso
    }

    # Salva no índice
    _salvar_usuario_unico(meta_admin)

    # Cria dados iniciais criptografados
    caminho = _caminho_usuario(admin_id)
    caminho.mkdir(parents=True, exist_ok=True)
    _salvar_dados_usuario_enc(admin_id, _estrutura_dados_inicial(), chave)

    print("\n" + "="*60)
    print("  ADMINISTRADOR CRIADO")
    print("="*60)
    print("  Usuario : admin")
    print("  Senha   : admin")
    print("  TROQUE A SENHA NO PRIMEIRO ACESSO!")
    print("="*60 + "\n")

# ==================== OPERAÇÕES PRINCIPAIS ====================

def registrar_usuario(username: str, senha: str) -> tuple[bool, str]:
    import re

    if len(username) < 3 or len(username) > 50:
        return False, "Username deve ter entre 3 e 50 caracteres"

    if not re.match(r'^[a-zA-Z0-9_.\-]+$', username):
        return False, "Username: use apenas letras, numeros, _, . ou -"

    if len(senha) < 8:
        return False, "Senha deve ter no minimo 8 caracteres"

    with _lock_criar_usuario:
        if _username_existe(username):
            return False, "Usuário já existe"

        user_id    = str(uuid.uuid4()).replace('-', '')
        salt_chave = gerar_salt()
        hash_pw    = hash_senha(senha)
        chave      = derivar_chave_usuario(senha, salt_chave)

        meta = {
            "user_id"          : user_id,
            "username"         : username,
            "hash_senha"       : hash_pw,
            "salt"             : gerar_salt().hex(),
            "salt_chave"       : salt_chave.hex(),
            "is_admin"         : False,
            "ativo"            : True,
            "suspenso"         : False,
            "criado_em"        : datetime.now().isoformat(),
            "ultimo_acesso"    : None,
            "deve_trocar_senha": False
        }

        _salvar_usuario_unico(meta)

        caminho = _caminho_usuario(user_id)
        caminho.mkdir(parents=True, exist_ok=True)
        _salvar_dados_usuario_enc(user_id, _estrutura_dados_inicial(), chave)

    return True, user_id

def autenticar_usuario(username: str, senha: str) -> tuple[bool, dict]:
    """Login sem lock global"""
    meta = _buscar_usuario_por_username(username)

    if not meta:
        # Timing attack prevention
        hash_senha("dummy_xYz9_prevention_hash")
        return False, {"erro": "Credenciais inválidas"}

    if meta.get('suspenso'):
        return False, {"erro": "Conta suspensa pelo administrador"}

    if not verificar_senha(meta['hash_senha'], senha):
        return False, {"erro": "Credenciais inválidas"}

    # Atualiza último acesso apenas deste usuário
    meta['ultimo_acesso'] = datetime.now().isoformat()
    _salvar_usuario_unico(meta)

    return True, {
        "user_id"          : meta['user_id'],
        "username"         : meta['username'],
        "is_admin"         : meta.get('is_admin', False),
        "salt_chave"       : meta['salt_chave'],
        "deve_trocar_senha": meta.get('deve_trocar_senha', False)
    }

def obter_chave_usuario(user_id: str, senha: str) -> bytes:
    meta = _buscar_usuario_por_id(user_id)
    if not meta:
        raise ValueError("Usuário não encontrado")
    salt_chave = bytes.fromhex(meta['salt_chave'])
    return derivar_chave_usuario(senha, salt_chave)

def carregar_dados_usuario(user_id: str, chave: bytes) -> dict:
    lock = _get_lock_usuario(user_id)
    with lock:
        return _carregar_dados_usuario_enc(user_id, chave)

def salvar_dados_usuario(user_id: str, dados: dict, chave: bytes):
    lock = _get_lock_usuario(user_id)
    with lock:
        _salvar_dados_usuario_enc(user_id, dados, chave)

def alterar_senha_usuario(user_id: str, senha_atual: str, nova_senha: str) -> tuple[bool, str]:
    meta = _buscar_usuario_por_id(user_id)
    if not meta:
        return False, "Usuário não encontrado"

    if not verificar_senha(meta['hash_senha'], senha_atual):
        return False, "Senha atual incorreta"

    if len(nova_senha) < 8:
        return False, "Nova senha deve ter no mínimo 8 caracteres"

    # Carrega dados com chave antiga
    chave_antiga = derivar_chave_usuario(
        senha_atual, bytes.fromhex(meta['salt_chave'])
    )
    try:
        dados = _carregar_dados_usuario_enc(user_id, chave_antiga)
    except Exception:
        return False, "Erro ao acessar dados"

    # Novo salt e nova chave
    novo_salt  = gerar_salt()
    nova_chave = derivar_chave_usuario(nova_senha, novo_salt)

    # Re-criptografa com nova chave
    _salvar_dados_usuario_enc(user_id, dados, nova_chave)

    # Atualiza metadados
    meta['hash_senha']        = hash_senha(nova_senha)
    meta['salt_chave']        = novo_salt.hex()
    meta['deve_trocar_senha'] = False
    _salvar_usuario_unico(meta)

    return True, "Senha alterada com sucesso"

def listar_usuarios_admin() -> list:
    indice = _carregar_indice_usuarios()
    return [
        {
            "user_id"     : m.get('user_id'),
            "username"    : m.get('username'),
            "is_admin"    : m.get('is_admin', False),
            "ativo"       : m.get('ativo', True),
            "suspenso"    : m.get('suspenso', False),
            "criado_em"   : m.get('criado_em'),
            "ultimo_acesso": m.get('ultimo_acesso')
        }
        for m in indice.values()
    ]

def suspender_usuario(admin_id: str, user_id: str, suspender: bool) -> bool:
    admin = _buscar_usuario_por_id(admin_id)
    if not admin or not admin.get('is_admin'):
        return False
    meta = _buscar_usuario_por_id(user_id)
    if not meta:
        return False
    meta['suspenso'] = suspender
    _salvar_usuario_unico(meta)
    return True

def excluir_usuario(admin_id: str, user_id: str) -> bool:
    admin = _buscar_usuario_por_id(admin_id)
    if not admin or not admin.get('is_admin'):
        return False

    import shutil
    caminho = _caminho_usuario(user_id)
    if caminho.exists():
        shutil.rmtree(caminho)

    if DB_BACKEND == 'postgres':
        conn = None
        try:
            conn = _get_pg_conn()
            cur  = conn.cursor()
            cur.execute("DELETE FROM usuarios WHERE user_id=%s", (user_id,))
            conn.commit()
        except Exception:
            if conn: conn.rollback()
            return False
        finally:
            if conn: _release_pg_conn(conn)
    else:
        indice = _json_carregar_indice()
        indice.pop(user_id, None)
        _json_salvar_indice(indice)

    return True

def limpar_usuarios_inativos():
    cutoff = (datetime.now() - timedelta(days=90)).isoformat()

    if DB_BACKEND == 'postgres':
        conn = None
        try:
            conn = _get_pg_conn()
            cur  = conn.cursor()
            cur.execute("""
                SELECT user_id FROM usuarios
                WHERE is_admin=FALSE
                  AND COALESCE(ultimo_acesso, criado_em) < %s
            """, (cutoff,))
            inativos = [r[0] for r in cur.fetchall()]

            import shutil
            for uid in inativos:
                p = _caminho_usuario(uid)
                if p.exists(): shutil.rmtree(p)

            cur.execute("""
                DELETE FROM usuarios
                WHERE is_admin=FALSE
                  AND COALESCE(ultimo_acesso, criado_em) < %s
            """, (cutoff,))
            conn.commit()
            if inativos:
                registrar_log("sistema", f"{len(inativos)} usuarios inativos removidos")
        except Exception:
            if conn: conn.rollback()
        finally:
            if conn: _release_pg_conn(conn)
    else:
        indice = _json_carregar_indice()
        remover = []
        for uid, meta in indice.items():
            if meta.get('is_admin'):
                continue
            data_ref = meta.get('ultimo_acesso') or meta.get('criado_em')
            if data_ref and data_ref < cutoff:
                remover.append(uid)

        import shutil
        for uid in remover:
            p = _caminho_usuario(uid)
            if p.exists(): shutil.rmtree(p)
            del indice[uid]

        if remover:
            _json_salvar_indice(indice)
            registrar_log("sistema", f"{len(remover)} usuarios inativos removidos")

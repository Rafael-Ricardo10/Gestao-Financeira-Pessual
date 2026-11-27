"""
Banco de dados por usuário - cada usuário tem seu arquivo criptografado
Estrutura: dados/usuarios/{user_id}/dados.enc
Suporta bilhões de usuários via sharding por diretório
"""

import os
import json
import uuid
import threading
from pathlib import Path
from datetime import datetime, timedelta
from modulos.crypto import (
    criptografar_dados, descriptografar_dados,
    criptografar_campo, descriptografar_campo,
    gerar_salt, hash_senha, verificar_senha,
    derivar_chave_usuario
)
from modulos.logs import registrar_log
import hashlib

DADOS_DIR = Path("dados")
USUARIOS_DIR = DADOS_DIR / "usuarios"
SISTEMA_DIR = DADOS_DIR / "sistema"

_lock_global = threading.Lock()
_locks_usuario = {}

def _get_lock_usuario(user_id: str) -> threading.Lock:
    """Lock por usuário para operações concorrentes"""
    with _lock_global:
        if user_id not in _locks_usuario:
            _locks_usuario[user_id] = threading.Lock()
        return _locks_usuario[user_id]

def _caminho_usuario(user_id: str) -> Path:
    """
    Sharding: primeiros 2 chars do ID como subdiretório
    Suporta bilhões de usuários sem degradação
    """
    shard = user_id[:2]
    return USUARIOS_DIR / shard / user_id

def inicializar_db():
    """Cria estrutura de diretórios"""
    DADOS_DIR.mkdir(exist_ok=True)
    USUARIOS_DIR.mkdir(exist_ok=True)
    SISTEMA_DIR.mkdir(exist_ok=True)

    # Arquivo de índice de usuários (apenas metadados, sem dados sensíveis)
    indice_path = SISTEMA_DIR / "indice_usuarios.json"
    if not indice_path.exists():
        _salvar_json_sistema(indice_path, {})

    # Admin padrão
    _criar_admin_padrao()

def _salvar_json_sistema(path: Path, dados: dict):
    """Salva JSON do sistema (não dados de usuário)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

def _carregar_json_sistema(path: Path) -> dict:
    """Carrega JSON do sistema"""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _criar_admin_padrao():
    """Cria administrador padrão admin/admin"""
    indice = _carregar_indice_usuarios()

    # Verifica se já existe admin
    for uid, meta in indice.items():
        if meta.get('username') == 'admin':
            return

    # Cria admin
    admin_id = "admin_" + hashlib.sha256(b"admin_fixo").hexdigest()[:16]
    salt = gerar_salt()
    hash_pw = hash_senha("admin")

    meta_admin = {
        "user_id": admin_id,
        "username": "admin",
        "hash_senha": hash_pw,
        "salt": salt.hex(),
        "salt_chave": gerar_salt().hex(),
        "is_admin": True,
        "ativo": True,
        "criado_em": datetime.now().isoformat(),
        "ultimo_acesso": None,
        "suspenso": False,
        "deve_trocar_senha": True
    }

    indice[admin_id] = meta_admin
    _salvar_indice_usuarios(indice)

    # Cria diretório e dados vazios do admin
    caminho = _caminho_usuario(admin_id)
    caminho.mkdir(parents=True, exist_ok=True)

    # Chave derivada da senha admin
    chave = derivar_chave_usuario("admin", bytes.fromhex(meta_admin['salt_chave']))
    dados_iniciais = _estrutura_dados_inicial()

    _salvar_dados_usuario_enc(admin_id, dados_iniciais, chave)
    print("[DB] Administrador padrão criado: admin/admin")

def _carregar_indice_usuarios() -> dict:
    """Carrega índice de usuários"""
    path = SISTEMA_DIR / "indice_usuarios.json"
    return _carregar_json_sistema(path)

def _salvar_indice_usuarios(indice: dict):
    """Salva índice de usuários"""
    path = SISTEMA_DIR / "indice_usuarios.json"
    _salvar_json_sistema(path, indice)

def _estrutura_dados_inicial() -> dict:
    """Estrutura inicial de dados do usuário"""
    return {
        "transacoes": [],
        "categorias": [],
        "configuracoes": {
            "moeda": "BRL",
            "tema": "dark"
        },
        "historico_ia": [],
        "ultimo_acesso": datetime.now().isoformat()
    }

def _salvar_dados_usuario_enc(user_id: str, dados: dict, chave: bytes):
    """Salva dados criptografados do usuário"""
    caminho = _caminho_usuario(user_id)
    caminho.mkdir(parents=True, exist_ok=True)
    arquivo = caminho / "dados.enc"

    dados_enc = criptografar_dados(dados, chave)
    with open(arquivo, 'wb') as f:
        f.write(dados_enc)

def _carregar_dados_usuario_enc(user_id: str, chave: bytes) -> dict:
    """Carrega e descriptografa dados do usuário"""
    arquivo = _caminho_usuario(user_id) / "dados.enc"

    if not arquivo.exists():
        return _estrutura_dados_inicial()

    with open(arquivo, 'rb') as f:
        dados_enc = f.read()

    return descriptografar_dados(dados_enc, chave)

# ==================== OPERAÇÕES DE USUÁRIO ====================

def registrar_usuario(username: str, senha: str) -> tuple[bool, str]:
    """
    Registra novo usuário
    Retorna: (sucesso, mensagem)
    """
    with _lock_global:
        indice = _carregar_indice_usuarios()

        # Verifica username único
        for uid, meta in indice.items():
            if meta.get('username', '').lower() == username.lower():
                return False, "Usuário já existe"

        if len(username) < 3 or len(username) > 50:
            return False, "Username deve ter entre 3 e 50 caracteres"

        if len(senha) < 8:
            return False, "Senha deve ter no mínimo 8 caracteres"

        # Gera IDs únicos
        user_id = str(uuid.uuid4()).replace('-', '')
        salt = gerar_salt()
        salt_chave = gerar_salt()
        hash_pw = hash_senha(senha)

        meta = {
            "user_id": user_id,
            "username": username,
            "hash_senha": hash_pw,
            "salt": salt.hex(),
            "salt_chave": salt_chave.hex(),
            "is_admin": False,
            "ativo": True,
            "criado_em": datetime.now().isoformat(),
            "ultimo_acesso": None,
            "suspenso": False,
            "deve_trocar_senha": False
        }

        indice[user_id] = meta
        _salvar_indice_usuarios(indice)

        # Cria dados iniciais criptografados
        chave = derivar_chave_usuario(senha, salt_chave)
        caminho = _caminho_usuario(user_id)
        caminho.mkdir(parents=True, exist_ok=True)
        _salvar_dados_usuario_enc(user_id, _estrutura_dados_inicial(), chave)

        return True, user_id

def autenticar_usuario(username: str, senha: str) -> tuple[bool, dict]:
    """
    Autentica usuário
    Retorna: (sucesso, {user_id, is_admin, ...} ou erro)
    """
    indice = _carregar_indice_usuarios()

    usuario_meta = None
    for uid, meta in indice.items():
        if meta.get('username', '').lower() == username.lower():
            usuario_meta = meta
            break

    if not usuario_meta:
        # Timing attack prevention
        hash_senha("dummy_para_timing")
        return False, {"erro": "Credenciais inválidas"}

    if usuario_meta.get('suspenso'):
        return False, {"erro": "Conta suspensa pelo administrador"}

    if not verificar_senha(usuario_meta['hash_senha'], senha):
        return False, {"erro": "Credenciais inválidas"}

    # Atualiza último acesso
    with _lock_global:
        indice[usuario_meta['user_id']]['ultimo_acesso'] = datetime.now().isoformat()
        _salvar_indice_usuarios(indice)

    return True, {
        "user_id": usuario_meta['user_id'],
        "username": usuario_meta['username'],
        "is_admin": usuario_meta.get('is_admin', False),
        "salt_chave": usuario_meta['salt_chave'],
        "deve_trocar_senha": usuario_meta.get('deve_trocar_senha', False)
    }

def obter_chave_usuario(user_id: str, senha: str) -> bytes:
    """Deriva chave do usuário a partir da senha"""
    indice = _carregar_indice_usuarios()
    meta = indice.get(user_id)
    if not meta:
        raise ValueError("Usuário não encontrado")
    salt_chave = bytes.fromhex(meta['salt_chave'])
    return derivar_chave_usuario(senha, salt_chave)

def carregar_dados_usuario(user_id: str, chave: bytes) -> dict:
    """Carrega dados descriptografados do usuário"""
    lock = _get_lock_usuario(user_id)
    with lock:
        return _carregar_dados_usuario_enc(user_id, chave)

def salvar_dados_usuario(user_id: str, dados: dict, chave: bytes):
    """Salva dados criptografados do usuário"""
    lock = _get_lock_usuario(user_id)
    with lock:
        _salvar_dados_usuario_enc(user_id, dados, chave)

def alterar_senha_usuario(user_id: str, senha_atual: str, nova_senha: str) -> tuple[bool, str]:
    """Altera senha e re-criptografa dados com nova chave"""
    with _lock_global:
        indice = _carregar_indice_usuarios()
        meta = indice.get(user_id)

        if not meta:
            return False, "Usuário não encontrado"

        if not verificar_senha(meta['hash_senha'], senha_atual):
            return False, "Senha atual incorreta"

        if len(nova_senha) < 8:
            return False, "Nova senha deve ter no mínimo 8 caracteres"

        # Carrega dados com chave antiga
        salt_chave_antigo = bytes.fromhex(meta['salt_chave'])
        chave_antiga = derivar_chave_usuario(senha_atual, salt_chave_antigo)

        try:
            dados = _carregar_dados_usuario_enc(user_id, chave_antiga)
        except Exception:
            return False, "Erro ao acessar dados"

        # Novo salt e chave
        novo_salt_chave = gerar_salt()
        nova_chave = derivar_chave_usuario(nova_senha, novo_salt_chave)
        novo_hash = hash_senha(nova_senha)

        # Re-criptografa dados
        _salvar_dados_usuario_enc(user_id, dados, nova_chave)

        # Atualiza metadados
        indice[user_id]['hash_senha'] = novo_hash
        indice[user_id]['salt_chave'] = novo_salt_chave.hex()
        indice[user_id]['deve_trocar_senha'] = False
        _salvar_indice_usuarios(indice)

        return True, "Senha alterada com sucesso"

def listar_usuarios_admin() -> list:
    """Lista usuários para o administrador (sem dados sensíveis)"""
    indice = _carregar_indice_usuarios()
    resultado = []
    for uid, meta in indice.items():
        resultado.append({
            "user_id": uid,
            "username": meta.get('username'),
            "is_admin": meta.get('is_admin', False),
            "ativo": meta.get('ativo', True),
            "suspenso": meta.get('suspenso', False),
            "criado_em": meta.get('criado_em'),
            "ultimo_acesso": meta.get('ultimo_acesso')
        })
    return resultado

def suspender_usuario(admin_id: str, user_id: str, suspender: bool) -> bool:
    """Admin suspende/reativa usuário"""
    with _lock_global:
        indice = _carregar_indice_usuarios()
        admin = indice.get(admin_id)

        if not admin or not admin.get('is_admin'):
            return False

        if user_id in indice:
            indice[user_id]['suspenso'] = suspender
            _salvar_indice_usuarios(indice)
            return True
        return False

def excluir_usuario(admin_id: str, user_id: str) -> bool:
    """Admin exclui usuário e seus dados"""
    with _lock_global:
        indice = _carregar_indice_usuarios()
        admin = indice.get(admin_id)

        if not admin or not admin.get('is_admin'):
            return False

        if user_id in indice:
            # Remove dados criptografados
            import shutil
            caminho = _caminho_usuario(user_id)
            if caminho.exists():
                shutil.rmtree(caminho)

            del indice[user_id]
            _salvar_indice_usuarios(indice)
            return True
        return False

def limpar_usuarios_inativos():
    """Remove usuários inativos há mais de 3 meses"""
    with _lock_global:
        indice = _carregar_indice_usuarios()
        cutoff = datetime.now() - timedelta(days=90)
        para_remover = []

        for uid, meta in indice.items():
            if meta.get('is_admin'):
                continue

            ultimo = meta.get('ultimo_acesso')
            criado = meta.get('criado_em')

            # Usa criado_em se nunca acessou
            data_ref = ultimo or criado
            if data_ref:
                try:
                    data = datetime.fromisoformat(data_ref)
                    if data < cutoff:
                        para_remover.append(uid)
                except Exception:
                    pass

        import shutil
        for uid in para_remover:
            caminho = _caminho_usuario(uid)
            if caminho.exists():
                shutil.rmtree(caminho)
            del indice[uid]

        if para_remover:
            _salvar_indice_usuarios(indice)
            print(f"[DB] {len(para_remover)} usuários inativos removidos")

"""
Autenticação segura
- Rate limit por IP E por username
- Chave de sessão criptografada no Redis
- Sem dados sensíveis em logs
"""

import jwt
import secrets
import time
import base64
import os
import threading
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from modulos.database import autenticar_usuario, obter_chave_usuario
from modulos.logs import registrar_log
from modulos.cache import cache

JWT_SECRET      = secrets.token_hex(64)
JWT_ALGORITHM   = "HS256"
JWT_HORAS       = 8

# Chave mestra para criptografar chaves de sessão no Redis
# Existe APENAS na RAM do processo - nunca em disco
_CHAVE_MESTRA = secrets.token_bytes(32)

# Rate limiting
_tentativas_ip   = {}
_tentativas_user = {}
_LIMITE          = 5
_BLOQUEIO        = 300  # segundos
_lock_rate       = threading.Lock()

# ==================== CRIPTOGRAFIA DA SESSÃO ====================

def _cifrar_chave(chave_usuario: bytes) -> str:
    """Criptografa chave do usuário com chave mestra antes de salvar no Redis"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(_CHAVE_MESTRA)
    nonce = secrets.token_bytes(12)
    cifrado = aesgcm.encrypt(nonce, chave_usuario, None)
    return base64.b64encode(nonce + cifrado).decode()

def _decifrar_chave(cifrada_b64: str) -> bytes:
    """Descriptografa chave do usuário usando chave mestra"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        raw = base64.b64decode(cifrada_b64)
        aesgcm = AESGCM(_CHAVE_MESTRA)
        return aesgcm.decrypt(raw[:12], raw[12:], None)
    except Exception:
        raise ValueError("Sessão inválida ou expirada")

# ==================== RATE LIMITING ====================

def _hash_user(username: str) -> str:
    return hashlib.sha256(username.lower().encode()).hexdigest()[:16]

def _bloqueado(ip: str, username: str) -> tuple[bool, str]:
    agora = time.time()
    with _lock_rate:
        # Verifica IP
        d_ip = _tentativas_ip.get(ip, {})
        if agora < d_ip.get('bloqueado_ate', 0):
            restante = int(d_ip['bloqueado_ate'] - agora)
            return True, f"IP bloqueado. Aguarde {restante}s"

        # Verifica username
        hu = _hash_user(username)
        d_u = _tentativas_user.get(hu, {})
        if agora < d_u.get('bloqueado_ate', 0):
            restante = int(d_u['bloqueado_ate'] - agora)
            return True, f"Usuario bloqueado. Aguarde {restante}s"

    return False, ""

def _registrar_falha(ip: str, username: str):
    agora = time.time()
    with _lock_rate:
        # Por IP
        if ip not in _tentativas_ip:
            _tentativas_ip[ip] = {'count': 0, 'bloqueado_ate': 0}
        _tentativas_ip[ip]['count'] += 1
        if _tentativas_ip[ip]['count'] >= _LIMITE:
            _tentativas_ip[ip]['bloqueado_ate'] = agora + _BLOQUEIO
            registrar_log("auth", "IP bloqueado por excesso de tentativas")

        # Por username
        hu = _hash_user(username)
        if hu not in _tentativas_user:
            _tentativas_user[hu] = {'count': 0, 'bloqueado_ate': 0}
        _tentativas_user[hu]['count'] += 1
        if _tentativas_user[hu]['count'] >= _LIMITE:
            _tentativas_user[hu]['bloqueado_ate'] = agora + _BLOQUEIO
            registrar_log("auth", "Usuario bloqueado por excesso de tentativas")

def _limpar_rate(ip: str, username: str):
    with _lock_rate:
        _tentativas_ip.pop(ip, None)
        _tentativas_user.pop(_hash_user(username), None)

# ==================== JWT ====================

def gerar_token_jwt(user_id: str, username: str, is_admin: bool) -> str:
    payload = {
        "user_id"  : user_id,
        "username" : username,
        "is_admin" : is_admin,
        "iat"      : datetime.utcnow(),
        "exp"      : datetime.utcnow() + timedelta(hours=JWT_HORAS),
        "jti"      : secrets.token_hex(16)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verificar_token_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return {"erro": "Token expirado"}
    except jwt.InvalidTokenError:
        return {"erro": "Token inválido"}

# ==================== LOGIN ====================

def fazer_login(username: str, senha: str, ip: str) -> tuple[bool, dict]:
    bloqueado, motivo = _bloqueado(ip, username)
    if bloqueado:
        return False, {"erro": motivo}

    sucesso, dados = autenticar_usuario(username, senha)
    if not sucesso:
        _registrar_falha(ip, username)
        return False, dados

    _limpar_rate(ip, username)

    # Deriva chave e criptografa antes de salvar no Redis
    chave = obter_chave_usuario(dados['user_id'], senha)
    chave_cifrada = _cifrar_chave(chave)

    chave_sessao = secrets.token_hex(32)
    cache.set(
        f"chave_sessao_{chave_sessao}",
        {"user_id": dados['user_id'], "chave_enc": chave_cifrada},
        ttl=JWT_HORAS * 3600
    )

    token = gerar_token_jwt(
        dados['user_id'], dados['username'], dados['is_admin']
    )

    return True, {
        "token"            : token,
        "username"         : dados['username'],
        "is_admin"         : dados['is_admin'],
        "chave_sessao"     : chave_sessao,
        "deve_trocar_senha": dados.get('deve_trocar_senha', False)
    }

def obter_chave_da_sessao(chave_sessao: str, user_id: str) -> bytes:
    dados = cache.get(f"chave_sessao_{chave_sessao}")
    if not dados or dados.get('user_id') != user_id:
        raise ValueError("Sessão inválida ou expirada")
    return _decifrar_chave(dados['chave_enc'])

# ==================== DECORATORS ====================

def requer_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        if not token:
            token = request.cookies.get('auth_token')
        if not token:
            return jsonify({"erro": "Autenticação necessária"}), 401
        payload = verificar_token_jwt(token)
        if "erro" in payload:
            return jsonify(payload), 401
        request.user_id  = payload['user_id']
        request.username = payload['username']
        request.is_admin = payload['is_admin']
        return f(*args, **kwargs)
    return decorated

def requer_admin(f):
    @wraps(f)
    @requer_auth
    def decorated(*args, **kwargs):
        if not request.is_admin:
            return jsonify({"erro": "Acesso negado"}), 403
        return f(*args, **kwargs)
    return decorated

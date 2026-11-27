"""
Autenticação e gestão de sessões seguras
"""

import jwt
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session
from modulos.database import autenticar_usuario, obter_chave_usuario
from modulos.logs import registrar_log
from modulos.cache import cache
import hashlib

# Chave secreta JWT (gerada na inicialização)
JWT_SECRET = secrets.token_hex(64)
JWT_ALGORITHM = "HS256"
JWT_EXPIRACAO_HORAS = 8

# Controle de tentativas de login (anti-brute force)
_tentativas_login = {}
_LIMITE_TENTATIVAS = 5
_BLOQUEIO_SEGUNDOS = 300  # 5 minutos

def _verificar_bloqueio(ip: str) -> bool:
    """Verifica se IP está bloqueado"""
    dados = _tentativas_login.get(ip, {"count": 0, "bloqueado_ate": 0})

    if time.time() < dados.get("bloqueado_ate", 0):
        return True

    if time.time() > dados.get("bloqueado_ate", 0) and dados.get("bloqueado_ate", 0) > 0:
        _tentativas_login[ip] = {"count": 0, "bloqueado_ate": 0}

    return False

def _registrar_tentativa_falha(ip: str):
    """Registra tentativa de login falha"""
    if ip not in _tentativas_login:
        _tentativas_login[ip] = {"count": 0, "bloqueado_ate": 0}

    _tentativas_login[ip]["count"] += 1

    if _tentativas_login[ip]["count"] >= _LIMITE_TENTATIVAS:
        _tentativas_login[ip]["bloqueado_ate"] = time.time() + _BLOQUEIO_SEGUNDOS
        registrar_log("auth", f"IP {ip} bloqueado por excesso de tentativas")

def _limpar_tentativas(ip: str):
    """Limpa tentativas após login bem-sucedido"""
    _tentativas_login.pop(ip, None)

def gerar_token_jwt(user_id: str, username: str, is_admin: bool) -> str:
    """Gera token JWT seguro"""
    payload = {
        "user_id": user_id,
        "username": username,
        "is_admin": is_admin,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRACAO_HORAS),
        "jti": secrets.token_hex(16)  # JWT ID único
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verificar_token_jwt(token: str) -> dict:
    """Verifica e decodifica token JWT"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return {"erro": "Token expirado"}
    except jwt.InvalidTokenError:
        return {"erro": "Token inválido"}

def fazer_login(username: str, senha: str, ip: str) -> tuple[bool, dict]:
    """
    Processo completo de login
    Retorna: (sucesso, {token, user_data} ou {erro})
    """
    if _verificar_bloqueio(ip):
        return False, {"erro": "IP temporariamente bloqueado por excesso de tentativas"}

    sucesso, dados = autenticar_usuario(username, senha)

    if not sucesso:
        _registrar_tentativa_falha(ip)
        return False, dados

    _limpar_tentativas(ip)

    # Salva chave na sessão (derivada da senha, não a senha)
    from modulos.database import obter_chave_usuario
    chave = obter_chave_usuario(dados['user_id'], senha)

    # Armazena chave criptografada na sessão server-side
    chave_sessao = secrets.token_hex(16)
    cache.set(
        f"chave_sessao_{chave_sessao}",
        {"user_id": dados['user_id'], "chave": list(chave)},
        ttl=JWT_EXPIRACAO_HORAS * 3600
    )

    token = gerar_token_jwt(dados['user_id'], dados['username'], dados['is_admin'])

    return True, {
        "token": token,
        "username": dados['username'],
        "is_admin": dados['is_admin'],
        "chave_sessao": chave_sessao,
        "deve_trocar_senha": dados.get('deve_trocar_senha', False)
    }

def obter_chave_da_sessao(chave_sessao: str, user_id: str) -> bytes:
    """Recupera chave de criptografia da sessão"""
    dados = cache.get(f"chave_sessao_{chave_sessao}")
    if not dados or dados.get('user_id') != user_id:
        raise ValueError("Sessão inválida ou expirada")
    return bytes(dados['chave'])

def requer_auth(f):
    """Decorator para rotas que precisam de autenticação"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Token no header Authorization
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

        # Token no cookie
        if not token:
            token = request.cookies.get('auth_token')

        if not token:
            return jsonify({"erro": "Autenticação necessária"}), 401

        payload = verificar_token_jwt(token)
        if "erro" in payload:
            return jsonify(payload), 401

        request.user_id = payload['user_id']
        request.username = payload['username']
        request.is_admin = payload['is_admin']

        return f(*args, **kwargs)

    return decorated

def requer_admin(f):
    """Decorator para rotas de administrador"""
    @wraps(f)
    @requer_auth
    def decorated(*args, **kwargs):
        if not request.is_admin:
            return jsonify({"erro": "Acesso negado - Apenas administradores"}), 403
        return f(*args, **kwargs)
    return decorated

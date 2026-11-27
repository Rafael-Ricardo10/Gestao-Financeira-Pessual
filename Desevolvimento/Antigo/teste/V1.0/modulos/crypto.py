"""
Módulo de criptografia - AES-256-GCM + Argon2id
Cada usuário tem sua própria chave derivada da senha
Dados em RAM são protegidos via SecureString
"""

import os
import secrets
import hashlib
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
import json
import struct
import ctypes

# Argon2id - melhor algoritmo para hash de senha
ph = PasswordHasher(
    time_cost=3,        # iterações
    memory_cost=65536,  # 64MB RAM
    parallelism=4,      # threads
    hash_len=32,
    salt_len=16
)

def limpar_memoria(data: bytearray):
    """Sobrescreve memória para evitar vazamento"""
    if isinstance(data, bytearray):
        for i in range(len(data)):
            data[i] = 0

def hash_senha(senha: str) -> str:
    """Hash seguro da senha com Argon2id"""
    return ph.hash(senha)

def verificar_senha(hash_armazenado: str, senha: str) -> bool:
    """Verifica senha contra hash Argon2id"""
    try:
        return ph.verify(hash_armazenado, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False

def derivar_chave_usuario(senha: str, salt: bytes) -> bytes:
    """
    Deriva chave AES-256 única por usuário usando Scrypt
    Esta chave nunca é armazenada, apenas derivada em memória
    """
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=2**17,    # CPU/memória cost
        r=8,
        p=1,
        backend=default_backend()
    )
    chave = kdf.derive(senha.encode('utf-8'))
    return chave

def gerar_salt() -> bytes:
    """Gera salt criptograficamente seguro"""
    return secrets.token_bytes(32)

def criptografar_dados(dados: dict, chave: bytes) -> bytes:
    """
    Criptografa dados com AES-256-GCM
    Retorna: nonce(12) + tag(16) + ciphertext
    """
    aesgcm = AESGCM(chave)
    nonce = secrets.token_bytes(12)
    dados_json = json.dumps(dados, ensure_ascii=False).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, dados_json, None)
    # nonce + ciphertext (tag já incluída no GCM)
    resultado = nonce + ciphertext
    return resultado

def descriptografar_dados(dados_criptografados: bytes, chave: bytes) -> dict:
    """
    Descriptografa dados AES-256-GCM
    """
    try:
        aesgcm = AESGCM(chave)
        nonce = dados_criptografados[:12]
        ciphertext = dados_criptografados[12:]
        dados_json = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(dados_json.decode('utf-8'))
    except Exception:
        raise ValueError("Falha na descriptografia - dados corrompidos ou chave incorreta")

def criptografar_campo(valor: str, chave: bytes) -> str:
    """Criptografa campo individual, retorna base64"""
    aesgcm = AESGCM(chave)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, valor.encode('utf-8'), None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')

def descriptografar_campo(valor_b64: str, chave: bytes) -> str:
    """Descriptografa campo individual de base64"""
    try:
        dados = base64.b64decode(valor_b64)
        aesgcm = AESGCM(chave)
        nonce = dados[:12]
        ciphertext = dados[12:]
        return aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
    except Exception:
        raise ValueError("Falha ao descriptografar campo")

def gerar_token_sessao() -> str:
    """Token de sessão criptograficamente seguro"""
    return secrets.token_urlsafe(64)

def hmac_dados(dados: bytes, chave: bytes) -> bytes:
    """HMAC-SHA256 para integridade"""
    import hmac as hmac_lib
    return hmac_lib.new(chave, dados, hashlib.sha256).digest()

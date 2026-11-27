"""
Sistema de cache em memória com TTL
Suporta Redis quando disponível, fallback para dict em memória
"""

import time
import threading
import json
import hashlib
from typing import Any, Optional

try:
    import redis
    REDIS_DISPONIVEL = True
except ImportError:
    REDIS_DISPONIVEL = False

_cache_memoria = {}
_cache_lock = threading.Lock()

class GerenciadorCache:
    def __init__(self):
        self.redis_client = None
        self.usar_redis = False
        self._tentar_redis()

    def _tentar_redis(self):
        """Tenta conectar ao Redis"""
        if REDIS_DISPONIVEL:
            try:
                client = redis.Redis(host='localhost', port=6379, db=0)
                client.ping()
                self.redis_client = client
                self.usar_redis = True
                print("[CACHE] Redis conectado com sucesso")
            except Exception:
                print("[CACHE] Redis não disponível, usando cache em memória")

    def _chave_segura(self, chave: str) -> str:
        """Hash da chave para segurança"""
        return hashlib.sha256(chave.encode()).hexdigest()[:32]

    def set(self, chave: str, valor: Any, ttl: int = 300):
        """Define valor no cache com TTL em segundos"""
        chave_h = self._chave_segura(chave)

        if self.usar_redis and self.redis_client:
            try:
                self.redis_client.setex(
                    chave_h,
                    ttl,
                    json.dumps(valor, default=str)
                )
                return
            except Exception:
                pass

        # Fallback memória
        with _cache_lock:
            _cache_memoria[chave_h] = {
                "valor": valor,
                "expira": time.time() + ttl
            }

    def get(self, chave: str) -> Optional[Any]:
        """Obtém valor do cache"""
        chave_h = self._chave_segura(chave)

        if self.usar_redis and self.redis_client:
            try:
                val = self.redis_client.get(chave_h)
                if val:
                    return json.loads(val)
                return None
            except Exception:
                pass

        # Fallback memória
        with _cache_lock:
            entrada = _cache_memoria.get(chave_h)
            if not entrada:
                return None
            if time.time() > entrada['expira']:
                del _cache_memoria[chave_h]
                return None
            return entrada['valor']

    def delete(self, chave: str):
        """Remove entrada do cache"""
        chave_h = self._chave_segura(chave)

        if self.usar_redis and self.redis_client:
            try:
                self.redis_client.delete(chave_h)
            except Exception:
                pass

        with _cache_lock:
            _cache_memoria.pop(chave_h, None)

    def invalidar_usuario(self, user_id: str):
        """Invalida todo cache de um usuário"""
        prefixo = f"user_{user_id}"
        self.delete(prefixo + "_dados")
        self.delete(prefixo + "_transacoes")
        self.delete(prefixo + "_categorias")
        self.delete(prefixo + "_saldo")

    def limpar_expirados(self):
        """Limpa entradas expiradas da memória"""
        with _cache_lock:
            agora = time.time()
            expirados = [
                k for k, v in _cache_memoria.items()
                if agora > v['expira']
            ]
            for k in expirados:
                del _cache_memoria[k]

# Instância global
cache = GerenciadorCache()

def iniciar_limpeza_periodica():
    """Inicia thread de limpeza de cache"""
    def _limpar():
        while True:
            time.sleep(60)
            cache.limpar_expirados()

    t = threading.Thread(target=_limpar, daemon=True)
    t.start()

"""
Cache com Redis configurável por variável de ambiente
REDIS_HOST=172.17.0.1  → Host Docker bridge (padrão)
REDIS_HOST=redis       → Nome do container Docker
REDIS_HOST=localhost   → Redis local fora do Docker
"""

import os
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

REDIS_HOST     = os.environ.get('REDIS_HOST', '172.17.0.1')
REDIS_PORT     = int(os.environ.get('REDIS_PORT', 6379))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)
REDIS_DB       = int(os.environ.get('REDIS_DB', 0))

class GerenciadorCache:
    def __init__(self):
        self.redis_client = None
        self.usar_redis = False
        self._tentar_redis()

    def _tentar_redis(self):
        if not REDIS_DISPONIVEL:
            print("[CACHE] redis-py não instalado. Usando memória.")
            return
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                socket_connect_timeout=3,
                socket_timeout=3,
                decode_responses=False,
                retry_on_timeout=True
            )
            client.ping()
            self.redis_client = client
            self.usar_redis = True
            print(f"[CACHE] Redis conectado: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            print(f"[CACHE] Redis indisponivel ({REDIS_HOST}:{REDIS_PORT})")
            print(f"[CACHE] Fallback: cache em memoria")

    def _chave_segura(self, chave: str) -> str:
        return hashlib.sha256(chave.encode()).hexdigest()[:32]

    def set(self, chave: str, valor: Any, ttl: int = 300):
        chave_h = self._chave_segura(chave)
        if self.usar_redis and self.redis_client:
            try:
                self.redis_client.setex(
                    chave_h, ttl,
                    json.dumps(valor, default=str)
                )
                return
            except Exception:
                self.usar_redis = False

        with _cache_lock:
            _cache_memoria[chave_h] = {
                "valor": valor,
                "expira": time.time() + ttl
            }

    def get(self, chave: str) -> Optional[Any]:
        chave_h = self._chave_segura(chave)
        if self.usar_redis and self.redis_client:
            try:
                val = self.redis_client.get(chave_h)
                if val:
                    return json.loads(val)
                return None
            except Exception:
                self.usar_redis = False

        with _cache_lock:
            entrada = _cache_memoria.get(chave_h)
            if not entrada:
                return None
            if time.time() > entrada['expira']:
                del _cache_memoria[chave_h]
                return None
            return entrada['valor']

    def delete(self, chave: str):
        chave_h = self._chave_segura(chave)
        if self.usar_redis and self.redis_client:
            try:
                self.redis_client.delete(chave_h)
            except Exception:
                pass
        with _cache_lock:
            _cache_memoria.pop(chave_h, None)

    def invalidar_usuario(self, user_id: str):
        prefixos = [
            f"user_{user_id}_dados",
            f"user_{user_id}_transacoes",
            f"user_{user_id}_categorias",
            f"user_{user_id}_saldo",
            f"ctx_financeiro_{user_id}",
            f"analise_completa_{user_id}",
            f"anomalias_{user_id}",
        ]
        for p in prefixos:
            self.delete(p)

    def limpar_expirados(self):
        with _cache_lock:
            agora = time.time()
            expirados = [
                k for k, v in _cache_memoria.items()
                if agora > v['expira']
            ]
            for k in expirados:
                del _cache_memoria[k]

    def reconectar_redis(self):
        """Tenta reconectar ao Redis após falha"""
        self.usar_redis = False
        self._tentar_redis()

cache = GerenciadorCache()

def iniciar_limpeza_periodica():
    def _limpar():
        while True:
            time.sleep(60)
            cache.limpar_expirados()
            # Tenta reconectar ao Redis se estava fora
            if not cache.usar_redis and REDIS_DISPONIVEL:
                cache.reconectar_redis()

    t = threading.Thread(target=_limpar, daemon=True)
    t.start()

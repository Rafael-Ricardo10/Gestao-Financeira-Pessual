"""
Cache local criptografado com SQLite + AES-256
SEM expiração por tempo
Dados persistem até serem explicitamente atualizados
"""

import os
import json
import time
import sqlite3
import hashlib
import secrets
import threading
from pathlib import Path
from typing import Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _dir_dados() -> Path:
    import platform
    s = platform.system().lower()
    if s == 'windows':
        base = Path(os.environ.get('APPDATA', Path.home()))
    elif s == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    elif 'android' in s or os.path.exists('/data/data'):
        base = Path('/data/data/com.rrfs.financeiro/files')
    else:
        base = Path.home() / '.local' / 'share'
    p = base / 'RRFSFinanceiro'
    p.mkdir(parents=True, exist_ok=True)
    return p


class CacheLocal:
    """
    Cache SQLite AES-256 SEM expiração por tempo.
    Dados ficam até serem explicitamente substituídos.
    Sistema funciona offline indefinidamente.
    """

    # Valor especial para TTL infinito
    TTL_INFINITO = 999999999999.0

    def __init__(self):
        self._chave        : Optional[bytes] = None
        self._conn         : Optional[sqlite3.Connection] = None
        self._lock         = threading.Lock()
        self._db_path      = _dir_dados() / 'cache.db'
        self._inicializado = False

    def inicializar(self, senha_usuario: str, user_id: str):
        """Inicializa cache com chave derivada da senha"""
        salt = hashlib.sha256(
            (user_id + "cache_local_rrfs_v2").encode()
        ).digest()

        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        from cryptography.hazmat.backends import default_backend

        kdf = Scrypt(
            salt=salt, length=32,
            n=2**14, r=8, p=1,
            backend=default_backend()
        )
        self._chave = kdf.derive(senha_usuario.encode())
        self._conectar()
        self._criar_tabelas()
        self._inicializado = True
        print("[CACHE] Inicializado - modo sem expiração")

    def _conectar(self):
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def _criar_tabelas(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache (
                chave        TEXT PRIMARY KEY,
                valor_enc    BLOB NOT NULL,
                atualizado_em REAL NOT NULL,
                versao       INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sessao (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fila_sync (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                operacao    TEXT NOT NULL,
                endpoint    TEXT NOT NULL,
                dados       TEXT,
                criado_em   REAL NOT NULL,
                tentativas  INTEGER DEFAULT 0,
                enviado     INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS versoes (
                chave       TEXT PRIMARY KEY,
                versao      INTEGER DEFAULT 0,
                hash_dados  TEXT,
                atualizado_em REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_fila_enviado
                ON fila_sync(enviado);
        """)
        self._conn.commit()

    # ==================== CRIPTOGRAFIA ====================

    def _criptografar(self, dados: Any) -> bytes:
        aesgcm  = AESGCM(self._chave)
        nonce   = secrets.token_bytes(12)
        texto   = json.dumps(dados, default=str, ensure_ascii=False).encode()
        cifrado = aesgcm.encrypt(nonce, texto, None)
        return nonce + cifrado

    def _descriptografar(self, blob: bytes) -> Any:
        aesgcm  = AESGCM(self._chave)
        nonce   = blob[:12]
        cifrado = blob[12:]
        texto   = aesgcm.decrypt(nonce, cifrado, None)
        return json.loads(texto.decode())

    # ==================== CACHE SEM EXPIRAÇÃO ====================

    def set(self, chave: str, valor: Any, ttl: int = None):
        """
        Salva valor no cache.
        ttl ignorado - dados não expiram por tempo.
        Só são atualizados quando explicitamente substituídos.
        """
        if not self._inicializado or not self._chave:
            return

        with self._lock:
            try:
                blob   = self._criptografar(valor)
                agora  = time.time()

                # Calcula hash para detectar mudanças
                hash_v = hashlib.md5(
                    json.dumps(valor, default=str, sort_keys=True).encode()
                ).hexdigest()

                # Obtém versão atual
                cur = self._conn.execute(
                    "SELECT versao FROM versoes WHERE chave=?", (chave,)
                )
                row    = cur.fetchone()
                versao = (row[0] + 1) if row else 1

                self._conn.execute("""
                    INSERT OR REPLACE INTO cache
                    (chave, valor_enc, atualizado_em, versao)
                    VALUES (?, ?, ?, ?)
                """, (chave, blob, agora, versao))

                self._conn.execute("""
                    INSERT OR REPLACE INTO versoes
                    (chave, versao, hash_dados, atualizado_em)
                    VALUES (?, ?, ?, ?)
                """, (chave, versao, hash_v, agora))

                self._conn.commit()
            except Exception as e:
                print(f"[CACHE] Erro set '{chave}': {e}")

    def get(self, chave: str) -> Optional[Any]:
        """
        Busca valor do cache.
        Retorna None apenas se a chave não existir nunca.
        Não expira por tempo.
        """
        if not self._inicializado or not self._chave:
            return None

        with self._lock:
            try:
                cur = self._conn.execute(
                    "SELECT valor_enc FROM cache WHERE chave=?",
                    (chave,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                return self._descriptografar(row[0])
            except Exception as e:
                print(f"[CACHE] Erro get '{chave}': {e}")
                return None

    def existe(self, chave: str) -> bool:
        """Verifica se chave existe no cache"""
        if not self._inicializado:
            return False
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM cache WHERE chave=?", (chave,)
            )
            return cur.fetchone() is not None

    def get_versao(self, chave: str) -> int:
        """Retorna versão atual dos dados"""
        if not self._inicializado:
            return 0
        with self._lock:
            cur = self._conn.execute(
                "SELECT versao FROM versoes WHERE chave=?", (chave,)
            )
            row = cur.fetchone()
            return row[0] if row else 0

    def get_hash(self, chave: str) -> Optional[str]:
        """Retorna hash dos dados para comparação"""
        if not self._inicializado:
            return None
        with self._lock:
            cur = self._conn.execute(
                "SELECT hash_dados FROM versoes WHERE chave=?", (chave,)
            )
            row = cur.fetchone()
            return row[0] if row else None

    def get_ultima_atualizacao(self, chave: str) -> float:
        """Retorna timestamp da última atualização"""
        if not self._inicializado:
            return 0.0
        with self._lock:
            cur = self._conn.execute(
                "SELECT atualizado_em FROM cache WHERE chave=?", (chave,)
            )
            row = cur.fetchone()
            return row[0] if row else 0.0

    def delete(self, chave: str):
        """Remove entrada do cache"""
        if not self._inicializado:
            return
        with self._lock:
            try:
                self._conn.execute(
                    "DELETE FROM cache WHERE chave=?", (chave,)
                )
                self._conn.execute(
                    "DELETE FROM versoes WHERE chave=?", (chave,)
                )
                self._conn.commit()
            except Exception:
                pass

    def invalidar_tudo(self):
        """
        Marca todos os dados como desatualizados.
        Não apaga - apenas força busca no servidor na próxima vez.
        """
        if not self._inicializado:
            return
        with self._lock:
            try:
                # Zera versões para forçar sync
                self._conn.execute(
                    "UPDATE versoes SET versao=0"
                )
                self._conn.commit()
                print("[CACHE] Todos os dados marcados para re-sync")
            except Exception:
                pass

    def limpar_tudo(self):
        """Limpa todo o cache (logout)"""
        if not self._inicializado:
            return
        with self._lock:
            try:
                self._conn.execute("DELETE FROM cache")
                self._conn.execute("DELETE FROM versoes")
                self._conn.commit()
            except Exception:
                pass

    # ==================== SESSÃO PERSISTENTE ====================

    def salvar_sessao(self, dados: dict):
        """Salva sessão criptografada - persiste entre execuções"""
        if not self._inicializado or not self._chave:
            return
        with self._lock:
            try:
                import base64
                blob = self._criptografar(dados)
                val  = base64.b64encode(blob).decode()
                self._conn.execute("""
                    INSERT OR REPLACE INTO sessao (chave, valor)
                    VALUES ('sessao_ativa', ?)
                """, (val,))
                self._conn.commit()
            except Exception as e:
                print(f"[CACHE] Erro salvar sessao: {e}")

    def carregar_sessao(self) -> Optional[dict]:
        if not self._inicializado or not self._chave:
            return None
        with self._lock:
            try:
                import base64
                cur = self._conn.execute(
                    "SELECT valor FROM sessao WHERE chave='sessao_ativa'"
                )
                row = cur.fetchone()
                if not row:
                    return None
                blob = base64.b64decode(row[0])
                return self._descriptografar(blob)
            except Exception:
                return None

    def apagar_sessao(self):
        if not self._inicializado:
            return
        with self._lock:
            try:
                self._conn.execute(
                    "DELETE FROM sessao WHERE chave='sessao_ativa'"
                )
                self._conn.commit()
            except Exception:
                pass

    # ==================== FILA DE SYNC ====================

    def enfileirar_sync(
        self,
        operacao: str,
        endpoint: str,
        dados: dict = None
    ):
        """Enfileira operação para sync quando online"""
        if not self._inicializado:
            return
        with self._lock:
            try:
                self._conn.execute("""
                    INSERT INTO fila_sync
                    (operacao, endpoint, dados, criado_em)
                    VALUES (?, ?, ?, ?)
                """, (
                    operacao, endpoint,
                    json.dumps(dados) if dados else None,
                    time.time()
                ))
                self._conn.commit()
            except Exception as e:
                print(f"[CACHE] Erro enfileirar: {e}")

    def obter_fila_sync(self) -> list:
        """Retorna operações pendentes"""
        if not self._inicializado:
            return []
        with self._lock:
            try:
                cur = self._conn.execute("""
                    SELECT id, operacao, endpoint, dados, tentativas
                    FROM fila_sync
                    WHERE enviado = 0
                    ORDER BY criado_em ASC
                    LIMIT 100
                """)
                return [
                    {
                        'id'        : r[0],
                        'operacao'  : r[1],
                        'endpoint'  : r[2],
                        'dados'     : json.loads(r[3]) if r[3] else None,
                        'tentativas': r[4]
                    }
                    for r in cur.fetchall()
                ]
            except Exception:
                return []

    def marcar_sync_enviado(self, item_id: int):
        """Marca item como enviado com sucesso"""
        if not self._inicializado:
            return
        with self._lock:
            try:
                self._conn.execute(
                    "UPDATE fila_sync SET enviado=1 WHERE id=?",
                    (item_id,)
                )
                self._conn.commit()
            except Exception:
                pass

    def limpar_fila_enviados(self):
        """Remove itens já enviados"""
        if not self._inicializado:
            return
        with self._lock:
            try:
                self._conn.execute(
                    "DELETE FROM fila_sync WHERE enviado=1"
                )
                self._conn.commit()
            except Exception:
                pass

    def tem_pendencias(self) -> bool:
        """Verifica se há operações pendentes de sync"""
        if not self._inicializado:
            return False
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM fila_sync WHERE enviado=0"
            )
            return cur.fetchone()[0] > 0

    def fechar(self):
        """Fecha e limpa chave da memória"""
        if self._conn:
            self._conn.close()
            self._conn = None
        if self._chave:
            self._chave = bytearray(len(self._chave))
            self._chave = None
        self._inicializado = False


# Instância global
cache_local = CacheLocal()

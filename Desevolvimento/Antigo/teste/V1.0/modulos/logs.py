"""
Sistema de logs - apenas erros, com timestamp
"""

import os
import json
from datetime import datetime
from pathlib import Path
import threading

LOG_DIR = Path("dados/logs")
LOG_FILE = LOG_DIR / "erros.json"
_lock = threading.Lock()

def inicializar_logs():
    """Cria estrutura de logs"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, 'w') as f:
            json.dump([], f)

def registrar_log(modulo: str, erro: str, detalhes: str = ""):
    """
    Registra erro no log
    Formato: ID, módulo, erro, data/hora
    """
    inicializar_logs()

    with _lock:
        try:
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)
        except Exception:
            logs = []

        import secrets
        log_entry = {
            "id": secrets.token_hex(8),
            "modulo": modulo,
            "erro": erro,
            "detalhes": detalhes,
            "data": datetime.now().isoformat(),
            "resolvido": False
        }

        logs.append(log_entry)

        with open(LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

def obter_logs() -> list:
    """Retorna todos os logs"""
    inicializar_logs()
    try:
        with open(LOG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def marcar_resolvido(log_id: str) -> bool:
    """Marca log como resolvido e remove"""
    with _lock:
        try:
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)

            logs = [l for l in logs if l.get('id') != log_id]

            with open(LOG_FILE, 'w') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

def limpar_logs_antigos(dias: int = 90):
    """Remove logs muito antigos"""
    with _lock:
        try:
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)

            cutoff = datetime.now().timestamp() - (dias * 86400)
            logs = [
                l for l in logs
                if datetime.fromisoformat(l['data']).timestamp() > cutoff
            ]

            with open(LOG_FILE, 'w') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

"""
Sistema de logs com sanitização de dados sensíveis
"""

import re
import json
import secrets
import os
from datetime import datetime
from pathlib import Path
import threading

LOG_DIR  = Path("dados/logs")
LOG_FILE = LOG_DIR / "erros.json"
_lock    = threading.Lock()
MAX_LOGS = 1000

_PADROES_SENSIVEIS = [
    (re.compile(r'\b\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[\-\s]?\d{2}\b'), '[CPF]'),
    (re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'), '[CARTAO]'),
    (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), '[EMAIL]'),
    (re.compile(r'senha["\s:=]+\S+', re.IGNORECASE), 'senha=[REDACTED]'),
    (re.compile(r'password["\s:=]+\S+', re.IGNORECASE), 'password=[REDACTED]'),
    (re.compile(r'chave["\s:=]+[A-Fa-f0-9]{16,}', re.IGNORECASE), 'chave=[REDACTED]'),
    (re.compile(r'token["\s:=]+[A-Za-z0-9\-_\.]{20,}', re.IGNORECASE), 'token=[REDACTED]'),
    (re.compile(r'[A-Fa-f0-9]{64,}'), '[HASH]'),
]

def _sanitizar(msg: str) -> str:
    result = str(msg)[:500]
    for padrao, sub in _PADROES_SENSIVEIS:
        result = padrao.sub(sub, result)
    return result

def inicializar_logs():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, 'w') as f:
            json.dump([], f)

def registrar_log(modulo: str, erro: str, detalhes: str = ""):
    inicializar_logs()
    with _lock:
        try:
            with open(LOG_FILE, 'r') as f:
                logs = json.load(f)
        except Exception:
            logs = []

        logs.append({
            "id"       : secrets.token_hex(8),
            "modulo"   : modulo,
            "erro"     : _sanitizar(erro),
            "detalhes" : _sanitizar(detalhes),
            "data"     : datetime.now().isoformat(),
            "resolvido": False
        })

        if len(logs) > MAX_LOGS:
            logs = logs[-MAX_LOGS:]

        with open(LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

def obter_logs() -> list:
    inicializar_logs()
    try:
        with open(LOG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def marcar_resolvido(log_id: str) -> bool:
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

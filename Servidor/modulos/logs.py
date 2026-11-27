"""
Sistema simples de logs
"""
import os
from datetime import datetime
from pathlib import Path

PASTA_LOGS = Path("logs")
PASTA_LOGS.mkdir(exist_ok=True)

def registrar_log(modulo: str, mensagem: str, nivel: str = "INFO"):
    """
    Registra uma mensagem no arquivo de log

    Args:
        modulo: Nome do módulo
        mensagem: Mensagem a ser registrada
        nivel: Nível do log (INFO, WARNING, ERROR)
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = PASTA_LOGS / f"{modulo}_{datetime.now().strftime('%Y%m%d')}.log"

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{nivel}] {mensagem}\n")
    except Exception as e:
        print(f"Erro ao registrar log: {e}")

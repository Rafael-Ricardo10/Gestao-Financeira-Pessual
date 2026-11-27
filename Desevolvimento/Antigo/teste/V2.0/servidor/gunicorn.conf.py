"""
Configuração Gunicorn - Produção
Iniciar com: gunicorn -c gunicorn.conf.py app:app
"""

import os
import multiprocessing
from pathlib import Path

# ── Garante que o SSL existe antes do gunicorn subir ──────────────
def on_starting(server):
    """Hook executado antes do gunicorn iniciar os workers"""
    print("=" * 60)
    print("  💰 FinanceIA - Iniciando com Gunicorn")
    print("=" * 60)

    # Garante as pastas necessárias
    Path("dados/ssl").mkdir(parents=True, exist_ok=True)
    Path("dados/logs").mkdir(parents=True, exist_ok=True)

    # Gera o certificado SSL se não existir
    cert = Path("dados/ssl/cert.pem")
    key  = Path("dados/ssl/key.pem")

    if not cert.exists() or not key.exists():
        print("[→] Gerando certificado SSL...")
        try:
            from modulos.ssl_config import gerar_certificado_ssl
            gerar_certificado_ssl()
            print("[✔] Certificado SSL gerado.")
        except Exception as e:
            print(f"[!] Erro ao gerar SSL: {e}")
    else:
        print("[✔] Certificado SSL encontrado.")


def post_fork(server, worker):
    """Executado após cada worker ser criado"""
    server.log.info(f"Worker iniciado: PID {worker.pid}")


def worker_exit(server, worker):
    """Executado quando um worker encerra"""
    server.log.info(f"Worker encerrado: PID {worker.pid}")


# ── Workers ───────────────────────────────────────────────────────
# Fórmula padrão: (cpu * 2) + 1
# Para sistema financeiro pessoal não precisa de muitos workers
cpu_count        = multiprocessing.cpu_count()
workers          = int(os.environ.get('GUNICORN_WORKERS', min((cpu_count * 2) + 1, 4)))
worker_class     = 'gthread'      # threads por worker
threads          = int(os.environ.get('GUNICORN_THREADS', 4))
worker_connections = 1000

# ── Rede ──────────────────────────────────────────────────────────
bind             = os.environ.get('BIND', '0.0.0.0:6300')

# ── SSL ───────────────────────────────────────────────────────────
_cert = Path("dados/ssl/cert.pem")
_key  = Path("dados/ssl/key.pem")

if _cert.exists() and _key.exists():
    certfile = str(_cert)
    keyfile  = str(_key)
    print("[✔] Gunicorn usará HTTPS")
else:
    # Sem SSL - gunicorn sobe em HTTP
    # (o on_starting vai tentar gerar, mas se falhar cai aqui)
    certfile = None
    keyfile  = None

# ── Timeouts ──────────────────────────────────────────────────────
timeout          = 120       # worker morto se não responder em 120s
keepalive        = 5         # conexões keep-alive
graceful_timeout = 30        # tempo para worker terminar graciosamente

# ── Limites e Estabilidade ────────────────────────────────────────
max_requests          = 1000   # reinicia worker após N requests (evita memory leak)
max_requests_jitter   = 100    # aleatoriedade para evitar todos reiniciarem juntos
limit_request_line    = 4096
limit_request_fields  = 50

# ── Logs ──────────────────────────────────────────────────────────
accesslog  = 'dados/logs/access.log'
errorlog   = 'dados/logs/gunicorn.log'
loglevel   = 'warning'         # debug | info | warning | error | critical

# ── Processo ──────────────────────────────────────────────────────
proc_name  = 'gasto-pessuais'
daemon     = False             # False pois o systemd já gerencia

# ── Segurança ─────────────────────────────────────────────────────
# Não define user/group aqui - o systemd já executa como casaos
forwarded_allow_ips = '127.0.0.1'

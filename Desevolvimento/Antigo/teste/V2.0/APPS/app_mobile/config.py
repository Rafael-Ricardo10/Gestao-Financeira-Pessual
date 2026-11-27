"""
================================================
RRFS Gestão Financeira - Configurações
================================================
EDITE AQUI antes de compilar o app
================================================
"""

# ================================================
# SERVIDOR - Conexão Direta
# ================================================
SERVIDOR_DIRETO = "https://192.168.1.100:6300"

# ================================================
# SERVIDOR - Via Tor (.onion)
# ================================================
SERVIDOR_ONION = "https://seulink12345abcde.onion:6300"

# ================================================
# PRIORIDADE: 1 = direto primeiro / 2 = tor primeiro
# ================================================
PRIORIDADE_CONEXAO = 1

# ================================================
# TIMEOUT de conexão (segundos)
# ================================================
TIMEOUT_DIRETO = 5
TIMEOUT_TOR    = 30

# ================================================
# CACHE LOCAL - SEM EXPIRAÇÃO POR TEMPO
# Cache só é invalidado quando dados mudam
# TTL = 0 significa sem expiração
# ================================================
CACHE_SEM_EXPIRACAO = True   # Cache permanente

# ================================================
# SINCRONIZAÇÃO
# Intervalo para verificar se servidor tem dados
# mais novos que o cache local (segundos)
# ================================================
SYNC_INTERVALO        = 30   # Verifica a cada 30s se há mudanças
SYNC_POLLING_ONLINE   = 30   # Intervalo quando online
SYNC_POLLING_OFFLINE  = 10   # Intervalo para tentar reconectar

# ================================================
# SEGURANÇA
# ================================================
VERIFICAR_SSL = False

# ================================================
# APP
# ================================================
APP_NOME   = "RRFS Gestão Financeira"
APP_VERSAO = "2.0"
APP_ICONE  = "$"

# ================================================
# TOR
# ================================================
TOR_PORTA_SOCKS  = 9150
TOR_PORTA_CTRL   = 9151
TOR_TIMEOUT_INIT = 60

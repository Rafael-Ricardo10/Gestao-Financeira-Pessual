"""
================================================
RRFS Gestão Financeira - Configurações
================================================
EDITE AQUI antes de compilar o app
================================================
"""

# ================================================
# SERVIDOR - Conexão Direta
# Use IP local quando estiver na mesma rede
# Use domínio quando tiver DNS configurado
# ================================================
SERVIDOR_DIRETO = "https://192.168.1.100:6300"

# ================================================
# SERVIDOR - Via Tor (.onion)
# Usado quando fora da rede local
# ou quando conexão direta falhar
# ================================================
SERVIDOR_ONION = "https://seulink12345abcde.onion:6300"

# ================================================
# PRIORIDADE DE CONEXÃO
# 1 = testa direto primeiro (recomendado)
# 2 = testa onion primeiro
# ================================================
PRIORIDADE_CONEXAO = 1

# ================================================
# TIMEOUT de conexão (segundos)
# ================================================
TIMEOUT_DIRETO = 5    # Rápido para rede local
TIMEOUT_TOR    = 30   # Tor é mais lento

# ================================================
# CACHE LOCAL
# Tempo em segundos para expirar cache local
# ================================================
CACHE_TTL_TRANSACOES  = 300   # 5 minutos
CACHE_TTL_CATEGORIAS  = 600   # 10 minutos
CACHE_TTL_SALDO       = 120   # 2 minutos
CACHE_TTL_PROJECOES   = 1800  # 30 minutos

# ================================================
# SINCRONIZAÇÃO automática (segundos)
# 0 = desabilitado
# ================================================
SYNC_INTERVALO = 60  # Sincroniza a cada 1 minuto

# ================================================
# SEGURANÇA
# ================================================
VERIFICAR_SSL = False  # False para certificado auto-assinado
                       # True para certificado válido (produção)

# ================================================
# APP
# ================================================
APP_NOME    = "RRFS Gestão Financeira"
APP_VERSAO  = "2.0"
APP_ICONE   = "$"  # Ícone na bandeja do sistema

# ================================================
# TOR - Configurações internas
# NÃO altere a menos que saiba o que está fazendo
# ================================================
TOR_PORTA_SOCKS = 9150   # Porta SOCKS do Tor local
TOR_PORTA_CTRL  = 9151   # Porta de controle do Tor
TOR_TIMEOUT_INIT = 60    # Segundos para Tor iniciar

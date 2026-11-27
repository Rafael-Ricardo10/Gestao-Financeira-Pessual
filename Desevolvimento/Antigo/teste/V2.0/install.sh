#!/bin/bash

# ==============================================================================
#  INSTALADOR - Sistema de Gestão Financeira Pessoal
#  Arquivo: install.sh
#  Produção: Gunicorn + systemd
#  UID:GID: 1000:1000 (padrão seguro - não executa como root)
# ==============================================================================

# ── Cores ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

# ── Configurações Globais ──────────────────────────────────────────────────────
APP_NAME="Gasto Pessuais"
SERVICE_NAME="gasto-pessuais"
INSTALL_DIR="/DATA/AppData/Gasto_Pessuais"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Configuração do usuário de execução ───────────────────────────────────────
# UID:GID 1000:1000 - Padrão de segurança (não-root)
# Funciona com UID numérico mesmo sem usuário no /etc/passwd
APP_UID=1000
APP_GID=1000
APP_USER="casaos"
APP_GROUP="casaos"
APP_PASSWORD="casaos123"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SOURCE="${SCRIPT_DIR}/servidor"

# ── Detecta OS ─────────────────────────────────────────────────────────────────
IS_DEBIAN=false
if [[ -f /etc/debian_version ]] || \
   grep -qi "debian\|ubuntu\|raspbian" /etc/os-release 2>/dev/null; then
    IS_DEBIAN=true
fi

# ── Funções de Log Visual ──────────────────────────────────────────────────────
print_header() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         SISTEMA DE GESTÃO FINANCEIRA PESSOAL                ║"
    echo "║         Instalador v2.1 — Gunicorn + UID 1000               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}┌─────────────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│${WHITE} ➤  $1${NC}"
    echo -e "${BLUE}└─────────────────────────────────────────────┘${NC}"
}

print_ok()    { echo -e "  ${GREEN}✔${NC}  $1"; }
print_warn()  { echo -e "  ${YELLOW}⚠${NC}  $1"; }
print_error() { echo -e "  ${RED}✘${NC}  $1"; }
print_info()  { echo -e "  ${CYAN}ℹ${NC}  $1"; }

# ── Verificação de Root ────────────────────────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "\n${RED}✘ Execute como root: sudo bash install.sh${NC}\n"
        exit 1
    fi
}

# ── Verificações de Estado ─────────────────────────────────────────────────────
check_existing_installation() {
    [[ -d "${INSTALL_DIR}" ]] && return 0
    return 1
}

check_venv() {
    [[ -d "${INSTALL_DIR}/env" ]]               && \
    [[ -f "${INSTALL_DIR}/env/bin/python3" ]]   && \
    [[ -f "${INSTALL_DIR}/env/bin/pip" ]]       && \
    [[ -f "${INSTALL_DIR}/env/bin/gunicorn" ]]  && \
    return 0
    return 1
}

check_libraries() {
    print_info "Verificando bibliotecas..."
    local pip_bin="${INSTALL_DIR}/env/bin/pip"
    local req_file="${INSTALL_DIR}/requirements.txt"

    [[ ! -f "${req_file}" ]] && {
        print_warn "requirements.txt não encontrado."
        return 1
    }

    local missing=0
    while IFS= read -r line; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        local pkg_name
        pkg_name=$(echo "$line" | sed 's/[>=<!].*//' \
                   | tr '[:upper:]' '[:lower:]' | xargs)
        if ! "${pip_bin}" show "${pkg_name}" &>/dev/null; then
            print_warn "Ausente: ${pkg_name}"
            missing=1
        fi
    done < "${req_file}"

    [[ $missing -eq 0 ]] && { print_ok "Todas as bibliotecas OK."; return 0; }
    return 1
}

# ── Gerenciar Usuário (UID:GID 1000:1000) ─────────────────────────────────────
manage_user() {
    print_step "Configurando usuário de serviço (UID:GID 1000:1000)"

    # ── Verifica se UID 1000 está ocupado ──────────────────────
    if getent passwd 1000 &>/dev/null; then
        local existing_user
        existing_user=$(getent passwd 1000 | cut -d: -f1)
        print_info "UID 1000 pertence a: ${existing_user}"

        # Se for o usuário casaos, está tudo certo
        if [[ "${existing_user}" == "${APP_USER}" ]]; then
            print_ok "Usuário '${APP_USER}' já existe com UID 1000 ✓"
            return 0
        else
            print_warn "UID 1000 ocupado por '${existing_user}'"
            print_info "O serviço usará UID numérico 1000 diretamente (seguro)"
            return 0
        fi
    fi

    # ── Cria grupo se não existir ─────────────────────────────
    if ! getent group 1000 &>/dev/null; then
        print_info "Criando grupo '${APP_GROUP}' (GID=1000)..."

        if [[ "${IS_DEBIAN}" == true ]]; then
            groupadd --gid 1000 "${APP_GROUP}" 2>/dev/null || \
            addgroup --gid 1000 "${APP_GROUP}" 2>/dev/null
        else
            groupadd --gid 1000 "${APP_GROUP}" 2>/dev/null
        fi

        if getent group 1000 &>/dev/null; then
            print_ok "Grupo '${APP_GROUP}' criado (GID=1000)"
        else
            print_warn "Grupo não criado, mas GID 1000 será usado numericamente"
        fi
    else
        local existing_group
        existing_group=$(getent group 1000 | cut -d: -f1)
        print_ok "GID 1000 existe: ${existing_group}"
    fi

    # ── Cria usuário se não existir ───────────────────────────
    if ! id "${APP_USER}" &>/dev/null; then
        print_info "Criando usuário '${APP_USER}' (UID=1000)..."

        local criado=false

        if [[ "${IS_DEBIAN}" == true ]]; then
            # Tenta adduser primeiro (Debian/Ubuntu)
            if command -v adduser &>/dev/null; then
                adduser \
                    --uid 1000 \
                    --gid 1000 \
                    --disabled-password \
                    --gecos "Usuario Sistema Gastos Pessoais" \
                    --shell /bin/bash \
                    "${APP_USER}" 2>/dev/null && criado=true
            fi
        fi

        # Se não criou, tenta useradd
        if [[ "${criado}" == false ]]; then
            useradd \
                --uid 1000 \
                --gid 1000 \
                --create-home \
                --shell /bin/bash \
                --comment "Usuario Sistema Gastos Pessoais" \
                "${APP_USER}" 2>/dev/null && criado=true
        fi

        if [[ "${criado}" == true ]]; then
            # Define senha
            echo "${APP_USER}:${APP_PASSWORD}" | chpasswd 2>/dev/null
            print_ok "Usuário '${APP_USER}' criado (UID=1000)"
            print_warn "Senha padrão: '${APP_PASSWORD}' - ALTERE após instalação!"
        else
            print_warn "Usuário não criado, mas UID 1000 será usado numericamente"
            print_info "Isso é NORMAL e SEGURO - padrão Docker/systemd"
        fi
    else
        print_ok "Usuário '${APP_USER}' já existe"
    fi

    # ── Resumo final ───────────────────────────────────────────
    echo ""
    print_info "╔════════════════════════════════════════════════╗"
    print_info "║  Configuração de Segurança do Serviço         ║"
    print_info "╠════════════════════════════════════════════════╣"
    print_info "║  UID         : 1000  (não-root)                ║"
    print_info "║  GID         : 1000  (não-root)                ║"
    print_info "║  Usuário     : ${APP_USER}                              ║"
    print_info "║  Execução    : Modo numérico (seguro)          ║"
    print_info "╚════════════════════════════════════════════════╝"
    echo ""
}

# ── Criar Estrutura de Diretórios ──────────────────────────────────────────────
create_directories() {
    print_step "Criando estrutura de diretórios"

    local dirs=(
        "${INSTALL_DIR}"
        "${INSTALL_DIR}/dados"
        "${INSTALL_DIR}/dados/logs"
        "${INSTALL_DIR}/dados/ssl"
        "${INSTALL_DIR}/dados/usuarios"
        "${INSTALL_DIR}/dados/sistema"
        "${INSTALL_DIR}/modulos"
        "${INSTALL_DIR}/templates"
        "${INSTALL_DIR}/static"
    )

    for dir in "${dirs[@]}"; do
        if [[ ! -d "${dir}" ]]; then
            mkdir -p "${dir}"
            print_ok "Criada : ${dir}"
        else
            print_ok "Existe : ${dir}"
        fi
    done
}

# ── Copiar Arquivos do Servidor ────────────────────────────────────────────────
copy_server_files() {
    print_step "Copiando arquivos do servidor"

    if [[ ! -d "${SERVER_SOURCE}" ]]; then
        print_error "Pasta 'servidor' não encontrada em: ${SCRIPT_DIR}"
        exit 1
    fi

    cp -r "${SERVER_SOURCE}/." "${INSTALL_DIR}/"
    print_ok "Arquivos copiados para: ${INSTALL_DIR}"

    if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
        cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
        print_ok "requirements.txt copiado."
    fi

    # Verifica arquivos essenciais
    local essenciais=("app.py" "gunicorn.conf.py" "requirements.txt")
    for f in "${essenciais[@]}"; do
        if [[ -f "${INSTALL_DIR}/${f}" ]]; then
            print_ok "${f} → OK"
        else
            print_error "${f} → NÃO ENCONTRADO!"
            exit 1
        fi
    done
}

# ── Criar Ambiente Virtual ─────────────────────────────────────────────────────
create_venv() {
    print_step "Criando ambiente virtual Python"

    if ! python3 -m venv --help &>/dev/null; then
        print_warn "python3-venv não encontrado. Instalando..."
        if [[ "${IS_DEBIAN}" == true ]]; then
            apt-get update -qq
            apt-get install -y python3-venv python3-pip python3-full 2>/dev/null || \
            apt-get install -y python3-venv python3-pip
        else
            yum install -y python3-venv python3-pip 2>/dev/null || \
            dnf install -y python3-venv python3-pip 2>/dev/null || true
        fi
    fi

    python3 -m venv "${INSTALL_DIR}/env"

    if [[ $? -ne 0 ]]; then
        print_error "Falha ao criar ambiente virtual!"
        exit 1
    fi

    print_ok "Ambiente virtual: ${INSTALL_DIR}/env"
    print_ok "Python: $("${INSTALL_DIR}/env/bin/python3" --version)"
}

# ── Instalar Bibliotecas ───────────────────────────────────────────────────────
install_libraries() {
    print_step "Instalando bibliotecas Python"

    local pip_bin="${INSTALL_DIR}/env/bin/pip"
    local req_file="${INSTALL_DIR}/requirements.txt"

    [[ ! -f "${req_file}" ]] && {
        print_error "requirements.txt não encontrado!"
        exit 1
    }

    # Garante que gunicorn está no requirements
    if ! grep -qi "gunicorn" "${req_file}"; then
        echo "gunicorn" >> "${req_file}"
        print_info "Adicionado 'gunicorn' ao requirements.txt"
    fi

    print_info "Atualizando pip..."
    "${pip_bin}" install --upgrade pip --quiet
    print_ok "pip atualizado."

    print_info "Instalando dependências..."
    "${pip_bin}" install -r "${req_file}"

    if [[ $? -ne 0 ]]; then
        print_error "Erro ao instalar bibliotecas!"
        exit 1
    fi

    # Verifica gunicorn
    if [[ ! -f "${INSTALL_DIR}/env/bin/gunicorn" ]]; then
        print_warn "Instalando gunicorn separadamente..."
        "${pip_bin}" install gunicorn
    fi

    print_ok "Bibliotecas instaladas!"
    print_ok "Gunicorn: $("${INSTALL_DIR}/env/bin/gunicorn" --version 2>/dev/null)"
}

# ── Atualizar Bibliotecas ──────────────────────────────────────────────────────
update_libraries() {
    print_step "Atualizando bibliotecas Python"
    local pip_bin="${INSTALL_DIR}/env/bin/pip"
    local req_file="${INSTALL_DIR}/requirements.txt"

    # Garante gunicorn
    if ! grep -qi "gunicorn" "${req_file}"; then
        echo "gunicorn" >> "${req_file}"
    fi

    "${pip_bin}" install --upgrade -r "${req_file}"
    [[ $? -eq 0 ]] && print_ok "Bibliotecas atualizadas!" \
                   || print_warn "Algumas bibliotecas podem não ter atualizado."
}

# ── Definir Permissões (UID:GID 1000:1000) ────────────────────────────────────
set_permissions() {
    print_step "Definindo permissões (UID:GID 1000:1000)"

    # Usa UID:GID numérico 1000:1000
    chown -R 1000:1000 "${INSTALL_DIR}"

    # Permissões de arquivos e pastas
    find "${INSTALL_DIR}" -type d -exec chmod 755 {} \;
    find "${INSTALL_DIR}" -type f -exec chmod 644 {} \;
    find "${INSTALL_DIR}/env/bin" -type f -exec chmod 755 {} \; 2>/dev/null

    # Arquivos específicos
    chmod 755 "${INSTALL_DIR}/app.py" 2>/dev/null

    # Pastas de dados precisam de escrita
    chmod 775 "${INSTALL_DIR}/dados"
    chmod 775 "${INSTALL_DIR}/dados/logs"
    chmod 775 "${INSTALL_DIR}/dados/ssl"
    chmod 775 "${INSTALL_DIR}/dados/usuarios"
    chmod 775 "${INSTALL_DIR}/dados/sistema"

    print_ok "Dono     → 1000:1000 (não-root)"
    print_ok "Pastas   → 755"
    print_ok "Arquivos → 644"
    print_ok "Dados    → 775 (escrita)"
}

# ── Criar Serviço systemd ──────────────────────────────────────────────────────
create_service() {
    print_step "Criando serviço systemd: ${SERVICE_NAME}"

    local gunicorn_bin="${INSTALL_DIR}/env/bin/gunicorn"
    local gunicorn_conf="${INSTALL_DIR}/gunicorn.conf.py"
    local log_dir="${INSTALL_DIR}/dados/logs"

    [[ ! -f "${gunicorn_bin}" ]] && {
        print_error "Gunicorn não encontrado: ${gunicorn_bin}"
        exit 1
    }

    cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=${APP_NAME} - Sistema de Gestão Financeira Pessoal
After=network.target network-online.target
Wants=network-online.target

[Service]
# ══════════════════════════════════════════════════════════════
#  SEGURANÇA: Execução com UID:GID 1000:1000 (não-root)
# ══════════════════════════════════════════════════════════════
User=1000
Group=1000

# ══════════════════════════════════════════════════════════════
#  Diretório e Execução
# ══════════════════════════════════════════════════════════════
WorkingDirectory=${INSTALL_DIR}
ExecStart=${gunicorn_bin} -c ${gunicorn_conf} app:app
ExecReload=/bin/kill -s HUP \$MAINPID

# ══════════════════════════════════════════════════════════════
#  Restart Automático
# ══════════════════════════════════════════════════════════════
Restart=on-failure
RestartSec=5s
StartLimitIntervalSec=60s
StartLimitBurst=3

# ══════════════════════════════════════════════════════════════
#  Logs do Serviço
# ══════════════════════════════════════════════════════════════
StandardOutput=append:${log_dir}/service-stdout.log
StandardError=append:${log_dir}/service-stderr.log

# ══════════════════════════════════════════════════════════════
#  Variáveis de Ambiente
# ══════════════════════════════════════════════════════════════
Environment="PYTHONUNBUFFERED=1"
Environment="APP_ENV=production"
Environment="APP_DIR=${INSTALL_DIR}"

# ══════════════════════════════════════════════════════════════
#  Hardening de Segurança
# ══════════════════════════════════════════════════════════════
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${INSTALL_DIR}/dados

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"

    print_ok "Serviço criado: ${SERVICE_FILE}"
    print_ok "Execução: UID=1000 GID=1000 (seguro, não-root)"
}

# ── Iniciar / Parar Serviço ────────────────────────────────────────────────────
start_service() {
    print_step "Iniciando serviço: ${SERVICE_NAME}"
    systemctl start "${SERVICE_NAME}"
    sleep 3

    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_ok "Serviço ATIVO com Gunicorn!"
        echo ""
        print_info "╔════════════════════════════════════════════════╗"
        print_info "║  Acesse o sistema:                             ║"
        print_info "║  https://$(hostname -I | awk '{print $1}'):6300                     ║"
        print_info "╚════════════════════════════════════════════════╝"
    else
        print_error "Falha ao iniciar!"
        echo ""
        echo -e "${YELLOW}─── Log de erro ───────────────────────────────${NC}"
        journalctl -u "${SERVICE_NAME}" -n 30 --no-pager
        echo ""
        print_info "Log em tempo real: journalctl -u ${SERVICE_NAME} -f"
    fi
}

stop_service() {
    print_step "Parando serviço: ${SERVICE_NAME}"
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        systemctl stop "${SERVICE_NAME}"
        sleep 2
        print_ok "Serviço parado."
    else
        print_info "Serviço já estava parado."
    fi
}

# ── Status ─────────────────────────────────────────────────────────────────────
show_status() {
    print_header
    print_step "Status do Servidor — ${APP_NAME}"
    echo ""

    # Status do serviço
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        echo -e "  ${GREEN}● Serviço: ATIVO (Gunicorn em execução)${NC}"
    elif systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null 2>&1; then
        echo -e "  ${RED}● Serviço: PARADO${NC}"
    else
        echo -e "  ${RED}● Serviço: NÃO INSTALADO${NC}"
    fi

    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    systemctl status "${SERVICE_NAME}" --no-pager --lines=10 2>/dev/null \
        || echo "  Serviço não encontrado."

    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}  Informações da Instalação${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"

    [[ -d "${INSTALL_DIR}" ]] && {
        print_ok "Instalado em : ${INSTALL_DIR}"
        print_info "Tamanho      : $(du -sh "${INSTALL_DIR}" 2>/dev/null | cut -f1)"
    } || print_warn "Não instalado."

    [[ -f "${INSTALL_DIR}/env/bin/gunicorn" ]] && \
        print_ok "Gunicorn     : $("${INSTALL_DIR}/env/bin/gunicorn" --version 2>/dev/null)" || \
        print_warn "Gunicorn     : não encontrado"

    check_venv && \
        print_ok "Python       : $("${INSTALL_DIR}/env/bin/python3" --version 2>/dev/null)" || \
        print_warn "Venv         : incompleto"

    print_ok "Execução     : UID=1000 GID=1000 (seguro, não-root)"

    [[ -f "${INSTALL_DIR}/dados/ssl/cert.pem" ]] && \
        print_ok "SSL          : certificado presente" || \
        print_warn "SSL          : será gerado no primeiro start"

    # Logs recentes
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}  Últimas 15 linhas — Log de Erro do Gunicorn${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    local glog="${INSTALL_DIR}/dados/logs/gunicorn.log"
    if [[ -f "${glog}" ]]; then
        tail -n 15 "${glog}"
    else
        echo "  (sem logs ainda)"
    fi

    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}  Últimas 10 linhas — Service STDERR${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    local slog="${INSTALL_DIR}/dados/logs/service-stderr.log"
    if [[ -f "${slog}" ]]; then
        tail -n 10 "${slog}"
    else
        echo "  (sem logs ainda)"
    fi

    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}  Comandos Úteis${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
    echo -e "  ${CYAN}journalctl -u ${SERVICE_NAME} -f${NC}      → Logs em tempo real"
    echo -e "  ${CYAN}systemctl restart ${SERVICE_NAME}${NC}     → Reiniciar serviço"
    echo -e "  ${CYAN}systemctl stop ${SERVICE_NAME}${NC}        → Parar serviço"
    echo ""
}

# ── Instalação Fresh ───────────────────────────────────────────────────────────
fresh_install() {
    print_header
    echo -e "${GREEN}  Nova instalação do ${APP_NAME}...${NC}\n"

    manage_user
    create_directories
    copy_server_files
    create_venv
    install_libraries
    set_permissions
    create_service
    start_service

    echo ""
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           INSTALAÇÃO CONCLUÍDA COM SUCESSO!                 ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║                                                              ║"
    echo "║  Pasta    : /DATA/AppData/Gasto_Pessuais                    ║"
    echo "║  Serviço  : gasto-pessuais                                  ║"
    echo "║  Servidor : Gunicorn (produção)                             ║"
    echo "║  Porta    : 6300 (HTTPS)                                    ║"
    echo "║  Execução : UID=1000 GID=1000 (seguro, não-root)            ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── Reinstalação ───────────────────────────────────────────────────────────────
reinstall() {
    print_header
    echo -e "${YELLOW}  Reinstalação detectada. Atualizando...${NC}\n"

    stop_service

    print_step "Preservando ambiente virtual e dados"
    local tmp_dir="/tmp/gasto_backup_$$"
    mkdir -p "${tmp_dir}"

    # Backup do ambiente virtual
    if [[ -d "${INSTALL_DIR}/env" ]]; then
        print_info "Preservando ambiente virtual..."
        cp -r "${INSTALL_DIR}/env" "${tmp_dir}/env"
        print_ok "Ambiente virtual preservado."
    fi

    # Backup dos dados
    if [[ -d "${INSTALL_DIR}/dados" ]]; then
        print_info "Preservando dados..."
        cp -r "${INSTALL_DIR}/dados" "${tmp_dir}/dados"
        print_ok "Dados preservados."
    fi

    print_step "Removendo arquivos antigos"
    find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 \
        ! -name "env" ! -name "dados" \
        -exec rm -rf {} \; 2>/dev/null
    print_ok "Arquivos antigos removidos."

    # Restaura backups
    [[ -d "${tmp_dir}/env" && ! -d "${INSTALL_DIR}/env" ]] && \
        cp -r "${tmp_dir}/env" "${INSTALL_DIR}/env"
    [[ -d "${tmp_dir}/dados" && ! -d "${INSTALL_DIR}/dados" ]] && \
        cp -r "${tmp_dir}/dados" "${INSTALL_DIR}/dados"

    rm -rf "${tmp_dir}"

    copy_server_files

    # Verifica ambiente virtual
    if check_venv; then
        print_ok "Ambiente virtual OK."
        check_libraries || update_libraries
    else
        print_warn "Venv inválido. Recriando..."
        rm -rf "${INSTALL_DIR}/env"
        create_venv
        install_libraries
    fi

    manage_user
    set_permissions
    create_service
    start_service

    echo ""
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║          REINSTALAÇÃO CONCLUÍDA COM SUCESSO!                ║"
    echo "║  Dados e ambiente virtual foram preservados.                ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── Desinstalação ──────────────────────────────────────────────────────────────
uninstall() {
    print_header
    echo -e "${RED}  ⚠  DESINSTALAÇÃO DO ${APP_NAME}${NC}\n"
    echo -e "${YELLOW}  Esta operação irá:${NC}"
    echo -e "  ${RED}•${NC} Parar e remover o serviço '${SERVICE_NAME}'"
    echo -e "  ${RED}•${NC} Deletar a pasta: ${INSTALL_DIR}"
    echo -e "  ${RED}•${NC} Remover TODOS os dados e logs"
    echo ""
    echo -e "${RED}  ⚠ ATENÇÃO: Esta ação é IRREVERSÍVEL!${NC}"
    echo ""

    read -r -p "  Digite 'CONFIRMAR' para prosseguir: " confirm
    [[ "${confirm}" != "CONFIRMAR" ]] && {
        print_info "Desinstalação cancelada."
        return
    }

    stop_service

    print_step "Removendo serviço systemd"
    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        systemctl disable "${SERVICE_NAME}"
        print_ok "Serviço desabilitado."
    fi

    if [[ -f "${SERVICE_FILE}" ]]; then
        rm -f "${SERVICE_FILE}"
        systemctl daemon-reload
        systemctl reset-failed 2>/dev/null
        print_ok "Arquivo de serviço removido."
    fi

    print_step "Removendo pasta da aplicação"
    if [[ -d "${INSTALL_DIR}" ]]; then
        rm -rf "${INSTALL_DIR}"
        print_ok "Removida: ${INSTALL_DIR}"
    else
        print_info "Pasta não encontrada."
    fi

    echo ""
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              DESINSTALAÇÃO CONCLUÍDA!                       ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── Menu Principal ─────────────────────────────────────────────────────────────
show_menu() {
    print_header

    local install_status service_status

    check_existing_installation && \
        install_status="${GREEN}Instalado${NC}" || \
        install_status="${RED}Não instalado${NC}"

    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        service_status="${GREEN}● Em execução (Gunicorn)${NC}"
    elif systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null 2>&1; then
        service_status="${YELLOW}● Parado${NC}"
    else
        service_status="${RED}● Não configurado${NC}"
    fi

    echo -e "  ${WHITE}Aplicação:${NC} $(eval echo -e "${install_status}")   ${WHITE}Serviço:${NC} $(eval echo -e "${service_status}")"
    echo ""
    echo -e "${CYAN}  ┌──────────────────────────────────────────────┐${NC}"
    echo -e "${CYAN}  │${WHITE}              MENU PRINCIPAL                  ${CYAN}│${NC}"
    echo -e "${CYAN}  ├──────────────────────────────────────────────┤${NC}"
    echo -e "${CYAN}  │${NC}                                              ${CYAN}│${NC}"
    echo -e "${CYAN}  │${NC}   ${WHITE}1.${NC} Instalar / Reinstalar                   ${CYAN}│${NC}"
    echo -e "${CYAN}  │${NC}   ${WHITE}2.${NC} Desinstalar                             ${CYAN}│${NC}"
    echo -e "${CYAN}  │${NC}   ${WHITE}3.${NC} Status do Servidor                      ${CYAN}│${NC}"
    echo -e "${CYAN}  │${NC}   ${WHITE}4.${NC} Sair                                    ${CYAN}│${NC}"
    echo -e "${CYAN}  │${NC}                                              ${CYAN}│${NC}"
    echo -e "${CYAN}  └──────────────────────────────────────────────┘${NC}"
    echo ""
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    check_root

    while true; do
        show_menu
        read -r -p "  Escolha uma opção [1-4]: " choice
        echo ""

        case "$choice" in
            1)
                if check_existing_installation; then
                    reinstall
                else
                    fresh_install
                fi
                ;;
            2)
                if check_existing_installation; then
                    uninstall
                else
                    print_warn "Nenhuma instalação encontrada."
                fi
                ;;
            3)
                show_status
                ;;
            4)
                echo -e "\n${CYAN}  Até logo!${NC}\n"
                exit 0
                ;;
            *)
                print_error "Opção inválida. Escolha 1-4."
                ;;
        esac

        echo ""
        read -r -p "  Pressione ENTER para voltar ao menu..."
    done
}

# ── Execução ───────────────────────────────────────────────────────────────────
main

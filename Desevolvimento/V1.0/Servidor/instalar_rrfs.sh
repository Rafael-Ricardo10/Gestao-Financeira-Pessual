#!/usr/bin/env bash
# =====================================================================
#  RRFS Gestão Financeira - Instalador do servidor (Debian / Ubuntu)
#
#  Coloque este arquivo na MESMA pasta que contém:
#     servidor.py   requirements.txt   templates/   modulos/
#
#  Uso:   sudo ./instalar_rrfs.sh              -> menu
#         sudo ./instalar_rrfs.sh install      -> 1) instalar
#         sudo ./instalar_rrfs.sh update       -> 2) atualizar
#         sudo ./instalar_rrfs.sh stop         -> 3) parar o serviço
#         sudo ./instalar_rrfs.sh start        -> 4) iniciar o serviço
# =====================================================================
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -Eeuo pipefail
umask 022

# ── configuração (pode ser sobrescrita por variáveis de ambiente) ─────
APP_DIR="${RRFS_APP_DIR:-/DATA/AppData/RRFS_Gastos_Pessoais}"
BACKUP_DIR="${RRFS_BACKUP_DIR:-${APP_DIR}_backups}"
SVC="rrfs-gastos"
SVC_USER="${RRFS_USER:-rrfs}"
UNIT_DIR="${RRFS_UNIT_DIR:-/etc/systemd/system}"
UNIT_FILE="$UNIT_DIR/$SVC.service"
ENV_FILE="${RRFS_ENV_FILE:-/etc/default/rrfs-gastos}"
LOG_FILE="${RRFS_LOG_FILE:-/var/log/rrfs-instalador.log}"
MIN_MB=900                      # espaço livre mínimo (venv com numpy/pandas)
SRC="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

ROLLBACK_ARMED=0
INICIOU_NOVA=0
WAS_ACTIVE=0
BK_DIR=""

# ── mensagens ─────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_OK=$'\e[32m'; C_ERR=$'\e[31m'; C_WARN=$'\e[33m'; C_INFO=$'\e[36m'
  C_B=$'\e[1m'; C_0=$'\e[0m'
else
  C_OK=''; C_ERR=''; C_WARN=''; C_INFO=''; C_B=''; C_0=''
fi
info()  { echo "${C_INFO}➜${C_0} $*"; }
ok()    { echo "${C_OK}✔${C_0} $*"; }
aviso() { echo "${C_WARN}!${C_0} $*" >&2; }
titulo(){ echo; echo "${C_B}== $* ==${C_0}"; }

die() {
  trap - ERR
  echo "${C_ERR}✘ $*${C_0}" >&2
  if [[ $ROLLBACK_ARMED -eq 1 ]]; then reverter; fi
  echo "   (detalhes técnicos em $LOG_FILE)" >&2
  exit 1
}
on_err() { die "Erro inesperado na linha $1."; }
trap 'on_err $LINENO' ERR

# ── utilidades ────────────────────────────────────────────────────────
log_cmd() {          # executa gravando a saída no log; mostra o fim se falhar
  local rc=0
  { echo "--- $(date '+%F %T') \$ $*"; } >>"$LOG_FILE" 2>/dev/null || true
  "$@" >>"$LOG_FILE" 2>&1 || rc=$?
  if [[ $rc -ne 0 ]]; then
    aviso "Comando falhou (código $rc): $*"
    tail -n 15 "$LOG_FILE" >&2 || true
  fi
  return $rc
}

run_svc() {          # executa como usuário não-root do serviço
  runuser -u "$SVC_USER" -- env HOME="$APP_DIR/dados" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 "$@"
}

perguntar_sn() {     # perguntar_sn "texto" S|N  -> 0 = sim
  local def="${2:-S}" r
  if [[ ! -t 0 ]]; then [[ "$def" == "S" ]]; return; fi
  read -r -p "$1 [$( [[ $def == S ]] && echo 'S/n' || echo 's/N')] " r || r=""
  r="${r:-$def}"
  [[ "$r" =~ ^[sSyY]$ ]]
}

precisa_root() {
  if [[ $EUID -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      info "Pedindo permissão de administrador (sudo)..."
      exec sudo -E bash "$0" "$@"
    fi
    echo "Execute como administrador:  sudo $0" >&2
    exit 1
  fi
}

validar_config() {
  [[ -n "$APP_DIR" && "$APP_DIR" == /* && "$APP_DIR" != "/" ]] \
    || die "Pasta de instalação inválida: '$APP_DIR'"
  [[ "$SVC_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "Usuário inválido: $SVC_USER"
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
  touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/rrfs-instalador.log"
  chmod 600 "$LOG_FILE" 2>/dev/null || true
}

checar_sistema() {
  command -v systemctl >/dev/null 2>&1 || die "systemd não encontrado (systemctl)."
  [[ -d /run/systemd/system ]] || die "O systemd não está em execução neste sistema."
  command -v python3 >/dev/null 2>&1 \
    || die "python3 não encontrado (instale com: apt install python3 python3-venv)."
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    || die "É necessário Python 3.9 ou superior (encontrado: $(python3 --version 2>&1))."
  command -v runuser >/dev/null 2>&1 || die "Comando 'runuser' não encontrado (pacote util-linux)."
}

validar_origem() {
  local f faltando=()
  local obrig=(servidor.py requirements.txt
    templates/login.html templates/dashboard.html templates/transacoes.html
    templates/categorias.html templates/emprestimos.html templates/config.html
    modulos/contas.py modulos/sync_tox.py modulos/sync_core.py
    modulos/tox_financeiro.py modulos/database.py modulos/loans.py
    modulos/currency_tracker.py modulos/importar_db.py)
  for f in "${obrig[@]}"; do
    [[ -f "$SRC/$f" ]] || faltando+=("$f")
  done
  if [[ ${#faltando[@]} -gt 0 ]]; then
    echo "${C_ERR}Arquivos não encontrados ao lado do instalador ($SRC):${C_0}" >&2
    printf '   - %s\n' "${faltando[@]}" >&2
    die "Coloque o instalador na pasta do servidor, junto de servidor.py, templates/ e modulos/."
  fi
  case "$SRC/" in
    "$APP_DIR"/*) die "O instalador está dentro da pasta de instalação ($APP_DIR). Rode-o a partir da pasta com os arquivos novos." ;;
  esac
}

checar_espaco() {
  local pai livre
  pai="$(dirname "$APP_DIR")"
  mkdir -p "$pai" || die "Não foi possível criar $pai (verifique se /DATA está montado)."
  livre="$(df -Pm "$pai" | awk 'NR==2{print $4}')"
  [[ "${livre:-0}" -ge "$MIN_MB" ]] \
    || die "Pouco espaço livre em $pai: ${livre:-0} MB (necessário ao menos $MIN_MB MB)."
}

# ── estado ────────────────────────────────────────────────────────────
tem_arquivos()  { [[ -f "$APP_DIR/servidor.py" ]]; }
tem_servico()   { [[ -f "$UNIT_FILE" ]]; }
tem_venv()      { [[ -x "$APP_DIR/venv/bin/python" ]]; }
instalado()     { tem_arquivos && tem_servico && tem_venv; }
servico_ativo() { systemctl is-active --quiet "$SVC" 2>/dev/null; }

porta_servico() {
  local p=""
  [[ -f "$ENV_FILE" ]] && p="$(grep -E '^RRFS_PORTA=' "$ENV_FILE" | tail -n1 | cut -d= -f2 | tr -dc '0-9')"
  echo "${p:-6250}"
}

host_servico() {
  local h=""
  [[ -f "$ENV_FILE" ]] && h="$(grep -E '^RRFS_HOST=' "$ENV_FILE" | tail -n1 | cut -d= -f2 | tr -d '[:space:]')"
  echo "${h:-127.0.0.1}"
}

ips_locais() {
  local ip
  for ip in $(hostname -I 2>/dev/null || true); do
    [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || continue
    [[ "$ip" == 127.* || "$ip" == 172.17.* ]] && continue
    echo "$ip"
  done
}

porta_ocupada() {
  command -v ss >/dev/null 2>&1 || return 1
  [[ -n "$(ss -ltnH "sport = :$1" 2>/dev/null)" ]]
}

# ── pacotes do sistema ────────────────────────────────────────────────
tox_instalada() {
  python3 -c 'import ctypes.util,sys; sys.exit(0 if ctypes.util.find_library("toxcore") else 1)' 2>/dev/null
}

venv_possivel() {
  local t; t="$(mktemp -d)"
  if python3 -m venv "$t/v" >/dev/null 2>&1; then rm -rf "$t"; return 0; fi
  rm -rf "$t"; return 1
}

instalar_pacotes() {
  local falta=() apt_ok=0 atualizado=0
  command -v apt-get >/dev/null 2>&1 && apt_ok=1
  command -v curl >/dev/null 2>&1 || falta+=(curl)
  venv_possivel || falta+=(python3-venv)

  apt_instalar() {
    [[ $apt_ok -eq 1 ]] || return 1
    if [[ $atualizado -eq 0 ]]; then
      info "Atualizando lista de pacotes (apt)..."
      log_cmd apt-get update || aviso "apt-get update falhou; tentando mesmo assim."
      atualizado=1
    fi
    DEBIAN_FRONTEND=noninteractive log_cmd apt-get install -y --no-install-recommends "$@"
  }

  if [[ ${#falta[@]} -gt 0 ]]; then
    info "Instalando pacotes necessários: ${falta[*]}"
    apt_instalar "${falta[@]}" \
      || die "Não foi possível instalar: ${falta[*]}. Instale manualmente e rode de novo."
    venv_possivel || die "python3 -m venv continua indisponível. Instale o pacote python3-venv."
  fi

  if ! tox_instalada; then
    info "Instalando a biblioteca Tox (sincronização com os apps)..."
    if ! { apt_instalar libtoxcore2 || apt_instalar libtoxcore-dev; } || ! tox_instalada; then
      aviso "libtoxcore não pôde ser instalada. O site funciona, mas a sincronização"
      aviso "com os apps desktop ficará indisponível até instalá-la (apt install libtoxcore2)."
    fi
  fi
  ok "Pacotes do sistema verificados."
}

# ── usuário, pastas, arquivos ─────────────────────────────────────────
criar_usuario() {
  if id -u "$SVC_USER" >/dev/null 2>&1; then
    ok "Usuário '$SVC_USER' já existe."
    return 0
  fi
  local sh=/usr/sbin/nologin
  [[ -x "$sh" ]] || sh=/bin/false
  useradd --system --user-group --no-create-home --home-dir "$APP_DIR" \
          --shell "$sh" "$SVC_USER" || die "Não foi possível criar o usuário '$SVC_USER'."
  ok "Usuário de serviço '$SVC_USER' criado (sem login, sem privilégios de root)."
}

preparar_dirs() {
  mkdir -p "$APP_DIR/templates" "$APP_DIR/modulos" "$APP_DIR/dados" "$APP_DIR/logs" \
    || die "Não foi possível criar $APP_DIR."
  mkdir -p "$APP_DIR/dados/.cache"
}

copiar_sistema() {
  info "Copiando arquivos do sistema..."
  local f
  install -d "$APP_DIR/templates" "$APP_DIR/modulos"
  install -m 640 "$SRC/servidor.py"       "$APP_DIR/servidor.py"
  install -m 640 "$SRC/requirements.txt"  "$APP_DIR/requirements.txt"
  for f in "$SRC"/templates/*.html; do install -m 640 "$f" "$APP_DIR/templates/"; done
  for f in "$SRC"/modulos/*.py;     do install -m 640 "$f" "$APP_DIR/modulos/"; done
  [[ -f "$APP_DIR/modulos/__init__.py" ]] || : > "$APP_DIR/modulos/__init__.py"
  date '+%Y-%m-%d %H:%M:%S' > "$APP_DIR/VERSAO"
  install -d "$APP_DIR/logs"
  ok "Arquivos copiados para $APP_DIR."
}

copiar_dados_origem() {
  [[ -d "$SRC/dados" ]] || return 0
  [[ -z "$(ls -A "$APP_DIR/dados" 2>/dev/null | grep -v '^\.cache$' || true)" ]] || return 0
  local n; n="$(find "$SRC/dados" -maxdepth 1 -name '*.db' | wc -l)"
  [[ "$n" -gt 0 ]] || return 0
  echo
  info "Encontrei dados na pasta de origem ($n banco(s) em $SRC/dados)."
  aviso "Pare o servidor de teste ANTES de copiar (senão a cópia pode ficar inconsistente)."
  aviso "Copiar também preserva a identidade Tox: os apps já pareados continuam funcionando."
  if perguntar_sn "Copiar os dados existentes para a instalação?" S; then
    cp -a "$SRC/dados/." "$APP_DIR/dados/" || die "Falha ao copiar os dados."
    ok "Dados copiados."
  else
    info "Instalação começará sem dados (contas novas)."
  fi
}

limpar_codigo() {    # apaga tudo, exceto dados/ e venv/
  [[ -n "$APP_DIR" && -d "$APP_DIR" ]] || return 1
  find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name dados ! -name venv \
       -exec rm -rf -- {} +
}

aplicar_permissoes() {
  info "Aplicando permissões (usuário '$SVC_USER', sem root)..."
  chown -R "$SVC_USER:$SVC_USER" "$APP_DIR" || die "chown falhou em $APP_DIR."
  chmod 750 "$APP_DIR"
  find "$APP_DIR" \( -path "$APP_DIR/venv" -o -path "$APP_DIR/dados" \) -prune -o \
       -type d -exec chmod 750 {} +
  find "$APP_DIR" \( -path "$APP_DIR/venv" -o -path "$APP_DIR/dados" \) -prune -o \
       -type f -exec chmod 640 {} +
  mkdir -p "$APP_DIR/dados"
  find "$APP_DIR/dados" -type d -exec chmod 700 {} +
  find "$APP_DIR/dados" -type f -exec chmod 600 {} +
  # o usuário do serviço precisa conseguir gravar nestas pastas
  runuser -u "$SVC_USER" -- test -w "$APP_DIR/dados" \
    || die "O usuário '$SVC_USER' não consegue gravar em $APP_DIR/dados."
  runuser -u "$SVC_USER" -- test -w "$APP_DIR/logs" \
    || die "O usuário '$SVC_USER' não consegue gravar em $APP_DIR/logs."
  ok "Permissões aplicadas."
}

# ── ambiente virtual e bibliotecas ────────────────────────────────────
criar_venv() {
  if tem_venv && run_svc "$APP_DIR/venv/bin/python" -c 'import sys' >/dev/null 2>&1; then
    ok "Ambiente virtual existente está saudável."
    return 0
  fi
  if [[ -d "$APP_DIR/venv" ]]; then
    aviso "Ambiente virtual danificado (ex.: Python do sistema foi atualizado). Recriando..."
    rm -rf "$APP_DIR/venv"
  fi
  info "Criando ambiente virtual..."
  chown "$SVC_USER:$SVC_USER" "$APP_DIR"
  log_cmd run_svc python3 -m venv "$APP_DIR/venv" \
    || die "Falha ao criar o ambiente virtual."
  ok "Ambiente virtual criado."
}

instalar_libs() {
  info "Instalando/atualizando bibliotecas do requirements.txt (pode levar alguns minutos)..."
  log_cmd run_svc "$APP_DIR/venv/bin/python" -m pip install --quiet --upgrade pip wheel \
    || aviso "Não foi possível atualizar o pip (seguindo com a versão atual)."
  log_cmd run_svc "$APP_DIR/venv/bin/python" -m pip install --upgrade \
      --progress-bar off -r "$APP_DIR/requirements.txt" \
    || die "Falha ao instalar as bibliotecas (verifique a conexão com a internet)."
  if ! log_cmd run_svc "$APP_DIR/venv/bin/python" -m pip check; then
    aviso "pip check apontou conflitos de versões (veja $LOG_FILE)."
  fi
  ok "Bibliotecas instaladas e atualizadas."
}

testar_import() {    # garante que o servidor carrega antes de ligar o serviço
  info "Testando se o servidor carrega corretamente..."
  ( cd "$APP_DIR" && log_cmd run_svc "$APP_DIR/venv/bin/python" -c "import servidor" ) \
    || die "O servidor não carregou (arquivo ou biblioteca faltando). Veja $LOG_FILE."
  ok "Servidor carrega sem erros."
}

# ── configuração e serviço ────────────────────────────────────────────
criar_env() {
  if [[ -f "$ENV_FILE" ]]; then
    ok "Configuração existente mantida ($ENV_FILE)."
    return 0
  fi
  local modo="2" hosts="" ip nome
  if [[ -t 0 ]]; then
    echo
    echo "Quem poderá acessar o site?"
    echo "  1) Somente este computador"
    echo "  2) Outros aparelhos da rede local / VPN (recomendado para a família)"
    read -r -p "Escolha [2]: " modo || modo=2
    modo="${modo:-2}"
  fi
  mkdir -p "$(dirname "$ENV_FILE")"
  if [[ "$modo" == "1" ]]; then
    printf 'RRFS_HOST=127.0.0.1\nRRFS_PORTA=6250\nRRFS_HOSTS=\n' > "$ENV_FILE"
  else
    nome="$(hostname 2>/dev/null || echo servidor)"
    hosts="$nome,$nome.local"
    for ip in $(ips_locais); do hosts="$hosts,$ip"; done
    printf 'RRFS_HOST=0.0.0.0\nRRFS_PORTA=6250\nRRFS_HOSTS=%s\n' "$hosts" > "$ENV_FILE"
  fi
  chmod 644 "$ENV_FILE"
  ok "Configuração criada em $ENV_FILE"
  info "Para liberar outro endereço/nome, edite RRFS_HOSTS nesse arquivo e reinicie (opção 3 e 4)."
}

criar_servico() {
  info "Criando o serviço systemd ($SVC)..."
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_FILE" <<EOF
[Unit]
Description=RRFS Gestão Financeira (servidor web)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=-$ENV_FILE
Environment=HOME=$APP_DIR/dados
Environment=XDG_CACHE_HOME=$APP_DIR/dados/.cache
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/venv/bin/python servidor.py
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
EOF
  chmod 644 "$UNIT_FILE"
  systemctl daemon-reload || die "systemctl daemon-reload falhou."
  systemctl enable "$SVC" >>"$LOG_FILE" 2>&1 || die "Não foi possível ativar o serviço no boot."
  ok "Serviço criado e ativado para iniciar com o sistema."
}

esperar_servidor() {
  local porta i; porta="$(porta_servico)"
  for i in $(seq 1 45); do
    servico_ativo || return 1
    if curl -fsS -o /dev/null --max-time 3 "http://127.0.0.1:${porta}/login" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

mostrar_log_servico() {
  echo "---- últimas linhas do serviço ----" >&2
  journalctl -u "$SVC" -n 25 --no-pager 2>/dev/null >&2 || tail -n 25 "$APP_DIR/logs/servidor.log" >&2 || true
  echo "-----------------------------------" >&2
}

iniciar_servico() {
  local porta; porta="$(porta_servico)"
  if ! servico_ativo && porta_ocupada "$porta"; then
    die "A porta $porta já está em uso por outro programa (talvez o servidor de teste). Feche-o e tente de novo."
  fi
  INICIOU_NOVA=1
  systemctl restart "$SVC" || { mostrar_log_servico; die "Não foi possível iniciar o serviço."; }
  info "Aguardando o servidor responder..."
  if esperar_servidor; then
    ok "Servidor no ar."
  else
    mostrar_log_servico
    die "O serviço iniciou mas o site não respondeu na porta $porta."
  fi
}

mostrar_acesso() {
  local porta host ip; porta="$(porta_servico)"; host="$(host_servico)"
  titulo "Pronto"
  echo "  Acesse:  ${C_B}http://127.0.0.1:$porta${C_0}   (neste computador)"
  if [[ "$host" != "127.0.0.1" ]]; then
    for ip in $(ips_locais); do echo "           ${C_B}http://$ip:$porta${C_0}   (rede local / VPN)"; done
  fi
  echo
  echo "  Ver logs:        journalctl -u $SVC -f"
  echo "  Configuração:    $ENV_FILE"
  echo "  Dados/contas:    $APP_DIR/dados"
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    aviso "Firewall (ufw) ativo: libere a porta para a rede, ex.:  sudo ufw allow $porta/tcp"
  fi
}

# ── backup / rollback (atualização) ───────────────────────────────────
fazer_backup() {
  BK_DIR="$BACKUP_DIR/$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BK_DIR" || die "Não foi possível criar a pasta de backup $BK_DIR."
  chmod 700 "$BACKUP_DIR" "$BK_DIR"
  info "Criando backup em $BK_DIR ..."
  tar -czf "$BK_DIR/codigo.tar.gz" -C "$APP_DIR" \
      --exclude=./dados --exclude=./venv --exclude=./logs . \
    || die "Falha ao criar o backup do código."
  tar -czf "$BK_DIR/dados.tar.gz" -C "$APP_DIR" dados \
    || die "Falha ao criar o backup dos dados."
  ok "Backup criado."
}

limpar_backups_antigos() {
  [[ -d "$BACKUP_DIR" ]] || return 0
  local d
  while IFS= read -r d; do rm -rf -- "$d"; done < <(
    find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +6)
}

reverter() {
  ROLLBACK_ARMED=0
  set +e
  trap - ERR
  aviso "Algo deu errado: restaurando a versão anterior..."
  systemctl stop "$SVC" >/dev/null 2>&1
  if [[ -n "$BK_DIR" && -f "$BK_DIR/codigo.tar.gz" ]]; then
    limpar_codigo
    tar -xzf "$BK_DIR/codigo.tar.gz" -C "$APP_DIR"
    if [[ $INICIOU_NOVA -eq 1 && -f "$BK_DIR/dados.tar.gz" ]]; then
      rm -rf "$APP_DIR/dados"
      tar -xzf "$BK_DIR/dados.tar.gz" -C "$APP_DIR"
    fi
    aplicar_permissoes >/dev/null 2>&1
    systemctl daemon-reload
    if [[ $WAS_ACTIVE -eq 1 ]]; then
      systemctl start "$SVC"
      if esperar_servidor; then
        ok "Versão anterior restaurada e em execução."
      else
        aviso "Versão anterior restaurada, mas o serviço não respondeu. Veja: journalctl -u $SVC -n 50"
      fi
    else
      ok "Versão anterior restaurada (serviço permanece parado, como estava)."
    fi
    info "Backup mantido em: $BK_DIR"
  else
    aviso "Backup não disponível para restaurar."
  fi
}

# ── ações do menu ─────────────────────────────────────────────────────
acao_instalar() {
  titulo "1) Instalar"
  if instalado; then
    aviso "O sistema já está instalado em $APP_DIR."
    info "Para colocar uma nova versão use a opção 2 (Atualizar)."
    return 0
  fi
  if tem_arquivos || tem_servico || tem_venv; then
    info "Instalação incompleta encontrada: será concluída (dados preservados)."
  fi
  validar_origem
  checar_sistema
  checar_espaco
  instalar_pacotes
  criar_usuario
  preparar_dirs
  copiar_sistema
  copiar_dados_origem
  chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"
  criar_venv
  instalar_libs
  testar_import
  criar_env
  criar_servico
  aplicar_permissoes
  iniciar_servico
  mostrar_acesso
  ok "Instalação concluída."
}

acao_atualizar() {
  titulo "2) Atualizar"
  if ! instalado; then
    aviso "O sistema não está instalado (ou está incompleto). Use a opção 1 (Instalar)."
    return 0
  fi
  validar_origem
  checar_sistema
  checar_espaco
  id -u "$SVC_USER" >/dev/null 2>&1 || die "Usuário '$SVC_USER' não existe. Use a opção 1 para reparar."

  if servico_ativo; then WAS_ACTIVE=1; fi
  info "Parando o serviço antes de atualizar..."
  systemctl stop "$SVC" || die "Não foi possível parar o serviço."

  fazer_backup
  ROLLBACK_ARMED=1

  info "Removendo a versão antiga (mantendo dados e ambiente virtual)..."
  limpar_codigo || die "Falha ao remover arquivos antigos."
  preparar_dirs
  copiar_sistema
  chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"
  criar_venv
  instalar_libs
  testar_import
  criar_env
  criar_servico
  aplicar_permissoes
  iniciar_servico

  ROLLBACK_ARMED=0
  limpar_backups_antigos
  mostrar_acesso
  ok "Atualização concluída. Backup desta atualização: $BK_DIR"
}

acao_parar() {
  titulo "3) Parar serviço"
  if ! tem_servico; then aviso "Serviço não instalado. Use a opção 1."; return 0; fi
  if ! servico_ativo; then ok "O serviço já está parado."; return 0; fi
  systemctl stop "$SVC" || die "Não foi possível parar o serviço."
  servico_ativo && die "O serviço continua ativo."
  ok "Serviço parado. (Ele volta a iniciar no próximo boot; para isso não acontecer: systemctl disable $SVC)"
}

acao_iniciar() {
  titulo "4) Iniciar serviço"
  if ! instalado; then aviso "O sistema não está instalado. Use a opção 1."; return 0; fi
  checar_sistema
  iniciar_servico
  mostrar_acesso
}

# ── menu ──────────────────────────────────────────────────────────────
status_linha() {
  local i s v=""
  if instalado; then i="${C_OK}instalado${C_0}"; else i="${C_WARN}não instalado${C_0}"; fi
  if tem_servico; then
    if servico_ativo; then s="${C_OK}rodando${C_0}"; else s="${C_WARN}parado${C_0}"; fi
  else s="—"; fi
  [[ -f "$APP_DIR/VERSAO" ]] && v="  |  versão de $(cat "$APP_DIR/VERSAO")"
  echo "  Estado: $i  |  Serviço: $s$v"
  echo "  Pasta:  $APP_DIR"
}

executar() {         # roda a ação isolada: um erro não derruba o menu
  set +e
  ( set -e; "$@" )
  local rc=$?
  set -e
  [[ $rc -eq 0 ]] || aviso "A operação terminou com erro (veja a mensagem acima)."
  return 0
}

menu() {
  local op
  while true; do
    echo
    echo "${C_B}=========== RRFS Gestão Financeira - Servidor ===========${C_0}"
    status_linha
    echo
    echo "  1) Instalar"
    echo "  2) Atualizar (nova versão)"
    echo "  3) Parar serviço"
    echo "  4) Iniciar serviço"
    echo "  0) Sair"
    echo
    read -r -p "Escolha uma opção: " op || exit 0
    case "$op" in
      1) executar acao_instalar ;;
      2) executar acao_atualizar ;;
      3) executar acao_parar ;;
      4) executar acao_iniciar ;;
      0|q|Q|sair) exit 0 ;;
      *) aviso "Opção inválida." ;;
    esac
  done
}

# ── principal ─────────────────────────────────────────────────────────
precisa_root "$@"
validar_config
case "${1:-}" in
  "")                 menu ;;
  1|install|instalar) acao_instalar ;;
  2|update|atualizar) acao_atualizar ;;
  3|stop|parar)       acao_parar ;;
  4|start|iniciar)    acao_iniciar ;;
  *) echo "Uso: sudo $0 [install|update|stop|start]" >&2; exit 2 ;;
esac

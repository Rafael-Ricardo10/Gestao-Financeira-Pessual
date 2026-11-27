#!/usr/bin/env bash
# ======================================================================
#  Instalador do RRFS Finanças para Linux (versão DISTROBOX)
#  Host: Debian 13 (ou derivado) limpo. Usuário comum, sem sudo.
#
#  O sistema do usuário fica LIMPO: Python, bibliotecas Qt, libtoxcore e
#  o ambiente virtual ficam dentro de um container Debian (distrobox).
#
#  Instala em  ~/.local/share/Gastos_Pessoais/   (código, venv e dados)
#  Cria atalho no menu (categoria Escritório) e início automático.
#  O atalho abre o distrobox e roda o app.py dentro do container.
#
#  Uso:  ./install.sh [--sem-autostart] [--sem-apt] [--sem-pip]
#                     [--desinstalar [--container]]
#   --sem-autostart  não inicia junto com o sistema
#   --sem-apt        não instala pacotes (nem no sistema, nem no container)
#   --sem-pip        não cria/atualiza o ambiente Python (uso em testes)
#   --desinstalar    remove atalho, início automático e programa
#                    (pergunta antes de apagar seus dados)
#   --container      junto com --desinstalar: remove também o container
#
#  SEGURANÇA: roda SEMPRE como o seu usuário. A senha de ROOT só é pedida
#  (via "su") se o distrobox/podman ainda NÃO estiverem instalados, e é
#  digitada no próprio su (este script nunca a lê nem a guarda). Todo o
#  resto roda sem root. Os dados (dados/) e logs (logs/) NUNCA são
#  copiados do projeto nem apagados em atualizações.
# ======================================================================
set -uo pipefail

APP_ID="rrfs-financas"
NOME="RRFS Finanças"
QUADRO="$(cd "$(dirname "$0")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DESTINO="$DATA_HOME/Gastos_Pessoais"
SODIUM_URL="https://github.com/jedisct1/libsodium/releases/download/1.0.19-RELEASE/libsodium-1.0.19.tar.gz"
TOX_URL="https://github.com/TokTok/c-toxcore/releases/download/v0.2.20/c-toxcore-0.2.20.tar.gz"
APPS="$DATA_HOME/applications"
ICONES="$DATA_HOME/icons/hicolor/256x256/apps"
AUTOSTART="$CONF_HOME/autostart"
LAUNCHER="$DESTINO/executar.sh"
CONF_CONTAINER="$DESTINO/container.conf"

CONTAINER="debian"                       # nome do container distrobox
IMAGEM="docker.io/library/debian:13"     # imagem usada se for preciso criar

AUTO=1; APT=1; PIP=1; REMOVER=0; REM_CONT=0
for a in "$@"; do
    case "$a" in
        --sem-autostart) AUTO=0 ;;
        --sem-apt) APT=0 ;;
        --sem-pip) PIP=0 ;;
        --desinstalar) REMOVER=1 ;;
        --container) REM_CONT=1 ;;
        --su|--sudo) ;;   # ignorado: a elevação é sempre via su, só para o distrobox
        -h|--help) sed -n 2,26p "$0"; exit 0 ;;
        *) echo "opção desconhecida: $a"; exit 1 ;;
    esac
done

die()   { echo; echo "ERRO: $*" >&2; exit 1; }
passo() { echo; echo "[$1] $2"; }
aviso() { echo "   AVISO: $*"; }

[ "$(uname -s)" = "Linux" ] || die "este instalador é para Linux."
[ "$(id -u)" -ne 0 ] || die "não rode como root nem com sudo: rode como usuário comum. A senha de root é pedida só se o distrobox precisar ser instalado."

[ -f "$CONF_CONTAINER" ] && CONTAINER="$(head -n1 "$CONF_CONTAINER")"

# Executa um comando DENTRO do container (stdin isolado para não travar)
dbx() { distrobox enter "$CONTAINER" -- "$@" </dev/null; }

atualiza_caches() {
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null
    if   command -v kbuildsycoca6 >/dev/null 2>&1; then kbuildsycoca6 >/dev/null 2>&1
    elif command -v kbuildsycoca5 >/dev/null 2>&1; then kbuildsycoca5 >/dev/null 2>&1; fi
    return 0
}

# ── desinstalar ───────────────────────────────────────────────────────
if [ "$REMOVER" = 1 ]; then
    pkill -f "$DESTINO/app.py" 2>/dev/null || true
    rm -f "$APPS/$APP_ID.desktop" "$AUTOSTART/$APP_ID.desktop" "$ICONES/$APP_ID.png"
    if [ -d "$DESTINO/dados" ]; then
        read -r -p "Apagar também seus DADOS em $DESTINO/dados ? (digite APAGAR para confirmar): " r
        if [ "$r" = "APAGAR" ]; then rm -rf "$DESTINO"; echo "Tudo removido."
        else
            find "$DESTINO" -mindepth 1 -maxdepth 1 ! -name dados ! -name logs -exec rm -rf {} +
            echo "Programa removido. Dados mantidos em $DESTINO/dados"
        fi
    else rm -rf "$DESTINO"; echo "Programa removido."; fi
    if [ "$REM_CONT" = 1 ] && command -v distrobox >/dev/null 2>&1; then
        distrobox rm --force "$CONTAINER" </dev/null >/dev/null 2>&1 \
            && echo "Container '$CONTAINER' removido." || echo "Não foi possível remover o container."
    else
        echo "O container '$CONTAINER' foi mantido (use --desinstalar --container para removê-lo)."
    fi
    atualiza_caches
    exit 0
fi

[ -f "$QUADRO/app.py" ] || die "app.py não encontrado em $QUADRO (rode o instalador dentro da pasta do projeto)."
[ -d "$QUADRO/modulos" ] && [ -d "$QUADRO/interface" ] || die "pastas modulos/ e interface/ não encontradas."

# ── 1. SISTEMA (host): distrobox + podman ─────────────────────────────
#    Só aqui a senha de ROOT é necessária, e só se algo estiver faltando.
passo "1/7" "distrobox no sistema"
TMP="$(mktemp -d)"; chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT

TEM_DISTROBOX=0; command -v distrobox >/dev/null 2>&1 && TEM_DISTROBOX=1
MOTOR=""
if   command -v podman >/dev/null 2>&1; then MOTOR="podman"
elif command -v docker >/dev/null 2>&1; then MOTOR="docker"; fi

PKGS_ROOT=""
[ "$TEM_DISTROBOX" -eq 0 ] && PKGS_ROOT="distrobox"
if [ -z "$MOTOR" ]; then PKGS_ROOT="$PKGS_ROOT podman uidmap passt"; MOTOR="podman"; fi

PRECISA_SUBID=0
if [ "$MOTOR" = "podman" ]; then
    grep -q "^$USER:" /etc/subuid 2>/dev/null || PRECISA_SUBID=1
    grep -q "^$USER:" /etc/subgid 2>/dev/null || PRECISA_SUBID=1
fi

if [ -n "$PKGS_ROOT" ] || [ "$PRECISA_SUBID" -eq 1 ]; then
    command -v apt-get >/dev/null 2>&1 || die "sistema sem apt. Instale (como root): distrobox e podman."
    command -v su >/dev/null 2>&1 || die "comando 'su' não encontrado. Peça ao administrador para instalar:$PKGS_ROOT"
    [ "$APT" = 1 ] || die "distrobox/podman ausentes e --sem-apt foi usado. Instale:$PKGS_ROOT"

    FLAG="$TMP/auth.flag"
    {
        echo '#!/bin/bash'
        echo "touch '$FLAG'"
        echo 'export PATH=/usr/sbin:/sbin:/usr/local/sbin:/usr/local/bin:/usr/bin:/bin'
        echo 'export DEBIAN_FRONTEND=noninteractive'
        if [ -n "$PKGS_ROOT" ]; then
            echo 'apt-get update -qq'
            echo "apt-get install -y $PKGS_ROOT || { for p in $PKGS_ROOT; do apt-get install -y \$p || echo \"(nao instalado: \$p)\"; done; }"
        fi
        if [ "$PRECISA_SUBID" -eq 1 ]; then
            echo "grep -q '^$USER:' /etc/subuid || usermod --add-subuids 100000-165535 '$USER'"
            echo "grep -q '^$USER:' /etc/subgid || usermod --add-subgids 100000-165535 '$USER'"
        fi
        echo 'true'
    } > "$TMP/root1.sh"
    chmod 755 "$TMP"; chmod 644 "$TMP/root1.sh"   # root precisa ler o arquivo

    echo "   Comandos que serão executados como administrador:"
    grep -v '^#!\|^export ' "$TMP/root1.sh" | sed 's/^/     | /'
    echo "   Digite a senha do ROOT quando o terminal pedir (usada só nesta etapa)."
    TENT=0
    while [ "$TENT" -lt 3 ]; do
        su -l root -c "bash '$TMP/root1.sh'" && break
        [ -f "$FLAG" ] && break          # senha aceita; falha foi do apt
        TENT=$((TENT+1)); echo "   Senha incorreta ($TENT/3)."
    done
    chmod 700 "$TMP"
    hash -r
    command -v distrobox >/dev/null 2>&1 || die "distrobox não foi instalado. Confira a senha de root e a internet."
    [ "$MOTOR" = "podman" ] && podman system migrate >/dev/null 2>&1
    echo "   ok: distrobox pronto."
else
    echo "   distrobox já instalado: a senha de root NÃO é necessária."
fi

# A partir daqui tudo roda como USUÁRIO COMUM (sem root).

# ── 2. container Debian ───────────────────────────────────────────────
passo "2/7" "container Debian no distrobox"
LISTA="$(distrobox list --no-color </dev/null 2>/dev/null)"
EXISTE=""
if echo "$LISTA" | awk -F'|' 'NR>1{gsub(/ /,"",$2); print $2}' | grep -qx "$CONTAINER"; then
    EXISTE="$CONTAINER"
else
    OUTRO="$(echo "$LISTA" | awk -F'|' 'NR>1{n=$2; i=$4; gsub(/ /,"",n); if (i ~ /debian/) {print n; exit}}')"
    [ -n "$OUTRO" ] && EXISTE="$OUTRO"
fi
if [ -n "$EXISTE" ]; then
    CONTAINER="$EXISTE"
    echo "   usando o container existente: $CONTAINER"
else
    echo "   nenhum container Debian: baixando $IMAGEM e criando '$CONTAINER'..."
    distrobox create --name "$CONTAINER" --image "$IMAGEM" --yes </dev/null \
        || die "falha ao criar o container (verifique a internet)."
fi
echo "   iniciando o container (a primeira vez demora)..."
dbx true || die "não foi possível iniciar o container '$CONTAINER'."
dbx grep -qi '^ID=debian' /etc/os-release || aviso "o container não parece Debian; seguindo com apt."

# ── 3. dependências DENTRO do container ───────────────────────────────
#    O sudo do container é interno: não dá root no sistema do usuário.
passo "3/7" "dependências dentro do container"
PACOTES="python3 python3-venv python3-pip libsodium23 \
 libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
 libxcb-shape0 libxcb-cursor0 libxkbcommon-x11-0 libgl1 libegl1 libdbus-1-3 libglib2.0-0 \
 libfontconfig1 ca-certificates libtoxcore2"

tem_tox() { dbx bash -c 'ldconfig -p 2>/dev/null | grep -q "libtoxcore\.so\.2"'; }

if [ "$APT" = 1 ]; then
    FALTANDO="$(dbx bash -c "for p in $PACOTES; do dpkg -s \$p >/dev/null 2>&1 || echo -n \"\$p \"; done")"
    if [ -n "${FALTANDO// /}" ]; then
        echo "   instalando no container: $FALTANDO"
        dbx sudo env DEBIAN_FRONTEND=noninteractive apt-get update -qq
        if ! dbx sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $FALTANDO; then
            echo "   falha em lote, tentando um por um..."
            for p in $FALTANDO; do
                dbx sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$p" >/dev/null 2>&1 \
                    || echo "   (nao instalado: $p)"
            done
        fi
    else
        echo "   pacotes do container já instalados."
    fi
else
    echo "   (pulado)"
fi
dbx python3 --version >/dev/null 2>&1 || die "python3 não encontrado no container."

# ── 4. copiar o programa (nunca dados/ nem logs/) ─────────────────────
passo "4/7" "copiando para $DESTINO"
pkill -f "$DESTINO/app.py" 2>/dev/null || true
mkdir -p "$DESTINO/dados" "$DESTINO/logs"
for d in interface modulos tests; do
    rm -rf "${DESTINO:?}/$d"
    [ -d "$QUADRO/$d" ] && cp -r "$QUADRO/$d" "$DESTINO/$d"
done
for f in app.py requirements.txt finance_icon.png make_icon.py LICENSE; do
    [ -f "$QUADRO/$f" ] && cp "$QUADRO/$f" "$DESTINO/$f"
done
find "$DESTINO" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
chmod 700 "$DESTINO/dados"
printf '%s\n' "$CONTAINER" > "$CONF_CONTAINER"

# ── 5. ambiente Python + libtoxcore (dentro do container) ─────────────
passo "5/7" "ambiente Python (venv) e libtoxcore"
REQ_BASE="PyQt5 matplotlib numpy python-dateutil yfinance pdfplumber requests psutil
cryptography keyring sqlcipher3-binary pandas werkzeug"
PIPB="$DESTINO/venv/bin/pip"
PY="$DESTINO/venv/bin/python"

instalar_pacotes() {
    local req="$DESTINO/requirements.txt"
    if [ -f "$req" ]; then
        dbx "$PIPB" install -q -r "$req" && return 0
        echo "   a instalação em bloco falhou; tentando pacote por pacote..."
        grep -vE '^\s*(#|$)' "$req" | sed 's/#.*//' | while read -r linha; do
            [ -n "$linha" ] && { dbx "$PIPB" install -q "$linha" || echo "   FALHOU: $linha"; }
        done
    else
        for pc in $REQ_BASE; do dbx "$PIPB" install -q "$pc" || echo "   FALHOU: $pc"; done
    fi
}

# Imprime "OK <pip>" ou "FALTA <pip> <critico|opcional>"
verificar_libs() {
    cat > "$DESTINO/.verificar_libs.py" <<'PYEOF'
import importlib
obrigatorias = [('PyQt5', 'PyQt5'), ('cryptography', 'cryptography'),
                ('matplotlib', 'matplotlib'), ('numpy', 'numpy'),
                ('dateutil', 'python-dateutil'), ('yfinance', 'yfinance'),
                ('pdfplumber', 'pdfplumber'), ('requests', 'requests'),
                ('psutil', 'psutil'), ('keyring', 'keyring')]
opcionais = [('sqlcipher3', 'sqlcipher3-binary')]
for lista, tipo in ((obrigatorias, 'critico'), (opcionais, 'opcional')):
    for mod, pip in lista:
        try:
            importlib.import_module(mod)
            print(f'OK {pip}')
        except Exception:
            print(f'FALTA {pip} {tipo}')
PYEOF
    dbx "$PY" "$DESTINO/.verificar_libs.py"
    rm -f "$DESTINO/.verificar_libs.py"
}

if [ "$PIP" = 1 ]; then
    if [ -e "$DESTINO/venv" ] && ! dbx "$PY" -c "import sys" >/dev/null 2>&1; then
        echo "   ambiente virtual antigo/incompatível: recriando."
        rm -rf "$DESTINO/venv"
    fi
    [ -x "$PY" ] || dbx python3 -m venv "$DESTINO/venv" || die "falha ao criar o venv no container."
    dbx "$PIPB" install -q --upgrade pip
    instalar_pacotes
    RES="$(verificar_libs)"
    FALTAM="$(echo "$RES" | awk '$1=="FALTA"{print $2}')"
    if [ -n "$FALTAM" ]; then
        echo "   bibliotecas ausentes, tentando de novo: $(echo $FALTAM)"
        for pc in $FALTAM; do dbx "$PIPB" install -q "$pc" || true; done
        RES="$(verificar_libs)"
    fi
    echo "$RES" | awk '$1=="OK"{printf "   ok: %s\n",$2}'
    echo "$RES" | awk '$1=="FALTA" && $3=="critico"{printf "   ERRO: falta %s (o app pode não abrir)\n",$2}'
    echo "$RES" | awk '$1=="FALTA" && $3=="opcional"{printf "   AVISO: falta %s: os dados ficariam SEM cifra própria em disco\n",$2}'
else
    [ -x "$PY" ] || dbx python3 -m venv "$DESTINO/venv"
    echo "   (instalação de pacotes pulada)"
fi

# libtoxcore: a do container (libtoxcore2) ou, se não existir, uma cópia
# própria do app compilada AQUI dentro do container (o app procura
# libtoxcore.so.2 primeiro na própria pasta).
compilar_toxcore() {
    echo "   libtoxcore não encontrada: compilando uma cópia para o app (no container)..."
    dbx sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential cmake pkg-config curl \
        || die "não consegui instalar as ferramentas de compilação no container."
    cat > "$DESTINO/.compilar_tox.sh" <<'BEOF'
#!/bin/bash
set -e
DESTINO="$1"; SODIUM_URL="$2"; TOX_URL="$3"
B="$(mktemp -d)"; trap 'rm -rf "$B"' EXIT
mkdir -p "$B/sodium" "$B/tox"
curl -sSL --fail -o "$B/sodium.tgz" "$SODIUM_URL"
tar xzf "$B/sodium.tgz" -C "$B/sodium" --strip-components=1
( cd "$B/sodium" && ./configure --disable-shared --enable-static --with-pic --prefix="$B/out" >/dev/null 2>&1 \
    && make -j"$(nproc)" >/dev/null 2>&1 && make install >/dev/null 2>&1 )
curl -sSL --fail -o "$B/tox.tgz" "$TOX_URL"
tar xzf "$B/tox.tgz" -C "$B/tox" --strip-components=1
( cd "$B/tox" && mkdir b && cd b \
  && PKG_CONFIG_LIBDIR="$B/out/lib/pkgconfig" cmake .. -DCMAKE_BUILD_TYPE=Release \
       -DBUILD_TOXAV=OFF -DBOOTSTRAP_DAEMON=OFF -DUNITTEST=OFF -DAUTOTEST=OFF \
       -DENABLE_SHARED=ON -DENABLE_STATIC=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
       -DCMAKE_PREFIX_PATH="$B/out" >/dev/null 2>&1 \
  && PKG_CONFIG_LIBDIR="$B/out/lib/pkgconfig" cmake --build . --target toxcore_shared -j"$(nproc)" >/dev/null 2>&1 )
so="$(find "$B/tox/b" -name 'libtoxcore.so.*.*' -type f | head -n1)"
[ -n "$so" ]
cp "$so" "$DESTINO/libtoxcore.so.2"
BEOF
    dbx bash "$DESTINO/.compilar_tox.sh" "$DESTINO" "$SODIUM_URL" "$TOX_URL" \
        || { rm -f "$DESTINO/.compilar_tox.sh"; die "falha ao compilar a libtoxcore."; }
    rm -f "$DESTINO/.compilar_tox.sh"
    echo "   ok: $DESTINO/libtoxcore.so.2 (libsodium embutida)"
}
if ! tem_tox && [ ! -f "$DESTINO/libtoxcore.so.2" ]; then
    if [ "$APT" = 1 ]; then compilar_toxcore
    else aviso "libtoxcore não encontrada no container e --sem-apt foi usado."; fi
else
    echo "   libtoxcore ok."
fi

# ── 6. launcher, ícone e atalhos (só agora, com o container pronto) ───
passo "6/7" "launcher, atalho no menu (Escritório) e início automático"
mkdir -p "$APPS" "$ICONES"
if [ -f "$DESTINO/finance_icon.png" ]; then cp "$DESTINO/finance_icon.png" "$ICONES/$APP_ID.png"
elif [ -f "$DESTINO/make_icon.py" ]; then
    ( cd "$DESTINO" && dbx "$PY" make_icon.py && cp finance_icon.png "$ICONES/$APP_ID.png" ) || true
fi

# Launcher: inicia o container Debian (se parado) e roda o app dentro dele
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# $NOME - launcher (executa o app dentro do distrobox)
DESTINO="$DESTINO"
CONTAINER="$CONTAINER"
cd "\$DESTINO" || exit 1
mkdir -p "\$DESTINO/logs"
export XDG_RUNTIME_DIR="\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="\${DBUS_SESSION_BUS_ADDRESS:-unix:path=\$XDG_RUNTIME_DIR/bus}"
exec distrobox enter "\$CONTAINER" -- "\$DESTINO/venv/bin/python" "\$DESTINO/app.py" "\$@" \\
    >> "\$DESTINO/logs/launcher.log" 2>&1 </dev/null
EOF
chmod 755 "$LAUNCHER"

ENTRADA="[Desktop Entry]
Type=Application
Name=$NOME
Comment=Gestão financeira pessoal (container Debian)
Exec=\"$LAUNCHER\"
Path=$DESTINO
Icon=$APP_ID
Terminal=false
Categories=Office;Finance;
StartupWMClass=$APP_ID
"
printf '%s' "$ENTRADA" > "$APPS/$APP_ID.desktop"
chmod 755 "$APPS/$APP_ID.desktop"
echo "   atalho: $APPS/$APP_ID.desktop"

if [ "$AUTO" = 1 ]; then
    mkdir -p "$AUTOSTART"
    printf '%sX-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=10\n' "$ENTRADA" > "$AUTOSTART/$APP_ID.desktop"
    chmod 755 "$AUTOSTART/$APP_ID.desktop"
    echo "   autostart ativado. Para desativar: rm $AUTOSTART/$APP_ID.desktop"
else
    rm -f "$AUTOSTART/$APP_ID.desktop"; echo "   autostart desativado (--sem-autostart)"
fi
atualiza_caches

# ── 7. permissões e verificação ───────────────────────────────────────
passo "7/7" "permissões e verificação"
EU="$(id -un)"
chmod -R u+rwX "$DESTINO" 2>/dev/null || true
chmod 700 "$DESTINO/dados" "$DESTINO/logs" 2>/dev/null || true
find "$DESTINO/dados" "$DESTINO/logs" -type f -exec chmod 600 {} + 2>/dev/null || true
[ -f "$DESTINO/libtoxcore.so.2" ] && chmod 755 "$DESTINO/libtoxcore.so.2"
if [ -z "$(find "$DESTINO" ! -user "$EU" 2>/dev/null | head -n 1)" ]; then
    echo "   ok: todos os arquivos são do usuário $EU; dados e logs com acesso só seu (700)."
else
    aviso "há arquivos de outro dono em $DESTINO (sobra de execução antiga como root?)."
    aviso "peça ao administrador: chown -R $EU: $DESTINO"
fi
if [ "$PIP" = 1 ]; then
    ( cd "$DESTINO" && dbx env QT_QPA_PLATFORM=offscreen "$PY" app.py --autoteste ) || \
        echo "   (o autoteste apontou falhas acima: veja a mensagem e abra uma Issue se precisar)"
else
    echo "   (autoteste pulado)"
fi
echo
echo ">> PRONTO. Abra \"$NOME\" no menu de aplicativos (Escritório)."
echo ">> Container: $CONTAINER (distrobox)  |  Programa e dados: $DESTINO"
echo ">> Faça backup dos seus dados pelo próprio app (Rede/Conta > Exportar)."

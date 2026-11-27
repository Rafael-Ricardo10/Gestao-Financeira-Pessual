#!/usr/bin/env bash
# ======================================================================
#  Instalador do RRFS Finanças para Linux (usuário comum, sem root no app)
#
#  Instala em  ~/.local/share/Gastos_Pessoais/   (código, venv e dados)
#  Cria atalho no menu (categoria Escritório) e início automático.
#
#  Uso:  ./install.sh [--sem-autostart] [--sem-apt] [--sem-pip] [--su|--sudo]
#                     [--desinstalar]
#   --sem-autostart  não inicia junto com o sistema
#   --sem-apt        não instala pacotes do sistema (você cuida das dependências)
#   --su / --sudo    força como pedir privilégios (padrão: sudo se você puder
#                    usá-lo; senão "su", que pede a SENHA DO ROOT no terminal)
#   --sem-pip        não cria/atualiza o ambiente Python (uso em testes)
#   --desinstalar    remove atalho, início automático e programa
#                    (pergunta antes de apagar seus dados)
#
#  SEGURANÇA: o instalador roda SEMPRE como o seu usuário. Só os comandos de
#  sistema (instalar pacotes e a libtoxcore) rodam como administrador: eles
#  são mostrados na tela antes e a senha é digitada no próprio sudo/su (este
#  script nunca a lê nem a guarda). O programa e os dados ficam na SUA pasta.
#
#  Os dados (dados/) e logs (logs/) NUNCA são copiados do projeto nem
#  apagados em atualizações.
# ======================================================================
set -euo pipefail

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

AUTO=1; APT=1; PIP=1; REMOVER=0; FORCAR=""
for a in "$@"; do
    case "$a" in
        --sem-autostart) AUTO=0 ;;
        --sem-apt) APT=0 ;;
        --sem-pip) PIP=0 ;;
        --su) FORCAR=su ;;
        --sudo) FORCAR=sudo ;;
        --desinstalar) REMOVER=1 ;;
        -h|--help) sed -n 2,24p "$0"; exit 0 ;;
        *) echo "opção desconhecida: $a"; exit 1 ;;
    esac
done

die()   { echo; echo "ERRO: $*" >&2; exit 1; }
passo() { echo; echo "[$1] $2"; }

[ "$(uname -s)" = "Linux" ] || die "este instalador é para Linux."
[ "$(id -u)" -ne 0 ] || die "não rode como root nem com sudo: o app é instalado na pasta do SEU usuário. Rode como usuário comum; a senha de administrador é pedida só para instalar pacotes."

# ── desinstalar ───────────────────────────────────────────────────────
if [ "$REMOVER" = 1 ]; then
    rm -f "$APPS/$APP_ID.desktop" "$AUTOSTART/$APP_ID.desktop" "$ICONES/$APP_ID.png"
    if [ -d "$DESTINO/dados" ]; then
        read -r -p "Apagar também seus DADOS em $DESTINO/dados ? (digite APAGAR para confirmar): " r
        if [ "$r" = "APAGAR" ]; then rm -rf "$DESTINO"; echo "Tudo removido."
        else
            find "$DESTINO" -mindepth 1 -maxdepth 1 ! -name dados ! -name logs -exec rm -rf {} +
            echo "Programa removido. Dados mantidos em $DESTINO/dados"
        fi
    else rm -rf "$DESTINO"; echo "Programa removido."; fi
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
    exit 0
fi

[ -f "$QUADRO/app.py" ] || die "app.py não encontrado em $QUADRO (rode o instalador dentro da pasta do projeto)."
[ -d "$QUADRO/modulos" ] && [ -d "$QUADRO/interface" ] || die "pastas modulos/ e interface/ não encontradas."

# ── 1. dependências do sistema ────────────────────────────────────────
passo "1/6" "dependências do sistema"
PACOTES="python3 python3-venv python3-pip libsodium23 \
 libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
 libxcb-shape0 libxkbcommon-x11-0 libgl1 libegl1 libdbus-1-3 libglib2.0-0 libfontconfig1"
TMP="$(mktemp -d)"; chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT

# Como obter privilégios: sudo (se o usuário puder) ou su (senha do root).
MODO_ROOT=""
escolher_modo_root() {
    case "$FORCAR" in sudo|su) MODO_ROOT="$FORCAR"; return ;; esac
    if command -v sudo >/dev/null 2>&1 && \
       { sudo -n true 2>/dev/null || id -nG | tr ' ' '\n' | grep -qxE 'sudo|wheel|admin'; }; then
        MODO_ROOT=sudo
    elif command -v su >/dev/null 2>&1 && [ -t 0 ]; then
        MODO_ROOT=su
    else
        MODO_ROOT=nenhum
    fi
}

# Roda um arquivo de comandos como administrador. Mostra o conteúdo antes.
rodar_como_root() {
    local arq="$1"
    echo "   Comandos que serão executados como administrador:"
    sed 's/^/     | /' "$arq" | grep -v '^     | #!/\|^     | set -e\|^     | export '
    case "$MODO_ROOT" in
        sudo) echo "   (usando sudo: digite a SUA senha se o terminal pedir)"
              sudo bash "$arq" ;;
        su)   echo "   Você não tem sudo. Digite a senha do ROOT (administrador) quando o terminal pedir."
              su -c "bash '$arq'" ;;
        *)    return 2 ;;
    esac
}

instrucao_manual() {
    echo
    echo "   Não foi possível obter privilégios de administrador."
    echo "   Peça a quem administra o computador para rodar, como root, estes comandos:"
    echo
    sed 's/^/     /' "$1" | grep -v '^     #!/\|^     set -e\|^     export '
    echo
    echo "   Depois rode:  ./install.sh --sem-apt"
}

tem_tox() { ldconfig -p 2>/dev/null | grep -q 'libtoxcore\.so\.2'; }

if [ "$APT" = 1 ]; then
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "   apt-get não encontrado. Instale com o gerenciador da sua distribuição:"
        echo "   python3, venv, pip, libsodium, libtoxcore e as bibliotecas xcb/Qt:"
        echo "   ${PACOTES}"
    else
        escolher_modo_root
        # sem libtoxcore2 no apt, o app compila a sua cópia (sem root): só
        # precisa de gcc, make, curl e pkg-config
        CAND="$(apt-cache policy libtoxcore2 2>/dev/null | awk '/Candidate:/{print $2}')"
        EXTRA=""
        if [ -z "$CAND" ] || [ "$CAND" = "(none)" ]; then
            EXTRA="build-essential curl"
        fi
        {
            echo '#!/bin/bash'
            echo 'set -e'
            echo 'export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
            echo 'export DEBIAN_FRONTEND=noninteractive'
            echo "apt-get update 2>&1 | grep -E '^(E:|W:|Err)' || true"
            echo 'quebrado=0'
            echo "for p in $PACOTES libtoxcore2 $EXTRA; do"
            echo '    if ! out=$(apt-get install -y -qq "$p" 2>&1); then'
            echo '        echo "(nao instalado: $p)"'
            echo '        echo "$out" | grep -E "^(E:|dpkg:)" | head -n 3 | sed "s/^/      /"'
            echo '        case "$out" in *dpkg*) quebrado=1 ;; esac'
            echo '    fi'
            echo 'done'
            echo 'if [ "$quebrado" = 1 ]; then'
            echo '    echo "AVISO: o dpkg deste sistema esta com um pacote quebrado (nao e culpa do instalador)."'
            echo '    echo "Como root, rode:  dpkg --configure -a  &&  apt-get -f install   e depois ./install.sh"'
            echo 'fi'
        } > "$TMP/root1.sh"
        if ! rodar_como_root "$TMP/root1.sh"; then
            instrucao_manual "$TMP/root1.sh"
            echo "   Continuando sem instalar pacotes de sistema (pode falhar adiante)."
        fi
    fi
else
    echo "   (pulado)"
fi
command -v python3 >/dev/null || die "python3 não encontrado."

# ── 2. copiar o programa (nunca dados/ nem logs/) ─────────────────────
passo "2/6" "copiando para $DESTINO"
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

# ── 3. ambiente Python ────────────────────────────────────────────────
passo "3/6" "ambiente Python (venv) e libtoxcore"
# Lista base (usada se o projeto não tiver requirements.txt). Fica em sincronia
# com o requirements.txt do projeto.
REQ_BASE="PyQt5 matplotlib numpy python-dateutil yfinance pdfplumber requests psutil
cryptography keyring sqlcipher3-binary pandas werkzeug"

instalar_pacotes() {
    local pip="$DESTINO/venv/bin/pip" req="$DESTINO/requirements.txt"
    if [ -f "$req" ]; then
        "$pip" install -q -r "$req" && return 0
        echo "   a instalação em bloco falhou; tentando pacote por pacote..."
        grep -vE '^\s*(#|$)' "$req" | sed 's/#.*//' | while read -r linha; do
            [ -n "$linha" ] && { "$pip" install -q "$linha" || echo "   FALHOU: $linha"; }
        done
    else
        for pc in $REQ_BASE; do "$pip" install -q "$pc" || echo "   FALHOU: $pc"; done
    fi
}

# Confere se as bibliotecas que o código realmente importa estão no venv.
# Imprime "FALTA <pacote-pip> <critico|opcional>" para cada ausente.
verificar_libs() {
    "$PY" - <<'PYEOF'
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
}

if [ "$PIP" = 1 ]; then
    [ -d "$DESTINO/venv" ] || python3 -m venv "$DESTINO/venv" || die "falha ao criar o venv (instale python3-venv)."
    "$DESTINO/venv/bin/pip" install -q --upgrade pip
    PY="$DESTINO/venv/bin/python"
    instalar_pacotes
    RES="$(verificar_libs)"
    FALTAM="$(echo "$RES" | awk '$1=="FALTA"{print $2}')"
    if [ -n "$FALTAM" ]; then
        echo "   bibliotecas ausentes, tentando de novo: $(echo $FALTAM)"
        for pc in $FALTAM; do "$DESTINO/venv/bin/pip" install -q "$pc" || true; done
        RES="$(verificar_libs)"
    fi
    echo "$RES" | awk '$1=="OK"{printf "   ok: %s\n",$2}'
    echo "$RES" | awk '$1=="FALTA" && $3=="critico"{printf "   ERRO: falta %s (o app pode não abrir)\n",$2}'
    echo "$RES" | awk '$1=="FALTA" && $3=="opcional"{printf "   AVISO: falta %s: os dados ficariam SEM cifra própria em disco\n",$2}'
else
    [ -x "$DESTINO/venv/bin/python" ] || python3 -m venv "$DESTINO/venv"
    echo "   (instalação de pacotes pulada)"
fi
PY="$DESTINO/venv/bin/python"

# libtoxcore: a do sistema, ou uma cópia própria do app compilada AQUI, sem
# root (o app procura libtoxcore.so.2 primeiro na própria pasta).
compilar_toxcore_usuario() {
    echo "   libtoxcore não encontrada no sistema: compilando uma cópia para o app (sem root)..."
    local falta="" c
    for c in gcc make curl tar; do
        command -v "$c" >/dev/null 2>&1 || falta="$falta $c"
    done
    [ -z "$falta" ] || die "faltam ferramentas:$falta. Peça a um administrador: apt-get install build-essential curl pkg-config   (depois rode de novo)."
    local CM="cmake" PKGC="" B="$TMP/nativo" pacotes=""
    command -v cmake >/dev/null 2>&1 || pacotes="$pacotes cmake"
    command -v pkg-config >/dev/null 2>&1 || command -v pkgconf >/dev/null 2>&1 || pacotes="$pacotes pkgconf"
    if [ -n "$pacotes" ]; then      # ferramentas ausentes: vêm do pip, sem root
        echo "   obtendo pelo pip (sem root):$pacotes"
        python3 -m venv "$TMP/cm" || die "falha ao criar o venv temporário (instale python3-venv)."
        # shellcheck disable=SC2086
        "$TMP/cm/bin/pip" install -q $pacotes || die "não consegui obter$pacotes pelo pip (sem internet?)."
        [ -x "$TMP/cm/bin/cmake" ] && CM="$TMP/cm/bin/cmake"
        [ -x "$TMP/cm/bin/pkg-config" ] && PKGC="-DPKG_CONFIG_EXECUTABLE=$TMP/cm/bin/pkg-config"
    fi
    mkdir -p "$B/sodium" "$B/tox"
    curl -sSL --fail -o "$B/sodium.tgz" "$SODIUM_URL" || die "falha ao baixar a libsodium."
    tar xzf "$B/sodium.tgz" -C "$B/sodium" --strip-components=1
    ( cd "$B/sodium" && ./configure --disable-shared --enable-static --with-pic \
          --prefix="$B/out" >/dev/null 2>&1 && make -j"$(nproc)" >/dev/null 2>&1 && make install >/dev/null 2>&1 ) \
        || die "falha ao compilar a libsodium."
    curl -sSL --fail -o "$B/tox.tgz" "$TOX_URL" || die "falha ao baixar a c-toxcore."
    tar xzf "$B/tox.tgz" -C "$B/tox" --strip-components=1
    ( cd "$B/tox" && mkdir b && cd b \
      && PATH="$TMP/cm/bin:$PATH" PKG_CONFIG_LIBDIR="$B/out/lib/pkgconfig" "$CM" .. $PKGC -DCMAKE_BUILD_TYPE=Release \
           -DBUILD_TOXAV=OFF -DBOOTSTRAP_DAEMON=OFF -DUNITTEST=OFF -DAUTOTEST=OFF \
           -DENABLE_SHARED=ON -DENABLE_STATIC=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
           -DCMAKE_PREFIX_PATH="$B/out" >/dev/null 2>&1 \
      && PATH="$TMP/cm/bin:$PATH" PKG_CONFIG_LIBDIR="$B/out/lib/pkgconfig" "$CM" --build . --target toxcore_shared \
           -j"$(nproc)" >/dev/null 2>&1 ) || die "falha ao compilar a libtoxcore."
    local so; so="$(find "$B/tox/b" -name 'libtoxcore.so.*.*' -type f | head -n1)"
    [ -n "$so" ] || die "a libtoxcore compilada não foi encontrada."
    cp "$so" "$DESTINO/libtoxcore.so.2"
    echo "   ok: $DESTINO/libtoxcore.so.2 (libsodium embutida)"
}
if ! tem_tox && [ ! -f "$DESTINO/libtoxcore.so.2" ]; then
    compilar_toxcore_usuario
fi

# ── 4. ícone e atalho ─────────────────────────────────────────────────
passo "4/6" "atalho no menu (Escritório)"
mkdir -p "$APPS" "$ICONES"
if [ -f "$DESTINO/finance_icon.png" ]; then cp "$DESTINO/finance_icon.png" "$ICONES/$APP_ID.png"
elif [ -f "$DESTINO/make_icon.py" ]; then ( cd "$DESTINO" && "$PY" make_icon.py && cp finance_icon.png "$ICONES/$APP_ID.png" ) || true; fi

# Mesmo conteúdo que o app grava sozinho ao abrir, para não haver briga.
ENTRADA="[Desktop Entry]
Type=Application
Name=$NOME
Comment=Gestão financeira pessoal
Exec=\"$PY\" \"$DESTINO/app.py\"
Path=$DESTINO
Icon=$APP_ID
Terminal=false
Categories=Office;Finance;
StartupWMClass=$APP_ID
"
printf '%s' "$ENTRADA" > "$APPS/$APP_ID.desktop"
chmod 755 "$APPS/$APP_ID.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true

# ── 5. início automático ──────────────────────────────────────────────
passo "5/6" "início automático com o sistema"
if [ "$AUTO" = 1 ]; then
    mkdir -p "$AUTOSTART"
    printf '%sX-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=10\n' "$ENTRADA" > "$AUTOSTART/$APP_ID.desktop"
    chmod 755 "$AUTOSTART/$APP_ID.desktop"
    echo "   ativado (inicia minimizado na bandeja). Para desativar: rm $AUTOSTART/$APP_ID.desktop"
else
    rm -f "$AUTOSTART/$APP_ID.desktop"; echo "   desativado (--sem-autostart)"
fi

# ── 6. permissões e verificação ───────────────────────────────────────
passo "6/6" "permissões e verificação"
EU="$(id -un)"; MEU_GRUPO="$(id -gn)"
# 6a) tudo na pasta do app precisa ser do SEU usuário (sobra de uma execução
#     antiga como root, por exemplo). Só se houver, pede privilégio para corrigir.
ESTRANHOS="$(find "$DESTINO" ! -user "$EU" 2>/dev/null | head -n 1)"
if [ -n "$ESTRANHOS" ]; then
    echo "   há arquivos de outro dono em $DESTINO (ex.: $ESTRANHOS): corrigindo..."
    printf '#!/bin/bash\nchown -R %s:%s "%s"\n' "$EU" "$MEU_GRUPO" "$DESTINO" > "$TMP/root3.sh"
    [ -n "$MODO_ROOT" ] || escolher_modo_root
    rodar_como_root "$TMP/root3.sh" || instrucao_manual "$TMP/root3.sh"
fi
# 6b) modos: dono lê/escreve; dados e logs só do dono; executáveis onde precisa
chmod -R u+rwX "$DESTINO" 2>/dev/null || true
chmod 700 "$DESTINO/dados" "$DESTINO/logs" 2>/dev/null || true
find "$DESTINO/dados" "$DESTINO/logs" -type f -exec chmod 600 {} + 2>/dev/null || true
[ -f "$DESTINO/libtoxcore.so.2" ] && chmod 755 "$DESTINO/libtoxcore.so.2"
chmod 755 "$APPS/$APP_ID.desktop" 2>/dev/null || true
[ -f "$AUTOSTART/$APP_ID.desktop" ] && chmod 755 "$AUTOSTART/$APP_ID.desktop"
if [ -z "$(find "$DESTINO" ! -user "$EU" 2>/dev/null | head -n 1)" ]; then
    echo "   ok: todos os arquivos são do usuário $EU; dados e logs com acesso só seu (700)."
else
    echo "   AVISO: ainda há arquivos de outro dono em $DESTINO."
fi
# 6c) autoteste do próprio app
if [ "$PIP" = 1 ]; then
    ( cd "$DESTINO" && QT_QPA_PLATFORM=offscreen "$PY" app.py --autoteste ) || \
        echo "   (o autoteste apontou falhas acima: veja a mensagem e abra uma Issue se precisar)"
else
    echo "   (autoteste pulado)"
fi
echo
echo ">> PRONTO. Abra \"$NOME\" no menu de aplicativos (Escritório)."
echo ">> Programa e dados: $DESTINO"
echo ">> Faça backup dos seus dados pelo próprio app (Rede/Conta > Exportar)."

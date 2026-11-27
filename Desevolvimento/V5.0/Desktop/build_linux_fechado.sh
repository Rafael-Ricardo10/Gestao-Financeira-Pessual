#!/usr/bin/env bash
# Binário Linux com o código COMPILADO em C (Nuitka): não há .pyc para extrair.
# Demora (de minutos a horas, conforme a CPU). Requisitos: python3.12, gcc,
# patchelf, cmake, libsodium-dev, binutils (objdump/readelf). Funciona dentro
# ou fora de venv.
set -e
cd "$(dirname "$0")"

# ── localizar o ldconfig (em alguns venvs/distros o PATH não inclui /sbin) ──
LDCONFIG=""
for c in ldconfig /sbin/ldconfig /usr/sbin/ldconfig /usr/bin/ldconfig; do
    command -v "$c" >/dev/null 2>&1 && LDCONFIG="$(command -v "$c")" && break
done
[ -z "$LDCONFIG" ] && echo ">> aviso: ldconfig não encontrado; usando busca alternativa (find)."

# acha um arquivo pelo NOME EXATO (sem pegar outra versão por engano)
achar_exato() {
    local nome="$1" r=""
    if [ -n "$LDCONFIG" ]; then
        r=$("$LDCONFIG" -p 2>/dev/null | grep -F " $nome " | awk '{print $NF}' | head -n1)
    fi
    if [ -z "$r" ]; then
        r=$(find /usr/lib /usr/local/lib /lib -xdev -name "$nome" 2>/dev/null | head -n1)
    fi
    echo "$r"
}

# acha a biblioteca mais recente por PREFIXO (quando não se sabe a versão)
achar_prefixo() {
    local prefixo="$1" r=""
    if [ -n "$LDCONFIG" ]; then
        r=$("$LDCONFIG" -p 2>/dev/null | grep -F " $prefixo" | awk '{print $NF}' | sort -V | tail -n1)
    fi
    if [ -z "$r" ]; then
        r=$(find /usr/lib /usr/local/lib /lib -xdev -name "${prefixo}*" 2>/dev/null | sort -V | tail -n1)
    fi
    echo "$r"
}

# nome exato (SONAME) que um .so precisa de outra lib, ex.: "libsodium.so.23"
soname_exigido() {
    # $1 = caminho do .so ; $2 = prefixo SIMPLES (ex.: "libsodium.so.") sem escapes
    local arquivo="$1" prefixo="$2"
    if command -v objdump >/dev/null 2>&1; then
        objdump -p "$arquivo" 2>/dev/null | awk '/NEEDED/{print $2}' | grep -F "$prefixo" | head -n1
    elif command -v readelf >/dev/null 2>&1; then
        local re
        re=$(printf '%s' "$prefixo" | sed 's/\./\\./g')   # escapa os pontos p/ regex
        readelf -d "$arquivo" 2>/dev/null | grep NEEDED | grep -oE "${re}[0-9.]*" | head -n1
    fi
}

# ── dependências Python (--break-system-packages só fora de venv) ──
PIP_FLAGS=""
[ -z "$VIRTUAL_ENV" ] && PIP_FLAGS="--break-system-packages"
python3 -m pip install -q $PIP_FLAGS nuitka ordered-set zstandard PyQt5 \
    sqlcipher3-binary psutil keyring cryptography yfinance matplotlib \
    numpy pandas pdfplumber requests werkzeug

[ -f finance_icon.png ] || python3 make_icon.py

# ── libtoxcore ───────────────────────────────────────────────────────
LIB=$(achar_prefixo "libtoxcore.so.2")
if [ -z "$LIB" ]; then
    echo ">> libtoxcore não encontrada: compilando a partir do código-fonte..."
    command -v cmake >/dev/null 2>&1 || {
        echo "Instale primeiro: sudo apt install cmake libsodium-dev build-essential binutils"
        exit 1; }
    T=$(mktemp -d); D=$(pwd); cd "$T"
    curl -sSL -o t.tgz https://github.com/TokTok/c-toxcore/releases/download/v0.2.20/c-toxcore-0.2.20.tar.gz
    tar xzf t.tgz; cd c-toxcore-*; mkdir b; cd b
    cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TOXAV=OFF -DBOOTSTRAP_DAEMON=OFF \
          -DUNITTEST=OFF -DAUTOTEST=OFF >/dev/null
    make -j"$(nproc)" >/dev/null
    sudo make install >/dev/null
    [ -n "$LDCONFIG" ] && sudo "$LDCONFIG"
    cd "$D"
    LIB=$(achar_prefixo "libtoxcore.so.2")
    [ -z "$LIB" ] && LIB=$(find /usr/local/lib -name "libtoxcore.so.2*" 2>/dev/null | sort -V | tail -n1)
fi
[ -z "$LIB" ] && { echo "ERRO: não achei libtoxcore.so.2."; exit 1; }
LIB=$(readlink -f "$LIB")
echo ">> libtoxcore: $LIB"

# ── libsodium: usa exatamente o SONAME que a libtoxcore pede ───────────
SONAME=$(soname_exigido "$LIB" "libsodium.so.")
if [ -z "$SONAME" ]; then
    echo ">> aviso: não consegui ler o SONAME exigido (sem objdump/readelf);"
    echo "          assumindo libsodium.so.23 (o mais comum)."
    SONAME="libsodium.so.23"
fi
SODIUM=$(achar_exato "$SONAME")
[ -z "$SODIUM" ] && SODIUM=$(achar_prefixo "libsodium.so")
if [ -z "$SODIUM" ]; then
    echo "ERRO: não achei $SONAME (instale: sudo apt install libsodium23 libsodium-dev)."
    exit 1
fi
SODIUM=$(readlink -f "$SODIUM")
echo ">> libsodium ($SONAME): $SODIUM"

cp "$LIB" ./libtoxcore.so.2
cp "$SODIUM" "./$SONAME"

python3 -m nuitka --onefile --assume-yes-for-downloads --output-dir=dist-nuitka \
  --output-filename=RRFS-Financas-nuitka --enable-plugin=pyqt5 \
  --enable-plugin=matplotlib \
  --include-package=interface --include-package=modulos --include-package=sqlcipher3 \
  --include-package=keyring --include-package=secretstorage --include-package=jeepney \
  --include-package=yfinance --include-package=curl_cffi --include-package=pdfplumber \
  --include-package=pdfminer --include-package=psutil --include-module=cryptography \
  --include-data-files=finance_icon.png=finance_icon.png \
  --include-data-files=libtoxcore.so.2=libtoxcore.so.2 \
  --include-data-files="$SONAME=$SONAME" \
  --nofollow-import-to=tkinter --nofollow-import-to=IPython --nofollow-import-to=PyQt5.QtWebEngine \
  --jobs="$(nproc)" app.py

rm -f ./libtoxcore.so.2 "./$SONAME"
echo
echo ">> PRONTO. O binário ficou em:"
echo ">>   $(pwd)/dist-nuitka/RRFS-Financas-nuitka"
echo ">> Teste com:"
echo ">>   ./dist-nuitka/RRFS-Financas-nuitka --autoteste"

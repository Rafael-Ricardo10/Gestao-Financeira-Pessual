#!/usr/bin/env bash
# ======================================================================
#  Gera o APK do RRFS Finanças (Android) com Buildozer / python-for-android.
#
#  Rode no LINUX (Ubuntu/Debian 22.04+ ou WSL2), na pasta do projeto, que
#  deve conter:  modulos/   mobile/main.py   mobile/plataforma.py
#                finance_icon.png (opcional)
#
#  Uso:
#    ./build_android.sh --sem-sqlcipher     APK de TESTE (banco sem cifra
#                                           própria; veja o aviso abaixo)
#    ./build_android.sh                     APK com SQLCipher (exige a pasta
#                                           android-recipes/sqlcipher3/)
#    opções:  --release      APK assinado (pede/gera a chave de assinatura)
#             --emulador     inclui x86_64 (para o emulador do Android Studio)
#             --so-preparar  só monta a pasta de build e o buildozer.spec
#             --sem-apt      não instala pacotes do sistema
#             --limpar       apaga build-android/ antes
#
#  ESTADO DESTE SCRIPT (seja transparente):
#   * VALIDADO no Linux comum: libsodium estática + libtoxcore compilam com
#     as opções usadas aqui, a libtoxcore fica sem dependência de libsodium,
#     o soname é corrigido e a biblioteca carrega e responde via ctypes.
#   * NÃO TESTADO: o cross-compile com o NDK do Android, o Buildozer e a
#     execução num celular (o autor não tinha NDK/SDK nem aparelho). Se algo
#     falhar, o log completo fica em build-android/build.log.
#   * SQLCipher no Android exige uma "receita" do python-for-android que não
#     existe pronta. Sem ela, use --sem-sqlcipher: o app funciona, mas os
#     dados ficam só no armazenamento privado do app (protegido pelo
#     Android, sem a cifra AES-256 própria) e o app AVISA isso ao usuário.
#   * iPhone: não dá para gerar daqui (exige um Mac com Xcode).
#   * O APK contém código Python (compilado em bytecode, mas recuperável).
#     No celular a proteção real vem da criptografia, não do código fechado.
# ======================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")" && pwd)"
BUILD="$RAIZ/build-android"
LIBS="$BUILD/libs"
SAIDA="$RAIZ/dist-android"
VERSAO_APP="1.0.0"
NDK_VERSAO="25b"
NDK_URL="https://dl.google.com/android/repository/android-ndk-r${NDK_VERSAO}-linux.zip"
SODIUM_URL="https://github.com/jedisct1/libsodium/releases/download/1.0.19-RELEASE/libsodium-1.0.19.tar.gz"
TOX_URL="https://github.com/TokTok/c-toxcore/releases/download/v0.2.20/c-toxcore-0.2.20.tar.gz"
API_NATIVA=24               # API usada ao compilar as bibliotecas nativas
P4A_TAG="v2024.01.21"

SEM_SQLCIPHER=0; RELEASE=0; EMULADOR=0; SO_PREPARAR=0; SEM_APT=0; LIMPAR=0
for a in "$@"; do
    case "$a" in
        --sem-sqlcipher) SEM_SQLCIPHER=1 ;;
        --release)       RELEASE=1 ;;
        --emulador)      EMULADOR=1 ;;
        --so-preparar)   SO_PREPARAR=1 ;;
        --sem-apt)       SEM_APT=1 ;;
        --limpar)        LIMPAR=1 ;;
        -h|--help)       sed -n 2,40p "$0"; exit 0 ;;
        *) echo "opção desconhecida: $a"; exit 1 ;;
    esac
done

ABIS="arm64-v8a armeabi-v7a"
[ "$EMULADOR" = 1 ] && ABIS="$ABIS x86_64"

die() { echo; echo "ERRO: $*" >&2; exit 1; }
passo() { echo; echo "[$1] $2"; }

# ── verificações iniciais ──────────────────────────────────────────────
[ "$(uname -s)" = "Linux" ] || die "rode no Linux (ou WSL2 no Windows)."
[ -d "$RAIZ/modulos" ] || die "pasta modulos/ não encontrada em $RAIZ"
[ -f "$RAIZ/mobile/main.py" ] || die "mobile/main.py não encontrado"
[ -f "$RAIZ/mobile/plataforma.py" ] || die "mobile/plataforma.py não encontrado"

if [ "$SEM_SQLCIPHER" = 0 ] && [ ! -f "$RAIZ/android-recipes/sqlcipher3/__init__.py" ]; then
    echo "O build com SQLCipher precisa de uma receita do python-for-android em"
    echo "  android-recipes/sqlcipher3/__init__.py"
    echo "que ainda não existe. Opções:"
    echo "  1) ./build_android.sh --sem-sqlcipher   (APK de teste agora; o banco"
    echo "     fica só no armazenamento privado do app, SEM cifra própria)"
    echo "  2) criar a receita (peça ajuda enviando o log do build)."
    exit 1
fi
if [ "$SEM_SQLCIPHER" = 1 ]; then
    echo ">> ATENÇÃO: build SEM SQLCipher. O app mostra um aviso ao usuário."
fi

PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
case "$PYV" in
    3.9|3.10|3.11|3.12) ;;
    *) echo ">> aviso: Python $PYV no sistema; o Buildozer é mais estável com 3.10-3.12." ;;
esac

[ "$LIMPAR" = 1 ] && rm -rf "$BUILD"
mkdir -p "$BUILD" "$LIBS" "$SAIDA"
exec > >(tee -a "$BUILD/build.log") 2>&1

# ── 1. pacotes do sistema ─────────────────────────────────────────────
passo "1/8" "pacotes do sistema"
if [ "$SEM_APT" = 0 ] && [ "$SO_PREPARAR" = 0 ]; then
    command -v apt-get >/dev/null || die "apt-get não encontrado (use --sem-apt e instale à mão)."
    sudo apt-get update -qq
    sudo apt-get install -y -qq git zip unzip openjdk-17-jdk autoconf automake \
        libtool libtool-bin pkg-config zlib1g-dev libncurses-dev cmake \
        libffi-dev libssl-dev build-essential ccache patchelf curl \
        python3-venv python3-pip
else
    echo "   (pulado)"
fi

# ── 2. staging do app (testável sem baixar nada) ──────────────────────
passo "2/8" "montando a pasta do app"
APP="$BUILD/app"
rm -rf "$APP"; mkdir -p "$APP"
cp -r "$RAIZ/modulos" "$APP/modulos"
cp "$RAIZ/mobile/main.py" "$RAIZ/mobile/plataforma.py" "$APP/"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +
[ -f "$RAIZ/finance_icon.png" ] && cp "$RAIZ/finance_icon.png" "$APP/"
printf 'SEM_SQLCIPHER = %s\n' "$([ "$SEM_SQLCIPHER" = 1 ] && echo True || echo False)" > "$APP/config_build.py"

REQ="python3,kivy==2.3.0,pyjnius,android,androidstorage4kivy,cryptography,openssl,psutil"
[ "$SEM_SQLCIPHER" = 0 ] && REQ="$REQ,sqlcipher3"
LOCAL_RECIPES=""
if [ "$SEM_SQLCIPHER" = 0 ]; then
    mkdir -p "$BUILD/recipes"; rm -rf "$BUILD/recipes/sqlcipher3"
    cp -r "$RAIZ/android-recipes/sqlcipher3" "$BUILD/recipes/sqlcipher3"
    LOCAL_RECIPES="p4a.local_recipes = $BUILD/recipes"
fi

ICONE_LINHA=""
[ -f "$APP/finance_icon.png" ] && ICONE_LINHA="icon.filename = %(source.dir)s/finance_icon.png"

ARCHS_LINHA=$(echo "$ABIS" | sed 's/ /, /g')
LIBS_LINHAS=""
for abi in $ABIS; do
    chave=$(echo "$abi" | tr '-' '_')
    LIBS_LINHAS="${LIBS_LINHAS}android.add_libs_${chave} = libs/${abi}/*.so
"
done

# Permissões: SÓ as de rede. Não há permissão de armazenamento: o app usa o
# seletor de arquivos do sistema (Storage Access Framework) e grava backups em
# Downloads pelo MediaStore, o que dispensa READ/WRITE_EXTERNAL_STORAGE.
# minapi 29 (Android 10+) torna isso verdadeiro em todos os aparelhos aceitos.
cat > "$BUILD/buildozer.spec" <<EOF
[app]
title = RRFS Finanças
package.name = rrfsfinancas
package.domain = org.rrfs
source.dir = app
source.include_exts = py,png,kv,json
version = $VERSAO_APP
requirements = $REQ
orientation = portrait
fullscreen = 0
$ICONE_LINHA
android.archs = $ARCHS_LINHA
android.api = 34
android.minapi = 29
android.ndk = $NDK_VERSAO
android.ndk_path = $BUILD/ndk/android-ndk-r$NDK_VERSAO
android.accept_sdk_license = True
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE, CHANGE_WIFI_MULTICAST_STATE
android.allow_backup = False
android.enable_androidx = True
android.gradle_dependencies = androidx.core:core:1.6.0
android.release_artifact = apk
${LIBS_LINHAS}p4a.branch = $P4A_TAG
$LOCAL_RECIPES

[buildozer]
log_level = 2
warn_on_root = 1
EOF
echo "   app: $APP"
echo "   spec: $BUILD/buildozer.spec"

if [ "$SO_PREPARAR" = 1 ]; then
    echo; echo ">> --so-preparar: pronto. Revise build-android/buildozer.spec."
    exit 0
fi

# ── 3. NDK ────────────────────────────────────────────────────────────
passo "3/8" "NDK r$NDK_VERSAO"
NDK="$BUILD/ndk/android-ndk-r$NDK_VERSAO"
if [ ! -d "$NDK" ]; then
    mkdir -p "$BUILD/ndk"
    curl -L --fail -o "$BUILD/ndk.zip" "$NDK_URL" || die "não consegui baixar o NDK ($NDK_URL)"
    unzip -q "$BUILD/ndk.zip" -d "$BUILD/ndk"; rm -f "$BUILD/ndk.zip"
fi
TC="$NDK/toolchains/llvm/prebuilt/linux-x86_64"
[ -d "$TC" ] || die "toolchain do NDK não encontrada em $TC"

# ── 4-5. bibliotecas nativas por ABI ──────────────────────────────────
baixar_fontes() {
    mkdir -p "$BUILD/src/sodium" "$BUILD/src/tox"
    if [ ! -f "$BUILD/src/sodium/configure" ]; then
        curl -L --fail -o "$BUILD/sodium.tgz" "$SODIUM_URL" || die "falha ao baixar libsodium"
        tar xzf "$BUILD/sodium.tgz" -C "$BUILD/src/sodium" --strip-components=1
    fi
    if [ ! -f "$BUILD/src/tox/CMakeLists.txt" ]; then
        curl -L --fail -o "$BUILD/tox.tgz" "$TOX_URL" || die "falha ao baixar c-toxcore"
        tar xzf "$BUILD/tox.tgz" -C "$BUILD/src/tox" --strip-components=1
    fi
}

compilar_abi() {
    local abi="$1" triple host clang
    case "$abi" in
        arm64-v8a)   triple="aarch64-linux-android";   host="aarch64-linux-android";  clang="aarch64-linux-android${API_NATIVA}-clang" ;;
        armeabi-v7a) triple="arm-linux-androideabi";   host="arm-linux-androideabi";  clang="armv7a-linux-androideabi${API_NATIVA}-clang" ;;
        x86_64)      triple="x86_64-linux-android";    host="x86_64-linux-android";   clang="x86_64-linux-android${API_NATIVA}-clang" ;;
        *) die "ABI desconhecida: $abi" ;;
    esac
    local pref="$BUILD/native/$abi"
    mkdir -p "$pref" "$LIBS/$abi"

    echo "   [$abi] libsodium (estática, PIC)"
    rm -rf "$BUILD/obj-sodium-$abi"; cp -r "$BUILD/src/sodium" "$BUILD/obj-sodium-$abi"
    ( cd "$BUILD/obj-sodium-$abi"
      export CC="$TC/bin/$clang" AR="$TC/bin/llvm-ar" RANLIB="$TC/bin/llvm-ranlib" \
             STRIP="$TC/bin/llvm-strip" LD="$TC/bin/ld"
      ./configure --host="$host" --disable-shared --enable-static --with-pic \
          --prefix="$pref" >/dev/null
      make -j"$(nproc)" >/dev/null
      make install >/dev/null )

    echo "   [$abi] libtoxcore (compartilhada, libsodium embutida)"
    rm -rf "$BUILD/obj-tox-$abi"; mkdir -p "$BUILD/obj-tox-$abi"
    ( cd "$BUILD/obj-tox-$abi"
      export PKG_CONFIG_LIBDIR="$pref/lib/pkgconfig" PKG_CONFIG_PATH=""
      cmake "$BUILD/src/tox" \
          -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
          -DANDROID_ABI="$abi" -DANDROID_PLATFORM="android-$API_NATIVA" \
          -DCMAKE_BUILD_TYPE=Release \
          -DBUILD_TOXAV=OFF -DBOOTSTRAP_DAEMON=OFF -DUNITTEST=OFF -DAUTOTEST=OFF \
          -DENABLE_SHARED=ON -DENABLE_STATIC=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
          -DCMAKE_PREFIX_PATH="$pref" -DCMAKE_FIND_ROOT_PATH="$pref" \
          -DCMAKE_C_FLAGS="-I$pref/include -fPIC" \
          -DCMAKE_SHARED_LINKER_FLAGS="-L$pref/lib" >/dev/null
      cmake --build . --target toxcore_shared -j"$(nproc)" >/dev/null )

    local so; so=$(find "$BUILD/obj-tox-$abi" -name 'libtoxcore.so.*.*' -type f | head -n1)
    [ -n "$so" ] || die "[$abi] libtoxcore.so não foi gerada"
    cp "$so" "$LIBS/$abi/libtoxcore.so"
    # o Android só aceita nomes terminados em .so: tira a versão do soname
    patchelf --set-soname libtoxcore.so "$LIBS/$abi/libtoxcore.so"
    "$TC/bin/llvm-strip" --strip-unneeded "$LIBS/$abi/libtoxcore.so" || true
    if "$TC/bin/llvm-readelf" -d "$LIBS/$abi/libtoxcore.so" | grep -q 'libsodium'; then
        die "[$abi] a libtoxcore ainda depende de libsodium.so (ficaria sem a lib no APK)."
    fi
    echo "   [$abi] ok: $LIBS/$abi/libtoxcore.so"
}

passo "4/8" "baixando fontes (libsodium, c-toxcore)"
baixar_fontes
passo "5/8" "compilando bibliotecas nativas: $ABIS"
for abi in $ABIS; do compilar_abi "$abi"; done

# ── 6. Rust (a 'cryptography' do python-for-android precisa) ──────────
passo "6/8" "Rust (necessário para compilar a cryptography)"
if ! command -v rustup >/dev/null 2>&1; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
fi
# shellcheck disable=SC1091
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
for abi in $ABIS; do
    case "$abi" in
        arm64-v8a)   rustup target add aarch64-linux-android ;;
        armeabi-v7a) rustup target add armv7-linux-androideabi ;;
        x86_64)      rustup target add x86_64-linux-android ;;
    esac
done

# ── 7. Buildozer ──────────────────────────────────────────────────────
passo "7/8" "Buildozer (a 1ª vez baixa o SDK e leva bastante tempo)"
if [ ! -d "$BUILD/venv" ]; then python3 -m venv "$BUILD/venv"; fi
# shellcheck disable=SC1091
. "$BUILD/venv/bin/activate"
pip install -q --upgrade pip wheel setuptools
pip install -q "buildozer==1.5.0" "cython==0.29.37" virtualenv

MODO=debug
if [ "$RELEASE" = 1 ]; then
    MODO=release
    KS="$RAIZ/rrfs-release.keystore"
    if [ ! -f "$KS" ]; then
        echo ">> Criando a chave de assinatura (UMA vez). GUARDE o arquivo e as"
        echo ">> senhas: sem elas você nunca mais poderá atualizar o app."
        keytool -genkey -v -keystore "$KS" -alias rrfs -keyalg RSA -keysize 4096 -validity 10000
    fi
    read -r -s -p "Senha da keystore: " KSPW; echo
    export P4A_RELEASE_KEYSTORE="$KS" P4A_RELEASE_KEYALIAS="rrfs" \
           P4A_RELEASE_KEYSTORE_PASSWD="$KSPW" P4A_RELEASE_KEYALIAS_PASSWD="$KSPW"
fi

( cd "$BUILD" && buildozer -v android "$MODO" ) || die "o Buildozer falhou. Veja $BUILD/build.log"

# ── 8. resultado ──────────────────────────────────────────────────────
passo "8/8" "resultado"
APK=$(ls -t "$BUILD"/bin/*.apk 2>/dev/null | head -n1 || true)
[ -n "$APK" ] || die "nenhum APK encontrado em $BUILD/bin"
SUFIXO="$MODO"; [ "$SEM_SQLCIPHER" = 1 ] && SUFIXO="$SUFIXO-sem-sqlcipher"
DEST="$SAIDA/RRFS-Financas-$VERSAO_APP-$SUFIXO.apk"
cp "$APK" "$DEST"
echo
echo ">> PRONTO: $DEST"
echo ">> Instalar no celular (modo desenvolvedor + depuração USB):"
echo ">>   adb install -r \"$DEST\""
echo ">> Depois abra o app > Conta > Diagnóstico e veja o que ficou OK/FALHA."

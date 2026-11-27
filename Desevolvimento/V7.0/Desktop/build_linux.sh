#!/usr/bin/env bash
# Gera UM arquivo executável (dist/RRFS-Financas) com Python, Qt, SQLCipher e
# libtoxcore dentro. 'dados/' e 'logs/' ficam AO LADO do executável.
# Requisitos (Debian/Ubuntu): python3-pip, cmake, libsodium-dev, build-essential
set -e
cd "$(dirname "$0")"
pip install --break-system-packages -q pyinstaller PyQt5 sqlcipher3-binary psutil keyring \
    cryptography yfinance matplotlib numpy pandas pdfplumber requests werkzeug 2>&1 | tail -1

# libtoxcore: usa a do sistema se existir, senão compila
LIB=$(ldconfig -p | awk '/libtoxcore\.so\.2 /{print $NF; exit}')
if [ -z "$LIB" ]; then
  echo ">> compilando libtoxcore..."
  T=$(mktemp -d); cd "$T"
  curl -sSL -o t.tgz https://github.com/TokTok/c-toxcore/releases/download/v0.2.20/c-toxcore-0.2.20.tar.gz
  tar xzf t.tgz; cd c-toxcore-*; mkdir b; cd b
  cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TOXAV=OFF -DBOOTSTRAP_DAEMON=OFF \
        -DUNITTEST=OFF -DAUTOTEST=OFF -DBUILD_FUN_UTILS=OFF >/dev/null
  make -j"$(nproc)" >/dev/null && sudo make install >/dev/null && sudo ldconfig
  cd - >/dev/null; cd "$(dirname "$0")"
  LIB=$(ldconfig -p | awk '/libtoxcore\.so\.2 /{print $NF; exit}')
fi
SODIUM=$(ldconfig -p | awk '/libsodium\.so\.[0-9]+ /{print $NF; exit}')
echo ">> libtoxcore: $LIB | libsodium: $SODIUM"

[ -f finance_icon.png ] || python3 make_icon.py
cp "$LIB" libtoxcore.so.2; cp "$SODIUM" "$(basename "$SODIUM")"

pyinstaller --noconfirm --clean --onefile --name RRFS-Financas \
  --add-data "finance_icon.png:." \
  --add-binary "libtoxcore.so.2:." --add-binary "$(basename "$SODIUM"):." \
  --hidden-import sqlcipher3.dbapi2 --hidden-import keyring.backends.SecretService \
  --hidden-import keyring.backends.libsecret --hidden-import secretstorage --hidden-import jeepney \
  --hidden-import psutil \
  --collect-submodules interface --collect-submodules modulos \
  --collect-all yfinance --collect-all curl_cffi --collect-all pdfplumber --collect-all pdfminer \
  --exclude-module tkinter --exclude-module PyQt5.QtWebEngine --exclude-module PyQt5.QtWebEngineWidgets \
  --exclude-module PyQt5.QtQml --exclude-module PyQt5.QtQuick --exclude-module IPython \
  app.py
rm -f libtoxcore.so.2 libsodium.so.*
echo ">> pronto: dist/RRFS-Financas"; ls -lh dist/RRFS-Financas

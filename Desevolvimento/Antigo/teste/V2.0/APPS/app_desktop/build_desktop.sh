#!/bin/bash
# ================================================
# Compila o app desktop para Linux/Windows/Mac
# Uso: ./build_desktop.sh [linux|windows|mac]
# ================================================

PLATAFORMA=${1:-linux}
NOME="RRFS_Financeiro"

echo "================================================"
echo "  RRFS - Compilando para: $PLATAFORMA"
echo "================================================"

# Instala dependências
pip install -r requirements_desktop.txt
pip install pyinstaller

# Baixa binários do Tor
echo "[*] Preparando binários do Tor..."
mkdir -p assets/tor/linux_x64
mkdir -p assets/tor/windows_x64
mkdir -p assets/tor/mac_x64

# Para Linux: instala tor e copia binário
if [ "$PLATAFORMA" = "linux" ]; then
    which tor > /dev/null 2>&1 || sudo apt-get install -y tor
    TOR_BIN=$(which tor)
    cp "$TOR_BIN" assets/tor/linux_x64/tor
    chmod +x assets/tor/linux_x64/tor
    echo "[✓] Tor Linux: assets/tor/linux_x64/tor"
fi

# Compila
echo "[*] Compilando com PyInstaller..."

pyinstaller \
    --name "$NOME" \
    --onefile \
    --windowed \
    --icon="assets/icone.ico" \
    --add-data "assets:assets" \
    --add-data "config.py:." \
    --hidden-import "customtkinter" \
    --hidden-import "PIL._tkinter_finder" \
    --hidden-import "pystray._xorg" \
    --hidden-import "stem" \
    --hidden-import "requests" \
    --hidden-import "cryptography" \
    main.py

echo "================================================"
echo "  Compilado: dist/$NOME"
echo "================================================"

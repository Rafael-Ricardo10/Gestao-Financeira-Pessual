#!/bin/bash
# ================================================
# Compila o app Android (.apk)
# Uso: ./build_android.sh
# ================================================

echo "================================================"
echo "  RRFS - Compilando para Android"
echo "================================================"

# Instala dependências
pip install buildozer kivymd kivy

# Instala dependências do sistema (Ubuntu/Debian)
sudo apt-get install -y \
    python3-pip \
    build-essential \
    git \
    ffmpeg \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev \
    libavformat-dev \
    libavcodec-dev \
    zlib1g-dev \
    libgstreamer1.0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    openjdk-17-jdk \
    unzip \
    autoconf \
    libtool \
    pkg-config \
    cmake

# Cria assets
mkdir -p assets

# Baixa binário Tor para Android ARM
echo "[*] Baixando Tor para Android..."
mkdir -p assets/tor/android_arm

# O tor para Android pode ser obtido do projeto Guardian:
# https://github.com/guardianproject/tor-android
# Ou compilado do código fonte

echo "[!] ATENÇÃO: Coloque o binário do Tor ARM em:"
echo "    assets/tor/android_arm/tor"
echo "    Obtenha em: https://github.com/guardianproject/tor-android/releases"

# Compila APK
echo "[*] Compilando APK..."
buildozer -v android debug

echo "================================================"
echo "  APK gerado em: bin/rrfsfinanceiro-2.0-debug.apk"
echo "================================================"
echo ""
echo "Para instalar no dispositivo:"
echo "  adb install bin/rrfsfinanceiro-2.0-debug.apk"
echo ""
echo "Para APK de produção (assinado):"
echo "  buildozer android release"

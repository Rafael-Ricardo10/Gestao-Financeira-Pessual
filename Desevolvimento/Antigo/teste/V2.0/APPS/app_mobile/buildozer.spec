[app]
title = RRFS Gestão Financeira
package.name = rrfsfinanceiro
package.domain = com.rrfs
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.include_patterns = assets/*,core/*,config.py

version = 2.0
requirements = python3,kivy==2.2.1,kivymd==1.1.1,pillow,requests,cryptography,certifi,urllib3,charset-normalizer,idna,pysocks,stem

orientation = portrait
fullscreen = 0
android.minapi = 21
android.api = 33
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

android.gradle_dependencies = com.android.support:support-v4:28.0.0

# Ícone
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/splash.png

[buildozer]
log_level = 2
warn_on_root = 1

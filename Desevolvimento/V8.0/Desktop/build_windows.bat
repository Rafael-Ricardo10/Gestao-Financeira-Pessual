@echo off
REM ====================================================================
REM  Gera RRFS-Financas.exe (UM arquivo, codigo COMPILADO em C via Nuitka)
REM  Execute no WINDOWS 10/11 x64, na pasta do projeto.
REM  Pre-requisitos:
REM    1) Python 3.12 x64 (python.org, marque "Add to PATH")
REM    2) MSYS2 (https://www.msys2.org) instalado em C:\msys64
REM  NAO foi testado de ponta a ponta pelo autor (sem maquina Windows para
REM  testar). Se algo falhar, rode "RRFS-Financas.exe --autoteste" e leia
REM  a mensagem de erro.
REM ====================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo [1/5] libtoxcore (via MSYS2)...
C:\msys64\usr\bin\bash.exe -lc "pacman -S --noconfirm --needed mingw-w64-x86_64-toxcore mingw-w64-x86_64-libsodium"
if errorlevel 1 goto erro
copy /y C:\msys64\mingw64\bin\libtoxcore.dll . >nul
if errorlevel 1 goto erro

REM libsodium e as DLLs de runtime do MinGW que ela/o toxcore podem exigir.
REM Cada uma vira um --include-data-files= para ir DENTRO do .exe (sem
REM isso, a DLL fica solta na pasta e o .exe falha em outro computador).
set "NUITKA_DLLS="
for %%N in (libsodium-*.dll libwinpthread-1.dll libgcc_s_seh-1.dll libstdc++-6.dll) do (
    if exist "C:\msys64\mingw64\bin\%%N" (
        copy /y "C:\msys64\mingw64\bin\%%N" . >nul
        set "NUITKA_DLLS=!NUITKA_DLLS! --include-data-files=%%N=%%N"
    )
)
if "!NUITKA_DLLS!"=="" (
    echo ERRO: nao achei libsodium-*.dll em C:\msys64\mingw64\bin
    goto erro
)
echo   DLLs encontradas:!NUITKA_DLLS!

echo [2/5] dependencias Python...
python -m pip install -q nuitka ordered-set zstandard PyQt5 sqlcipher3-binary psutil keyring ^
    cryptography yfinance matplotlib numpy pandas pdfplumber requests werkzeug
if errorlevel 1 goto erro

if not exist finance_icon.png python make_icon.py

echo [3/5] compilando (demora bastante; a 1a vez tambem baixa o compilador MinGW do Nuitka)...
python -m nuitka --onefile --mingw64 --assume-yes-for-downloads --windows-console-mode=disable ^
  --output-filename=RRFS-Financas.exe --enable-plugin=pyqt5 --enable-plugin=matplotlib ^
  --include-package=interface --include-package=modulos --include-package=sqlcipher3 ^
  --include-package=keyring --include-package=yfinance --include-package=curl_cffi ^
  --include-package=pdfplumber --include-package=pdfminer --include-package=psutil ^
  --include-module=cryptography ^
  --include-data-files=finance_icon.png=finance_icon.png ^
  --include-data-files=libtoxcore.dll=libtoxcore.dll ^
  !NUITKA_DLLS! ^
  --nofollow-import-to=tkinter --nofollow-import-to=IPython app.py
if errorlevel 1 goto erro

echo [4/5] verificando o resultado...
if not exist RRFS-Financas.exe (
    echo ERRO: RRFS-Financas.exe nao foi gerado.
    goto erro
)
echo [5/5] pronto: %cd%\RRFS-Financas.exe
echo       Teste agora com:  RRFS-Financas.exe --autoteste
goto fim
:erro
echo.
echo FALHOU. Veja a mensagem de erro acima (role para cima no terminal).
exit /b 1
:fim

@echo off
REM ====================================================================
REM  Instalador do RRFS Financas para Windows 10/11 (sem precisar de admin)
REM
REM  Instala em  %LOCALAPPDATA%\Gastos_Pessoais  (codigo, venv e dados)
REM  Cria atalho no Menu Iniciar e inicio automatico com o Windows.
REM
REM  Uso:  duplo clique, ou no terminal:  install.bat [/sem-autostart]
REM        install.bat /desinstalar
REM
REM  NAO FOI TESTADO de ponta a ponta (o autor nao tinha maquina Windows).
REM  Se falhar, copie a mensagem de erro e abra uma Issue no GitHub.
REM  Os dados (dados\) e logs (logs\) NUNCA sao copiados do projeto nem
REM  apagados em atualizacoes.
REM ====================================================================
setlocal enabledelayedexpansion
set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\Gastos_Pessoais"
set "PYV=%DEST%\venv\Scripts\python.exe"
set "MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "LNK_MENU=%MENU%\RRFS Financas.lnk"
set "LNK_AUTO=%MENU%\Startup\RRFS Financas.lnk"
set "AUTOSTART=1"
if /i "%~1"=="/sem-autostart" set "AUTOSTART=0"
if /i "%~2"=="/sem-autostart" set "AUTOSTART=0"
if /i "%~1"=="/desinstalar" goto desinstalar

if not exist "%SRC%app.py" goto sem_projeto
if not exist "%SRC%modulos" goto sem_projeto
if not exist "%SRC%interface" goto sem_projeto

echo [1/6] Python 3.10 ou mais novo...
call :procurar_python
if defined PYEXE goto python_ok
echo   Python adequado nao encontrado. Tentando instalar o Python 3.12 pelo winget...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
echo.
echo   Feche esta janela, abra outro terminal e rode install.bat de novo
echo   (o Windows precisa recarregar o PATH). Se o winget nao existir,
echo   instale o Python 3.12 em python.org marcando "Add python.exe to PATH".
goto fim_erro
:python_ok
echo   usando: %PYEXE%

echo [2/6] copiando o programa para %DEST% ...
if not exist "%DEST%" mkdir "%DEST%"
if not exist "%DEST%\dados" mkdir "%DEST%\dados"
if not exist "%DEST%\logs" mkdir "%DEST%\logs"
for %%D in (interface modulos tests) do if exist "%SRC%%%D" robocopy "%SRC%%%D" "%DEST%\%%D" /MIR /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
for %%F in (app.py requirements.txt finance_icon.png make_icon.py LICENSE) do if exist "%SRC%%%F" copy /y "%SRC%%%F" "%DEST%\%%F" >nul
REM robocopy devolve 1-7 quando copia com sucesso: zera o errorlevel
ver >nul

echo [3/6] biblioteca de rede libtoxcore ...
if exist "%DEST%\libtoxcore.dll" goto dll_ok
if exist "C:\msys64\usr\bin\bash.exe" goto msys_ok
echo   Instalando o MSYS2 pelo winget (fonte da libtoxcore para Windows) ...
winget install -e --id MSYS2.MSYS2 --silent --accept-package-agreements --accept-source-agreements
:msys_ok
if not exist "C:\msys64\usr\bin\bash.exe" goto sem_msys
C:\msys64\usr\bin\bash.exe -lc "pacman -S --noconfirm --needed mingw-w64-x86_64-toxcore mingw-w64-x86_64-libsodium"
if not errorlevel 1 goto msys_pronto
echo   Primeira tentativa falhou; atualizando a lista de pacotes e tentando de novo ...
C:\msys64\usr\bin\bash.exe -lc "pacman -Sy --noconfirm --needed mingw-w64-x86_64-toxcore mingw-w64-x86_64-libsodium"
if errorlevel 1 goto sem_msys
:msys_pronto
copy /y "C:\msys64\mingw64\bin\libtoxcore.dll" "%DEST%\" >nul
if errorlevel 1 goto sem_msys
for %%N in (libsodium-*.dll libwinpthread-1.dll libgcc_s_seh-1.dll libstdc++-6.dll) do if exist "C:\msys64\mingw64\bin\%%N" copy /y "C:\msys64\mingw64\bin\%%N" "%DEST%\" >nul
:dll_ok

echo [4/6] ambiente Python (venv) e pacotes - pode demorar ...
ver >nul
if not exist "%PYV%" %PYEXE% -m venv "%DEST%\venv"
if not exist "%PYV%" goto erro
"%PYV%" -m pip install -q --upgrade pip
if exist "%DEST%\requirements.txt" goto pip_req
set "REQ_BASE=PyQt5 matplotlib numpy python-dateutil yfinance pdfplumber requests psutil cryptography keyring sqlcipher3-binary pandas werkzeug"
for %%P in (%REQ_BASE%) do "%PYV%" -m pip install -q %%P || echo   FALHOU: %%P
goto pip_verif
:pip_req
"%PYV%" -m pip install -q -r "%DEST%\requirements.txt"
if not errorlevel 1 goto pip_verif
echo   A instalacao em bloco falhou; tentando pacote por pacote ...
for /f "usebackq eol=# tokens=1" %%P in ("%DEST%\requirements.txt") do "%PYV%" -m pip install -q %%P || echo   FALHOU: %%P
:pip_verif
"%PYV%" -c "import importlib.util as u; f=[p for m,p in (('PyQt5','PyQt5'),('cryptography','cryptography'),('matplotlib','matplotlib'),('numpy','numpy'),('dateutil','python-dateutil'),('yfinance','yfinance'),('pdfplumber','pdfplumber'),('requests','requests'),('psutil','psutil'),('keyring','keyring')) if u.find_spec(m) is None]; print('   ERRO: faltam', ' '.join(f)) if f else print('   bibliotecas ok'); print('   AVISO: sqlcipher3 ausente - dados SEM cifra propria') if u.find_spec('sqlcipher3') is None else None"

echo [5/6] icone e atalhos ...
call :mkico
set "RRFS_ALVO=%DEST%\venv\Scripts\pythonw.exe"
set "RRFS_ARGS="%DEST%\app.py""
set "RRFS_DIR=%DEST%"
set "RRFS_ICO=%DEST%\finance_icon.ico"
set "RRFS_LNK=%LNK_MENU%"
call :atalho
if "%AUTOSTART%"=="1" goto auto_sim
if exist "%LNK_AUTO%" del /q "%LNK_AUTO%"
echo   inicio automatico desativado
goto auto_fim
:auto_sim
set "RRFS_LNK=%LNK_AUTO%"
call :atalho
echo   inicio automatico ativado (inicia minimizado na bandeja)
:auto_fim

echo [6/6] verificando ...
pushd "%DEST%"
set "QT_QPA_PLATFORM=offscreen"
"%PYV%" app.py --autoteste
set "QT_QPA_PLATFORM="
popd
echo.
echo PRONTO. Abra "RRFS Financas" no Menu Iniciar.
echo Programa e dados: %DEST%
echo Faca backup dos seus dados pelo proprio app (Rede/Conta ^> Exportar).
goto fim

:procurar_python
set "PYEXE="
for %%V in (3.12 3.13 3.11 3.10) do if not defined PYEXE py -%%V -c "import sys" >nul 2>&1 && set "PYEXE=py -%%V"
if defined PYEXE exit /b 0
python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)" >nul 2>&1 && set "PYEXE=python"
exit /b 0

:mkico
if not exist "%DEST%\finance_icon.png" exit /b 0
"%PYV%" -c "from PIL import Image; Image.open(r'%DEST%\finance_icon.png').convert('RGBA').save(r'%DEST%\finance_icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" >nul 2>&1
exit /b 0

:atalho
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:RRFS_LNK);$s.TargetPath=$env:RRFS_ALVO;$s.Arguments=$env:RRFS_ARGS;$s.WorkingDirectory=$env:RRFS_DIR;$s.IconLocation=$env:RRFS_ICO;$s.Description='Gestao financeira pessoal';$s.Save()"
exit /b 0

:pausa
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 pause
exit /b 0

:desinstalar
if exist "%LNK_MENU%" del /q "%LNK_MENU%"
if exist "%LNK_AUTO%" del /q "%LNK_AUTO%"
if not exist "%DEST%\dados" goto remover_tudo
set "RESP="
set /p RESP=Apagar tambem seus DADOS em %DEST%\dados ? Digite APAGAR para confirmar: 
if /i "%RESP%"=="APAGAR" goto remover_tudo
for /d %%D in ("%DEST%\*") do if /i not "%%~nxD"=="dados" if /i not "%%~nxD"=="logs" rmdir /s /q "%%D"
for %%F in ("%DEST%\*") do del /q "%%F"
echo Programa removido. Dados mantidos em %DEST%\dados
goto fim
:remover_tudo
if exist "%DEST%" rmdir /s /q "%DEST%"
echo Tudo removido.
goto fim

:sem_projeto
echo ERRO: rode o instalador dentro da pasta do projeto (app.py, modulos e interface).
goto fim_erro
:sem_msys
echo ERRO: nao consegui obter a libtoxcore pelo MSYS2. Instale o MSYS2 (msys2.org),
echo abra o terminal "MSYS2 MINGW64" e rode:
echo   pacman -S mingw-w64-x86_64-toxcore mingw-w64-x86_64-libsodium
echo depois rode install.bat de novo.
goto fim_erro
:erro
echo.
echo FALHOU. Veja a mensagem acima (role para cima no terminal).
:fim_erro
call :pausa
exit /b 1
:fim
call :pausa
endlocal

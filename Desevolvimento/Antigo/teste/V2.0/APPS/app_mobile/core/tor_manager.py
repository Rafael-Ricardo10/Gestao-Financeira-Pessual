"""
Gerenciador do Tor embutido no binário
Baixa, extrai e inicia o Tor automaticamente
Suporta: Linux x64, Windows x64, macOS, Android ARM
"""

import os
import sys
import stat
import time
import signal
import threading
import subprocess
import platform
import tempfile
import shutil
import hashlib
from pathlib import Path
from typing import Optional

# Importa stem para controle do Tor
try:
    import stem
    import stem.process
    import stem.control
    STEM_OK = True
except ImportError:
    STEM_OK = False

# Config
try:
    from config import TOR_PORTA_SOCKS, TOR_PORTA_CTRL, TOR_TIMEOUT_INIT
except ImportError:
    TOR_PORTA_SOCKS = 9150
    TOR_PORTA_CTRL  = 9151
    TOR_TIMEOUT_INIT = 60

# ==================== DETECÇÃO DE PLATAFORMA ====================

def _plataforma():
    s = platform.system().lower()
    m = platform.machine().lower()

    if s == 'linux':
        if 'arm' in m or 'aarch' in m:
            return 'linux_arm'
        return 'linux_x64'
    elif s == 'windows':
        return 'windows_x64'
    elif s == 'darwin':
        return 'mac_x64'
    elif s == 'android':
        return 'android_arm'
    else:
        return 'linux_x64'

def _diretorio_app() -> Path:
    """Diretório onde o app está rodando"""
    if getattr(sys, 'frozen', False):
        # Compilado com PyInstaller
        return Path(sys._MEIPASS)
    else:
        # Rodando como script
        return Path(__file__).parent.parent

def _diretorio_dados() -> Path:
    """Diretório de dados persistentes do usuário"""
    plat = platform.system().lower()
    if plat == 'windows':
        base = Path(os.environ.get('APPDATA', Path.home()))
    elif plat == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    elif 'android' in plat or os.path.exists('/data/data'):
        base = Path('/data/data/com.rrfs.financeiro/files')
    else:
        base = Path.home() / '.local' / 'share'

    caminho = base / 'RRFSFinanceiro'
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho

# ==================== CLASSE PRINCIPAL ====================

class TorManager:
    """
    Gerencia o processo Tor embutido no app
    Tor roda localmente como SOCKS5 proxy
    """

    def __init__(self):
        self.processo      : Optional[subprocess.Popen] = None
        self.iniciado      : bool = False
        self.inicializando : bool = False
        self._lock         = threading.Lock()
        self._dir_dados    = _diretorio_dados() / 'tor_data'
        self._dir_dados.mkdir(parents=True, exist_ok=True)
        self._callback_status = None  # Para atualizar UI

    def set_callback_status(self, fn):
        """Define função chamada com updates de status"""
        self._callback_status = fn

    def _status(self, msg: str):
        print(f"[TOR] {msg}")
        if self._callback_status:
            try:
                self._callback_status(msg)
            except Exception:
                pass

    def _obter_binario_tor(self) -> Optional[Path]:
        """
        Localiza o binário do Tor:
        1. Dentro do bundle PyInstaller (_MEIPASS/tor/)
        2. Na pasta assets/tor/ do projeto
        3. No PATH do sistema (fallback)
        """
        plat = _plataforma()

        # Nomes do executável por plataforma
        nomes = {
            'linux_x64'  : 'tor',
            'linux_arm'  : 'tor',
            'windows_x64': 'tor.exe',
            'mac_x64'    : 'tor',
            'android_arm': 'tor'
        }
        nome_exe = nomes.get(plat, 'tor')

        # 1. Bundle PyInstaller
        dir_app = _diretorio_app()
        candidatos = [
            dir_app / 'tor' / plat / nome_exe,
            dir_app / 'tor' / nome_exe,
            dir_app / 'assets' / 'tor' / plat / nome_exe,
            dir_app / 'assets' / 'tor' / nome_exe,
            Path(__file__).parent.parent / 'assets' / 'tor' / plat / nome_exe,
        ]

        for c in candidatos:
            if c.exists():
                # Garante permissão de execução
                c.chmod(c.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                self._status(f"Binário Tor: {c}")
                return c

        # 2. Fallback: Tor do sistema
        tor_sistema = shutil.which('tor')
        if tor_sistema:
            self._status(f"Usando Tor do sistema: {tor_sistema}")
            return Path(tor_sistema)

        self._status("ERRO: Binário do Tor não encontrado!")
        return None

    def _gerar_torrc(self) -> Path:
        """Gera arquivo de configuração do Tor"""
        torrc_path = self._dir_dados / 'torrc'
        data_dir   = self._dir_dados / 'data'
        data_dir.mkdir(parents=True, exist_ok=True)

        conteudo = f"""
# RRFS - Configuração Tor automática
SocksPort {TOR_PORTA_SOCKS}
ControlPort {TOR_PORTA_CTRL}
DataDirectory {data_dir}
CookieAuthentication 0
HashedControlPassword ""
Log notice stdout
ClientOnly 1
StrictNodes 0
"""
        with open(torrc_path, 'w') as f:
            f.write(conteudo)

        return torrc_path

    def iniciar(self) -> bool:
        """
        Inicia o processo Tor em background
        Retorna True se iniciado com sucesso
        """
        with self._lock:
            if self.iniciado:
                return True

            if self.inicializando:
                return False

            self.inicializando = True

        self._status("Iniciando Tor embutido...")

        binario = self._obter_binario_tor()
        if not binario:
            self.inicializando = False
            return False

        torrc = self._gerar_torrc()

        try:
            if STEM_OK:
                return self._iniciar_com_stem(binario, torrc)
            else:
                return self._iniciar_sem_stem(binario, torrc)
        except Exception as e:
            self._status(f"Erro ao iniciar Tor: {e}")
            self.inicializando = False
            return False

    def _iniciar_com_stem(self, binario: Path, torrc: Path) -> bool:
        """Inicia Tor usando a biblioteca stem (controle avançado)"""
        try:
            self._status("Aguardando Tor estabelecer circuito...")

            def print_bootstrap(line):
                if 'Bootstrapped' in line:
                    self._status(f"Tor: {line.strip()}")

            self.processo = stem.process.launch_tor_with_config(
                tor_cmd=str(binario),
                config={
                    'SocksPort'           : str(TOR_PORTA_SOCKS),
                    'ControlPort'         : str(TOR_PORTA_CTRL),
                    'DataDirectory'       : str(self._dir_dados / 'data'),
                    'CookieAuthentication': '0',
                    'ClientOnly'          : '1',
                    'Log'                 : 'notice stdout',
                },
                init_msg_handler=print_bootstrap,
                timeout=TOR_TIMEOUT_INIT,
                take_ownership=True
            )

            with self._lock:
                self.iniciado      = True
                self.inicializando = False

            self._status("✅ Tor conectado! Circuito estabelecido.")
            return True

        except Exception as e:
            self._status(f"Erro stem: {e}")
            self.inicializando = False
            return False

    def _iniciar_sem_stem(self, binario: Path, torrc: Path) -> bool:
        """Inicia Tor sem stem (fallback)"""
        try:
            cmd = [str(binario), '-f', str(torrc)]

            self.processo = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            # Aguarda bootstrap
            inicio = time.time()
            while time.time() - inicio < TOR_TIMEOUT_INIT:
                linha = self.processo.stdout.readline()
                if not linha:
                    break
                if 'Bootstrapped 100%' in linha:
                    with self._lock:
                        self.iniciado      = True
                        self.inicializando = False
                    self._status("✅ Tor conectado!")
                    return True
                if 'Bootstrapped' in linha:
                    self._status(f"Tor: {linha.strip()}")
                if self.processo.poll() is not None:
                    break

            self.inicializando = False
            return False

        except Exception as e:
            self._status(f"Erro ao iniciar Tor: {e}")
            self.inicializando = False
            return False

    def parar(self):
        """Para o processo Tor"""
        with self._lock:
            if self.processo:
                try:
                    self.processo.terminate()
                    self.processo.wait(timeout=5)
                except Exception:
                    try:
                        self.processo.kill()
                    except Exception:
                        pass
                self.processo  = None
                self.iniciado  = False
            self._status("Tor parado.")

    def obter_proxies(self) -> dict:
        """Retorna configuração de proxy SOCKS5 para requests"""
        return {
            'http' : f'socks5h://127.0.0.1:{TOR_PORTA_SOCKS}',
            'https': f'socks5h://127.0.0.1:{TOR_PORTA_SOCKS}'
        }

    def esta_ativo(self) -> bool:
        """Verifica se Tor está ativo"""
        if not self.iniciado:
            return False
        if self.processo and self.processo.poll() is not None:
            self.iniciado = False
            return False
        return True

    def iniciar_em_thread(self, callback_concluido=None):
        """Inicia Tor em background sem bloquear a UI"""
        def _run():
            ok = self.iniciar()
            if callback_concluido:
                callback_concluido(ok)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t


# Instância global
tor = TorManager()

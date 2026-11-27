"""
Gerenciador Tor para o Sistema de Gestão Financeira.

Função: cliente Tor para conectar ao servidor de IA via onion.
- Baixa e mantém o binário Tor atualizado automaticamente
- Guarda o binário localmente (não baixa de novo se já existe)
- Expõe proxy SOCKS5 em 127.0.0.1:9050 para uso pelo requests
- Aguarda bootstrap 100% antes de declarar sucesso
- NÃO cria hidden service (apenas cliente)
"""

import os
import re
import stat
import time
import shutil
import socket
import tarfile
import platform
import threading
import subprocess
from pathlib import Path

import requests as req_lib
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from modulos.logs import registrar_log


# ══════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DE CAMINHOS
# ══════════════════════════════════════════════════════════════════

_BASE_DIR   = Path(__file__).resolve().parent.parent
TOR_DIR     = (_BASE_DIR / "dados" / "tor_client").resolve()
TOR_BIN     = (TOR_DIR   / "tor" / "tor").resolve()
TORRC       = (TOR_DIR   / "torrc").resolve()
DATA_DIR    = (TOR_DIR   / "data").resolve()
LOG_TOR     = (TOR_DIR   / "tor.log").resolve()
VERSION_FILE = (TOR_DIR  / "tor_version.txt").resolve()

# Porta SOCKS5 local — usada pelo requests via socks5h://
SOCKS_PORT = 9150   # 9150 para não conflitar com Tor Browser (9050)

# Variáveis globais de controle
_tor_process = None
_tor_lock    = threading.Lock()
_iniciando   = False


# ══════════════════════════════════════════════════════════════════
# LOG INTERNO
# ══════════════════════════════════════════════════════════════════

def _log(msg: str, nivel: str = "info"):
    icones = {
        "info": "[TOR-CLIENT]",
        "ok"  : "[TOR-CLIENT] ✓",
        "warn": "[TOR-CLIENT] ⚠",
        "erro": "[TOR-CLIENT] ✗",
    }
    print(f"{icones.get(nivel, '[TOR-CLIENT]')} {msg}", flush=True)
    try:
        nivel_log = (
            "erro"  if nivel == "erro" else
            "aviso" if nivel == "warn" else
            "info"
        )
        registrar_log("tor_client", msg, nivel=nivel_log)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════

def _porta_ok(porta: int) -> bool:
    """Verifica se uma porta TCP está escutando em 127.0.0.1"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(('127.0.0.1', porta)) == 0
    except Exception:
        return False


def _chmod_exec(caminho: Path) -> bool:
    """Torna um arquivo executável"""
    if not caminho.exists():
        return False
    try:
        os.chmod(str(caminho), 0o755)
        return os.access(str(caminho), os.X_OK)
    except Exception:
        try:
            subprocess.run(
                ['chmod', '+x', str(caminho)],
                timeout=5
            )
            return os.access(str(caminho), os.X_OK)
        except Exception:
            return False


def _no_android() -> bool:
    """Detecta ambiente Android/Termux"""
    return (
        'android' in platform.platform().lower() or
        Path('/system/build.prop').exists() or
        Path('/data/data/com.termux').exists()
    )


def _obter_arch() -> str | None:
    """Retorna a arquitetura para download do bundle"""
    maquina = platform.machine().lower()
    if maquina in ["x86_64", "amd64"]:
        return "linux-x86_64"
    if maquina in ["aarch64", "arm64"]:
        return "linux-aarch64"
    return None


# ══════════════════════════════════════════════════════════════════
# VERSÃO INSTALADA
# ══════════════════════════════════════════════════════════════════

def _versao_instalada() -> str | None:
    """Retorna a versão do binário Tor instalado localmente"""
    if not TOR_BIN.exists():
        return None
    try:
        r = subprocess.run(
            [str(TOR_BIN), "--version"],
            capture_output=True,
            timeout=5
        )
        saida = r.stdout.decode('utf-8', errors='ignore')
        match = re.search(r'Tor version ([\d.]+)', saida)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def _versao_salva() -> str | None:
    """Retorna a versão salva no arquivo de controle"""
    try:
        if VERSION_FILE.exists():
            return VERSION_FILE.read_text().strip()
    except Exception:
        pass
    return None


def _salvar_versao(versao: str):
    """Salva a versão instalada no arquivo de controle"""
    try:
        VERSION_FILE.write_text(versao)
    except Exception:
        pass


def _versao_mais_recente() -> str | None:
    """
    Consulta o site do Tor Project e retorna
    a versão mais recente disponível para download.
    """
    try:
        url = "https://dist.torproject.org/torbrowser/"
        r   = req_lib.get(url, timeout=10)
        versoes = sorted(
            re.findall(r'(\d+\.\d+\.\d+)', r.text),
            key=lambda v: [int(x) for x in v.split('.')],
            reverse=True
        )
        return versoes[0] if versoes else None
    except Exception as e:
        _log(f"Não foi possível checar versão mais recente: {e}", "warn")
        return None


# ══════════════════════════════════════════════════════════════════
# TOR DO SISTEMA
# ══════════════════════════════════════════════════════════════════

def _tor_sistema() -> str | None:
    """
    Verifica se há um Tor instalado no sistema operacional.
    Prioriza o do sistema para evitar downloads desnecessários.
    """
    candidatos = [
        "/usr/bin/tor",
        "/usr/local/bin/tor",
        "/data/data/com.termux/files/usr/bin/tor",
        shutil.which("tor"),
    ]
    for caminho in candidatos:
        if caminho and Path(caminho).exists():
            try:
                r = subprocess.run(
                    [caminho, "--version"],
                    capture_output=True,
                    timeout=3
                )
                if r.returncode == 0:
                    saida  = r.stdout.decode('utf-8', errors='ignore')
                    versao = saida.strip().splitlines()[0]
                    _log(
                        f"Tor do sistema encontrado: "
                        f"{caminho} ({versao})", "ok"
                    )
                    return caminho
            except Exception:
                pass
    return None


def _resolver_binario() -> str | None:
    """
    Resolve qual binário Tor usar:
    1. Tor do sistema operacional (prioridade)
    2. Bundle baixado localmente
    """
    ts = _tor_sistema()
    if ts:
        return ts

    if TOR_BIN.exists() and _chmod_exec(TOR_BIN):
        return str(TOR_BIN)

    return None


# ══════════════════════════════════════════════════════════════════
# DOWNLOAD E ATUALIZAÇÃO DO BINÁRIO
# ══════════════════════════════════════════════════════════════════

def verificar_atualizacao() -> dict:
    """
    Verifica se há uma versão mais recente do Tor disponível.

    Returns:
        dict com:
        - tem_atualizacao (bool)
        - versao_atual (str)
        - versao_nova (str)
        - usar_sistema (bool)
    """
    # Se Tor do sistema está disponível, não precisa gerenciar versão
    ts = _tor_sistema()
    if ts:
        return {
            'tem_atualizacao': False,
            'versao_atual':    'sistema',
            'versao_nova':     None,
            'usar_sistema':    True,
            'mensagem':        'Usando Tor do sistema operacional'
        }

    versao_atual = _versao_instalada()
    versao_nova  = _versao_mais_recente()

    if not versao_nova:
        return {
            'tem_atualizacao': False,
            'versao_atual':    versao_atual,
            'versao_nova':     None,
            'usar_sistema':    False,
            'mensagem':        'Não foi possível verificar atualizações'
        }

    tem_atualizacao = (
        versao_atual is None or
        versao_atual != versao_nova
    )

    return {
        'tem_atualizacao': tem_atualizacao,
        'versao_atual':    versao_atual or 'não instalado',
        'versao_nova':     versao_nova,
        'usar_sistema':    False,
        'mensagem': (
            f"Atualização disponível: "
            f"{versao_atual} → {versao_nova}"
            if tem_atualizacao else
            f"Tor atualizado (v{versao_atual})"
        )
    }


def baixar_tor(forcar: bool = False) -> bool:
    """
    Baixa e instala o Tor Expert Bundle.

    Não baixa novamente se já está instalado e atualizado,
    a menos que forcar=True.

    Args:
        forcar: Se True, baixa mesmo que já esteja instalado

    Returns:
        bool: True se o binário está pronto para uso
    """
    # Tor do sistema disponível — não precisa baixar
    ts = _tor_sistema()
    if ts:
        _log("Usando Tor do sistema — download não necessário", "ok")
        return True

    # Verificar se já está instalado e atualizado
    if not forcar and TOR_BIN.exists():
        info = verificar_atualizacao()
        if not info['tem_atualizacao']:
            _log(
                f"Tor já instalado e atualizado "
                f"(v{info['versao_atual']}) — "
                f"download ignorado", "ok"
            )
            return True
        else:
            _log(
                f"Atualização disponível: "
                f"{info['versao_atual']} → {info['versao_nova']}",
                "info"
            )

    sistema = platform.system().lower()
    if sistema != "linux":
        _log(
            f"Download automático não suportado em {sistema}. "
            f"Instale o Tor manualmente.", "warn"
        )
        return False

    arch = _obter_arch()
    if not arch:
        _log(
            f"Arquitetura não suportada: "
            f"{platform.machine()}", "erro"
        )
        return False

    _log(f"Baixando Tor Expert Bundle ({arch})...", "info")

    try:
        # Descobrir versões disponíveis
        url_base = "https://dist.torproject.org/torbrowser/"
        r = req_lib.get(url_base, timeout=10)
        versoes = sorted(
            re.findall(r'(\d+\.\d+\.\d+)', r.text),
            key=lambda v: [int(x) for x in v.split('.')],
            reverse=True
        )

        if not versoes:
            _log("Não foi possível listar versões disponíveis", "erro")
            return False

        for versao in versoes[:3]:
            nome_arquivo = (
                f"tor-expert-bundle-{arch}-{versao}.tar.gz"
            )
            url_download = f"{url_base}{versao}/{nome_arquivo}"

            _log(f"Tentando versão {versao}: {url_download}", "info")

            try:
                # Verificar se URL existe
                head = req_lib.head(url_download, timeout=5)
                if head.status_code != 200:
                    _log(
                        f"Versão {versao} não encontrada "
                        f"(HTTP {head.status_code})", "warn"
                    )
                    continue

                # Criar diretórios
                TOR_DIR.mkdir(parents=True, exist_ok=True)
                tar_path = TOR_DIR / "tor_bundle.tar.gz"

                # Download com progresso
                _log(f"Baixando {nome_arquivo}...", "info")
                with req_lib.get(
                    url_download,
                    stream=True,
                    timeout=120
                ) as resp:
                    resp.raise_for_status()
                    total_bytes = 0
                    ultimo_log  = 0

                    with open(tar_path, 'wb') as f:
                        for chunk in resp.iter_content(32768):
                            f.write(chunk)
                            total_bytes += len(chunk)

                            # Log a cada 5 MB
                            mb = total_bytes // (1024 * 1024)
                            if mb > ultimo_log:
                                _log(
                                    f"Baixando... {mb} MB",
                                    "info"
                                )
                                ultimo_log = mb

                _log(
                    f"Download concluído: "
                    f"{total_bytes // 1024} KB", "ok"
                )

                # Extrair bundle
                _log("Extraindo bundle...", "info")
                dir_extracao = TOR_DIR / "extracted"
                if dir_extracao.exists():
                    shutil.rmtree(dir_extracao)
                dir_extracao.mkdir()

                with tarfile.open(tar_path, 'r:gz') as tar:
                    tar.extractall(dir_extracao)

                # Localizar binário 'tor' dentro do bundle
                binario_encontrado = None
                for candidato in dir_extracao.rglob("tor"):
                    if (
                        candidato.is_file() and
                        candidato.name == "tor"
                    ):
                        binario_encontrado = candidato
                        break

                if not binario_encontrado:
                    _log(
                        "Binário 'tor' não encontrado no bundle",
                        "erro"
                    )
                    shutil.rmtree(dir_extracao, ignore_errors=True)
                    tar_path.unlink(missing_ok=True)
                    continue

                # Instalar binário
                TOR_BIN.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(binario_encontrado, TOR_BIN)
                _chmod_exec(TOR_BIN)

                # Copiar bibliotecas compartilhadas se existirem
                lib_dir_src = binario_encontrado.parent
                lib_dir_dst = TOR_BIN.parent
                for lib in lib_dir_src.glob("*.so*"):
                    try:
                        shutil.copy2(lib, lib_dir_dst / lib.name)
                    except Exception:
                        pass

                # Limpar temporários
                tar_path.unlink(missing_ok=True)
                shutil.rmtree(dir_extracao, ignore_errors=True)

                # Salvar versão instalada
                _salvar_versao(versao)

                _log(
                    f"Tor v{versao} instalado em: {TOR_BIN}",
                    "ok"
                )
                return True

            except Exception as e:
                _log(f"Falha na versão {versao}: {e}", "warn")
                continue

        _log("Nenhuma versão disponível para download", "erro")
        return False

    except Exception as e:
        _log(f"Erro ao baixar Tor: {e}", "erro")
        return False


# ══════════════════════════════════════════════════════════════════
# TORRC — MODO CLIENTE
# ══════════════════════════════════════════════════════════════════

def _gerar_torrc():
    """
    Gera o torrc para uso como cliente (sem hidden service).
    Expõe apenas SocksPort para uso pelo requests.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    extra = ""
    if _no_android():
        _log("Android detectado — ajustes aplicados", "info")
        extra = """
CircuitBuildTimeout 120
LearnCircuitBuildTimeout 0
MaxCircuitDirtiness 600
"""

    cfg = f"""# Tor Client — Gestão Financeira
DataDirectory {DATA_DIR.resolve()}
SocksPort 127.0.0.1:{SOCKS_PORT}
ControlPort 0
Log notice file {LOG_TOR.resolve()}
SafeLogging 1
{extra}
"""
    TORRC.write_text(cfg.strip())
    _log(
        f"torrc gerado → SocksPort 127.0.0.1:{SOCKS_PORT}",
        "info"
    )


# ══════════════════════════════════════════════════════════════════
# MONITOR DE LOG TOR
# ══════════════════════════════════════════════════════════════════

def _monitorar_log_tor(parar_evento: threading.Event):
    """
    Thread que lê o tor.log em tempo real e exibe
    progresso do bootstrap no terminal.
    """
    posicao = 0
    while not parar_evento.is_set():
        try:
            if LOG_TOR.exists():
                conteudo = LOG_TOR.read_text(errors='ignore')
                linhas   = conteudo.splitlines()
                if len(linhas) > posicao:
                    for linha in linhas[posicao:]:
                        _filtrar_linha_log(linha)
                    posicao = len(linhas)
        except Exception:
            pass
        time.sleep(0.5)


def _filtrar_linha_log(linha: str):
    """Exibe apenas linhas relevantes do tor.log"""
    linha = linha.strip()
    if not linha:
        return

    padroes = [
        'Bootstrapped', '100% (done)', 'Opened',
        'WARN', 'ERR', 'error', 'failed',
        'Problem bootstrapping', 'Could not bind',
        'Heartbeat',
    ]
    for padrao in padroes:
        if padrao.lower() in linha.lower():
            partes = linha.split(']', 1)
            msg    = partes[1].strip() if len(partes) > 1 else linha
            print(f"  [TOR-LOG] {msg}", flush=True)
            return


# ══════════════════════════════════════════════════════════════════
# INICIAR TOR (CLIENTE)
# ══════════════════════════════════════════════════════════════════

def iniciar_tor() -> tuple[bool, str]:
    """
    Inicia o Tor como cliente SOCKS5.

    Fluxo:
    1. Verifica/baixa binário
    2. Gera torrc de cliente
    3. Inicia processo Tor
    4. Aguarda bootstrap 100%
    5. Retorna (True, mensagem) ou (False, erro)
    """
    global _tor_process, _iniciando

    with _tor_lock:
        # Já está rodando?
        if _tor_process and _tor_process.poll() is None:
            _log("Tor já está rodando", "ok")
            return True, f"SOCKS5 em 127.0.0.1:{SOCKS_PORT}"

        if _iniciando:
            _log("Inicialização já em andamento", "warn")
            return False, "Já iniciando"

        _iniciando = True

    try:
        _log("═" * 50, "info")
        _log("Iniciando cliente Tor...", "info")

        # ── 1. Garantir binário disponível ────────────────────
        _log("Verificando binário Tor...", "info")
        if not baixar_tor():
            _iniciando = False
            return False, "Não foi possível obter o binário Tor"

        tor_bin = _resolver_binario()
        if not tor_bin:
            _iniciando = False
            return False, "Binário Tor não executável"

        # Exibir versão
        try:
            r = subprocess.run(
                [tor_bin, "--version"],
                capture_output=True,
                timeout=3
            )
            versao = (
                r.stdout.decode('utf-8', errors='ignore')
                .strip().splitlines()[0]
            )
            _log(f"Binário: {tor_bin}", "ok")
            _log(f"Versão : {versao}", "ok")
        except Exception:
            _log(f"Binário: {tor_bin}", "ok")

        # ── 2. Gerar torrc ────────────────────────────────────
        _gerar_torrc()

        # ── 3. Limpar log anterior ────────────────────────────
        if LOG_TOR.exists():
            try:
                LOG_TOR.unlink()
            except Exception:
                pass

        # ── 4. Iniciar processo Tor ───────────────────────────
        _log("Iniciando processo Tor...", "info")
        try:
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = (
                f"{TOR_BIN.parent.resolve()}:"
                f"{env.get('LD_LIBRARY_PATH', '')}"
            )

            with _tor_lock:
                _tor_process = subprocess.Popen(
                    [tor_bin, "-f", str(TORRC.resolve())],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(_BASE_DIR.resolve()),
                    env=env,
                    start_new_session=True,
                )
                _log(
                    f"Processo iniciado — PID: {_tor_process.pid}",
                    "ok"
                )

        except Exception as e:
            _iniciando = False
            return False, f"Erro ao iniciar processo: {e}"

        # ── 5. Monitor de log ─────────────────────────────────
        parar_monitor = threading.Event()
        monitor = threading.Thread(
            target=_monitorar_log_tor,
            args=(parar_monitor,),
            daemon=True,
            name="tor-log-monitor"
        )
        monitor.start()

        # ── 6. Aguardar bootstrap ─────────────────────────────
        _log("Aguardando bootstrap da rede Tor...", "info")
        _log("(pode levar 30-90 segundos)", "info")

        bootstrap_ok = False
        socks_ok     = False
        ultimo_pct   = -1
        erros_criticos = [
            'Could not bind',
            'Address already in use',
            'Failed to parse/validate config',
            'Problem bootstrapping',
            '[err]',
        ]

        for i in range(120):

            # Processo morreu?
            with _tor_lock:
                proc = _tor_process
            if proc and proc.poll() is not None:
                parar_monitor.set()
                log_final = ""
                try:
                    if LOG_TOR.exists():
                        log_final = LOG_TOR.read_text(
                            errors='ignore'
                        )[-800:]
                except Exception:
                    pass
                _iniciando = False
                return (
                    False,
                    f"Tor encerrou inesperadamente "
                    f"(código {proc.returncode}):\n{log_final}"
                )

            # Ler log
            if LOG_TOR.exists():
                try:
                    log_txt = LOG_TOR.read_text(errors='ignore')

                    # Erros críticos
                    for erro in erros_criticos:
                        if erro.lower() in log_txt.lower():
                            parar_monitor.set()
                            with _tor_lock:
                                if _tor_process:
                                    _tor_process.terminate()
                                    _tor_process = None
                            _iniciando = False
                            return (
                                False,
                                f"Erro Tor: {erro}\n"
                                f"Log:\n{log_txt[-800:]}"
                            )

                    # Progresso bootstrap
                    matches = re.findall(
                        r'Bootstrapped (\d+)%', log_txt
                    )
                    if matches:
                        pct = int(matches[-1])
                        if pct != ultimo_pct:
                            ultimo_pct = pct
                            barra = (
                                "█" * (pct // 5) +
                                "░" * (20 - pct // 5)
                            )
                            print(
                                f"  [TOR] Bootstrap "
                                f"[{barra}] {pct}%",
                                flush=True
                            )
                            if pct == 100:
                                bootstrap_ok = True

                except Exception:
                    pass

            # Verificar SOCKS5 disponível
            if _porta_ok(SOCKS_PORT):
                socks_ok = True

            # ✓ Sucesso: bootstrap 100% + SOCKS5 escutando
            if bootstrap_ok and socks_ok:
                parar_monitor.set()
                print("", flush=True)
                _log("═" * 50, "info")
                _log("CLIENTE TOR ATIVO", "ok")
                _log(
                    f"SOCKS5  : 127.0.0.1:{SOCKS_PORT}",
                    "ok"
                )
                _log(
                    f"Uso     : "
                    f"socks5h://127.0.0.1:{SOCKS_PORT}",
                    "ok"
                )
                _log("Bootstrap: 100% ✓", "ok")
                _log(f"PID Tor  : {_tor_process.pid}", "ok")
                _log("═" * 50, "info")

                _iniciando = False
                return (
                    True,
                    f"SOCKS5 em 127.0.0.1:{SOCKS_PORT}"
                )

            # Progresso a cada 15s
            if i > 0 and i % 15 == 0:
                _log(
                    f"Aguardando... {i}s/120s "
                    f"| bootstrap={'100%' if bootstrap_ok else f'{ultimo_pct}%'} "
                    f"| socks={'sim' if socks_ok else 'não'}",
                    "info"
                )

            time.sleep(1)

        # Timeout
        parar_monitor.set()
        log_final = ""
        try:
            if LOG_TOR.exists():
                log_final = LOG_TOR.read_text(
                    errors='ignore'
                )[-1000:]
        except Exception:
            pass

        with _tor_lock:
            if _tor_process:
                try:
                    _tor_process.terminate()
                except Exception:
                    pass
                _tor_process = None

        _log("Timeout de 120s atingido", "erro")
        _iniciando = False
        return False, f"Timeout 120s\nLog:\n{log_final}"

    except Exception as e:
        _iniciando = False
        import traceback
        traceback.print_exc()
        return False, f"Erro inesperado: {e}"


# ══════════════════════════════════════════════════════════════════
# PARAR / REINICIAR
# ══════════════════════════════════════════════════════════════════

def parar_tor() -> bool:
    """Para o processo Tor"""
    global _tor_process

    with _tor_lock:
        if not _tor_process:
            _log("Nenhum processo Tor ativo", "info")
            return True

        pid = _tor_process.pid
        try:
            _tor_process.terminate()
            _tor_process.wait(timeout=10)
            _tor_process = None
            _log(f"Processo {pid} encerrado", "ok")
            return True

        except subprocess.TimeoutExpired:
            _tor_process.kill()
            _tor_process = None
            _log(f"Processo {pid} forçado (SIGKILL)", "warn")
            return True

        except Exception as e:
            _tor_process = None
            _log(f"Erro ao parar: {e}", "erro")
            return False


def reiniciar_tor() -> tuple[bool, str]:
    """Para e reinicia o Tor"""
    _log("Reiniciando Tor...", "info")
    parar_tor()
    time.sleep(2)
    return iniciar_tor()


# ══════════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════════

def status_tor() -> dict:
    """Retorna status completo do cliente Tor"""
    with _tor_lock:
        rodando = (
            _tor_process is not None and
            _tor_process.poll() is None
        )
        pid = _tor_process.pid if rodando else None

    socks_ok      = _porta_ok(SOCKS_PORT)
    bootstrap_pct = 0
    bootstrap_ok  = False

    if LOG_TOR.exists():
        try:
            log_txt = LOG_TOR.read_text(errors='ignore')
            matches = re.findall(r'Bootstrapped (\d+)%', log_txt)
            if matches:
                bootstrap_pct = int(matches[-1])
                bootstrap_ok  = bootstrap_pct == 100
        except Exception:
            pass

    info = verificar_atualizacao()

    return {
        "rodando"          : rodando,
        "pid"              : pid,
        "socks_port"       : SOCKS_PORT,
        "socks_ok"         : socks_ok,
        "bootstrap_pct"    : bootstrap_pct,
        "bootstrap_ok"     : bootstrap_ok,
        "versao_instalada" : info['versao_atual'],
        "versao_nova"      : info.get('versao_nova'),
        "tem_atualizacao"  : info['tem_atualizacao'],
        "usar_sistema"     : info['usar_sistema'],
        "log_disponivel"   : LOG_TOR.exists(),
        "proxy_url"        : (
            f"socks5h://127.0.0.1:{SOCKS_PORT}"
            if socks_ok else None
        ),
    }


def obter_proxy_url() -> str | None:
    """
    Retorna a URL do proxy SOCKS5 se o Tor estiver ativo.
    Usada pelo financial_ai.py e ai_widget.py.
    """
    if _porta_ok(SOCKS_PORT):
        return f"socks5h://127.0.0.1:{SOCKS_PORT}"
    return None


def obter_log_tor(linhas: int = 50) -> list[str]:
    """Retorna as últimas N linhas do log do Tor"""
    if not LOG_TOR.exists():
        return ["Log não disponível"]
    try:
        todas = LOG_TOR.read_text(errors='ignore').splitlines()
        return todas[-linhas:]
    except Exception as e:
        return [f"Erro ao ler log: {e}"]


# ══════════════════════════════════════════════════════════════════
# INICIAR EM BACKGROUND
# ══════════════════════════════════════════════════════════════════

def iniciar_tor_background(
    callback_sucesso=None,
    callback_erro=None
):
    """
    Inicia o Tor em uma thread daemon (não bloqueia a UI).

    Args:
        callback_sucesso: função chamada com (proxy_url) ao conectar
        callback_erro   : função chamada com (mensagem_erro) se falhar
    """
    def _executar():
        # Verificar atualização antes de iniciar
        _log("Verificando atualizações do Tor...", "info")
        info = verificar_atualizacao()

        if info['tem_atualizacao'] and not info['usar_sistema']:
            _log(info['mensagem'], "info")
            _log("Baixando atualização...", "info")
            baixar_tor(forcar=True)
        else:
            _log(info['mensagem'], "ok")

        # Iniciar Tor
        sucesso, msg = iniciar_tor()

        if sucesso:
            proxy_url = obter_proxy_url()
            _log(f"Tor pronto — proxy: {proxy_url}", "ok")
            if callback_sucesso:
                try:
                    callback_sucesso(proxy_url)
                except Exception as e:
                    _log(f"Erro no callback: {e}", "warn")
        else:
            _log(f"Falha ao iniciar Tor: {msg}", "erro")
            if callback_erro:
                try:
                    callback_erro(msg)
                except Exception as e:
                    _log(f"Erro no callback: {e}", "warn")

    threading.Thread(
        target=_executar,
        daemon=True,
        name="tor-startup"
    ).start()

"""
Gerenciador de conexão: Direto vs Tor
Escolhe automaticamente a melhor conexão disponível
"""

import requests
import threading
import time
from typing import Optional, Tuple
from enum import Enum

try:
    from config import (
        SERVIDOR_DIRETO, SERVIDOR_ONION,
        TIMEOUT_DIRETO, TIMEOUT_TOR,
        VERIFICAR_SSL, PRIORIDADE_CONEXAO
    )
except ImportError:
    SERVIDOR_DIRETO    = "https://192.168.1.100:6300"
    SERVIDOR_ONION     = "https://seulink.onion"
    TIMEOUT_DIRETO     = 5
    TIMEOUT_TOR        = 30
    VERIFICAR_SSL      = False
    PRIORIDADE_CONEXAO = 1

from core.tor_manager import tor
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TipoConexao(Enum):
    DIRETA     = "direta"
    TOR        = "tor"
    OFFLINE    = "offline"
    CONECTANDO = "conectando"


class GerenciadorConexao:
    """
    Gerencia conexão com o servidor RRFS
    Testa direto primeiro → fallback para Tor
    """

    def __init__(self):
        self.tipo_atual    : TipoConexao = TipoConexao.OFFLINE
        self.url_ativa     : str         = ""
        self._lock         = threading.Lock()
        self._session_dir  = requests.Session()
        self._session_tor  = requests.Session()
        self._callbacks    = []         # Funções chamadas quando muda conexão
        self._testando     = False
        self._ultima_falha = 0.0

    def adicionar_callback(self, fn):
        """Callback chamado quando status de conexão muda"""
        self._callbacks.append(fn)

    def _notificar(self, tipo: TipoConexao, msg: str = ""):
        self.tipo_atual = tipo
        for fn in self._callbacks:
            try:
                fn(tipo, msg)
            except Exception:
                pass

    def _testar_direto(self) -> bool:
        """Testa conexão direta com o servidor"""
        try:
            r = self._session_dir.get(
                SERVIDOR_DIRETO + '/api/health',
                timeout=TIMEOUT_DIRETO,
                verify=VERIFICAR_SSL
            )
            return r.status_code == 200
        except Exception:
            return False

    def _testar_tor(self) -> bool:
        """Testa conexão via Tor"""
        if not tor.esta_ativo():
            return False
        try:
            self._session_tor.proxies = tor.obter_proxies()
            r = self._session_tor.get(
                SERVIDOR_ONION + '/api/health',
                timeout=TIMEOUT_TOR,
                verify=VERIFICAR_SSL
            )
            return r.status_code == 200
        except Exception:
            return False

    def conectar(self) -> TipoConexao:
        """
        Tenta conectar: direto → tor
        Retorna o tipo de conexão estabelecida
        """
        with self._lock:
            if self._testando:
                return self.tipo_atual
            self._testando = True

        self._notificar(TipoConexao.CONECTANDO, "Testando conexão...")

        try:
            if PRIORIDADE_CONEXAO == 1:
                # Tenta direto primeiro
                if self._testar_direto():
                    self.url_ativa = SERVIDOR_DIRETO
                    self._notificar(TipoConexao.DIRETA, "Conexão direta")
                    return TipoConexao.DIRETA

                # Fallback Tor
                self._notificar(TipoConexao.CONECTANDO, "Iniciando Tor...")
                if not tor.esta_ativo():
                    tor.iniciar()

                if self._testar_tor():
                    self.url_ativa = SERVIDOR_ONION
                    self._notificar(TipoConexao.TOR, "Conexão via Tor")
                    return TipoConexao.TOR

            else:
                # Tenta Tor primeiro
                if not tor.esta_ativo():
                    tor.iniciar()

                if self._testar_tor():
                    self.url_ativa = SERVIDOR_ONION
                    self._notificar(TipoConexao.TOR, "Conexão via Tor")
                    return TipoConexao.TOR

                if self._testar_direto():
                    self.url_ativa = SERVIDOR_DIRETO
                    self._notificar(TipoConexao.DIRETA, "Conexão direta")
                    return TipoConexao.DIRETA

            self._notificar(TipoConexao.OFFLINE, "Sem conexão - modo offline")
            self._ultima_falha = time.time()
            return TipoConexao.OFFLINE

        finally:
            with self._lock:
                self._testando = False

    def reconectar_se_necessario(self):
        """Tenta reconectar se está offline há mais de 30s"""
        if (self.tipo_atual == TipoConexao.OFFLINE and
                time.time() - self._ultima_falha > 30):
            threading.Thread(target=self.conectar, daemon=True).start()

    def request(
        self,
        metodo: str,
        endpoint: str,
        **kwargs
    ) -> Optional[requests.Response]:
        """
        Faz requisição usando a conexão ativa
        Fallback automático se conexão cair
        """
        if not self.url_ativa:
            return None

        url = self.url_ativa + endpoint
        kwargs.setdefault('verify', VERIFICAR_SSL)

        try:
            if self.tipo_atual == TipoConexao.TOR:
                kwargs['proxies'] = tor.obter_proxies()
                kwargs.setdefault('timeout', TIMEOUT_TOR)
                return self._session_tor.request(metodo, url, **kwargs)
            else:
                kwargs.setdefault('timeout', TIMEOUT_DIRETO)
                resp = self._session_dir.request(metodo, url, **kwargs)
                return resp

        except requests.exceptions.ConnectionError:
            # Conexão caiu - tenta reconectar
            self._notificar(TipoConexao.OFFLINE, "Conexão perdida")
            threading.Thread(target=self.conectar, daemon=True).start()
            return None
        except Exception as e:
            print(f"[CONEXAO] Erro: {e}")
            return None

    def get(self, endpoint: str, **kwargs) -> Optional[dict]:
        """GET com parse JSON automático"""
        r = self.request('GET', endpoint, **kwargs)
        if r and r.status_code < 500:
            try:
                return r.json()
            except Exception:
                return None
        return None

    def post(self, endpoint: str, json_data: dict = None, **kwargs) -> Optional[dict]:
        """POST com JSON"""
        r = self.request('POST', endpoint, json=json_data, **kwargs)
        if r and r.status_code < 500:
            try:
                return r.json()
            except Exception:
                return None
        return None

    def put(self, endpoint: str, json_data: dict = None, **kwargs) -> Optional[dict]:
        """PUT com JSON"""
        r = self.request('PUT', endpoint, json=json_data, **kwargs)
        if r and r.status_code < 500:
            try:
                return r.json()
            except Exception:
                return None
        return None

    def delete(self, endpoint: str, **kwargs) -> Optional[dict]:
        """DELETE"""
        r = self.request('DELETE', endpoint, **kwargs)
        if r and r.status_code < 500:
            try:
                return r.json()
            except Exception:
                return None
        return None

    def esta_online(self) -> bool:
        return self.tipo_atual in (TipoConexao.DIRETA, TipoConexao.TOR)

    def definir_headers_auth(self, token: str, chave_sessao: str):
        """Define headers de autenticação para todas as sessões"""
        headers = {
            'Authorization' : f'Bearer {token}',
            'X-Chave-Sessao': chave_sessao
        }
        self._session_dir.headers.update(headers)
        self._session_tor.headers.update(headers)

    def limpar_auth(self):
        """Remove headers de autenticação"""
        for h in ['Authorization', 'X-Chave-Sessao']:
            self._session_dir.headers.pop(h, None)
            self._session_tor.headers.pop(h, None)


# Instância global
conexao = GerenciadorConexao()

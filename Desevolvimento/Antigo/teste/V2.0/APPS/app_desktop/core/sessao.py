"""
Gerencia sessão do usuário - login persistente
"""

import json
import time
import threading
from typing import Optional
from core.cache_local import cache_local
from core.conexao import conexao

class GerenciadorSessao:
    def __init__(self):
        self.token        : Optional[str]  = None
        self.chave_sessao : Optional[str]  = None
        self.username     : Optional[str]  = None
        self.is_admin     : bool           = False
        self.user_id      : Optional[str]  = None
        self.logado       : bool           = False
        self._senha_temp  : Optional[str]  = None
        self._lock        = threading.Lock()

    def fazer_login(
        self,
        username: str,
        senha: str
    ) -> tuple[bool, str]:
        """
        Faz login no servidor e inicializa cache local
        Retorna (sucesso, mensagem)
        """
        dados = conexao.post('/api/login', {
            'username': username,
            'password': senha
        })

        if not dados:
            return False, "Sem conexão com o servidor"

        if not dados.get('sucesso'):
            return False, dados.get('erro', 'Credenciais inválidas')

        with self._lock:
            self.token        = dados['token']
            self.chave_sessao = dados['chave_sessao']
            self.username     = dados['username']
            self.is_admin     = dados.get('is_admin', False)
            self.logado       = True
            self._senha_temp  = senha

        # Configura headers de auth na conexão
        conexao.definir_headers_auth(self.token, self.chave_sessao)

        # Extrai user_id do token JWT (sem biblioteca extra)
        try:
            import base64
            payload_b64 = self.token.split('.')[1]
            # Padding
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            self.user_id = payload.get('user_id', username)
        except Exception:
            self.user_id = username

        # Inicializa cache local com chave da senha
        cache_local.inicializar(senha, self.user_id)

        # Salva sessão para auto-login
        cache_local.salvar_sessao({
            'token'        : self.token,
            'chave_sessao' : self.chave_sessao,
            'username'     : self.username,
            'is_admin'     : self.is_admin,
            'user_id'      : self.user_id,
            'senha_hash'   : _hash_senha_local(senha),
            'salvo_em'     : time.time()
        })

        deve_trocar = dados.get('deve_trocar_senha', False)
        if deve_trocar:
            return True, "TROCAR_SENHA"

        return True, "OK"

    def restaurar_sessao(self, senha: str) -> bool:
        """
        Tenta restaurar sessão salva (auto-login)
        Requer a senha para descriptografar o cache
        """
        # Precisamos da senha para inicializar o cache
        # Mas ainda não temos o user_id...
        # Usamos um identificador temporário baseado em hash da senha
        temp_id = _hash_senha_local(senha)[:16]
        cache_local.inicializar(senha, temp_id)

        dados_sessao = cache_local.carregar_sessao()
        if not dados_sessao:
            return False

        # Verifica se a senha bate
        if dados_sessao.get('senha_hash') != _hash_senha_local(senha):
            cache_local.fechar()
        # Verifica se não expirou (8 horas)
        salvo_em = dados_sessao.get('salvo_em', 0)
        if time.time() - salvo_em > 8 * 3600:
            return False

        with self._lock:
            self.token        = dados_sessao['token']
            self.chave_sessao = dados_sessao['chave_sessao']
            self.username     = dados_sessao['username']
            self.is_admin     = dados_sessao.get('is_admin', False)
            self.user_id      = dados_sessao.get('user_id', '')
            self.logado       = True

        conexao.definir_headers_auth(self.token, self.chave_sessao)

        # Re-inicializa cache com user_id correto
        cache_local.fechar()
        cache_local.inicializar(senha, self.user_id)

        return True

    def auto_login(self) -> bool:
        """
        Tenta auto-login sem senha
        Só funciona se o cache não expirou e a sessão foi salva
        Não é possível sem a senha pois o cache é criptografado
        Retorna False - usuário precisa digitar a senha uma vez
        """
        return False

    def logout(self):
        """Faz logout e limpa dados locais"""
        with self._lock:
            self.token        = None
            self.chave_sessao = None
            self.username     = None
            self.is_admin     = False
            self.user_id      = None
            self.logado       = False
            self._senha_temp  = None

        conexao.limpar_auth()
        cache_local.apagar_sessao()
        cache_local.limpar_tudo()
        cache_local.fechar()

    def esta_logado(self) -> bool:
        return self.logado


def _hash_senha_local(senha: str) -> str:
    """Hash rápido para verificar senha localmente"""
    import hashlib
    return hashlib.sha256(
        (senha + "rrfs_local_check_v1").encode()
    ).hexdigest()[:32]


# Instância global
sessao = GerenciadorSessao()

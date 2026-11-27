"""
Sincronização bidirecional completa
Cache local ↔ Servidor

REGRAS:
  1. Cache local NUNCA expira por tempo
  2. Dados só mudam quando há mudança real
  3. Servidor é a fonte da verdade
  4. App funciona offline indefinidamente
  5. Ao voltar online: sincroniza fila de pendências
  6. Multi-dispositivo: servidor distribui para todos
"""

import threading
import time
import hashlib
import json
from typing import Optional, Callable
from core.cache_local import cache_local
from core.conexao import conexao, TipoConexao

try:
    from config import SYNC_INTERVALO, SYNC_POLLING_ONLINE, SYNC_POLLING_OFFLINE
except ImportError:
    SYNC_INTERVALO        = 30
    SYNC_POLLING_ONLINE   = 30
    SYNC_POLLING_OFFLINE  = 10


class SincronizadorDados:
    """
    Gerencia sincronização bidirecional.
    Cache local = espelho permanente do servidor.
    """

    def __init__(self):
        self._lock           = threading.Lock()
        self._sync_ativo     = False
        self._thread_sync    = None
        self._callbacks_ui   : list[Callable] = []
        self._ultima_sync    = 0.0
        self._estava_offline = False

    def adicionar_callback_ui(self, fn: Callable):
        self._callbacks_ui.append(fn)

    def _notificar_ui(self, tipo: str, dados=None):
        for fn in self._callbacks_ui:
            try:
                fn(tipo, dados)
            except Exception:
                pass

    # ==================== HASH PARA DETECTAR MUDANÇAS ====================

    def _hash_lista(self, lista: list) -> str:
        """Gera hash de uma lista para detectar mudanças"""
        conteudo = json.dumps(lista, default=str, sort_keys=True)
        return hashlib.md5(conteudo.encode()).hexdigest()

    def _dados_mudaram(self, chave: str, novos_dados: Any) -> bool:
        """Verifica se os dados realmente mudaram"""
        hash_novo   = self._hash_lista(novos_dados) if isinstance(novos_dados, list) \
                      else hashlib.md5(json.dumps(novos_dados, default=str, sort_keys=True).encode()).hexdigest()
        hash_local  = cache_local.get_hash(chave)
        return hash_novo != hash_local

    # ==================== LEITURA INTELIGENTE ====================

    def obter_transacoes(self, forcar: bool = False) -> list:
        """
        Retorna transações do cache local.
        Só busca no servidor se:
          - Não tem cache ainda (primeira vez)
          - forcar=True (usuário pediu)
          - Acabou de voltar online
        """
        chave  = 'transacoes'
        cached = cache_local.get(chave)

        # Tem cache local → usa ele (mesmo offline)
        if cached is not None and not forcar:
            return cached

        # Sem cache ou forçou → tenta buscar no servidor
        if conexao.esta_online():
            dados = conexao.get('/api/transacoes')
            if dados and dados.get('sucesso'):
                trans = dados.get('transacoes', [])

                # Só atualiza cache se dados mudaram
                if self._dados_mudaram(chave, trans):
                    cache_local.set(chave, trans)
                    self._notificar_ui('dados_atualizados',
                                       {'tipo': 'transacoes'})
                    print(f"[SYNC] Transações atualizadas: {len(trans)}")
                return trans

        # Sem conexão → retorna cache (mesmo que seja antigo)
        return cached or []

    def obter_categorias(self, forcar: bool = False) -> list:
        chave  = 'categorias'
        cached = cache_local.get(chave)

        if cached is not None and not forcar:
            return cached

        if conexao.esta_online():
            dados = conexao.get('/api/categorias')
            if dados and dados.get('sucesso'):
                cats = dados.get('categorias', [])
                if self._dados_mudaram(chave, cats):
                    cache_local.set(chave, cats)
                    self._notificar_ui('dados_atualizados',
                                       {'tipo': 'categorias'})
                return cats

        return cached or []

    def obter_saldo(self, forcar: bool = False) -> dict:
        chave  = 'saldo'
        cached = cache_local.get(chave)

        if cached is not None and not forcar:
            return cached

        if conexao.esta_online():
            dados = conexao.get('/api/transacoes/saldo')
            if dados and dados.get('sucesso'):
                if self._dados_mudaram(chave, dados):
                    cache_local.set(chave, dados)
                return dados

        # Calcula saldo local se tiver transações em cache
        if not cached:
            trans = cache_local.get('transacoes') or []
            if trans:
                entrada = sum(t['valor'] for t in trans if t.get('tipo') == 'entrada')
                saida   = sum(t['valor'] for t in trans if t.get('tipo') == 'saida')
                cached  = {
                    'total_entrada': round(entrada, 2),
                    'total_saida'  : round(saida, 2),
                    'saldo'        : round(entrada - saida, 2),
                    'quantidade'   : len(trans),
                    'calculado_local': True
                }

        return cached or {}

    def obter_projecoes(self, meses: int = 3) -> dict:
        chave  = f'projecoes_{meses}'
        cached = cache_local.get(chave)

        # Projeções: busca do servidor se online
        # Mantém cache local quando offline
        if cached is not None and not conexao.esta_online():
            return cached

        if conexao.esta_online():
            dados = conexao.get(f'/api/agente/projecao?meses={meses}')
            if dados and dados.get('sucesso'):
                if self._dados_mudaram(chave, dados):
                    cache_local.set(chave, dados)
                return dados

        return cached or {}

    # ==================== ESCRITA COM CACHE IMEDIATO ====================

    def adicionar_transacao(self, dados: dict) -> tuple[bool, str]:
        """
        Adiciona transação:
        1. Atualiza cache local imediatamente
        2. Envia ao servidor (ou enfileira se offline)
        """
        import uuid
        from datetime import datetime

        if conexao.esta_online():
            resp = conexao.post('/api/transacoes', dados)
            if resp and resp.get('sucesso'):
                tid = resp.get('transacao_id', '')

                # Atualiza cache local com dado confirmado
                self._atualizar_cache_transacao_add({
                    **dados,
                    'id'        : tid,
                    'criado_em' : datetime.now().isoformat(),
                    'origem'    : 'manual'
                })
                self._notificar_ui('transacao_adicionada', dados)
                return True, tid

            return False, resp.get('erro', 'Erro') if resp else 'Sem resposta'

        else:
            # OFFLINE: adiciona no cache local e enfileira
            tid = 'local_' + str(uuid.uuid4()).replace('-','')[:12]
            transacao_local = {
                **dados,
                'id'          : tid,
                'criado_em'   : datetime.now().isoformat(),
                'origem'      : 'manual',
                'pendente_sync': True
            }
            self._atualizar_cache_transacao_add(transacao_local)

            # Enfileira para sync
            cache_local.enfileirar_sync('POST', '/api/transacoes', dados)

            self._notificar_ui('transacao_adicionada', transacao_local)
            print(f"[SYNC] Transação enfileirada (offline): {tid}")
            return True, tid

    def _atualizar_cache_transacao_add(self, transacao: dict):
        """Atualiza cache local adicionando transação"""
        trans = cache_local.get('transacoes') or []
        trans.insert(0, transacao)
        cache_local.set('transacoes', trans)

        # Recalcula saldo
        self._recalcular_saldo_local(trans)

    def _recalcular_saldo_local(self, trans: list):
        """Recalcula e atualiza saldo no cache local"""
        entrada = sum(t['valor'] for t in trans if t.get('tipo') == 'entrada')
        saida   = sum(t['valor'] for t in trans if t.get('tipo') == 'saida')
        saldo   = {
            'total_entrada'  : round(entrada, 2),
            'total_saida'    : round(saida, 2),
            'saldo'          : round(entrada - saida, 2),
            'quantidade'     : len(trans),
            'calculado_local': True
        }
        cache_local.set('saldo', saldo)

    def editar_transacao(self, tid: str, campos: dict) -> tuple[bool, str]:
        if conexao.esta_online():
            resp = conexao.put(f'/api/transacoes/{tid}', campos)
            if resp and resp.get('sucesso'):
                # Atualiza no cache local
                trans = cache_local.get('transacoes') or []
                for i, t in enumerate(trans):
                    if t['id'] == tid:
                        trans[i].update(campos)
                        break
                cache_local.set('transacoes', trans)
                self._recalcular_saldo_local(trans)
                self._notificar_ui('transacao_editada', {'id': tid})
                return True, 'Atualizado'
            return False, resp.get('erro', 'Erro') if resp else 'Sem conexão'
        else:
            # Offline: edita no cache e enfileira
            trans = cache_local.get('transacoes') or []
            for i, t in enumerate(trans):
                if t['id'] == tid:
                    trans[i].update(campos)
                    break
            cache_local.set('transacoes', trans)
            self._recalcular_saldo_local(trans)
            cache_local.enfileirar_sync(
                'PUT', f'/api/transacoes/{tid}', campos
            )
            self._notificar_ui('transacao_editada', {'id': tid})
            return True, 'Pendente sync'

    def excluir_transacao(self, tid: str) -> tuple[bool, str]:
        if conexao.esta_online():
            resp = conexao.delete(f'/api/transacoes/{tid}')
            if resp and resp.get('sucesso'):
                trans = [t for t in (cache_local.get('transacoes') or [])
                         if t['id'] != tid]
                cache_local.set('transacoes', trans)
                self._recalcular_saldo_local(trans)
                self._notificar_ui('transacao_excluida', {'id': tid})
                return True, 'Excluído'
            return False, 'Erro'
        else:
            # Offline: remove do cache e enfileira
            trans = [t for t in (cache_local.get('transacoes') or [])
                     if t['id'] != tid]
            cache_local.set('transacoes', trans)
            self._recalcular_saldo_local(trans)
            cache_local.enfileirar_sync('DELETE', f'/api/transacoes/{tid}')
            self._notificar_ui('transacao_excluida', {'id': tid})
            return True, 'Pendente sync'

    def adicionar_categoria(self, dados: dict) -> tuple[bool, str]:
        if conexao.esta_online():
            resp = conexao.post('/api/categorias', dados)
            if resp and resp.get('sucesso'):
                cid = resp.get('categoria_id', '')
                # Força atualização das categorias do servidor
                self.obter_categorias(forcar=True)
                self._notificar_ui('categoria_adicionada', dados)
                return True, cid
            return False, resp.get('erro', 'Erro') if resp else 'Sem conexão'
        else:
            import uuid
            cid = 'local_' + str(uuid.uuid4()).replace('-','')[:12]
            cats = cache_local.get('categorias') or []
            cats.append({
                **dados,
                'id'            : cid,
                'nomes_fantasia': [],
                'total_entrada' : 0,
                'total_saida'   : 0,
                'saldo'         : 0,
                'qtd_transacoes': 0,
                'pendente_sync' : True
            })
            cache_local.set('categorias', cats)
            cache_local.enfileirar_sync('POST', '/api/categorias', dados)
            self._notificar_ui('categoria_adicionada', dados)
            return True, cid

    def chat_ia(self, mensagem: str, contexto: dict) -> Optional[str]:
        """Chat com IA - requer conexão (não funciona offline)"""
        if not conexao.esta_online():
            return (
                "⚠️ O assistente IA precisa de conexão com o servidor.\n"
                "Você está no modo offline. Quando conectar, o chat funcionará normalmente."
            )
        resp = conexao.post('/api/agente/chat', {'mensagem': mensagem})
        if resp and resp.get('sucesso'):
            return resp.get('resposta', '')
        return "Erro ao conectar com IA."

    # ==================== SYNC AUTOMÁTICO ====================

    def processar_fila_sync(self) -> int:
        """
        Processa operações pendentes acumuladas offline.
        Chamado automaticamente quando conexão volta.
        """
        if not conexao.esta_online():
            return 0

        fila = cache_local.obter_fila_sync()
        if not fila:
            return 0

        print(f"[SYNC] Processando {len(fila)} operações pendentes...")
        sincronizados = 0
        erros         = 0

        for item in fila:
            try:
                op       = item['operacao']
                endpoint = item['endpoint']
                dados    = item.get('dados')

                if op == 'POST':
                    resp = conexao.post(endpoint, dados)
                elif op == 'PUT':
                    resp = conexao.put(endpoint, dados)
                elif op == 'DELETE':
                    resp = conexao.delete(endpoint)
                else:
                    resp = None

                if resp and resp.get('sucesso'):
                    cache_local.marcar_sync_enviado(item['id'])
                    sincronizados += 1
                else:
                    erros += 1
                    print(f"[SYNC] Erro no item {item['id']}: {resp}")

            except Exception as e:
                erros += 1
                print(f"[SYNC] Exceção no item {item['id']}: {e}")

        cache_local.limpar_fila_enviados()

        if sincronizados > 0:
            print(f"[SYNC] ✅ {sincronizados} operações enviadas, {erros} erros")

            # Após sync da fila, busca dados atualizados do servidor
            self._pull_dados_servidor()
            self._notificar_ui('sync_concluido', {
                'sincronizados': sincronizados,
                'erros'        : erros
            })

        return sincronizados

    def _pull_dados_servidor(self):
        """
        Busca dados atualizados do servidor e compara com cache local.
        Só atualiza o que realmente mudou.
        """
        if not conexao.esta_online():
            return

        atualizados = []

        # Transações
        dados = conexao.get('/api/transacoes')
        if dados and dados.get('sucesso'):
            trans = dados.get('transacoes', [])
            if self._dados_mudaram('transacoes', trans):
                cache_local.set('transacoes', trans)
                self._recalcular_saldo_local(trans)
                atualizados.append('transacoes')

        # Categorias
        dados = conexao.get('/api/categorias')
        if dados and dados.get('sucesso'):
            cats = dados.get('categorias', [])
            if self._dados_mudaram('categorias', cats):
                cache_local.set('categorias', cats)
                atualizados.append('categorias')

        # Saldo
        dados = conexao.get('/api/transacoes/saldo')
        if dados and dados.get('sucesso'):
            if self._dados_mudaram('saldo', dados):
                cache_local.set('saldo', dados)
                atualizados.append('saldo')

        if atualizados:
            print(f"[SYNC] Dados atualizados: {atualizados}")
            self._notificar_ui('dados_atualizados', {'campos': atualizados})

    def iniciar_sync_automatico(self):
        """
        Inicia loop de sincronização automática.

        COMPORTAMENTO:
        - Online:  verifica mudanças no servidor a cada 30s
        - Offline: tenta reconectar a cada 10s
        - Ao voltar online: processa fila e puxa dados
        """
        if self._sync_ativo:
            return

        self._sync_ativo = True

        def _loop():
            while self._sync_ativo:
                try:
                    online_agora = conexao.esta_online()

                    # Detecta transição offline → online
                    voltou_online = self._estava_offline and online_agora

                    if voltou_online:
                        print("[SYNC] 🌐 Conexão restaurada! Sincronizando...")
                        # Processa fila de pendências
                        self.processar_fila_sync()
                        # Puxa dados atualizados
                        self._pull_dados_servidor()
                        self._notificar_ui('conexao_restaurada', None)

                    elif online_agora:
                        # Verifica se servidor tem algo novo
                        self._verificar_mudancas_servidor()

                    elif not online_agora:
                        # Tenta reconectar
                        conexao.conectar()

                    self._estava_offline = not online_agora
                    self._ultima_sync    = time.time()

                    # Intervalo baseado no status
                    intervalo = SYNC_POLLING_ONLINE if online_agora \
                                else SYNC_POLLING_OFFLINE
                    time.sleep(intervalo)

                except Exception as e:
                    print(f"[SYNC] Erro no loop: {e}")
                    time.sleep(5)

        self._thread_sync = threading.Thread(
            target=_loop, name="SyncThread", daemon=True
        )
        self._thread_sync.start()
        print("[SYNC] Loop automático iniciado")

    def _verificar_mudancas_servidor(self):
        """
        Verificação leve: pede apenas os hashes/contagens ao servidor
        para decidir se precisa baixar dados completos.
        Economiza banda - não baixa dados se nada mudou.
        """
        if not conexao.esta_online():
            return

        # Verifica saldo (endpoint leve)
        dados_saldo = conexao.get('/api/transacoes/saldo')
        if dados_saldo and dados_saldo.get('sucesso'):
            if self._dados_mudaram('saldo', dados_saldo):
                # Saldo mudou → alguém adicionou transação
                # (pode ter sido outro dispositivo ou a versão web)
                print("[SYNC] Mudança detectada no servidor, atualizando...")
                self._pull_dados_servidor()

    def parar_sync(self):
        self._sync_ativo = False
        print("[SYNC] Sincronização parada")

    def forcar_sync_completo(self):
        """Força sincronização completa (usuário pediu)"""
        def _run():
            if conexao.esta_online():
                self.processar_fila_sync()
                self._pull_dados_servidor()
                self._notificar_ui('sync_forcado', None)
            else:
                self._notificar_ui('sync_sem_conexao', None)

        threading.Thread(target=_run, daemon=True).start()

    def tem_pendencias(self) -> bool:
        return cache_local.tem_pendencias()

    def status(self) -> dict:
        return {
            'online'          : conexao.esta_online(),
            'tipo_conexao'    : conexao.tipo_atual.value,
            'tem_pendencias'  : self.tem_pendencias(),
            'ultima_sync'     : self._ultima_sync,
            'sync_ativo'      : self._sync_ativo,
        }


# Instância global
sync = SincronizadorDados()


# Type hint fix
from typing import Any

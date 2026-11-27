"""
Módulo de transações financeiras
"""

import uuid
from datetime import datetime
from typing import Optional
from modulos.database import carregar_dados_usuario, salvar_dados_usuario
from modulos.cache import cache
from modulos.logs import registrar_log

def _chave_cache_dados(user_id: str) -> str:
    return f"user_{user_id}_dados"

def _carregar_com_cache(user_id: str, chave: bytes) -> dict:
    """Carrega dados com cache"""
    chave_cache = _chave_cache_dados(user_id)
    # Não cacheamos dados descriptografados por segurança
    # Cache apenas para metadados não sensíveis
    return carregar_dados_usuario(user_id, chave)

def adicionar_transacao(
    user_id: str,
    chave: bytes,
    tipo: str,           # "entrada" ou "saida"
    valor: float,
    nome_fantasia: str,
    descricao: str,
    categoria_id: Optional[str],
    data: Optional[str] = None,
    origem: str = "manual"  # "manual", "importacao", "agente"
) -> tuple[bool, str]:
    """Adiciona nova transação"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        transacao_id = str(uuid.uuid4()).replace('-', '')

        transacao = {
            "id": transacao_id,
            "tipo": tipo,
            "valor": round(float(valor), 2),
            "nome_fantasia": nome_fantasia.strip(),
            "descricao": descricao.strip(),
            "categoria_id": categoria_id,
            "data": data or datetime.now().strftime("%Y-%m-%d"),
            "criado_em": datetime.now().isoformat(),
            "origem": origem
        }

        dados["transacoes"].append(transacao)
        salvar_dados_usuario(user_id, dados, chave)
        cache.invalidar_usuario(user_id)

        return True, transacao_id
    except Exception as e:
        registrar_log("transacoes", f"Erro ao adicionar transação: {str(e)}")
        return False, str(e)

def editar_transacao(
    user_id: str,
    chave: bytes,
    transacao_id: str,
    campos: dict
) -> tuple[bool, str]:
    """Edita transação existente"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        for i, t in enumerate(dados["transacoes"]):
            if t["id"] == transacao_id:
                campos_permitidos = [
                    "tipo", "valor", "nome_fantasia",
                    "descricao", "categoria_id", "data"
                ]
                for campo in campos_permitidos:
                    if campo in campos:
                        dados["transacoes"][i][campo] = campos[campo]

                dados["transacoes"][i]["editado_em"] = datetime.now().isoformat()
                salvar_dados_usuario(user_id, dados, chave)
                cache.invalidar_usuario(user_id)
                return True, "Transação atualizada"

        return False, "Transação não encontrada"
    except Exception as e:
        registrar_log("transacoes", f"Erro ao editar transação: {str(e)}")
        return False, str(e)

def excluir_transacao(user_id: str, chave: bytes, transacao_id: str) -> tuple[bool, str]:
    """Exclui transação"""
    try:
        dados = carregar_dados_usuario(user_id, chave)
        antes = len(dados["transacoes"])
        dados["transacoes"] = [
            t for t in dados["transacoes"] if t["id"] != transacao_id
        ]

        if len(dados["transacoes"]) == antes:
            return False, "Transação não encontrada"

        salvar_dados_usuario(user_id, dados, chave)
        cache.invalidar_usuario(user_id)
        return True, "Transação excluída"
    except Exception as e:
        registrar_log("transacoes", f"Erro ao excluir transação: {str(e)}")
        return False, str(e)

def listar_transacoes(
    user_id: str,
    chave: bytes,
    filtros: Optional[dict] = None
) -> list:
    """
    Lista transações com filtros opcionais
    filtros: {nome_fantasia, categoria_id, descricao, tipo, data_inicio, data_fim, texto_livre}
    """
    try:
        dados = carregar_dados_usuario(user_id, chave)
        transacoes = dados.get("transacoes", [])

        if not filtros:
            return sorted(transacoes, key=lambda x: x.get('data', ''), reverse=True)

        resultado = transacoes

        if filtros.get('nome_fantasia'):
            termo = filtros['nome_fantasia'].lower()
            resultado = [
                t for t in resultado
                if termo in t.get('nome_fantasia', '').lower()
            ]

        if filtros.get('categoria_id'):
            resultado = [
                t for t in resultado
                if t.get('categoria_id') == filtros['categoria_id']
            ]

        if filtros.get('descricao'):
            termo = filtros['descricao'].lower()
            resultado = [
                t for t in resultado
                if termo in t.get('descricao', '').lower()
            ]

        if filtros.get('tipo'):
            resultado = [
                t for t in resultado
                if t.get('tipo') == filtros['tipo']
            ]

        if filtros.get('data_inicio'):
            resultado = [
                t for t in resultado
                if t.get('data', '') >= filtros['data_inicio']
            ]

        if filtros.get('data_fim'):
            resultado = [
                t for t in resultado
                if t.get('data', '') <= filtros['data_fim']
            ]

        if filtros.get('texto_livre'):
            termo = filtros['texto_livre'].lower()
            resultado = [
                t for t in resultado
                if (termo in t.get('nome_fantasia', '').lower() or
                    termo in t.get('descricao', '').lower())
            ]

        return sorted(resultado, key=lambda x: x.get('data', ''), reverse=True)

    except Exception as e:
        registrar_log("transacoes", f"Erro ao listar transações: {str(e)}")
        return []

def calcular_saldo(user_id: str, chave: bytes, categoria_id: Optional[str] = None) -> dict:
    """Calcula saldo total ou por categoria"""
    try:
        dados = carregar_dados_usuario(user_id, chave)
        transacoes = dados.get("transacoes", [])

        if categoria_id:
            transacoes = [t for t in transacoes if t.get('categoria_id') == categoria_id]

        total_entrada = sum(t['valor'] for t in transacoes if t.get('tipo') == 'entrada')
        total_saida = sum(t['valor'] for t in transacoes if t.get('tipo') == 'saida')
        saldo = total_entrada - total_saida

        return {
            "total_entrada": round(total_entrada, 2),
            "total_saida": round(total_saida, 2),
            "saldo": round(saldo, 2),
            "quantidade": len(transacoes)
        }
    except Exception as e:
        registrar_log("transacoes", f"Erro ao calcular saldo: {str(e)}")
        return {"total_entrada": 0, "total_saida": 0, "saldo": 0, "quantidade": 0}

def obter_nomes_fantasia_unicos(user_id: str, chave: bytes) -> list:
    """Retorna lista única de nomes fantasia"""
    dados = carregar_dados_usuario(user_id, chave)
    nomes = set()
    for t in dados.get("transacoes", []):
        nf = t.get("nome_fantasia", "").strip()
        if nf:
            nomes.add(nf)
    return sorted(list(nomes))

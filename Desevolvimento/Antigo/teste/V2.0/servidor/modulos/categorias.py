"""
Módulo de categorias - Organização, Quitação e Empréstimo
"""

import uuid
from datetime import datetime
from typing import Optional
from modulos.database import carregar_dados_usuario, salvar_dados_usuario
from modulos.cache import cache
from modulos.logs import registrar_log


def criar_categoria(
    user_id: str,
    chave: bytes,
    nome: str,
    tipo: str,
    meta_valor: Optional[float] = None,
    descricao: str = "",
    emp_dados: Optional[dict] = None
) -> tuple:
    """Cria nova categoria"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        for cat in dados.get("categorias", []):
            if cat["nome"].lower() == nome.lower():
                return False, "Categoria com este nome já existe"

        categoria_id = str(uuid.uuid4()).replace('-', '')

        categoria = {
            "id": categoria_id,
            "nome": nome.strip(),
            "tipo": tipo,  # organizacao | quitacao | emprestimo
            "meta_valor": round(float(meta_valor), 2) if meta_valor else None,
            "descricao": descricao.strip(),
            "nomes_fantasia": [],
            "criado_em": datetime.now().isoformat(),
            "ativo": True
        }

        # Dados específicos de empréstimo
        if tipo == 'emprestimo' and emp_dados:
            categoria['emp_dados'] = {
                "valor_principal": float(emp_dados.get('valor_principal', 0)),
                "juros_pct": float(emp_dados.get('juros_pct', 0)),
                "parcelas": int(emp_dados.get('parcelas', 1)),
                "desconto": float(emp_dados.get('desconto', 0)),
                "total_a_pagar": float(emp_dados.get('total_a_pagar', 0)),
                "valor_parcela": float(emp_dados.get('valor_parcela', 0)),
                "quitado": False,
                "quitado_em": None
            }

        if "categorias" not in dados:
            dados["categorias"] = []

        dados["categorias"].append(categoria)
        salvar_dados_usuario(user_id, dados, chave)
        cache.invalidar_usuario(user_id)

        return True, categoria_id
    except Exception as e:
        registrar_log("categorias", f"Erro ao criar categoria: {str(e)}")
        return False, str(e)


def editar_categoria(
    user_id: str,
    chave: bytes,
    categoria_id: str,
    campos: dict
) -> tuple:
    """Edita categoria existente"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        for i, cat in enumerate(dados.get("categorias", [])):
            if cat["id"] == categoria_id:
                campos_permitidos = ["nome", "tipo", "meta_valor",
                                     "descricao", "emp_dados"]
                for campo in campos_permitidos:
                    if campo in campos:
                        if campo == 'emp_dados' and campos[campo]:
                            # Merge dos dados de empréstimo
                            existing = dados["categorias"][i].get('emp_dados', {})
                            existing.update(campos[campo])
                            dados["categorias"][i]['emp_dados'] = existing
                        else:
                            dados["categorias"][i][campo] = campos[campo]

                dados["categorias"][i]["editado_em"] = datetime.now().isoformat()
                salvar_dados_usuario(user_id, dados, chave)
                cache.invalidar_usuario(user_id)
                return True, "Categoria atualizada"

        return False, "Categoria não encontrada"
    except Exception as e:
        registrar_log("categorias", f"Erro ao editar categoria: {str(e)}")
        return False, str(e)


def excluir_categoria(user_id: str, chave: bytes, categoria_id: str) -> tuple:
    """Exclui categoria e desvincula transações"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        antes = len(dados.get("categorias", []))
        dados["categorias"] = [
            c for c in dados.get("categorias", []) if c["id"] != categoria_id
        ]

        if len(dados["categorias"]) == antes:
            return False, "Categoria não encontrada"

        for t in dados.get("transacoes", []):
            if t.get("categoria_id") == categoria_id:
                t["categoria_id"] = None

        salvar_dados_usuario(user_id, dados, chave)
        cache.invalidar_usuario(user_id)
        return True, "Categoria excluída"
    except Exception as e:
        registrar_log("categorias", f"Erro ao excluir categoria: {str(e)}")
        return False, str(e)


def adicionar_nome_fantasia_categoria(
    user_id: str,
    chave: bytes,
    categoria_id: str,
    nome_fantasia: str
) -> tuple:
    """Vincula nome fantasia a uma categoria e auto-categoriza transações"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        for i, cat in enumerate(dados.get("categorias", [])):
            if cat["id"] == categoria_id:
                if nome_fantasia not in cat.get("nomes_fantasia", []):
                    dados["categorias"][i].setdefault("nomes_fantasia", []).append(nome_fantasia)

                    count = 0
                    for t in dados.get("transacoes", []):
                        if (t.get("nome_fantasia") == nome_fantasia
                                and t.get("categoria_id") is None):
                            t["categoria_id"] = categoria_id
                            count += 1

                    salvar_dados_usuario(user_id, dados, chave)
                    cache.invalidar_usuario(user_id)
                    return True, f"Nome vinculado. {count} transações categorizadas"

                return False, "Nome fantasia já está nesta categoria"

        return False, "Categoria não encontrada"
    except Exception as e:
        registrar_log("categorias", f"Erro ao adicionar nome fantasia: {str(e)}")
        return False, str(e)


def remover_nome_fantasia_categoria(
    user_id: str,
    chave: bytes,
    categoria_id: str,
    nome_fantasia: str
) -> tuple:
    """Remove nome fantasia de uma categoria"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        for i, cat in enumerate(dados.get("categorias", [])):
            if cat["id"] == categoria_id:
                nomes = cat.get("nomes_fantasia", [])
                if nome_fantasia in nomes:
                    dados["categorias"][i]["nomes_fantasia"].remove(nome_fantasia)
                    salvar_dados_usuario(user_id, dados, chave)
                    cache.invalidar_usuario(user_id)
                    return True, "Nome fantasia removido"

        return False, "Não encontrado"
    except Exception as e:
        registrar_log("categorias", f"Erro ao remover nome fantasia: {str(e)}")
        return False, str(e)


def atribuir_categoria_transacao(
    user_id: str,
    chave: bytes,
    transacao_id: str,
    categoria_id: Optional[str]
) -> tuple:
    """Atribui ou remove categoria de uma transação"""
    try:
        dados = carregar_dados_usuario(user_id, chave)

        for i, t in enumerate(dados.get("transacoes", [])):
            if t["id"] == transacao_id:
                dados["transacoes"][i]["categoria_id"] = categoria_id
                salvar_dados_usuario(user_id, dados, chave)
                cache.invalidar_usuario(user_id)
                return True, "Categoria atribuída"

        return False, "Transação não encontrada"
    except Exception as e:
        registrar_log("categorias", f"Erro ao atribuir categoria: {str(e)}")
        return False, str(e)


def listar_categorias(user_id: str, chave: bytes) -> list:
    """Lista todas as categorias com resumo financeiro"""
    try:
        dados = carregar_dados_usuario(user_id, chave)
        categorias = dados.get("categorias", [])
        transacoes = dados.get("transacoes", [])

        resultado = []
        for cat in categorias:
            trans_cat = [t for t in transacoes if t.get("categoria_id") == cat["id"]]
            total_entrada = sum(t["valor"] for t in trans_cat if t.get("tipo") == "entrada")
            total_saida = sum(t["valor"] for t in trans_cat if t.get("tipo") == "saida")

            cat_info = dict(cat)
            cat_info["total_entrada"] = round(total_entrada, 2)
            cat_info["total_saida"] = round(total_saida, 2)
            cat_info["saldo"] = round(total_entrada - total_saida, 2)
            cat_info["qtd_transacoes"] = len(trans_cat)

            if cat.get("tipo") == "quitacao" and cat.get("meta_valor"):
                cat_info["percentual_quitado"] = round(
                    (total_saida / cat["meta_valor"]) * 100, 2
                )
                cat_info["valor_restante"] = round(
                    cat["meta_valor"] - total_saida, 2
                )

            if cat.get("tipo") == "emprestimo" and cat.get("meta_valor"):
                total_pago = total_saida
                meta = cat["meta_valor"]
                cat_info["percentual_quitado"] = round(
                    (total_pago / meta) * 100, 2
                ) if meta > 0 else 0
                cat_info["valor_restante"] = round(max(0, meta - total_pago), 2)

            resultado.append(cat_info)

        return resultado
    except Exception as e:
        registrar_log("categorias", f"Erro ao listar categorias: {str(e)}")
        return []


def obter_transacoes_sem_categoria(user_id: str, chave: bytes) -> list:
    """Retorna transações sem categoria"""
    dados = carregar_dados_usuario(user_id, chave)
    return [t for t in dados.get("transacoes", []) if not t.get("categoria_id")]

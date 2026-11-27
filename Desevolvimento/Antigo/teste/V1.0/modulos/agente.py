"""
Agente de IA - Motor principal do sistema
Usa LLM via Ollama apenas quando necessário
Processamento local para tarefas simples
Cache agressivo para velocidade
"""

import json
import requests
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Any
from modulos.cache import cache
from modulos.logs import registrar_log
import statistics
import math

# URL Ollama
OLLAMA_BASE = "http://172.17.0.1:11434"
TIMEOUT_LLM = 30

# Modelo padrão (pode ser alterado pelo admin)
_modelo_atual = {"nome": None}

def obter_modelo_atual() -> Optional[str]:
    return _modelo_atual["nome"]

def definir_modelo(nome: str):
    _modelo_atual["nome"] = nome

def listar_modelos_ollama() -> list:
    """Lista modelos disponíveis no Ollama"""
    chave_cache = "ollama_modelos"
    cached = cache.get(chave_cache)
    if cached:
        return cached

    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        if resp.status_code == 200:
            modelos = [m["name"] for m in resp.json().get("models", [])]
            cache.set(chave_cache, modelos, ttl=300)
            return modelos
    except Exception as e:
        registrar_log("agente", f"Erro ao listar modelos Ollama: {str(e)}")
    return []

def _chamar_llm(prompt: str, max_tokens: int = 500) -> Optional[str]:
    """
    Chama LLM via Ollama com engenharia de prompt otimizada
    Retorna resposta da LLM ou None em caso de erro
    """
    modelo = _modelo_atual["nome"]
    if not modelo:
        modelos = listar_modelos_ollama()
        if modelos:
            _modelo_atual["nome"] = modelos[0]
            modelo = modelos[0]
        else:
            return None

    try:
        payload = {
            "model": modelo,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.1,  # Baixo para respostas consistentes
                "top_p": 0.9,
            }
        }

        resp = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            timeout=TIMEOUT_LLM
        )

        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except Exception as e:
        registrar_log("agente", f"Erro LLM: {str(e)}")
    return None

# ==================== PROMPTS OTIMIZADOS ====================

def _prompt_analise_transacao(transacao: dict, historico_resumo: dict) -> str:
    """Prompt compacto para análise de transação"""
    return f"""SISTEMA:responda em JSON compacto
TAREFA:analise_transacao
DADOS:{{
"valor":{transacao.get('valor')},
"tipo":"{transacao.get('tipo')}",
"nome":"{transacao.get('nome_fantasia')}",
"data":"{transacao.get('data')}",
"media_historica":{historico_resumo.get('media', 0)},
"periodo_similar":{historico_resumo.get('periodo_similar', 0)}
}}
RESPONDA:{{
"anormal":bool,
"risco":"baixo|medio|alto",
"resumo":"max 20 palavras",
"sugestao":"max 15 palavras"
}}"""

def _prompt_tendencia(dados_serie: list) -> str:
    """Prompt para análise de tendência"""
    return f"""SISTEMA:analista_financeiro
DADOS_SERIE:{json.dumps(dados_serie[-12:], default=str)}
RESPONDA_JSON:{{
"tendencia":"crescimento|queda|estavel|volatil",
"percentual_mudanca":float,
"previsao_proximo_mes":float,
"alerta":"max 15 palavras ou null"
}}"""

def _prompt_projecao(historico_mensal: list, meses_futuros: int) -> str:
    """Prompt para projeção financeira"""
    return f"""SISTEMA:projecao_financeira
HISTORICO:{json.dumps(historico_mensal[-6:], default=str)}
MESES_PROJETAR:{meses_futuros}
RESPONDA_JSON:{{
"projecoes":[{{"mes":"YYYY-MM","entrada":float,"saida":float,"saldo":float}}],
"confianca":"baixa|media|alta",
"observacao":"max 20 palavras"
}}"""

def _prompt_chat_livre(mensagem: str, contexto_financeiro: dict) -> str:
    """Prompt para chat livre com contexto financeiro"""
    return f"""Você é um assistente financeiro pessoal especializado.
Contexto do usuário:
- Saldo atual: R$ {contexto_financeiro.get('saldo', 0):.2f}
- Entradas este mês: R$ {contexto_financeiro.get('entrada_mes', 0):.2f}
- Saídas este mês: R$ {contexto_financeiro.get('saida_mes', 0):.2f}
- Categorias ativas: {contexto_financeiro.get('qtd_categorias', 0)}

Usuário: {mensagem}

Responda de forma direta, útil e em português. Máximo 150 palavras."""

def _prompt_extrair_transacao(texto: str) -> str:
    """Prompt para extrair dados de transação do texto do usuário"""
    return f"""TAREFA:extrair_transacao
TEXTO:"{texto}"
RESPONDA_JSON:{{
"tipo":"entrada|saida",
"valor":float_ou_null,
"nome_fantasia":"texto",
"descricao":"texto",
"data":"YYYY-MM-DD_ou_null",
"categoria_sugerida":"texto_ou_null",
"confianca":"baixa|media|alta"
}}
DATA_HOJE:{datetime.now().strftime('%Y-%m-%d')}"""

# ==================== ANÁLISES LOCAIS (SEM LLM) ====================

def calcular_estatisticas_mensais(transacoes: list) -> dict:
    """Calcula estatísticas mensais sem LLM"""
    if not transacoes:
        return {}

    mensais = {}
    for t in transacoes:
        data = t.get('data', '')
        if len(data) >= 7:
            mes = data[:7]  # YYYY-MM
            if mes not in mensais:
                mensais[mes] = {"entrada": 0, "saida": 0, "transacoes": 0}

            if t.get('tipo') == 'entrada':
                mensais[mes]["entrada"] += t.get('valor', 0)
            else:
                mensais[mes]["saida"] += t.get('valor', 0)
            mensais[mes]["transacoes"] += 1

    for mes in mensais:
        mensais[mes]["saldo"] = round(
            mensais[mes]["entrada"] - mensais[mes]["saida"], 2
        )
        mensais[mes]["entrada"] = round(mensais[mes]["entrada"], 2)
        mensais[mes]["saida"] = round(mensais[mes]["saida"], 2)

    return mensais

def detectar_anomalias_local(transacoes: list) -> list:
    """
    Detecta anomalias localmente usando estatística
    Usa Z-score para identificar outliers
    """
    if len(transacoes) < 5:
        return []

    anomalias = []

    # Agrupa por tipo
    for tipo in ['entrada', 'saida']:
        valores = [t['valor'] for t in transacoes if t.get('tipo') == tipo]

        if len(valores) < 3:
            continue

        media = statistics.mean(valores)
        desvio = statistics.stdev(valores) if len(valores) > 1 else 0

        if desvio == 0:
            continue

        for t in transacoes:
            if t.get('tipo') != tipo:
                continue

            z_score = abs((t['valor'] - media) / desvio)

            if z_score > 2.5:  # 2.5 desvios padrão
                anomalias.append({
                    "transacao_id": t.get('id'),
                    "nome_fantasia": t.get('nome_fantasia'),
                    "valor": t.get('valor'),
                    "tipo": tipo,
                    "z_score": round(z_score, 2),
                    "media_tipo": round(media, 2),
                    "severidade": "alta" if z_score > 3.5 else "media"
                })

    return anomalias

def projecao_local(historico_mensal: dict, meses: int = 3) -> list:
    """Projeção simples baseada em média móvel"""
    if not historico_mensal:
        return []

    meses_ordenados = sorted(historico_mensal.keys())
    ultimos = meses_ordenados[-6:] if len(meses_ordenados) >= 6 else meses_ordenados

    media_entrada = statistics.mean([historico_mensal[m]["entrada"] for m in ultimos])
    media_saida = statistics.mean([historico_mensal[m]["saida"] for m in ultimos])

    # Tendência linear simples
    if len(ultimos) >= 2:
        entradas = [historico_mensal[m]["entrada"] for m in ultimos]
        saidas = [historico_mensal[m]["saida"] for m in ultimos]

        # Inclinação simples
        tend_entrada = (entradas[-1] - entradas[0]) / len(entradas) if entradas else 0
        tend_saida = (saidas[-1] - saidas[0]) / len(saidas) if saidas else 0
    else:
        tend_entrada = tend_saida = 0

    projecoes = []
    ultimo_mes = meses_ordenados[-1] if meses_ordenados else datetime.now().strftime('%Y-%m')

    try:
        data_base = datetime.strptime(ultimo_mes + "-01", "%Y-%m-%d")
    except Exception:
        data_base = datetime.now()

    for i in range(1, meses + 1):
        from datetime import date
        import calendar

        # Próximo mês
        mes_num = data_base.month + i
        ano = data_base.year + (mes_num - 1) // 12
        mes = ((mes_num - 1) % 12) + 1

        entrada_proj = max(0, media_entrada + (tend_entrada * i))
        saida_proj = max(0, media_saida + (tend_saida * i))

        projecoes.append({
            "mes": f"{ano:04d}-{mes:02d}",
            "entrada": round(entrada_proj, 2),
            "saida": round(saida_proj, 2),
            "saldo": round(entrada_proj - saida_proj, 2)
        })

    return projecoes

def detectar_tendencia_local(historico_mensal: dict) -> dict:
    """Detecta tendência sem LLM"""
    if len(historico_mensal) < 2:
        return {"tendencia": "insuficiente", "mensagem": "Dados insuficientes"}

    meses = sorted(historico_mensal.keys())
    saidas = [historico_mensal[m]["saida"] for m in meses]
    entradas = [historico_mensal[m]["entrada"] for m in meses]

    # Analisa últimos 3 meses vs 3 anteriores
    if len(saidas) >= 6:
        media_antiga_saida = statistics.mean(saidas[-6:-3])
        media_recente_saida = statistics.mean(saidas[-3:])
        variacao_saida = ((media_recente_saida - media_antiga_saida) / media_antiga_saida * 100
                         if media_antiga_saida > 0 else 0)

        media_antiga_entrada = statistics.mean(entradas[-6:-3])
        media_recente_entrada = statistics.mean(entradas[-3:])
        variacao_entrada = ((media_recente_entrada - media_antiga_entrada) / media_antiga_entrada * 100
                           if media_antiga_entrada > 0 else 0)
    else:
        variacao_saida = 0
        variacao_entrada = 0

    alertas = []
    if variacao_saida > 20:
        alertas.append(f"⚠️ Gastos aumentaram {variacao_saida:.1f}% nos últimos 3 meses")
    if variacao_entrada < -15:
        alertas.append(f"⚠️ Receitas caíram {abs(variacao_entrada):.1f}% nos últimos 3 meses")
    if variacao_saida > 30:
        alertas.append("🚨 Aceleração de gastos detectada!")

    return {
        "tendencia_gastos": "crescimento" if variacao_saida > 5 else "queda" if variacao_saida < -5 else "estavel",
        "tendencia_receitas": "crescimento" if variacao_entrada > 5 else "queda" if variacao_entrada < -5 else "estavel",
        "variacao_gastos_pct": round(variacao_saida, 2),
        "variacao_receitas_pct": round(variacao_entrada, 2),
        "alertas": alertas
    }

# ==================== INTERFACE DO AGENTE ====================

def agente_analisar_transacao(transacao: dict, todas_transacoes: list) -> dict:
    """
    Analisa transação: primeiro localmente, LLM só se necessário
    """
    chave_cache = f"analise_t_{transacao.get('id', '')}"
    cached = cache.get(chave_cache)
    if cached:
        return cached

    # Análise local primeiro
    anomalias = detectar_anomalias_local(todas_transacoes)
    e_anomalia = any(a['transacao_id'] == transacao.get('id') for a in anomalias)

    resultado = {
        "transacao_id": transacao.get('id'),
        "anormal": e_anomalia,
        "fonte": "local"
    }

    # Só usa LLM se anomalia detectada ou valor muito alto
    if e_anomalia and _modelo_atual["nome"]:
        stats = calcular_estatisticas_mensais(todas_transacoes)
        mes_atual = datetime.now().strftime('%Y-%m')
        hist = stats.get(mes_atual, {"entrada": 0, "saida": 0})

        prompt = _prompt_analise_transacao(transacao, {
            "media": statistics.mean([t['valor'] for t in todas_transacoes]) if todas_transacoes else 0,
            "periodo_similar": hist.get('saida', 0) if transacao.get('tipo') == 'saida' else hist.get('entrada', 0)
        })

        resposta = _chamar_llm(prompt, max_tokens=150)
        if resposta:
            try:
                llm_data = json.loads(resposta)
                resultado.update(llm_data)
                resultado["fonte"] = "llm"
            except Exception:
                pass

    cache.set(chave_cache, resultado, ttl=600)
    return resultado

def agente_projecao(transacoes: list, meses: int = 3, usar_llm: bool = True) -> dict:
    """Projeção financeira com opção de usar LLM"""
    historico = calcular_estatisticas_mensais(transacoes)
    projecoes_local = projecao_local(historico, meses)
    tendencia = detectar_tendencia_local(historico)

    resultado = {
        "projecoes": projecoes_local,
        "tendencia": tendencia,
        "historico_mensal": historico,
        "fonte": "local"
    }

    # Enriquece com LLM se disponível
    if usar_llm and _modelo_atual["nome"] and len(historico) >= 3:
        chave_cache = f"proj_{hashlib.md5(str(sorted(historico.keys())).encode()).hexdigest()[:8]}"
        cached_llm = cache.get(chave_cache)

        if not cached_llm:
            hist_lista = [{"mes": k, **v} for k, v in sorted(historico.items())]
            prompt = _prompt_projecao(hist_lista, meses)
            resposta = _chamar_llm(prompt, max_tokens=300)

            if resposta:
                try:
                    llm_data = json.loads(resposta)
                    cache.set(chave_cache, llm_data, ttl=3600)
                    resultado["projecao_ia"] = llm_data
                    resultado["fonte"] = "hibrido"
                except Exception:
                    pass
        else:
            resultado["projecao_ia"] = cached_llm
            resultado["fonte"] = "hibrido"

    return resultado

def agente_chat(mensagem: str, user_id: str, contexto_financeiro: dict) -> str:
    """Chat livre com o agente de IA"""
    if not _modelo_atual["nome"]:
        return "Nenhum modelo de IA configurado. Por favor, peça ao administrador para configurar um modelo."

    # Verifica se é comando de extração de transação
    palavras_transacao = ['gastei', 'recebi', 'paguei', 'comprei', 'vendi', 'transferi']
    e_transacao = any(p in mensagem.lower() for p in palavras_transacao)

    if e_transacao:
        # Usa prompt otimizado para extração
        prompt = _prompt_extrair_transacao(mensagem)
        resposta = _chamar_llm(prompt, max_tokens=150)

        if resposta:
            try:
                dados = json.loads(resposta)
                if dados.get('confianca') in ['media', 'alta']:
                    return json.dumps({
                        "tipo": "transacao_detectada",
                        "dados": dados,
                        "mensagem": f"Detectei uma transação: {dados.get('tipo')} de R$ {dados.get('valor', 0):.2f} em {dados.get('nome_fantasia', '')}. Confirma?"
                    })
            except Exception:
                pass

    # Chat livre
    prompt = _prompt_chat_livre(mensagem, contexto_financeiro)
    resposta = _chamar_llm(prompt, max_tokens=200)

    return resposta or "Desculpe, não consegui processar sua mensagem. Tente novamente."

def agente_interpretar_extrato_texto(texto_extraido: list, categorias_existentes: list) -> list:
    """
    Interpreta extrato bancário com ajuda da IA
    Usa análise local + LLM para categorização
    """
    from modulos.pdf_parser import _parsear_linhas, _normalizar_valor, _normalizar_data, _determinar_tipo

    transacoes = _parsear_linhas(texto_extraido)

    # Auto-categorização por nome fantasia
    mapa_categorias = {}
    for cat in categorias_existentes:
        for nome in cat.get('nomes_fantasia', []):
            mapa_categorias[nome.lower()] = cat['id']

    for t in transacoes:
        nome_lower = t.get('nome_fantasia', '').lower()
        # Busca parcial
        for nome_cat, cat_id in mapa_categorias.items():
            if nome_cat in nome_lower or nome_lower in nome_cat:
                t['categoria_id'] = cat_id
                break

    return transacoes

def agente_analise_completa(user_id: str, transacoes: list, categorias: list) -> dict:
    """Análise completa do perfil financeiro do usuário"""
    chave_cache = f"analise_completa_{user_id}"
    cached = cache.get(chave_cache)
    if cached:
        return cached

    historico = calcular_estatisticas_mensais(transacoes)
    tendencia = detectar_tendencia_local(historico)
    anomalias = detectar_anomalias_local(transacoes)
    projecoes = projecao_local(historico, 3)

    # Resumo por categoria
    resumo_categorias = {}
    for t in transacoes:
        cat_id = t.get('categoria_id')
        if cat_id:
            if cat_id not in resumo_categorias:
                resumo_categorias[cat_id] = {"entrada": 0, "saida": 0}
            if t.get('tipo') == 'entrada':
                resumo_categorias[cat_id]["entrada"] += t.get('valor', 0)
            else:
                resumo_categorias[cat_id]["saida"] += t.get('valor', 0)

    resultado = {
        "historico_mensal": historico,
        "tendencia": tendencia,
        "anomalias": anomalias,
        "projecoes": projecoes,
        "resumo_categorias": resumo_categorias,
        "gerado_em": datetime.now().isoformat()
    }

    cache.set(chave_cache, resultado, ttl=1800)  # 30 min cache
    return resultado

def agente_aprender_comportamento(user_id: str, transacoes: list):
    """
    Salva perfil comportamental do usuário para aprendizado
    Dados anonimizados - apenas padrões estatísticos
    """
    if len(transacoes) < 10:
        return

    historico = calcular_estatisticas_mensais(transacoes)

    # Apenas estatísticas agregadas - sem dados identificáveis
    perfil = {
        "media_entrada_mensal": round(
            statistics.mean([v["entrada"] for v in historico.values()]) if historico else 0, 2
        ),
        "media_saida_mensal": round(
            statistics.mean([v["saida"] for v in historico.values()]) if historico else 0, 2
        ),
        "variabilidade": round(
            statistics.stdev([v["saida"] for v in historico.values()]) if len(historico) > 1 else 0, 2
        ),
        "meses_dados": len(historico)
    }

    # Salva em arquivo global anonimizado
    from pathlib import Path
    import json
    import threading

    perfil_path = Path("dados/sistema/perfis_anonimos.json")
    lock = threading.Lock()

    with lock:
        try:
            if perfil_path.exists():
                with open(perfil_path) as f:
                    perfis = json.load(f)
            else:
                perfis = {}

            # ID anonimizado
            import hashlib
            uid_anon = hashlib.sha256(user_id.encode()).hexdigest()[:16]
            perfis[uid_anon] = perfil

            with open(perfil_path, 'w') as f:
                json.dump(perfis, f)
        except Exception:
            pass

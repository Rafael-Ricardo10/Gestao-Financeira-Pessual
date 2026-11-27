"""
Sistema de Gestão Financeira com IA
Arquivo principal - Servidor Flask HTTPS na porta 6300
Produção: gunicorn -c gunicorn.conf.py app:app
"""

import os
import sys
import json
import threading
import secrets
import time
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

from flask import (
    Flask, request, jsonify, make_response,
    send_file, render_template, send_from_directory
)
import io

# ── Garante estrutura de pastas ───────────────────────────────────
Path("dados").mkdir(exist_ok=True)
Path("dados/logs").mkdir(exist_ok=True)
Path("dados/ssl").mkdir(exist_ok=True)
Path("dados/usuarios").mkdir(exist_ok=True)
Path("dados/sistema").mkdir(exist_ok=True)
Path("modulos").mkdir(exist_ok=True)
Path("templates").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

init_path = Path("modulos/__init__.py")
if not init_path.exists():
    init_path.touch()

# ── Imports dos módulos internos ──────────────────────────────────
from modulos.database import inicializar_db, limpar_usuarios_inativos
from modulos.auth import (
    fazer_login, requer_auth, requer_admin,
    obter_chave_da_sessao
)
from modulos.cache import cache, iniciar_limpeza_periodica
from modulos.logs import registrar_log, inicializar_logs
from modulos.ssl_config import gerar_certificado_ssl
from modulos.transacoes import (
    adicionar_transacao, editar_transacao, excluir_transacao,
    listar_transacoes, calcular_saldo, obter_nomes_fantasia_unicos
)
from modulos.categorias import (
    criar_categoria, editar_categoria, excluir_categoria,
    adicionar_nome_fantasia_categoria, remover_nome_fantasia_categoria,
    atribuir_categoria_transacao, listar_categorias
)
from modulos.agente import (
    agente_analisar_transacao, agente_projecao, agente_chat,
    agente_analise_completa, agente_aprender_comportamento,
    listar_modelos_ollama, definir_modelo, obter_modelo_atual,
    detectar_anomalias_local
)
from modulos.admin import exportar_todos_dados, importar_dados, obter_estatisticas_sistema
from modulos.pdf_parser import processar_pdf_extrato
from modulos.database import (
    registrar_usuario, listar_usuarios_admin,
    suspender_usuario, excluir_usuario,
    alterar_senha_usuario, carregar_dados_usuario,
    salvar_dados_usuario, obter_chave_usuario,
    _carregar_indice_usuarios, _salvar_indice_usuarios
)

# ── Aplicação Flask ───────────────────────────────────────────────
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = secrets.token_hex(64)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,
)


# ── Helpers internos ──────────────────────────────────────────────
def _get_chave_usuario(user_id: str) -> bytes:
    chave_sessao = request.cookies.get('chave_sessao') or \
                   request.headers.get('X-Chave-Sessao')
    if not chave_sessao:
        raise ValueError("Sessão de criptografia não encontrada")
    return obter_chave_da_sessao(chave_sessao, user_id)


def _resposta_erro(mensagem: str, codigo: int = 400):
    return jsonify({"erro": mensagem, "sucesso": False}), codigo


def _resposta_ok(dados: dict = None, mensagem: str = "OK"):
    resp = {"sucesso": True, "mensagem": mensagem}
    if dados:
        resp.update(dados)
    return jsonify(resp), 200


def _aprender_async(user_id, chave):
    try:
        dados = carregar_dados_usuario(user_id, chave)
        agente_aprender_comportamento(user_id, dados.get('transacoes', []))
    except Exception:
        pass


def _tarefa_limpeza():
    """Thread de limpeza diária de usuários inativos"""
    while True:
        time.sleep(86400)
        try:
            limpar_usuarios_inativos()
        except Exception as e:
            registrar_log("sistema", f"Erro na limpeza: {str(e)}")


# ==================== ROTAS PRINCIPAIS ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/admin')
def admin_panel():
    return render_template('admin.html')


# ==================== AUTH ====================

@app.route('/api/login', methods=['POST'])
def rota_login():
    dados = request.get_json() or {}
    username = dados.get('username', '').strip()
    password = dados.get('password', '')
    ip = request.remote_addr or '0.0.0.0'
    if not username or not password:
        return _resposta_erro("Usuário e senha são obrigatórios")
    sucesso, resultado = fazer_login(username, password, ip)
    if not sucesso:
        return _resposta_erro(resultado.get('erro', 'Credenciais inválidas'), 401)
    response = jsonify({
        "sucesso": True,
        "token": resultado['token'],
        "username": resultado['username'],
        "is_admin": resultado['is_admin'],
        "chave_sessao": resultado['chave_sessao'],
        "deve_trocar_senha": resultado.get('deve_trocar_senha', False)
    })
    response.set_cookie('auth_token', resultado['token'],
        httponly=True, secure=True, samesite='Strict', max_age=8*3600)
    response.set_cookie('chave_sessao', resultado['chave_sessao'],
        httponly=True, secure=True, samesite='Strict', max_age=8*3600)
    return response


@app.route('/api/registro', methods=['POST'])
def rota_registro():
    dados = request.get_json() or {}
    sucesso, resultado = registrar_usuario(
        dados.get('username', '').strip(),
        dados.get('password', '')
    )
    if not sucesso:
        return _resposta_erro(resultado)
    return _resposta_ok(mensagem="Usuário registrado com sucesso")


@app.route('/api/usuario/senha', methods=['PUT'])
@requer_auth
def rota_alterar_senha():
    dados = request.get_json() or {}
    sucesso, msg = alterar_senha_usuario(
        request.user_id,
        dados.get('senha_atual', ''),
        dados.get('nova_senha', '')
    )
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


# ==================== TRANSAÇÕES ====================

@app.route('/api/transacoes', methods=['GET'])
@requer_auth
def rota_listar_transacoes():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)

    filtros = {}
    for campo in ['nome_fantasia', 'descricao', 'tipo', 'categoria_id',
                  'data_inicio', 'data_fim', 'texto_livre']:
        val = request.args.get(campo)
        if val:
            filtros[campo] = val

    valor_min = request.args.get('valor_min')
    valor_max = request.args.get('valor_max')
    limite    = int(request.args.get('limite', 9999))

    transacoes = listar_transacoes(request.user_id, chave, filtros or None)

    if valor_min:
        try:
            transacoes = [t for t in transacoes if t['valor'] >= float(valor_min)]
        except Exception:
            pass
    if valor_max:
        try:
            transacoes = [t for t in transacoes if t['valor'] <= float(valor_max)]
        except Exception:
            pass

    return jsonify({
        "sucesso": True,
        "transacoes": transacoes[:limite],
        "total": len(transacoes)
    })


@app.route('/api/transacoes', methods=['POST'])
@requer_auth
def rota_adicionar_transacao():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    dados = request.get_json() or {}
    if not dados.get('nome_fantasia'):
        return _resposta_erro("Nome fantasia é obrigatório")
    try:
        valor = float(dados.get('valor', 0))
    except Exception:
        return _resposta_erro("Valor inválido")
    if valor <= 0:
        return _resposta_erro("Valor deve ser maior que zero")
    if dados.get('tipo') not in ['entrada', 'saida']:
        return _resposta_erro("Tipo deve ser 'entrada' ou 'saida'")
    sucesso, resultado = adicionar_transacao(
        request.user_id, chave,
        tipo=dados['tipo'],
        valor=valor,
        nome_fantasia=dados['nome_fantasia'],
        descricao=dados.get('descricao', ''),
        categoria_id=dados.get('categoria_id'),
        data=dados.get('data'),
        origem=dados.get('origem', 'manual')
    )
    if not sucesso:
        return _resposta_erro(resultado)
    threading.Thread(
        target=_aprender_async,
        args=(request.user_id, chave),
        daemon=True
    ).start()
    return _resposta_ok({"transacao_id": resultado}, "Transação adicionada")


@app.route('/api/transacoes/<tid>', methods=['PUT'])
@requer_auth
def rota_editar_transacao(tid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    campos = request.get_json() or {}
    if 'valor' in campos:
        campos['valor'] = float(campos['valor'])
    sucesso, msg = editar_transacao(request.user_id, chave, tid, campos)
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


@app.route('/api/transacoes/<tid>', methods=['DELETE'])
@requer_auth
def rota_excluir_transacao(tid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    sucesso, msg = excluir_transacao(request.user_id, chave, tid)
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


@app.route('/api/transacoes/saldo', methods=['GET'])
@requer_auth
def rota_saldo():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    saldo = calcular_saldo(request.user_id, chave, request.args.get('categoria_id'))
    return jsonify({"sucesso": True, **saldo})


@app.route('/api/transacoes/nomes-fantasia', methods=['GET'])
@requer_auth
def rota_nomes_fantasia():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    nomes = obter_nomes_fantasia_unicos(request.user_id, chave)
    return jsonify({"sucesso": True, "nomes": nomes})


@app.route('/api/transacoes/<tid>/categoria', methods=['PUT'])
@requer_auth
def rota_atribuir_categoria_transacao(tid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    dados = request.get_json() or {}
    sucesso, msg = atribuir_categoria_transacao(
        request.user_id, chave, tid, dados.get('categoria_id')
    )
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


# ==================== CATEGORIAS ====================

@app.route('/api/categorias', methods=['GET'])
@requer_auth
def rota_listar_categorias():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    cats = listar_categorias(request.user_id, chave)
    return jsonify({"sucesso": True, "categorias": cats})


@app.route('/api/categorias', methods=['POST'])
@requer_auth
def rota_criar_categoria():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    dados = request.get_json() or {}
    if not dados.get('nome'):
        return _resposta_erro("Nome é obrigatório")
    meta = None
    if dados.get('meta_valor'):
        try:
            meta = float(dados['meta_valor'])
        except Exception:
            return _resposta_erro("meta_valor inválido")
    sucesso, resultado = criar_categoria(
        request.user_id, chave,
        nome=dados['nome'],
        tipo=dados.get('tipo', 'organizacao'),
        meta_valor=meta,
        descricao=dados.get('descricao', ''),
        emp_dados=dados.get('emp_dados')
    )
    if not sucesso:
        return _resposta_erro(resultado)
    return _resposta_ok({"categoria_id": resultado}, "Categoria criada")


@app.route('/api/categorias/<cid>', methods=['PUT'])
@requer_auth
def rota_editar_categoria(cid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    campos = request.get_json() or {}
    if 'meta_valor' in campos and campos['meta_valor']:
        try:
            campos['meta_valor'] = float(campos['meta_valor'])
        except Exception:
            pass
    sucesso, msg = editar_categoria(request.user_id, chave, cid, campos)
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


@app.route('/api/categorias/<cid>', methods=['DELETE'])
@requer_auth
def rota_excluir_categoria(cid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    sucesso, msg = excluir_categoria(request.user_id, chave, cid)
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


@app.route('/api/categorias/<cid>/nomes-fantasia', methods=['POST'])
@requer_auth
def rota_add_nome_fantasia(cid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    dados = request.get_json() or {}
    nome = dados.get('nome_fantasia', '').strip()
    if not nome:
        return _resposta_erro("nome_fantasia é obrigatório")
    sucesso, msg = adicionar_nome_fantasia_categoria(request.user_id, chave, cid, nome)
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


@app.route('/api/categorias/<cid>/nomes-fantasia', methods=['DELETE'])
@requer_auth
def rota_rem_nome_fantasia(cid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    dados = request.get_json() or {}
    nome = dados.get('nome_fantasia', '').strip()
    if not nome:
        return _resposta_erro("nome_fantasia é obrigatório")
    sucesso, msg = remover_nome_fantasia_categoria(request.user_id, chave, cid, nome)
    if not sucesso:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


@app.route('/api/categorias/<cid>/quitar', methods=['POST'])
@requer_auth
def rota_quitar_emprestimo(cid):
    """Marca empréstimo como quitado"""
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    try:
        dados = carregar_dados_usuario(request.user_id, chave)
        for i, cat in enumerate(dados.get('categorias', [])):
            if cat['id'] == cid and cat.get('tipo') == 'emprestimo':
                if 'emp_dados' not in dados['categorias'][i]:
                    dados['categorias'][i]['emp_dados'] = {}
                dados['categorias'][i]['emp_dados']['quitado'] = True
                dados['categorias'][i]['emp_dados']['quitado_em'] = datetime.now().isoformat()
                salvar_dados_usuario(request.user_id, dados, chave)
                cache.invalidar_usuario(request.user_id)
                return _resposta_ok(mensagem="Empréstimo marcado como quitado")
        return _resposta_erro("Empréstimo não encontrado")
    except Exception as e:
        registrar_log("categorias", f"Erro ao quitar empréstimo: {str(e)}")
        return _resposta_erro(str(e))


# ==================== AGENTE ====================

@app.route('/api/agente/modelo', methods=['GET'])
@requer_auth
def rota_get_modelo():
    return jsonify({"sucesso": True, "modelo": obter_modelo_atual()})


@app.route('/api/agente/modelo', methods=['POST'])
@requer_admin
def rota_set_modelo():
    dados = request.get_json() or {}
    modelo = dados.get('modelo', '').strip()
    if not modelo:
        return _resposta_erro("modelo é obrigatório")
    definir_modelo(modelo)
    cache.delete("ollama_modelos")
    return _resposta_ok(mensagem=f"Modelo definido: {modelo}")


@app.route('/api/agente/modelos', methods=['GET'])
@requer_auth
def rota_listar_modelos():
    modelos = listar_modelos_ollama()
    return jsonify({
        "sucesso": True,
        "modelos": modelos,
        "modelo_atual": obter_modelo_atual()
    })


@app.route('/api/agente/chat', methods=['POST'])
@requer_auth
def rota_chat():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)

    dados_req = request.get_json() or {}
    mensagem  = dados_req.get('mensagem', '').strip()
    if not mensagem:
        return _resposta_erro("mensagem é obrigatória")

    chave_ctx = f"ctx_financeiro_{request.user_id}"
    contexto  = cache.get(chave_ctx)

    if not contexto:
        try:
            saldo    = calcular_saldo(request.user_id, chave)
            dados_u  = carregar_dados_usuario(request.user_id, chave)
            trans    = dados_u.get('transacoes', [])
            cats     = dados_u.get('categorias', [])
            mes      = datetime.now().strftime('%Y-%m')
            trans_mes = [t for t in trans if t.get('data', '').startswith(mes)]

            cats_info = [
                {
                    "nome": c['nome'],
                    "tipo": c['tipo'],
                    "descricao": c.get('descricao', ''),
                    "saldo": c.get('saldo', 0)
                }
                for c in cats
            ]
            emp_ativos = [
                c for c in cats
                if c.get('tipo') == 'emprestimo'
                and not c.get('emp_dados', {}).get('quitado')
            ]

            contexto = {
                "saldo": saldo.get('saldo', 0),
                "entrada_mes": sum(
                    t['valor'] for t in trans_mes if t.get('tipo') == 'entrada'
                ),
                "saida_mes": sum(
                    t['valor'] for t in trans_mes if t.get('tipo') == 'saida'
                ),
                "qtd_categorias": len(cats),
                "categorias": cats_info,
                "emprestimos_ativos": len(emp_ativos),
            }
            cache.set(chave_ctx, contexto, ttl=300)
        except Exception:
            contexto = {}

    resposta = agente_chat(mensagem, request.user_id, contexto)
    return jsonify({"sucesso": True, "resposta": resposta})


@app.route('/api/agente/projecao', methods=['GET'])
@requer_auth
def rota_projecao():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    meses      = int(request.args.get('meses', 3))
    chave_cache = f"proj_{request.user_id}_{meses}"
    cached     = cache.get(chave_cache)
    if cached:
        return jsonify({"sucesso": True, **cached})
    dados     = carregar_dados_usuario(request.user_id, chave)
    resultado = agente_projecao(dados.get('transacoes', []), meses, True)
    cache.set(chave_cache, resultado, ttl=1800)
    return jsonify({"sucesso": True, **resultado})


@app.route('/api/agente/anomalias', methods=['GET'])
@requer_auth
def rota_anomalias():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    chave_cache = f"anomalias_{request.user_id}"
    cached      = cache.get(chave_cache)
    if cached:
        return jsonify({"sucesso": True, "anomalias": cached})
    dados     = carregar_dados_usuario(request.user_id, chave)
    anomalias = detectar_anomalias_local(dados.get('transacoes', []))
    cache.set(chave_cache, anomalias, ttl=900)
    return jsonify({"sucesso": True, "anomalias": anomalias})


@app.route('/api/agente/analisar-transacao/<tid>', methods=['GET'])
@requer_auth
def rota_analisar_transacao(tid):
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    dados    = carregar_dados_usuario(request.user_id, chave)
    trans    = dados.get('transacoes', [])
    transacao = next((t for t in trans if t['id'] == tid), None)
    if not transacao:
        return _resposta_erro("Transação não encontrada", 404)
    resultado = agente_analisar_transacao(transacao, trans)
    return jsonify({"sucesso": True, **resultado})


@app.route('/api/agente/analise-completa', methods=['GET'])
@requer_auth
def rota_analise_completa():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)
    dados     = carregar_dados_usuario(request.user_id, chave)
    resultado = agente_analise_completa(
        request.user_id,
        dados.get('transacoes', []),
        dados.get('categorias', [])
    )
    return jsonify({"sucesso": True, **resultado})


# ==================== EXTRATO PDF ====================

def _gerar_chave_dedup(tipo: str, valor: float, data: str, nome: str) -> str:
    """Chave MD5 para detectar transações duplicadas"""
    conteudo = f"{tipo}|{valor:.2f}|{data}|{nome[:30].lower().strip()}"
    return hashlib.md5(conteudo.encode()).hexdigest()


@app.route('/api/extrato/pdf', methods=['POST'])
@requer_auth
def rota_processar_pdf():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)

    if 'arquivo' not in request.files:
        return _resposta_erro("Arquivo PDF não encontrado")
    arquivo = request.files['arquivo']
    if not arquivo.filename.lower().endswith('.pdf'):
        return _resposta_erro("Arquivo deve ser PDF")

    sucesso, transacoes, mensagem = processar_pdf_extrato(arquivo.read())
    if not sucesso:
        return _resposta_erro(mensagem)

    try:
        dados          = carregar_dados_usuario(request.user_id, chave)
        trans_existentes = dados.get('transacoes', [])
        cats           = dados.get('categorias', [])

        chaves_existentes = set()
        for t in trans_existentes:
            chaves_existentes.add(_gerar_chave_dedup(
                t.get('tipo', ''), t.get('valor', 0),
                t.get('data', ''), t.get('nome_fantasia', '')
            ))

        novas      = []
        duplicatas = 0
        for t in transacoes:
            chave_t = _gerar_chave_dedup(
                t.get('tipo', ''), t.get('valor', 0),
                t.get('data', ''), t.get('nome_fantasia', '')
            )
            if chave_t in chaves_existentes:
                duplicatas += 1
            else:
                novas.append(t)

        # Auto-categorização
        if cats:
            mapa = {}
            for cat in cats:
                for nome_f in cat.get('nomes_fantasia', []):
                    mapa[nome_f.lower()] = cat['id']
            for t in novas:
                nome_lower = t.get('nome_fantasia', '').lower()
                for nome_cat, cat_id in mapa.items():
                    if nome_cat in nome_lower or nome_lower in nome_cat:
                        t['categoria_id'] = cat_id
                        break

        return jsonify({
            "sucesso": True,
            "transacoes": novas,
            "mensagem": mensagem,
            "duplicatas_ignoradas": duplicatas,
            "total_original": len(transacoes)
        })
    except Exception as e:
        registrar_log("extrato", f"Erro ao processar: {str(e)}")
        return jsonify({
            "sucesso": True,
            "transacoes": transacoes,
            "mensagem": mensagem
        })


@app.route('/api/extrato/importar', methods=['POST'])
@requer_auth
def rota_importar_extrato():
    try:
        chave = _get_chave_usuario(request.user_id)
    except ValueError as e:
        return _resposta_erro(str(e), 401)

    dados_req  = request.get_json() or {}
    transacoes = dados_req.get('transacoes', [])
    if not transacoes:
        return _resposta_erro("Nenhuma transação para importar")

    try:
        dados_usr  = carregar_dados_usuario(request.user_id, chave)
        trans_exist = dados_usr.get('transacoes', [])
        chaves_exist = set()
        for t in trans_exist:
            chaves_exist.add(_gerar_chave_dedup(
                t.get('tipo', ''), t.get('valor', 0),
                t.get('data', ''), t.get('nome_fantasia', '')
            ))
    except Exception:
        chaves_exist = set()

    importadas = erros = duplicatas = 0
    for t in transacoes:
        chave_t = _gerar_chave_dedup(
            t.get('tipo', 'saida'), float(t.get('valor', 0)),
            t.get('data', ''), t.get('nome_fantasia', '')
        )
        if chave_t in chaves_exist:
            duplicatas += 1
            continue
        try:
            sucesso, _ = adicionar_transacao(
                request.user_id, chave,
                tipo=t.get('tipo', 'saida'),
                valor=float(t.get('valor', 0)),
                nome_fantasia=t.get('nome_fantasia', 'Importado'),
                descricao=t.get('descricao', ''),
                categoria_id=t.get('categoria_id'),
                data=t.get('data'),
                origem='importacao_pdf'
            )
            if sucesso:
                importadas += 1
                chaves_exist.add(chave_t)
            else:
                erros += 1
        except Exception:
            erros += 1

    return _resposta_ok(
        {"importadas": importadas, "erros": erros, "duplicatas": duplicatas},
        f"{importadas} importadas, {duplicatas} duplicatas ignoradas"
    )


# ==================== ADMIN ====================

@app.route('/api/admin/usuarios', methods=['GET'])
@requer_admin
def rota_admin_usuarios():
    return jsonify({"sucesso": True, "usuarios": listar_usuarios_admin()})


@app.route('/api/admin/usuarios/<uid>/suspender', methods=['POST'])
@requer_admin
def rota_admin_suspender(uid):
    if uid == request.user_id:
        return _resposta_erro("Não pode suspender a si mesmo")
    dados = request.get_json() or {}
    ok    = suspender_usuario(request.user_id, uid, dados.get('suspender', True))
    if not ok:
        return _resposta_erro("Operação falhou")
    return _resposta_ok(mensagem="Status atualizado")


@app.route('/api/admin/usuarios/<uid>', methods=['DELETE'])
@requer_admin
def rota_admin_excluir_usuario(uid):
    if uid == request.user_id:
        return _resposta_erro("Não pode excluir a si mesmo")
    ok = excluir_usuario(request.user_id, uid)
    if not ok:
        return _resposta_erro("Operação falhou")
    return _resposta_ok(mensagem="Usuário excluído")


@app.route('/api/admin/estatisticas', methods=['GET'])
@requer_admin
def rota_admin_stats():
    return jsonify({"sucesso": True, **obter_estatisticas_sistema()})


@app.route('/api/admin/logs', methods=['GET'])
@requer_admin
def rota_admin_logs():
    from modulos.logs import obter_logs
    return jsonify({"sucesso": True, "logs": obter_logs()})


@app.route('/api/admin/logs/<log_id>/resolver', methods=['POST'])
@requer_admin
def rota_admin_resolver_log(log_id):
    from modulos.logs import marcar_resolvido
    ok = marcar_resolvido(log_id)
    if not ok:
        return _resposta_erro("Log não encontrado")
    return _resposta_ok(mensagem="Log resolvido")


@app.route('/api/admin/exportar', methods=['GET'])
@requer_admin
def rota_admin_exportar():
    try:
        dados_zip = exportar_todos_dados()
        nome = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        return send_file(
            io.BytesIO(dados_zip),
            mimetype='application/zip',
            as_attachment=True,
            download_name=nome
        )
    except Exception as e:
        registrar_log("admin", f"Erro ao exportar: {str(e)}")
        return _resposta_erro("Erro ao gerar backup")


@app.route('/api/admin/importar', methods=['POST'])
@requer_admin
def rota_admin_importar():
    if 'arquivo' not in request.files:
        return _resposta_erro("Arquivo não encontrado")
    ok, msg = importar_dados(request.files['arquivo'].read())
    if not ok:
        return _resposta_erro(msg)
    return _resposta_ok(mensagem=msg)


@app.route('/api/health', methods=['GET'])
def rota_health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    })


# ==================== HEADERS DE SEGURANÇA ====================

@app.after_request
def headers_seguranca(response):
    response.headers['X-Content-Type-Options']    = 'nosniff'
    response.headers['X-Frame-Options']           = 'DENY'
    response.headers['X-XSS-Protection']          = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy']   = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    return response


# ==================== INICIALIZAÇÃO DO SISTEMA ====================

def inicializar_sistema():
    """
    Inicializa todos os módulos do sistema.
    Chamado tanto pelo Gunicorn (via on_starting) quanto
    pela execução direta (python3 app.py).
    """
    print("=" * 60)
    print("  💰 FinanceIA - Gestão Financeira com IA")
    print("=" * 60)

    inicializar_logs()
    inicializar_db()
    iniciar_limpeza_periodica()

    # Thread de limpeza diária
    threading.Thread(target=_tarefa_limpeza, daemon=True).start()

    # Tenta conectar ao Ollama
    modelos = listar_modelos_ollama()
    if modelos:
        definir_modelo(modelos[0])
        print(f"[✔] Ollama: {len(modelos)} modelo(s) — padrão: {modelos[0]}")
    else:
        print("[!] Ollama não disponível — IA desativada")

    print("[✔] Sistema inicializado com sucesso")
    print("=" * 60)


# ==================== ENTRY POINT GUNICORN ====================
# O Gunicorn importa este módulo e usa o objeto 'app' diretamente.
# A inicialização é feita pelo hook on_starting do gunicorn.conf.py
# para garantir que rode apenas UMA vez no processo master.


# ==================== ENTRY POINT DIRETO ====================

def main():
    """Execução direta: python3 app.py (desenvolvimento/teste)"""
    inicializar_sistema()

    cert_file = key_file = None
    try:
        cert_file, key_file = gerar_certificado_ssl()
        print("[✔] Certificado SSL gerado/carregado.")
    except Exception as e:
        print(f"[!] SSL indisponível: {e}")

    porta = 6300
    print(f"\n{'=' * 60}")
    if cert_file:
        print(f"  🔒 https://localhost:{porta}")
    else:
        print(f"  ⚠️  http://localhost:{porta}  (sem SSL)")
    print(f"  👤 Admin padrão: admin / admin")
    print(f"{'=' * 60}\n")

    if cert_file and key_file:
        try:
            app.run(
                host='0.0.0.0',
                port=porta,
                ssl_context=(cert_file, key_file),
                debug=False,
                threaded=True,
                use_reloader=False
            )
        except Exception as e:
            print(f"[!] SSL falhou, subindo sem SSL: {e}")
            app.run(
                host='0.0.0.0',
                port=porta,
                debug=False,
                threaded=True,
                use_reloader=False
            )
    else:
        app.run(
            host='0.0.0.0',
            port=porta,
            debug=False,
            threaded=True,
            use_reloader=False
        )


if __name__ == '__main__':
    main()

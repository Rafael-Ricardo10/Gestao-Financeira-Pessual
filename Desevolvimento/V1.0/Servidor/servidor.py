#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RRFS Gestão Financeira - SERVIDOR WEB
Interface em http://localhost:6250  (templates/ com HTML+CSS+JS embutidos)
Sincroniza com os apps desktop via Tox (modulos/sync_tox.py).
"""
import os
import re
import sys
import time
import logging
import secrets
import tempfile
import threading
from datetime import datetime
from functools import wraps

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)
os.makedirs('dados', exist_ok=True)
os.makedirs('logs', exist_ok=True)

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)

from modulos import contas, sync_core
from modulos import loans as emp
from modulos.sync_tox import ToxManagerSync
from modulos.importar_db import importar

PORTA = int(os.environ.get('RRFS_PORTA', '6250'))
HOST = os.environ.get('RRFS_HOST', '127.0.0.1')
HOSTS_OK = {'localhost', '127.0.0.1', '[::1]'} | {
    h.strip() for h in os.environ.get('RRFS_HOSTS', '').split(',') if h.strip()}
TIPOS = ('entrada', 'saida')

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler('logs/servidor.log', encoding='utf-8'),
              logging.StreamHandler(sys.stdout)])
log = logging.getLogger('servidor')


def _chave_secreta():
    p = os.path.join('dados', 'secret.key')
    if not os.path.exists(p):
        with open(p, 'wb') as f:
            f.write(secrets.token_bytes(32))
        os.chmod(p, 0o600)
    with open(p, 'rb') as f:
        return f.read()


app = Flask(__name__, template_folder='templates', static_folder=None)
app.secret_key = _chave_secreta()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  MAX_CONTENT_LENGTH=512 * 1024 * 1024,
                  PERMANENT_SESSION_LIFETIME=30 * 86400)
tox = ToxManagerSync(BASE)


# ── segurança básica ────────────────────────────────────────────────

@app.before_request
def _protecao():
    if request.host.rsplit(':', 1)[0] not in HOSTS_OK:
        return jsonify(erro='Host não permitido'), 400
    if request.method in ('POST', 'PUT', 'DELETE'):
        o = request.headers.get('Origin')
        if o and o.split('://', 1)[-1] != request.host:
            return jsonify(erro='Origem inválida'), 403


_falhas = {}


def _bloqueado(chave):
    t = [x for x in _falhas.get(chave, []) if time.time() - x < 600]
    _falhas[chave] = t
    return len(t) >= 8


def login_requerido(f):
    @wraps(f)
    def w(*a, **k):
        if 'u' not in session:
            if request.path.startswith('/api/'):
                return jsonify(erro='Sessão expirada'), 401
            return redirect(url_for('pagina_login'))
        return f(*a, **k)
    return w


def db():
    if 'conn' not in g:
        g.conn = contas.abrir_db(session['u'])
        g.uid = contas.user_id(g.conn)
    return g.conn


@app.teardown_appcontext
def _fechar(_e):
    c = g.pop('conn', None)
    if c is not None:
        c.close()


def _json():
    return request.get_json(silent=True) or {}


def _valor(v, positivo=True):
    try:
        x = round(float(str(v).replace(',', '.')), 2)
    except (TypeError, ValueError):
        return None
    return x if (x > 0 or not positivo) else None


def _data(s):
    try:
        return datetime.strptime(str(s), '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        return None


# ── páginas ─────────────────────────────────────────────────────────

def _pagina(nome):
    return render_template(f'{nome}.html', usuario=session.get('u'),
                           pagina=nome)


@app.route('/')
def raiz():
    return redirect(url_for('pagina_dashboard' if 'u' in session
                            else 'pagina_login'))


@app.route('/login')
def pagina_login():
    return _pagina('login')


for _n in ('dashboard', 'transacoes', 'categorias', 'emprestimos', 'config'):
    app.add_url_rule(
        f'/{_n}',
        endpoint=f'pagina_{_n}',
        view_func=login_requerido((lambda n: lambda: _pagina(n))(_n))
    )


# ── autenticação ────────────────────────────────────────────────────

@app.post('/api/registrar')
def api_registrar():
    d = _json()
    ok, erro = contas.criar_conta(d.get('usuario'), d.get('senha'))
    if not ok:
        return jsonify(erro=erro), 400
    session.clear()
    session['u'] = d['usuario'].strip()
    session.permanent = True
    return jsonify(ok=True)


@app.post('/api/entrar')
def api_entrar():
    d = _json()
    u = (d.get('usuario') or '').strip()
    chave = f'{request.remote_addr}|{u.lower()}'
    if _bloqueado(chave):
        return jsonify(erro='Muitas tentativas. Aguarde alguns minutos.'), 429
    if not contas.verificar(u, d.get('senha')):
        _falhas.setdefault(chave, []).append(time.time())
        return jsonify(erro='Usuário ou senha inválidos'), 401
    session.clear()
    session['u'] = u
    session.permanent = True
    return jsonify(ok=True)


@app.post('/api/sair')
def api_sair():
    session.clear()
    return jsonify(ok=True)


@app.post('/api/config/senha')
@login_requerido
def api_senha():
    d = _json()
    ok, erro = contas.trocar_senha(session['u'], d.get('atual'), d.get('nova'))
    return (jsonify(ok=True) if ok else (jsonify(erro=erro), 400))


# ── dashboard ───────────────────────────────────────────────────────

def _meses(n):
    y, m = datetime.now().year, datetime.now().month
    out = []
    for _ in range(n):
        out.append(f'{y:04d}-{m:02d}')
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out[::-1]


@app.get('/api/resumo')
@login_requerido
def api_resumo():
    mes = request.args.get('mes') or datetime.now().strftime('%Y-%m')
    if not re.match(r'^\d{4}-\d{2}$', mes):
        return jsonify(erro='Mês inválido'), 400
    c, u = db(), g.uid
    emp.check_and_complete_loans(c, u)
    saldo = c.execute(
        "SELECT COALESCE(SUM(CASE WHEN transaction_type='entrada' "
        "THEN amount ELSE -amount END),0) FROM transactions WHERE user_id=?",
        (u,)).fetchone()[0]
    mm = {r['t']: r['s'] for r in c.execute(
        "SELECT transaction_type t, SUM(amount) s FROM transactions "
        "WHERE user_id=? AND substr(date,1,7)=? GROUP BY transaction_type",
        (u, mes))}
    cats = [{'nome': r['n'], 'total': r['s']} for r in c.execute(
        "SELECT COALESCE(c.name,'Sem categoria') n, SUM(t.amount) s "
        "FROM transactions t LEFT JOIN categories c ON c.id=t.category_id "
        "WHERE t.user_id=? AND t.transaction_type='saida' "
        "AND substr(t.date,1,7)=? GROUP BY n ORDER BY s DESC LIMIT 12",
        (u, mes))]
    meses = _meses(6)
    por = {}
    for r in c.execute(
            "SELECT substr(date,1,7) m, transaction_type t, SUM(amount) s "
            "FROM transactions WHERE user_id=? AND substr(date,1,7)>=? "
            "GROUP BY m, t", (u, meses[0])):
        por[(r['m'], r['t'])] = r['s']
    serie = [{'mes': m, 'entradas': por.get((m, 'entrada'), 0),
              'saidas': por.get((m, 'saida'), 0)} for m in meses]
    resumo = emp.get_loan_summary(c, u)
    return jsonify(
        saldo=saldo, entradas=mm.get('entrada', 0), saidas=mm.get('saida', 0),
        categorias=cats, serie=serie,
        emprestimos={'divida_total': resumo['divida_total'],
                     'lista': [e for e in resumo['emprestimos']
                               if e['status'] == 'ativo']})


@app.get('/api/cotacoes')
@login_requerido
def api_cotacoes():
    try:
        from modulos.currency_tracker import get_all_current_rates
        return jsonify(get_all_current_rates(db()))
    except Exception as e:
        log.warning('cotações: %s', e)
        return jsonify({})


# ── transações ──────────────────────────────────────────────────────

def _ler_tx(c, u, d):
    v = _valor(d.get('amount'))
    tipo, dt = d.get('transaction_type'), _data(d.get('date'))
    desc = (d.get('description') or '').strip()[:200]
    if v is None:
        return None, 'Valor inválido'
    if tipo not in TIPOS:
        return None, 'Tipo inválido'
    if not dt:
        return None, 'Data inválida'
    if not desc:
        return None, 'Descrição obrigatória'
    cat = d.get('category_id')
    if cat in (None, '', 0, '0'):
        cat = None
    else:
        try:
            cat = int(cat)
        except (TypeError, ValueError):
            return None, 'Categoria inválida'
        if not c.execute('SELECT 1 FROM categories WHERE id=? AND user_id=?',
                         (cat, u)).fetchone():
            return None, 'Categoria inválida'
    return (v, desc, tipo, dt, cat), None


@app.get('/api/transacoes')
@login_requerido
def api_tx_listar():
    c, u = db(), g.uid
    sql = ("SELECT t.id, t.amount, t.description, t.transaction_type, t.date, "
           "t.category_id, c.name categoria FROM transactions t "
           "LEFT JOIN categories c ON c.id=t.category_id WHERE t.user_id=?")
    args = [u]
    mes = request.args.get('mes')
    if mes and re.match(r'^\d{4}-\d{2}$', mes):
        sql += ' AND substr(t.date,1,7)=?'
        args.append(mes)
    if request.args.get('tipo') in TIPOS:
        sql += ' AND t.transaction_type=?'
        args.append(request.args['tipo'])
    q = (request.args.get('q') or '').strip()
    if q:
        sql += ' AND t.description LIKE ?'
        args.append(f'%{q}%')
    sql += ' ORDER BY t.date DESC, t.id DESC LIMIT 500'
    return jsonify([dict(r) for r in c.execute(sql, args)])


@app.post('/api/transacoes')
@login_requerido
def api_tx_criar():
    c, u = db(), g.uid
    v, erro = _ler_tx(c, u, _json())
    if erro:
        return jsonify(erro=erro), 400
    cur = c.execute(
        'INSERT INTO transactions(user_id,amount,description,'
        'transaction_type,date,category_id) VALUES(?,?,?,?,?,?)', (u, *v))
    c.commit()
    return jsonify(ok=True, id=cur.lastrowid)


@app.put('/api/transacoes/<int:tid>')
@login_requerido
def api_tx_editar(tid):
    c, u = db(), g.uid
    if not c.execute('SELECT 1 FROM transactions WHERE id=? AND user_id=?',
                     (tid, u)).fetchone():
        return jsonify(erro='Não encontrada'), 404
    info = emp.is_loan_transaction(c, tid)
    if info.get('type') == 'recebimento':
        return jsonify(erro='Transação de recebimento de empréstimo: '
                            'gerencie pela tela de Empréstimos.'), 400
    v, erro = _ler_tx(c, u, _json())
    if erro:
        return jsonify(erro=erro), 400
    c.execute('UPDATE transactions SET amount=?, description=?, '
              'transaction_type=?, date=?, category_id=? WHERE id=?',
              (*v, tid))
    c.execute('UPDATE loan_payments SET amount=?, payment_date=?, notes=? '
              'WHERE transaction_id=?', (v[0], v[3], v[1], tid))
    c.commit()
    return jsonify(ok=True)


@app.delete('/api/transacoes/<int:tid>')
@login_requerido
def api_tx_excluir(tid):
    c, u = db(), g.uid
    if not c.execute('SELECT 1 FROM transactions WHERE id=? AND user_id=?',
                     (tid, u)).fetchone():
        return jsonify(erro='Não encontrada'), 404
    if emp.is_loan_transaction(c, tid).get('type') == 'recebimento':
        return jsonify(erro='Exclua o empréstimo pela tela de '
                            'Empréstimos.'), 400
    c.execute('DELETE FROM loan_payments WHERE transaction_id=?', (tid,))
    c.execute('DELETE FROM transactions WHERE id=?', (tid,))
    c.commit()
    return jsonify(ok=True)


# ── categorias ──────────────────────────────────────────────────────

@app.get('/api/categorias')
@login_requerido
def api_cat_listar():
    rows = db().execute(
        "SELECT c.id, c.name, c.year, (SELECT COUNT(*) FROM transactions t "
        "WHERE t.category_id=c.id) usos FROM categories c "
        "WHERE c.user_id=? AND COALESCE(c.is_hidden,0)=0 ORDER BY c.name",
        (g.uid,))
    return jsonify([dict(r) for r in rows])


def _nome_cat(c, u, d, ignorar=None):
    nome = (d.get('name') or '').strip()[:60]
    if not nome:
        return None, 'Nome obrigatório'
    if nome.lower().startswith('empréstimo:'):
        return None, 'Nome reservado para empréstimos'
    r = c.execute('SELECT id FROM categories WHERE user_id=? AND '
                  'name=? COLLATE NOCASE AND COALESCE(is_hidden,0)=0',
                  (u, nome)).fetchone()
    if r and r['id'] != ignorar:
        return None, 'Já existe uma categoria com esse nome'
    return nome, None


@app.post('/api/categorias')
@login_requerido
def api_cat_criar():
    c, u = db(), g.uid
    nome, erro = _nome_cat(c, u, _json())
    if erro:
        return jsonify(erro=erro), 400
    c.execute('INSERT INTO categories(user_id,name,year) VALUES(?,?,?)',
              (u, nome, datetime.now().year))
    c.commit()
    return jsonify(ok=True)


@app.put('/api/categorias/<int:cid>')
@login_requerido
def api_cat_editar(cid):
    c, u = db(), g.uid
    r = c.execute('SELECT name FROM categories WHERE id=? AND user_id=?',
                  (cid, u)).fetchone()
    if not r:
        return jsonify(erro='Não encontrada'), 404
    if r['name'].startswith('Empréstimo:'):
        return jsonify(erro='Categoria de empréstimo não pode ser '
                            'renomeada'), 400
    nome, erro = _nome_cat(c, u, _json(), ignorar=cid)
    if erro:
        return jsonify(erro=erro), 400
    c.execute('UPDATE categories SET name=? WHERE id=?', (nome, cid))
    c.commit()
    return jsonify(ok=True)


@app.delete('/api/categorias/<int:cid>')
@login_requerido
def api_cat_excluir(cid):
    c, u = db(), g.uid
    r = c.execute('SELECT name FROM categories WHERE id=? AND user_id=?',
                  (cid, u)).fetchone()
    if not r:
        return jsonify(erro='Não encontrada'), 404
    if r['name'].startswith('Empréstimo:'):
        return jsonify(erro='Gerencie pela tela de Empréstimos'), 400
    usos = c.execute('SELECT COUNT(*) FROM transactions WHERE category_id=?',
                     (cid,)).fetchone()[0]
    if usos:
        c.execute('UPDATE categories SET is_hidden=1 WHERE id=?', (cid,))
        msg = f'Categoria ocultada ({usos} transações mantidas).'
    else:
        c.execute('DELETE FROM categories WHERE id=?', (cid,))
        msg = 'Categoria excluída.'
    c.commit()
    return jsonify(ok=True, mensagem=msg)


# ── empréstimos ─────────────────────────────────────────────────────

def _ler_emp(d):
    nome = (d.get('nome') or '').strip()[:60]
    valor = _valor(d.get('valor'))
    juros = _valor(d.get('juros') or 0, positivo=False)
    desc = _valor(d.get('desconto') or 0, positivo=False)
    try:
        n = int(d.get('parcelas'))
    except (TypeError, ValueError):
        n = 0
    if valor is None or juros is None or juros < 0 or desc is None \
            or desc < 0 or n < 1 or n > 600:
        return None, 'Confira valor, juros, desconto e parcelas'
    return (nome, valor, juros, n, desc), None


@app.post('/api/emprestimos/calcular')
@login_requerido
def api_emp_calcular():
    v, erro = _ler_emp({**_json(), 'nome': 'x'})
    if erro:
        return jsonify(erro=erro), 400
    return jsonify(emp.calculate_loan(v[1], v[2], v[3], v[4]))


@app.get('/api/emprestimos')
@login_requerido
def api_emp_listar():
    c, u = db(), g.uid
    emp.check_and_complete_loans(c, u)
    return jsonify(emp.get_loan_summary(c, u))


@app.post('/api/emprestimos')
@login_requerido
def api_emp_criar():
    c, u = db(), g.uid
    d = _json()
    v, erro = _ler_emp(d)
    if erro or not v[0]:
        return jsonify(erro=erro or 'Nome obrigatório'), 400
    nome, valor, juros, n, desc = v
    data = _data(d.get('data')) or datetime.now().strftime('%Y-%m-%d')
    calc = emp.calculate_loan(valor, juros, n, desc)
    cat = c.execute(
        'INSERT INTO categories(user_id,name,total_amount,is_payment_goal,'
        'year) VALUES(?,?,?,1,?)',
        (u, f'Empréstimo: {nome}', calc['final_amount'],
         datetime.now().year)).lastrowid
    tx = c.execute(
        "INSERT INTO transactions(user_id,amount,description,"
        "transaction_type,date,category_id) VALUES(?,?,?,'entrada',?,?)",
        (u, valor, f'Empréstimo recebido: {nome}', data, cat)).lastrowid
    c.execute(
        'INSERT INTO loans(user_id,name,description,reason,total_amount,'
        'interest_rate,num_installments,discount,final_amount,'
        'installment_amount,start_date,status,transaction_id,category_id) '
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,'ativo',?,?)",
        (u, nome, (d.get('descricao') or '')[:200], (d.get('motivo') or '')[:200],
         valor, juros, n, desc, calc['final_amount'],
         calc['installment_amount'], data, tx, cat))
    c.commit()
    return jsonify(ok=True)


@app.delete('/api/emprestimos/<int:lid>')
@login_requerido
def api_emp_excluir(lid):
    c, u = db(), g.uid
    loan = c.execute('SELECT * FROM loans WHERE id=? AND user_id=?',
                     (lid, u)).fetchone()
    if not loan:
        return jsonify(erro='Não encontrado'), 404
    c.execute('DELETE FROM loan_payments WHERE loan_id=?', (lid,))
    c.execute('DELETE FROM loans WHERE id=?', (lid,))
    if loan['transaction_id']:
        c.execute('DELETE FROM transactions WHERE id=?',
                  (loan['transaction_id'],))
    if loan['category_id']:
        c.execute('UPDATE categories SET is_hidden=1 WHERE id=?',
                  (loan['category_id'],))
    c.commit()
    return jsonify(ok=True)


# ── importar banco antigo ───────────────────────────────────────────

@app.post('/api/config/importar')
@login_requerido
def api_importar():
    f = request.files.get('arquivo')
    if not f:
        return jsonify(erro='Selecione o arquivo .db'), 400
    fd, tmp = tempfile.mkstemp(suffix='.db', dir='dados')
    os.close(fd)
    try:
        f.save(tmp)
        r = importar(tmp, request.form.get('senha', ''), db(), g.uid,
                     request.form.get('limpar') == '1')
    finally:
        for suf in ('', '-wal', '-shm', '-journal'):
            try:
                os.remove(tmp + suf)
            except OSError:
                pass
    return jsonify(r), (400 if r.get('erro') else 200)


# ── Tox / dispositivos ──────────────────────────────────────────────
# O Tox é um recurso do SERVIDOR: fica sempre ligado (ver _manter_tox) e o
# usuário não o liga nem desliga. Cada usuário tem UMA chave permanente, que
# usa em quantos apps quiser; cada app novo precisa ser aceito aqui.

@app.get('/api/tox/status')
@login_requerido
def api_tox_status():
    s = tox.obter_status()
    return jsonify(lib_ok=s.get('lib_ok'), rodando=s.get('rodando'),
                   rede=s.get('rede_texto', 'Offline'))


@app.get('/api/dispositivos')
@login_requerido
def api_disp_listar():
    return jsonify(tox.estado_dispositivos(session['u']))


@app.get('/api/dispositivos/chave')
@login_requerido
def api_disp_chave():
    r = tox.chave(session['u'])
    return jsonify(r), (400 if r.get('erro') else 200)


@app.post('/api/dispositivos/chave/renovar')
@login_requerido
def api_disp_chave_renovar():
    r = tox.chave(session['u'], renovar=True)
    return jsonify(r), (400 if r.get('erro') else 200)


def _pub_ok(pub):
    return bool(re.match(r'^[0-9A-Fa-f]{64}$', pub))


@app.post('/api/dispositivos/<pub>/aceitar')
@login_requerido
def api_disp_aceitar(pub):
    if not _pub_ok(pub):
        return jsonify(erro='Chave inválida'), 400
    r = tox.aceitar_dispositivo(session['u'], pub)
    return jsonify(r), (200 if r.get('sucesso') else 400)


@app.post('/api/dispositivos/<pub>/recusar')
@login_requerido
def api_disp_recusar(pub):
    if not _pub_ok(pub):
        return jsonify(erro='Chave inválida'), 400
    return jsonify(tox.recusar_dispositivo(session['u'], pub))


@app.put('/api/dispositivos/<pub>')
@login_requerido
def api_disp_renomear(pub):
    if not _pub_ok(pub):
        return jsonify(erro='Chave inválida'), 400
    r = tox.renomear_dispositivo(session['u'], pub, _json().get('nome'))
    return jsonify(r), (200 if r.get('sucesso') else 400)


@app.delete('/api/dispositivos/<pub>')
@login_requerido
def api_disp_remover(pub):
    if not _pub_ok(pub):
        return jsonify(erro='Chave inválida'), 400
    return jsonify(tox.remover_dispositivo(session['u'], pub))


def _manter_tox():
    """Mantém o Tox do servidor sempre ligado (tenta de novo se falhar)."""
    ultimo = None
    while True:
        try:
            if not tox.obter_status().get('rodando'):
                r = tox.ativar()
                if r.get('sucesso'):
                    log.info('Tox ativo')
                    ultimo = None
                elif r.get('erro') != ultimo:
                    ultimo = r.get('erro')
                    log.warning('Tox indisponível: %s', ultimo)
        except Exception:
            log.exception('manter tox')
        time.sleep(30)


# ── importar extrato em PDF ─────────────────────────────────────────

@app.post('/api/transacoes/pdf/ler')
@login_requerido
def api_pdf_ler():
    f = request.files.get('arquivo')
    if not f:
        return jsonify(erro='Selecione o PDF do extrato'), 400
    dados = f.read()
    if not dados.startswith(b'%PDF'):
        return jsonify(erro='O arquivo não é um PDF válido'), 400
    try:
        from modulos.pdf_parser import (processar_pdf_extrato,
                                        gerar_hash_transacao,
                                        gerar_hash_fuzzy)
    except ImportError:
        return jsonify(erro='Instale o pdfplumber: pip install pdfplumber'), 500
    ok, itens, msg = processar_pdf_extrato(dados)
    if not ok:
        return jsonify(erro=msg), 400
    exatos, fuzzy = set(), {}
    for t in db().execute(
            'SELECT transaction_type, amount, date, description '
            'FROM transactions WHERE user_id=?', (g.uid,)):
        exatos.add(gerar_hash_transacao(t['transaction_type'], t['amount'],
                                        t['date'], t['description']))
        fuzzy.setdefault(gerar_hash_fuzzy(t['transaction_type'], t['amount'],
                                          t['date']), t['description'])
    saida = []
    for it in itens:
        dup, tipo, ref = False, None, None
        if it['hash'] in exatos:
            dup, tipo = True, 'exata'
        else:
            h = gerar_hash_fuzzy(it['tipo'], it['valor'], it['data'])
            if h in fuzzy:
                dup, tipo, ref = True, 'fuzzy', fuzzy[h]
        saida.append({'descricao': it['descricao'], 'tipo': it['tipo'],
                      'valor': it['valor'], 'data': it['data'],
                      'duplicada': dup, 'duplicata_tipo': tipo,
                      'duplicata_descricao': ref})
    return jsonify(ok=True, mensagem=msg, itens=saida)


def _aplicar_regras(c, u, ids):
    """Categoriza (por regras) só as transações recém-importadas sem categoria."""
    if not ids:
        return 0
    regras = c.execute(
        "SELECT cr.category_id, cr.rule_text, cr.match_type FROM category_rules cr "
        "JOIN categories ca ON ca.id=cr.category_id "
        "WHERE cr.user_id=? AND ca.name NOT LIKE 'Empréstimo:%' ORDER BY cr.id",
        (u,)).fetchall()
    if not regras:
        return 0
    n = 0
    for tid in ids:
        desc = (c.execute('SELECT description FROM transactions WHERE id=?',
                          (tid,)).fetchone()['description'] or '').lower()
        for r in regras:
            txt, m = (r['rule_text'] or '').lower(), r['match_type']
            if (m == 'starts_with' and desc.startswith(txt)) or \
               (m == 'exact' and desc == txt) or \
               (m not in ('starts_with', 'exact') and txt in desc):
                c.execute('UPDATE transactions SET category_id=? WHERE id=?',
                          (r['category_id'], tid))
                n += 1
                break
    return n


@app.post('/api/transacoes/pdf/importar')
@login_requerido
def api_pdf_importar():
    c, u = db(), g.uid
    d = _json()
    itens = d.get('itens') or []
    if not isinstance(itens, list) or not itens or len(itens) > 5000:
        return jsonify(erro='Nenhuma transação para importar'), 400
    cat = d.get('category_id')
    if cat in (None, '', 0, '0'):
        cat = None
    else:
        try:
            cat = int(cat)
        except (TypeError, ValueError):
            return jsonify(erro='Categoria inválida'), 400
        if not c.execute('SELECT 1 FROM categories WHERE id=? AND user_id=?',
                         (cat, u)).fetchone():
            return jsonify(erro='Categoria inválida'), 400
    ids, erros = [], 0
    try:
        for it in itens:
            v, tipo, dt = (_valor(it.get('valor')), it.get('tipo'),
                           _data(it.get('data')))
            desc = (it.get('descricao') or '').strip()[:200]
            if v is None or tipo not in TIPOS or not dt or not desc:
                erros += 1
                continue
            ids.append(c.execute(
                'INSERT INTO transactions(user_id,amount,description,'
                'transaction_type,date,category_id) VALUES(?,?,?,?,?,?)',
                (u, v, desc, tipo, dt, cat)).lastrowid)
        cats = _aplicar_regras(c, u, [i for i in ids] if cat is None else [])
        c.commit()
    except Exception:
        c.rollback()
        log.exception('importar pdf')
        return jsonify(erro='Falha ao importar (nada foi alterado)'), 500
    return jsonify(ok=True, importadas=len(ids), erros=erros,
                   categorizadas=cats)


# ── empréstimos: detalhe e valor descontado ─────────────────────────

def _emprestimo(c, u, lid):
    return c.execute('SELECT * FROM loans WHERE id=? AND user_id=?',
                     (lid, u)).fetchone()


@app.get('/api/emprestimos/<int:lid>')
@login_requerido
def api_emp_detalhe(lid):
    c, u = db(), g.uid
    if not _emprestimo(c, u, lid):
        return jsonify(erro='Não encontrado'), 404
    st = emp.get_loan_status(c, lid)
    loan = dict(st['loan'])
    rec = None
    if loan['transaction_id']:
        r = c.execute('SELECT id,date,amount,description FROM transactions '
                      'WHERE id=?', (loan['transaction_id'],)).fetchone()
        rec = dict(r) if r else None
    pag = [dict(r) for r in c.execute(
        'SELECT id, installment_number n, payment_date data, amount valor, '
        'notes nota, transaction_id tx FROM loan_payments WHERE loan_id=? '
        'ORDER BY installment_number, id', (lid,))]
    return jsonify(emprestimo=loan, pago=st['total_paid'],
                   restante=st['remaining_amount'], progresso=st['progress'],
                   parcelas_pagas=st['installments_paid'],
                   concluido=st['is_completed'], recebimento=rec,
                   pagamentos=pag)


@app.post('/api/emprestimos/<int:lid>/desconto')
@login_requerido
def api_emp_desconto(lid):
    """Registra parcela já descontada do valor recebido (ex.: salário líquido).
    Não cria transação de saída: só abate o empréstimo. A entrada escolhida
    fica referenciada na observação (tx #id) para evitar duplicidade."""
    c, u = db(), g.uid
    loan = _emprestimo(c, u, lid)
    if not loan:
        return jsonify(erro='Não encontrado'), 404
    if loan['status'] == 'quitado':
        return jsonify(erro='Empréstimo já quitado'), 400
    d = _json()
    v = _valor(d.get('valor'))
    if v is None:
        return jsonify(erro='Valor descontado inválido'), 400
    data, nota = _data(d.get('data')), ''
    tid = d.get('transaction_id')
    if tid not in (None, '', 0, '0'):
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return jsonify(erro='Transação inválida'), 400
        t = c.execute('SELECT id,date,description,transaction_type '
                      'FROM transactions WHERE id=? AND user_id=?',
                      (tid, u)).fetchone()
        if not t or t['transaction_type'] != 'entrada':
            return jsonify(erro='Selecione uma transação de entrada'), 400
        if c.execute('SELECT 1 FROM loan_payments WHERE loan_id=? AND notes '
                     'LIKE ?', (lid, f'%(tx #{tid})%')).fetchone():
            return jsonify(erro='Esse recebimento já tem desconto '
                                'registrado neste empréstimo'), 400
        data = data or t['date']
        nota = f"Desconto em: {t['description'][:80]} (tx #{tid})"
    st = emp.get_loan_status(c, lid)
    if v > st['remaining_amount'] + 0.01:
        return jsonify(erro=f"Valor maior que o restante "
                            f"(R$ {st['remaining_amount']:.2f})"), 400
    n = (c.execute('SELECT COALESCE(MAX(installment_number),0) FROM '
                   'loan_payments WHERE loan_id=?', (lid,)).fetchone()[0]) + 1
    c.execute('INSERT INTO loan_payments(loan_id,transaction_id,payment_date,'
              'amount,installment_number,notes) VALUES(?,NULL,?,?,?,?)',
              (lid, data or datetime.now().strftime('%Y-%m-%d'), v, n,
               nota or 'Desconto informado manualmente'))
    c.commit()
    emp.check_and_complete_loans(c, u)
    return jsonify(ok=True)


@app.delete('/api/emprestimos/<int:lid>/pagamentos/<int:pid>')
@login_requerido
def api_emp_pag_excluir(lid, pid):
    c, u = db(), g.uid
    loan = _emprestimo(c, u, lid)
    if not loan:
        return jsonify(erro='Não encontrado'), 404
    p = c.execute('SELECT transaction_id FROM loan_payments WHERE id=? '
                  'AND loan_id=?', (pid, lid)).fetchone()
    if not p:
        return jsonify(erro='Pagamento não encontrado'), 404
    if p['transaction_id']:
        return jsonify(erro='Pagamento vem de uma transação de saída: '
                            'exclua a transação.'), 400
    c.execute('DELETE FROM loan_payments WHERE id=?', (pid,))
    c.commit()
    if loan['status'] == 'quitado' and not emp.get_loan_status(
            c, lid)['is_completed']:          # reabre se deixou de estar quitado
        c.execute("UPDATE loans SET status='ativo' WHERE id=?", (lid,))
        if loan['category_id']:
            c.execute('UPDATE categories SET is_hidden=0 WHERE id=?',
                      (loan['category_id'],))
        c.commit()
    return jsonify(ok=True)


# ── regras de categoria ─────────────────────────────────────────────

def _cat_do_usuario(c, u, cid):
    return c.execute('SELECT name FROM categories WHERE id=? AND user_id=?',
                     (cid, u)).fetchone()


@app.get('/api/categorias/<int:cid>/regras')
@login_requerido
def api_regras_listar(cid):
    c, u = db(), g.uid
    if not _cat_do_usuario(c, u, cid):
        return jsonify(erro='Não encontrada'), 404
    return jsonify([dict(r) for r in c.execute(
        'SELECT id, rule_text, match_type FROM category_rules '
        'WHERE user_id=? AND category_id=? ORDER BY id', (u, cid))])


@app.post('/api/categorias/<int:cid>/regras')
@login_requerido
def api_regras_criar(cid):
    c, u = db(), g.uid
    if not _cat_do_usuario(c, u, cid):
        return jsonify(erro='Não encontrada'), 404
    d = _json()
    txt = (d.get('rule_text') or '').strip()[:80]
    mt = d.get('match_type')
    if not txt or mt not in ('contains', 'starts_with', 'exact'):
        return jsonify(erro='Regra inválida'), 400
    try:
        c.execute('INSERT INTO category_rules(user_id,category_id,rule_text,'
                  'match_type) VALUES(?,?,?,?)', (u, cid, txt, mt))
        c.commit()
    except Exception:
        return jsonify(erro='Essa regra já existe'), 400
    return jsonify(ok=True)


@app.delete('/api/categorias/<int:cid>/regras/<int:rid>')
@login_requerido
def api_regras_excluir(cid, rid):
    c, u = db(), g.uid
    c.execute('DELETE FROM category_rules WHERE id=? AND category_id=? '
              'AND user_id=?', (rid, cid, u))
    c.commit()
    return jsonify(ok=True)


# ── início ──────────────────────────────────────────────────────────

def main():
    contas.iniciar()
    for u in contas.listar_contas():           # garante triggers de sync
        try:
            c = contas.abrir_db(u)
            sync_core.preparar(c)
            c.close()
        except Exception:
            log.exception('preparar sync de %s', u)
    threading.Thread(target=_manter_tox, daemon=True, name='Tox-Guarda').start()
    log.info('Servidor em http://localhost:%d', PORTA)
    app.run(host=HOST, port=PORTA, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()

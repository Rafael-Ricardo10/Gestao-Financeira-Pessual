#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RRFS Gestão Financeira - SERVIDOR WEB
Interface em http://0.0.0.0:6250  (templates/ com HTML+CSS+JS embutidos)
É um PAR da rede de cada conta (modulos/rede.py): sincroniza com os apps e
com outros servidores via Tox (cifrado). Login = usuário+senha, os mesmos dos
apps; as chaves derivam da senha e só ficam em memória (modulos/contas.py).
HTTPS automático (certificado próprio) a menos que RRFS_TLS=0.
"""
import os
import ssl
import socket
from urllib.parse import quote
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

from werkzeug.serving import ThreadedWSGIServer, WSGIRequestHandler
from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)

from modulos import contas, sync_core, backup, identidade
from modulos import loans as emp
from modulos.importar_db import importar

PORTA = int(os.environ.get('RRFS_PORTA', '6250'))
TLS = os.environ.get('RRFS_TLS', '1') != '0'
REGISTRO_ABERTO = os.environ.get('RRFS_REGISTRO', 'aberto') != 'fechado'
HOST = os.environ.get('RRFS_HOST', '0.0.0.0')
HOSTS_OK = {'localhost', '127.0.0.1', '[::1]', '0.0.0.0'} | {
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
                  SESSION_COOKIE_SECURE=TLS,
                  MAX_CONTENT_LENGTH=512 * 1024 * 1024,
                  PERMANENT_SESSION_LIFETIME=30 * 86400)


# ── segurança básica ────────────────────────────────────────────────

@app.before_request
def _protecao():
    host = request.host.rsplit(':', 1)[0]
    if host not in HOSTS_OK and host != '0.0.0.0':
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
        if session.get('u') not in contas.ATIVAS:
            session.clear()
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
    ch = contas.chaves_de(session.get('u'))
    return render_template(f'{nome}.html', usuario=ch.usuario if ch else '',
                           pagina=nome)


@app.route('/')
def raiz():
    return redirect(url_for('pagina_dashboard'
                            if session.get('u') in contas.ATIVAS
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

_criacoes = {}


def _entrar(criar):
    d = _json()
    u = (d.get('usuario') or '').strip()
    ip = request.remote_addr
    chave = f'{ip}|{u.casefold()}'
    if _bloqueado(chave) or _bloqueado(f'{ip}|*'):
        return jsonify(erro='Muitas tentativas. Aguarde alguns minutos.'), 429
    if criar:
        if not REGISTRO_ABERTO:
            return jsonify(erro='Cadastro desativado neste servidor'), 403
        rec = [x for x in _criacoes.get(ip, []) if time.time() - x < 3600]
        _criacoes[ip] = rec
        if len(rec) >= 5:
            return jsonify(erro='Limite de contas novas por hora'), 429
    nid, erro = contas.entrar(u, d.get('senha') or '', criar=criar)
    if not nid:
        _falhas.setdefault(chave, []).append(time.time())
        _falhas.setdefault(f'{ip}|*', []).append(time.time())
        return jsonify(erro=erro), 401
    if criar:
        _criacoes.setdefault(ip, []).append(time.time())
    session.clear()
    session['u'] = nid
    session.permanent = True
    return jsonify(ok=True)


@app.post('/api/registrar')            # "primeiro acesso": cria ou junta-se
def api_registrar():                   # à rede existente (mesmos dados)
    return _entrar(True)


@app.post('/api/entrar')
def api_entrar():
    return _entrar(False)


@app.post('/api/sair')
def api_sair():
    session.clear()
    return jsonify(ok=True)


@app.post('/api/config/senha')
@login_requerido
def api_senha():
    d = _json()
    nid, erro = contas.trocar_senha(session['u'], d.get('atual'), d.get('nova'))
    if not nid:
        return jsonify(erro=erro), 400
    session['u'] = nid
    return jsonify(ok=True)


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


# ── rede de aparelhos / backup ──────────────────────────────────────

def rede():
    return contas.rede_de(session['u'])


@app.get('/api/rede/estado')
@login_requerido
def api_rede_estado():
    e = rede().estado()
    e['bootstrap'] = rede().meu_bootstrap()
    e['manter_ativa'] = contas.cofre_ativo(session['u'])
    e['tls'] = TLS
    return jsonify(e)


@app.post('/api/rede/sincronizar')
@login_requerido
def api_rede_sync():
    rede().sincronizar_agora()
    return jsonify(ok=True)


@app.post('/api/rede/renomear')
@login_requerido
def api_rede_renomear():
    return jsonify(ok=rede().renomear(_json().get('nome')))


@app.post('/api/rede/no')
@login_requerido
def api_rede_no():
    d = _json()
    r = rede().adicionar_no(d.get('ip', ''), d.get('porta'), d.get('dht', ''))
    return jsonify(r), (200 if r.get('sucesso') else 400)


@app.post('/api/rede/manter')
@login_requerido
def api_rede_manter():
    contas.cofre_definir(session['u'], bool(_json().get('ligado')))
    return jsonify(ok=True)


@app.post('/api/rede/bloquear')
@login_requerido
def api_rede_bloquear():
    nid = session['u']
    session.clear()
    contas.bloquear(nid)
    return jsonify(ok=True)


@app.post('/api/config/exportar')
@login_requerido
def api_exportar():
    try:
        blob, n = backup.exportar(db(), _json().get('frase'))
    except ValueError as e:
        return jsonify(erro=str(e)), 400
    nome = 'rrfs-backup-' + datetime.now().strftime('%Y%m%d-%H%M') + '.rrfs'
    return app.response_class(
        blob, mimetype='application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename={nome}'})


@app.post('/api/config/importar-backup')
@login_requerido
def api_importar_backup():
    f = request.files.get('arquivo')
    if not f:
        return jsonify(erro='Selecione o arquivo .rrfs'), 400
    try:
        n = backup.importar(db(), f.read(), request.form.get('frase', ''))
    except ValueError as e:
        return jsonify(erro=str(e)), 400
    return jsonify(ok=True, registros=n)


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

def _nomes_certificado():
    """Nomes/IPs pelos quais o servidor é acessado (entram no certificado)."""
    import socket
    nomes = {'localhost', '127.0.0.1'}
    try:
        h = socket.gethostname()
        nomes |= {h, h + '.local'}
        for r in socket.getaddrinfo(h, None, socket.AF_INET):
            nomes.add(r[4][0])
    except Exception:
        pass
    try:                                    # IP usado para sair à rede
        t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t.connect(('192.0.2.1', 9))
        nomes.add(t.getsockname()[0])
        t.close()
    except Exception:
        pass
    for h in os.environ.get('RRFS_HOSTS', '').split(','):
        h = h.strip().split(':')[0]
        if h:
            nomes.add(h)
    return sorted(n for n in nomes if n and n != '0.0.0.0')


def _certificado():
    """Certificado TLS próprio (auto-assinado) para não trafegar senhas em
    texto puro. Vale para o nome e os IPs do servidor e é refeito se eles
    mudarem. Para um certificado confiável, use um proxy (Caddy/nginx) e
    rode com RRFS_TLS=0."""
    pasta = os.path.join('dados', 'tls')
    crt, key = os.path.join(pasta, 'cert.pem'), os.path.join(pasta, 'key.pem')
    marca = os.path.join(pasta, 'nomes.txt')
    nomes = _nomes_certificado()
    try:
        igual = open(marca).read().split() == nomes
    except OSError:
        igual = False
    if igual and os.path.exists(crt) and os.path.exists(key):
        return crt, key
    import datetime as dt
    import ipaddress
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    os.makedirs(pasta, exist_ok=True)
    k = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'RRFS Finanças')])
    san = []
    for n in nomes:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(n)))
        except ValueError:
            san.append(x509.DNSName(n))
    agora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(k.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(agora - dt.timedelta(days=1))
            .not_valid_after(agora + dt.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                           critical=True)
            .sign(k, hashes.SHA256()))
    with open(crt, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key, 'wb') as f:
        f.write(k.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()))
    os.chmod(key, 0o600)
    with open(marca, 'w') as f:
        f.write('\n'.join(nomes))
    log.info('Certificado TLS gerado para: %s', ', '.join(nomes))
    return crt, key


# ── HTTP e HTTPS na MESMA porta ─────────────────────────────────────
# Sem isto, quem abrir http://...:6250 (atalho, proxy, ferramenta de saúde,
# link antigo) levava "connection reset". Aqui o primeiro byte da conexão
# decide: 0x16 = TLS; qualquer outra coisa = HTTP puro, que é redirecionado
# para HTTPS (exceto vindo do próprio servidor, em 127.0.0.1).

class _Handler(WSGIRequestHandler):
    def make_environ(self):
        e = super().make_environ()
        tls = isinstance(self.connection, ssl.SSLSocket)
        e['rrfs.tls'] = tls
        if tls:
            e['wsgi.url_scheme'] = 'https'
        return e


class _ServidorDuplo(ThreadedWSGIServer):
    ctx_tls = None

    def finish_request(self, request, client_address):
        try:
            request.settimeout(10)
            if self.ctx_tls is not None and \
                    request.recv(1, socket.MSG_PEEK) == b'\x16':
                request = self.ctx_tls.wrap_socket(request, server_side=True)
            request.settimeout(None)
        except (OSError, ssl.SSLError):
            return                    # cliente desistiu / handshake inválido
        super().finish_request(request, client_address)


def _redirecionar_http(wsgi):
    def app_(environ, start):
        local = environ.get('REMOTE_ADDR') in ('127.0.0.1', '::1')
        if environ.get('rrfs.tls') or local:
            return wsgi(environ, start)
        host = environ.get('HTTP_HOST') or f"{environ.get('SERVER_NAME')}:{PORTA}"
        if ':' not in host.rsplit(']', 1)[-1]:
            host = f'{host}:{PORTA}'
        alvo = 'https://' + host + quote(environ.get('PATH_INFO', '/') or '/')
        if environ.get('QUERY_STRING'):
            alvo += '?' + environ['QUERY_STRING']
        start('308 Permanent Redirect', [('Location', alvo),
                                         ('Content-Length', '0')])
        return [b'']
    return app_


def main():
    contas.iniciar(BASE)
    from modulos import bd_seguro
    if not bd_seguro.CRIPTO_REPOUSO:
        log.warning('SQLCipher ausente: dados SEM criptografia em disco. '
                    'Instale: pip install sqlcipher3-binary')
    contas.restaurar_cofres(log)
    wsgi = app.wsgi_app
    if TLS:
        crt, key = _certificado()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(crt, key)
        wsgi = _redirecionar_http(wsgi)
        _ServidorDuplo.ctx_tls = ctx
    srv = _ServidorDuplo(HOST, PORTA, wsgi, handler=_Handler)
    log.info('Servidor em %s://%s:%d%s', 'https' if TLS else 'http', HOST,
             PORTA, ' (HTTP é redirecionado para HTTPS)' if TLS else '')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

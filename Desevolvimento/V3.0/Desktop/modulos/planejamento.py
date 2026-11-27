"""
Planejamento financeiro (NÃO são transações: é só uma simulação de gastos).

Um PLANO tem nome, data de início e um período (N dias/semanas/meses/anos).
O período é do plano, não das categorias. Cada CATEGORIA do plano tem um
preço unitário, uma quantidade opcional (kg, litros, unidades...) e a
frequência com que se repete (todo dia, toda semana, todo mês ou uma vez).

    custo da categoria = preço × quantidade (se preenchida, senão 1)
                               × repetições dentro do período do plano
"""
import calendar
from datetime import date, datetime, timedelta

UNIDADES_PERIODO = [('dia', 'dia(s)'), ('semana', 'semana(s)'),
                    ('mes', 'mês(es)'), ('ano', 'ano(s)')]

UNIDADES_MEDIDA = ['unidade', 'kg', 'g', 'litro', 'ml', 'pacote', 'caixa',
                   'dúzia', 'fardo', 'pote', 'garrafa']

FREQUENCIAS = [('dia', 'Todo dia'), ('semana', 'Toda semana'),
               ('mes', 'Todo mês'), ('unico', 'Uma única vez')]

DIAS_NO_MES = 365.25 / 12


def criar_tabelas(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS plans
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         user_id INTEGER NOT NULL,
         name TEXT NOT NULL,
         start_date TEXT NOT NULL,
         period_amount INTEGER NOT NULL DEFAULT 1,
         period_unit TEXT NOT NULL DEFAULT 'mes',
         notes TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS plan_categories
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         plan_id INTEGER NOT NULL,
         name TEXT NOT NULL,
         unit_price REAL NOT NULL DEFAULT 0,
         quantity REAL NOT NULL DEFAULT 0,
         unit TEXT,
         frequency TEXT NOT NULL DEFAULT 'dia')''')
    conn.commit()


# ── tempo ───────────────────────────────────────────────────────────

def _somar_meses(d, n):
    m = d.month - 1 + n
    ano = d.year + m // 12
    mes = m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def _data(txt):
    try:
        return datetime.strptime(str(txt)[:10], '%Y-%m-%d').date()
    except Exception:
        return date.today()


def periodo(inicio, quantidade, unidade):
    """Devolve dict: inicio, fim (exclusivo), dias, semanas, meses."""
    ini = inicio if isinstance(inicio, date) else _data(inicio)
    q = max(1, int(quantidade or 1))
    if unidade == 'dia':
        fim = ini + timedelta(days=q)
    elif unidade == 'semana':
        fim = ini + timedelta(days=7 * q)
    elif unidade == 'ano':
        fim = _somar_meses(ini, 12 * q)
    else:
        unidade = 'mes'
        fim = _somar_meses(ini, q)
    dias = (fim - ini).days
    meses = (q if unidade == 'mes' else 12 * q if unidade == 'ano'
             else dias / DIAS_NO_MES)
    semanas = q if unidade == 'semana' else dias / 7
    return {'inicio': ini, 'fim': fim, 'dias': dias,
            'semanas': semanas, 'meses': meses}


def repeticoes(freq, per):
    return {'dia': per['dias'], 'semana': per['semanas'],
            'mes': per['meses'], 'unico': 1}.get(freq, per['dias'])


def custo(preco, quantidade, freq, per):
    """preço × quantidade (se > 0, senão ×1) × repetições no período."""
    qtd = quantidade if (quantidade or 0) > 0 else 1
    return round((preco or 0) * qtd * repeticoes(freq, per), 2)


def resumo(plano, categorias):
    """plano: dict/Row do plano. categorias: lista de dict/Row."""
    per = periodo(plano['start_date'], plano['period_amount'],
                  plano['period_unit'])
    linhas, total = [], 0.0
    for c in categorias:
        v = custo(c['unit_price'], c['quantity'], c['frequency'], per)
        total += v
        linhas.append({'id': c['id'], 'valor': v})
    for l in linhas:
        l['pct'] = (l['valor'] / total * 100) if total else 0
    return {'periodo': per, 'linhas': linhas, 'total': round(total, 2),
            'por_dia': total / per['dias'] if per['dias'] else 0,
            'por_semana': total / per['semanas'] if per['semanas'] else 0,
            'por_mes': total / per['meses'] if per['meses'] else 0}


# ── banco ───────────────────────────────────────────────────────────

def listar_planos(conn, user_id):
    return conn.execute('SELECT * FROM plans WHERE user_id=? '
                        'ORDER BY name COLLATE NOCASE, id',
                        (user_id,)).fetchall()


def obter_plano(conn, plan_id):
    return conn.execute('SELECT * FROM plans WHERE id=?',
                        (plan_id,)).fetchone()


def criar_plano(conn, user_id, nome, inicio=None, qtd=1, unidade='mes',
                notas=''):
    cur = conn.execute(
        'INSERT INTO plans(user_id,name,start_date,period_amount,'
        'period_unit,notes) VALUES(?,?,?,?,?,?)',
        (user_id, nome.strip(),
         (inicio or date.today()).strftime('%Y-%m-%d'), qtd, unidade, notas))
    conn.commit()
    return cur.lastrowid


def atualizar_plano(conn, plan_id, nome, inicio, qtd, unidade, notas):
    conn.execute(
        'UPDATE plans SET name=?, start_date=?, period_amount=?, '
        'period_unit=?, notes=? WHERE id=?',
        (nome.strip(), inicio.strftime('%Y-%m-%d'), qtd, unidade, notas,
         plan_id))
    conn.commit()


def excluir_plano(conn, plan_id):
    # sem ON DELETE CASCADE: apaga as categorias antes (cada exclusão é
    # sincronizada com os outros aparelhos)
    conn.execute('DELETE FROM plan_categories WHERE plan_id=?', (plan_id,))
    conn.execute('DELETE FROM plans WHERE id=?', (plan_id,))
    conn.commit()


def duplicar_plano(conn, user_id, plan_id, novo_nome):
    p = obter_plano(conn, plan_id)
    novo = criar_plano(conn, user_id, novo_nome, _data(p['start_date']),
                       p['period_amount'], p['period_unit'], p['notes'] or '')
    for c in listar_categorias(conn, plan_id):
        conn.execute(
            'INSERT INTO plan_categories(plan_id,name,unit_price,quantity,'
            'unit,frequency) VALUES(?,?,?,?,?,?)',
            (novo, c['name'], c['unit_price'], c['quantity'], c['unit'],
             c['frequency']))
    conn.commit()
    return novo


def listar_categorias(conn, plan_id):
    return conn.execute('SELECT * FROM plan_categories WHERE plan_id=? '
                        'ORDER BY id', (plan_id,)).fetchall()


def salvar_categoria(conn, plan_id, nome, preco, qtd, unidade, freq,
                     cat_id=None):
    if cat_id:
        conn.execute(
            'UPDATE plan_categories SET name=?, unit_price=?, quantity=?, '
            'unit=?, frequency=? WHERE id=?',
            (nome.strip(), preco, qtd, unidade, freq, cat_id))
    else:
        conn.execute(
            'INSERT INTO plan_categories(plan_id,name,unit_price,quantity,'
            'unit,frequency) VALUES(?,?,?,?,?,?)',
            (plan_id, nome.strip(), preco, qtd, unidade, freq))
    conn.commit()


def excluir_categoria(conn, cat_id):
    conn.execute('DELETE FROM plan_categories WHERE id=?', (cat_id,))
    conn.commit()

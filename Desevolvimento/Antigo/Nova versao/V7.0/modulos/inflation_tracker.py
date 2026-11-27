# modulos/inflation_tracker.py
"""
Rastreador de Inflação Pessoal e Oficial (IPCA)
Compara inflação vivida pelo usuário vs IPCA oficial do Banco Central
API BCB: gratuita, sem registro, sem chave de API

MODOS DE CÁLCULO:
  - 2+ anos de dados : compara ano atual vs ano anterior
  - 6-12 meses      : compara semestres / trimestres
  - 3-6 meses       : tendência de alta/baixa nos gastos
  - < 3 meses       : análise básica do período disponível
"""
import json
import sqlite3
from datetime import datetime, timedelta

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print('[Inflation] requests não instalado. '
          'Execute: pip install requests')


# ── URLs da API do Banco Central (sem autenticação) ──────────
BCB_API_BASE = 'https://api.bcb.gov.br/dados/serie'

BCB_SERIES = {
    'IPCA':  {'code': 433,   'label': 'IPCA (Inflação Oficial)'},
    'INPC':  {'code': 188,   'label': 'INPC (Classe Baixa)'},
    'IGP_M': {'code': 189,   'label': 'IGP-M (Mercado)'},
    'SELIC': {'code': 432,   'label': 'Selic (Juros)'},
    'DOLAR': {'code': 10813, 'label': 'Dólar Médio (BCB)'},
}


# ══════════════════════════════════════════════════════════════
# TABELAS DO BANCO DE DADOS
# ══════════════════════════════════════════════════════════════

def create_inflation_tables(db_connection):
    """Cria tabelas para armazenar dados de inflação"""

    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS inflation_official (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            series_code TEXT    NOT NULL,
            ref_date    TEXT    NOT NULL,
            value       REAL    NOT NULL,
            fetched_at  TEXT    NOT NULL,
            UNIQUE(series_code, ref_date)
        )
    ''')

    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS inflation_personal (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            category_id     INTEGER,
            category_name   TEXT,
            ref_year        INTEGER NOT NULL,
            ref_month       INTEGER NOT NULL,
            avg_expense     REAL    NOT NULL,
            prev_avg        REAL    DEFAULT 0,
            variation_pct   REAL    DEFAULT 0,
            calculated_at   TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, category_id, ref_year, ref_month)
        )
    ''')

    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS inflation_cache (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            series_code   TEXT    NOT NULL UNIQUE,
            last_fetch    TEXT    NOT NULL,
            records_count INTEGER DEFAULT 0
        )
    ''')

    db_connection.commit()


# ══════════════════════════════════════════════════════════════
# DETECÇÃO DE PERÍODO DISPONÍVEL
# ══════════════════════════════════════════════════════════════

def detect_data_period(db_connection, user_id: int) -> dict:
    """
    Detecta quanto histórico de dados o usuário tem.
    Retorna informações sobre o período e qual modo
    de cálculo usar.

    Modos:
        'anual'     : 2+ anos → compara ano atual vs anterior
        'semestral' : 6-24 meses → compara semestres
        'trimestral': 3-6 meses → compara trimestres
        'basico'    : < 3 meses → análise básica
    """
    try:
        result = db_connection.execute(
            '''SELECT
                   MIN(date)                          AS first_date,
                   MAX(date)                          AS last_date,
                   COUNT(DISTINCT strftime('%Y-%m', date)) AS months_count,
                   COUNT(DISTINCT strftime('%Y', date))    AS years_count,
                   COUNT(*)                           AS total_transactions
               FROM transactions
               WHERE user_id = ?
               AND transaction_type = 'saida' ''',
            (user_id,)
        ).fetchone()

        if not result or not result['first_date']:
            return {
                'mode':          'sem_dados',
                'months':        0,
                'years':         0,
                'first_date':    None,
                'last_date':     None,
                'transactions':  0,
                'description':   'Sem transações registradas',
            }

        first_dt     = datetime.strptime(
            result['first_date'], '%Y-%m-%d'
        )
        last_dt      = datetime.strptime(
            result['last_date'], '%Y-%m-%d'
        )
        months_total = (
            (last_dt.year - first_dt.year) * 12 +
            (last_dt.month - first_dt.month) + 1
        )
        years_total  = last_dt.year - first_dt.year

        # Definir modo
        if years_total >= 2 or months_total >= 24:
            mode        = 'anual'
            description = (
                f'Comparando ano atual vs ano anterior '
                f'({result["months_count"]} meses de dados)'
            )
        elif months_total >= 6:
            mode        = 'semestral'
            description = (
                f'Comparando períodos de 6 meses '
                f'({months_total} meses disponíveis)'
            )
        elif months_total >= 3:
            mode        = 'trimestral'
            description = (
                f'Comparando trimestres '
                f'({months_total} meses disponíveis)'
            )
        else:
            mode        = 'basico'
            description = (
                f'Análise básica '
                f'({months_total} meses disponíveis)'
            )

        return {
            'mode':         mode,
            'months':       months_total,
            'years':        years_total,
            'first_date':   result['first_date'],
            'last_date':    result['last_date'],
            'transactions': result['total_transactions'],
            'description':  description,
        }

    except Exception as e:
        print(f'[Inflation] Erro ao detectar período: {e}')
        return {
            'mode':        'sem_dados',
            'months':      0,
            'years':       0,
            'first_date':  None,
            'last_date':   None,
            'transactions': 0,
            'description': str(e),
        }


# ══════════════════════════════════════════════════════════════
# BUSCA DE DADOS DO BANCO CENTRAL
# ══════════════════════════════════════════════════════════════

def _needs_bcb_update(db_connection, series_code: str) -> bool:
    """Verifica se precisa buscar dados do BCB (uma vez por dia)"""
    row = db_connection.execute(
        'SELECT last_fetch FROM inflation_cache '
        'WHERE series_code = ?',
        (series_code,)
    ).fetchone()

    if not row:
        return True

    try:
        last      = datetime.strptime(
            row['last_fetch'], '%Y-%m-%d %H:%M:%S'
        )
        horas     = (datetime.now() - last).total_seconds() / 3600
        return horas >= 24
    except Exception:
        return True


def fetch_bcb_series(
    db_connection,
    series_code: str,
    since_date: str = None,
    force: bool = False
) -> bool:
    """
    Busca série histórica do Banco Central do Brasil.
    API pública, gratuita, sem autenticação.
    """
    if not REQUESTS_AVAILABLE:
        print('[Inflation] requests não disponível.')
        return False

    if not force and not _needs_bcb_update(db_connection, series_code):
        return False

    series_info = BCB_SERIES.get(series_code)
    if not series_info:
        print(f'[Inflation] Série {series_code} não encontrada.')
        return False

    try:
        code = series_info['code']

        if since_date:
            try:
                dt        = datetime.strptime(since_date, '%Y-%m-%d')
                # Pegar 5 anos antes para ter base de comparação
                dt_inicio = dt.replace(
                    year=max(2010, dt.year - 5)
                )
                dt_str    = dt_inicio.strftime('%d/%m/%Y')
                today_str = datetime.now().strftime('%d/%m/%Y')
                url = (
                    f'{BCB_API_BASE}/bcdata.sgs.{code}/dados'
                    f'?formato=json'
                    f'&dataInicial={dt_str}'
                    f'&dataFinal={today_str}'
                )
            except Exception:
                url = (
                    f'{BCB_API_BASE}/bcdata.sgs.{code}/dados'
                    f'?formato=json'
                )
        else:
            # Últimos 5 anos
            since = datetime.now() - timedelta(days=365 * 5)
            url = (
                f'{BCB_API_BASE}/bcdata.sgs.{code}/dados'
                f'?formato=json'
                f'&dataInicial={since.strftime("%d/%m/%Y")}'
                f'&dataFinal={datetime.now().strftime("%d/%m/%Y")}'
            )

        print(f'[Inflation] Buscando {series_info["label"]} do BCB...')

        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not data:
            return False

        count      = 0
        fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for item in data:
            try:
                date_str = item.get('data', '')
                value    = float(
                    str(item.get('valor', '0')).replace(',', '.')
                )
                dt       = datetime.strptime(date_str, '%d/%m/%Y')
                ref_date = dt.strftime('%Y-%m-%d')

                db_connection.execute(
                    '''INSERT OR REPLACE INTO inflation_official
                       (series_code, ref_date, value, fetched_at)
                       VALUES (?, ?, ?, ?)''',
                    (series_code, ref_date, value, fetched_at)
                )
                count += 1
            except Exception:
                pass

        db_connection.commit()

        # Atualizar cache
        db_connection.execute(
            '''INSERT OR REPLACE INTO inflation_cache
               (series_code, last_fetch, records_count)
               VALUES (?, ?, ?)''',
            (series_code, fetched_at, count)
        )
        db_connection.commit()

        print(
            f'[Inflation] {series_info["label"]}: '
            f'{count} registros salvos.'
        )
        return True

    except requests.exceptions.ConnectionError:
        print(f'[Inflation] Sem conexão para {series_code}.')
        return False
    except requests.exceptions.Timeout:
        print(f'[Inflation] Timeout ao buscar {series_code}.')
        return False
    except Exception as e:
        print(f'[Inflation] Erro ao buscar {series_code}: {e}')
        return False


def fetch_all_bcb_series(
    db_connection, since_date: str = None
) -> dict:
    """Busca todas as séries do BCB necessárias."""
    results = {}
    for series_code in BCB_SERIES:
        results[series_code] = fetch_bcb_series(
            db_connection, series_code, since_date
        )
    return results


# ══════════════════════════════════════════════════════════════
# CÁLCULO ADAPTATIVO DE INFLAÇÃO PESSOAL
# Funciona com qualquer quantidade de dados
# ══════════════════════════════════════════════════════════════

def calculate_personal_inflation(
    db_connection, user_id: int
) -> dict:
    """
    Calcula a inflação pessoal de forma ADAPTATIVA.
    Funciona com qualquer quantidade de dados disponíveis.

    Modos automáticos:
    - anual     : 2+ anos → ano atual vs ano anterior
    - semestral : 6-24 meses → primeiro semestre vs segundo
    - trimestral: 3-6 meses → primeiro vs segundo trimestre
    - basico    : < 3 meses → tendência dos dados disponíveis
    """
    try:
        # Detectar período disponível
        period = detect_data_period(db_connection, user_id)
        mode   = period.get('mode', 'sem_dados')

        if mode == 'sem_dados':
            return {
                'has_data':           False,
                'message':            'Sem transações registradas',
                'mode':               mode,
                'period_description': period['description'],
            }

        # Redirecionar para o método correto
        if mode == 'anual':
            return _calculate_annual(db_connection, user_id, period)
        elif mode == 'semestral':
            return _calculate_semestral(
                db_connection, user_id, period
            )
        elif mode == 'trimestral':
            return _calculate_trimestral(
                db_connection, user_id, period
            )
        else:
            return _calculate_basic(db_connection, user_id, period)

    except Exception as e:
        print(f'[Inflation] Erro ao calcular inflação: {e}')
        import traceback
        traceback.print_exc()
        return {'has_data': False, 'message': str(e)}


def _calculate_annual(
    db_connection, user_id: int, period: dict
) -> dict:
    """
    Modo ANUAL: compara ano atual vs ano anterior.
    Requer 12+ meses de dados.
    """
    today        = datetime.now()
    current_year = today.year
    prev_year    = current_year - 1

    # Gastos por categoria - ano atual
    current_data = db_connection.execute(
        '''SELECT
               COALESCE(c.name, 'Sem Categoria') AS category,
               c.id                              AS category_id,
               AVG(monthly_total)                AS avg_monthly,
               COUNT(DISTINCT month)             AS months_count
           FROM (
               SELECT t.category_id,
                      strftime('%Y-%m', t.date) AS month,
                      SUM(t.amount)             AS monthly_total
               FROM transactions t
               WHERE t.user_id = ?
               AND t.transaction_type = 'saida'
               AND strftime('%Y', t.date) = ?
               GROUP BY t.category_id, month
           ) sub
           LEFT JOIN categories c ON sub.category_id = c.id
           GROUP BY sub.category_id
           ORDER BY avg_monthly DESC''',
        (user_id, str(current_year))
    ).fetchall()

    # Gastos por categoria - ano anterior
    prev_data = db_connection.execute(
        '''SELECT
               c.id        AS category_id,
               AVG(monthly_total) AS avg_monthly
           FROM (
               SELECT t.category_id,
                      strftime('%Y-%m', t.date) AS month,
                      SUM(t.amount)             AS monthly_total
               FROM transactions t
               WHERE t.user_id = ?
               AND t.transaction_type = 'saida'
               AND strftime('%Y', t.date) = ?
               GROUP BY t.category_id, month
           ) sub
           LEFT JOIN categories c ON sub.category_id = c.id
           GROUP BY sub.category_id''',
        (user_id, str(prev_year))
    ).fetchall()

    prev_map = {
        row['category_id']: float(row['avg_monthly'] or 0)
        for row in prev_data
    }

    return _build_result(
        db_connection, user_id,
        current_data, prev_map,
        current_year, prev_year,
        mode='anual',
        period=period,
        label_current=f'Ano {current_year}',
        label_prev=f'Ano {prev_year}'
    )


def _calculate_semestral(
    db_connection, user_id: int, period: dict
) -> dict:
    """
    Modo SEMESTRAL: compara últimos 6 meses vs 6 meses anteriores.
    Para usuários com 6-24 meses de dados.
    """
    today     = datetime.now()
    # Último semestre: últimos 6 meses
    end_curr  = today
    start_curr = today - timedelta(days=183)
    # Semestre anterior: 6 meses antes do atual
    end_prev  = start_curr
    start_prev = end_prev - timedelta(days=183)

    end_curr_str   = end_curr.strftime('%Y-%m-%d')
    start_curr_str = start_curr.strftime('%Y-%m-%d')
    end_prev_str   = end_prev.strftime('%Y-%m-%d')
    start_prev_str = start_prev.strftime('%Y-%m-%d')

    current_data = db_connection.execute(
        '''SELECT
               COALESCE(c.name, 'Sem Categoria') AS category,
               c.id                              AS category_id,
               AVG(monthly_total)                AS avg_monthly,
               COUNT(DISTINCT month)             AS months_count
           FROM (
               SELECT t.category_id,
                      strftime('%Y-%m', t.date) AS month,
                      SUM(t.amount)             AS monthly_total
               FROM transactions t
               WHERE t.user_id = ?
               AND t.transaction_type = 'saida'
               AND t.date BETWEEN ? AND ?
               GROUP BY t.category_id, month
           ) sub
           LEFT JOIN categories c ON sub.category_id = c.id
           GROUP BY sub.category_id
           ORDER BY avg_monthly DESC''',
        (user_id, start_curr_str, end_curr_str)
    ).fetchall()

    prev_data = db_connection.execute(
        '''SELECT
               c.id AS category_id,
               AVG(monthly_total) AS avg_monthly
           FROM (
               SELECT t.category_id,
                      strftime('%Y-%m', t.date) AS month,
                      SUM(t.amount)             AS monthly_total
               FROM transactions t
               WHERE t.user_id = ?
               AND t.transaction_type = 'saida'
               AND t.date BETWEEN ? AND ?
               GROUP BY t.category_id, month
           ) sub
           LEFT JOIN categories c ON sub.category_id = c.id
           GROUP BY sub.category_id''',
        (user_id, start_prev_str, end_prev_str)
    ).fetchall()

    prev_map = {
        row['category_id']: float(row['avg_monthly'] or 0)
        for row in prev_data
    }

    label_curr = (
        f'{start_curr.strftime("%b/%Y")} – '
        f'{end_curr.strftime("%b/%Y")}'
    )
    label_prev = (
        f'{start_prev.strftime("%b/%Y")} – '
        f'{end_prev.strftime("%b/%Y")}'
    )

    return _build_result(
        db_connection, user_id,
        current_data, prev_map,
        today.year, today.year - 1,
        mode='semestral',
        period=period,
        label_current=label_curr,
        label_prev=label_prev
    )


def _calculate_trimestral(
    db_connection, user_id: int, period: dict
) -> dict:
    """
    Modo TRIMESTRAL: compara últimos 3 meses vs 3 meses anteriores.
    Para usuários com 3-6 meses de dados.
    """
    today      = datetime.now()
    end_curr   = today
    start_curr = today - timedelta(days=91)
    end_prev   = start_curr
    start_prev = end_prev - timedelta(days=91)

    end_curr_str   = end_curr.strftime('%Y-%m-%d')
    start_curr_str = start_curr.strftime('%Y-%m-%d')
    end_prev_str   = end_prev.strftime('%Y-%m-%d')
    start_prev_str = start_prev.strftime('%Y-%m-%d')

    current_data = db_connection.execute(
        '''SELECT
               COALESCE(c.name, 'Sem Categoria') AS category,
               c.id                              AS category_id,
               AVG(monthly_total)                AS avg_monthly,
               COUNT(DISTINCT month)             AS months_count
           FROM (
               SELECT t.category_id,
                      strftime('%Y-%m', t.date) AS month,
                      SUM(t.amount)             AS monthly_total
               FROM transactions t
               WHERE t.user_id = ?
               AND t.transaction_type = 'saida'
               AND t.date BETWEEN ? AND ?
               GROUP BY t.category_id, month
           ) sub
           LEFT JOIN categories c ON sub.category_id = c.id
           GROUP BY sub.category_id
           ORDER BY avg_monthly DESC''',
        (user_id, start_curr_str, end_curr_str)
    ).fetchall()

    prev_data = db_connection.execute(
        '''SELECT
               c.id AS category_id,
               AVG(monthly_total) AS avg_monthly
           FROM (
               SELECT t.category_id,
                      strftime('%Y-%m', t.date) AS month,
                      SUM(t.amount)             AS monthly_total
               FROM transactions t
               WHERE t.user_id = ?
               AND t.transaction_type = 'saida'
               AND t.date BETWEEN ? AND ?
               GROUP BY t.category_id, month
           ) sub
           LEFT JOIN categories c ON sub.category_id = c.id
           GROUP BY sub.category_id''',
        (user_id, start_prev_str, end_prev_str)
    ).fetchall()

    prev_map = {
        row['category_id']: float(row['avg_monthly'] or 0)
        for row in prev_data
    }

    label_curr = (
        f'{start_curr.strftime("%b/%Y")} – '
        f'{end_curr.strftime("%b/%Y")}'
    )
    label_prev = (
        f'{start_prev.strftime("%b/%Y")} – '
        f'{end_prev.strftime("%b/%Y")}'
    )

    return _build_result(
        db_connection, user_id,
        current_data, prev_map,
        today.year, today.year,
        mode='trimestral',
        period=period,
        label_current=label_curr,
        label_prev=label_prev
    )


def _calculate_basic(
    db_connection, user_id: int, period: dict
) -> dict:
    """
    Modo BÁSICO: analisa tendência mês a mês com dados disponíveis.
    Para usuários com menos de 3 meses de dados.
    """
    try:
        # Buscar todos os meses disponíveis
        monthly = db_connection.execute(
            '''SELECT
                   strftime('%Y-%m', date) AS month,
                   SUM(amount)             AS total,
                   COUNT(*)                AS transactions
               FROM transactions
               WHERE user_id = ?
               AND transaction_type = 'saida'
               GROUP BY month
               ORDER BY month ASC''',
            (user_id,)
        ).fetchall()

        if not monthly:
            return {
                'has_data': False,
                'message':  'Sem dados de despesas',
                'mode':     'basico',
            }

        months   = [r['month'] for r in monthly]
        totals   = [float(r['total'] or 0) for r in monthly]
        avg      = sum(totals) / len(totals) if totals else 0

        # Tendência: primeiro mês vs último mês
        if len(totals) >= 2:
            first_total = totals[0]
            last_total  = totals[-1]
            variation   = (
                (last_total - first_total) / first_total * 100
                if first_total > 0 else 0
            )
        else:
            variation = 0

        # Labels
        labels = []
        for m in months:
            try:
                dt = datetime.strptime(m, '%Y-%m')
                labels.append(dt.strftime('%b/%Y'))
            except Exception:
                labels.append(m)

        # Gastos por categoria no período
        cat_data = db_connection.execute(
            '''SELECT
                   COALESCE(c.name, 'Sem Categoria') AS category,
                   c.id                              AS category_id,
                   AVG(monthly_total)                AS avg_monthly,
                   COUNT(DISTINCT month)             AS months_count
               FROM (
                   SELECT t.category_id,
                          strftime('%Y-%m', t.date) AS month,
                          SUM(t.amount)             AS monthly_total
                   FROM transactions t
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   GROUP BY t.category_id, month
               ) sub
               LEFT JOIN categories c ON sub.category_id = c.id
               GROUP BY sub.category_id
               ORDER BY avg_monthly DESC''',
            (user_id,)
        ).fetchall()

        categories = [
            {
                'category':     row['category'],
                'category_id':  row['category_id'],
                'current_avg':  round(float(row['avg_monthly'] or 0), 2),
                'prev_avg':     0,
                'variation':    0,
                'months_count': row['months_count'],
                'has_prev':     False,
            }
            for row in cat_data
        ]

        today = datetime.now()
        return {
            'has_data':           True,
            'mode':               'basico',
            'current_year':       today.year,
            'prev_year':          today.year,
            'label_current':      f'Período atual',
            'label_prev':         'Período anterior',
            'personal_inflation': round(variation, 2),
            'total_current_avg':  round(avg, 2),
            'total_prev_avg':     0,
            'categories':         categories,
            'top_inflation':      [],
            'deflated':           [],
            'monthly_yoy':        [],
            'monthly_data':       [
                {
                    'month':  months[i],
                    'label':  labels[i],
                    'total':  totals[i],
                }
                for i in range(len(months))
            ],
            'period':             period,
            'period_description': period['description'],
            'message': (
                f'Análise básica de {len(months)} meses. '
                f'Acumule mais dados para análises mais precisas.'
            )
        }

    except Exception as e:
        print(f'[Inflation] Erro no modo básico: {e}')
        return {'has_data': False, 'message': str(e)}


def _build_result(
    db_connection,
    user_id: int,
    current_data,
    prev_map: dict,
    current_year: int,
    prev_year: int,
    mode: str,
    period: dict,
    label_current: str,
    label_prev: str,
) -> dict:
    """
    Constrói o resultado padronizado para os modos
    anual, semestral e trimestral.
    """
    categories_inflation = []
    total_current        = 0.0
    total_prev           = 0.0

    for row in current_data:
        current_avg = float(row['avg_monthly'] or 0)
        prev_avg    = float(prev_map.get(row['category_id'], 0))
        total_current += current_avg

        if prev_avg > 0:
            variation   = (current_avg - prev_avg) / prev_avg * 100
            total_prev += prev_avg
        else:
            variation = 0

        categories_inflation.append({
            'category':     row['category'],
            'category_id':  row['category_id'],
            'current_avg':  round(current_avg, 2),
            'prev_avg':     round(prev_avg, 2),
            'variation':    round(variation, 2),
            'months_count': row['months_count'],
            'has_prev':     prev_avg > 0,
        })

    # Inflação pessoal geral
    if total_prev > 0:
        personal_inflation = (
            (total_current - total_prev) / total_prev * 100
        )
    else:
        # Sem período anterior: calcular tendência interna
        personal_inflation = _calculate_internal_trend(
            db_connection, user_id
        )

    # YoY mensal (só para modo anual)
    monthly_yoy = []
    if mode == 'anual':
        monthly_yoy = _calculate_monthly_yoy(
            db_connection, user_id
        )

    # Dados mensais do período atual para gráfico
    monthly_data = _get_monthly_data(db_connection, user_id)

    top_inflation = sorted(
        [c for c in categories_inflation if c['has_prev']],
        key=lambda x: x['variation'],
        reverse=True
    )

    deflated = [
        c for c in categories_inflation
        if c['has_prev'] and c['variation'] < 0
    ]

    return {
        'has_data':           True,
        'mode':               mode,
        'current_year':       current_year,
        'prev_year':          prev_year,
        'label_current':      label_current,
        'label_prev':         label_prev,
        'personal_inflation': round(personal_inflation, 2),
        'total_current_avg':  round(total_current, 2),
        'total_prev_avg':     round(total_prev, 2),
        'categories':         categories_inflation,
        'top_inflation':      top_inflation[:5],
        'deflated':           deflated,
        'monthly_yoy':        monthly_yoy,
        'monthly_data':       monthly_data,
        'period':             period,
        'period_description': period['description'],
    }


def _calculate_internal_trend(
    db_connection, user_id: int
) -> float:
    """
    Calcula tendência interna quando não há período anterior.
    Usa regressão linear nos gastos mensais.
    """
    try:
        monthly = db_connection.execute(
            '''SELECT SUM(amount) AS total
               FROM transactions
               WHERE user_id = ?
               AND transaction_type = 'saida'
               GROUP BY strftime('%Y-%m', date)
               ORDER BY strftime('%Y-%m', date) ASC''',
            (user_id,)
        ).fetchall()

        totals = [float(r['total'] or 0) for r in monthly]

        if len(totals) < 2:
            return 0.0

        # Variação simples primeiro vs último
        first = totals[0]
        last  = totals[-1]

        if first > 0:
            return round((last - first) / first * 100, 2)
        return 0.0

    except Exception:
        return 0.0


def _calculate_monthly_yoy(
    db_connection, user_id: int
) -> list:
    """
    Calcula variação YoY (mesmo mês vs ano anterior).
    Usado apenas no modo anual.
    """
    monthly = db_connection.execute(
        '''SELECT
               strftime('%Y-%m', date) AS month,
               SUM(amount)             AS total
           FROM transactions
           WHERE user_id = ?
           AND transaction_type = 'saida'
           AND date >= date('now', '-25 months')
           GROUP BY month
           ORDER BY month ASC''',
        (user_id,)
    ).fetchall()

    month_map = {r['month']: float(r['total'] or 0)
                 for r in monthly}
    result    = []

    for month_str, total in month_map.items():
        try:
            dt         = datetime.strptime(month_str, '%Y-%m')
            prev_month = dt.replace(year=dt.year - 1)
            prev_key   = prev_month.strftime('%Y-%m')
            prev_total = month_map.get(prev_key, 0)

            if prev_total > 0:
                yoy = (total - prev_total) / prev_total * 100
                result.append({
                    'month':      month_str,
                    'label':      dt.strftime('%b/%Y'),
                    'total':      total,
                    'prev_total': prev_total,
                    'yoy_pct':    round(yoy, 2),
                })
        except Exception:
            pass

    return result


def _get_monthly_data(
    db_connection, user_id: int, months_back: int = 12
) -> list:
    """Retorna dados mensais recentes para gráfico"""
    rows = db_connection.execute(
        '''SELECT
               strftime('%Y-%m', date) AS month,
               SUM(amount)             AS total
           FROM transactions
           WHERE user_id = ?
           AND transaction_type = 'saida'
           AND date >= date('now', ? || ' months')
           GROUP BY month
           ORDER BY month ASC''',
        (user_id, f'-{months_back}')
    ).fetchall()

    result = []
    for r in rows:
        try:
            dt = datetime.strptime(r['month'], '%Y-%m')
            result.append({
                'month': r['month'],
                'label': dt.strftime('%b/%Y'),
                'total': float(r['total'] or 0),
            })
        except Exception:
            pass
    return result


# ══════════════════════════════════════════════════════════════
# COMPARAÇÃO PESSOAL vs OFICIAL
# ══════════════════════════════════════════════════════════════

def compare_personal_vs_official(
    db_connection, user_id: int
) -> dict:
    """
    Compara inflação pessoal com IPCA oficial.
    CORRIGIDO: todos os valores None tratados como 0.0
    Funciona com qualquer quantidade de dados.
    """
    try:
        personal = calculate_personal_inflation(
            db_connection, user_id
        )

        if not personal.get('has_data'):
            return {
                'has_data': False,
                'message':  personal.get(
                    'message', 'Dados insuficientes'
                ),
            }

        current_year = personal.get('current_year', datetime.now().year)
        prev_year    = personal.get('prev_year', current_year - 1)
        mode         = personal.get('mode', 'basico')

        # ── IPCA acumulado ────────────────────────────────────
        ipca_rows = db_connection.execute(
            '''SELECT ref_date, value
               FROM inflation_official
               WHERE series_code = 'IPCA'
               AND strftime('%Y', ref_date) = ?
               ORDER BY ref_date ASC''',
            (str(current_year),)
        ).fetchall()

        ipca_prev_rows = db_connection.execute(
            '''SELECT ref_date, value
               FROM inflation_official
               WHERE series_code = 'IPCA'
               AND strftime('%Y', ref_date) = ?
               ORDER BY ref_date ASC''',
            (str(prev_year),)
        ).fetchall()

        def acumular_ipca(rows):
            if not rows:
                return 0.0
            fator = 1.0
            for r in rows:
                val = r['value']
                if val is not None:
                    fator *= (1 + float(val) / 100)
            return round((fator - 1) * 100, 2)

        ipca_current_acum = acumular_ipca(ipca_rows)
        ipca_prev_acum    = acumular_ipca(ipca_prev_rows)

        # IPCA mensal para gráfico
        ipca_monthly = []
        for r in ipca_rows:
            try:
                dt = datetime.strptime(r['ref_date'], '%Y-%m-%d')
                ipca_monthly.append({
                    'month': r['ref_date'][:7],
                    'value': float(r['value'] or 0),
                    'label': dt.strftime('%b/%Y')
                })
            except Exception:
                pass

        # ── INPC acumulado ────────────────────────────────────
        inpc_row = db_connection.execute(
            '''SELECT COALESCE(SUM(value), 0) AS total
               FROM inflation_official
               WHERE series_code = 'INPC'
               AND strftime('%Y', ref_date) = ?''',
            (str(current_year),)
        ).fetchone()
        inpc_acum = float(inpc_row['total'] or 0)

        # ── IGP-M acumulado ───────────────────────────────────
        igpm_row = db_connection.execute(
            '''SELECT COALESCE(SUM(value), 0) AS total
               FROM inflation_official
               WHERE series_code = 'IGP_M'
               AND strftime('%Y', ref_date) = ?''',
            (str(current_year),)
        ).fetchone()
        igpm_acum = float(igpm_row['total'] or 0)

        # ── Inflação pessoal ──────────────────────────────────
        personal_inflation = float(
            personal.get('personal_inflation') or 0
        )
        diff_vs_ipca = personal_inflation - ipca_current_acum

        # ── Por categoria vs IPCA ─────────────────────────────
        categories_vs_ipca = []
        for cat in personal.get('categories', []):
            if not cat.get('has_prev'):
                continue
            variation = float(cat.get('variation') or 0)
            diff      = variation - ipca_current_acum
            categories_vs_ipca.append({
                **cat,
                'variation':    variation,
                'diff_vs_ipca': round(diff, 2),
                'above_ipca':   diff > 0,
            })

        categories_vs_ipca.sort(
            key=lambda x: x.get('diff_vs_ipca', 0),
            reverse=True
        )

        # ── Insights ──────────────────────────────────────────
        insights = _generate_inflation_insights(
            personal_inflation=personal_inflation,
            ipca=ipca_current_acum,
            inpc=inpc_acum,
            igpm=igpm_acum,
            diff=diff_vs_ipca,
            categories=categories_vs_ipca,
            monthly_yoy=personal.get('monthly_yoy', []),
            mode=mode,
            period=personal.get('period', {}),
            monthly_data=personal.get('monthly_data', []),
        )

        return {
            'has_data':            True,
            'mode':                mode,
            'period_description':  personal.get('period_description', ''),
            'label_current':       personal.get(
                'label_current', str(current_year)
            ),
            'label_prev':          personal.get(
                'label_prev', str(prev_year)
            ),
            'current_year':        current_year,
            'prev_year':           prev_year,

            # Inflação pessoal
            'personal_inflation':  round(personal_inflation, 2),
            'total_current_avg':   float(
                personal.get('total_current_avg') or 0
            ),
            'total_prev_avg':      float(
                personal.get('total_prev_avg') or 0
            ),

            # Índices oficiais
            'ipca_acum':           round(ipca_current_acum, 2),
            'ipca_prev_acum':      round(ipca_prev_acum, 2),
            'inpc_acum':           round(inpc_acum, 2),
            'igpm_acum':           round(igpm_acum, 2),
            'ipca_monthly':        ipca_monthly,
            'has_official_data':   len(ipca_rows) > 0,

            # Comparação
            'diff_vs_ipca':        round(diff_vs_ipca, 2),
            'above_ipca':          diff_vs_ipca > 0,

            # Categorias
            'categories':          personal.get('categories', []),
            'categories_vs_ipca':  categories_vs_ipca,
            'top_inflation':       personal.get('top_inflation', []),
            'deflated':            personal.get('deflated', []),

            # Séries temporais
            'monthly_yoy':         personal.get('monthly_yoy', []),
            'monthly_data':        personal.get('monthly_data', []),

            # Insights
            'insights':            insights,
        }

    except Exception as e:
        print(f'[Inflation] Erro na comparação: {e}')
        import traceback
        traceback.print_exc()
        return {'has_data': False, 'message': str(e)}


# ══════════════════════════════════════════════════════════════
# GERAÇÃO DE INSIGHTS ADAPTATIVA
# ══════════════════════════════════════════════════════════════

def _generate_inflation_insights(
    personal_inflation: float,
    ipca: float,
    inpc: float,
    igpm: float,
    diff: float,
    categories: list,
    monthly_yoy: list,
    mode: str = 'anual',
    period: dict = None,
    monthly_data: list = None,
) -> list:
    """
    Gera insights automáticos sobre a inflação.
    CORRIGIDO: todos os valores garantidos como float.
    Adaptativo ao modo de cálculo.
    """
    insights = []

    # ── Garantir tipos corretos ───────────────────────────────
    personal_inflation = float(personal_inflation or 0)
    ipca               = float(ipca  or 0)
    inpc               = float(inpc  or 0)
    igpm               = float(igpm  or 0)
    diff               = float(diff  or 0)
    period             = period or {}
    monthly_data       = monthly_data or []

    # ── Informação do modo de cálculo ─────────────────────────
    mode_labels = {
        'anual':      'comparação anual',
        'semestral':  'comparação semestral',
        'trimestral': 'comparação trimestral',
        'basico':     'análise do período disponível',
    }
    mode_label = mode_labels.get(mode, mode)

    if mode in ('trimestral', 'basico'):
        insights.append({
            'type':    'info',
            'emoji':   'ℹ️',
            'message': (
                f'Análise baseada em {mode_label}. '
                f'Acumule mais dados para análises mais precisas. '
                f'({period.get("description", "")})'
            )
        })

    # ── Comparação com IPCA ───────────────────────────────────
    if ipca > 0:
        if diff > 5:
            insights.append({
                'type':    'critical',
                'emoji':   '🚨',
                'message': (
                    f'Sua inflação pessoal ({personal_inflation:.1f}%) '
                    f'está {diff:.1f}% ACIMA do IPCA oficial '
                    f'({ipca:.1f}%). Seus gastos sobem muito mais '
                    f'que a inflação média!'
                )
            })
        elif diff > 2:
            insights.append({
                'type':    'warning',
                'emoji':   '⚠️',
                'message': (
                    f'Você está pagando {diff:.1f}% a mais que '
                    f'a inflação oficial (IPCA {ipca:.1f}%). '
                    f'Revise seus gastos principais.'
                )
            })
        elif diff < -2:
            insights.append({
                'type':    'positive',
                'emoji':   '✅',
                'message': (
                    f'Parabéns! Sua inflação pessoal '
                    f'({personal_inflation:.1f}%) está abaixo '
                    f'do IPCA ({ipca:.1f}%). Você está '
                    f'controlando bem seus gastos!'
                )
            })
        else:
            insights.append({
                'type':    'info',
                'emoji':   'ℹ️',
                'message': (
                    f'Sua inflação pessoal ({personal_inflation:.1f}%) '
                    f'está alinhada com o IPCA ({ipca:.1f}%).'
                )
            })
    else:
        # Sem IPCA ainda
        if personal_inflation > 10:
            insights.append({
                'type':    'warning',
                'emoji':   '⚠️',
                'message': (
                    f'Seus gastos aumentaram {personal_inflation:.1f}% '
                    f'no período analisado. '
                    f'Verifique as categorias com maior alta.'
                )
            })
        elif personal_inflation > 0:
            insights.append({
                'type':    'info',
                'emoji':   'ℹ️',
                'message': (
                    f'Seus gastos aumentaram {personal_inflation:.1f}% '
                    f'no período analisado.'
                )
            })
        elif personal_inflation < 0:
            insights.append({
                'type':    'positive',
                'emoji':   '✅',
                'message': (
                    f'Seus gastos diminuíram '
                    f'{abs(personal_inflation):.1f}% '
                    f'no período analisado!'
                )
            })
        else:
            insights.append({
                'type':    'info',
                'emoji':   'ℹ️',
                'message': (
                    'Seus gastos estão estáveis no período. '
                    'Clique em "Atualizar BCB" para comparar '
                    'com o IPCA oficial.'
                )
            })

    # ── Categorias com maior alta ─────────────────────────────
    if categories:
        top = [
            c for c in categories
            if float(c.get('variation', 0) or 0) > 0
        ][:3]

        for cat in top:
            var = float(cat.get('variation', 0) or 0)
            if var > 20:
                diff_ipca = cat.get('diff_vs_ipca')
                insights.append({
                    'type':    'warning',
                    'emoji':   '📈',
                    'message': (
                        f'"{cat["category"]}" subiu '
                        f'{var:.1f}% no período'
                        + (
                            f' ({diff_ipca:+.1f}% vs IPCA)'
                            if ipca > 0 and diff_ipca is not None
                            else ''
                        )
                    )
                })

        # Categorias abaixo do IPCA
        if ipca > 0:
            below = [
                c for c in categories
                if c.get('diff_vs_ipca') is not None and
                float(c['diff_vs_ipca'] or 0) < -3
            ]
            if below:
                names = ', '.join(
                    f'"{c["category"]}"' for c in below[:2]
                )
                insights.append({
                    'type':    'positive',
                    'emoji':   '💚',
                    'message': (
                        f'{names}: gastos abaixo do IPCA. '
                        f'Continue assim!'
                    )
                })

    # ── Tendência recente (YoY) ───────────────────────────────
    if monthly_yoy and len(monthly_yoy) >= 3:
        recent     = monthly_yoy[-3:]
        avg_recent = sum(
            m['yoy_pct'] for m in recent
        ) / len(recent)

        if avg_recent > 15:
            insights.append({
                'type':    'critical',
                'emoji':   '🔥',
                'message': (
                    f'Nos últimos 3 meses seus gastos cresceram '
                    f'em média {avg_recent:.1f}% vs mesmo período '
                    f'do ano passado. Tendência de alta acelerada!'
                )
            })
        elif avg_recent < -5:
            insights.append({
                'type':    'positive',
                'emoji':   '📉',
                'message': (
                    f'Tendência de queda nos gastos: '
                    f'{avg_recent:.1f}% vs mesmo período '
                    f'do ano passado. Ótimo controle!'
                )
            })

    # ── Tendência dos dados mensais (modo básico/trimestral) ──
    if mode in ('basico', 'trimestral') and len(monthly_data) >= 2:
        totals = [m['total'] for m in monthly_data]
        first  = totals[0]
        last   = totals[-1]
        if first > 0:
            trend = (last - first) / first * 100
            if trend > 15:
                insights.append({
                    'type':    'warning',
                    'emoji':   '📊',
                    'message': (
                        f'Seus gastos mensais cresceram '
                        f'{trend:.1f}% desde '
                        f'{monthly_data[0]["label"]}.'
                    )
                })
            elif trend < -10:
                insights.append({
                    'type':    'positive',
                    'emoji':   '📊',
                    'message': (
                        f'Seus gastos mensais reduziram '
                        f'{abs(trend):.1f}% desde '
                        f'{monthly_data[0]["label"]}. Ótimo!'
                    )
                })

    # ── IGP-M ─────────────────────────────────────────────────
    if igpm > 0 and personal_inflation > igpm + 3:
        insights.append({
            'type':    'attention',
            'emoji':   '🏠',
            'message': (
                f'Sua inflação pessoal ({personal_inflation:.1f}%) '
                f'está acima do IGP-M ({igpm:.1f}%). '
                f'Verifique gastos com aluguel e serviços.'
            )
        })

    # ── INPC ──────────────────────────────────────────────────
    if inpc > 0 and personal_inflation > inpc + 5:
        insights.append({
            'type':    'attention',
            'emoji':   '👷',
            'message': (
                f'Sua inflação pessoal ({personal_inflation:.1f}%) '
                f'está bem acima do INPC ({inpc:.1f}%), '
                f'índice das classes de menor renda.'
            )
        })

    # ── Fallback ──────────────────────────────────────────────
    if not insights:
        insights.append({
            'type':    'info',
            'emoji':   'ℹ️',
            'message': (
                'Continue registrando suas transações para '
                'gerar insights de inflação mais precisos!'
            )
        })

    return insights


# ══════════════════════════════════════════════════════════════
# CORRELAÇÃO INFLAÇÃO × CÂMBIO
# ══════════════════════════════════════════════════════════════

def correlate_inflation_currency(
    db_connection, user_id: int
) -> dict:
    """
    Correlaciona variação dos gastos mensais com
    IPCA e câmbio simultaneamente.
    """
    if not NUMPY_AVAILABLE:
        return {
            'has_data': False,
            'message':  'numpy não disponível'
        }

    try:
        expenses = db_connection.execute(
            '''SELECT
                   strftime('%Y-%m', date) AS month,
                   SUM(amount)             AS total
               FROM transactions
               WHERE user_id = ?
               AND transaction_type = 'saida'
               GROUP BY month
               ORDER BY month ASC''',
            (user_id,)
        ).fetchall()

        if len(expenses) < 4:
            return {
                'has_data': False,
                'message':  (
                    f'Mínimo 4 meses de dados necessários '
                    f'(você tem {len(expenses)})'
                )
            }

        month_map = {
            r['month']: float(r['total'] or 0)
            for r in expenses
        }
        months = sorted(month_map.keys())

        # IPCA mensal
        ipca_data = db_connection.execute(
            '''SELECT strftime('%Y-%m', ref_date) AS month,
                      value
               FROM inflation_official
               WHERE series_code = 'IPCA'
               AND ref_date >= ?
               ORDER BY ref_date ASC''',
            (months[0] + '-01',)
        ).fetchall()
        ipca_map = {
            r['month']: float(r['value'] or 0)
            for r in ipca_data
        }

        # USD/BRL mensal
        usd_data = db_connection.execute(
            '''SELECT strftime('%Y-%m', rate_date) AS month,
                      AVG(close_rate) AS avg_rate
               FROM currency_rates
               WHERE pair = 'USDBRL'
               AND rate_date >= ?
               GROUP BY month
               ORDER BY month ASC''',
            (months[0] + '-01',)
        ).fetchall()
        usd_map = {
            r['month']: float(r['avg_rate'] or 0)
            for r in usd_data
        }

        # Meses com pelo menos gastos (IPCA e USD opcionais)
        has_ipca = any(m in ipca_map for m in months)
        has_usd  = any(m in usd_map  for m in months)

        # Usar apenas gastos se não tiver IPCA/USD
        if not has_ipca and not has_usd:
            return {
                'has_data':  True,
                'months':    months,
                'chart_data': [
                    {
                        'month':    m,
                        'expenses': month_map[m],
                        'ipca':     0,
                        'usd':      0,
                    }
                    for m in months
                ],
                'corr_ipca':       0,
                'corr_usd':        0,
                'dominant':        'sem_dados',
                'dominant_label':  'Sem dados de IPCA/Câmbio',
                'months_analyzed': len(months),
                'has_ipca':        False,
                'has_usd':         False,
            }

        # Interseção ou usar meses disponíveis
        if has_ipca and has_usd:
            common_months = [
                m for m in months
                if m in ipca_map and m in usd_map
            ]
        elif has_ipca:
            common_months = [m for m in months if m in ipca_map]
        else:
            common_months = [m for m in months if m in usd_map]

        if len(common_months) < 3:
            # Usar todos os meses com dados parciais
            common_months = months

        expenses_arr = np.array(
            [month_map[m] for m in common_months]
        )
        ipca_arr     = np.array(
            [ipca_map.get(m, 0) for m in common_months]
        )
        usd_arr      = np.array(
            [usd_map.get(m, 0) for m in common_months]
        )

        # Correlações
        corr_ipca = 0.0
        corr_usd  = 0.0

        if len(expenses_arr) > 2:
            if has_ipca and np.std(ipca_arr) > 0:
                corr_ipca = float(
                    np.corrcoef(expenses_arr, ipca_arr)[0, 1]
                )
            if has_usd and np.std(usd_arr) > 0:
                corr_usd = float(
                    np.corrcoef(expenses_arr, usd_arr)[0, 1]
                )

        # Fator dominante
        if has_ipca and has_usd:
            if abs(corr_ipca) > abs(corr_usd) + 0.1:
                dominant       = 'ipca'
                dominant_label = 'IPCA (Inflação Oficial)'
            elif abs(corr_usd) > abs(corr_ipca) + 0.1:
                dominant       = 'usd'
                dominant_label = 'Câmbio USD/BRL'
            else:
                dominant       = 'ambos'
                dominant_label = 'IPCA e Câmbio igualmente'
        elif has_ipca:
            dominant       = 'ipca'
            dominant_label = 'IPCA (único dado disponível)'
        elif has_usd:
            dominant       = 'usd'
            dominant_label = 'Câmbio USD/BRL (único dado disponível)'
        else:
            dominant       = 'sem_dados'
            dominant_label = 'Sem dados suficientes'

        chart_data = [
            {
                'month':    m,
                'expenses': month_map.get(m, 0),
                'ipca':     ipca_map.get(m, 0),
                'usd':      usd_map.get(m, 0),
            }
            for m in common_months
        ]

        return {
            'has_data':        True,
            'months':          common_months,
            'chart_data':      chart_data,
            'corr_ipca':       round(corr_ipca, 3),
            'corr_usd':        round(corr_usd,  3),
            'dominant':        dominant,
            'dominant_label':  dominant_label,
            'months_analyzed': len(common_months),
            'has_ipca':        has_ipca,
            'has_usd':         has_usd,
        }

    except Exception as e:
        print(f'[Inflation] Erro na correlação: {e}')
        import traceback
        traceback.print_exc()
        return {'has_data': False, 'message': str(e)}


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def get_ipca_for_period(
    db_connection,
    start_date: str,
    end_date: str = None
) -> list:
    """Retorna IPCA mensal para um período"""
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    rows = db_connection.execute(
        '''SELECT ref_date, value,
                  strftime('%Y-%m', ref_date) AS month
           FROM inflation_official
           WHERE series_code = 'IPCA'
           AND ref_date BETWEEN ? AND ?
           ORDER BY ref_date ASC''',
        (start_date, end_date)
    ).fetchall()

    return [dict(r) for r in rows]


def get_accumulated_ipca(
    db_connection, year: int = None
) -> float:
    """Retorna IPCA acumulado de um ano"""
    if year is None:
        year = datetime.now().year

    rows = db_connection.execute(
        '''SELECT value FROM inflation_official
           WHERE series_code = 'IPCA'
           AND strftime('%Y', ref_date) = ?
           ORDER BY ref_date ASC''',
        (str(year),)
    ).fetchall()

    if not rows:
        return 0.0

    fator = 1.0
    for r in rows:
        val = r['value']
        if val is not None:
            fator *= (1 + float(val) / 100)
    return round((fator - 1) * 100, 2)


def has_official_data(db_connection) -> bool:
    """Verifica se há dados oficiais do BCB"""
    try:
        count = db_connection.execute(
            "SELECT COUNT(*) FROM inflation_official "
            "WHERE series_code = 'IPCA'"
        ).fetchone()[0]
        return count > 0
    except Exception:
        return False

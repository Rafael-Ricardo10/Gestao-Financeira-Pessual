"""
Rastreador de cotações de moedas usando yFinance
Salva histórico no banco de dados para evitar consultas repetidas
Busca cotação apenas uma vez por dia (fechamento)
"""
import json
from datetime import datetime, timedelta, date

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("[Currency] yfinance não instalado.")


# Pares de moeda a monitorar
CURRENCY_PAIRS = {
    'USDBRL': {'ticker': 'USDBRL=X', 'label': 'USD/BRL'},
    'EURBRL': {'ticker': 'EURBRL=X', 'label': 'EUR/BRL'},
    'BTCBRL': {'ticker': 'BTC-BRL',  'label': 'BTC/BRL'},
}


def create_currency_tables(db_connection):
    """Cria tabelas para armazenar histórico de cotações"""
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS currency_rates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pair        TEXT    NOT NULL,
            rate_date   TEXT    NOT NULL,
            open_rate   REAL,
            close_rate  REAL    NOT NULL,
            high_rate   REAL,
            low_rate    REAL,
            fetched_at  TEXT    NOT NULL,
            UNIQUE(pair, rate_date)
        )
    ''')
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS currency_analysis (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            pair            TEXT    NOT NULL,
            analysis_date   TEXT    NOT NULL,
            category_id     INTEGER,
            correlation     REAL    DEFAULT 0,
            impact_score    REAL    DEFAULT 0,
            notes           TEXT,
            created_at      TEXT    NOT NULL,
            FOREIGN KEY (user_id)    REFERENCES users (id),
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    db_connection.commit()


def get_last_fetched_date(db_connection, pair: str):
    """Retorna a última data em que a cotação foi buscada"""
    row = db_connection.execute(
        '''SELECT MAX(rate_date) as last_date
           FROM currency_rates WHERE pair = ?''',
        (pair,)
    ).fetchone()
    return row['last_date'] if row and row['last_date'] else None


def needs_update(db_connection, pair: str) -> bool:
    """
    Verifica se precisa atualizar a cotação.
    Atualiza apenas uma vez por dia (após fechamento).
    """
    last_date = get_last_fetched_date(db_connection, pair)
    if not last_date:
        return True

    today     = date.today().strftime('%Y-%m-%d')
    yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Se já tem de hoje ou ontem, não precisa atualizar
    # (mercado fecha às 18h BRT)
    now_hour = datetime.now().hour
    if last_date == today and now_hour < 18:
        return False
    if last_date >= yesterday:
        return False
    return True


def fetch_and_save_latest(db_connection, pair: str) -> bool:
    """
    Busca e salva a cotação mais recente se necessário.
    Retorna True se atualizou, False se não precisou.
    """
    if not YFINANCE_AVAILABLE:
        return False

    if not needs_update(db_connection, pair):
        return False

    try:
        ticker_info = CURRENCY_PAIRS.get(pair)
        if not ticker_info:
            return False

        ticker = yf.Ticker(ticker_info['ticker'])
        hist   = ticker.history(period='5d')

        if hist.empty:
            return False

        fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for idx, row in hist.iterrows():
            rate_date = idx.strftime('%Y-%m-%d')
            try:
                db_connection.execute(
                    '''INSERT OR REPLACE INTO currency_rates
                       (pair, rate_date, open_rate, close_rate,
                        high_rate, low_rate, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        pair,
                        rate_date,
                        round(float(row['Open']),  4),
                        round(float(row['Close']), 4),
                        round(float(row['High']),  4),
                        round(float(row['Low']),   4),
                        fetched_at
                    )
                )
            except Exception:
                pass

        db_connection.commit()
        print(f"[Currency] {pair} atualizado.")
        return True

    except Exception as e:
        print(f"[Currency] Erro ao buscar {pair}: {e}")
        return False


def fetch_history_since(
    db_connection, pair: str, since_date: str
) -> bool:
    """
    Busca histórico desde uma data específica.
    Usado para baixar histórico desde a primeira transação.
    """
    if not YFINANCE_AVAILABLE:
        return False

    try:
        # Verificar se já tem dados desta data
        existing = db_connection.execute(
            '''SELECT COUNT(*) FROM currency_rates
               WHERE pair = ? AND rate_date >= ?''',
            (pair, since_date)
        ).fetchone()[0]

        # Calcular quantos dias de histórico precisamos
        since_dt = datetime.strptime(since_date, '%Y-%m-%d')
        days     = (datetime.now() - since_dt).days + 5

        if existing > (days * 0.8):
            # Já tem a maioria dos dados
            return False

        ticker_info = CURRENCY_PAIRS.get(pair)
        if not ticker_info:
            return False

        print(
            f"[Currency] Baixando histórico de {pair} "
            f"desde {since_date}..."
        )

        ticker = yf.Ticker(ticker_info['ticker'])
        hist   = ticker.history(
            start=since_date,
            end=datetime.now().strftime('%Y-%m-%d')
        )

        if hist.empty:
            return False

        fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        count      = 0

        for idx, row in hist.iterrows():
            rate_date = idx.strftime('%Y-%m-%d')
            try:
                db_connection.execute(
                    '''INSERT OR IGNORE INTO currency_rates
                       (pair, rate_date, open_rate, close_rate,
                        high_rate, low_rate, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        pair,
                        rate_date,
                        round(float(row['Open']),  4),
                        round(float(row['Close']), 4),
                        round(float(row['High']),  4),
                        round(float(row['Low']),   4),
                        fetched_at
                    )
                )
                count += 1
            except Exception:
                pass

        db_connection.commit()
        print(
            f"[Currency] {pair}: {count} registros históricos salvos."
        )
        return True

    except Exception as e:
        print(f"[Currency] Erro ao buscar histórico {pair}: {e}")
        return False


def get_rates_for_period(
    db_connection, pair: str,
    start_date: str, end_date: str = None
) -> list:
    """Retorna cotações salvas para um período"""
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    rows = db_connection.execute(
        '''SELECT rate_date, open_rate, close_rate,
                  high_rate, low_rate
           FROM currency_rates
           WHERE pair = ?
           AND rate_date BETWEEN ? AND ?
           ORDER BY rate_date ASC''',
        (pair, start_date, end_date)
    ).fetchall()

    return [dict(r) for r in rows]


def get_current_rate(db_connection, pair: str) -> dict:
    """Retorna a cotação mais recente salva"""
    fetch_and_save_latest(db_connection, pair)

    row = db_connection.execute(
        '''SELECT * FROM currency_rates
           WHERE pair = ?
           ORDER BY rate_date DESC
           LIMIT 1''',
        (pair,)
    ).fetchone()

    if row:
        return dict(row)
    return {}


def analyze_currency_impact(
    db_connection, user_id: int, pair: str = 'USDBRL'
) -> dict:
    """
    Analisa o impacto da variação cambial nos gastos do usuário.
    Compara variação do câmbio com variação dos gastos mensais.
    """
    try:
        # Data da primeira transação do usuário
        first_trans = db_connection.execute(
            '''SELECT MIN(date) as first_date
               FROM transactions WHERE user_id = ?''',
            (user_id,)
        ).fetchone()

        if not first_trans or not first_trans['first_date']:
            return {'has_data': False, 'message': 'Sem transações'}

        since_date = first_trans['first_date']

        # Garantir histórico de câmbio desde a primeira transação
        fetch_history_since(db_connection, pair, since_date)

        # Buscar gastos mensais do usuário
        monthly_expenses = db_connection.execute(
            '''SELECT
                   strftime('%Y-%m', date) AS month,
                   SUM(amount)             AS total
               FROM transactions
               WHERE user_id = ? AND transaction_type = 'saida'
               AND date >= ?
               GROUP BY month
               ORDER BY month''',
            (user_id, since_date)
        ).fetchall()

        if not monthly_expenses:
            return {'has_data': False, 'message': 'Sem despesas'}

        # Buscar câmbio médio por mês
        monthly_rates = db_connection.execute(
            '''SELECT
                   strftime('%Y-%m', rate_date) AS month,
                   AVG(close_rate)              AS avg_rate,
                   MIN(close_rate)              AS min_rate,
                   MAX(close_rate)              AS max_rate
               FROM currency_rates
               WHERE pair = ?
               AND rate_date >= ?
               GROUP BY month
               ORDER BY month''',
            (pair, since_date)
        ).fetchall()

        # Cruzar dados
        rate_map = {
            r['month']: {
                'avg': r['avg_rate'],
                'min': r['min_rate'],
                'max': r['max_rate']
            }
            for r in monthly_rates
        }

        combined = []
        for expense in monthly_expenses:
            month = expense['month']
            rate  = rate_map.get(month)
            if rate:
                combined.append({
                    'month':    month,
                    'expenses': expense['total'],
                    'rate':     rate['avg'],
                    'rate_min': rate['min'],
                    'rate_max': rate['max'],
                })

        if len(combined) < 2:
            return {
                'has_data': True,
                'message':  'Dados insuficientes para correlação',
                'combined': combined,
                'pair':     pair,
                'pair_label': CURRENCY_PAIRS.get(
                    pair, {}
                ).get('label', pair)
            }

        # Calcular correlação simples
        import numpy as np
        expenses_arr = np.array([c['expenses'] for c in combined])
        rates_arr    = np.array([c['rate']     for c in combined])

        # Variação percentual mês a mês
        expense_var = np.diff(expenses_arr) / expenses_arr[:-1] * 100
        rate_var    = np.diff(rates_arr)    / rates_arr[:-1]    * 100

        if len(expense_var) > 1 and len(rate_var) > 1:
            correlation = float(np.corrcoef(
                expense_var, rate_var
            )[0, 1])
        else:
            correlation = 0

        # Tendência do câmbio
        rate_slope = 0
        if len(rates_arr) >= 2:
            x          = np.arange(len(rates_arr))
            slope, _   = np.polyfit(x, rates_arr, 1)
            avg        = np.mean(rates_arr)
            rate_slope = float(slope / avg) if avg != 0 else 0

        # Taxa atual vs início
        first_rate   = combined[0]['rate']
        last_rate    = combined[-1]['rate']
        rate_change  = (
            (last_rate - first_rate) / first_rate * 100
            if first_rate > 0 else 0
        )

        # Primeira e última despesa
        first_expense = combined[0]['expenses']
        last_expense  = combined[-1]['expenses']
        expense_change = (
            (last_expense - first_expense) / first_expense * 100
            if first_expense > 0 else 0
        )

        # Interpretar correlação
        if correlation > 0.5:
            interpretation = (
                'Alta correlacao positiva: quando o cambio sobe, '
                'seus gastos tendem a subir tambem.'
            )
        elif correlation < -0.5:
            interpretation = (
                'Alta correlacao negativa: quando o cambio sobe, '
                'seus gastos tendem a cair.'
            )
        elif abs(correlation) < 0.2:
            interpretation = (
                'Baixa correlacao: o cambio nao parece '
                'influenciar muito seus gastos.'
            )
        else:
            interpretation = (
                'Correlacao moderada entre cambio e gastos.'
            )

        # Estimativa de inflação importada
        inflation_impact = 0
        if correlation > 0.3 and rate_change > 0:
            inflation_impact = rate_change * correlation

        return {
            'has_data':          True,
            'pair':              pair,
            'pair_label':        CURRENCY_PAIRS.get(
                pair, {}
            ).get('label', pair),
            'combined':          combined,
            'correlation':       round(correlation, 3),
            'interpretation':    interpretation,
            'rate_slope':        round(rate_slope, 4),
            'rate_direction':    (
                'subindo'  if rate_slope > 0.02 else
                'caindo'   if rate_slope < -0.02 else
                'estavel'
            ),
            'first_rate':        round(first_rate, 4),
            'last_rate':         round(last_rate, 4),
            'rate_change_pct':   round(rate_change, 2),
            'expense_change_pct': round(expense_change, 2),
            'inflation_impact':  round(inflation_impact, 2),
            'months_analyzed':   len(combined),
            'since_date':        since_date,
        }

    except Exception as e:
        print(f"[Currency] Erro na análise: {e}")
        import traceback
        traceback.print_exc()
        return {'has_data': False, 'message': str(e)}


def get_all_current_rates(db_connection) -> dict:
    """
    Retorna cotações atuais de todos os pares monitorados.
    Atualiza apenas se necessário (uma vez por dia).
    """
    result = {}
    for pair in CURRENCY_PAIRS:
        rate = get_current_rate(db_connection, pair)
        if rate:
            result[pair] = {
                'label':      CURRENCY_PAIRS[pair]['label'],
                'rate':       rate.get('close_rate', 0),
                'date':       rate.get('rate_date', ''),
                'open':       rate.get('open_rate', 0),
                'high':       rate.get('high_rate', 0),
                'low':        rate.get('low_rate', 0),
            }
    return result


# ── BTC via USD (movido do antigo diálogo de cotações) ──────────

def get_btc_brl_via_usd(thread_conn) -> bool:
    """
    Busca BTC-USD e converte para BRL usando USDBRL.
    Salva na tabela currency_rates como par 'BTCBRL'.
    Retorna True se salvou novos dados.
    """
    try:
        import yfinance as yf

        # Verificar se precisa atualizar
        from modulos.currency_tracker import needs_update
        if not needs_update(thread_conn, 'BTCBRL'):
            return False

        # Buscar BTC-USD
        btc_ticker = yf.Ticker('BTC-USD')
        btc_hist   = btc_ticker.history(period='5d')
        if btc_hist.empty:
            print('[Currency] BTC-USD sem dados.')
            return False

        # Buscar USDBRL para conversão
        usd_ticker = yf.Ticker('USDBRL=X')
        usd_hist   = usd_ticker.history(period='5d')
        if usd_hist.empty:
            print('[Currency] USDBRL sem dados para conversão BTC.')
            return False

        fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        count      = 0

        for idx, row in btc_hist.iterrows():
            rate_date = idx.strftime('%Y-%m-%d')

            # Buscar taxa USD/BRL mais próxima desta data
            usd_row = None
            if rate_date in usd_hist.index.strftime('%Y-%m-%d').tolist():
                date_idx = usd_hist.index.strftime(
                    '%Y-%m-%d'
                ).tolist().index(rate_date)
                usd_row = usd_hist.iloc[date_idx]
            else:
                # Usar última taxa disponível
                usd_row = usd_hist.iloc[-1]

            if usd_row is None:
                continue

            usd_brl = float(usd_row['Close'])

            try:
                thread_conn.execute(
                    '''INSERT OR REPLACE INTO currency_rates
                       (pair, rate_date, open_rate, close_rate,
                        high_rate, low_rate, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        'BTCBRL',
                        rate_date,
                        round(float(row['Open'])  * usd_brl, 2),
                        round(float(row['Close']) * usd_brl, 2),
                        round(float(row['High'])  * usd_brl, 2),
                        round(float(row['Low'])   * usd_brl, 2),
                        fetched_at
                    )
                )
                count += 1
            except Exception:
                pass

        thread_conn.commit()
        print(f'[Currency] BTC/BRL: {count} registros via conversão USD.')
        return count > 0

    except Exception as e:
        print(f'[Currency] Erro ao buscar BTC via USD: {e}')
        return False


def fetch_btc_history_via_usd(
    thread_conn, since_date: str
) -> bool:
    """
    Busca histórico completo de BTC-BRL via conversão BTC-USD × USDBRL.
    Verifica o que já existe antes de buscar.
    """
    try:
        import yfinance as yf

        # Verificar dados existentes
        existing = thread_conn.execute(
            '''SELECT COUNT(*) FROM currency_rates
               WHERE pair = 'BTCBRL' AND rate_date >= ?''',
            (since_date,)
        ).fetchone()[0]

        since_dt = datetime.strptime(since_date, '%Y-%m-%d')
        days     = (datetime.now() - since_dt).days + 5

        if existing > (days * 0.7):
            print(f'[Currency] BTC/BRL já tem {existing} registros.')
            return False

        print(
            f'[Currency] Baixando histórico BTC/BRL desde '
            f'{since_date} via BTC-USD × USDBRL...'
        )

        end_date = datetime.now().strftime('%Y-%m-%d')

        # Buscar histórico BTC-USD
        btc_ticker = yf.Ticker('BTC-USD')
        btc_hist   = btc_ticker.history(
            start=since_date, end=end_date
        )
        if btc_hist.empty:
            print('[Currency] BTC-USD sem histórico.')
            return False

        # Buscar histórico USDBRL
        usd_ticker = yf.Ticker('USDBRL=X')
        usd_hist   = usd_ticker.history(
            start=since_date, end=end_date
        )
        if usd_hist.empty:
            print('[Currency] USDBRL sem histórico para conversão.')
            return False

        # Criar mapa de datas USDBRL
        usd_map = {}
        for idx, row in usd_hist.iterrows():
            usd_map[idx.strftime('%Y-%m-%d')] = float(row['Close'])

        fetched_at  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        count       = 0
        last_usd_brl = list(usd_map.values())[-1] if usd_map else 5.0

        for idx, row in btc_hist.iterrows():
            rate_date = idx.strftime('%Y-%m-%d')

            # Taxa USD/BRL do dia ou a mais recente disponível
            usd_brl = usd_map.get(rate_date, last_usd_brl)
            # Atualizar último valor conhecido
            if rate_date in usd_map:
                last_usd_brl = usd_map[rate_date]

            try:
                thread_conn.execute(
                    '''INSERT OR IGNORE INTO currency_rates
                       (pair, rate_date, open_rate, close_rate,
                        high_rate, low_rate, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        'BTCBRL',
                        rate_date,
                        round(float(row['Open'])  * usd_brl, 2),
                        round(float(row['Close']) * usd_brl, 2),
                        round(float(row['High'])  * usd_brl, 2),
                        round(float(row['Low'])   * usd_brl, 2),
                        fetched_at
                    )
                )
                count += 1
            except Exception:
                pass

        thread_conn.commit()
        print(
            f'[Currency] BTC/BRL histórico: {count} registros salvos.'
        )
        return True

    except Exception as e:
        print(f'[Currency] Erro no histórico BTC via USD: {e}')
        return False


_get_btc_brl_via_usd = get_btc_brl_via_usd
_fetch_btc_history_via_usd = fetch_btc_history_via_usd

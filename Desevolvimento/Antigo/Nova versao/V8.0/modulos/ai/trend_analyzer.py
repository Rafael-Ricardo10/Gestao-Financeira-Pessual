"""
Analisador de tendências com IA
Filtra por categoria e descrição
Detecta padrões de alta/baixa
"""
import numpy as np
from datetime import datetime, timedelta


class TrendAnalyzer:
    """
    Analisa tendências financeiras com filtros avançados.
    Integrado com o motor de IA principal.
    """

    def __init__(self, db_connection, user_id: int, ai_engine=None):
        self.db         = db_connection
        self.user_id    = user_id
        self.ai_engine  = ai_engine

    def get_categories(self) -> list:
        """Retorna categorias disponíveis para filtro"""
        return self.db.execute(
            '''SELECT id, name FROM categories
               WHERE user_id = ?
               AND (is_hidden = 0 OR is_hidden IS NULL)
               ORDER BY name''',
            (self.user_id,)
        ).fetchall()

    def get_descriptions(self, limit: int = 100) -> list:
        """Retorna descrições únicas para filtro"""
        return self.db.execute(
            '''SELECT DISTINCT description
               FROM transactions
               WHERE user_id = ?
               ORDER BY description COLLATE NOCASE
               LIMIT ?''',
            (self.user_id, limit)
        ).fetchall()

    def analyze(
        self,
        category_id: int = None,
        description: str = None,
        months: int = 6,
        trans_type: str = None
    ) -> dict:
        """
        Análise completa de tendências com filtros.

        Args:
            category_id : filtrar por categoria
            description : filtrar por descrição (busca parcial)
            months      : quantos meses analisar
            trans_type  : 'entrada', 'saida' ou None (ambos)
        """
        try:
            today  = datetime.now()
            d_from = (
                today - timedelta(days=30 * months)
            ).strftime('%Y-%m-%d')

            query  = '''
                SELECT
                    strftime('%Y-%m', t.date)  AS month,
                    t.transaction_type,
                    SUM(t.amount)              AS total,
                    COUNT(*)                   AS count,
                    AVG(t.amount)              AS avg_amount,
                    MAX(t.amount)              AS max_amount,
                    MIN(t.amount)              AS min_amount
                FROM transactions t
                WHERE t.user_id = ? AND t.date >= ?
            '''
            params = [self.user_id, d_from]

            if category_id:
                query  += ' AND t.category_id = ?'
                params.append(category_id)

            if description:
                query  += ' AND LOWER(t.description) LIKE ?'
                params.append(f'%{description.lower()}%')

            if trans_type:
                query  += ' AND t.transaction_type = ?'
                params.append(trans_type)

            query += (
                ' GROUP BY month, t.transaction_type'
                ' ORDER BY month'
            )

            rows = self.db.execute(query, params).fetchall()

            if not rows:
                return {'has_data': False, 'message': 'Sem dados para o período'}

            # ── Organizar dados por mês ────────────────────
            all_months       = sorted(set(r['month'] for r in rows))
            income_data      = {}
            expense_data     = {}

            for row in rows:
                m = row['month']
                if row['transaction_type'] == 'entrada':
                    income_data[m] = {
                        'total':      row['total'],
                        'count':      row['count'],
                        'avg':        row['avg_amount'],
                        'max':        row['max_amount'],
                        'min':        row['min_amount'],
                    }
                else:
                    expense_data[m] = {
                        'total':      row['total'],
                        'count':      row['count'],
                        'avg':        row['avg_amount'],
                        'max':        row['max_amount'],
                        'min':        row['min_amount'],
                    }

            # ── Preencher meses sem dados ──────────────────
            for m in all_months:
                if m not in income_data:
                    income_data[m]  = {
                        'total': 0, 'count': 0,
                        'avg': 0, 'max': 0, 'min': 0
                    }
                if m not in expense_data:
                    expense_data[m] = {
                        'total': 0, 'count': 0,
                        'avg': 0, 'max': 0, 'min': 0
                    }

            income_totals  = [income_data[m]['total']  for m in all_months]
            expense_totals = [expense_data[m]['total'] for m in all_months]
            balance_totals = [
                income_data[m]['total'] - expense_data[m]['total']
                for m in all_months
            ]

            # ── Calcular tendências ────────────────────────
            income_slope  = self._slope(income_totals)
            expense_slope = self._slope(expense_totals)
            balance_slope = self._slope(balance_totals)

            # ── Variação mês a mês ─────────────────────────
            income_mom  = self._month_over_month(income_totals)
            expense_mom = self._month_over_month(expense_totals)

            # ── Detecção de anomalias ──────────────────────
            income_anomalies  = self._detect_anomalies(
                income_totals, all_months
            )
            expense_anomalies = self._detect_anomalies(
                expense_totals, all_months
            )

            # ── Sazonalidade ───────────────────────────────
            seasonality = self._detect_seasonality(
                all_months, income_totals, expense_totals
            )

            # ── Insights automáticos ───────────────────────
            insights = self._generate_insights(
                income_totals, expense_totals,
                income_slope, expense_slope,
                income_anomalies, expense_anomalies,
                income_mom, expense_mom,
                category_id, description
            )

            # ── Labels formatados ──────────────────────────
            month_labels = []
            for m in all_months:
                try:
                    dt = datetime.strptime(m, '%Y-%m')
                    month_labels.append(dt.strftime('%b/%Y'))
                except Exception:
                    month_labels.append(m)

            return {
                'has_data':           True,
                'months':             all_months,
                'month_labels':       month_labels,
                'income_totals':      income_totals,
                'expense_totals':     expense_totals,
                'balance_totals':     balance_totals,
                'income_data':        income_data,
                'expense_data':       expense_data,

                # Tendências
                'income_slope':       income_slope,
                'expense_slope':      expense_slope,
                'balance_slope':      balance_slope,
                'income_direction':   self._direction(income_slope),
                'expense_direction':  self._direction(expense_slope),
                'balance_direction':  self._direction(balance_slope),

                # Médias
                'avg_income':   round(np.mean(income_totals), 2),
                'avg_expense':  round(np.mean(expense_totals), 2),
                'avg_balance':  round(np.mean(balance_totals), 2),

                # Variação mês a mês
                'income_mom':   income_mom,
                'expense_mom':  expense_mom,

                # Anomalias
                'income_anomalies':  income_anomalies,
                'expense_anomalies': expense_anomalies,

                # Sazonalidade
                'seasonality':  seasonality,

                # Insights
                'insights':     insights,
            }

        except Exception as e:
            print(f"[TrendAnalyzer] Erro: {e}")
            import traceback
            traceback.print_exc()
            return {'has_data': False, 'message': str(e)}

    def _slope(self, values: list) -> float:
        """Calcula slope normalizado da tendência"""
        if len(values) < 2:
            return 0.0
        x   = np.arange(len(values))
        y   = np.array(values, dtype=float)
        avg = np.mean(y)
        if avg == 0:
            return 0.0
        try:
            slope, _ = np.polyfit(x, y, 1)
            return float(slope / avg)
        except Exception:
            return 0.0

    def _direction(self, slope: float) -> dict:
        """Converte slope em direção com emoji e texto"""
        if slope > 0.08:
            return {
                'code':  'subindo_forte',
                'label': 'Subindo Forte',
                'emoji': '📈🔴',
                'color': '#e74c3c'
            }
        elif slope > 0.03:
            return {
                'code':  'subindo',
                'label': 'Subindo',
                'emoji': '📈',
                'color': '#e67e22'
            }
        elif slope < -0.08:
            return {
                'code':  'caindo_forte',
                'label': 'Caindo Forte',
                'emoji': '📉🟢',
                'color': '#27ae60'
            }
        elif slope < -0.03:
            return {
                'code':  'caindo',
                'label': 'Caindo',
                'emoji': '📉',
                'color': '#2ecc71'
            }
        return {
            'code':  'estavel',
            'label': 'Estável',
            'emoji': '➡️',
            'color': '#3498db'
        }

    def _month_over_month(self, values: list) -> list:
        """Calcula variação percentual mês a mês"""
        result = [0.0]
        for i in range(1, len(values)):
            if values[i - 1] > 0:
                pct = (values[i] - values[i - 1]) / values[i - 1] * 100
                result.append(round(pct, 2))
            else:
                result.append(0.0)
        return result

    def _detect_anomalies(
        self, values: list, months: list
    ) -> list:
        """
        Detecta meses com valores anômalos
        usando desvio padrão (Z-score).
        """
        anomalies = []
        if len(values) < 3:
            return anomalies

        arr  = np.array(values, dtype=float)
        mean = np.mean(arr)
        std  = np.std(arr)

        if std == 0:
            return anomalies

        for i, (v, m) in enumerate(zip(values, months)):
            z = abs(v - mean) / std
            if z > 1.8:
                try:
                    dt    = datetime.strptime(m, '%Y-%m')
                    label = dt.strftime('%b/%Y')
                except Exception:
                    label = m

                anomalies.append({
                    'month':   m,
                    'label':   label,
                    'value':   v,
                    'z_score': round(z, 2),
                    'type':    'alto' if v > mean else 'baixo'
                })

        return anomalies

    def _detect_seasonality(
        self,
        months: list,
        income: list,
        expense: list
    ) -> dict:
        """Detecta padrões sazonais nos dados"""
        if len(months) < 4:
            return {'detected': False}

        month_nums = []
        for m in months:
            try:
                month_nums.append(datetime.strptime(m, '%Y-%m').month)
            except Exception:
                month_nums.append(0)

        # Agrupar por mês do ano
        by_month_income  = {}
        by_month_expense = {}

        for i, mn in enumerate(month_nums):
            if mn not in by_month_income:
                by_month_income[mn]  = []
                by_month_expense[mn] = []
            by_month_income[mn].append(income[i])
            by_month_expense[mn].append(expense[i])

        avg_income_by_month = {
            mn: np.mean(vals)
            for mn, vals in by_month_income.items()
        }
        avg_expense_by_month = {
            mn: np.mean(vals)
            for mn, vals in by_month_expense.items()
        }

        month_names = [
            '', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
            'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'
        ]

        peak_expense_month = max(
            avg_expense_by_month, key=avg_expense_by_month.get
        ) if avg_expense_by_month else None

        peak_income_month = max(
            avg_income_by_month, key=avg_income_by_month.get
        ) if avg_income_by_month else None

        return {
            'detected':             True,
            'peak_expense_month':   peak_expense_month,
            'peak_income_month':    peak_income_month,
            'peak_expense_label':   (
                month_names[peak_expense_month]
                if peak_expense_month else 'N/A'
            ),
            'peak_income_label':    (
                month_names[peak_income_month]
                if peak_income_month else 'N/A'
            ),
            'avg_income_by_month':  avg_income_by_month,
            'avg_expense_by_month': avg_expense_by_month,
        }

    def _generate_insights(
        self,
        income_totals, expense_totals,
        income_slope, expense_slope,
        income_anomalies, expense_anomalies,
        income_mom, expense_mom,
        category_id, description
    ) -> list:
        """Gera insights automáticos em texto"""
        insights = []

        avg_income  = np.mean(income_totals)  if income_totals  else 0
        avg_expense = np.mean(expense_totals) if expense_totals else 0

        # Tendência de gastos
        if expense_slope > 0.08:
            pct = abs(expense_slope) * 100
            insights.append({
                'type':    'warning',
                'emoji':   '🚨',
                'message': f'Gastos aumentando fortemente '
                           f'({pct:.0f}% de tendência). '
                           f'Revise suas despesas!'
            })
        elif expense_slope > 0.03:
            pct = abs(expense_slope) * 100
            insights.append({
                'type':    'attention',
                'emoji':   '⚠️',
                'message': f'Gastos em tendência de alta '
                           f'({pct:.0f}%). Fique atento.'
            })
        elif expense_slope < -0.03:
            pct = abs(expense_slope) * 100
            insights.append({
                'type':    'positive',
                'emoji':   '✅',
                'message': f'Ótimo! Seus gastos estão '
                           f'diminuindo ({pct:.0f}% de redução).'
            })

        # Tendência de receitas
        if income_slope > 0.03:
            insights.append({
                'type':    'positive',
                'emoji':   '💰',
                'message': 'Suas entradas estão crescendo. '
                           'Boa evolução financeira!'
            })
        elif income_slope < -0.05:
            insights.append({
                'type':    'warning',
                'emoji':   '📉',
                'message': 'Suas entradas estão diminuindo. '
                           'Atenção ao orçamento!'
            })

        # Anomalias
        for anomaly in expense_anomalies:
            if anomaly['type'] == 'alto':
                insights.append({
                    'type':    'attention',
                    'emoji':   '🔍',
                    'message': f'Gasto incomum em '
                               f'{anomaly["label"]}: '
                               f'R$ {anomaly["value"]:,.2f} '
                               f'(Z={anomaly["z_score"]})'
                })

        # Última variação mês a mês
        if len(expense_mom) >= 2:
            last_mom = expense_mom[-1]
            if last_mom > 20:
                insights.append({
                    'type':    'warning',
                    'emoji':   '📊',
                    'message': f'Gastos do último mês '
                               f'{last_mom:.0f}% acima '
                               f'do mês anterior!'
                })
            elif last_mom < -20:
                insights.append({
                    'type':    'positive',
                    'emoji':   '📊',
                    'message': f'Gastos do último mês '
                               f'{abs(last_mom):.0f}% abaixo '
                               f'do mês anterior. Parabéns!'
                })

        # Balanço geral
        if avg_income > 0 and avg_expense > avg_income:
            insights.append({
                'type':    'critical',
                'emoji':   '🚨',
                'message': 'ATENÇÃO: Média de gastos maior '
                           'que média de receitas!'
            })

        if not insights:
            insights.append({
                'type':    'info',
                'emoji':   'ℹ️',
                'message': 'Dados insuficientes para gerar '
                           'insights. Continue registrando '
                           'suas transações!'
            })

        return insights

    def get_category_trend_summary(self) -> list:
        """
        Retorna resumo de tendências por categoria.
        Usado no painel principal.
        """
        categories = self.get_categories()
        summaries  = []

        for cat in categories:
            result = self.analyze(
                category_id=cat['id'], months=3
            )
            if not result.get('has_data'):
                continue

            summaries.append({
                'category_id':   cat['id'],
                'category_name': cat['name'],
                'avg_expense':   result.get('avg_expense', 0),
                'avg_income':    result.get('avg_income', 0),
                'expense_dir':   result.get('expense_direction', {}),
                'income_dir':    result.get('income_direction', {}),
                'last_expense':  (
                    result['expense_totals'][-1]
                    if result.get('expense_totals') else 0
                ),
                'last_income':   (
                    result['income_totals'][-1]
                    if result.get('income_totals') else 0
                ),
                'insights':      result.get('insights', [])[:1],
            })

        return sorted(
            summaries,
            key=lambda x: x['avg_expense'],
            reverse=True
        )

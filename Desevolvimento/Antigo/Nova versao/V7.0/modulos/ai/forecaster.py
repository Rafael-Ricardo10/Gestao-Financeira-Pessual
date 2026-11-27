"""
Módulo de previsões futuras com IA
Projeta entradas e saídas baseado no histórico real
CORRIGIDO: query _get_category_breakdown
"""
import numpy as np
from datetime import datetime, timedelta


class FinanceForecaster:
    """
    Gera projeções financeiras futuras usando
    o histórico real do usuário.
    """

    def __init__(
        self, db_connection, user_id: int, ai_engine=None
    ):
        self.db        = db_connection
        self.user_id   = user_id
        self.ai_engine = ai_engine

    def get_full_forecast(self, months_ahead: int = 3) -> dict:
        """
        Retorna projeção completa para os próximos N meses.
        """
        try:
            today        = datetime.now()
            forecasts    = []
            ai_forecasts = []

            if self.ai_engine:
                ai_forecasts = self.ai_engine.get_monthly_forecast(
                    months_ahead
                )

            for i in range(1, months_ahead + 1):
                month_date = today.replace(day=1) + timedelta(
                    days=32 * i
                )
                month_date = month_date.replace(day=1)
                month_str  = month_date.strftime('%Y-%m')

                stat_income  = self._forecast_statistical(
                    month_date, 'entrada'
                )
                stat_expense = self._forecast_statistical(
                    month_date, 'saida'
                )

                ai_data = next(
                    (f for f in ai_forecasts
                     if f.get('month') == month_str),
                    None
                )

                if ai_data and ai_data.get('income', 0) > 0:
                    final_income = (
                        stat_income['amount'] * 0.4 +
                        ai_data['income'] * 0.6
                    )
                    income_conf = max(
                        stat_income['confidence'],
                        ai_data.get('income_conf', 0)
                    )
                else:
                    final_income = stat_income['amount']
                    income_conf  = stat_income['confidence']

                if ai_data and ai_data.get('expense', 0) > 0:
                    final_expense = (
                        stat_expense['amount'] * 0.4 +
                        ai_data['expense'] * 0.6
                    )
                    expense_conf = max(
                        stat_expense['confidence'],
                        ai_data.get('expense_conf', 0)
                    )
                else:
                    final_expense = stat_expense['amount']
                    expense_conf  = stat_expense['confidence']

                # ── CORRIGIDO: query sem alias errado ────────
                category_breakdown = self._get_category_breakdown(
                    month_date
                )

                forecasts.append({
                    'month':             month_str,
                    'month_label':       month_date.strftime('%B %Y'),
                    'predicted_income':  round(final_income, 2),
                    'predicted_expense': round(final_expense, 2),
                    'predicted_balance': round(
                        final_income - final_expense, 2
                    ),
                    'income_confidence':  round(income_conf, 2),
                    'expense_confidence': round(expense_conf, 2),
                    'category_breakdown': category_breakdown,
                    'income_detail':      stat_income.get('details', []),
                    'expense_detail':     stat_expense.get('details', []),
                })

            total_income  = sum(
                f['predicted_income'] for f in forecasts
            )
            total_expense = sum(
                f['predicted_expense'] for f in forecasts
            )
            avg_conf = np.mean(
                [f['income_confidence'] for f in forecasts] +
                [f['expense_confidence'] for f in forecasts]
            ) if forecasts else 0

            return {
                'success':        True,
                'months_ahead':   months_ahead,
                'forecasts':      forecasts,
                'total_income':   round(total_income, 2),
                'total_expense':  round(total_expense, 2),
                'total_balance':  round(
                    total_income - total_expense, 2
                ),
                'avg_confidence': round(float(avg_conf) * 100, 1),
                'generated_at':   datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S'
                ),
            }

        except Exception as e:
            print(f"[Forecaster] Erro: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def _forecast_statistical(
        self, month_date: datetime, trans_type: str
    ) -> dict:
        """Previsão estatística baseada em histórico."""
        month_num = month_date.month
        d_from    = (
            month_date - timedelta(days=365)
        ).strftime('%Y-%m-%d')
        d_to      = datetime.now().strftime('%Y-%m-%d')

        monthly = self.db.execute(
            '''SELECT
                   strftime('%Y-%m', date) AS month,
                   SUM(amount)             AS total,
                   strftime('%m', date)    AS month_num
               FROM transactions
               WHERE user_id = ? AND transaction_type = ?
               AND date BETWEEN ? AND ?
               GROUP BY month
               ORDER BY month''',
            (self.user_id, trans_type, d_from, d_to)
        ).fetchall()

        if not monthly:
            return {'amount': 0, 'confidence': 0, 'details': []}

        values = [r['total'] for r in monthly]
        avg    = np.mean(values)
        std    = np.std(values) if len(values) > 1 else 0

        same_month = [
            r['total'] for r in monthly
            if int(r['month_num']) == month_num
        ]
        seasonal_avg = np.mean(same_month) if same_month else avg

        if same_month:
            predicted = avg * 0.5 + seasonal_avg * 0.5
        else:
            predicted = avg

        if len(values) >= 3:
            recent_avg = np.mean(values[-3:])
            trend_adj  = (
                (recent_avg - avg) / avg if avg > 0 else 0
            )
            predicted  = predicted * (1 + trend_adj * 0.5)

        cv          = std / avg if avg > 0 else 1
        consistency = max(0, 1 - cv)
        data_factor = min(1, len(values) / 6)
        confidence  = consistency * 0.6 + data_factor * 0.4
        details     = self._get_top_descriptions(trans_type)

        return {
            'amount':     max(0, round(predicted, 2)),
            'confidence': round(confidence, 3),
            'std':        round(std, 2),
            'details':    details
        }

    def _get_top_descriptions(
        self, trans_type: str, limit: int = 5
    ) -> list:
        """Retorna as descrições mais frequentes"""
        rows = self.db.execute(
            '''SELECT description,
                      COUNT(*)    AS freq,
                      AVG(amount) AS avg_amount
               FROM transactions
               WHERE user_id = ? AND transaction_type = ?
               GROUP BY LOWER(description)
               ORDER BY freq DESC
               LIMIT ?''',
            (self.user_id, trans_type, limit)
        ).fetchall()

        return [
            {
                'description': r['description'],
                'frequency':   r['freq'],
                'avg_amount':  round(r['avg_amount'], 2)
            }
            for r in rows
        ]

    def _get_category_breakdown(
        self, month_date: datetime
    ) -> list:
        """
        Previsão detalhada por categoria.
        CORRIGIDO: query sem alias de tabela errado.
        """
        d_from = (
            month_date - timedelta(days=365)
        ).strftime('%Y-%m-%d')

        try:
            rows = self.db.execute(
                '''SELECT
                       c.id               AS cat_id,
                       c.name             AS cat_name,
                       t.transaction_type AS trans_type,
                       AVG(t.amount)      AS avg_amount,
                       COUNT(*)           AS freq
                   FROM transactions t
                   JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ? AND t.date >= ?
                   GROUP BY c.id, t.transaction_type
                   ORDER BY avg_amount DESC
                   LIMIT 10''',
                (self.user_id, d_from)
            ).fetchall()

            return [
                {
                    'category_id':   r['cat_id'],
                    'category_name': r['cat_name'],
                    'trans_type':    r['trans_type'],
                    'predicted_avg': round(r['avg_amount'], 2),
                    'frequency':     r['freq']
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[Forecaster] Erro no breakdown: {e}")
            return []

    def get_predictions_from_db(self) -> list:
        """Retorna previsões pendentes armazenadas pela IA."""
        try:
            predictions = self.db.execute(
                '''SELECT
                       p.*,
                       c.name AS category_name
                   FROM ai_predictions p
                   LEFT JOIN categories c ON p.category_id = c.id
                   WHERE p.user_id = ? AND p.status = 'pendente'
                   ORDER BY p.target_date ASC''',
                (self.user_id,)
            ).fetchall()

            return [dict(p) for p in predictions]
        except Exception as e:
            print(f"[Forecaster] Erro ao buscar previsões: {e}")
            return []

    def get_prediction_accuracy(self) -> dict:
        """Retorna métricas de acurácia das previsões"""
        try:
            validated = self.db.execute(
                '''SELECT
                       COUNT(*)              AS total,
                       SUM(is_correct)       AS correct,
                       AVG(error_percentage) AS avg_error
                   FROM ai_validations
                   WHERE user_id = ?''',
                (self.user_id,)
            ).fetchone()

            by_type = self.db.execute(
                '''SELECT
                       p.prediction_type,
                       COUNT(*)              AS total,
                       SUM(v.is_correct)     AS correct,
                       AVG(v.error_percentage) AS avg_error
                   FROM ai_validations v
                   JOIN ai_predictions p ON v.prediction_id = p.id
                   WHERE v.user_id = ?
                   GROUP BY p.prediction_type''',
                (self.user_id,)
            ).fetchall()

            total    = validated['total']   or 0
            correct  = validated['correct'] or 0
            accuracy = (
                (correct / total * 100) if total > 0 else 0
            )

            by_type_dict = {}
            for row in by_type:
                t        = row['total']   or 0
                c        = row['correct'] or 0
                type_acc = (c / t * 100) if t > 0 else 0
                by_type_dict[row['prediction_type']] = {
                    'total':     t,
                    'correct':   c,
                    'accuracy':  round(type_acc, 1),
                    'avg_error': round(row['avg_error'] or 0, 1)
                }

            return {
                'total':     total,
                'correct':   correct,
                'accuracy':  round(accuracy, 1),
                'avg_error': round(validated['avg_error'] or 0, 1),
                'by_type':   by_type_dict
            }
        except Exception as e:
            print(f"[Forecaster] Erro na acurácia: {e}")
            return {
                'total': 0, 'correct': 0,
                'accuracy': 0, 'avg_error': 0, 'by_type': {}
            }

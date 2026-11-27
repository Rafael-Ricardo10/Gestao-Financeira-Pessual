"""
Motor principal da IA - Online Learning
Aprende continuamente com cada nova transação
Compatível com conversão futura para mobile
"""
import json
import sqlite3
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
from modulos.ai.ai_database import (
    create_ai_tables, get_or_create_model_state,
    update_model_state, add_notification
)


class FinanceAIEngine:
    """
    Motor de IA com Online Learning para finanças pessoais.
    Aprende com cada transação adicionada pelo usuário.
    Faz previsões de entradas e saídas futuras.
    Valida suas próprias previsões automaticamente.
    """

    def __init__(self, db_connection, user_id: int):
        self.db        = db_connection
        self.user_id   = user_id
        self.tolerance = 15.0  # % de tolerância para acerto

        # Garantir tabelas criadas
        create_ai_tables(db_connection)

        # Estado do modelo
        self.state = get_or_create_model_state(db_connection, user_id)

        # Modelos em memória
        self._load_patterns()

    # ══════════════════════════════════════════════════════
    # CARREGAMENTO DE PADRÕES
    # ══════════════════════════════════════════════════════

    def _load_patterns(self):
        """Carrega padrões aprendidos do banco de dados"""
        self.patterns = {
            'category':    {},
            'description': {},
            'weekly':      {},
            'monthly':     {},
            'seasonal':    {}
        }

        try:
            rows = self.db.execute(
                '''SELECT pattern_type, pattern_key, pattern_data
                   FROM ai_patterns WHERE user_id = ?''',
                (self.user_id,)
            ).fetchall()

            for row in rows:
                try:
                    data = json.loads(row['pattern_data'])
                    self.patterns[row['pattern_type']][
                        row['pattern_key']
                    ] = data
                except Exception:
                    pass
        except Exception as e:
            print(f"[AI] Erro ao carregar padrões: {e}")

    def _save_pattern(
        self,
        pattern_type: str,
        pattern_key: str,
        pattern_data: dict
    ):
        """Salva ou atualiza um padrão aprendido"""
        try:
            now       = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data_json = json.dumps(pattern_data)

            existing = self.db.execute(
                '''SELECT id FROM ai_patterns
                   WHERE user_id = ? AND pattern_type = ?
                   AND pattern_key = ?''',
                (self.user_id, pattern_type, pattern_key)
            ).fetchone()

            if existing:
                self.db.execute(
                    '''UPDATE ai_patterns
                       SET pattern_data = ?, confidence = ?,
                           sample_count = ?, last_seen = ?,
                           updated_at = ?
                       WHERE user_id = ? AND pattern_type = ?
                       AND pattern_key = ?''',
                    (
                        data_json,
                        pattern_data.get('confidence', 0),
                        pattern_data.get('count', 0),
                        now, now,
                        self.user_id, pattern_type, pattern_key
                    )
                )
            else:
                self.db.execute(
                    '''INSERT INTO ai_patterns
                       (user_id, pattern_type, pattern_key,
                        pattern_data, confidence, sample_count,
                        last_seen, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        self.user_id, pattern_type, pattern_key,
                        data_json,
                        pattern_data.get('confidence', 0),
                        pattern_data.get('count', 0),
                        now, now, now
                    )
                )
            self.db.commit()
        except Exception as e:
            print(f"[AI] Erro ao salvar padrão: {e}")

    # ══════════════════════════════════════════════════════
    # ONLINE LEARNING
    # ══════════════════════════════════════════════════════

    def learn_from_transaction(self, transaction: dict):
        """
        Aprende com uma nova transação (Online Learning).
        Chamado automaticamente ao adicionar transação.
        """
        try:
            amount      = transaction.get('amount', 0)
            trans_type  = transaction.get('transaction_type', '')
            description = transaction.get('description', '').lower()
            date_str    = transaction.get('date', '')
            category_id = transaction.get('category_id')

            if not date_str or amount <= 0:
                return

            date = datetime.strptime(date_str, '%Y-%m-%d')

            # 1. Aprender padrão por categoria
            if category_id:
                self._learn_category_pattern(
                    category_id, amount, trans_type, date
                )

            # 2. Aprender padrão por descrição
            self._learn_description_pattern(
                description, amount, trans_type, date
            )

            # 3. Aprender padrão semanal
            self._learn_weekly_pattern(
                description, category_id, amount, trans_type, date
            )

            # 4. Aprender padrão mensal
            self._learn_monthly_pattern(
                description, category_id, amount, trans_type, date
            )

            # 5. Atualizar estado do modelo
            seen = self.state.get('total_transactions_seen', 0) + 1
            update_model_state(
                self.db, self.user_id,
                total_transactions_seen=seen,
                last_trained=datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S'
                ),
                health_status=self._calculate_health(seen)
            )
            self.state = get_or_create_model_state(
                self.db, self.user_id
            )

            # 6. Validar previsões pendentes
            self._validate_pending_predictions(transaction)

            # 7. Gerar novas previsões se houver dados suficientes
            if seen >= 7:
                self._generate_predictions_for_transaction(
                    transaction
                )

        except Exception as e:
            print(f"[AI] Erro ao aprender: {e}")

    def _learn_category_pattern(
        self,
        category_id: int,
        amount: float,
        trans_type: str,
        date: datetime
    ):
        """Aprende padrão de uma categoria"""
        key     = f"{category_id}_{trans_type}"
        pattern = self.patterns['category'].get(key, {
            'amounts':    [],
            'days':       [],
            'months':     [],
            'count':      0,
            'mean':       0,
            'std':        0,
            'confidence': 0
        })

        pattern['amounts'].append(amount)
        pattern['days'].append(date.day)
        pattern['months'].append(date.month)
        pattern['count'] += 1

        # Janela deslizante de 50 valores
        if len(pattern['amounts']) > 50:
            pattern['amounts'] = pattern['amounts'][-50:]
            pattern['days']    = pattern['days'][-50:]
            pattern['months']  = pattern['months'][-50:]

        values = pattern['amounts']
        pattern['mean']      = float(np.mean(values))
        pattern['std']       = float(np.std(values)) if len(values) > 1 else 0
        pattern['trans_type'] = trans_type
        pattern['confidence'] = min(
            0.95, 0.3 + (pattern['count'] / 20) * 0.65
        )

        self.patterns['category'][key] = pattern
        self._save_pattern('category', key, pattern)

    def _learn_description_pattern(
        self,
        description: str,
        amount: float,
        trans_type: str,
        date: datetime
    ):
        """Aprende padrão de uma descrição"""
        key     = self._normalize_description(description)
        pattern = self.patterns['description'].get(key, {
            'amounts':    [],
            'days':       [],
            'months':     [],
            'count':      0,
            'mean':       0,
            'std':        0,
            'confidence': 0,
            'trans_type': trans_type
        })

        pattern['amounts'].append(amount)
        pattern['days'].append(date.day)
        pattern['months'].append(date.month)
        pattern['count'] += 1

        if len(pattern['amounts']) > 50:
            pattern['amounts'] = pattern['amounts'][-50:]
            pattern['days']    = pattern['days'][-50:]
            pattern['months']  = pattern['months'][-50:]

        values = pattern['amounts']
        pattern['mean']       = float(np.mean(values))
        pattern['std']        = float(np.std(values)) if len(values) > 1 else 0
        pattern['trans_type'] = trans_type
        pattern['confidence'] = min(
            0.95, 0.3 + (pattern['count'] / 15) * 0.65
        )

        if pattern['days']:
            pattern['typical_day'] = int(np.median(pattern['days']))

        self.patterns['description'][key] = pattern
        self._save_pattern('description', key, pattern)

    def _learn_weekly_pattern(
        self,
        description: str,
        category_id,
        amount: float,
        trans_type: str,
        date: datetime
    ):
        """Aprende padrão semanal"""
        weekday = date.weekday()
        key     = f"{trans_type}_weekday_{weekday}"
        pattern = self.patterns['weekly'].get(key, {
            'amounts': [], 'count': 0,
            'mean': 0, 'confidence': 0
        })

        pattern['amounts'].append(amount)
        pattern['count'] += 1

        if len(pattern['amounts']) > 30:
            pattern['amounts'] = pattern['amounts'][-30:]

        pattern['mean']       = float(np.mean(pattern['amounts']))
        pattern['weekday']    = weekday
        pattern['trans_type'] = trans_type
        pattern['confidence'] = min(0.8, pattern['count'] / 10 * 0.8)

        self.patterns['weekly'][key] = pattern
        self._save_pattern('weekly', key, pattern)

    def _learn_monthly_pattern(
        self,
        description: str,
        category_id,
        amount: float,
        trans_type: str,
        date: datetime
    ):
        """Aprende padrão mensal"""
        month = date.month
        key   = f"{trans_type}_month_{month}"
        pattern = self.patterns['monthly'].get(key, {
            'amounts': [], 'count': 0,
            'mean': 0, 'confidence': 0
        })

        pattern['amounts'].append(amount)
        pattern['count'] += 1

        if len(pattern['amounts']) > 24:
            pattern['amounts'] = pattern['amounts'][-24:]

        pattern['mean']       = float(np.mean(pattern['amounts']))
        pattern['month']      = month
        pattern['trans_type'] = trans_type
        pattern['confidence'] = min(0.85, pattern['count'] / 8 * 0.85)

        self.patterns['monthly'][key] = pattern
        self._save_pattern('monthly', key, pattern)

    # ══════════════════════════════════════════════════════
    # GERAÇÃO DE PREVISÕES INTELIGENTE
    # Só gera se não existir previsão pendente para o período
    # ══════════════════════════════════════════════════════

    def _generate_predictions_for_transaction(
        self, transaction: dict
    ):
        """Gera previsões baseadas na transação atual"""
        try:
            category_id = transaction.get('category_id')
            description = transaction.get(
                'description', ''
            ).lower()
            trans_type  = transaction.get('transaction_type', '')

            if category_id:
                self._predict_next_category(
                    category_id, trans_type
                )

            self._predict_next_description(description, trans_type)

        except Exception as e:
            print(f"[AI] Erro ao gerar previsões: {e}")

    def _predict_next_category(
        self, category_id: int, trans_type: str
    ):
        """
        Prevê próxima ocorrência de uma categoria.
        Só cria se não houver previsão pendente futura.
        """
        key     = f"{category_id}_{trans_type}"
        pattern = self.patterns['category'].get(key)

        if not pattern or pattern['count'] < 3:
            return

        typical_day = int(np.median(pattern.get('days', [15])))
        today       = datetime.now()
        next_month  = today.replace(day=1) + timedelta(days=32)
        next_month  = next_month.replace(day=1)

        try:
            target_date = next_month.replace(day=min(typical_day, 28))
        except ValueError:
            target_date = next_month.replace(day=28)

        # Verificar se já existe previsão pendente futura
        existing = self.db.execute(
            '''SELECT id FROM ai_predictions
               WHERE user_id = ? AND category_id = ?
               AND status = 'pendente'
               AND prediction_type = 'category'
               AND target_date >= ?''',
            (
                self.user_id, category_id,
                today.strftime('%Y-%m-%d')
            )
        ).fetchone()

        if existing:
            return  # Já existe, não duplicar

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.execute(
            '''INSERT INTO ai_predictions
               (user_id, prediction_date, target_date,
                prediction_type, category_id,
                predicted_amount, predicted_type,
                confidence, status, created_at)
               VALUES (?, ?, ?, 'category', ?, ?, ?, ?, 'pendente', ?)''',
            (
                self.user_id,
                today.strftime('%Y-%m-%d'),
                target_date.strftime('%Y-%m-%d'),
                category_id,
                round(pattern['mean'], 2),
                trans_type,
                round(pattern['confidence'], 3),
                now
            )
        )
        self.db.commit()

    def _predict_next_description(
        self, description: str, trans_type: str
    ):
        """
        Prevê próxima ocorrência de uma descrição.
        Só cria se não houver previsão pendente futura.
        """
        key     = self._normalize_description(description)
        pattern = self.patterns['description'].get(key)

        if not pattern or pattern['count'] < 3:
            return

        typical_day = pattern.get('typical_day', 15)
        today       = datetime.now()
        next_month  = today.replace(day=1) + timedelta(days=32)
        next_month  = next_month.replace(day=1)

        try:
            target_date = next_month.replace(day=min(typical_day, 28))
        except ValueError:
            target_date = next_month.replace(day=28)

        # Verificar se já existe previsão pendente futura
        existing = self.db.execute(
            '''SELECT id FROM ai_predictions
               WHERE user_id = ? AND description = ?
               AND status = 'pendente'
               AND prediction_type = 'description'
               AND target_date >= ?''',
            (
                self.user_id, key,
                today.strftime('%Y-%m-%d')
            )
        ).fetchone()

        if existing:
            return  # Já existe, não duplicar

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.execute(
            '''INSERT INTO ai_predictions
               (user_id, prediction_date, target_date,
                prediction_type, description,
                predicted_amount, predicted_type,
                confidence, status, created_at)
               VALUES (?, ?, ?, 'description', ?, ?, ?, ?, 'pendente', ?)''',
            (
                self.user_id,
                today.strftime('%Y-%m-%d'),
                target_date.strftime('%Y-%m-%d'),
                key,
                round(pattern['mean'], 2),
                trans_type,
                round(pattern['confidence'], 3),
                now
            )
        )
        self.db.commit()

    def generate_weekly_predictions(self):
        """
        Gera previsões semanais baseadas nos padrões aprendidos.
        Chamado uma vez após login se houver dados suficientes.
        """
        try:
            seen = self.state.get('total_transactions_seen', 0)
            if seen < 7:
                return  # Precisa de pelo menos 7 transações

            today     = datetime.now()
            week_end  = today + timedelta(days=7)

            for key, pattern in self.patterns['category'].items():
                if pattern['count'] < 3:
                    continue

                cat_id     = int(key.split('_')[0])
                trans_type = key.split('_')[1]

                # Verificar dia típico desta semana
                typical_day = int(
                    np.median(pattern.get('days', [today.day]))
                )

                # Ver se o dia típico cai nesta semana
                for delta in range(8):
                    check_date = today + timedelta(days=delta)
                    if check_date.day == typical_day:
                        target_date = check_date
                        break
                else:
                    continue

                # Não criar duplicata
                existing = self.db.execute(
                    '''SELECT id FROM ai_predictions
                       WHERE user_id = ? AND category_id = ?
                       AND status = 'pendente'
                       AND target_date = ?''',
                    (
                        self.user_id, cat_id,
                        target_date.strftime('%Y-%m-%d')
                    )
                ).fetchone()

                if existing:
                    continue

                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.db.execute(
                    '''INSERT INTO ai_predictions
                       (user_id, prediction_date, target_date,
                        prediction_type, category_id,
                        predicted_amount, predicted_type,
                        confidence, status, created_at)
                       VALUES (?, ?, ?, 'weekly', ?, ?, ?, ?, 'pendente', ?)''',
                    (
                        self.user_id,
                        today.strftime('%Y-%m-%d'),
                        target_date.strftime('%Y-%m-%d'),
                        cat_id,
                        round(pattern['mean'], 2),
                        trans_type,
                        round(pattern['confidence'] * 0.8, 3),
                        now
                    )
                )

            self.db.commit()
            print(f"[AI] Previsões semanais geradas.")

        except Exception as e:
            print(f"[AI] Erro ao gerar previsões semanais: {e}")

    # ══════════════════════════════════════════════════════
    # VALIDAÇÃO DE PREVISÕES
    # ══════════════════════════════════════════════════════

    def _validate_pending_predictions(self, transaction: dict):
        """
        Valida previsões pendentes comparando com
        a transação recém adicionada.
        """
        try:
            amount      = transaction.get('amount', 0)
            trans_type  = transaction.get('transaction_type', '')
            description = transaction.get('description', '').lower()
            category_id = transaction.get('category_id')
            date_str    = transaction.get('date', '')

            if not date_str:
                return

            date   = datetime.strptime(date_str, '%Y-%m-%d')
            d_from = (date - timedelta(days=15)).strftime('%Y-%m-%d')
            d_to   = (date + timedelta(days=15)).strftime('%Y-%m-%d')

            pending = self.db.execute(
                '''SELECT * FROM ai_predictions
                   WHERE user_id = ? AND status = 'pendente'
                   AND predicted_type = ?
                   AND target_date BETWEEN ? AND ?''',
                (self.user_id, trans_type, d_from, d_to)
            ).fetchall()

            for pred in pending:
                matched = False

                if (
                    pred['prediction_type'] in ('category', 'weekly') and
                    category_id and
                    pred['category_id'] == category_id
                ):
                    matched = True
                elif pred['prediction_type'] in (
                    'description', 'monthly'
                ):
                    pred_desc = pred['description'] or ''
                    norm_desc = self._normalize_description(description)
                    if pred_desc == norm_desc:
                        matched = True

                if matched:
                    self._record_validation(
                        pred['id'],
                        pred['predicted_amount'],
                        amount,
                        date_str
                    )

        except Exception as e:
            print(f"[AI] Erro ao validar: {e}")

    def _record_validation(
        self,
        prediction_id: int,
        predicted: float,
        actual: float,
        actual_date: str
    ):
        """Registra resultado da validação"""
        try:
            error_pct = (
                abs(predicted - actual) / actual * 100
                if actual > 0 else 100
            )
            is_correct = 1 if error_pct <= self.tolerance else 0
            now        = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            self.db.execute(
                '''UPDATE ai_predictions
                   SET status = ?, actual_amount = ?,
                       actual_date = ?, error_percentage = ?
                   WHERE id = ?''',
                (
                    'correto' if is_correct else 'incorreto',
                    actual, actual_date,
                    round(error_pct, 2),
                    prediction_id
                )
            )

            self.db.execute(
                '''INSERT INTO ai_validations
                   (prediction_id, user_id, validation_date,
                    predicted_amount, actual_amount,
                    error_percentage, is_correct, tolerance_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    prediction_id, self.user_id, now,
                    predicted, actual,
                    round(error_pct, 2),
                    is_correct, self.tolerance
                )
            )
            self.db.commit()
            self._update_accuracy()

            if is_correct:
                add_notification(
                    self.db, self.user_id,
                    'prediction_correct',
                    'Previsão Confirmada!',
                    f'A IA previu R$ {predicted:.2f} e o valor '
                    f'real foi R$ {actual:.2f} '
                    f'(erro: {error_pct:.1f}%)',
                    priority='low'
                )
        except Exception as e:
            print(f"[AI] Erro ao registrar validação: {e}")

    def _update_accuracy(self):
        """Atualiza as métricas de acurácia"""
        try:
            validations = self.db.execute(
                '''SELECT is_correct FROM ai_validations
                   WHERE user_id = ?''',
                (self.user_id,)
            ).fetchall()

            if not validations:
                return

            total    = len(validations)
            correct  = sum(
                1 for v in validations if v['is_correct'] == 1
            )
            accuracy = correct / total * 100

            update_model_state(
                self.db, self.user_id,
                total_predictions=total,
                correct_predictions=correct,
                accuracy_general=round(accuracy, 2)
            )
            self.state = get_or_create_model_state(
                self.db, self.user_id
            )
        except Exception as e:
            print(f"[AI] Erro ao atualizar acurácia: {e}")

    # ══════════════════════════════════════════════════════
    # PROJEÇÕES FUTURAS
    # ══════════════════════════════════════════════════════

    def get_monthly_forecast(
        self, months_ahead: int = 3
    ) -> list:
        """
        Retorna projeção de entradas e saídas
        para os próximos N meses.
        """
        try:
            forecasts = []
            today     = datetime.now()

            for i in range(1, months_ahead + 1):
                month_date = today.replace(day=1) + timedelta(
                    days=32 * i
                )
                month_date = month_date.replace(day=1)

                month_income  = self._forecast_month(
                    month_date, 'entrada'
                )
                month_expense = self._forecast_month(
                    month_date, 'saida'
                )

                forecasts.append({
                    'month':          month_date.strftime('%Y-%m'),
                    'month_label':    month_date.strftime('%B %Y'),
                    'income':         month_income['total'],
                    'expense':        month_expense['total'],
                    'balance':        month_income['total'] - month_expense['total'],
                    'income_conf':    month_income['confidence'],
                    'expense_conf':   month_expense['confidence'],
                    'income_detail':  month_income['details'],
                    'expense_detail': month_expense['details']
                })

            return forecasts

        except Exception as e:
            print(f"[AI] Erro na projeção: {e}")
            return []

    def _forecast_month(
        self, month_date: datetime, trans_type: str
    ) -> dict:
        """Projeta total de entradas ou saídas para um mês"""
        total      = 0
        confidence = 0
        details    = []
        count      = 0

        for key, pattern in self.patterns['category'].items():
            if not key.endswith(f'_{trans_type}'):
                continue
            if pattern['count'] < 2:
                continue

            month_key     = f"{trans_type}_month_{month_date.month}"
            month_pattern = self.patterns['monthly'].get(month_key)

            amount = pattern['mean']
            if month_pattern and month_pattern['count'] >= 2:
                all_monthly_means = [
                    p['mean']
                    for p in self.patterns['monthly'].values()
                    if p.get('trans_type') == trans_type
                    and p['count'] >= 2
                ]
                if all_monthly_means:
                    seasonal_factor = (
                        month_pattern['mean'] /
                        np.mean(all_monthly_means)
                    )
                    amount *= seasonal_factor

            cat_id = key.split('_')[0]
            try:
                cat = self.db.execute(
                    'SELECT name FROM categories WHERE id = ?',
                    (int(cat_id),)
                ).fetchone()
                cat_name = cat['name'] if cat else f'Cat {cat_id}'
            except Exception:
                cat_name = f'Cat {cat_id}'

            total      += amount
            confidence += pattern['confidence']
            count      += 1

            details.append({
                'name':       cat_name,
                'amount':     round(amount, 2),
                'confidence': round(pattern['confidence'], 2)
            })

        avg_confidence = (confidence / count) if count > 0 else 0

        return {
            'total':      round(total, 2),
            'confidence': round(avg_confidence, 3),
            'details':    details
        }

    # ══════════════════════════════════════════════════════
    # ANÁLISE DE TENDÊNCIAS
    # ══════════════════════════════════════════════════════

    def get_trend_analysis(
        self,
        category_id: int = None,
        description: str = None,
        months: int = 6
    ) -> dict:
        """Analisa tendência de gastos/receitas."""
        try:
            today  = datetime.now()
            d_from = (
                today - timedelta(days=30 * months)
            ).strftime('%Y-%m-%d')

            query  = '''
                SELECT strftime('%Y-%m', date) as month,
                       SUM(amount) as total,
                       COUNT(*) as count,
                       transaction_type
                FROM transactions
                WHERE user_id = ? AND date >= ?
            '''
            params = [self.user_id, d_from]

            if category_id:
                query  += ' AND category_id = ?'
                params.append(category_id)

            if description:
                query  += ' AND LOWER(description) LIKE ?'
                params.append(f'%{description.lower()}%')

            query += (
                ' GROUP BY month, transaction_type'
                ' ORDER BY month'
            )

            rows = self.db.execute(query, params).fetchall()

            if not rows:
                return {'has_data': False}

            income_by_month  = {}
            expense_by_month = {}

            for row in rows:
                month = row['month']
                if row['transaction_type'] == 'entrada':
                    income_by_month[month] = row['total']
                else:
                    expense_by_month[month] = row['total']

            income_trend  = self._calculate_trend_slope(
                list(income_by_month.values())
            )
            expense_trend = self._calculate_trend_slope(
                list(expense_by_month.values())
            )

            avg_income  = (
                np.mean(list(income_by_month.values()))
                if income_by_month else 0
            )
            avg_expense = (
                np.mean(list(expense_by_month.values()))
                if expense_by_month else 0
            )

            income_values  = list(income_by_month.values())
            expense_values = list(expense_by_month.values())

            income_variation = (
                ((income_values[-1] - income_values[-2]) /
                 income_values[-2] * 100)
                if len(income_values) >= 2 and income_values[-2] > 0
                else 0
            )
            expense_variation = (
                ((expense_values[-1] - expense_values[-2]) /
                 expense_values[-2] * 100)
                if len(expense_values) >= 2 and expense_values[-2] > 0
                else 0
            )

            return {
                'has_data':          True,
                'months':            sorted(
                    set(
                        list(income_by_month.keys()) +
                        list(expense_by_month.keys())
                    )
                ),
                'income_by_month':   income_by_month,
                'expense_by_month':  expense_by_month,
                'income_trend':      income_trend,
                'expense_trend':     expense_trend,
                'avg_income':        round(avg_income, 2),
                'avg_expense':       round(avg_expense, 2),
                'income_variation':  round(income_variation, 2),
                'expense_variation': round(expense_variation, 2),
                'income_direction':  self._trend_direction(
                    income_trend
                ),
                'expense_direction': self._trend_direction(
                    expense_trend
                ),
                'balance_trend':     income_trend - expense_trend,
            }

        except Exception as e:
            print(f"[AI] Erro na análise de tendências: {e}")
            return {'has_data': False}

    def _calculate_trend_slope(self, values: list) -> float:
        """Calcula inclinação da tendência"""
        if len(values) < 2:
            return 0
        x = np.arange(len(values))
        y = np.array(values)
        if np.all(y == 0):
            return 0
        try:
            slope, _ = np.polyfit(x, y, 1)
            avg      = np.mean(y)
            return float(slope / avg) if avg != 0 else 0
        except Exception:
            return 0

    def _trend_direction(self, slope: float) -> str:
        """Converte slope em direção textual"""
        if slope > 0.05:
            return 'subindo'
        elif slope < -0.05:
            return 'caindo'
        return 'estavel'

    # ══════════════════════════════════════════════════════
    # SCORE FINANCEIRO
    # ══════════════════════════════════════════════════════

    def get_financial_score(self) -> dict:
        """Calcula score de saúde financeira (0-1000)"""
        try:
            transactions = self.db.execute(
                '''SELECT * FROM transactions
                   WHERE user_id = ?
                   ORDER BY date DESC''',
                (self.user_id,)
            ).fetchall()

            if not transactions:
                return {
                    'score':          0,
                    'classification': 'Sem dados',
                    'details':        {},
                    'suggestions':    [
                        'Adicione suas transações para começar!'
                    ]
                }

            total_income  = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )
            total_expense = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'saida'
            )
            balance = total_income - total_expense

            savings_rate  = (
                (balance / total_income * 100)
                if total_income > 0 else 0
            )
            savings_score = min(250, max(0, savings_rate * 5))

            monthly_income = self._get_monthly_values('entrada')
            income_consistency = (
                self._calculate_consistency(monthly_income) * 200
            )

            monthly_expense = self._get_monthly_values('saida')
            expense_control = (
                self._calculate_expense_control(
                    monthly_income, monthly_expense
                ) * 200
            )

            cat_count = self.db.execute(
                'SELECT COUNT(*) FROM categories WHERE user_id = ?',
                (self.user_id,)
            ).fetchone()[0]
            category_score = min(150, cat_count * 20)

            ai_accuracy = self.state.get('accuracy_general', 0)
            ai_score    = ai_accuracy * 1.0

            trend_analysis = self.get_trend_analysis(months=3)
            trend_score    = 0
            if trend_analysis.get('has_data'):
                if trend_analysis['income_direction'] == 'subindo':
                    trend_score += 50
                if trend_analysis['expense_direction'] == 'caindo':
                    trend_score += 50

            total_score = int(min(1000, (
                savings_score + income_consistency +
                expense_control + category_score +
                ai_score + trend_score
            )))

            classification = self._score_classification(total_score)
            suggestions    = self._generate_suggestions(
                savings_rate, income_consistency,
                expense_control, trend_analysis
            )

            return {
                'score':          total_score,
                'classification': classification,
                'details': {
                    'savings_score':      int(savings_score),
                    'income_consistency': int(income_consistency),
                    'expense_control':    int(expense_control),
                    'category_score':     int(category_score),
                    'ai_score':           int(ai_score),
                    'trend_score':        int(trend_score),
                    'savings_rate':       round(savings_rate, 1),
                    'balance':            round(balance, 2)
                },
                'suggestions': suggestions
            }

        except Exception as e:
            print(f"[AI] Erro no score: {e}")
            return {
                'score': 0, 'classification': 'Erro',
                'details': {}, 'suggestions': []
            }

    def _get_monthly_values(self, trans_type: str) -> list:
        """Retorna totais mensais de um tipo de transação"""
        rows = self.db.execute(
            '''SELECT SUM(amount) as total
               FROM transactions
               WHERE user_id = ? AND transaction_type = ?
               GROUP BY strftime('%Y-%m', date)
               ORDER BY strftime('%Y-%m', date)''',
            (self.user_id, trans_type)
        ).fetchall()
        return [r['total'] for r in rows if r['total']]

    def _calculate_consistency(self, values: list) -> float:
        """Calcula consistência (0-1) de uma série"""
        if len(values) < 2:
            return 0.5
        mean = np.mean(values)
        if mean == 0:
            return 0
        cv = np.std(values) / mean
        return max(0, min(1, 1 - cv))

    def _calculate_expense_control(
        self, income: list, expense: list
    ) -> float:
        """Calcula controle de gastos (0-1)"""
        if not income or not expense:
            return 0.5
        min_len = min(len(income), len(expense))
        if min_len == 0:
            return 0.5
        ratios = [
            expense[i] / income[i]
            for i in range(min_len)
            if income[i] > 0
        ]
        if not ratios:
            return 0.5
        avg_ratio = np.mean(ratios)
        return max(0, min(1, 1 - (avg_ratio - 0.5)))

    def _score_classification(self, score: int) -> str:
        """Classifica o score financeiro"""
        if score >= 850:
            return 'Excelente'
        elif score >= 700:
            return 'Otimo'
        elif score >= 550:
            return 'Bom'
        elif score >= 400:
            return 'Regular'
        elif score >= 250:
            return 'Ruim'
        return 'Critico'

    def _generate_suggestions(
        self,
        savings_rate: float,
        income_consistency: float,
        expense_control: float,
        trend: dict
    ) -> list:
        """Gera sugestões personalizadas"""
        suggestions = []

        if savings_rate < 10:
            suggestions.append(
                'Tente poupar ao menos 10% da sua renda mensal'
            )
        if savings_rate < 0:
            suggestions.append(
                'Suas despesas estao maiores que suas receitas!'
            )
        if income_consistency < 0.5:
            suggestions.append(
                'Sua receita e muito variavel - '
                'considere uma reserva de emergencia'
            )
        if expense_control < 0.5:
            suggestions.append(
                'Seus gastos estao altos em relacao a sua receita'
            )
        if trend.get('has_data'):
            if trend.get('expense_direction') == 'subindo':
                suggestions.append(
                    'Atencao: seus gastos estao aumentando '
                    'nos ultimos meses'
                )
            if trend.get('income_direction') == 'caindo':
                suggestions.append(
                    'Atencao: sua receita esta diminuindo '
                    'nos ultimos meses'
                )

        if not suggestions:
            suggestions.append(
                'Continue assim! Suas financas estao saudaveis!'
            )

        return suggestions

    # ══════════════════════════════════════════════════════
    # UTILITÁRIOS
    # ══════════════════════════════════════════════════════

    def _normalize_description(self, description: str) -> str:
        """Normaliza descrição removendo números variáveis."""
        import re
        desc = description.lower().strip()
        desc = re.sub(r'\d+', '', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()
        return desc[:100]

    def _calculate_health(self, transactions_seen: int) -> str:
        """Calcula saúde do modelo"""
        if transactions_seen < 5:
            return 'iniciando'
        elif transactions_seen < 20:
            return 'aprendendo'
        elif transactions_seen < 50:
            return 'desenvolvendo'
        elif transactions_seen < 100:
            return 'treinado'
        return 'maduro'

    def get_model_status(self) -> dict:
        """Retorna status completo do modelo"""
        try:
            self.state = get_or_create_model_state(
                self.db, self.user_id
            )

            total_pred = self.db.execute(
                '''SELECT COUNT(*) FROM ai_predictions
                   WHERE user_id = ?''',
                (self.user_id,)
            ).fetchone()[0]

            pending_pred = self.db.execute(
                '''SELECT COUNT(*) FROM ai_predictions
                   WHERE user_id = ? AND status = 'pendente' ''',
                (self.user_id,)
            ).fetchone()[0]

            correct_pred = self.db.execute(
                '''SELECT COUNT(*) FROM ai_predictions
                   WHERE user_id = ? AND status = 'correto' ''',
                (self.user_id,)
            ).fetchone()[0]

            wrong_pred = self.db.execute(
                '''SELECT COUNT(*) FROM ai_predictions
                   WHERE user_id = ? AND status = 'incorreto' ''',
                (self.user_id,)
            ).fetchone()[0]

            patterns_count = (
                len(self.patterns['category']) +
                len(self.patterns['description'])
            )

            return {
                'health':              self.state.get(
                    'health_status', 'iniciando'
                ),
                'transactions_seen':   self.state.get(
                    'total_transactions_seen', 0
                ),
                'accuracy_general':    self.state.get(
                    'accuracy_general', 0
                ),
                'last_trained':        self.state.get(
                    'last_trained', 'Nunca'
                ),
                'total_predictions':   total_pred,
                'pending_predictions': pending_pred,
                'correct_predictions': correct_pred,
                'wrong_predictions':   wrong_pred,
                'patterns_learned':    patterns_count,
            }
        except Exception as e:
            print(f"[AI] Erro no status: {e}")
            return {
                'health': 'erro',
                'transactions_seen': 0,
                'accuracy_general': 0,
                'last_trained': 'Nunca',
                'total_predictions': 0,
                'pending_predictions': 0,
                'correct_predictions': 0,
                'wrong_predictions': 0,
                'patterns_learned': 0,
            }

    def train_on_existing_data(self):
        """
        Treina com todos os dados existentes do usuário.
        CORRIGIDO: Cria conexão própria para rodar em thread.
        """
        try:
            import os
            # Buscar caminho do banco pelo user_id
            db_path = None
            dados_dir = 'dados'
            if os.path.exists(dados_dir):
                for fname in os.listdir(dados_dir):
                    if fname.endswith('.db'):
                        test_conn = sqlite3.connect(
                            os.path.join(dados_dir, fname)
                        )
                        test_conn.row_factory = sqlite3.Row
                        try:
                            user = test_conn.execute(
                                'SELECT id FROM users WHERE id = ?',
                                (self.user_id,)
                            ).fetchone()
                            if user:
                                db_path = os.path.join(
                                    dados_dir, fname
                                )
                                test_conn.close()
                                break
                        except Exception:
                            pass
                        test_conn.close()

            if not db_path:
                print("[AI] Banco não encontrado para treinamento.")
                return

            # Conexão própria da thread
            thread_conn = sqlite3.connect(db_path)
            thread_conn.row_factory = sqlite3.Row

            transactions = thread_conn.execute(
                '''SELECT * FROM transactions
                   WHERE user_id = ?
                   ORDER BY date ASC''',
                (self.user_id,)
            ).fetchall()

            thread_conn.close()

            # Usar a conexão principal apenas para salvar padrões
            for transaction in transactions:
                self._learn_from_dict(dict(transaction))

            print(
                f"[AI] Treinamento inicial: "
                f"{len(transactions)} transações processadas"
            )

        except Exception as e:
            print(f"[AI] Erro no treinamento inicial: {e}")
            import traceback
            traceback.print_exc()

    def _learn_from_dict(self, transaction: dict):
        """
        Versão do learn_from_transaction que não acessa
        o banco de dados (para uso em threads).
        Apenas atualiza os padrões em memória.
        """
        try:
            amount      = transaction.get('amount', 0)
            trans_type  = transaction.get('transaction_type', '')
            description = transaction.get('description', '').lower()
            date_str    = transaction.get('date', '')
            category_id = transaction.get('category_id')

            if not date_str or amount <= 0:
                return

            date = datetime.strptime(date_str, '%Y-%m-%d')

            # Aprender padrões apenas em memória
            if category_id:
                key     = f"{category_id}_{trans_type}"
                pattern = self.patterns['category'].get(key, {
                    'amounts': [], 'days': [], 'months': [],
                    'count': 0, 'mean': 0, 'std': 0,
                    'confidence': 0
                })
                pattern['amounts'].append(amount)
                pattern['days'].append(date.day)
                pattern['months'].append(date.month)
                pattern['count'] += 1
                if len(pattern['amounts']) > 50:
                    pattern['amounts'] = pattern['amounts'][-50:]
                    pattern['days']    = pattern['days'][-50:]
                    pattern['months']  = pattern['months'][-50:]
                values = pattern['amounts']
                pattern['mean']      = float(np.mean(values))
                pattern['std']       = (
                    float(np.std(values)) if len(values) > 1 else 0
                )
                pattern['trans_type'] = trans_type
                pattern['confidence'] = min(
                    0.95, 0.3 + (pattern['count'] / 20) * 0.65
                )
                self.patterns['category'][key] = pattern

            # Descrição
            key     = self._normalize_description(description)
            pattern = self.patterns['description'].get(key, {
                'amounts': [], 'days': [], 'months': [],
                'count': 0, 'mean': 0, 'std': 0,
                'confidence': 0, 'trans_type': trans_type
            })
            pattern['amounts'].append(amount)
            pattern['days'].append(date.day)
            pattern['months'].append(date.month)
            pattern['count'] += 1
            if len(pattern['amounts']) > 50:
                pattern['amounts'] = pattern['amounts'][-50:]
                pattern['days']    = pattern['days'][-50:]
                pattern['months']  = pattern['months'][-50:]
            values = pattern['amounts']
            pattern['mean']       = float(np.mean(values))
            pattern['std']        = (
                float(np.std(values)) if len(values) > 1 else 0
            )
            pattern['trans_type'] = trans_type
            pattern['confidence'] = min(
                0.95, 0.3 + (pattern['count'] / 15) * 0.65
            )
            if pattern['days']:
                pattern['typical_day'] = int(
                    np.median(pattern['days'])
                )
            self.patterns['description'][key] = pattern

        except Exception as e:
            print(f"[AI] Erro no _learn_from_dict: {e}")

    def save_patterns_after_training(self):
        """
        Salva todos os padrões aprendidos no banco.
        CORRIGIDO: Conta transações corretamente.
        """
        try:
            # Salvar padrões de categoria
            for key, pattern in self.patterns['category'].items():
                self._save_pattern('category', key, pattern)

            # Salvar padrões de descrição
            for key, pattern in self.patterns['description'].items():
                self._save_pattern('description', key, pattern)

            # Salvar padrões semanais
            for key, pattern in self.patterns['weekly'].items():
                self._save_pattern('weekly', key, pattern)

            # Salvar padrões mensais
            for key, pattern in self.patterns['monthly'].items():
                self._save_pattern('monthly', key, pattern)

            # Contar total real de transações no banco
            total_seen = self.db.execute(
                'SELECT COUNT(*) FROM transactions WHERE user_id = ?',
                (self.user_id,)
            ).fetchone()[0]

            # Atualizar estado do modelo
            update_model_state(
                self.db, self.user_id,
                total_transactions_seen=total_seen,
                last_trained=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                health_status=self._calculate_health(total_seen)
            )

            self.state = get_or_create_model_state(self.db, self.user_id)

            print(
                f"[AI] Padrões salvos! "
                f"Total vistas: {total_seen} | "
                f"Categorias: {len(self.patterns['category'])} | "
                f"Descrições: {len(self.patterns['description'])}"
            )

        except Exception as e:
            print(f"[AI] Erro ao salvar padrões: {e}")
            import traceback
            traceback.print_exc()

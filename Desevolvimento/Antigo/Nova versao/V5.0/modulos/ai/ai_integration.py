"""
Integração da IA com o sistema principal.
Helper para conectar a IA com todas as operações.
"""
from datetime import datetime


class AIIntegration:
    """
    Classe auxiliar que conecta a IA com as
    operações do sistema principal.
    """

    def __init__(self, db_connection, user_id: int):
        self.db      = db_connection
        self.user_id = user_id
        self.engine  = None
        self._init_engine()

    def _init_engine(self):
        """Inicializa o motor da IA"""
        try:
            from modulos.ai.ai_database import create_ai_tables
            from modulos.ai.ai_engine   import FinanceAIEngine
            create_ai_tables(self.db)
            self.engine = FinanceAIEngine(self.db, self.user_id)
        except Exception as e:
            print(f'[AIIntegration] Erro ao inicializar: {e}')

    def on_transaction_added(self, transaction_id: int):
        """
        Chamado sempre que uma transação é adicionada.
        A IA aprende com o novo dado.
        """
        if not self.engine:
            return
        try:
            trans = self.db.execute(
                'SELECT * FROM transactions WHERE id = ?',
                (transaction_id,)
            ).fetchone()
            if trans:
                self.engine.learn_from_transaction(dict(trans))
        except Exception as e:
            print(f'[AIIntegration] Erro ao processar transação: {e}')

    def on_transactions_imported(self, transaction_ids: list):
        """
        Chamado após importação de extrato PDF.
        A IA aprende com todas as transações importadas.
        """
        if not self.engine:
            return
        try:
            for tid in transaction_ids:
                self.on_transaction_added(tid)
        except Exception as e:
            print(f'[AIIntegration] Erro na importação: {e}')

    def get_unread_count(self) -> int:
        """Retorna quantidade de notificações não lidas"""
        if not self.engine:
            return 0
        try:
            from modulos.ai import get_unread_notifications
            notifs = get_unread_notifications(self.db, self.user_id)
            return len(notifs)
        except Exception:
            return 0

    def get_quick_insights(self) -> list:
        """
        Retorna insights rápidos para mostrar no dashboard.
        Máximo de 3 insights mais importantes.
        """
        if not self.engine:
            return []
        try:
            from modulos.ai.trend_analyzer import TrendAnalyzer
            analyzer = TrendAnalyzer(
                self.db, self.user_id, self.engine
            )
            result   = analyzer.analyze(months=3)
            if not result.get('has_data'):
                return []
            insights = result.get('insights', [])
            # Priorizar warnings e críticos
            priority = ['critical', 'warning', 'attention',
                       'positive', 'info']
            sorted_insights = sorted(
                insights,
                key=lambda x: priority.index(x.get('type', 'info'))
                if x.get('type') in priority else len(priority)
            )
            return sorted_insights[:3]
        except Exception as e:
            print(f'[AIIntegration] Erro nos insights: {e}')
            return []

    def get_score(self) -> dict:
        """Retorna score financeiro atual"""
        if not self.engine:
            return {'score': 0, 'classification': '---'}
        try:
            return self.engine.get_financial_score()
        except Exception:
            return {'score': 0, 'classification': '---'}

"""
Módulo de IA para o Sistema de Gestão Financeira
Online Learning - aprende com cada transação
"""
from modulos.ai.ai_engine   import FinanceAIEngine
from modulos.ai.trend_analyzer import TrendAnalyzer
from modulos.ai.forecaster  import FinanceForecaster
from modulos.ai.ai_database import (
    create_ai_tables,
    get_or_create_model_state,
    update_model_state,
    add_notification,
    get_unread_notifications,
    mark_notification_read
)

__all__ = [
    'FinanceAIEngine',
    'TrendAnalyzer',
    'FinanceForecaster',
    'create_ai_tables',
    'get_or_create_model_state',
    'update_model_state',
    'add_notification',
    'get_unread_notifications',
    'mark_notification_read',
]

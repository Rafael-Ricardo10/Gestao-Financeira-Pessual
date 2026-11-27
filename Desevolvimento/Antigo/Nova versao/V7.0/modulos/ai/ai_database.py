"""
Gerenciamento do banco de dados da IA
Tabelas para previsões, validações e estado do modelo
"""
import sqlite3
import os
from datetime import datetime


def create_ai_tables(db_connection):
    """Cria todas as tabelas necessárias para a IA"""

    # ── Previsões feitas pela IA ──────────────────────────
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS ai_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prediction_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            prediction_type TEXT NOT NULL,
            category_id INTEGER,
            description TEXT,
            predicted_amount REAL NOT NULL,
            predicted_type TEXT NOT NULL,
            confidence REAL DEFAULT 0,
            status TEXT DEFAULT 'pendente',
            actual_amount REAL,
            actual_date TEXT,
            error_percentage REAL,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    # ── Validações das previsões ──────────────────────────
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS ai_validations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            validation_date TEXT NOT NULL,
            predicted_amount REAL NOT NULL,
            actual_amount REAL NOT NULL,
            error_percentage REAL NOT NULL,
            is_correct INTEGER DEFAULT 0,
            tolerance_used REAL DEFAULT 15.0,
            FOREIGN KEY (prediction_id) REFERENCES ai_predictions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # ── Estado do modelo por usuário ──────────────────────
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS ai_model_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            total_predictions INTEGER DEFAULT 0,
            correct_predictions INTEGER DEFAULT 0,
            accuracy_general REAL DEFAULT 0,
            accuracy_by_category TEXT DEFAULT '{}',
            accuracy_by_description TEXT DEFAULT '{}',
            last_trained TEXT,
            last_prediction TEXT,
            model_version INTEGER DEFAULT 1,
            total_transactions_seen INTEGER DEFAULT 0,
            health_status TEXT DEFAULT 'iniciando',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # ── Log de acurácia histórica ─────────────────────────
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS ai_accuracy_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            accuracy_general REAL DEFAULT 0,
            accuracy_category REAL DEFAULT 0,
            accuracy_description REAL DEFAULT 0,
            accuracy_amount REAL DEFAULT 0,
            total_predictions INTEGER DEFAULT 0,
            correct_predictions INTEGER DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # ── Padrões aprendidos pela IA ────────────────────────
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS ai_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            pattern_data TEXT NOT NULL,
            confidence REAL DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            last_seen TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, pattern_type, pattern_key)
        )
    ''')

    # ── Notificações da IA ────────────────────────────────
    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS ai_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            priority TEXT DEFAULT 'normal',
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            read_at TEXT,
            data TEXT DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    db_connection.commit()


def get_or_create_model_state(db_connection, user_id: int) -> dict:
    """Retorna ou cria o estado do modelo para o usuário"""
    state = db_connection.execute(
        'SELECT * FROM ai_model_state WHERE user_id = ?',
        (user_id,)
    ).fetchone()

    if not state:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db_connection.execute(
            '''INSERT INTO ai_model_state
               (user_id, created_at, updated_at)
               VALUES (?, ?, ?)''',
            (user_id, now, now)
        )
        db_connection.commit()

        state = db_connection.execute(
            'SELECT * FROM ai_model_state WHERE user_id = ?',
            (user_id,)
        ).fetchone()

    return dict(state)


def update_model_state(db_connection, user_id: int, **kwargs):
    """Atualiza o estado do modelo"""
    kwargs['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    set_clause = ', '.join(f'{k} = ?' for k in kwargs.keys())
    values     = list(kwargs.values()) + [user_id]

    db_connection.execute(
        f'UPDATE ai_model_state SET {set_clause} WHERE user_id = ?',
        values
    )
    db_connection.commit()


def add_notification(
    db_connection,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    priority: str = 'normal',
    data: str = '{}'
):
    """Adiciona uma notificação da IA"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db_connection.execute(
        '''INSERT INTO ai_notifications
           (user_id, notification_type, title,
            message, priority, created_at, data)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (user_id, notification_type, title,
         message, priority, now, data)
    )
    db_connection.commit()


def get_unread_notifications(db_connection, user_id: int) -> list:
    """Retorna notificações não lidas"""
    return db_connection.execute(
        '''SELECT * FROM ai_notifications
           WHERE user_id = ? AND is_read = 0
           ORDER BY created_at DESC''',
        (user_id,)
    ).fetchall()


def mark_notification_read(db_connection, notification_id: int):
    """Marca notificação como lida"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db_connection.execute(
        '''UPDATE ai_notifications
           SET is_read = 1, read_at = ?
           WHERE id = ?''',
        (now, notification_id)
    )
    db_connection.commit()

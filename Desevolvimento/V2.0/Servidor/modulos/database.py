"""
Gerenciamento do banco de dados e migrações
"""
import os
import shutil
from modulos import bd_seguro
from datetime import datetime

DB_VERSION = 5

class DBManager:
    """Gerencia conexão e criação do banco de dados"""

    def __init__(self, username: str, chave_hex: str = None):
        self.username = username
        self.chave_hex = chave_hex
        self.db_path = os.path.join('dados', f'{username}.db')
        self.connection = None

    def connect(self):
        """Abre conexão com o banco de dados"""
        self.connection = bd_seguro.conectar(self.db_path, self.chave_hex)
        return self.connection

    def close(self):
        """Fecha conexão com o banco de dados"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def create_tables(self):
        """Cria todas as tabelas necessárias"""
        conn = self.connection

        conn.execute('''CREATE TABLE IF NOT EXISTS users
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             username TEXT UNIQUE NOT NULL,
             password TEXT NOT NULL)''')

        conn.execute('''CREATE TABLE IF NOT EXISTS transactions
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             amount REAL NOT NULL,
             description TEXT NOT NULL,
             transaction_type TEXT NOT NULL,
             date TEXT NOT NULL,
             category_id INTEGER,
             savings_category_id INTEGER,
             is_saving_transaction INTEGER DEFAULT 0,
             FOREIGN KEY (user_id) REFERENCES users (id),
             FOREIGN KEY (category_id) REFERENCES categories (id))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS notes
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             note TEXT NOT NULL,
             FOREIGN KEY (user_id) REFERENCES users (id))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS categories
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             name TEXT NOT NULL,
             total_amount REAL DEFAULT 0,
             is_payment_goal INTEGER DEFAULT 0,
             is_savings_goal INTEGER DEFAULT 0,
             is_hidden INTEGER DEFAULT 0,
             year INTEGER,
             FOREIGN KEY (user_id) REFERENCES users (id))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS category_budgets
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             category_id INTEGER NOT NULL,
             month INTEGER NOT NULL,
             year INTEGER NOT NULL,
             amount REAL NOT NULL,
             FOREIGN KEY (user_id) REFERENCES users (id),
             FOREIGN KEY (category_id) REFERENCES categories (id),
             UNIQUE(user_id, category_id, month, year))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS savings_goals
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             name TEXT NOT NULL,
             target_amount REAL NOT NULL,
             current_amount REAL DEFAULT 0,
             start_date TEXT NOT NULL,
             deadline TEXT,
             category_id INTEGER,
             notes TEXT,
             FOREIGN KEY (user_id) REFERENCES users (id),
             FOREIGN KEY (category_id) REFERENCES categories (id))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS user_settings
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             setting_key TEXT NOT NULL,
             setting_value TEXT,
             FOREIGN KEY (user_id) REFERENCES users (id),
             UNIQUE(user_id, setting_key))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS category_rules
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             category_id INTEGER NOT NULL,
             rule_text TEXT NOT NULL,
             match_type TEXT DEFAULT 'contains',
             FOREIGN KEY (user_id) REFERENCES users (id),
             FOREIGN KEY (category_id) REFERENCES categories (id),
             UNIQUE(user_id, category_id, rule_text))''')

        # ── NOVO: Tabelas de Empréstimos ────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS loans
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER NOT NULL,
             name TEXT NOT NULL,
             description TEXT,
             reason TEXT,
             total_amount REAL NOT NULL,
             interest_rate REAL DEFAULT 0,
             num_installments INTEGER NOT NULL,
             discount REAL DEFAULT 0,
             final_amount REAL NOT NULL,
             installment_amount REAL NOT NULL,
             start_date TEXT NOT NULL,
             status TEXT DEFAULT 'ativo',
             transaction_id INTEGER,
             category_id INTEGER,
             FOREIGN KEY (user_id) REFERENCES users (id),
             FOREIGN KEY (transaction_id) REFERENCES transactions (id),
             FOREIGN KEY (category_id) REFERENCES categories (id))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS loan_payments
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             loan_id INTEGER NOT NULL,
             transaction_id INTEGER,
             payment_date TEXT NOT NULL,
             amount REAL NOT NULL,
             installment_number INTEGER NOT NULL,
             notes TEXT,
             FOREIGN KEY (loan_id) REFERENCES loans (id),
             FOREIGN KEY (transaction_id) REFERENCES transactions (id))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS db_version
            (version INTEGER)''')

        conn.commit()


class DBUpdater:
    """Responsável por atualizar o esquema do banco de dados"""

    @staticmethod
    def check_and_update(db_connection, username):
        """Verifica a versão e atualiza se necessário"""
        cursor = db_connection.cursor()

        # Verificar/criar tabela de versão
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'"
        )
        if not cursor.fetchone():
            cursor.execute('CREATE TABLE db_version (version INTEGER)')
            cursor.execute('INSERT INTO db_version VALUES (1)')
            db_connection.commit()
            current_version = 1
        else:
            version_record = cursor.execute(
                'SELECT version FROM db_version'
            ).fetchone()
            if version_record is None:
                cursor.execute('INSERT INTO db_version VALUES (1)')
                db_connection.commit()
                current_version = 1
            else:
                current_version = version_record[0]

        if current_version < DB_VERSION:
            print(f"Atualizando BD de v{current_version} para v{DB_VERSION}")
            DBUpdater._run_migrations(db_connection, username, current_version)

        return True

    @staticmethod
    def _run_migrations(db_connection, username, current_version):
        """Executa as migrações necessárias"""
        try:
            db_path = os.path.join('dados', f'{username}.db')
            backup_path = os.path.join(
                'dados', f'{username}_backup_v{current_version}.db'
            )
            shutil.copy2(db_path, backup_path)

            migrations = [
                ('categories', 'total_amount', 'REAL DEFAULT 0'),
                ('categories', 'is_payment_goal', 'INTEGER DEFAULT 0'),
                ('categories', 'is_savings_goal', 'INTEGER DEFAULT 0'),
                ('categories', 'is_hidden', 'INTEGER DEFAULT 0'),
                ('transactions', 'savings_category_id', 'INTEGER'),
                ('transactions', 'is_saving_transaction', 'INTEGER DEFAULT 0'),
            ]

            for table, column, col_type in migrations:
                DBUpdater._add_column_if_not_exists(
                    db_connection, table, column, col_type
                )

            # Coluna year com valor dinâmico
            current_year = datetime.now().year
            DBUpdater._add_column_if_not_exists(
                db_connection, 'categories', 'year',
                f'INTEGER DEFAULT {current_year}'
            )

            # Criar tabelas novas se não existirem
            db_connection.execute('''CREATE TABLE IF NOT EXISTS category_budgets
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 category_id INTEGER NOT NULL,
                 month INTEGER NOT NULL,
                 year INTEGER NOT NULL,
                 amount REAL NOT NULL,
                 FOREIGN KEY (user_id) REFERENCES users (id),
                 FOREIGN KEY (category_id) REFERENCES categories (id),
                 UNIQUE(user_id, category_id, month, year))''')

            db_connection.execute('''CREATE TABLE IF NOT EXISTS savings_goals
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 name TEXT NOT NULL,
                 target_amount REAL NOT NULL,
                 current_amount REAL DEFAULT 0,
                 start_date TEXT NOT NULL,
                 deadline TEXT,
                 category_id INTEGER,
                 notes TEXT,
                 FOREIGN KEY (user_id) REFERENCES users (id),
                 FOREIGN KEY (category_id) REFERENCES categories (id))''')

            db_connection.execute('''CREATE TABLE IF NOT EXISTS user_settings
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 setting_key TEXT NOT NULL,
                 setting_value TEXT,
                 FOREIGN KEY (user_id) REFERENCES users (id),
                 UNIQUE(user_id, setting_key))''')

            db_connection.execute('''CREATE TABLE IF NOT EXISTS category_rules
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER NOT NULL,
                 category_id INTEGER NOT NULL,
                 rule_text TEXT NOT NULL,
                 match_type TEXT DEFAULT 'contains',
                 FOREIGN KEY (user_id) REFERENCES users (id),
                 FOREIGN KEY (category_id) REFERENCES categories (id),
                 UNIQUE(user_id, category_id, rule_text))''')

            db_connection.execute(
                f'UPDATE db_version SET version = {DB_VERSION}'
            )
            db_connection.commit()
            print(f"BD atualizado para v{DB_VERSION}")

        except Exception as e:
            db_connection.rollback()
            print(f"Erro na migração: {e}")
            import traceback
            traceback.print_exc()

    @staticmethod
    def _add_column_if_not_exists(conn, table, column, col_type):
        """Adiciona coluna se não existir"""
        exists = conn.execute(
            f"SELECT COUNT(*) FROM pragma_table_info('{table}') "
            f"WHERE name='{column}'"
        ).fetchone()[0] > 0

        if not exists:
            conn.execute(
                f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'
            )
            conn.commit()

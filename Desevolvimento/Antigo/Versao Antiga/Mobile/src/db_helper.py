import sqlite3
import os
from datetime import datetime

class DatabaseHelper:
    """Classe para gerenciar operações de banco de dados"""

    def __init__(self, db_path):
        """Inicializa conexão com o banco de dados"""
        # Verificar se o diretório existe
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        # Conectar ao banco
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

        # Criar tabelas se não existirem
        self.create_tables()

    def create_tables(self):
        """Cria as tabelas necessárias"""
        # Tabela de usuários
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        # Tabela de categorias
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                total_amount REAL DEFAULT 0,
                is_payment_goal INTEGER DEFAULT 0,
                is_savings_goal INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0,
                year INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Tabela de transações
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                date TEXT NOT NULL,
                category_id INTEGER,
                savings_category_id INTEGER,
                is_saving_transaction INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (category_id) REFERENCES categories (id),
                FOREIGN KEY (savings_category_id) REFERENCES categories (id)
            )
        ''')

        # Tabela de notas
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Tabela de versão do banco
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS db_version (
                version INTEGER
            )
        ''')

        # Inicializar versão se não existir
        version_exists = self.connection.execute(
            "SELECT COUNT(*) FROM db_version"
        ).fetchone()[0]

        if not version_exists:
            self.connection.execute('INSERT INTO db_version VALUES (3)')

        self.connection.commit()

    def create_user(self, username, password):
        """Cria um novo usuário"""
        self.connection.execute(
            'INSERT INTO users (username, password) VALUES (?, ?)',
            (username, password)
        )
        self.connection.commit()
        return True

    def authenticate_user(self, username, password):
        """Autentica um usuário"""
        user = self.connection.execute(
            'SELECT * FROM users WHERE username = ? AND password = ?',
            (username, password)
        ).fetchone()
        return user

    def get_transactions(self, user_id, year=None, month=None, search=None):
        """Obtém transações com filtros"""
        query = '''
            SELECT t.*, c.name as category_name
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
        '''

        params = [user_id]

        # Adicionar filtro de ano
        if year:
            query += " AND strftime('%Y', t.date) = ?"
            params.append(str(year))

        # Adicionar filtro de mês
        if month:
            query += " AND strftime('%m', t.date) = ?"
            params.append(f"{month:02d}")  # Formatar com zero à esquerda

        # Adicionar filtro de busca
        if search:
            query += " AND (t.description LIKE ? OR c.name LIKE ?)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        query += " ORDER BY t.date DESC"

        return self.connection.execute(query, params).fetchall()

    def get_categories(self, user_id, include_hidden=False):
        """Obtém categorias do usuário"""
        query = '''
            SELECT * FROM categories
            WHERE user_id = ?
        '''

        if not include_hidden:
            query += " AND (is_hidden = 0 OR is_hidden IS NULL)"

        query += " ORDER BY name"

        return self.connection.execute(query, [user_id]).fetchall()

    def get_notes(self, user_id):
        """Obtém notas do usuário"""
        query = '''
            SELECT * FROM notes
            WHERE user_id = ?
            ORDER BY created_at DESC
        '''

        return self.connection.execute(query, [user_id]).fetchall()

    def get_balance(self, user_id, year=None, month=None):
        """Calcula saldo do usuário com filtros opcionais"""
        # Construir query base
        query = '''
            SELECT
                SUM(CASE WHEN transaction_type = 'entrada' THEN amount ELSE 0 END) as total_income,
                SUM(CASE WHEN transaction_type = 'saida' THEN amount ELSE 0 END) as total_expense
            FROM transactions
            WHERE user_id = ?
        '''

        params = [user_id]

        # Adicionar filtros
        if year:
            query += " AND strftime('%Y', date) = ?"
            params.append(str(year))

        if month:
            query += " AND strftime('%m', date) = ?"
            params.append(f"{month:02d}")

        # Executar consulta
        result = self.connection.execute(query, params).fetchone()

        # Calcular saldo
        total_income = result['total_income'] or 0
        total_expense = result['total_expense'] or 0
        balance = total_income - total_expense

        return {
            'total_income': total_income,
            'total_expense': total_expense,
            'balance': balance
        }

    def get_available_years(self, user_id):
        """Retorna lista de anos com transações"""
        query = '''
            SELECT DISTINCT strftime('%Y', date) as year
            FROM transactions
            WHERE user_id = ?
            ORDER BY year DESC
        '''

        years = self.connection.execute(query, [user_id]).fetchall()
        return [year['year'] for year in years] if years else [str(datetime.now().year)]

    def add_transaction(self, transaction_data):
        """Adiciona uma nova transação"""
        self.connection.execute(
            '''
            INSERT INTO transactions
            (user_id, amount, description, transaction_type, date, category_id,
             savings_category_id, is_saving_transaction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                transaction_data['user_id'],
                transaction_data['amount'],
                transaction_data['description'],
                transaction_data['transaction_type'],
                transaction_data['date'],
                transaction_data.get('category_id'),
                transaction_data.get('savings_category_id'),
                transaction_data.get('is_saving_transaction', 0)
            )
        )
        self.connection.commit()
        return True

    def update_transaction(self, transaction_id, transaction_data):
        """Atualiza uma transação existente"""
        self.connection.execute(
            '''
            UPDATE transactions
            SET amount = ?, description = ?, transaction_type = ?,
                date = ?, category_id = ?
            WHERE id = ?
            ''',
            (
                transaction_data['amount'],
                transaction_data['description'],
                transaction_data['transaction_type'],
                transaction_data['date'],
                transaction_data.get('category_id'),
                transaction_id
            )
        )
        self.connection.commit()
        return True

    def delete_transaction(self, transaction_id):
        """Exclui uma transação"""
        self.connection.execute(
            'DELETE FROM transactions WHERE id = ?',
            (transaction_id,)
        )
        self.connection.commit()
        return True

    def add_category(self, category_data):
        """Adiciona uma nova categoria"""
        self.connection.execute(
            '''
            INSERT INTO categories
            (user_id, name, total_amount, is_payment_goal, is_savings_goal, year)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                category_data['user_id'],
                category_data['name'],
                category_data.get('total_amount', 0),
                category_data.get('is_payment_goal', 0),
                category_data.get('is_savings_goal', 0),
                datetime.now().year
            )
        )
        self.connection.commit()
        return True

    def close(self):
        """Fecha a conexão com o banco de dados"""
        if self.connection:
            self.connection.close()

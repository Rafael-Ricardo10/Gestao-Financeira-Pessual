"""
Módulo de gerenciamento de empréstimos
"""
from datetime import datetime


def create_loans_tables(db_connection):
    """Cria as tabelas necessárias para empréstimos"""

    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    db_connection.execute('''
        CREATE TABLE IF NOT EXISTS loan_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL,
            transaction_id INTEGER,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            installment_number INTEGER NOT NULL,
            notes TEXT,
            FOREIGN KEY (loan_id) REFERENCES loans (id),
            FOREIGN KEY (transaction_id) REFERENCES transactions (id)
        )
    ''')

    db_connection.commit()


def sync_loan_payments(db_connection, loan_id: int):
    """
    Sincroniza pagamentos do empréstimo buscando transações
    de SAÍDA vinculadas à categoria do empréstimo.

    Usa o ID ESPECÍFICO da transação para não confundir
    com outras transações de mesmo nome.
    """
    try:
        loan = db_connection.execute(
            'SELECT * FROM loans WHERE id = ?',
            (loan_id,)
        ).fetchone()

        if not loan or not loan['category_id']:
            return 0

        # Buscar transações de SAÍDA vinculadas à categoria
        transacoes = db_connection.execute(
            """SELECT id, amount, date, description
               FROM transactions
               WHERE category_id = ?
               AND transaction_type = 'saida'
               ORDER BY date ASC, id ASC""",
            (loan['category_id'],)
        ).fetchall()

        if not transacoes:
            return 0

        # Buscar IDs já registrados como pagamento
        pagamentos_existentes = db_connection.execute(
            """SELECT transaction_id FROM loan_payments
               WHERE loan_id = ?
               AND transaction_id IS NOT NULL""",
            (loan_id,)
        ).fetchall()

        ids_ja_registrados = {
            p['transaction_id'] for p in pagamentos_existentes
        }

        # Próximo número de parcela
        ultimo_numero = db_connection.execute(
            """SELECT MAX(installment_number) as ultimo
               FROM loan_payments WHERE loan_id = ?""",
            (loan_id,)
        ).fetchone()['ultimo'] or 0

        numero_parcela    = ultimo_numero
        novos_pagamentos  = 0

        for trans in transacoes:
            # Verificar pelo ID ESPECÍFICO da transação
            if trans['id'] not in ids_ja_registrados:
                numero_parcela += 1
                db_connection.execute(
                    """INSERT INTO loan_payments
                       (loan_id, transaction_id, payment_date,
                        amount, installment_number, notes)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        loan_id,
                        trans['id'],
                        trans['date'],
                        trans['amount'],
                        numero_parcela,
                        trans['description']
                    )
                )
                novos_pagamentos += 1

        if novos_pagamentos > 0:
            db_connection.commit()

        return novos_pagamentos

    except Exception as e:
        print(f"[loans] Erro ao sincronizar pagamentos: {e}")
        return 0


def calculate_loan(
    total_amount: float,
    interest_rate: float,
    num_installments: int,
    discount: float = 0
) -> dict:
    """
    Calcula os valores do empréstimo.

    Args:
        total_amount: Valor principal do empréstimo
        interest_rate: Taxa de juros em % ao mês (ex: 2.5)
        num_installments: Número de parcelas
        discount: Desconto em R$ no valor final

    Returns:
        Dicionário com os valores calculados
    """
    if interest_rate > 0:
        rate = interest_rate / 100
        # Tabela Price (juros compostos)
        total_with_interest = total_amount * (
            (rate * (1 + rate) ** num_installments) /
            ((1 + rate) ** num_installments - 1)
        ) * num_installments
    else:
        total_with_interest = total_amount

    final_amount = total_with_interest - discount
    if final_amount < 0:
        final_amount = 0

    installment_amount = (
        final_amount / num_installments
        if num_installments > 0 else 0
    )

    return {
        'total_amount':        total_amount,
        'interest_rate':       interest_rate,
        'num_installments':    num_installments,
        'discount':            discount,
        'total_with_interest': total_with_interest,
        'final_amount':        final_amount,
        'installment_amount':  installment_amount,
    }


def get_loan_status(db_connection, loan_id: int) -> dict:
    """
    Retorna o status atual de um empréstimo.
    Sincroniza pagamentos automaticamente antes de calcular.

    Returns:
        Dicionário com informações completas do status
    """
    # Sincronizar pagamentos automaticamente
    sync_loan_payments(db_connection, loan_id)

    loan = db_connection.execute(
        'SELECT * FROM loans WHERE id = ?',
        (loan_id,)
    ).fetchone()

    if not loan:
        return {}

    payments = db_connection.execute(
        """SELECT SUM(amount)  as total_paid,
                  COUNT(*)     as installments_paid
           FROM loan_payments
           WHERE loan_id = ?""",
        (loan_id,)
    ).fetchone()

    total_paid         = payments['total_paid'] or 0
    installments_paid  = payments['installments_paid'] or 0
    remaining_amount   = loan['final_amount'] - total_paid
    remaining_install  = loan['num_installments'] - installments_paid
    progress           = (
        (total_paid / loan['final_amount'] * 100)
        if loan['final_amount'] > 0 else 0
    )
    is_completed = remaining_amount <= 0.01

    return {
        'loan':                   loan,
        'total_paid':             total_paid,
        'installments_paid':      installments_paid,
        'remaining_amount':       max(0, remaining_amount),
        'remaining_installments': max(0, remaining_install),
        'progress':               min(100, progress),
        'is_completed':           is_completed,
    }


def check_and_complete_loans(db_connection, user_id: int) -> list:
    """
    Verifica e marca como concluídos os empréstimos quitados.
    Oculta a categoria do empréstimo quando quitado.

    Returns:
        Lista de empréstimos recém concluídos
    """
    active_loans = db_connection.execute(
        "SELECT * FROM loans WHERE user_id = ? AND status = 'ativo'",
        (user_id,)
    ).fetchall()

    completed = []
    for loan in active_loans:
        status = get_loan_status(db_connection, loan['id'])

        if status.get('is_completed'):
            # Marcar como quitado
            db_connection.execute(
                "UPDATE loans SET status = 'quitado' WHERE id = ?",
                (loan['id'],)
            )

            # Ocultar categoria do empréstimo
            # (não aparece mais em Categorias nem no AddTransaction)
            if loan['category_id']:
                db_connection.execute(
                    "UPDATE categories SET is_hidden = 1 WHERE id = ?",
                    (loan['category_id'],)
                )

            completed.append(loan)

    if completed:
        db_connection.commit()

    return completed


def is_loan_transaction(db_connection, transaction_id: int) -> dict:
    """
    Verifica se uma transação ESPECÍFICA está vinculada
    a um empréstimo pelo seu ID.

    Não verifica por nome/descrição - apenas pelo ID específico
    para não bloquear outras transações com o mesmo nome.

    Returns:
        dict com:
        - is_loan (bool): se é transação de empréstimo
        - type (str): 'recebimento' ou 'pagamento'
        - loan_id (int): ID do empréstimo
        - loan_name (str): Nome do empréstimo
        - category_id (int): ID da categoria do empréstimo
    """
    try:
        # Verificar se é a transação de RECEBIMENTO do empréstimo
        loan_received = db_connection.execute(
            """SELECT l.id, l.name, l.category_id
               FROM loans l
               WHERE l.transaction_id = ?""",
            (transaction_id,)
        ).fetchone()

        if loan_received:
            return {
                'is_loan':     True,
                'type':        'recebimento',
                'loan_id':     loan_received['id'],
                'loan_name':   loan_received['name'],
                'category_id': loan_received['category_id']
            }

        # Verificar se é uma transação de PAGAMENTO registrada
        loan_payment = db_connection.execute(
            """SELECT l.id, l.name, l.category_id
               FROM loan_payments lp
               JOIN loans l ON lp.loan_id = l.id
               WHERE lp.transaction_id = ?""",
            (transaction_id,)
        ).fetchone()

        if loan_payment:
            return {
                'is_loan':     True,
                'type':        'pagamento',
                'loan_id':     loan_payment['id'],
                'loan_name':   loan_payment['name'],
                'category_id': loan_payment['category_id']
            }

        # Verificar se a categoria da transação é de empréstimo
        # (transação já categorizada mas sem registro em loan_payments)
        trans = db_connection.execute(
            """SELECT t.id, t.category_id, c.name as cat_name
               FROM transactions t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.id = ?""",
            (transaction_id,)
        ).fetchone()

        if trans and trans['cat_name']:
            if trans['cat_name'].startswith('Empréstimo:'):
                loan = db_connection.execute(
                    """SELECT id, name FROM loans
                       WHERE category_id = ?""",
                    (trans['category_id'],)
                ).fetchone()
                if loan:
                    return {
                        'is_loan':     True,
                        'type':        'pagamento',
                        'loan_id':     loan['id'],
                        'loan_name':   loan['name'],
                        'category_id': trans['category_id']
                    }

        return {'is_loan': False}

    except Exception as e:
        print(f"[loans] Erro ao verificar transação: {e}")
        return {'is_loan': False}


def get_loan_summary(db_connection, user_id: int) -> dict:
    """
    Retorna um resumo geral de todos os empréstimos do usuário.

    Returns:
        Dicionário com resumo geral
    """
    try:
        tabela_existe = db_connection.execute(
            """SELECT COUNT(*) FROM sqlite_master
               WHERE type='table' AND name='loans'"""
        ).fetchone()[0] > 0

        if not tabela_existe:
            return {
                'tem_emprestimos':  False,
                'total_ativos':     0,
                'total_quitados':   0,
                'divida_total':     0,
                'total_pago':       0,
                'emprestimos':      []
            }

        loans = db_connection.execute(
            """SELECT * FROM loans WHERE user_id = ?
               ORDER BY status ASC, name ASC""",
            (user_id,)
        ).fetchall()

        if not loans:
            return {
                'tem_emprestimos':  False,
                'total_ativos':     0,
                'total_quitados':   0,
                'divida_total':     0,
                'total_pago':       0,
                'emprestimos':      []
            }

        ativos    = [l for l in loans if l['status'] == 'ativo']
        quitados  = [l for l in loans if l['status'] == 'quitado']

        divida_total = 0
        total_pago   = 0
        lista        = []

        for loan in loans:
            status = get_loan_status(db_connection, loan['id'])
            divida_total += status.get('remaining_amount', 0)
            total_pago   += status.get('total_paid', 0)

            lista.append({
                'id':             loan['id'],
                'nome':           loan['name'],
                'status':         loan['status'],
                'valor_final':    loan['final_amount'],
                'total_pago':     status.get('total_paid', 0),
                'restante':       status.get('remaining_amount', 0),
                'progresso':      status.get('progress', 0),
                'parcela':        loan['installment_amount'],
                'parcelas_pagas': status.get('installments_paid', 0),
                'total_parcelas': loan['num_installments'],
            })

        return {
            'tem_emprestimos': True,
            'total_ativos':    len(ativos),
            'total_quitados':  len(quitados),
            'divida_total':    divida_total,
            'total_pago':      total_pago,
            'emprestimos':     lista
        }

    except Exception as e:
        print(f"[loans] Erro ao gerar resumo: {e}")
        return {
            'tem_emprestimos': False,
            'total_ativos':    0,
            'total_quitados':  0,
            'divida_total':    0,
            'total_pago':      0,
            'emprestimos':     []
        }

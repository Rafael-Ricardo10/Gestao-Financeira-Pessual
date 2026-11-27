import os, sys, shutil, tempfile
sys.path.insert(0, '/home/claude/proj')
os.chdir(tempfile.mkdtemp()); os.makedirs('dados')
from modulos import identidade, sync_core, backup, bd_seguro, loans
from modulos.database import DBManager, DBUpdater
print('SQLCipher:', bd_seguro.CRIPTO_REPOUSO)

def nova_conta(usuario, senha):
    ch = identidade.derivar(usuario, senha)
    m = DBManager(ch.net_id, ch.chave_bd); c = m.connect(); m.create_tables()
    DBUpdater.check_and_update(c, ch.net_id)
    c.execute("INSERT INTO users(username,password) VALUES(?,?)", (usuario, '-')); c.commit()
    sync_core.preparar(c)
    return ch, c

def popular(c):
    uid = 1
    c.execute("INSERT INTO categories(user_id,name,year) VALUES(1,'Mercado',2026)")
    c.execute("INSERT INTO categories(user_id,name,year,is_savings_goal) VALUES(1,'Reserva',2026,1)")
    c.execute("INSERT INTO categories(user_id,name,year) VALUES(1,'Empréstimo: Carro',2026)")
    c.execute("INSERT INTO transactions(user_id,amount,description,transaction_type,date,category_id) VALUES(1,150.5,'Compra','saida','2026-03-02',1)")
    c.execute("INSERT INTO transactions(user_id,amount,description,transaction_type,date) VALUES(1,5000,'Salário','entrada','2026-03-01')")
    c.execute("INSERT INTO transactions(user_id,amount,description,transaction_type,date,category_id) VALUES(1,500,'Parcela 1','saida','2026-04-05',3)")
    c.execute("INSERT INTO notes(user_id,note) VALUES(1,'minha nota')")
    c.execute("INSERT INTO category_budgets(user_id,category_id,month,year,amount) VALUES(1,1,3,2026,800)")
    c.execute("INSERT INTO category_rules(user_id,category_id,rule_text) VALUES(1,1,'MERCADO')")
    c.execute("INSERT INTO savings_goals(user_id,name,target_amount,start_date,category_id) VALUES(1,'Viagem',9000,'2026-01-01',2)")
    c.execute("INSERT INTO loans(user_id,name,total_amount,num_installments,final_amount,installment_amount,start_date,category_id) VALUES(1,'Carro',6000,12,6000,500,'2026-03-01',3)")
    c.execute("INSERT INTO loan_payments(loan_id,transaction_id,payment_date,amount,installment_number,notes) VALUES(1,NULL,'2026-05-01',500,1,'desconto manual')")
    c.commit()
    loans.sync_loan_payments(c, 1)    # cria pagamento ligado à transação
    c.execute("INSERT INTO plans(user_id,name,start_date,period_amount,period_unit) VALUES(1,'Plano 2027','2027-01-01',12,'mes')")
    c.execute("INSERT INTO plan_categories(plan_id,name,unit_price,quantity,unit,frequency) VALUES(1,'Pão',1.5,2,'unidade','dia')")
    c.commit()

def contagem(c):
    tabs = ['categories','transactions','notes','category_budgets','category_rules','savings_goals','loans','loan_payments','plans','plan_categories']
    return {t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tabs}

chA, A = nova_conta('Ricardo', 'senha-forte-123'); popular(A)
cA = contagem(A); print('A      ', cA)

# --- BACKUP -> conta NOVA (login diferente) ---
blob, n = backup.exportar(A, 'frase-do-backup'); print('backup registros:', n, 'bytes:', len(blob))
chB, B = nova_conta('outro-login', 'outra-senha-456')
backup.importar(B, blob, 'frase-do-backup'); loans.sync_loan_payments(B, 1)
cB = contagem(B); print('B(rest)', cB)
print('IGUAIS:', cA == cB)
for t in cA:
    if cA[t] != cB[t]: print('  DIFERE', t, cA[t], cB[t])
# valores
q = lambda c, s: [tuple(r) for r in c.execute(s).fetchall()]
s1 = "SELECT t.amount,t.description,c.name FROM transactions t LEFT JOIN categories c ON c.id=t.category_id ORDER BY t.description"
print('transações+categoria iguais:', q(A,s1)==q(B,s1))
s2 = "SELECT l.name,c.name FROM loans l LEFT JOIN categories c ON c.id=l.category_id"
print('empréstimo->categoria igual:', q(A,s2)==q(B,s2))
print('Reimportar 2x idempotente:', end=' ')
backup.importar(B, blob, 'frase-do-backup'); print(contagem(B)==cB)
try: backup.importar(B, blob, 'errada'); print('FRASE ERRADA ACEITA!')
except ValueError as e: print('frase errada ->', e)

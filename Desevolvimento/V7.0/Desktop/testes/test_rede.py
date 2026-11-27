import os, sys, time, tempfile, logging
sys.path.insert(0, os.environ.get('PROJ', '/home/claude/proj'))
logging.basicConfig(level=logging.WARNING)
from modulos import identidade, sync_core, bd_seguro
from modulos.database import DBManager, DBUpdater
from modulos.rede import RedeConta

def prep(base, ch):
    os.makedirs(os.path.join(base, 'dados'), exist_ok=True)
    cwd = os.getcwd(); os.chdir(base)
    m = DBManager(ch.net_id, ch.chave_bd); c = m.connect(); m.create_tables()
    DBUpdater.check_and_update(c, ch.net_id)
    c.execute("INSERT INTO users(username,password) VALUES('u','-')"); c.commit()
    sync_core.preparar(c); os.chdir(cwd)
    return c, os.path.join(base, 'dados', f'{ch.net_id}.db')

ch = identidade.derivar('teste', 'senha-super-123')
bA, bB = tempfile.mkdtemp(), tempfile.mkdtemp()
cA, pA = prep(bA, ch); cB, pB = prep(bB, ch)
cA.execute("INSERT INTO categories(user_id,name,year) VALUES(1,'DoA',2026)"); cA.commit()
cB.execute("INSERT INTO notes(user_id,note) VALUES(1,'DoB')"); cB.commit()
cA.close(); cB.close()
A = RedeConta(bA, ch, pA); B = RedeConta(bB, ch, pB)
A.config['nome'] = 'PC-A'; B.config['nome'] = 'PC-B'
if A.slot == B.slot: B.config['slot'] = (A.slot + 1) % 40; B._salvar()
print('slots', A.slot, B.slot)
print(A.iniciar()); print(B.iniciar())
time.sleep(2)
a = A.meu_bootstrap(); print('A dht', a)
B.adicionar_no('127.0.0.1', a['porta'], a['dht'])
b = B.meu_bootstrap(); A.adicionar_no('127.0.0.1', b['porta'], b['dht'])
for i in range(40):
    time.sleep(1)
    ea, eb = A.estado(), B.estado()
    if ea['pares_online'] and eb['pares_online'] and not ea['pendentes'] and not eb['pendentes'] and i > 6:
        break
print('A:', ea['rede'], ea['pares_online'], [ (d['nome'],d['online']) for d in ea['dispositivos']], 'pend', ea['pendentes'])
print('B:', eb['rede'], eb['pares_online'], [ (d['nome'],d['online']) for d in eb['dispositivos']], 'pend', eb['pendentes'])
time.sleep(3)
for nome, p in (('A', pA), ('B', pB)):
    c = bd_seguro.conectar(p, ch.chave_bd)
    print(nome, 'cats', [r[0] for r in c.execute('select name from categories')], 'notes', [r[0] for r in c.execute('select note from notes')])
A.parar(); B.parar()

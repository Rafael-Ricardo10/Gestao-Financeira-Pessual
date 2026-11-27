import os, sys, time, tempfile
sys.path.insert(0, '/home/claude/proj')
papel, tmax = sys.argv[1], int(sys.argv[2])
base = tempfile.mkdtemp(); os.makedirs(base+'/dados'); os.chdir(base)
from modulos import identidade, sync_core, bd_seguro
from modulos.database import DBManager, DBUpdater
from modulos.rede import RedeConta
ch = identidade.derivar('nat', 'senha-super-123'); db = f'dados/{ch.net_id}.db'
m = DBManager(ch.net_id, ch.chave_bd); c = m.connect(); m.create_tables(); DBUpdater.check_and_update(c, ch.net_id)
c.execute("INSERT INTO users(username,password) VALUES('u','-')")
c.execute("INSERT INTO notes(user_id,note) VALUES(1,?)", (f'nota de {papel}',)); c.commit(); sync_core.preparar(c); c.close()
r = RedeConta(base, ch, db); r.config['nome'] = papel; r.config['slot'] = 3 if papel=='A-FORA' else 4; r._salvar(); r.iniciar()
if papel == 'C-DENTRO':
    time.sleep(10); print('C: iniciando varredura de sub-redes vizinhas', flush=True); r.varrer_sub_redes()
t0 = time.time(); ok = False
while time.time()-t0 < tmax:
    e = r.estado(); c = bd_seguro.conectar(db, ch.chave_bd); n = sorted(x[0] for x in c.execute('select note from notes')); c.close()
    if e['pares_online'] and len(n) == 2: ok = True; break
    time.sleep(2)
v = e['varredura']
print(papel, '| sincronizou:', ok, '| notas:', n, '| redes:', [i['ip'] for i in e['interfaces']], '| eventos:', [x[11:] for x in e['eventos'] if 'encontrado' in x][-2:], flush=True)
time.sleep(6); r.parar()

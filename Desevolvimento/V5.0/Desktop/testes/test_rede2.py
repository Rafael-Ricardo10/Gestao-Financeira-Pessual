import os, sys, time, tempfile, logging, threading
sys.path.insert(0, '/home/claude/proj')
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

def esperar(cond, t=40, passo=0.5):
    t0 = time.time()
    while time.time() - t0 < t:
        if cond(): return True
        time.sleep(passo)
    return False

ch = identidade.derivar('teste', 'senha-super-123')
bA, bB = tempfile.mkdtemp(), tempfile.mkdtemp()
cA, pA = prep(bA, ch); cB, pB = prep(bB, ch)
cA.execute("INSERT INTO categories(user_id,name,year) VALUES(1,'DoA',2026)"); cA.commit()
cB.execute("INSERT INTO notes(user_id,note) VALUES(1,'DoB')"); cB.commit(); cA.close(); cB.close()

saiu = []
A = RedeConta(bA, ch, pA); B = RedeConta(bB, ch, pB, ao_sair=lambda q: saiu.append(q))
A.config['nome'] = 'PC-A'; B.config['nome'] = 'NOTE-ESCRITORIO'
B.config['slot'] = (A.slot + 1) % 40; B._salvar()
A.iniciar(); B.iniciar()
print('1) descoberta SEM nó manual / SEM internet ...')
ok = esperar(lambda: A.estado()['pares_online'] and B.estado()['pares_online'], 60)
print('   conectados:', ok)
print('   eventos A:', [e for e in A.estado()['eventos'] if 'encontrado' in e or 'Rede' in e][-3:])
esperar(lambda: not A.estado()['pendentes'] and not B.estado()['pendentes'], 20)
for n, p in (('A', pA), ('B', pB)):
    c = bd_seguro.conectar(p, ch.chave_bd)
    print('  ', n, [r[0] for r in c.execute('select name from categories')], [r[0] for r in c.execute('select note from notes')]); c.close()

print('2) latência/IP/nome')
A.medir_latencia_agora()
esperar(lambda: any(d.get('lat_ms') is not None for d in A.estado()['dispositivos']), 15)
for d in A.estado()['dispositivos']: print('  ', d['nome'], d['online'], d['lat_ms'], 'ms', d['ips'])
print('   diag A:', A.estado()['diag']['titulo'], '|', A.estado()['diag']['texto'][:70])

print('3) desconexão remota (B online)')
devB = [d['dev'] for d in A.estado()['dispositivos'] if d['nome']=='NOTE-ESCRITORIO'][0]
A.desconectar_dispositivo(devB)
print('   B recebeu o comando:', esperar(lambda: saiu, 20), saiu)
print('   pendência limpa em A:', esperar(lambda: not A.estado()['sair_pendente'], 15))

print('4) comando pendente p/ aparelho OFFLINE, entregue ao voltar')
B.parar(); time.sleep(2)
saiu.clear()
A.desconectar_dispositivo(devB)
time.sleep(3); print('   pendente enquanto offline:', bool(A.estado()['sair_pendente']))
B2 = RedeConta(bB, ch, pB, ao_sair=lambda q: saiu.append(q)); B2.iniciar()
print('   entregue ao reconectar:', esperar(lambda: saiu, 40), '| comando NÃO repete (cmd já feito): ', end='')
saiu.clear(); time.sleep(8); print(not saiu)

A.parar(); B2.parar()

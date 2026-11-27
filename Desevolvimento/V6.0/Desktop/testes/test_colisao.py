import os, sys, time, tempfile, logging
sys.path.insert(0, '/home/claude/proj'); logging.basicConfig(level=logging.WARNING)
exec(open('/home/claude/t/test_rede2.py').read().split("ch = identidade")[0])
ch = identidade.derivar('colisao', 'senha-super-123')
bA, bB = tempfile.mkdtemp(), tempfile.mkdtemp()
cA, pA = prep(bA, ch); cB, pB = prep(bB, ch); cA.close(); cB.close()
A = RedeConta(bA, ch, pA); B = RedeConta(bB, ch, pB)
B.config['slot'] = A.slot; B._salvar()          # FORÇA a mesma identidade
print('slots iguais:', A.slot == B.slot)
A.iniciar(); B.iniciar()
ok = esperar(lambda: A.estado()['pares_online'] and B.estado()['pares_online'], 90)
print('apesar da colisão, se conectaram:', ok, '| slots agora', A.slot, B.slot, '(diferentes:', A.slot != B.slot, ')')
A.parar(); B.parar()

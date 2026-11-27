"""
Contas do SERVIDOR (que é só mais um par da rede de cada conta).

  dados/<net_id>.db           banco da conta, CIFRADO (SQLCipher) com chave
                              derivada do login; o nome do arquivo não revela
                              o usuário
  dados/redes/<net_id>/       identidade Tox e estado de sincronização
  dados/servidor.db           (legado) contas antigas com senha em hash

Chaves ficam SÓ EM MEMÓRIA enquanto a conta está ativa. Sem as chaves o
servidor não consegue ler nem sincronizar a conta. Opcional ("manter ativa
após reiniciar"): cofre em disco cifrado com o segredo do servidor.

O servidor usa EXATAMENTE a mesma rede do app (modulos/rede.py): mesmas
identidades Tox derivadas do login (com identidade.tox cifrado em disco),
descoberta na rede local, enlace TCP direto, desconexão remota e a mesma
troca de senha que preserva os dados (modulos/troca_senha.py).
"""
import os
import time
import json
import threading
import hashlib
import logging
import sqlite3 as _sqlite_plano
from werkzeug.security import check_password_hash

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from modulos import identidade, sync_core, bd_seguro, troca_senha
from modulos.database import DBManager, DBUpdater, DB_VERSION
from modulos.currency_tracker import create_currency_tables
from modulos.rede import RedeConta

log = logging.getLogger('RRFS.Contas')

DIR = 'dados'
LEGADO = os.path.join(DIR, 'servidor.db')
ATIVAS = {}                  # net_id -> {'chaves', 'rede'}
_trava = threading.RLock()
_base = os.getcwd()


def iniciar(base):
    global _base
    _base = base
    os.makedirs(DIR, exist_ok=True)
    os.makedirs(os.path.join(DIR, 'redes'), exist_ok=True)


def caminho_db(net_id):
    return os.path.join(DIR, f'{net_id}.db')


def abrir_db(net_id):
    a = ATIVAS.get(net_id)
    if not a:
        raise PermissionError('Conta bloqueada neste servidor')
    c = bd_seguro.conectar(caminho_db(net_id), a['chaves'].chave_bd)
    c.execute('PRAGMA foreign_keys=OFF')
    return c


def user_id(conn):
    return conn.execute('SELECT id FROM users ORDER BY id LIMIT 1'
                        ).fetchone()['id']


def chaves_de(net_id):
    a = ATIVAS.get(net_id)
    return a['chaves'] if a else None


def rede_de(net_id):
    a = ATIVAS.get(net_id)
    return a['rede'] if a else None


# ── criação / entrada ───────────────────────────────────────────────

def _criar_db(chaves):
    m = DBManager(chaves.net_id, chaves.chave_bd)
    c = m.connect()
    try:
        m.create_tables()
        c.execute('INSERT INTO users(username, password) VALUES(?,?)',
                  (chaves.usuario, '-'))
        c.execute('DELETE FROM db_version')
        c.execute('INSERT INTO db_version VALUES(?)', (DB_VERSION,))
        c.commit()
        create_currency_tables(c)
        sync_core.preparar(c)
    finally:
        c.close()


def _preparar_db(chaves):
    """Idempotente, igual à abertura de conta do app: cria o que faltar
    (ex.: tabelas de planejamento de bancos criados por versões anteriores
    do servidor), aplica migrações e liga os triggers de sincronização.
    Sem isto, um lote com registros de uma tabela inexistente faria a
    sincronização falhar."""
    m = DBManager(chaves.net_id, chaves.chave_bd)
    c = m.connect()
    try:
        m.create_tables()
        DBUpdater.check_and_update(c, chaves.net_id)
        create_currency_tables(c)
        if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            c.execute('INSERT INTO users(username, password) VALUES(?,?)',
                      (chaves.usuario, '-'))
            c.commit()
        sync_core.preparar(c)
    finally:
        c.close()


def _legado(usuario, senha):
    """Conta do formato antigo (usuário/senha em hash + dados/<usuario>.db)."""
    if not os.path.exists(LEGADO):
        return None
    try:
        m = _sqlite_plano.connect(LEGADO)
        r = m.execute('SELECT senha_hash FROM contas WHERE username=?',
                      (usuario,)).fetchone()
        m.close()
    except Exception:
        return None
    arq = os.path.join(DIR, f'{usuario}.db')
    if r and os.path.exists(arq) and check_password_hash(r[0], senha):
        return arq
    return None


def entrar(usuario, senha, criar=False):
    """Devolve (net_id, erro). `criar` permite abrir conta nova (ou entrar
    numa rede que existe só em outros aparelhos)."""
    erro = identidade.validar(usuario, senha)
    if erro and (criar or len(senha or '') < 1):
        return None, erro
    chaves = identidade.derivar(usuario, senha or '')
    nid = chaves.net_id
    with _trava:
        existe = os.path.exists(caminho_db(nid))
        if not existe:
            leg = _legado(usuario.strip(), senha)
            if leg:
                _criar_db(chaves)
                _importar_legado(chaves, leg, senha)
                existe = True
        if not existe:
            if not criar:
                return None, ('Usuário ou senha incorretos. Se esta conta '
                              'ainda não existe neste servidor, use '
                              '"Primeiro acesso".')
            if erro:
                return None, erro
            _criar_db(chaves)
        _ativar(chaves)
    return nid, ''


def _importar_legado(chaves, arquivo, senha):
    from modulos.importar_db import importar
    c = bd_seguro.conectar(caminho_db(chaves.net_id), chaves.chave_bd)
    try:
        importar(arquivo, senha, c, user_id(c), False, manter_uid=True)
    finally:
        c.close()
    os.replace(arquivo, arquivo + '.migrado')


def _ativar(chaves):
    if chaves.net_id in ATIVAS:
        return
    _preparar_db(chaves)
    nid = chaves.net_id

    def ao_sair(quem):
        # outro aparelho da conta mandou ESTE servidor sair: esquece as
        # chaves e desliga a rede (como o app volta à tela de login).
        # Em thread própria: bloquear() para a rede que chamou este callback.
        log.warning('Desconexão remota pedida por %s: bloqueando a conta', quem)
        threading.Thread(target=bloquear, args=(nid,), daemon=True,
                         name='Sair-Remoto').start()

    rede = RedeConta(_base, chaves, caminho_db(nid), ao_sair=ao_sair)
    ATIVAS[nid] = {'chaves': chaves, 'rede': rede}
    rede.iniciar()


def bloquear(net_id):
    """Esquece as chaves e desliga a rede da conta neste servidor."""
    with _trava:
        a = ATIVAS.pop(net_id, None)
    if a:
        a['rede'].parar()
    try:
        os.remove(_cofre_path(net_id))
    except OSError:
        pass


# ── "manter ativa após reiniciar" (opt-in) ──────────────────────────

def _segredo():
    with open(os.path.join(DIR, 'secret.key'), 'rb') as f:
        return hashlib.sha256(b'cofre|' + f.read()).digest()


def _cofre_path(net_id):
    return os.path.join(DIR, 'redes', net_id, 'cofre.bin')


def cofre_ativo(net_id):
    return os.path.exists(_cofre_path(net_id))


def cofre_definir(net_id, ligado):
    if not ligado:
        try:
            os.remove(_cofre_path(net_id))
        except OSError:
            pass
        return
    a = ATIVAS.get(net_id)
    if not a:
        return
    nonce = os.urandom(12)
    ct = ChaCha20Poly1305(_segredo()).encrypt(
        nonce, a['chaves'].exportar().encode(), b'cofre')
    os.makedirs(os.path.dirname(_cofre_path(net_id)), exist_ok=True)
    p = _cofre_path(net_id)
    with open(p, 'wb') as f:
        f.write(nonce + ct)
    os.chmod(p, 0o600)


def restaurar_cofres(log=None):
    base = os.path.join(DIR, 'redes')
    for nid in (os.listdir(base) if os.path.isdir(base) else []):
        p = _cofre_path(nid)
        if not os.path.exists(p):
            continue
        try:
            blob = open(p, 'rb').read()
            ch = identidade.Chaves.importar(ChaCha20Poly1305(_segredo()).decrypt(
                blob[:12], blob[12:], b'cofre').decode())
            if ch.net_id == nid and os.path.exists(caminho_db(nid)):
                with _trava:
                    _ativar(ch)
        except Exception as e:
            if log:
                log.warning('cofre de %s inválido: %s', nid, e)


# ── troca de senha: mesma rotina do app (os dados migram inteiros) ──

def trocar_senha(net_id, senha_atual, nova):
    """Migra a conta para as chaves da senha nova (modulos/troca_senha.py:
    copia o banco cifrado, confere contagens e integridade, e só então
    apaga a conta antiga; qualquer falha deixa a antiga intacta).
    Os OUTROS aparelhos não mudam sozinhos: neles, use "Alterar senha" com
    a mesma senha nova, ou saia e entre com a nova (os dados sincronizam)."""
    a = ATIVAS.get(net_id)
    if not a:
        return None, 'Conta bloqueada'
    atual = a['chaves']
    with _trava:
        manter = cofre_ativo(net_id)
        bloquear(net_id)                  # para a rede e solta o banco
        try:
            novas = troca_senha.trocar_senha(DIR, atual.usuario,
                                             senha_atual or '', nova)
        except Exception as e:
            _ativar(atual)                # falhou: a conta antiga continua
            if manter:
                cofre_definir(net_id, True)
            if isinstance(e, troca_senha.ErroTroca):
                return None, str(e)
            log.exception('trocar senha')
            return None, f'Não foi possível trocar a senha: {e}'
        _ativar(novas)
        if manter:
            cofre_definir(novas.net_id, True)
    return novas.net_id, ''

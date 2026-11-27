"""
Importa o arquivo .db da versão antiga (desktop) para a conta logada.
A senha informada é a do usuário DENTRO do arquivo antigo (tabela users).
Os ids são remapeados; os triggers de sync dão uid às linhas importadas.
"""
import hmac
import hashlib
import sqlite3
from pathlib import Path
try:
    from werkzeug.security import check_password_hash
except ImportError:                      # app desktop sem Flask/werkzeug
    def check_password_hash(*_a, **_k):
        return False

# (tabela, {coluna_fk: tabela_de_origem_do_mapa})
COPIA = [
    ('categories', {}),
    ('transactions', {'category_id': 'categories',
                      'savings_category_id': 'categories'}),
    ('savings_goals', {'category_id': 'categories'}),
    ('category_budgets', {'category_id': 'categories'}),
    ('category_rules', {'category_id': 'categories'}),
    ('loans', {'category_id': 'categories', 'transaction_id': 'transactions'}),
    ('notes', {}),
    ('user_settings', {}),
]
LIMPAR = ['loan_payments', 'loans', 'transactions', 'category_rules',
          'category_budgets', 'savings_goals', 'categories', 'notes']


def _confere(guardada, senha):
    if not guardada:
        return False
    g, b = str(guardada), senha.encode('utf-8')
    if hmac.compare_digest(g.encode('utf-8'), b):
        return True
    for h in (hashlib.sha256, hashlib.sha512):
        if hmac.compare_digest(h(b).hexdigest(), g.lower()):
            return True
    try:
        if check_password_hash(g, senha):
            return True
    except Exception:
        pass
    try:
        import bcrypt
        if g.startswith('$2') and bcrypt.checkpw(b, g.encode('utf-8')):
            return True
    except Exception:
        pass
    return False


def _existe(c, t):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                     "AND name=?", (t,)).fetchone() is not None


def _copiar(src, dst, tabela, remap, mapas, uid_old, uid_new,
            filtro='user_id=?', manter_uid=False):
    if not _existe(src, tabela):
        return 0
    csrc = {r[1] for r in src.execute(f'PRAGMA table_info({tabela})')}
    # manter_uid: bancos que JÁ sincronizavam entre si (app + servidor antigos)
    # trazem os mesmos uid; preservá-los evita duplicar tudo na rede nova
    excl = ('id',) if manter_uid else ('id', 'uid', 'updated_at')
    usar = [r[1] for r in dst.execute(f'PRAGMA table_info({tabela})')
            if r[1] not in excl and r[1] in csrc]
    if not usar:
        return 0
    mapa = mapas.setdefault(tabela, {})
    ins = (f"INSERT OR IGNORE INTO {tabela} ({', '.join(usar)}) "
           f"VALUES ({', '.join('?' * len(usar))})")
    n = 0
    for row in src.execute(f"SELECT id, {', '.join(usar)} FROM {tabela} "
                           f"WHERE {filtro}", (uid_old,)).fetchall():
        vals = []
        for c in usar:
            v = row[c]
            if c == 'user_id':
                v = uid_new
            elif c in remap and v is not None:
                v = mapas.get(remap[c], {}).get(v)
            vals.append(v)
        cur = dst.execute(ins, vals)
        if cur.rowcount:
            mapa[row['id']] = cur.lastrowid
            n += 1
    return n


def importar(caminho, senha, dst, uid_novo, limpar=False, manter_uid=False):
    """Retorna {'ok': True, 'contagem': {...}} ou {'erro': '...'}."""
    try:
        with open(caminho, 'rb') as f:
            if f.read(16) != b'SQLite format 3\x00':
                return {'erro': 'O arquivo não é um banco SQLite válido '
                                '(ou está criptografado).'}
        src = sqlite3.connect(Path(caminho).resolve().as_uri() + '?mode=ro',
                              uri=True)
        src.row_factory = sqlite3.Row
    except Exception as e:
        return {'erro': f'Não foi possível abrir o arquivo: {e}'}
    try:
        if not _existe(src, 'users'):
            return {'erro': 'Banco sem tabela de usuários (não é do RRFS).'}
        antigo = None
        for u in src.execute('SELECT id, password FROM users'):
            if _confere(u['password'], senha):
                antigo = u['id']
                break
        if antigo is None:
            return {'erro': 'Senha não confere com nenhum usuário do arquivo.'}
        mapas, cont = {}, {}
        try:
            if limpar:
                for t in LIMPAR:
                    if _existe(dst, t):
                        dst.execute(f'DELETE FROM {t}')
            for tabela, remap in COPIA:
                cont[tabela] = _copiar(src, dst, tabela, remap, mapas,
                                       antigo, uid_novo,
                                       manter_uid=manter_uid)
            if _existe(src, 'loan_payments'):
                cont['loan_payments'] = _copiar(
                    src, dst, 'loan_payments',
                    {'loan_id': 'loans', 'transaction_id': 'transactions'},
                    mapas, antigo, uid_novo,
                    filtro='loan_id IN (SELECT id FROM loans WHERE user_id=?)',
                    manter_uid=manter_uid)
            dst.commit()
        except Exception as e:
            dst.rollback()
            return {'erro': f'Falha na importação (nada foi alterado): {e}'}
        return {'ok': True, 'contagem': cont}
    finally:
        src.close()

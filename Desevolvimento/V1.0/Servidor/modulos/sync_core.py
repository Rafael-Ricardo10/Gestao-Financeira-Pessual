"""
Núcleo de sincronização offline-first (usado pelo SERVIDOR e pelo APP DESKTOP).

Como funciona
  * Cada linha sincronizada ganha `uid` (id global) e `updated_at` (UTC).
  * Triggers do SQLite preenchem uid/updated_at e registram toda mudança em
    `sync_changes` - o código antigo (INSERT/UPDATE/DELETE) NÃO precisa mudar.
  * DELETE vira "tombstone" (sync_tombstones) e a exclusão vence.
  * Conflito de edição: vence o `updated_at` mais recente (last-write-wins).
  * Chaves estrangeiras viajam como uid (os ids locais diferem por máquina).
  * Cada par (peer) tem uma marca d'água (`sync_peers.enviado_seq`).
"""
import sqlite3
from datetime import datetime, timezone

# tabela -> (colunas de dados, {coluna_fk: tabela_referenciada})
# A ORDEM importa: referenciadas antes das que referenciam.
DEF = {
    'categories': (['name', 'total_amount', 'is_payment_goal',
                    'is_savings_goal', 'is_hidden', 'year'], {}),
    'transactions': (['amount', 'description', 'transaction_type', 'date',
                      'is_saving_transaction'],
                     {'category_id': 'categories',
                      'savings_category_id': 'categories'}),
    'loans': (['name', 'description', 'reason', 'total_amount',
               'interest_rate', 'num_installments', 'discount',
               'final_amount', 'installment_amount', 'start_date', 'status'],
              {'category_id': 'categories', 'transaction_id': 'transactions'}),
    'savings_goals': (['name', 'target_amount', 'current_amount',
                       'start_date', 'deadline', 'notes'],
                      {'category_id': 'categories'}),
    'category_budgets': (['month', 'year', 'amount'],
                         {'category_id': 'categories'}),
    'category_rules': (['rule_text', 'match_type'],
                       {'category_id': 'categories'}),
}
ORDEM = {t: i for i, t in enumerate(DEF)}
# chaves naturais (UNIQUE) para unificar o uid em caso de conflito
NATURAL = {'category_budgets': ['category_id', 'month', 'year'],
           'category_rules': ['category_id', 'rule_text']}

_TS = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def agora():
    d = datetime.now(timezone.utc)
    return d.strftime('%Y-%m-%dT%H:%M:%S.') + f'{d.microsecond // 1000:03d}Z'


def _triggers(t):
    def log(u, op):
        return (f"INSERT INTO sync_changes(tabela,uid,op) "
                f"VALUES('{t}',{u},'{op}');")
    return f'''
CREATE TRIGGER IF NOT EXISTS sy_{t}_ai AFTER INSERT ON {t} WHEN NEW.uid IS NULL
BEGIN UPDATE {t} SET uid=lower(hex(randomblob(16))), updated_at={_TS} WHERE id=NEW.id; END;
CREATE TRIGGER IF NOT EXISTS sy_{t}_ai2 AFTER INSERT ON {t} WHEN NEW.uid IS NOT NULL
BEGIN {log('NEW.uid', 'u')} END;
CREATE TRIGGER IF NOT EXISTS sy_{t}_au AFTER UPDATE ON {t}
WHEN NEW.updated_at IS OLD.updated_at AND NEW.uid IS NOT NULL
BEGIN UPDATE {t} SET updated_at={_TS} WHERE id=NEW.id; {log('NEW.uid', 'u')} END;
CREATE TRIGGER IF NOT EXISTS sy_{t}_au2 AFTER UPDATE ON {t}
WHEN NEW.updated_at IS NOT OLD.updated_at AND NEW.uid IS NOT NULL
BEGIN {log('NEW.uid', 'u')} END;
CREATE TRIGGER IF NOT EXISTS sy_{t}_ad AFTER DELETE ON {t} WHEN OLD.uid IS NOT NULL
BEGIN INSERT OR REPLACE INTO sync_tombstones(tabela,uid,deleted_at)
VALUES('{t}',OLD.uid,{_TS}); {log('OLD.uid', 'd')} END;
'''


def preparar(conn):
    """Idempotente: cria tabelas/colunas/triggers de sincronização."""
    conn.executescript('''
CREATE TABLE IF NOT EXISTS sync_changes(
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    tabela TEXT NOT NULL, uid TEXT NOT NULL, op TEXT NOT NULL DEFAULT 'u');
CREATE TABLE IF NOT EXISTS sync_tombstones(
    tabela TEXT NOT NULL, uid TEXT NOT NULL, deleted_at TEXT NOT NULL,
    PRIMARY KEY(tabela, uid));
CREATE TABLE IF NOT EXISTS sync_peers(
    peer TEXT PRIMARY KEY, enviado_seq INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sync_meta(k TEXT PRIMARY KEY, v TEXT);
''')
    for t in DEF:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info({t})')}
        if not cols:
            continue
        if 'uid' not in cols:
            conn.execute(f'ALTER TABLE {t} ADD COLUMN uid TEXT')
        if 'updated_at' not in cols:
            conn.execute(f'ALTER TABLE {t} ADD COLUMN updated_at TEXT')
        conn.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS ix_{t}_uid ON {t}(uid)')
        conn.execute(f'UPDATE {t} SET uid=lower(hex(randomblob(16))) '
                     f'WHERE uid IS NULL')
        conn.execute(f'UPDATE {t} SET updated_at={_TS} '
                     f'WHERE updated_at IS NULL')
        conn.executescript(_triggers(t))
    if not conn.execute("SELECT 1 FROM sync_meta WHERE k='init'").fetchone():
        for t in DEF:
            if {r[1] for r in conn.execute(f'PRAGMA table_info({t})')}:
                conn.execute(
                    f"INSERT INTO sync_changes(tabela,uid,op) "
                    f"SELECT '{t}',uid,'u' FROM {t} WHERE uid IS NOT NULL")
        conn.execute("INSERT INTO sync_meta VALUES('init','1')")
    conn.commit()


# ── marca d'água por peer ───────────────────────────────────────────

def get_enviado(conn, peer):
    r = conn.execute('SELECT enviado_seq FROM sync_peers WHERE peer=?',
                     (peer,)).fetchone()
    return r[0] if r else 0


def set_enviado(conn, peer, seq):
    conn.execute(
        'INSERT INTO sync_peers(peer,enviado_seq) VALUES(?,?) '
        'ON CONFLICT(peer) DO UPDATE SET '
        'enviado_seq=MAX(enviado_seq, excluded.enviado_seq)', (peer, seq))
    conn.commit()


def ha_pendentes(conn, peer):
    ate = conn.execute(
        'SELECT COALESCE(MAX(seq),0) FROM sync_changes').fetchone()[0]
    return ate > get_enviado(conn, peer)


# ── coleta ──────────────────────────────────────────────────────────

def _uid_de(conn, tabela, rid):
    if rid is None:
        return None
    r = conn.execute(f'SELECT uid FROM {tabela} WHERE id=?',
                     (rid,)).fetchone()
    return r[0] if r else None


def _id_de(conn, tabela, uid):
    if not uid:
        return None
    r = conn.execute(f'SELECT id FROM {tabela} WHERE uid=?',
                     (uid,)).fetchone()
    return r[0] if r else None


def _registro(conn, t, uid):
    cols, refs = DEF[t]
    nomes = ['uid', 'updated_at'] + cols + list(refs)
    row = conn.execute(f'SELECT {", ".join(nomes)} FROM {t} WHERE uid=?',
                       (uid,)).fetchone()
    if row:
        d = {k: row[k] for k in ['uid', 'updated_at'] + cols}
        for col, tab in refs.items():
            d[col] = _uid_de(conn, tab, row[col])
        return {'t': t, 'op': 'u', 'uid': uid, 'd': d}
    tb = conn.execute('SELECT deleted_at FROM sync_tombstones '
                      'WHERE tabela=? AND uid=?', (t, uid)).fetchone()
    if tb:
        return {'t': t, 'op': 'd', 'uid': uid, 'em': tb[0]}
    return None


def coletar(conn, desde):
    """Retorna (registros ordenados por dependência, seq_final)."""
    ate = conn.execute(
        'SELECT COALESCE(MAX(seq),0) FROM sync_changes').fetchone()[0]
    if ate <= desde:
        return [], ate
    pend = conn.execute(
        'SELECT tabela, uid, MAX(seq) s FROM sync_changes '
        'WHERE seq>? AND seq<=? GROUP BY tabela, uid', (desde, ate)).fetchall()
    pend = sorted((p for p in pend if p['tabela'] in DEF),
                  key=lambda p: (ORDEM[p['tabela']], p['s']))
    regs = []
    for p in pend:
        r = _registro(conn, p['tabela'], p['uid'])
        if r:
            regs.append(r)
    return regs, ate


# ── aplicação ───────────────────────────────────────────────────────

def _ap_del(conn, t, uid, em):
    cur = conn.execute(f'DELETE FROM {t} WHERE uid=?', (uid,))
    if cur.rowcount == 0 and not conn.execute(
            'SELECT 1 FROM sync_tombstones WHERE tabela=? AND uid=?',
            (t, uid)).fetchone():
        conn.execute('INSERT INTO sync_tombstones VALUES(?,?,?)',
                     (t, uid, em or agora()))
        conn.execute("INSERT INTO sync_changes(tabela,uid,op) "
                     "VALUES(?,?,'d')", (t, uid))


def _ap_upd(conn, t, d, user_id):
    cols, refs = DEF[t]
    uid = str(d.get('uid') or '')[:64]
    ts = str(d.get('updated_at') or '')
    if not uid or not ts:
        return
    if conn.execute('SELECT 1 FROM sync_tombstones WHERE tabela=? AND uid=?',
                    (t, uid)).fetchone():
        return                                  # excluído: exclusão vence
    valores = {c: d.get(c) for c in cols}
    for col, tab in refs.items():
        valores[col] = _id_de(conn, tab, d.get(col))
    row = conn.execute(f'SELECT updated_at FROM {t} WHERE uid=?',
                       (uid,)).fetchone()
    if row:
        if ts <= (row[0] or ''):
            return                              # local igual/mais novo
        sets = ', '.join(f'{c}=?' for c in valores)
        conn.execute(f'UPDATE {t} SET {sets}, updated_at=? WHERE uid=?',
                     [*valores.values(), ts, uid])
        return
    nomes = ['uid', 'updated_at', 'user_id'] + list(valores)
    args = [uid, ts, user_id] + list(valores.values())
    try:
        conn.execute(f'INSERT INTO {t} ({", ".join(nomes)}) '
                     f'VALUES ({", ".join("?" * len(nomes))})', args)
    except sqlite3.IntegrityError:
        nk = NATURAL.get(t)
        if not nk:
            raise
        onde = ' AND '.join(f'{c}=?' for c in nk) + ' AND user_id=?'
        ex = conn.execute(f'SELECT id, updated_at FROM {t} WHERE {onde}',
                          [valores[c] for c in nk] + [user_id]).fetchone()
        if not ex:
            raise
        if ts > (ex['updated_at'] or ''):
            sets = ', '.join(f'{c}=?' for c in valores)
            conn.execute(
                f'UPDATE {t} SET uid=?, {sets}, updated_at=? WHERE id=?',
                [uid, *valores.values(), ts, ex['id']])
        else:
            conn.execute(f'UPDATE {t} SET uid=? WHERE id=?', (uid, ex['id']))


def aplicar(conn, registros):
    """Aplica registros vindos de um peer. Levanta exceção em caso de erro
    (nada é gravado nesse caso)."""
    r = conn.execute('SELECT id FROM users ORDER BY id LIMIT 1').fetchone()
    if not r:
        raise RuntimeError('Banco sem usuário')
    user_id = r['id']
    try:
        for reg in registros:
            t = reg.get('t')
            if t not in DEF:
                continue
            if reg.get('op') == 'd':
                _ap_del(conn, t, str(reg.get('uid') or '')[:64],
                        reg.get('em'))
            else:
                _ap_upd(conn, t, reg.get('d') or {}, user_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(registros)

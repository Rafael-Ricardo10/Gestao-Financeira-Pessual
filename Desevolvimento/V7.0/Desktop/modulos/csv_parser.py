#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csv_parser.py - leitura de extratos bancários em CSV (qualquer banco)

Em vez de um modelo por banco, o leitor descobre sozinho:
  * a codificação do arquivo (UTF-8, Windows-1252, Latin-1, UTF-16);
  * o separador (; , tab |);
  * a linha de cabeçalho (ignora textos antes e depois da tabela);
  * as colunas de data, descrição e valor (ou crédito/débito separados,
    ou coluna D/C), pelo NOME do cabeçalho; sem cabeçalho, pelo CONTEÚDO;
  * o formato da data (dd/mm/aaaa, aaaa-mm-dd, dd/mm/aa, dd mmm aaaa...)
    e do número (1.234,56 | 1,234.56 | -12,50 | (12,50) | 12,50 D | R$ 5).

Devolve o mesmo formato de processar_pdf_extrato():
    (sucesso, [transação, ...], mensagem)
onde cada transação é um dict com: data (AAAA-MM-DD), descricao,
tipo ('entrada'|'saida'), valor (positivo), hash, duplicada,
duplicata_tipo, duplicata_descricao e bloco_original (linha original).
"""
import csv
import io
import re
import hashlib
import unicodedata
from collections import Counter
from datetime import date

try:                                   # mesmo hash do PDF = mesma detecção
    from modulos.pdf_parser import gerar_hash_transacao
except Exception:                      # pdfplumber ausente, etc.
    def gerar_hash_transacao(tipo, valor, data, descricao):
        base = f'{tipo}|{float(valor):.2f}|{data}|{(descricao or "").strip().lower()}'
        return hashlib.md5(base.encode('utf-8')).hexdigest()

TAM_MAX = 25 * 1024 * 1024

MESES = {'jan': 1, 'fev': 2, 'feb': 2, 'mar': 3, 'abr': 4, 'apr': 4,
         'mai': 5, 'may': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'aug': 8,
         'set': 9, 'sep': 9, 'out': 10, 'oct': 10, 'nov': 11, 'dez': 12,
         'dec': 12}

T_DATA = {'data', 'date', 'dt', 'datahora', 'dia'}
T_DESC = {'descricao', 'historico', 'memo', 'title', 'titulo', 'description',
          'estabelecimento', 'detalhe', 'detalhes', 'favorecido', 'name',
          'nome', 'beneficiario', 'lancamento', 'complemento', 'movimento',
          'transacao', 'operacao'}
T_VALOR = {'valor', 'amount', 'value', 'quantia', 'montante'}
T_CRED = {'credito', 'credit', 'entrada', 'entradas', 'creditos'}
T_DEB = {'debito', 'debit', 'saida', 'saidas', 'debitos'}
T_TIPO = {'tipo', 'type', 'natureza', 'dc', 'cd', 'sinal'}
T_EXCLUI = {'saldo', 'balance', 'partial', 'parcial', 'limite', 'tarifa',
            'taxa', 'documento', 'doc', 'id', 'identificador', 'reference',
            'referencia', 'agencia', 'conta', 'categoria', 'category'}
VAL_CRED = {'c', 'cr', 'credito', 'credit', 'entrada'}
VAL_DEB = {'d', 'db', 'debito', 'debit', 'saida'}


# ── utilidades de texto ─────────────────────────────────────────────

def _sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')


def _norm(s):
    s = _sem_acento(str(s or '')).lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def _tokens(s):
    return set(_norm(s).split())


def decodificar(dados):
    if dados[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return dados.decode('utf-16')
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            pass
    return dados.decode('latin-1', errors='replace')


def detectar_separador(texto):
    linhas = [l for l in texto.splitlines() if l.strip()][:60]
    melhor, nota = ';', -1
    for sep in (';', ',', '\t', '|'):
        try:
            cols = [len(r) for r in csv.reader(linhas, delimiter=sep)]
        except csv.Error:
            continue
        comum, qtd = Counter(c for c in cols if c >= 2).most_common(1)[0] \
            if any(c >= 2 for c in cols) else (0, 0)
        if qtd * comum > nota:
            melhor, nota = sep, qtd * comum
    return melhor


# ── números e datas ─────────────────────────────────────────────────

def parse_valor(s):
    """'1.234,56' | '-12,50' | '(12,50)' | 'R$ 5,00' | '12,50 D' -> float
    (com sinal) ou None. Sufixo/prefixo D e '-' final = negativo."""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    neg = False
    baixo = _sem_acento(t).lower()
    if t.startswith('(') and t.endswith(')'):
        neg, t = True, t[1:-1]
    m = re.search(r'(?<![a-z])(d|db|deb|debito)\s*$|^\s*(d|db)(?![a-z])',
                  baixo)
    if m:
        neg = True
    t = re.sub(r'(?i)\b(r\$|brl|usd|us\$|eur)\b|r\$|[a-z]', '', t)
    t = t.replace(' ', '').replace('\u00a0', '')
    if t.endswith('-'):
        neg, t = True, t[:-1]
    if t.startswith('-'):
        neg, t = True, t[1:]
    elif t.startswith('+'):
        t = t[1:]
    if not re.fullmatch(r'[0-9.,]+', t or 'x'):
        return None
    if ',' in t and '.' in t:
        dec = ',' if t.rfind(',') > t.rfind('.') else '.'
        mil = '.' if dec == ',' else ','
        t = t.replace(mil, '').replace(dec, '.')
    elif ',' in t:
        partes = t.split(',')
        if len(partes) > 2:                       # 1,234,567
            t = t.replace(',', '')
        else:
            t = t.replace(',', '.')
    elif '.' in t:
        partes = t.split('.')
        if len(partes) > 2 or (len(partes[-1]) == 3 and len(partes) == 2):
            t = t.replace('.', '')                # 1.234 / 1.234.567
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _ano4(a):
    a = int(a)
    return a + 2000 if a < 100 else a


def _valida(a, m, d):
    try:
        return date(a, m, d).isoformat()
    except ValueError:
        return None


def parse_data(s, mdy=False):
    """Devolve 'AAAA-MM-DD' ou None."""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    m = re.match(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', t)
    if m:
        return _valida(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})(?!\d)', t)
    if m:
        a, b, ano = int(m[1]), int(m[2]), _ano4(m[3])
        d, mes = (b, a) if mdy else (a, b)
        return _valida(ano, mes, d)
    m = re.match(r'^(\d{1,2})\s*(?:de\s+)?([A-Za-zçÇ]{3,})\.?\s*(?:de\s+)?'
                 r'(\d{2}|\d{4})(?!\d)', _sem_acento(t))
    if m and m[2][:3].lower() in MESES:
        return _valida(_ano4(m[3]), MESES[m[2][:3].lower()], int(m[1]))
    return None


def _detectar_mdy(textos):
    """True se o arquivo usa mm/dd/aaaa (algum 'segundo campo' > 12 e
    nenhum 'primeiro campo' > 12)."""
    prim_grande = seg_grande = False
    for t in textos:
        m = re.match(r'^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}', str(t))
        if m:
            prim_grande |= int(m[1]) > 12
            seg_grande |= int(m[2]) > 12
    return seg_grande and not prim_grande


# ── estrutura do arquivo ────────────────────────────────────────────

def _achar_cabecalho(linhas):
    for i, row in enumerate(linhas[:80]):
        toks = [_tokens(c) for c in row]
        tem_data = any(t & T_DATA and not t & {'vencimento'} for t in toks)
        tem_val = any((t & (T_VALOR | T_CRED | T_DEB)) and not t & T_EXCLUI
                      for t in toks)
        if tem_data and tem_val:
            return i
    return None


def _mapear(cab, corpo):
    """Descobre as colunas a partir do nome do cabeçalho."""
    toks = [_tokens(c) for c in cab]
    ok = lambda t: not (t & T_EXCLUI)
    mp = {'data': None, 'desc': [], 'valor': None, 'cred': None,
          'deb': None, 'tipo': None}
    for i, t in enumerate(toks):
        if mp['data'] is None and t & T_DATA and ok(t) \
                and 'vencimento' not in t:
            mp['data'] = i
    for i, t in enumerate(toks):
        if i == mp['data'] or not t:
            continue
        if mp['valor'] is None and t & T_VALOR and ok(t):
            mp['valor'] = i
        elif mp['cred'] is None and t & T_CRED and ok(t) \
                and not t & T_VALOR:
            mp['cred'] = i
        elif mp['deb'] is None and t & T_DEB and ok(t) \
                and not t & T_VALOR:
            mp['deb'] = i
        elif t & T_DESC and ok(t) and not t & T_DATA:
            mp['desc'].append(i)
    # coluna D/C: só vale se os VALORES forem mesmo débito/crédito
    for i, t in enumerate(toks):
        junto = _norm(cab[i]).replace(' ', '')          # 'D/C' -> 'dc'
        if (t & T_TIPO or junto in T_TIPO) \
                and i not in (mp['data'], mp['valor']):
            vals = {_norm(r[i]) for r in corpo[:200]
                    if i < len(r) and r[i].strip()}
            if vals and vals <= (VAL_CRED | VAL_DEB):
                mp['tipo'] = i
                break
    if not mp['desc']:                       # 'type'/'tipo' como descrição
        for i, t in enumerate(toks):
            if t & T_TIPO and i != mp['tipo'] and ok(t):
                mp['desc'].append(i)
                break
    mp['desc'] = mp['desc'][:3]
    return mp


def _mapear_por_conteudo(corpo):
    """Sem cabeçalho: classifica as colunas olhando os dados."""
    amostra = corpo[:60]
    largura = max((len(r) for r in amostra), default=0)
    col_data, melhor = None, 0.0
    for i in range(largura):
        cel = [r[i] for r in amostra if i < len(r) and r[i].strip()]
        if not cel:
            continue
        taxa = sum(parse_data(c) is not None for c in cel) / len(cel)
        if taxa > melhor and taxa >= 0.6:
            col_data, melhor = i, taxa
    col_val, textos = None, []
    for i in range(largura):
        if i == col_data:
            continue
        cel = [r[i] for r in amostra if i < len(r) and r[i].strip()]
        if not cel:
            continue
        num = sum(parse_valor(c) is not None for c in cel) / len(cel)
        if num >= 0.7 and col_val is None:
            col_val = i
        elif num < 0.3:
            textos.append((sum(len(c) for c in cel) / len(cel), i))
    textos.sort(reverse=True)
    return {'data': col_data, 'desc': [i for _, i in textos[:2]],
            'valor': col_val, 'cred': None, 'deb': None, 'tipo': None}


_SALDO = re.compile(
    r'^(saldo|sdo)\b|saldo (anterior|do dia|final|inicial|parcial|'
    r'disponivel|total|em conta)|^total\b')


# ── leitura principal ───────────────────────────────────────────────

def processar_csv_extrato(dados, inverter=False):
    """dados: bytes do arquivo. inverter: troca entrada/saída (útil p/
    fatura de cartão em que compra aparece positiva).
    Retorna (sucesso, transacoes, mensagem)."""
    try:
        if not dados:
            return False, [], 'Arquivo vazio.'
        if len(dados) > TAM_MAX:
            return False, [], 'Arquivo grande demais (limite de 25 MB).'
        texto = decodificar(dados)
        sep = detectar_separador(texto)
        linhas = [r for r in csv.reader(io.StringIO(texto), delimiter=sep)
                  if any(c.strip() for c in r)]
        if len(linhas) < 2:
            return False, [], 'Não encontrei linhas de dados no arquivo.'

        i_cab = _achar_cabecalho(linhas)
        if i_cab is not None:
            cab, corpo = linhas[i_cab], linhas[i_cab + 1:]
            mp = _mapear(cab, corpo)
            rotulos = {k: (cab[v] if isinstance(v, int) and v < len(cab)
                           else None) for k, v in mp.items()
                       if k != 'desc'}
        else:
            corpo = linhas
            mp = _mapear_por_conteudo(corpo)
            rotulos = {}

        sem_valor = (mp['valor'] is None and mp['cred'] is None
                     and mp['deb'] is None)
        if mp['data'] is None or sem_valor:
            achou = ', '.join(c for c in (linhas[i_cab] if i_cab is not None
                                          else linhas[0])[:8])
            return False, [], (
                'Não consegui identificar as colunas de data e valor. '
                f'Colunas encontradas: {achou[:150]}. Se o arquivo é de '
                'um banco que ainda não funciona, envie uma amostra ao '
                'desenvolvedor (apague nomes e números de conta).')

        # fatura de cartão estilo "date,category,title,amount":
        # compra aparece como valor POSITIVO
        cartao = False
        if i_cab is not None:
            tk = set().union(*[_tokens(c) for c in linhas[i_cab]])
            cartao = {'title', 'category', 'amount'} <= tk
        inv = bool(inverter) != cartao

        col_data = mp['data']
        mdy = _detectar_mdy([r[col_data] for r in corpo
                             if col_data < len(r)])
        txs, ignoradas = [], 0
        for r in corpo:
            def cel(i):
                return r[i].strip() if i is not None and i < len(r) else ''
            data = parse_data(cel(col_data), mdy)
            if not data:
                continue                       # rodapé, total, lixo
            desc = ' - '.join(dict.fromkeys(
                cel(i) for i in mp['desc'] if cel(i)))
            desc = re.sub(r'\s+', ' ', desc).strip()[:200]
            if _SALDO.search(_norm(desc)):
                continue                       # linhas de saldo

            val = None
            if mp['valor'] is not None:
                val = parse_valor(cel(mp['valor']))
            if val is None and (mp['cred'] is not None
                                or mp['deb'] is not None):
                c = parse_valor(cel(mp['cred'])) or 0.0
                d = parse_valor(cel(mp['deb'])) or 0.0
                if c or d:
                    val = abs(c) - abs(d)
            if val is None or abs(val) < 0.005:
                ignoradas += 1
                continue
            if mp['tipo'] is not None and val > 0:
                if _norm(cel(mp['tipo'])) in VAL_DEB:
                    val = -val
            tipo = 'entrada' if val > 0 else 'saida'
            if inv:
                tipo = 'saida' if tipo == 'entrada' else 'entrada'
            valor = round(abs(val), 2)
            if not desc:
                desc = f'Transacao {len(txs) + 1}'
            txs.append({
                'data': data, 'descricao': desc, 'tipo': tipo,
                'valor': valor,
                'hash': gerar_hash_transacao(tipo, valor, data, desc),
                'duplicada': False, 'duplicata_tipo': None,
                'duplicata_descricao': None,
                'bloco_original': sep.join(r)[:400],
            })

        if not txs:
            return False, [], ('Nenhuma transação válida encontrada '
                               '(verifique datas e valores).')
        msg = f'{len(txs)} transações lidas do CSV'
        if cartao:
            msg += ' (fatura de cartão: valores positivos tratados como saída)'
        if mdy:
            msg += ' (datas no formato mm/dd/aaaa)'
        if ignoradas:
            msg += f'; {ignoradas} linha(s) sem valor ignorada(s)'
        return True, txs, msg + '.'
    except Exception as e:                     # nunca derruba a interface
        return False, [], f'Erro ao ler o CSV: {e}'

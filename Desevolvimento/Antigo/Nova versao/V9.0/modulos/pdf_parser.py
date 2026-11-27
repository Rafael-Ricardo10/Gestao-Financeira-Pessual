"""
Parser de extratos bancários em PDF
Suporta 3 formatos de transação
"""

import re
import io
import hashlib
from datetime import datetime
from modulos.logs import registrar_log

try:
    import pdfplumber
    PDF_PLUMBER = True
except ImportError:
    PDF_PLUMBER = False
    registrar_log("pdf_parser", "pdfplumber não instalado.", "WARNING")

try:
    from PIL import Image
    import pytesseract
    OCR_DISPONIVEL = True
except ImportError:
    OCR_DISPONIVEL = False

# ==================== PADRÕES ====================

PADRAO_VALOR_COM_SINAL = re.compile(
    r'(?<!\d)([+\-])\s*R\$\s*([\d]{1,3}(?:\.[\d]{3})*,\d{2}|[\d]+,\d{2})'
)

PADRAO_DATA_INICIO = re.compile(r'^(\d{2}/\d{2}/\d{4})')

PADROES_DATA = [
    re.compile(r'(\d{2}/\d{2}/\d{4})'),
    re.compile(r'(\d{2}/\d{2}/\d{2})'),
    re.compile(r'(\d{4}-\d{2}-\d{2})'),
    re.compile(r'(\d{2}-\d{2}-\d{4})'),
]

PADROES_LIXO = [
    re.compile(r'^Saldo\s+(Anterior|do\s+dia|em\s+conta|bloqueado)', re.IGNORECASE),
    re.compile(r'^Lançamento\s+a\s+conferir', re.IGNORECASE),
    re.compile(r'^Lançamentos\s+futuros', re.IGNORECASE),
    re.compile(r'^Bloqueio\s+judicial', re.IGNORECASE),
    re.compile(r'^Não\s+está\s+previsto', re.IGNORECASE),
    re.compile(r'^Movimentações\s+de\s+\d{2}/\d{2}/\d{4}', re.IGNORECASE),
    re.compile(r'^Momento\s+de\s+emissão', re.IGNORECASE),
    re.compile(r'^Período\s+das\s+movimentações', re.IGNORECASE),
    re.compile(r'^Extrato\s+de\s+conta', re.IGNORECASE),
    re.compile(r'^Titular\s*-\s*CPF', re.IGNORECASE),
    re.compile(r'^Dados\s+da\s+conta', re.IGNORECASE),
    re.compile(r'^Data\s+Descrição\s+Valor', re.IGNORECASE),
    re.compile(r'^Cheque\s+especial', re.IGNORECASE),
    re.compile(r'^Este\s+produto\s+não\s+está\s+contratado', re.IGNORECASE),
    re.compile(r'^Fim\s+dess[ae]\s+extrato', re.IGNORECASE),
    re.compile(r'^Central\s+de\s+atendimento', re.IGNORECASE),
    re.compile(r'SAC|Ouvidoria', re.IGNORECASE),
    re.compile(r'0800\s*\d{3}', re.IGNORECASE),
    re.compile(r'@.*\.com\.br', re.IGNORECASE),
    re.compile(r'^\s*R\$\s*[\d.,]+\s*(R\$\s*[\d.,]+)?\s*$'),
    re.compile(r'^Cooperativa\s*:', re.IGNORECASE),
    re.compile(r'^Conta\s*:', re.IGNORECASE),
]

# ==================== FUNÇÕES AUXILIARES ====================

def _normalizar_valor(valor_str):
    valor_str = re.sub(r'[R$\s]', '', valor_str).strip()
    if ',' in valor_str and '.' in valor_str:
        valor_str = valor_str.replace('.', '').replace(',', '.')
    elif ',' in valor_str:
        valor_str = valor_str.replace(',', '.')
    try:
        return abs(float(valor_str))
    except ValueError:
        return 0.0


def _normalizar_data(data_str):
    formatos = ['%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y']
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return datetime.now().strftime('%Y-%m-%d')


def gerar_hash_transacao(tipo, valor, data, descricao):
    conteudo = f"{tipo}|{valor:.2f}|{data}|{descricao[:30].lower().strip()}"
    return hashlib.md5(conteudo.encode()).hexdigest()


def gerar_hash_fuzzy(tipo, valor, data):
    conteudo = f"{tipo}|{valor:.2f}|{data}"
    return hashlib.md5(conteudo.encode()).hexdigest()


def _chave_dedup(tipo, valor, data, nome):
    return gerar_hash_transacao(tipo, valor, data, nome)


def _eh_lixo(linha):
    for padrao in PADROES_LIXO:
        if padrao.search(linha):
            return True
    return False


# ==================== EXTRAÇÃO ====================

def _extrair_linhas_pdf(arquivo_bytes):
    linhas = []

    if PDF_PLUMBER:
        try:
            with pdfplumber.open(io.BytesIO(arquivo_bytes)) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if texto:
                        for linha in texto.split('\n'):
                            linha = linha.strip()
                            if linha:
                                linhas.append(linha)
        except Exception as e:
            registrar_log("pdf_parser", f"Erro pdfplumber: {str(e)}", "ERROR")

    if not linhas and OCR_DISPONIVEL:
        try:
            import pdf2image
            imagens = pdf2image.convert_from_bytes(arquivo_bytes, dpi=200)
            for img in imagens:
                texto = pytesseract.image_to_string(img, lang='por+eng')
                for linha in texto.split('\n'):
                    linha = linha.strip()
                    if linha:
                        linhas.append(linha)
        except Exception as e:
            registrar_log("pdf_parser", f"Erro OCR: {str(e)}", "ERROR")

    registrar_log("pdf_parser", f"Linhas brutas: {len(linhas)}")
    return linhas


# ==================== AGRUPAMENTO ====================

def _agrupar_em_blocos(linhas):
    """
    Agrupa linhas em blocos de transação.

    FORMATOS SUPORTADOS:

    FORMATO 1 - Tudo em uma linha:
        22/04/2026 CARTAO DEBITO - THAYSE MAFFEI - R$ 54,60

    FORMATO 2 - Descrição quebrada após a data:
        01/04/2025 RECEBIMENTO PIX - JOAQUINA
        REPRESENTACOES COMERCIAIS LTDA
        + R$ 1.000,00

    FORMATO 3 - Descrição ANTES da data+valor (NOVO!):
        RECEBIMENTO PIX - 04394558000150 JOAQUINA REPRESENTACOES
        COMERCIAIS LTDA
        01/04/2025 + R$ 1.000,00
    """
    blocos = []
    bloco_atual = []
    desc_pendente = []  # Armazena descrições que podem vir antes da data

    for i, linha in enumerate(linhas):
        # Ignorar lixo
        if _eh_lixo(linha):
            # Salvar bloco atual se válido
            if bloco_atual:
                texto = ' '.join(bloco_atual)
                if PADRAO_VALOR_COM_SINAL.search(texto):
                    blocos.append(texto)
                    registrar_log("pdf_parser", f"BLOCO SALVO: {texto[:80]}")
                bloco_atual = []

            # Descartar descrições pendentes
            if desc_pendente:
                registrar_log("pdf_parser", f"DESC PENDENTE DESCARTADA (lixo): {' '.join(desc_pendente)[:60]}", "DEBUG")
                desc_pendente = []

            registrar_log("pdf_parser", f"LIXO [{i+1}]: {linha[:70]}", "DEBUG")
            continue

        tem_data_inicio = bool(PADRAO_DATA_INICIO.match(linha))
        tem_sinal_valor = bool(PADRAO_VALOR_COM_SINAL.search(linha))

        # ===== CASO 1: Linha começa com DATA =====
        if tem_data_inicio:

            # 1A) Data + Valor completo
            if tem_sinal_valor:
                # Salvar bloco anterior
                if bloco_atual:
                    texto = ' '.join(bloco_atual)
                    if PADRAO_VALOR_COM_SINAL.search(texto):
                        blocos.append(texto)
                        registrar_log("pdf_parser", f"BLOCO ANTERIOR: {texto[:80]}")
                    bloco_atual = []

                # Juntar descrição pendente + linha atual (FORMATO 3)
                if desc_pendente:
                    bloco_completo = ' '.join(desc_pendente + [linha])
                    blocos.append(bloco_completo)
                    registrar_log("pdf_parser", f"FORMATO 3: {bloco_completo[:80]}")
                    desc_pendente = []

                # Sem descrição pendente, é FORMATO 1 (tudo em uma linha)
                else:
                    blocos.append(linha)
                    registrar_log("pdf_parser", f"FORMATO 1: {linha[:80]}")

            # 1B) Data sem valor (início de FORMATO 2)
            else:
                # Salvar bloco anterior
                if bloco_atual:
                    texto = ' '.join(bloco_atual)
                    if PADRAO_VALOR_COM_SINAL.search(texto):
                        blocos.append(texto)
                        registrar_log("pdf_parser", f"BLOCO ANTERIOR: {texto[:80]}")
                    bloco_atual = []

                # Descartar descrição pendente (não era FORMATO 3)
                if desc_pendente:
                    registrar_log("pdf_parser", f"DESC PENDENTE DESCARTADA: {' '.join(desc_pendente)[:60]}", "WARNING")
                    desc_pendente = []

                # Iniciar novo bloco (FORMATO 2)
                bloco_atual = [linha]
                registrar_log("pdf_parser", f"INICIO FORMATO 2: {linha[:70]}", "DEBUG")

        # ===== CASO 2: Linha SEM data mas COM sinal+valor =====
        elif tem_sinal_valor:

            # Adicionar descrição pendente ao bloco
            if desc_pendente:
                bloco_atual.extend(desc_pendente)
                desc_pendente = []

            # Adicionar valor e fechar
            bloco_atual.append(linha)
            texto = ' '.join(bloco_atual)
            blocos.append(texto)
            registrar_log("pdf_parser", f"FORMATO 2 FECHADO: {texto[:80]}")
            bloco_atual = []

        # ===== CASO 3: Linha sem data e sem valor (descrição) =====
        else:
            # Se há bloco aberto, é continuação (FORMATO 2)
            if bloco_atual:
                bloco_atual.append(linha)
                registrar_log("pdf_parser", f"CONTINUACAO: {linha[:70]}", "DEBUG")

            # Se não há bloco, pode ser início de FORMATO 3 (descrição antes da data)
            else:
                # Só aceitar como descrição pendente se tiver conteúdo útil
                if len(linha) > 5 and not linha.isdigit():
                    desc_pendente.append(linha)
                    registrar_log("pdf_parser", f"DESC PENDENTE: {linha[:70]}", "DEBUG")
                else:
                    registrar_log("pdf_parser", f"LINHA SOLTA IGNORADA: {linha[:70]}", "DEBUG")

    # Último bloco pendente
    if bloco_atual:
        texto = ' '.join(bloco_atual)
        if PADRAO_VALOR_COM_SINAL.search(texto):
            blocos.append(texto)
            registrar_log("pdf_parser", f"ULTIMO BLOCO: {texto[:80]}")

    # Descrição pendente não fechada (ignorar)
    if desc_pendente:
        registrar_log("pdf_parser", f"DESC PENDENTE FINAL DESCARTADA: {' '.join(desc_pendente)[:60]}", "WARNING")

    registrar_log("pdf_parser", f"Total de blocos: {len(blocos)}")

    for idx, b in enumerate(blocos, 1):
        registrar_log("pdf_parser", f"BLOCO #{idx}: {b[:120]}")

    return blocos


# ==================== EXTRAÇÃO DE DESCRIÇÃO ====================

def _extrair_descricao(bloco):
    """
    Extrai descrição removendo data e valor.
    Corrigido para lidar com '+ R$' ou '- R$' precedidos de espaço.
    """
    desc = bloco

    # 1. Remover data do início
    desc = PADRAO_DATA_INICIO.sub('', desc).strip()

    # 2. Remover qualquer data no meio
    for padrao in PADROES_DATA:
        desc = padrao.sub('', desc)

    # 3. Remover sinal + valor (ex: "+ R$ 255,00" ou "- R$ 1.000,00")
    desc = PADRAO_VALOR_COM_SINAL.sub('', desc)

    # 4. Remover R$ solto que possa ter sobrado
    desc = re.sub(r'R\$\s*[\d.,]*', '', desc)

    # 5. Remover sinais soltos que sobraram no final ou início
    desc = re.sub(r'\s+[+\-]\s*$', '', desc)
    desc = re.sub(r'^\s*[+\-]\s+', '', desc)

    # 6. Limpar espaços duplos
    desc = re.sub(r'\s{2,}', ' ', desc).strip()

    # 7. Remover pontuação no início/fim
    desc = desc.strip('.,;:- ')

    # 8. Limpar novamente
    desc = re.sub(r'\s{2,}', ' ', desc).strip()

    return desc

# ==================== PARSING ====================

def _parsear_blocos(blocos):
    transacoes = []
    chaves_vistas = set()

    for idx, bloco in enumerate(blocos, 1):
        if not bloco.strip():
            continue

        # ── Tentar encontrar sinal+valor ─────────────────────
        # Busca TODAS as ocorrências e pega a última
        # (evita pegar datas como "19/02/2025" confundindo com sinal)
        matches = list(PADRAO_VALOR_COM_SINAL.finditer(bloco))

        if not matches:
            registrar_log(
                "pdf_parser",
                f"BLOCO #{idx} sem sinal: {bloco[:80]}",
                "WARNING"
            )
            continue

        # Usar a ÚLTIMA ocorrência (o valor real da transação)
        match     = matches[-1]
        sinal     = match.group(1)
        valor_str = match.group(2)
        valor     = _normalizar_valor(valor_str)

        if valor <= 0:
            continue

        tipo = 'entrada' if sinal == '+' else 'saida'

        # ── Extrair data ──────────────────────────────────────
        data = datetime.now().strftime('%Y-%m-%d')
        for padrao in PADROES_DATA:
            m = padrao.search(bloco)
            if m:
                data = _normalizar_data(m.group(1))
                break

        # ── Extrair descrição ─────────────────────────────────
        descricao = _extrair_descricao(bloco)

        if not descricao or len(descricao) < 3:
            descricao = 'Transação importada'
            registrar_log(
                "pdf_parser",
                f"AVISO: descrição vazia - BLOCO: {bloco[:100]}",
                "WARNING"
            )

        if len(descricao) > 200:
            descricao = descricao[:200].strip()

        # ── Deduplicação ──────────────────────────────────────
        chave = _chave_dedup(tipo, valor, data, descricao)
        if chave in chaves_vistas:
            registrar_log(
                "pdf_parser",
                f"DUPLICATA: {descricao[:50]}",
                "DEBUG"
            )
            continue
        chaves_vistas.add(chave)

        registrar_log(
            "pdf_parser",
            f"OK [{idx}] {data} | {tipo.upper():7} | "
            f"R$ {valor:>8.2f} | {descricao[:55]}"
        )

        transacoes.append({
            "descricao":      descricao,
            "nome_fantasia":  descricao,
            "tipo":           tipo,
            "valor":          round(valor, 2),
            "data":           data,
            "hash":           chave,
            "bloco_original": bloco[:300],
            "origem":         "importacao_pdf"
        })

    return transacoes


# ==================== FUNÇÃO PRINCIPAL ====================

def processar_pdf_extrato(arquivo_bytes):
    try:
        registrar_log("pdf_parser", "=" * 60)
        registrar_log("pdf_parser", "PROCESSAMENTO DE PDF")
        registrar_log("pdf_parser", "=" * 60)

        linhas     = _extrair_linhas_pdf(arquivo_bytes)
        blocos     = _agrupar_em_blocos(linhas)
        transacoes = _parsear_blocos(blocos)

        if not transacoes:
            return False, [], "Nenhuma transação encontrada com sinal +/-"

        entradas      = sum(1 for t in transacoes if t['tipo'] == 'entrada')
        saidas        = sum(1 for t in transacoes if t['tipo'] == 'saida')
        total_entrada = sum(t['valor'] for t in transacoes if t['tipo'] == 'entrada')
        total_saida   = sum(t['valor'] for t in transacoes if t['tipo'] == 'saida')

        mensagem = (
            f"{len(transacoes)} transações extraídas\n\n"
            f"Entradas: {entradas}x → R$ {total_entrada:,.2f}\n"
            f"Saídas  : {saidas}x  → R$ {total_saida:,.2f}\n"
            f"Saldo   : R$ {(total_entrada - total_saida):,.2f}"
        )

        registrar_log("pdf_parser", mensagem.replace('\n', ' | '))
        registrar_log("pdf_parser", "=" * 60)

        return True, transacoes, mensagem

    except Exception as e:
        import traceback
        registrar_log("pdf_parser", f"ERRO: {str(e)}", "ERROR")
        registrar_log("pdf_parser", traceback.format_exc(), "ERROR")
        return False, [], f"Erro: {str(e)}"


# ==================== COMPATIBILIDADE ====================

def _parsear_linhas(linhas):
    blocos = _agrupar_em_blocos(linhas)
    return _parsear_blocos(blocos)


def _determinar_tipo(linha):
    m = PADRAO_VALOR_COM_SINAL.search(linha)
    if m:
        return 'entrada' if m.group(1) == '+' else 'saida'
    return 'saida'

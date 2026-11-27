"""
Parser de extratos bancários em PDF
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
    registrar_log("pdf_parser", "pdfplumber não instalado. Use: pip install pdfplumber", "WARNING")

try:
    from PIL import Image
    import pytesseract
    OCR_DISPONIVEL = True
except ImportError:
    OCR_DISPONIVEL = False

# ==================== PADRÕES ====================

PADRAO_VALOR_COM_SINAL = re.compile(
    r'([+\-])\s*R?\$?\s*([\d]{1,3}(?:\.[\d]{3})*,\d{2}|[\d]+,\d{2})'
)

PADROES_DATA = [
    re.compile(r'(\d{2}/\d{2}/\d{4})'),
    re.compile(r'(\d{2}/\d{2}/\d{2})'),
    re.compile(r'(\d{4}-\d{2}-\d{2})'),
    re.compile(r'(\d{2}-\d{2}-\d{4})'),
]

# ==================== FUNÇÕES AUXILIARES ====================

def _normalizar_valor(valor_str: str) -> float:
    """Converte string de valor para float"""
    valor_str = re.sub(r'[R$\s]', '', valor_str).strip()
    if ',' in valor_str and '.' in valor_str:
        valor_str = valor_str.replace('.', '').replace(',', '.')
    elif ',' in valor_str:
        valor_str = valor_str.replace(',', '.')
    try:
        return abs(float(valor_str))
    except ValueError:
        return 0.0


def _normalizar_data(data_str: str) -> str:
    """Converte data para formato padrão YYYY-MM-DD"""
    formatos = ['%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y']
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return datetime.now().strftime('%Y-%m-%d')


def gerar_hash_transacao(tipo: str, valor: float, data: str, descricao: str) -> str:
    """
    Gera hash único para identificar transação e evitar duplicatas
    """
    conteudo = f"{tipo}|{valor:.2f}|{data}|{descricao[:30].lower().strip()}"
    return hashlib.md5(conteudo.encode()).hexdigest()


def _chave_dedup(tipo: str, valor: float, data: str, nome: str) -> str:
    """Alias para gerar_hash_transacao"""
    return gerar_hash_transacao(tipo, valor, data, nome)


# ==================== EXTRAÇÃO DE TEXTO ====================

def _extrair_texto_pdf(arquivo_bytes: bytes) -> list:
    """
    Extrai texto do PDF usando pdfplumber ou OCR
    """
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

    # OCR apenas se pdfplumber não extraiu nada
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

    registrar_log("pdf_parser", f"Total de linhas extraídas: {len(linhas)}")
    return linhas


# ==================== AGRUPAMENTO ====================

def _agrupar_em_transacoes(linhas: list) -> list:
    """
    Agrupa linhas em blocos de transação.
    - Transação começa com DATA
    - Termina quando aparece VALOR com sinal (+ ou -)
    - OU quando começa uma nova data
    """
    blocos = []
    bloco_atual = []

    for linha in linhas:
        tem_data = any(p.search(linha) for p in PADROES_DATA)
        tem_valor_sinal = bool(PADRAO_VALOR_COM_SINAL.search(linha))

        if tem_data:
            if bloco_atual:
                texto_bloco = ' '.join(bloco_atual)
                if PADRAO_VALOR_COM_SINAL.search(texto_bloco):
                    blocos.append(texto_bloco)
                bloco_atual = []

            bloco_atual.append(linha)

            if tem_valor_sinal:
                blocos.append(' '.join(bloco_atual))
                bloco_atual = []

        elif tem_valor_sinal:
            if bloco_atual:
                bloco_atual.append(linha)
                blocos.append(' '.join(bloco_atual))
                bloco_atual = []
            else:
                blocos.append(linha)
        else:
            if bloco_atual:
                bloco_atual.append(linha)

    # Último bloco pendente
    if bloco_atual:
        texto_bloco = ' '.join(bloco_atual)
        if PADRAO_VALOR_COM_SINAL.search(texto_bloco):
            blocos.append(texto_bloco)

    registrar_log("pdf_parser", f"Total de blocos agrupados: {len(blocos)}")
    return blocos


# ==================== EXTRAÇÃO DE DESCRIÇÃO ====================

def _extrair_nome(bloco: str) -> str:
    """
    Extrai o nome/descrição da transação do bloco
    """
    nome = bloco

    # 1. Remover todas as datas encontradas
    for padrao in PADROES_DATA:
        nome = padrao.sub('', nome)

    # 2. Remover valor com sinal
    nome = PADRAO_VALOR_COM_SINAL.sub('', nome)

    # 3. Remover R$ solto
    nome = re.sub(r'R\$', '', nome)

    # 4. Remover CNPJ formatado
    nome = re.sub(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', '', nome)

    # 5. Remover CPF formatado
    nome = re.sub(r'\d{3}\.\d{3}\.\d{3}-\d{2}', '', nome)

    # 6. Remover CNPJ sem formatação (14 dígitos)
    nome = re.sub(r'\b\d{14}\b', '', nome)

    # 7. Remover CPF sem formatação (11 dígitos)
    nome = re.sub(r'\b\d{11}\b', '', nome)

    # 8. Remover outros números longos (8+ dígitos)
    nome = re.sub(r'\b\d{8,}\b', '', nome)

    # 9. Limpar espaços extras
    nome = re.sub(r'\s{2,}', ' ', nome).strip()

    # 10. Remover pontuação solta
    nome = nome.strip('.,;:-')

    # 11. Remover hífen isolado
    nome = re.sub(r'\s+-\s+', ' ', nome)
    nome = re.sub(r'\s{2,}', ' ', nome).strip()

    return nome


# ==================== PARSING PRINCIPAL ====================

def _parsear_blocos(blocos: list) -> list:
    """
    Extrai transações dos blocos agrupados com deduplicação
    """
    transacoes = []
    chaves_vistas = set()

    for idx, bloco in enumerate(blocos):
        if not bloco.strip():
            continue

        match_sinal = PADRAO_VALOR_COM_SINAL.search(bloco)
        if not match_sinal:
            continue

        sinal = match_sinal.group(1)
        valor_str = match_sinal.group(2)
        valor = _normalizar_valor(valor_str)

        if valor <= 0:
            continue

        tipo = 'entrada' if sinal == '+' else 'saida'

        # Extrair data
        data_encontrada = datetime.now().strftime('%Y-%m-%d')
        for padrao in PADROES_DATA:
            m = padrao.search(bloco)
            if m:
                data_encontrada = _normalizar_data(m.group(1))
                break

        # Extrair nome/descrição
        nome = _extrair_nome(bloco)

        if len(nome) > 200:
            nome = nome[:200].strip()

        if not nome:
            nome = 'Transação importada'
            registrar_log(
                "pdf_parser",
                f"⚠️ Nome vazio no bloco #{idx+1}: {bloco[:100]}",
                "WARNING"
            )

        # Deduplicação
        chave = _chave_dedup(tipo, valor, data_encontrada, nome)
        if chave in chaves_vistas:
            registrar_log("pdf_parser", f"Duplicata ignorada: {nome[:50]}")
            continue
        chaves_vistas.add(chave)

        registrar_log(
            "pdf_parser",
            f"✓ [{idx+1}] {data_encontrada} | {tipo} | R${valor:.2f} | {nome[:50]}"
        )

        transacoes.append({
            "descricao": nome,
            "nome_fantasia": nome,
            "tipo": tipo,
            "valor": round(valor, 2),
            "data": data_encontrada,
            "hash": chave,
            "bloco_original": bloco[:300],
            "origem": "importacao_pdf"
        })

    return transacoes


# ==================== FUNÇÃO PRINCIPAL ====================

def processar_pdf_extrato(arquivo_bytes: bytes) -> tuple:
    """
    Processa PDF de extrato bancário.

    Regras:
    + R$ valor  → ENTRADA
    - R$ valor  → SAÍDA
    R$ valor    → IGNORADO (saldo sem sinal)

    Retorna: (sucesso: bool, transacoes: list, mensagem: str)
    """
    try:
        registrar_log("pdf_parser", "=" * 50)
        registrar_log("pdf_parser", "INICIANDO PROCESSAMENTO DE PDF")
        registrar_log("pdf_parser", "=" * 50)

        linhas = _extrair_texto_pdf(arquivo_bytes)

        if not linhas:
            return False, [], (
                "Não foi possível extrair texto do PDF.\n"
                "Verifique se não é um PDF protegido."
            )

        blocos = _agrupar_em_transacoes(linhas)
        transacoes = _parsear_blocos(blocos)

        if not transacoes:
            amostra = ' | '.join(linhas[:10])
            registrar_log(
                "pdf_parser",
                f"Nenhuma transação com +/- encontrada. Amostra: {amostra[:300]}",
                "WARNING"
            )
            return False, [], (
                "Nenhuma transação encontrada.\n"
                "O extrato deve conter valores precedidos de + ou -."
            )

        entradas = sum(1 for t in transacoes if t['tipo'] == 'entrada')
        saidas   = sum(1 for t in transacoes if t['tipo'] == 'saida')
        total_entrada = sum(t['valor'] for t in transacoes if t['tipo'] == 'entrada')
        total_saida   = sum(t['valor'] for t in transacoes if t['tipo'] == 'saida')

        mensagem = (
            f"{len(transacoes)} transações identificadas:\n"
            f"• {entradas} entradas (R$ {total_entrada:,.2f})\n"
            f"• {saidas} saídas (R$ {total_saida:,.2f})"
        )

        registrar_log("pdf_parser", mensagem.replace('\n', ' | '))
        registrar_log("pdf_parser", "=" * 50)

        return True, transacoes, mensagem

    except Exception as e:
        import traceback
        registrar_log("pdf_parser", f"❌ ERRO: {str(e)}", "ERROR")
        registrar_log("pdf_parser", traceback.format_exc(), "ERROR")
        return False, [], f"Erro ao processar PDF: {str(e)}"


# ==================== COMPATIBILIDADE ====================

def _parsear_linhas(linhas: list) -> list:
    """Compatibilidade com versões anteriores"""
    blocos = _agrupar_em_transacoes(linhas)
    return _parsear_blocos(blocos)


def _determinar_tipo(linha: str) -> str:
    """Compatibilidade com versões anteriores"""
    m = PADRAO_VALOR_COM_SINAL.search(linha)
    if m:
        return 'entrada' if m.group(1) == '+' else 'saida'
    return 'saida'

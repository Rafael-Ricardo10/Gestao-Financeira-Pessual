"""
Parser de extratos bancários em PDF - CORRIGIDO (sem duplicatas)
"""

import re
import io
import hashlib
from pathlib import Path
from datetime import datetime
from modulos.logs import registrar_log

try:
    import pdfplumber
    PDF_PLUMBER = True
except ImportError:
    PDF_PLUMBER = False

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


def _normalizar_valor(valor_str: str) -> float:
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
    formatos = ['%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y']
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return datetime.now().strftime('%Y-%m-%d')


def _extrair_texto_pdf(arquivo_bytes: bytes) -> list:
    """
    Extrai texto do PDF.
    IMPORTANTE: usa apenas extract_text(), NÃO usa extract_tables()
    para evitar que o mesmo conteúdo apareça duas vezes.
    """
    linhas = []

    if PDF_PLUMBER:
        try:
            with pdfplumber.open(io.BytesIO(arquivo_bytes)) as pdf:
                for pagina in pdf.pages:
                    # Usa APENAS extract_text - não mistura com extract_tables
                    # pois extract_tables extrai o mesmo conteúdo do texto
                    texto = pagina.extract_text()
                    if texto:
                        for linha in texto.split('\n'):
                            linha = linha.strip()
                            if linha:
                                linhas.append(linha)
        except Exception as e:
            registrar_log("pdf_parser", f"Erro pdfplumber: {str(e)}")

    # OCR apenas se não extraiu nada pelo pdfplumber
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
            registrar_log("pdf_parser", f"Erro OCR: {str(e)}")

    return linhas


def _agrupar_em_transacoes(linhas: list) -> list:
    """
    Agrupa linhas em blocos de transação.

    Lógica para extratos bancários:
    - Uma transação começa com uma DATA
    - Pode continuar em linhas seguintes (descrição longa)
    - Termina quando aparece o VALOR com sinal (+ ou -)
    - OU quando começa uma nova data

    Exemplo real:
      Linha 1: "15/04/2026 RECEBIMENTO PIX - 04394558000150 JOAQUINA"
      Linha 2: "COMERCIAIS LTDA"
      Linha 3: "+ R$ 1.000,00"
      → Agrupa tudo em 1 bloco
    """
    blocos = []
    bloco_atual = []

    for linha in linhas:
        tem_data = any(p.search(linha) for p in PADROES_DATA)
        tem_valor_sinal = bool(PADRAO_VALOR_COM_SINAL.search(linha))

        if tem_data:
            # Nova transação começa
            if bloco_atual:
                # Salva bloco anterior SE ainda não tinha valor
                # (significa que terminou sem valor = ignora)
                texto_bloco = ' '.join(bloco_atual)
                if PADRAO_VALOR_COM_SINAL.search(texto_bloco):
                    blocos.append(texto_bloco)
                bloco_atual = []
            bloco_atual.append(linha)

            # Se já tem valor na mesma linha, fecha o bloco imediatamente
            if tem_valor_sinal:
                blocos.append(' '.join(bloco_atual))
                bloco_atual = []

        elif tem_valor_sinal:
            # Linha com valor encerra o bloco atual
            if bloco_atual:
                bloco_atual.append(linha)
                blocos.append(' '.join(bloco_atual))
                bloco_atual = []
            else:
                # Valor sem bloco anterior (linha isolada com valor)
                blocos.append(linha)

        else:
            # Continuação da transação atual
            if bloco_atual:
                bloco_atual.append(linha)
            # Se não há bloco atual e não tem data nem valor = cabeçalho/rodapé, ignora

    # Último bloco pendente
    if bloco_atual:
        texto_bloco = ' '.join(bloco_atual)
        if PADRAO_VALOR_COM_SINAL.search(texto_bloco):
            blocos.append(texto_bloco)

    return blocos


def _chave_dedup(tipo: str, valor: float, data: str, nome: str) -> str:
    """
    Gera chave única para deduplicação.
    Usa tipo + valor + data + primeiros 30 chars do nome.
    """
    conteudo = f"{tipo}|{valor:.2f}|{data}|{nome[:30].lower().strip()}"
    return hashlib.md5(conteudo.encode()).hexdigest()


def _parsear_blocos(blocos: list) -> list:
    """
    Extrai transações dos blocos agrupados.
    Inclui deduplicação por hash para eliminar duplicatas.
    """
    transacoes = []
    chaves_vistas = set()  # Para deduplicação

    for bloco in blocos:
        if not bloco.strip():
            continue

        # Só processa se tem sinal + ou -
        match_sinal = PADRAO_VALOR_COM_SINAL.search(bloco)
        if not match_sinal:
            continue

        sinal = match_sinal.group(1)
        valor_str = match_sinal.group(2)
        valor = _normalizar_valor(valor_str)

        if valor <= 0:
            continue

        tipo = 'entrada' if sinal == '+' else 'saida'

        # Extrai data
        data_encontrada = datetime.now().strftime('%Y-%m-%d')
        for padrao in PADROES_DATA:
            m = padrao.search(bloco)
            if m:
                data_encontrada = _normalizar_data(m.group(1))
                break

        # Nome fantasia = remove data, valor e sinal do texto
        nome = bloco
        for padrao in PADROES_DATA:
            nome = padrao.sub('', nome)
        nome = PADRAO_VALOR_COM_SINAL.sub('', nome)
        nome = re.sub(r'R\$', '', nome)
        nome = re.sub(r'\s{2,}', ' ', nome).strip()
        if len(nome) > 80:
            nome = nome[:80].strip()
        if not nome:
            nome = 'Transação importada'

        # =============================================
        # DEDUPLICAÇÃO: ignora transação já vista
        # =============================================
        chave = _chave_dedup(tipo, valor, data_encontrada, nome)
        if chave in chaves_vistas:
            continue
        chaves_vistas.add(chave)

        transacoes.append({
            "tipo": tipo,
            "valor": round(valor, 2),
            "nome_fantasia": nome,
            "descricao": bloco[:300],
            "data": data_encontrada,
            "origem": "importacao_pdf"
        })

    return transacoes


def processar_pdf_extrato(arquivo_bytes: bytes) -> tuple:
    """
    Processa PDF de extrato bancário.

    + R$ valor  → ENTRADA
    - R$ valor  → SAÍDA
    R$ valor    → IGNORADO (balanço/saldo)

    Retorna: (sucesso, lista_transacoes, mensagem)
    """
    try:
        linhas = _extrair_texto_pdf(arquivo_bytes)

        if not linhas:
            return False, [], (
                "Não foi possível extrair texto do PDF. "
                "Verifique se não é um PDF protegido."
            )

        blocos = _agrupar_em_transacoes(linhas)
        transacoes = _parsear_blocos(blocos)

        if not transacoes:
            amostra = ' | '.join(linhas[:10])
            registrar_log("pdf_parser",
                f"Nenhuma transação com +/- encontrada. Amostra: {amostra[:300]}")
            return False, [], (
                "Nenhuma transação encontrada. "
                "O extrato deve conter valores precedidos de + ou -."
            )

        entradas = sum(1 for t in transacoes if t['tipo'] == 'entrada')
        saidas = sum(1 for t in transacoes if t['tipo'] == 'saida')
        total_entrada = sum(t['valor'] for t in transacoes if t['tipo'] == 'entrada')
        total_saida = sum(t['valor'] for t in transacoes if t['tipo'] == 'saida')

        mensagem = (
            f"{len(transacoes)} transações identificadas — "
            f"{entradas} entradas (R$ {total_entrada:,.2f}) | "
            f"{saidas} saídas (R$ {total_saida:,.2f})"
        )

        return True, transacoes, mensagem

    except Exception as e:
        registrar_log("pdf_parser", f"Erro ao processar PDF: {str(e)}")
        return False, [], f"Erro ao processar PDF: {str(e)}"


# ==================== COMPATIBILIDADE COM agente.py ====================

def _parsear_linhas(linhas: list) -> list:
    blocos = _agrupar_em_transacoes(linhas)
    return _parsear_blocos(blocos)


def _determinar_tipo(linha: str) -> str:
    m = PADRAO_VALOR_COM_SINAL.search(linha)
    if m:
        return 'entrada' if m.group(1) == '+' else 'saida'
    return 'saida'

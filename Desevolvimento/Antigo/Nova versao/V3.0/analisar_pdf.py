"""
analisar_pdf.py
Analisador de estrutura de extrato PDF - Versão Terminal
Uso: python analisar_pdf.py arquivo.pdf
"""

import re
import sys
import os

try:
    import pdfplumber
except ImportError:
    print("Instalando pdfplumber...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pdfplumber"])
    import pdfplumber


# ==================== PADRÕES ====================

PADRAO_VALOR_COM_SINAL = re.compile(
    r'([+\-])\s*R\$\s*([\d]{1,3}(?:\.[\d]{3})*,\d{2}|[\d]+,\d{2})'
)

PADRAO_VALOR_SEM_SINAL = re.compile(
    r'R\$\s*([\d]{1,3}(?:\.[\d]{3})*,\d{2}|[\d]+,\d{2})'
)

PADROES_DATA = [
    re.compile(r'(\d{2}/\d{2}/\d{4})'),
    re.compile(r'(\d{2}/\d{2}/\d{2})'),
    re.compile(r'(\d{4}-\d{2}-\d{2})'),
    re.compile(r'(\d{2}-\d{2}-\d{4})'),
]


# ==================== CORES NO TERMINAL ====================

class Cor:
    VERDE    = '\033[92m'
    AMARELO  = '\033[93m'
    VERMELHO = '\033[91m'
    AZUL     = '\033[94m'
    CIANO    = '\033[96m'
    BRANCO   = '\033[97m'
    CINZA    = '\033[90m'
    RESET    = '\033[0m'
    BOLD     = '\033[1m'


def c(texto, cor):
    return f"{cor}{texto}{Cor.RESET}"


# ==================== CLASSIFICAÇÃO ====================

def classificar_linha(linha):
    """Classifica o tipo de cada linha"""
    tem_data  = any(p.search(linha) for p in PADROES_DATA)
    tem_sinal = bool(PADRAO_VALOR_COM_SINAL.search(linha))
    tem_valor = bool(PADRAO_VALOR_SEM_SINAL.search(linha))

    if tem_data and tem_sinal:
        return "TRANSACAO_COMPLETA"
    elif tem_data and tem_valor:
        return "SALDO_OU_CABECALHO"
    elif tem_data:
        return "DATA_PURA"
    elif tem_sinal:
        return "VALOR_COM_SINAL"
    elif tem_valor:
        return "VALOR_SEM_SINAL"
    else:
        return "TEXTO_PURO"


LABELS = {
    "TRANSACAO_COMPLETA":  c("✅ TRANSACAO COMPLETA ", Cor.VERDE),
    "SALDO_OU_CABECALHO":  c("⚠️  SALDO/CABECALHO   ", Cor.AMARELO),
    "DATA_PURA":           c("📅 DATA               ", Cor.AZUL),
    "VALOR_COM_SINAL":     c("💰 VALOR COM SINAL    ", Cor.CIANO),
    "VALOR_SEM_SINAL":     c("🔸 VALOR SEM SINAL    ", Cor.AMARELO),
    "TEXTO_PURO":          c("📝 TEXTO              ", Cor.CINZA),
}


# ==================== ANÁLISES ====================

def analisar_linhas(pdf_path):
    """
    Mostra cada linha com seu tipo classificado
    """
    print(c("\n" + "=" * 80, Cor.BOLD))
    print(c("  ANÁLISE LINHA A LINHA", Cor.BOLD))
    print(c("=" * 80, Cor.RESET))

    with pdfplumber.open(pdf_path) as pdf:
        print(f"  Arquivo  : {c(pdf_path, Cor.AZUL)}")
        print(f"  Páginas  : {c(str(len(pdf.pages)), Cor.VERDE)}")

        total_linhas = 0

        for num_pag, pagina in enumerate(pdf.pages, 1):
            print(c(f"\n{'─' * 80}", Cor.CINZA))
            print(c(f"  PÁGINA {num_pag}", Cor.BOLD + Cor.AZUL))
            print(c(f"{'─' * 80}", Cor.CINZA))

            texto = pagina.extract_text()

            if not texto:
                print(c("  >>> PÁGINA VAZIA (imagem?) - necessário OCR", Cor.VERMELHO))
                continue

            linhas = [l.strip() for l in texto.split('\n') if l.strip()]
            total_linhas += len(linhas)

            print(f"  {c(str(len(linhas)), Cor.VERDE)} linhas nesta página\n")
            print(f"  {'N°':<5} {'TIPO':<30} CONTEÚDO")
            print(f"  {'─' * 5} {'─' * 28} {'─' * 44}")

            for i, linha in enumerate(linhas, 1):
                tipo   = classificar_linha(linha)
                label  = LABELS.get(tipo, tipo)
                print(f"  {c(str(i).ljust(5), Cor.CINZA)} {label} {linha[:65]}")

        print(c(f"\n  TOTAL DE LINHAS NO PDF: {total_linhas}", Cor.BOLD))


def analisar_blocos(pdf_path):
    """
    Simula o agrupamento e mostra como os blocos ficam
    """
    print(c("\n" + "=" * 80, Cor.BOLD))
    print(c("  SIMULAÇÃO DE AGRUPAMENTO (como o parser agrupa)", Cor.BOLD))
    print(c("=" * 80, Cor.RESET))

    with pdfplumber.open(pdf_path) as pdf:
        todas_linhas = []
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                for linha in texto.split('\n'):
                    linha = linha.strip()
                    if linha:
                        todas_linhas.append(linha)

    print(f"\n  Total de linhas brutas: {c(str(len(todas_linhas)), Cor.VERDE)}\n")

    bloco_num  = 0
    bloco_atual = []

    for i, linha in enumerate(todas_linhas, 1):
        tem_data  = any(p.search(linha) for p in PADROES_DATA)
        tem_sinal = bool(PADRAO_VALOR_COM_SINAL.search(linha))

        if tem_data:
            # Fecha bloco anterior
            if bloco_atual:
                bloco_num += 1
                texto_bloco    = ' '.join(bloco_atual)
                tem_sinal_bloco = bool(PADRAO_VALOR_COM_SINAL.search(texto_bloco))

                if tem_sinal_bloco:
                    print(c(f"  BLOCO #{bloco_num} ✅ TRANSACAO:", Cor.VERDE))
                else:
                    print(c(f"  BLOCO #{bloco_num} ❌ DESCARTADO (sem sinal):", Cor.VERMELHO))

                print(f"  → {texto_bloco[:110]}\n")
                bloco_atual = []

            bloco_atual.append(linha)
            print(c(f"  [{i:04}] 📅 INICIO BLOCO : {linha[:70]}", Cor.AZUL))

        elif tem_sinal:
            bloco_atual.append(linha)
            print(c(f"  [{i:04}] 💰 FECHA BLOCO  : {linha[:70]}", Cor.CIANO))

            bloco_num   += 1
            texto_bloco  = ' '.join(bloco_atual)
            print(c(f"  BLOCO #{bloco_num} ✅ TRANSACAO:", Cor.VERDE))
            print(f"  → {texto_bloco[:110]}\n")
            bloco_atual = []

        else:
            if bloco_atual:
                bloco_atual.append(linha)
                print(c(f"  [{i:04}] 📝 CONTINUACAO  : {linha[:70]}", Cor.AMARELO))
            else:
                print(c(f"  [{i:04}] ⚠️  LINHA SOLTA  : {linha[:70]}", Cor.CINZA))

    # Último bloco
    if bloco_atual:
        bloco_num  += 1
        texto_bloco = ' '.join(bloco_atual)
        tem_sinal_bloco = bool(PADRAO_VALOR_COM_SINAL.search(texto_bloco))

        if tem_sinal_bloco:
            print(c(f"  BLOCO #{bloco_num} ✅ TRANSACAO:", Cor.VERDE))
        else:
            print(c(f"  BLOCO #{bloco_num} ❌ DESCARTADO:", Cor.VERMELHO))

        print(f"  → {texto_bloco[:110]}\n")

    print(c(f"  TOTAL DE BLOCOS: {bloco_num}", Cor.BOLD))


def texto_bruto(pdf_path):
    """
    Mostra o texto EXATO que o pdfplumber extrai
    """
    print(c("\n" + "=" * 80, Cor.BOLD))
    print(c("  TEXTO BRUTO (exatamente como pdfplumber extrai)", Cor.BOLD))
    print(c("=" * 80, Cor.RESET))

    with pdfplumber.open(pdf_path) as pdf:
        for num_pag, pagina in enumerate(pdf.pages, 1):
            print(c(f"\n{'─' * 40} PÁGINA {num_pag} {'─' * 40}", Cor.AZUL))
            texto = pagina.extract_text()
            if texto:
                # Mostrar com número de linha
                for i, linha in enumerate(texto.split('\n'), 1):
                    print(f"  {c(str(i).rjust(4), Cor.CINZA)} │ {linha}")
            else:
                print(c("  (página vazia ou imagem)", Cor.VERMELHO))


def salvar_relatorio(pdf_path, saida_path):
    """
    Salva o relatório completo em arquivo txt (sem cores)
    """
    import io
    from contextlib import redirect_stdout

    # Desabilitar cores para o arquivo
    for attr in dir(Cor):
        if not attr.startswith('_'):
            setattr(Cor, attr, '')

    with open(saida_path, 'w', encoding='utf-8') as f:
        with redirect_stdout(f):
            texto_bruto(pdf_path)
            analisar_linhas(pdf_path)
            analisar_blocos(pdf_path)

    print(f"\n  Relatório salvo em: {saida_path}")


# ==================== MAIN ====================

def main():
    # Sem argumento: pedir o caminho
    if len(sys.argv) < 2:
        print(c("\n  🔍 Analisador de Estrutura de Extrato PDF", Cor.BOLD))
        print(c("  " + "─" * 45, Cor.CINZA))
        pdf_path = input(c("\n  Digite o caminho do PDF: ", Cor.AZUL)).strip()

        if not pdf_path:
            print(c("  ❌ Nenhum arquivo informado.", Cor.VERMELHO))
            sys.exit(1)
    else:
        pdf_path = sys.argv[1]

    # Verificar se o arquivo existe
    if not os.path.isfile(pdf_path):
        print(c(f"\n  ❌ Arquivo não encontrado: {pdf_path}", Cor.VERMELHO))
        sys.exit(1)

    print(c(f"\n  📂 Analisando: {pdf_path}", Cor.VERDE))

    # Menu de opções
    print(c("\n  O que deseja ver?", Cor.BOLD))
    print("  [1] Texto bruto do PDF")
    print("  [2] Análise linha a linha")
    print("  [3] Simulação de agrupamento")
    print("  [4] TUDO + salvar em relatorio.txt")
    print("  [5] Tudo no terminal")

    opcao = input(c("\n  Opção [1-5]: ", Cor.AZUL)).strip()

    if opcao == '1':
        texto_bruto(pdf_path)

    elif opcao == '2':
        analisar_linhas(pdf_path)

    elif opcao == '3':
        analisar_blocos(pdf_path)

    elif opcao == '4':
        saida = pdf_path.replace('.pdf', '_relatorio.txt')
        salvar_relatorio(pdf_path, saida)

    elif opcao == '5':
        texto_bruto(pdf_path)
        analisar_linhas(pdf_path)
        analisar_blocos(pdf_path)

    else:
        print(c("  Opção inválida.", Cor.VERMELHO))


if __name__ == "__main__":
    main()

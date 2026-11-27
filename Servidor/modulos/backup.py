"""
Exportar / importar dados. O arquivo (.rrfs) é cifrado com uma FRASE que o
usuário escolhe, independente do login: se a conta for perdida, basta criar
outro login e importar o arquivo com a frase.
"""
import time
from modulos import sync_core, identidade


def exportar(conn, frase):
    erro = identidade.validar_frase(frase)
    if erro:
        raise ValueError(erro)
    regs = sync_core.snapshot(conn)
    return identidade.cifrar_backup(
        {'versao': 2, 'criado': time.strftime('%Y-%m-%dT%H:%M:%S'),
         'registros': regs}, frase), len(regs)


def importar(conn, blob, frase):
    d = identidade.abrir_backup(blob, frase)
    regs = d.get('registros')
    if not isinstance(regs, list):
        raise ValueError('Backup inválido')
    n = sync_core.aplicar(conn, regs)       # idempotente: pode importar 2x
    return n

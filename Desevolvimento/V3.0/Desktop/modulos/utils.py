"""Utilitários exigidos por modulos/tox_remoto.py"""
import subprocess


def executar_comando(cmd, timeout=30):
    """Executa um comando de shell e devolve {'sucesso','saida','erro','codigo'}."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return {'sucesso': r.returncode == 0, 'saida': r.stdout,
                'erro': r.stderr, 'codigo': r.returncode}
    except Exception as e:
        return {'sucesso': False, 'saida': '', 'erro': str(e), 'codigo': -1}

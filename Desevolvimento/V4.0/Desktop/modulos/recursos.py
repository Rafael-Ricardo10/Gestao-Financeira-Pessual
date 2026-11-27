"""Caminhos que funcionam tanto rodando o código-fonte quanto no binário
único (PyInstaller): a pasta de DADOS fica ao lado do executável; os
recursos embutidos (ícone, libtoxcore) ficam dentro dele."""
import os
import sys


def congelado():
    return bool(getattr(sys, 'frozen', False))


def pasta_base():
    """Pasta onde ficam 'dados/' e 'logs/' (ao lado do executável)."""
    if congelado():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pasta_recursos():
    return getattr(sys, '_MEIPASS', pasta_base())


def recurso(nome):
    return os.path.join(pasta_recursos(), nome)


def env_limpo():
    """Ambiente para subprocessos externos (ufw, ip, netsh...). O binário
    único altera LD_LIBRARY_PATH para apontar às bibliotecas embutidas, o
    que quebraria programas do sistema."""
    env = dict(os.environ)
    if 'LD_LIBRARY_PATH_ORIG' in env:
        env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
    elif congelado():
        env.pop('LD_LIBRARY_PATH', None)
    env.setdefault('LC_ALL', 'C')
    return env

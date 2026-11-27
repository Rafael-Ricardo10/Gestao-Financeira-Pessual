"""Caminhos que funcionam tanto rodando o código-fonte quanto no binário
único (PyInstaller): a pasta de DADOS fica ao lado do executável; os
recursos embutidos (ícone, libtoxcore) ficam dentro dele."""
import os
import sys


def _nuitka():
    return '__compiled__' in globals()


def congelado():
    """True no binário (PyInstaller ou Nuitka)."""
    return bool(getattr(sys, 'frozen', False)) or _nuitka()


def caminho_exe():
    """Caminho do executável que o usuário abriu."""
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    if _nuitka():
        a = sys.argv[0]
        if not os.path.dirname(a):
            import shutil
            a = shutil.which(a) or a
        return os.path.abspath(a)
    return os.path.abspath(sys.executable)


def pasta_base():
    """Pasta onde ficam 'dados/' e 'logs/' (ao lado do executável)."""
    if congelado():
        return os.path.dirname(caminho_exe())
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pasta_recursos():
    if getattr(sys, '_MEIPASS', None):
        return sys._MEIPASS
    if _nuitka():
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return pasta_base()


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

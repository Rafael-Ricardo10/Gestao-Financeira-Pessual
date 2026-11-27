#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RRFS Finanças - aplicativo desktop (offline-first, sincroniza com o servidor)"""
import os
import sys
import time
import threading
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)
os.makedirs('dados', exist_ok=True)
os.makedirs('logs', exist_ok=True)

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QImage
from interface.main_window import MainWindow

APP_ID = 'rrfs-financas'
ICONE = os.path.join(BASE, 'finance_icon.png')


def _registrar_atalho_linux():
    """No Wayland a janela NÃO recebe o ícone pelo programa: o ambiente
    (GNOME/KDE) procura um arquivo .desktop com o mesmo nome do app_id e
    usa o Icon dele. Sem ele aparece o ícone genérico (a letra 'W').
    Cria/atualiza o atalho e o ícone do usuário. No X11 o WM_CLASS
    (applicationName) também casa com este atalho."""
    if not sys.platform.startswith('linux') or not os.path.exists(ICONE):
        return
    try:
        home = os.path.expanduser('~')
        dados = os.environ.get('XDG_DATA_HOME') or os.path.join(
            home, '.local', 'share')
        pasta_icone = os.path.join(dados, 'icons', 'hicolor', '256x256',
                                   'apps')
        os.makedirs(pasta_icone, exist_ok=True)
        destino_icone = os.path.join(pasta_icone, APP_ID + '.png')
        img = QImage(ICONE)
        if not img.isNull():
            img = img.scaled(256, 256, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
            img.save(destino_icone, 'PNG')

        script = os.path.join(BASE, 'app.py')
        conteudo = (
            '[Desktop Entry]\n'
            'Type=Application\n'
            'Name=RRFS Finanças\n'
            'Comment=Gestão financeira pessoal\n'
            f'Exec="{sys.executable}" "{script}"\n'
            f'Path={BASE}\n'
            f'Icon={APP_ID}\n'
            'Terminal=false\n'
            'Categories=Office;Finance;\n'
            f'StartupWMClass={APP_ID}\n'
        )
        pasta_apps = os.path.join(dados, 'applications')
        os.makedirs(pasta_apps, exist_ok=True)
        arq = os.path.join(pasta_apps, APP_ID + '.desktop')
        atual = ''
        if os.path.exists(arq):
            with open(arq, encoding='utf-8') as f:
                atual = f.read()
        if atual != conteudo:
            with open(arq, 'w', encoding='utf-8') as f:
                f.write(conteudo)
            os.chmod(arq, 0o755)
    except Exception:
        pass


def _iniciar_vigia(app, limite=1.0):
    """Detecta a interface congelada: se a thread principal ficar mais de
    `limite` s sem responder, grava em logs/travamento.log a linha exata em
    que ela está parada e o que as outras threads estão fazendo."""
    estado = {'t': time.monotonic()}
    principal = threading.main_thread().ident

    def batida():
        estado['t'] = time.monotonic()

    timer = QTimer(app)
    timer.timeout.connect(batida)
    timer.start(200)
    app._vigia_timer = timer

    def vigiar():
        avisado = False
        while True:
            time.sleep(0.25)
            parado = time.monotonic() - estado['t']
            if parado < limite:
                avisado = False
                continue
            if avisado:
                continue
            avisado = True
            try:
                quadros = sys._current_frames()
                nomes = {t.ident: t.name for t in threading.enumerate()}
                with open(os.path.join('logs', 'travamento.log'), 'a',
                          encoding='utf-8') as f:
                    f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} "
                            f"interface parada ha {parado:.1f}s =====\n")
                    for ident, quadro in quadros.items():
                        titulo = ('THREAD PRINCIPAL (interface)'
                                  if ident == principal
                                  else nomes.get(ident, str(ident)))
                        f.write(f"--- {titulo}\n")
                        f.write(''.join(traceback.format_stack(quadro)[-8:]))
            except Exception:
                pass

    threading.Thread(target=vigiar, daemon=True, name='Vigia').start()


def main():
    # Deve vir ANTES de criar o QApplication (define o app_id do Wayland
    # e o WM_CLASS do X11, que ligam a janela ao atalho .desktop)
    QApplication.setApplicationName(APP_ID)
    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv)
    app.setApplicationDisplayName('RRFS Finanças')
    app.setWindowIcon(QIcon(ICONE))           # todas as janelas e diálogos
    app.setQuitOnLastWindowClosed(False)      # continua sincronizando na bandeja
    _registrar_atalho_linux()
    _iniciar_vigia(app)

    janela = MainWindow()
    # Inicia minimizado na bandeja. Se o ambiente não tem bandeja (ou se
    # usar --mostrar), abre a janela normalmente para não ficar invisível.
    if ('--mostrar' in sys.argv
            or not QSystemTrayIcon.isSystemTrayAvailable()):
        janela.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

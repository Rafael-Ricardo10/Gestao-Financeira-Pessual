#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RRFS Finanças - aplicativo desktop (offline-first, sincroniza entre aparelhos)

Funciona de duas formas:
  * código-fonte:  python3 app.py
  * binário único (PyInstaller): a pasta 'dados/' e 'logs/' ficam AO LADO do
    executável, fora dele (o executável pode ser trocado por uma versão nova
    sem perder nada).
"""
import os
import sys
import time
import threading
import traceback

# Pasta de dados = ao lado do executável (ou do app.py)
if getattr(sys, 'frozen', False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
if BASE not in sys.path:
    sys.path.insert(0, BASE)
os.makedirs('dados', exist_ok=True)
os.makedirs('logs', exist_ok=True)

from modulos import recursos  # noqa: E402

APP_ID = 'rrfs-financas'
ICONE = recursos.recurso('finance_icon.png')


def _autoteste():
    """python app.py --autoteste  (ou ./RRFS-Financas --autoteste):
    confere que tudo que o app precisa está presente. Não abre janela."""
    ok = True

    def passo(nome, fn):
        nonlocal ok
        try:
            r = fn()
            print(f'  [ok] {nome}' + (f' - {r}' if r else ''))
        except Exception as e:
            ok = False
            print(f'  [FALHA] {nome}: {e}')

    print('RRFS Finanças - autoteste')
    passo('SQLCipher (banco cifrado)',
          lambda: __import__('modulos.bd_seguro', fromlist=['x'])
          .CRIPTO_REPOUSO or (_ for _ in ()).throw(
              RuntimeError('SQLCipher ausente: dados sem cifra')))
    passo('libtoxcore (rede)',
          lambda: __import__('modulos.tox_financeiro',
                             fromlist=['x']).carregar_libtoxcore() and
          'carregada')
    passo('criptografia (identidade/backup)', lambda: __import__(
        'modulos.identidade', fromlist=['x']).derivar('teste', 'senha-teste-1')
        and 'scrypt+HKDF')
    passo('descoberta LAN', lambda: __import__(
        'modulos.descoberta_lan', fromlist=['x']).interfaces() and 'ok')

    def telas():
        import importlib
        for m in ('interface.main_window', 'interface.dialogs.sync_dialog',
                  'interface.dialogs.login_dialog',
                  'interface.dialogs.inflation_dialog',
                  'interface.dialogs.report_dialogs',
                  'interface.dialogs.trends_dialog',
                  'interface.dialogs.loan_dialogs',
                  'interface.dialogs.planning_dialog',
                  'interface.dialogs.cashflow_dialog',
                  'interface.dialogs.goal_dialogs',
                  'interface.dialogs.category_dialogs',
                  'interface.dialogs.transaction_dialogs',
                  'modulos.pdf_parser', 'modulos.currency_tracker',
                  'modulos.inflation_tracker'):
            importlib.import_module(m)
        return 'todas as telas importam'
    passo('telas e módulos', telas)
    passo('ícone', lambda: os.path.exists(ICONE) or 'ausente (opcional)')
    print('RESULTADO:', 'TUDO OK' if ok else 'COM FALHAS')
    return 0 if ok else 1


def _registrar_atalho_linux():
    """No Wayland a janela NÃO recebe o ícone pelo programa: o ambiente
    (GNOME/KDE) procura um arquivo .desktop com o mesmo nome do app_id e
    usa o Icon dele. Cria/atualiza o atalho e o ícone do usuário.
    (Só é feito para o binário/app instalado, não a cada teste.)"""
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QImage
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

        if getattr(sys, 'frozen', False):
            exec_cmd = f'"{sys.executable}"'
        else:
            exec_cmd = f'"{sys.executable}" "{os.path.join(BASE, "app.py")}"'
        conteudo = (
            '[Desktop Entry]\n'
            'Type=Application\n'
            'Name=RRFS Finanças\n'
            'Comment=Gestão financeira pessoal\n'
            f'Exec={exec_cmd}\n'
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
    from PyQt5.QtCore import QTimer
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
    if '--autoteste' in sys.argv:
        sys.exit(_autoteste())

    from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMessageBox
    from PyQt5.QtCore import QLockFile
    from PyQt5.QtGui import QIcon

    # Deve vir ANTES de criar o QApplication (define o app_id do Wayland
    # e o WM_CLASS do X11, que ligam a janela ao atalho .desktop)
    QApplication.setApplicationName(APP_ID)
    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv)
    app.setApplicationDisplayName('RRFS Finanças')
    app.setWindowIcon(QIcon(ICONE))           # todas as janelas e diálogos
    app.setQuitOnLastWindowClosed(False)      # continua sincronizando na bandeja

    # Uma única cópia por pasta de dados (duas cópias disputariam o banco
    # cifrado e as portas da rede). Ao reiniciar após "sair da conta" a
    # cópia anterior ainda pode estar fechando: espera um pouco.
    trava = QLockFile(os.path.join(BASE, 'dados', 'app.lock'))
    trava.setStaleLockTime(30000)
    if not trava.tryLock(8000):
        QMessageBox.information(
            None, 'RRFS Finanças',
            'O RRFS Finanças já está aberto (procure o ícone na bandeja '
            'do sistema).')
        sys.exit(0)
    app._trava = trava

    _registrar_atalho_linux()
    _iniciar_vigia(app)

    from interface.main_window import MainWindow
    janela = MainWindow()
    app._janela = janela
    # Inicia minimizado na bandeja. Se o ambiente não tem bandeja (ou se
    # usar --mostrar), abre a janela normalmente para não ficar invisível.
    if ('--mostrar' in sys.argv
            or not QSystemTrayIcon.isSystemTrayAvailable()):
        janela.show()
    codigo = app.exec_()
    trava.unlock()
    sys.exit(codigo)


if __name__ == '__main__':
    main()

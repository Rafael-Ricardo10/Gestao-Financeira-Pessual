#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RRFS Finanças - aplicativo desktop (offline-first, sincroniza com o servidor)"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)
os.makedirs('dados', exist_ok=True)
os.makedirs('logs', exist_ok=True)

from PyQt5.QtWidgets import QApplication
from interface.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)      # continua sincronizando na bandeja
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

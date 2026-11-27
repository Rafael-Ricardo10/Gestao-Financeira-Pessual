import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont, QColor, QIcon, QPixmap, QPainter
from PyQt5.QtCore import Qt

def create_default_icon():
    """Cria ícone padrão se não existir"""
    if not os.path.exists('finance_icon.png'):
        from PyQt5.QtGui import QPainter, QPixmap, QFont

        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setPen(QColor(0, 128, 0))
        painter.setBrush(QColor(0, 128, 0, 100))
        painter.drawEllipse(5, 5, 54, 54)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 40, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "$")
        painter.end()

        pixmap.save('finance_icon.png')

def main():
    app = QApplication(sys.argv)

    # Criar pasta 'dados' se não existir
    if not os.path.exists('dados'):
        os.makedirs('dados')

    # Criar pasta 'logs' se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Criar pasta 'modulos' se não existir
    if not os.path.exists('modulos'):
        os.makedirs('modulos')

    # Criar pasta 'interface' se não existir
    if not os.path.exists('interface'):
        os.makedirs('interface')

    # Criar ícone padrão
    create_default_icon()

    # Importar e iniciar a janela principal
    from interface.main_window import MainWindow

    main_window = MainWindow()

    # Iniciar minimizado na bandeja
    if hasattr(main_window, 'start_minimized') and main_window.start_minimized:
        main_window.hide()
        main_window.tray_icon.showMessage(
            "Gestão Financeira",
            "Aplicativo iniciado e minimizado na bandeja do sistema.",
            main_window.tray_icon.Information,
            2000
        )
    else:
        main_window.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

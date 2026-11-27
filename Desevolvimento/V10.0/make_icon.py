import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtGui import QGuiApplication, QImage, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QRectF
app = QGuiApplication([])
img = QImage(256, 256, QImage.Format_ARGB32); img.fill(Qt.transparent)
p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
p.setBrush(QColor('#27ae60')); p.setPen(Qt.NoPen); p.drawEllipse(8, 8, 240, 240)
p.setPen(QColor('white')); f = QFont('sans', 92); f.setBold(True); p.setFont(f)
p.drawText(QRectF(0, 0, 256, 256), Qt.AlignCenter, 'R$'); p.end()
img.save('finance_icon.png'); print('ícone provisório criado: finance_icon.png (troque pelo seu)')

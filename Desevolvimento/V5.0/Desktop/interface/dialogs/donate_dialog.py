"""
Diálogo de doação - "Me pague um café"
Incentivo para continuar o desenvolvimento do RRFS Finanças
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor


class DonateDialog(QDialog):
    """
    Diálogo para exibir informações de doação ao desenvolvedor.
    Exibe endereços de criptomoedas e chave PIX.
    """

    # ── Dados de doação ──────────────────────────────────────────
    PIX_KEY       = "seu-pix@email.com"          # ← Altere aqui
    BTC_ADDRESS   = "bc1qSuaChaveReaBitcoinAqui"  # ← Altere aqui
    ETH_ADDRESS   = "0xSuaChaveRealEthereumAqui"  # ← Altere aqui
    USDT_ADDRESS  = "TSuaChaveRealUSDTAqui"        # ← Altere aqui (TRC20)
    LTC_ADDRESS   = "LSuaChaveRealLitecoinAqui"   # ← Altere aqui

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("☕ Me Pague um Café")
        self.setMinimumWidth(520)
        self.setMaximumWidth(600)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )
        self.init_ui()
        self.apply_theme()

    # ══════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════

    def init_ui(self):
        """Inicializa a interface do diálogo"""
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Cabeçalho ────────────────────────────────────────────
        header_label = QLabel("☕  Me Pague um Café!")
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; "
            "margin-bottom: 4px;"
        )
        layout.addWidget(header_label)

        # ── Mensagem motivacional ─────────────────────────────────
        msg = (
            "Olá! Sou o desenvolvedor do RRFS Finanças.\n\n"
            "Este projeto é desenvolvido no meu tempo livre com muito\n"
            "carinho para ajudar pessoas a organizarem suas finanças.\n\n"
            "Se o sistema te ajudou de alguma forma, considere\n"
            "contribuir com um cafezinho. Qualquer valor é muito\n"
            "bem-vindo e me motiva a continuar melhorando! 🚀\n\n"
            "Obrigado pelo apoio! ❤️"
        )
        msg_label = QLabel(msg)
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(
            "font-size: 13px; padding: 10px; "
            "border-radius: 8px; line-height: 1.5;"
        )
        layout.addWidget(msg_label)

        # ── Separador ────────────────────────────────────────────
        layout.addWidget(self._make_separator())

        # ── PIX ──────────────────────────────────────────────────
        layout.addWidget(
            self._make_section_title("🇧🇷  PIX (Brasil)")
        )
        layout.addWidget(
            self._make_address_row(
                "Chave PIX:", self.PIX_KEY, "#00a86b"
            )
        )

        # ── Separador ────────────────────────────────────────────
        layout.addWidget(self._make_separator())

        # ── Criptomoedas ─────────────────────────────────────────
        layout.addWidget(
            self._make_section_title("🪙  Criptomoedas")
        )
        layout.addWidget(
            self._make_address_row(
                "₿  Bitcoin (BTC):",
                self.BTC_ADDRESS, "#f7931a"
            )
        )
        layout.addWidget(
            self._make_address_row(
                "⟠  Ethereum (ETH):",
                self.ETH_ADDRESS, "#627eea"
            )
        )
        layout.addWidget(
            self._make_address_row(
                "₮  USDT (TRC20):",
                self.USDT_ADDRESS, "#26a17b"
            )
        )
        layout.addWidget(
            self._make_address_row(
                "Ł  Litecoin (LTC):",
                self.LTC_ADDRESS, "#345d9d"
            )
        )

        # ── Separador ────────────────────────────────────────────
        layout.addWidget(self._make_separator())

        # ── Nota de rodapé ───────────────────────────────────────
        footer = QLabel(
            "💡 Clique em 'Copiar' ao lado de qualquer endereço\n"
            "para copiar para a área de transferência."
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet(
            "font-size: 11px; color: #888; font-style: italic;"
        )
        layout.addWidget(footer)

        # ── Botão fechar ─────────────────────────────────────────
        close_btn = QPushButton("Fechar")
        close_btn.setFixedHeight(36)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)

        self.setLayout(layout)

    # ══════════════════════════════════════════════════════════════
    # HELPERS DE LAYOUT
    # ══════════════════════════════════════════════════════════════

    def _make_separator(self):
        """Cria uma linha separadora horizontal"""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _make_section_title(self, text):
        """Cria um título de seção"""
        label = QLabel(text)
        label.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "margin-top: 4px; margin-bottom: 2px;"
        )
        return label

    def _make_address_row(self, label_text, address, color):
        """
        Cria uma linha com label, endereço truncado e botão copiar.

        Args:
            label_text : Texto do rótulo (ex: 'Bitcoin (BTC):')
            address    : Endereço/chave completa
            color      : Cor de destaque do endereço
        """
        container = QFrame()
        container.setStyleSheet(
            "QFrame { border-radius: 6px; padding: 2px; }"
        )
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(6, 4, 6, 4)
        row_layout.setSpacing(8)

        # Rótulo
        lbl = QLabel(label_text)
        lbl.setFixedWidth(150)
        lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        row_layout.addWidget(lbl)

        # Endereço truncado (exibe primeiros e últimos caracteres)
        if len(address) > 24:
            display = address[:12] + "..." + address[-8:]
        else:
            display = address

        addr_lbl = QLabel(display)
        addr_lbl.setStyleSheet(
            f"font-family: monospace; font-size: 11px; "
            f"color: {color}; font-weight: bold;"
        )
        addr_lbl.setToolTip(address)   # Endereço completo no hover
        row_layout.addWidget(addr_lbl, 1)

        # Botão copiar
        copy_btn = QPushButton("Copiar")
        copy_btn.setFixedSize(65, 28)
        copy_btn.setStyleSheet(
            f"background-color: {color}; color: white; "
            f"border-radius: 4px; font-size: 11px; "
            f"font-weight: bold;"
        )
        copy_btn.clicked.connect(
            lambda _, addr=address, btn=copy_btn:
            self._copy_to_clipboard(addr, btn)
        )
        row_layout.addWidget(copy_btn)

        return container

    # ══════════════════════════════════════════════════════════════
    # AÇÕES
    # ══════════════════════════════════════════════════════════════

    def _copy_to_clipboard(self, text, button):
        """Copia o endereço para a área de transferência"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        # Feedback visual temporário no botão
        original_text  = button.text()
        original_style = button.styleSheet()

        button.setText("✓ Copiado!")
        button.setStyleSheet(
            "background-color: #2ecc71; color: white; "
            "border-radius: 4px; font-size: 11px; "
            "font-weight: bold;"
        )

        # Restaurar após 2 segundos
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(
            2000,
            lambda: self._restore_button(
                button, original_text, original_style
            )
        )

    def _restore_button(self, button, text, style):
        """Restaura o botão ao estado original"""
        try:
            button.setText(text)
            button.setStyleSheet(style)
        except RuntimeError:
            pass   # Widget pode ter sido destruído

    # ══════════════════════════════════════════════════════════════
    # TEMA
    # ══════════════════════════════════════════════════════════════

    def apply_theme(self):
        """Aplica o tema claro ou escuro ao diálogo"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                }
                QFrame {
                    background-color: #2d3436;
                    border: 1px solid #4b6584;
                }
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border-radius: 4px;
                    padding: 6px 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #fafafa;
                    color: #333;
                }
                QLabel {
                    color: #333;
                }
                QFrame {
                    background-color: #f0f0f0;
                    border: 1px solid #ddd;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border-radius: 4px;
                    padding: 6px 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)

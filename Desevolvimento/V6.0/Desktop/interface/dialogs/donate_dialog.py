"""
Diálogo de doação - "Me pague um café" + Transparência do sistema
Incentivo para continuar o desenvolvimento do RRFS Finanças.

Carteiras opcionais: basta DESCOMENTAR a linha da moeda (e colocar o
endereço real) que a linha aparece sozinha no diálogo. Moedas sem endereço
não aparecem e não causam erro.
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication, QTextBrowser
)
from PyQt5.QtCore import Qt, QTimer


# ══════════════════════════════════════════════════════════════════════
# TEXTO DA TRANSPARÊNCIA (HTML simples)
# Se algum recurso mudar, edite aqui.
# ══════════════════════════════════════════════════════════════════════
TRANSPARENCIA_HTML = """
<h2>🔍 Transparência do RRFS Finanças</h2>
<p>O RRFS Finanças é um sistema de gestão financeira pessoal. Ele foi
desenhado para que <b>só você</b> tenha acesso aos seus dados. O código do
sistema será fechado na distribuição para dificultar ataques, mas aqui
explicamos com clareza o que ele faz e o que ele não faz, para que qualquer
pessoa ou especialista possa conferir.</p>

<h3>🌐 Sem servidores centrais</h3>
<p>Não existe servidor do desenvolvedor que guarde ou processe seus dados.
Seus dados ficam <b>armazenados nos seus próprios aparelhos</b>, em um banco
de dados cifrado em disco. Os aparelhos conversam diretamente entre si.</p>

<h3>🔄 Como funciona a sincronização</h3>
<ul>
<li><b>Offline:</b> o app funciona normalmente sem internet.</li>
<li><b>Rede local:</b> aparelhos da mesma rede (Wi-Fi/cabo) se encontram
sozinhos e sincronizam, mesmo sem internet.</li>
<li><b>Pela internet:</b> você pode usar o app no computador de casa e em
outro no escritório; os dois se encontram e sincronizam à distância, sem
passar por um servidor central.</li>
</ul>
<p>Para os aparelhos se reconhecerem, basta entrar com o <b>mesmo usuário e
a mesma senha</b>. Não há cadastro em servidor.</p>

<h3>🔒 Criptografia de ponta a ponta</h3>
<p>Toda a comunicação entre seus aparelhos é cifrada de ponta a ponta.
As chaves são geradas a partir do seu usuário e senha e <b>nunca saem dos
seus aparelhos</b>. Ninguém além de você consegue ler os dados: nem outras
pessoas, nem provedores de internet, nem o desenvolvedor.</p>
<p>Por isso <b>não existe recuperação de senha</b>: a senha é a chave dos
seus dados. Use uma senha longa (uma frase de 4 palavras ou 14+ caracteres)
e guarde-a bem.</p>

<h3>💾 Você é responsável pelos seus dados</h3>
<p>Como não há servidor guardando uma cópia, recomendamos:</p>
<ul>
<li>Usar o sistema em <b>mais de um aparelho</b>: se um for perdido, os
dados continuam nos outros.</li>
<li>Fazer <b>backup</b> exportando os dados e guardando o arquivo em local
seguro.</li>
</ul>
<p>O arquivo de backup é <b>cifrado</b> com a frase que você escolher. Você
pode guardá-lo até na nuvem sem risco: só quem tem a frase consegue abri-lo.
Se perder todos os aparelhos, crie um novo login no app, importe o backup e
digite a frase do backup para recuperar tudo.</p>

<h3>🔌 Portas de rede usadas</h3>
<ul>
<li><b>Portas locais:</b> o app escuta em UDP <b>33700 a 33799</b> (faixa
própria, para não conflitar com outros programas Tox). Não abre servidor
TCP local.</li>
<li><b>Saída pela internet:</b> conecta a nós públicos da rede Tox, em
geral por UDP 33445. Se a rede bloquear essa porta, o app passa
automaticamente para relays <b>TCP, tentando primeiro a porta 443</b>
(a porta do HTTPS, que quase nenhuma rede bloqueia) e depois 3389 ou
33445.</li>
<li><b>Porta 53:</b> é possível usar a porta 53 (a do DNS) por meio de um
nó Tox seu, configurado em <code>dados/tox_financeiro/nos_proprios.json</code>.
Os nós públicos normalmente não atendem na 53.</li>
<li><b>Rede local:</b> aparelhos na mesma rede se encontram sozinhos,
sem internet.</li>
</ul>
<p>Isso torna o bloqueio bem mais difícil, mas <b>não é garantia
absoluta contra censura</b>: uma rede que analisa o tráfego pode reconhecer
o protocolo Tox mesmo na porta 443. O app é apenas uma ferramenta de gestão
financeira, e todo o conteúdo continua cifrado de ponta a ponta.</p>

<h3>🚫 O que NÃO coletamos</h3>
<ul>
<li>Não coletamos <b>nenhum dado</b> dos seus aparelhos.</li>
<li>Não coletamos seus dados financeiros.</li>
<li>Não vendemos nada, não temos anúncios, não rastreamos você.</li>
<li>O app só enxerga a rede o necessário para se comunicar com os seus
próprios aparelhos (por exemplo, o nome do computador na rede).</li>
</ul>

<h3>🧪 Verificação independente</h3>
<p>Você pode verificar o comportamento do app: monitore o tráfego da sua
rede, examine as portas abertas ou rode o app com
<code>--autoteste</code> para conferir seus componentes. O app é descentralizado
e tem um único objetivo: gerenciar finanças com segurança.
Especialistas são bem-vindos para analisar.</p>

<h3>🛠️ Recursos planejados</h3>
<p><b>Importação de extratos em CSV</b> (além do PDF atual).</p>
<p><b>Extrato online (opcional):</b> será possível conectar um serviço de
terceiros que fornece os extratos do seu banco automaticamente, sem importar
arquivos. Quando existir, funcionará assim:</p>
<ul>
<li>É <b>opcional</b>. Você cria sua própria conta no serviço de terceiros,
configura seu banco lá e autoriza o app.</li>
<li><b>Ninguém tem acesso ao seu login</b> desse serviço: nem o
desenvolvedor. O app só se conecta depois da sua permissão.</li>
<li>O acesso fica salvo, cifrado, para você não precisar entrar de novo, e
a configuração é sincronizada (também cifrada) com seus outros
aparelhos.</li>
<li>Você pode <b>desconectar a qualquer momento</b>.</li>
<li>Esses serviços são de terceiros e podem ser pagos, com termos próprios.</li>
</ul>
<p><i>Os itens desta seção ainda não estão disponíveis.</i></p>
"""


class TransparenciaDialog(QDialog):
    """Explica ao usuário como o sistema funciona e o que ele não faz."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Transparência")
        self.setMinimumSize(620, 560)
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)

        layout = QVBoxLayout(self)
        self.texto = QTextBrowser()
        self.texto.setOpenExternalLinks(True)
        self.texto.setHtml(TRANSPARENCIA_HTML)
        layout.addWidget(self.texto, 1)

        fechar = QPushButton("Fechar")
        fechar.setFixedHeight(36)
        fechar.clicked.connect(self.accept)
        layout.addWidget(fechar, 0, Qt.AlignCenter)
        self.apply_theme()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QTextBrowser { background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; padding: 8px; }
                QPushButton { background-color: #3498db; color: white;
                    border-radius: 4px; padding: 6px 18px;
                    font-weight: bold; }
                QPushButton:hover { background-color: #2980b9; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #fafafa; color: #333; }
                QTextBrowser { background-color: white; color: #333;
                    border: 1px solid #ddd; padding: 8px; }
                QPushButton { background-color: #4CAF50; color: white;
                    border-radius: 4px; padding: 6px 18px;
                    font-weight: bold; }
                QPushButton:hover { background-color: #45a049; }
            """)


class DonateDialog(QDialog):
    """
    Diálogo para exibir informações de doação ao desenvolvedor.
    Exibe endereços de criptomoedas e chave PIX, e dá acesso à Transparência.
    """

    # ── Dados de doação ──────────────────────────────────────────
    PIX_KEY       = "donationrrfs@proton.me"          # ← Altere aqui
    BTC_ADDRESS   = "bc1qqz3l07skhpvh4k5dzhcgyh342c76f2y4vmka27"  # ← Altere aqui
    # Para ativar uma moeda: remova o '#' da linha e coloque o endereço real.
    #ETH_ADDRESS   = "0xSuaChaveRealEthereumAqui"  # ← Altere aqui
    #USDT_ADDRESS  = "TSuaChaveRealUSDTAqui"        # ← Altere aqui (TRC20)
    #LTC_ADDRESS   = "LSuaChaveRealLitecoinAqui"   # ← Altere aqui

    # (atributo, rótulo, cor). Só aparece quem tiver endereço definido.
    MOEDAS = [
        ("BTC_ADDRESS",  "₿  Bitcoin (BTC):",  "#f7931a"),
        ("ETH_ADDRESS",  "⟠  Ethereum (ETH):", "#627eea"),
        ("USDT_ADDRESS", "₮  USDT (TRC20):",   "#26a17b"),
        ("LTC_ADDRESS",  "Ł  Litecoin (LTC):", "#345d9d"),
    ]

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
        pix = getattr(self, 'PIX_KEY', '')
        if pix:
            layout.addWidget(
                self._make_section_title("🇧🇷  PIX (Brasil)")
            )
            layout.addWidget(
                self._make_address_row("Chave PIX:", pix, "#00a86b")
            )
            layout.addWidget(self._make_separator())

        # ── Criptomoedas (só as que têm endereço) ────────────────
        linhas = []
        for attr, rotulo, cor in self.MOEDAS:
            endereco = (getattr(self, attr, '') or '').strip()
            if endereco:
                linhas.append((rotulo, endereco, cor))
        if linhas:
            layout.addWidget(
                self._make_section_title("🪙  Criptomoedas")
            )
            for rotulo, endereco, cor in linhas:
                layout.addWidget(
                    self._make_address_row(rotulo, endereco, cor)
                )
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

        # ── Botões: Transparência | Fechar ───────────────────────
        botoes = QHBoxLayout()
        botoes.addStretch()
        transp_btn = QPushButton("🔍 Transparência")
        transp_btn.setFixedHeight(36)
        transp_btn.setToolTip(
            "Veja como o sistema funciona, o que ele faz e o que não faz"
        )
        transp_btn.clicked.connect(self.abrir_transparencia)
        botoes.addWidget(transp_btn)
        close_btn = QPushButton("Fechar")
        close_btn.setFixedHeight(36)
        close_btn.clicked.connect(self.accept)
        botoes.addWidget(close_btn)
        botoes.addStretch()
        layout.addLayout(botoes)

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

    def abrir_transparencia(self):
        TransparenciaDialog(self).exec_()

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

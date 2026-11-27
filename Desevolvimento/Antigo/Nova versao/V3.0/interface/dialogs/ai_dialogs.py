"""
Diálogos para configuração da API de IA
"""
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton,
    QMessageBox, QProgressDialog, QApplication
)
from PyQt5.QtCore import Qt

import requests
import urllib3

urllib3.disable_warnings()


class ApiConfigDialog(QDialog):
    """
    Diálogo para configurar a conexão com o servidor de IA.

    O usuário só precisa informar a API Key.
    Os endpoints (rede local e Tor) já estão definidos
    no código em modulos/financial_ai.py
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração da IA")
        self.setMinimumWidth(420)
        self.setMaximumWidth(500)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        # ── Widgets ──────────────────────────────────────────
        self.info_label = QLabel(
            "Para usar o Assistente IA, informe sua\n"
            "chave de acesso ao servidor de IA.\n\n"
            "O sistema detecta automaticamente se você\n"
            "está na rede local ou usando a rede Tor."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignLeft)

        self.api_key_label = QLabel("Chave de API (obrigatória):")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Cole aqui sua chave de acesso")
        self.api_key_input.setEchoMode(QLineEdit.Password)

        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(36)
        self.show_key_btn.setToolTip("Mostrar/ocultar chave")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(self._toggle_key_visibility)

        self.test_button = QPushButton("🔌 Testar Conexão")
        self.test_button.clicked.connect(self.test_connection)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)

        self.save_button = QPushButton("💾 Salvar")
        self.save_button.clicked.connect(self.save_config)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # ── Layout ───────────────────────────────────────────
        layout = QVBoxLayout()
        layout.setSpacing(12)

        layout.addWidget(self.info_label)

        # Linha da chave com botão de mostrar/ocultar
        key_layout = QHBoxLayout()
        key_layout.addWidget(self.api_key_input)
        key_layout.addWidget(self.show_key_btn)

        form = QFormLayout()
        form.addRow(self.api_key_label)
        form.addRow(key_layout)
        layout.addLayout(form)

        layout.addWidget(self.test_button)
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.save_button)
        btn_layout.addWidget(self.cancel_button)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        # Carregar chave salva
        self._load_api_key()
        self.apply_theme(self.is_dark_mode)

    # ── Tema ─────────────────────────────────────────────────

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    margin-top: 4px;
                }
                QLineEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                    font-size: 13px;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QPushButton:checked { background-color: #2c3e50; }
            """)
            self.save_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
            self.test_button.setStyleSheet(
                "background-color: #f39c12; color: #ecf0f1;"
            )
            self.info_label.setStyleSheet(
                "color: #b2bec3; font-style: italic; "
                "background-color: #2d3436; padding: 10px; "
                "border-radius: 5px;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { margin-top: 4px; }
                QLineEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                    font-size: 13px;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:checked { background-color: #e0e0e0; }
            """)
            self.save_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )
            self.test_button.setStyleSheet(
                "background-color: #FF9800; color: white;"
            )
            self.info_label.setStyleSheet(
                "color: #555; font-style: italic; "
                "background-color: #e3f2fd; padding: 10px; "
                "border-radius: 5px;"
            )

    # ── Utilitários ──────────────────────────────────────────

    def _toggle_key_visibility(self, checked):
        """Mostra ou oculta o texto da chave"""
        self.api_key_input.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )

    def _set_status(self, message, color="gray"):
        """Atualiza o label de status com cor"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold; padding: 4px;"
        )

    def _has_db(self):
        """Verifica se o parent tem banco de dados configurado"""
        return (
            hasattr(self.parent(), 'db_connection') and
            hasattr(self.parent(), 'user_id')
        )

    # ── Carregar / Salvar ────────────────────────────────────

    def _load_api_key(self):
        """Carrega a API Key salva no banco de dados"""
        if not self._has_db():
            return

        try:
            row = self.parent().db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'ai_api_key'""",
                (self.parent().user_id,)
            ).fetchone()

            if row:
                self.api_key_input.setText(row[0])

        except Exception as e:
            print(f"[ApiConfigDialog] Erro ao carregar API Key: {e}")

    def _save_setting(self, key, value):
        """Salva ou atualiza uma configuração no banco de dados"""
        existing = self.parent().db_connection.execute(
            "SELECT id FROM user_settings "
            "WHERE user_id = ? AND setting_key = ?",
            (self.parent().user_id, key)
        ).fetchone()

        if existing:
            self.parent().db_connection.execute(
                "UPDATE user_settings SET setting_value = ? "
                "WHERE user_id = ? AND setting_key = ?",
                (value, self.parent().user_id, key)
            )
        else:
            self.parent().db_connection.execute(
                "INSERT INTO user_settings "
                "(user_id, setting_key, setting_value) "
                "VALUES (?, ?, ?)",
                (self.parent().user_id, key, value)
            )

    # ── Testar conexão ───────────────────────────────────────

    def test_connection(self):
        """
        Testa a conexão com o servidor de IA.

        Tenta primeiro a rede local (HTTPS),
        depois via Tor (HTTP onion).
        """
        api_key = self.api_key_input.text().strip()

        if not api_key:
            QMessageBox.warning(
                self, "Aviso",
                "Informe a Chave de API antes de testar a conexão."
            )
            return

        # Importar endpoints do módulo principal
        try:
            from modulos.financial_ai import LOCAL_URL, ONION_URL
        except ImportError:
            QMessageBox.critical(
                self, "Erro",
                "Módulo financial_ai não encontrado.\n"
                "Verifique se o arquivo existe em modulos/financial_ai.py"
            )
            return

        progress = QProgressDialog(
            "Testando conexão...", "Cancelar", 0, 0, self
        )
        progress.setWindowTitle("Testando")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        headers = {
            "X-API-Key":    api_key,
            "Content-Type": "application/json"
        }

        connected     = False
        network_used  = ""

        # 1) Tentar rede local (HTTPS)
        try:
            import urllib3
            urllib3.disable_warnings()

            session_local = requests.Session()
            session_local.verify = False
            session_local.headers.update(headers)

            resp = session_local.get(
                f"{LOCAL_URL}/api/status",
                timeout=5
            )

            if resp.status_code in (200, 401, 403):
                connected    = True
                network_used = f"Rede Local ({LOCAL_URL})"

        except Exception:
            pass

        # 2) Tentar via Tor se local falhou
        if not connected:
            try:
                import socks

                session_tor = requests.Session()
                session_tor.proxies = {
                    'http':  'socks5h://localhost:9050',
                    'https': 'socks5h://localhost:9050'
                }
                session_tor.headers.update(headers)

                resp = session_tor.get(
                    f"{ONION_URL}/api/status",
                    timeout=15
                )

                if resp.status_code in (200, 401, 403):
                    connected    = True
                    network_used = f"Rede Tor ({ONION_URL})"

            except Exception:
                pass

        progress.close()

        if connected:
            # Verificar se a chave é válida (200 = ok, 401/403 = chave errada)
            if resp.status_code == 200:
                self._set_status(
                    f"✅ Conectado via {network_used}", "green"
                )
                QMessageBox.information(
                    self, "Sucesso",
                    f"Conexão estabelecida!\n\nRede: {network_used}"
                )
            else:
                self._set_status(
                    "⚠️ Servidor encontrado, mas chave inválida", "orange"
                )
                QMessageBox.warning(
                    self, "Chave Inválida",
                    f"Servidor encontrado via {network_used}\n"
                    "mas a Chave de API foi rejeitada.\n\n"
                    "Verifique sua chave e tente novamente."
                )
        else:
            self._set_status("❌ Servidor não encontrado", "red")
            QMessageBox.critical(
                self, "Sem Conexão",
                "Não foi possível conectar ao servidor de IA.\n\n"
                "Verifique se:\n"
                "• Você está na rede local correta\n"
                "• O serviço Tor está ativo (se estiver fora)\n"
                "• O servidor de IA está online"
            )

    # ── Salvar configurações ─────────────────────────────────

    def save_config(self):
        """Salva a API Key no banco de dados"""
        api_key = self.api_key_input.text().strip()

        if not api_key:
            QMessageBox.warning(
                self, "Aviso",
                "A Chave de API é obrigatória para usar o Assistente IA."
            )
            return

        if not self._has_db():
            QMessageBox.warning(
                self, "Erro",
                "Não foi possível acessar o banco de dados."
            )
            return

        try:
            self._save_setting('ai_api_key', api_key)
            self.parent().db_connection.commit()

            self._set_status("✅ Configuração salva!", "green")
            QMessageBox.information(
                self, "Sucesso",
                "Chave de API salva com sucesso!\n\n"
                "O Assistente IA está pronto para uso."
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro",
                f"Erro ao salvar configuração:\n{str(e)}"
            )

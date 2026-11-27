"""
Diálogos para configuração da API de IA
"""
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QListWidget, QMessageBox, QProgressDialog, QApplication
)
from PyQt5.QtCore import Qt

import requests


class ApiConfigDialog(QDialog):
    """Diálogo para configurar a conexão com a API de IA"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração da API de IA")
        self.setMinimumWidth(500)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.endpoint_type_label = QLabel("Tipo de conexão:")
        self.endpoint_type_combo = QComboBox()
        self.endpoint_type_combo.addItems(["API HTTP", "Rede Tor (Onion)"])
        self.endpoint_type_combo.currentIndexChanged.connect(
            self.toggle_endpoint_type
        )

        self.host_label = QLabel("Endereço do servidor:")
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("localhost ou endereço IP ou URL")

        self.port_label = QLabel("Porta:")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("ex: 11434")

        self.onion_label = QLabel("Endereço Onion:")
        self.onion_input = QLineEdit()
        self.onion_input.setPlaceholderText("endereço.onion")
        self.onion_input.setEnabled(False)

        self.onion_port_label = QLabel("Porta Onion:")
        self.onion_port_input = QLineEdit()
        self.onion_port_input.setPlaceholderText("ex: 11434")
        self.onion_port_input.setEnabled(False)

        self.api_key_label = QLabel("API Key (opcional):")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText(
            "Deixe em branco se não for necessário"
        )

        self.test_button = QPushButton("Testar Conexão")
        self.test_button.clicked.connect(self.test_connection)

        self.model_list_label = QLabel("Modelos disponíveis:")
        self.model_list = QListWidget()
        self.model_list.setSelectionMode(QListWidget.SingleSelection)
        self.model_list.itemClicked.connect(self.on_model_selected)

        self.selected_model_label = QLabel("Modelo selecionado:")
        self.selected_model_input = QLineEdit()
        self.selected_model_input.setReadOnly(True)

        self.save_button = QPushButton("Salvar Configurações")
        self.save_button.clicked.connect(self.save_config)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.addRow(self.endpoint_type_label, self.endpoint_type_combo)
        form_layout.addRow(self.host_label, self.host_input)
        form_layout.addRow(self.port_label, self.port_input)
        form_layout.addRow(self.onion_label, self.onion_input)
        form_layout.addRow(self.onion_port_label, self.onion_port_input)
        form_layout.addRow(self.api_key_label, self.api_key_input)

        layout.addLayout(form_layout)
        layout.addWidget(self.test_button)
        layout.addWidget(QLabel(""))
        layout.addWidget(self.model_list_label)
        layout.addWidget(self.model_list)
        layout.addWidget(self.selected_model_label)
        layout.addWidget(self.selected_model_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.load_config()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox, QListWidget {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
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
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QLineEdit, QComboBox, QListWidget {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
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

    def toggle_endpoint_type(self, index):
        """Alterna entre conexão HTTP e Tor"""
        is_http = (index == 0)
        self.host_input.setEnabled(is_http)
        self.port_input.setEnabled(is_http)
        self.onion_input.setEnabled(not is_http)
        self.onion_port_input.setEnabled(not is_http)

    def on_model_selected(self, item):
        """Atualiza o campo de modelo selecionado"""
        self.selected_model_input.setText(item.text())

    def load_config(self):
        """Carrega as configurações salvas da API"""
        if not (
            hasattr(self.parent(), 'db_connection') and
            hasattr(self.parent(), 'user_id')
        ):
            return

        try:
            endpoint_config = self.parent().db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'ai_endpoint_config'""",
                (self.parent().user_id,)
            ).fetchone()

            if endpoint_config:
                config = json.loads(endpoint_config[0])

                if config.get('type') == 'tor':
                    self.endpoint_type_combo.setCurrentIndex(1)
                    self.onion_input.setText(config.get('onion', ''))
                    self.onion_port_input.setText(
                        str(config.get('onion_port', ''))
                    )
                else:
                    self.endpoint_type_combo.setCurrentIndex(0)
                    self.host_input.setText(config.get('host', ''))
                    self.port_input.setText(str(config.get('port', '')))

                self.api_key_input.setText(config.get('api_key', ''))

            selected_model = self.parent().db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'ai_selected_model'""",
                (self.parent().user_id,)
            ).fetchone()

            if selected_model:
                self.selected_model_input.setText(selected_model[0])

        except Exception as e:
            print(f"Erro ao carregar config: {e}")

    def test_connection(self):
        """Testa a conexão com a API"""
        try:
            self.model_list.clear()

            if self.endpoint_type_combo.currentIndex() == 0:
                host = self.host_input.text().strip()
                if not host:
                    QMessageBox.warning(
                        self, "Erro",
                        "Por favor, informe o endereço do servidor."
                    )
                    return

                try:
                    port = int(self.port_input.text().strip())
                except ValueError:
                    QMessageBox.warning(
                        self, "Erro", "Por favor, informe uma porta válida."
                    )
                    return

                base_url = f"http://{host}:{port}"
                use_tor = False
            else:
                onion = self.onion_input.text().strip()
                if not onion:
                    QMessageBox.warning(
                        self, "Erro",
                        "Por favor, informe o endereço onion."
                    )
                    return

                try:
                    onion_port = int(self.onion_port_input.text().strip())
                except ValueError:
                    QMessageBox.warning(
                        self, "Erro",
                        "Por favor, informe uma porta válida para o onion."
                    )
                    return

                base_url = f"http://{onion}:{onion_port}"
                use_tor = True

            api_key = self.api_key_input.text().strip()

            progress = QProgressDialog(
                "Testando conexão...", "Cancelar", 0, 0, self
            )
            progress.setWindowTitle("Teste de Conexão")
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            QApplication.processEvents()

            try:
                session = requests.Session()
                if use_tor:
                    session.proxies = {
                        'http': 'socks5h://localhost:9050',
                        'https': 'socks5h://localhost:9050'
                    }

                headers = {}
                if api_key:
                    headers['Authorization'] = f'Bearer {api_key}'

                response = session.get(
                    f"{base_url}/api/tags",
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()

                models_data = response.json()

                if (isinstance(models_data, dict) and
                        'models' in models_data):
                    models = [m['name'] for m in models_data['models']]
                elif isinstance(models_data, list):
                    models = [
                        m['name'] if isinstance(m, dict) and 'name' in m
                        else str(m)
                        for m in models_data
                    ]
                else:
                    raise ValueError("Formato de resposta não reconhecido")

                for model in models:
                    self.model_list.addItem(model)

                if self.selected_model_input.text():
                    matching = self.model_list.findItems(
                        self.selected_model_input.text(),
                        Qt.MatchExactly
                    )
                    if matching:
                        self.model_list.setCurrentItem(matching[0])

                QMessageBox.information(
                    self, "Sucesso",
                    f"Conexão estabelecida!\n{len(models)} modelos encontrados."
                )

            except Exception as e:
                QMessageBox.critical(
                    self, "Erro",
                    f"Não foi possível conectar à API: {str(e)}"
                )
            finally:
                progress.close()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro", f"Erro ao testar conexão: {str(e)}"
            )

    def save_config(self):
        """Salva as configurações da API"""
        selected_items = self.model_list.selectedItems()
        if not selected_items:
            if not self.selected_model_input.text():
                QMessageBox.warning(
                    self, "Aviso",
                    "Por favor, selecione um modelo de IA."
                )
                return

        selected_model = (
            selected_items[0].text()
            if selected_items
            else self.selected_model_input.text()
        )
        self.selected_model_input.setText(selected_model)

        config = {}
        if self.endpoint_type_combo.currentIndex() == 0:
            config['type'] = 'http'
            config['host'] = self.host_input.text().strip()
            try:
                config['port'] = int(self.port_input.text().strip())
            except ValueError:
                QMessageBox.warning(
                    self, "Erro", "Por favor, informe uma porta válida."
                )
                return
        else:
            config['type'] = 'tor'
            config['onion'] = self.onion_input.text().strip()
            try:
                config['onion_port'] = int(
                    self.onion_port_input.text().strip()
                )
            except ValueError:
                QMessageBox.warning(
                    self, "Erro",
                    "Por favor, informe uma porta válida para o onion."
                )
                return

        api_key = self.api_key_input.text().strip()
        if api_key:
            config['api_key'] = api_key

        if not (
            hasattr(self.parent(), 'db_connection') and
            hasattr(self.parent(), 'user_id')
        ):
            QMessageBox.warning(
                self, "Erro", "Não foi possível salvar as configurações."
            )
            return

        try:
            config_json = json.dumps(config)

            self._save_setting('ai_endpoint_config', config_json)
            self._save_setting('ai_selected_model', selected_model)

            self.parent().db_connection.commit()
            QMessageBox.information(
                self, "Sucesso", "Configurações salvas com sucesso!"
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro", f"Erro ao salvar configurações: {str(e)}"
            )

    def _save_setting(self, key, value):
        """Salva ou atualiza uma configuração no banco de dados"""
        existing = self.parent().db_connection.execute(
            "SELECT id FROM user_settings WHERE user_id = ? AND setting_key = ?",
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
                "INSERT INTO user_settings (user_id, setting_key, setting_value) "
                "VALUES (?, ?, ?)",
                (self.parent().user_id, key, value)
            )

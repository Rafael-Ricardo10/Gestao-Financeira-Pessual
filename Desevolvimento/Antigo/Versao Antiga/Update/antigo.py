import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QDateEdit, QDialog, QTabWidget, QGroupBox, QRadioButton, QTextEdit, QFileDialog
from PyQt5.QtCore import Qt, QDate
import sqlite3
from datetime import datetime
import os
import matplotlib.pyplot as plt
import requests
import json
import socket
import subprocess
import threading

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações de IA")
        self.setGeometry(200, 200, 500, 400)

        # Layout principal
        layout = QVBoxLayout()

        # Grupo para configuração de servidores
        server_group = QGroupBox("Configuração de Servidores")
        server_layout = QVBoxLayout()

        # Configuração do servidor local
        local_label = QLabel("Servidor Ollama Local:")
        self.local_ip_input = QLineEdit()
        self.local_ip_input.setPlaceholderText("Endereço IP (ex: 192.168.1.100)")
        self.local_port_input = QLineEdit()
        self.local_port_input.setPlaceholderText("Porta (ex: 11434)")

        local_layout = QHBoxLayout()
        local_layout.addWidget(self.local_ip_input)
        local_layout.addWidget(self.local_port_input)

        # Configuração do servidor Tor (rede onion)
        tor_label = QLabel("Servidor Ollama via Tor (endereço .onion):")
        self.tor_address_input = QLineEdit()
        self.tor_address_input.setPlaceholderText("Endereço .onion")
        self.tor_port_input = QLineEdit()
        self.tor_port_input.setPlaceholderText("Porta")

        tor_layout = QHBoxLayout()
        tor_layout.addWidget(self.tor_address_input)
        tor_layout.addWidget(self.tor_port_input)

        # Opções de seleção automática
        auto_select_label = QLabel("Seleção Automática:")
        self.auto_select_checkbox = QRadioButton("Detectar e selecionar servidor automaticamente")
        self.auto_select_checkbox.setChecked(True)
        self.manual_select_checkbox = QRadioButton("Selecionar servidor manualmente")

        # Selecionar modelo de IA
        model_label = QLabel("Modelo de IA:")
        self.model_combobox = QComboBox()
        self.model_combobox.setPlaceholderText("Selecione um modelo de IA")

        # Botão para buscar modelos disponíveis
        self.fetch_models_button = QPushButton("Buscar Modelos Disponíveis")
        self.fetch_models_button.clicked.connect(self.fetch_available_models)

        # Adicionar widgets ao layout do grupo
        server_layout.addWidget(local_label)
        server_layout.addLayout(local_layout)
        server_layout.addWidget(tor_label)
        server_layout.addLayout(tor_layout)
        server_layout.addWidget(auto_select_label)
        server_layout.addWidget(self.auto_select_checkbox)
        server_layout.addWidget(self.manual_select_checkbox)
        server_layout.addWidget(model_label)
        server_layout.addWidget(self.model_combobox)
        server_layout.addWidget(self.fetch_models_button)

        server_group.setLayout(server_layout)

        # Botões de ação
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_config)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        # Adicionar widgets ao layout principal
        layout.addWidget(server_group)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Carregar configurações salvas
        self.load_config()

    def load_config(self):
        # Carregar configurações do banco de dados
        if os.path.exists("ai_config.json"):
            try:
                with open("ai_config.json", "r") as f:
                    config = json.load(f)

                    # Preencher campos com valores salvos
                    self.local_ip_input.setText(config.get("local_ip", ""))
                    self.local_port_input.setText(config.get("local_port", ""))
                    self.tor_address_input.setText(config.get("tor_address", ""))
                    self.tor_port_input.setText(config.get("tor_port", ""))

                    # Configurar seleção automática
                    if config.get("auto_select", True):
                        self.auto_select_checkbox.setChecked(True)
                    else:
                        self.manual_select_checkbox.setChecked(True)

                    # Salvar o modelo selecionado para definir depois de buscar os modelos
                    self.saved_model = config.get("selected_model", "")
            except:
                pass

    def save_config(self):
        # Salvar configurações no arquivo JSON
        config = {
            "local_ip": self.local_ip_input.text(),
            "local_port": self.local_port_input.text(),
            "tor_address": self.tor_address_input.text(),
            "tor_port": self.tor_port_input.text(),
            "auto_select": self.auto_select_checkbox.isChecked(),
            "selected_model": self.model_combobox.currentText()
        }

        with open("ai_config.json", "w") as f:
            json.dump(config, f)

        QMessageBox.information(self, "Sucesso", "Configurações salvas com sucesso.")
        self.accept()

    def fetch_available_models(self):
        # Tenta buscar modelos do servidor local primeiro
        local_ip = self.local_ip_input.text()
        local_port = self.local_port_input.text()

        if local_ip and local_port:
            try:
                url = f"http://{local_ip}:{local_port}/api/tags"
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    model_names = [model.get("name") for model in models]

                    # Atualizar combobox com os modelos disponíveis
                    self.model_combobox.clear()
                    self.model_combobox.addItems(model_names)

                    # Selecionar modelo previamente salvo, se existir
                    if hasattr(self, 'saved_model') and self.saved_model in model_names:
                        self.model_combobox.setCurrentText(self.saved_model)

                    QMessageBox.information(self, "Sucesso", f"Encontrados {len(model_names)} modelos no servidor local.")
                    return
            except Exception as e:
                print(f"Erro ao conectar ao servidor local: {e}")

        # Se falhar ou não houver servidor local configurado, tenta via Tor
        tor_address = self.tor_address_input.text()
        tor_port = self.tor_port_input.text()

        if tor_address and tor_port:
            try:
                # Configurar proxy SOCKS para Tor
                import socks
                import socket

                # Verificar se o Tor está em execução
                try:
                    subprocess.check_output(["systemctl", "is-active", "--quiet", "tor"])
                except:
                    QMessageBox.warning(self, "Aviso", "O serviço Tor não parece estar em execução. Iniciando...")
                    try:
                        subprocess.run(["systemctl", "start", "tor"])
                    except:
                        QMessageBox.critical(self, "Erro", "Não foi possível iniciar o serviço Tor. Verifique se está instalado.")
                        return

                # Configurar proxy SOCKS5 para Tor (porta padrão 9050)
                socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
                socket.socket = socks.socksocket

                # Tentar acessar o serviço .onion
                url = f"http://{tor_address}:{tor_port}/api/tags"
                response = requests.get(url, timeout=10)  # Timeout maior para Tor

                if response.status_code == 200:
                    models = response.json().get("models", [])
                    model_names = [model.get("name") for model in models]

                    # Atualizar combobox com os modelos disponíveis
                    self.model_combobox.clear()
                    self.model_combobox.addItems(model_names)

                    # Selecionar modelo previamente salvo, se existir
                    if hasattr(self, 'saved_model') and self.saved_model in model_names:
                        self.model_combobox.setCurrentText(self.saved_model)

                    QMessageBox.information(self, "Sucesso", f"Encontrados {len(model_names)} modelos no servidor Tor.")
                    return
            except Exception as e:
                print(f"Erro ao conectar via Tor: {e}")
                QMessageBox.warning(self, "Aviso", f"Não foi possível conectar ao servidor via Tor: {str(e)}")

        QMessageBox.warning(self, "Aviso", "Não foi possível conectar a nenhum servidor Ollama. Verifique suas configurações.")


class AIAssistant:
    def __init__(self):
        self.config = self.load_config()
        self.current_server = None
        self.selected_model = self.config.get("selected_model", "")

    def load_config(self):
        # Carregar configurações do arquivo
        if os.path.exists("ai_config.json"):
            try:
                with open("ai_config.json", "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def detect_server(self):
        # Tenta detectar qual servidor está disponível
        config = self.load_config()

        # Se não for automático, usa o servidor manual configurado
        if not config.get("auto_select", True):
            return "manual"

        # Tenta conectar ao servidor local
        local_ip = config.get("local_ip", "")
        local_port = config.get("local_port", "")

        if local_ip and local_port:
            try:
                # Verifica se o servidor local está acessível
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((local_ip, int(local_port)))
                sock.close()

                if result == 0:
                    self.current_server = "local"
                    return "local"
            except:
                pass

        # Se o local falhar, tenta via Tor
        tor_address = config.get("tor_address", "")
        tor_port = config.get("tor_port", "")

        if tor_address and tor_port:
            try:
                # Verificar se o Tor está em execução
                try:
                    subprocess.check_output(["systemctl", "is-active", "--quiet", "tor"])
                    self.current_server = "tor"
                    return "tor"
                except:
                    pass
            except:
                pass

        return None

    def get_server_url(self):
        # Retorna a URL base do servidor atual
        config = self.load_config()
        server_type = self.detect_server()

        if server_type == "local" or (server_type == "manual" and not config.get("auto_select", True)):
            return f"http://{config.get('local_ip', '')}:{config.get('local_port', '')}"
        elif server_type == "tor":
            # Configurar proxy SOCKS para Tor
            import socks
            import socket
            socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
            socket.socket = socks.socksocket

            return f"http://{config.get('tor_address', '')}:{config.get('tor_port', '')}"

        return None

    def ask_ai(self, prompt, context=None, callback=None):
        """
        Envia uma pergunta para a IA e retorna a resposta

        Args:
            prompt (str): A pergunta ou instrução para a IA
            context (str, optional): Contexto adicional para a IA
            callback (function, optional): Função de callback para streaming

        Returns:
            str: Resposta da IA ou mensagem de erro
        """
        server_url = self.get_server_url()
        if not server_url:
            return "Não foi possível conectar a um servidor Ollama. Verifique suas configurações."

        model = self.selected_model
        if not model:
            return "Nenhum modelo de IA selecionado. Configure nas opções de IA."

        try:
            url = f"{server_url}/api/generate"

            # Se tiver contexto, incluir no prompt
            full_prompt = prompt
            if context:
                full_prompt = f"Contexto financeiro:\n{context}\n\nNOTA IMPORTANTE: Leia cuidadosamente o contexto acima, prestando atenção se as transações são RECEITAS (entradas) ou DESPESAS (saídas).\n\nCom base nesse contexto, {prompt}"

            # Se tiver callback, usar streaming
            if callback:
                payload = {
                    "model": model,
                    "prompt": full_prompt,
                    "stream": True
                }

                # Iniciar a resposta completa
                full_response = ""

                # Fazer solicitação com streaming
                with requests.post(url, json=payload, stream=True, timeout=120) as response:
                    if response.status_code != 200:
                        return f"Erro ao comunicar com a IA: {response.status_code} - {response.text}"

                    # Processar cada linha da resposta
                    for line in response.iter_lines():
                        if line:
                            json_response = json.loads(line)
                            chunk = json_response.get("response", "")
                            full_response += chunk
                            # Chamar o callback com o texto acumulado até agora
                            callback(full_response)

                return full_response
            else:
                # Versão sem streaming para compatibilidade
                payload = {
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False
                }

                response = requests.post(url, json=payload, timeout=120)

                if response.status_code == 200:
                    response_json = response.json()
                    return response_json.get("response", "Sem resposta da IA")
                else:
                    return f"Erro ao comunicar com a IA: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Erro ao comunicar com o servidor: {str(e)}"

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestão Financeira Pessoal")
        self.setGeometry(100, 100, 800, 600)

        # Criar pasta 'dados' se não existir
        if not os.path.exists('dados'):
            os.makedirs('dados')

        self.db_connection = None
        self.user_id = None
        self.selected_year = datetime.now().year

        # Inicializar o assistente de IA
        self.ai_assistant = AIAssistant()

        # Widgets para login
        self.username_label = QLabel("Usuário:")
        self.username_input = QLineEdit()
        self.password_label = QLabel("Senha:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.login_button = QPushButton("Login")
        self.register_button = QPushButton("Registrar")
        self.save_login_button = QPushButton("Salvar Login")

        # Widgets para dashboard
        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(6)
        self.transactions_table.setHorizontalHeaderLabels(["ID", "Descrição", "Valor", "Tipo", "Data", "Categoria"])

        self.add_transaction_button = QPushButton("Adicionar Transação")
        self.edit_transaction_button = QPushButton("Editar Transação")
        self.delete_transaction_button = QPushButton("Excluir Transação")

        self.notes_table = QTableWidget()
        self.notes_table.setColumnCount(2)
        self.notes_table.setHorizontalHeaderLabels(["ID", "Nota"])

        self.add_note_button = QPushButton("Adicionar Nota")
        self.edit_note_button = QPushButton("Editar Nota")
        self.delete_note_button = QPushButton("Excluir Nota")

        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(2)
        self.categories_table.setHorizontalHeaderLabels(["ID", "Nome"])

        self.add_category_button = QPushButton("Adicionar Categoria")
        self.edit_category_button = QPushButton("Editar Categoria")
        self.delete_category_button = QPushButton("Excluir Categoria")

        self.balance_label = QLabel("Saldo: R$ 0.00")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Pesquisar por descrição ou categoria...")
        self.search_input.textChanged.connect(self.load_transactions)

        self.year_buttons_layout = QHBoxLayout()

        self.logout_button = QPushButton("Sair")
        self.logout_button.clicked.connect(self.logout)

        # Botão de configuração da IA
        self.ai_config_button = QPushButton("Configurar IA")
        self.ai_config_button.clicked.connect(self.show_ai_config)

        # Botão de consulta à IA
        self.ai_query_button = QPushButton("Consultar IA")
        self.ai_query_button.clicked.connect(self.show_ai_query_dialog)

        # Layout principal
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Criar o layout de login inicialmente
        self.login_layout = self.create_login_layout()
        self.main_layout.addLayout(self.login_layout)

        # Carregar login salvo ao iniciar o aplicativo
        self.load_saved_login()

        # Conectar sinais aos slots
        self.login_button.clicked.connect(self.login)
        self.register_button.clicked.connect(self.register)
        self.add_transaction_button.clicked.connect(self.show_add_transaction_dialog)
        self.edit_transaction_button.clicked.connect(self.show_edit_transaction_dialog)
        self.delete_transaction_button.clicked.connect(self.delete_transaction)
        self.add_note_button.clicked.connect(self.show_add_note_dialog)
        self.edit_note_button.clicked.connect(self.show_edit_note_dialog)
        self.delete_note_button.clicked.connect(self.delete_note)
        self.add_category_button.clicked.connect(self.show_add_category_dialog)
        self.edit_category_button.clicked.connect(self.show_edit_category_dialog)
        self.delete_category_button.clicked.connect(self.delete_category)
        self.save_login_button.clicked.connect(self.save_login)

    def show_ai_config(self):
        # Mostrar diálogo de configuração da IA
        dialog = ConfigDialog(self)
        dialog.exec_()

        # Atualizar o assistente de IA com as novas configurações
        self.ai_assistant = AIAssistant()

    def show_ai_query_dialog(self):
        # Mostrar diálogo para consultar a IA
        dialog = AIQueryDialog(self)
        dialog.exec_()

    def create_login_layout(self):
        # Layout de login
        login_layout = QVBoxLayout()
        login_layout.addWidget(self.username_label)
        login_layout.addWidget(self.username_input)
        login_layout.addWidget(self.password_label)
        login_layout.addWidget(self.password_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.register_button)
        button_layout.addWidget(self.save_login_button)

        login_layout.addLayout(button_layout)

        return login_layout

    def get_db_path(self, username):
        # Caminho para o banco de dados do usuário
        return os.path.join('dados', f'{username}.db')

    def create_tables(self):
        # Criar tabelas no banco de dados
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS users
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         username TEXT UNIQUE NOT NULL,
                         password TEXT NOT NULL)''')
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS transactions
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         amount REAL NOT NULL,
                         description TEXT NOT NULL,
                         transaction_type TEXT NOT NULL,
                         date TEXT NOT NULL,
                         category_id INTEGER,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         FOREIGN KEY (category_id) REFERENCES categories (id))''')
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS notes
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         note TEXT NOT NULL,
                         FOREIGN KEY (user_id) REFERENCES users (id))''')
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS categories
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         name TEXT UNIQUE NOT NULL,
                         FOREIGN KEY (user_id) REFERENCES users (id))''')

    def login(self):
        # Função de login
        username = self.username_input.text()
        password = self.password_input.text()

        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        user = self.db_connection.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                            (username, password)).fetchone()
        if user:
            self.user_id = user['id']
            # Remover o layout de login
            self.clear_layout(self.main_layout)
            self.load_dashboard()
        else:
            QMessageBox.warning(self, "Erro", "Usuário ou senha incorretos.")
            self.db_connection.close()

    def register(self):
        # Função de registro
        username = self.username_input.text()
        password = self.password_input.text()

        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        self.create_tables()

        try:
            self.db_connection.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                     (username, password))
            self.db_connection.commit()
            QMessageBox.information(self, "Sucesso", "Usuário registrado com sucesso.")
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Erro", "Nome de usuário já existe.")
        finally:
            self.db_connection.close()

    def load_dashboard(self):
        # Carregar layout do dashboard
        dashboard_layout = QVBoxLayout()
        dashboard_layout.addWidget(self.transactions_table)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_input)
        dashboard_layout.addLayout(search_layout)

        dashboard_layout.addLayout(self.year_buttons_layout)

        transaction_button_layout = QHBoxLayout()
        transaction_button_layout.addWidget(self.add_transaction_button)
        transaction_button_layout.addWidget(self.edit_transaction_button)
        transaction_button_layout.addWidget(self.delete_transaction_button)

        dashboard_layout.addLayout(transaction_button_layout)

        dashboard_layout.addWidget(self.notes_table)

        note_button_layout = QHBoxLayout()
        note_button_layout.addWidget(self.add_note_button)
        note_button_layout.addWidget(self.edit_note_button)
        note_button_layout.addWidget(self.delete_note_button)

        dashboard_layout.addLayout(note_button_layout)

        dashboard_layout.addWidget(self.categories_table)

        category_button_layout = QHBoxLayout()
        category_button_layout.addWidget(self.add_category_button)
        category_button_layout.addWidget(self.edit_category_button)
        category_button_layout.addWidget(self.delete_category_button)

        dashboard_layout.addLayout(category_button_layout)

        dashboard_layout.addWidget(self.balance_label)

        # Adicionar botões para relatórios e gráficos ao dashboard
        report_button = QPushButton("Gerar Relatório")
        report_button.clicked.connect(self.generate_category_report)
        dashboard_layout.addWidget(report_button)

        graph_button = QPushButton("Gerar Gráfico")
        graph_button.clicked.connect(self.generate_category_graph)
        dashboard_layout.addWidget(graph_button)

        export_report_button = QPushButton("Exportar Relatório")
        export_report_button.clicked.connect(self.export_report)
        dashboard_layout.addWidget(export_report_button)

        # Adicionar botões de IA ao dashboard
        ai_button_layout = QHBoxLayout()
        ai_button_layout.addWidget(self.ai_config_button)
        ai_button_layout.addWidget(self.ai_query_button)
        dashboard_layout.addLayout(ai_button_layout)

        # Adicionar botão de logout
        dashboard_layout.addWidget(self.logout_button)

        # Adicionar o layout do dashboard ao layout principal
        self.main_layout.addLayout(dashboard_layout)

        self.load_transactions()
        self.load_notes()
        self.load_categories()
        self.update_balance()
        self.update_year_buttons()  # Atualizar botões de ano

    def export_report(self):
        # Obter transações do usuário para o ano selecionado
        transactions = self.db_connection.execute(
            """
            SELECT t.*, c.name AS category_name
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            ORDER BY t.date ASC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        # Montar o conteúdo do relatório
        report_lines = []
        report_lines.append(f"RELATÓRIO DE TRANSAÇÕES - Ano: {self.selected_year}")
        report_lines.append("=" * 50)
        report_lines.append("ID | Descrição | Valor | Tipo | Data | Categoria")
        report_lines.append("-" * 50)

        for t in transactions:
            line = f"{t['id']} | {t['description']} | R$ {t['amount']:.2f} | {t['transaction_type']} | {t['date']} | {t['category_name']}"
            report_lines.append(line)

        report_lines.append("=" * 50)
        report_lines.append("RESUMO POR CATEGORIA")

        # Consultar o resumo de gastos por categoria para o ano selecionado
        categories = self.db_connection.execute(
            """
            SELECT c.name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            GROUP BY c.name
            ORDER BY total_spent DESC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        for cat in categories:
            report_lines.append(f"{cat[0]}: R$ {cat[1]:.2f}")

        report_lines.append("=" * 50)

        # Informações de saldo geral
        transactions_all = self.db_connection.execute(
            'SELECT * FROM transactions WHERE user_id = ?', (self.user_id,)
        ).fetchall()
        entries_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'entrada')
        exits_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'saida')
        balance = entries_total - exits_total
        report_lines.append(f"Saldo Total: R$ {balance:.2f}")

        # Converter a lista de linhas em uma única string
        report_content = "\n".join(report_lines)

        # Abrir uma janela de diálogo para o usuário escolher onde salvar o arquivo
        from PyQt5.QtWidgets import QFileDialog  # Certifique-se de que já importou o QFileDialog no início do seu script
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório",
            f"relatorio_{self.selected_year}.txt",
            "Text Files (*.txt)"
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(report_content)
                QMessageBox.information(self, "Sucesso", f"Relatório exportado com sucesso!\nArquivo: {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Não foi possível exportar o relatório.\nErro: {str(e)}")

    def update_year_buttons(self):
        # Atualizar botões de ano com base nas transações
        while self.year_buttons_layout.count():
            child = self.year_buttons_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        years = self.db_connection.execute(
            '''
            SELECT DISTINCT strftime('%Y', date) as year
            FROM transactions
            WHERE user_id = ?
            ORDER BY year DESC
            ''', (self.user_id,)
        ).fetchall()

        for year in years:
            year_button = QPushButton(year['year'])
            year_button.setCheckable(True)
            year_button.setChecked(year['year'] == str(self.selected_year))
            year_button.toggled.connect(lambda checked, y=year['year']: self.toggle_year(y, checked))
            self.year_buttons_layout.addWidget(year_button)

    def toggle_year(self, year, checked):
        # Alternar ano selecionado
        if checked:
            self.selected_year = int(year)
        else:
            self.selected_year = datetime.now().year
        self.load_transactions()

    def load_transactions(self):
        # Carregar transações conforme o ano selecionado e texto de pesquisa
        search_text = self.search_input.text().lower()
        query = '''
            SELECT t.*, c.name AS category_name
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?'''

        if search_text:
            query += " AND (LOWER(t.description) LIKE ? OR LOWER(c.name) LIKE ?)"
            transactions = self.db_connection.execute(query, (self.user_id, str(self.selected_year), f'%{search_text}%', f'%{search_text}%')).fetchall()
        else:
            transactions = self.db_connection.execute(query, (self.user_id, str(self.selected_year))).fetchall()

        self.transactions_table.setRowCount(len(transactions))
        for i, transaction in enumerate(transactions):
            self.transactions_table.setItem(i, 0, QTableWidgetItem(str(transaction['id'])))
            self.transactions_table.setItem(i, 1, QTableWidgetItem(transaction['description']))
            self.transactions_table.setItem(i, 2, QTableWidgetItem(str(transaction['amount'])))
            self.transactions_table.setItem(i, 3, QTableWidgetItem(transaction['transaction_type']))
            self.transactions_table.setItem(i, 4, QTableWidgetItem(transaction['date']))
            self.transactions_table.setItem(i, 5, QTableWidgetItem(transaction['category_name']))

    def load_notes(self):
        # Carregar notas do usuário
        notes = self.db_connection.execute('SELECT * FROM notes WHERE user_id = ?', (self.user_id,)).fetchall()
        self.notes_table.setRowCount(len(notes))
        for i, note in enumerate(notes):
            self.notes_table.setItem(i, 0, QTableWidgetItem(str(note['id'])))
            self.notes_table.setItem(i, 1, QTableWidgetItem(note['note']))

    def load_categories(self):
        # Carregar categorias do usuário
        categories = self.db_connection.execute('SELECT * FROM categories WHERE user_id = ?', (self.user_id,)).fetchall()
        self.categories_table.setRowCount(len(categories))
        for i, category in enumerate(categories):
            self.categories_table.setItem(i, 0, QTableWidgetItem(str(category['id'])))
            self.categories_table.setItem(i, 1, QTableWidgetItem(category['name']))

    def update_balance(self):
        # Atualizar saldo do usuário
        transactions = self.db_connection.execute('SELECT * FROM transactions WHERE user_id = ?', (self.user_id,)).fetchall()
        entries_total = sum(transaction['amount'] for transaction in transactions if transaction['transaction_type'] == 'entrada')
        exits_total = sum(transaction['amount'] for transaction in transactions if transaction['transaction_type'] == 'saida')
        balance = entries_total - exits_total
        self.balance_label.setText(f"Saldo: R$ {balance:.2f}")

    def show_add_transaction_dialog(self):
        # Mostrar diálogo para adicionar transação
        dialog = AddTransactionDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_transactions()
            self.update_balance()
            self.update_year_buttons()  # Atualizar botões de ano

    def show_edit_transaction_dialog(self):
        # Mostrar diálogo para editar transação
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(self.transactions_table.item(selected_row, 0).text())
            dialog = EditTransactionDialog(self, transaction_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()  # Atualizar botões de ano

    def delete_transaction(self):
        # Deletar transação selecionada
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(self.transactions_table.item(selected_row, 0).text())
            self.db_connection.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
            self.db_connection.commit()
            self.load_transactions()
            self.update_balance()
            self.update_year_buttons()  # Atualizar botões de ano

    def show_add_note_dialog(self):
        # Mostrar diálogo para adicionar nota
        dialog = AddNoteDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_notes()

    def show_edit_note_dialog(self):
        # Mostrar diálogo para editar nota
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())
            dialog = EditNoteDialog(self, note_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_notes()

    def delete_note(self):
        # Deletar nota selecionada
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())
            self.db_connection.execute('DELETE FROM notes WHERE id = ?', (note_id,))
            self.db_connection.commit()
            self.load_notes()

    def show_add_category_dialog(self):
        # Mostrar diálogo para adicionar categoria
        dialog = AddCategoryDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_categories()

    def show_edit_category_dialog(self):
        # Mostrar diálogo para editar categoria
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(self.categories_table.item(selected_row, 0).text())
            dialog = EditCategoryDialog(self, category_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_categories()

    def delete_category(self):
        # Deletar categoria selecionada
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(self.categories_table.item(selected_row, 0).text())
            self.db_connection.execute('DELETE FROM categories WHERE id = ?', (category_id,))
            self.db_connection.commit()
            self.load_categories()

    def save_login(self):
        # Salvar login em um arquivo
        username = self.username_input.text()
        password = self.password_input.text()

        with open("login.txt", "w") as f:
            f.write(f"{username},{password}")

        QMessageBox.information(self, "Sucesso", "Login salvo com sucesso.")

    def load_saved_login(self):
        # Carregar login salvo do arquivo
        if os.path.exists("login.txt"):
            with open("login.txt", "r") as f:
                username, password = f.read().split(",")
                self.username_input.setText(username)
                self.password_input.setText(password)

    def generate_category_report(self):
        # Gerar relatório de gastos por categoria
        categories = self.db_connection.execute(
            """
            SELECT c.name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            GROUP BY c.name
            ORDER BY total_spent DESC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        report_dialog = QDialog(self)
        report_dialog.setWindowTitle("Relatório de Gastos por Categoria")
        report_layout = QVBoxLayout()

        report_table = QTableWidget(report_dialog)
        report_table.setColumnCount(2)
        report_table.setHorizontalHeaderLabels(["Categoria", "Total Gasto"])

        report_table.setRowCount(len(categories))
        for i, category in enumerate(categories):
            report_table.setItem(i, 0, QTableWidgetItem(category[0]))
            report_table.setItem(i, 1, QTableWidgetItem(f"R$ {category[1]:.2f}"))

        report_layout.addWidget(report_table)
        report_dialog.setLayout(report_layout)
        report_dialog.exec_()

    def generate_category_graph(self):
        # Gerar gráfico de gastos por categoria
        categories = self.db_connection.execute(
            """
            SELECT c.name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            GROUP BY c.name
            ORDER BY total_spent DESC
            """,
            (self.user_id, str(self.selected_year))
        ).fetchall()

        category_names = [category[0] for category in categories]
        total_spent = [category[1] for category in categories]

        plt.figure(figsize=(8, 6))
        plt.bar(category_names, total_spent)
        plt.xlabel("Categoria")
        plt.ylabel("Total Gasto")
        plt.title("Gastos por Categoria")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.show()

    def logout(self):
        # Função de logout
        if self.db_connection:
            self.db_connection.close()

        self.user_id = None

        # Limpar o layout do dashboard e voltar para o layout de login
        self.clear_layout(self.main_layout)

        self.login_layout = self.create_login_layout()
        self.main_layout.addLayout(self.login_layout)

    def clear_layout(self, layout):
        # Limpar todos os widgets de um layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self.clear_layout(child.layout())


class AIQueryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Consultar IA")
        self.setGeometry(200, 200, 700, 650)

        # Layout principal
        layout = QVBoxLayout()

        # Área para a pergunta
        query_label = QLabel("Faça sua pergunta à IA:")
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Ex: Analisar meus gastos do mês atual")
        self.query_input.returnPressed.connect(self.send_query)

        # Seleção de período para análise
        period_group = QGroupBox("Período para análise:")
        period_layout = QVBoxLayout()

        # Layout para ano/mês
        time_layout = QHBoxLayout()

        # Seleção de ano
        year_label = QLabel("Ano:")
        self.year_combo = QComboBox()
        # Preencher com anos disponíveis no banco de dados
        self.populate_years()

        # Seleção de mês
        month_label = QLabel("Mês:")
        self.month_combo = QComboBox()
        self.month_combo.addItems(["Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio",
                                  "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])

        # Adicionar ao layout
        time_layout.addWidget(year_label)
        time_layout.addWidget(self.year_combo)
        time_layout.addWidget(month_label)
        time_layout.addWidget(self.month_combo)

        # Adicionar ao grupo
        period_layout.addLayout(time_layout)
        period_group.setLayout(period_layout)

        # Botões de ação rápida
        quick_actions_group = QGroupBox("Ações Rápidas:")
        quick_actions_layout = QVBoxLayout()

        # Linha 1 - Análises gerais
        quick_row1 = QHBoxLayout()
        self.analyze_spending_button = QPushButton("Analisar Gastos")
        self.analyze_spending_button.clicked.connect(self.analyze_spending)
        self.budget_suggestion_button = QPushButton("Sugerir Orçamento")
        self.budget_suggestion_button.clicked.connect(self.suggest_budget)
        self.saving_tips_button = QPushButton("Dicas de Economia")
        self.saving_tips_button.clicked.connect(self.get_saving_tips)
        quick_row1.addWidget(self.analyze_spending_button)
        quick_row1.addWidget(self.budget_suggestion_button)
        quick_row1.addWidget(self.saving_tips_button)

        # Linha 2 - Análises específicas
        quick_row2 = QHBoxLayout()
        self.category_analysis_button = QPushButton("Análise por Categoria")
        self.category_analysis_button.clicked.connect(self.analyze_categories)
        self.trends_button = QPushButton("Tendências de Gastos")
        self.trends_button.clicked.connect(self.analyze_trends)
        self.investment_button = QPushButton("Sugestões de Investimento")
        self.investment_button.clicked.connect(self.suggest_investments)
        quick_row2.addWidget(self.category_analysis_button)
        quick_row2.addWidget(self.trends_button)
        quick_row2.addWidget(self.investment_button)

        # Adicionar linhas ao layout de ações rápidas
        quick_actions_layout.addLayout(quick_row1)
        quick_actions_layout.addLayout(quick_row2)
        quick_actions_group.setLayout(quick_actions_layout)

        # Área para a resposta
        response_label = QLabel("Resposta da IA:")
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("A resposta aparecerá aqui.")
        self.response_text.setStyleSheet("""
            background-color: #FFFFFF;
            color: #000000;
            padding: 10px;
            border: 1px solid #999999;
            border-radius: 5px;
            font-size: 12pt;
        """)
        self.response_text.setMinimumHeight(300)

        # Botão para enviar pergunta
        self.send_button = QPushButton("Enviar Pergunta")
        self.send_button.clicked.connect(self.send_query)
        self.send_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")

        # Botão para limpar resposta
        self.clear_button = QPushButton("Limpar")
        self.clear_button.clicked.connect(lambda: self.response_text.clear())

        # Botão de ajuda
        self.help_button = QPushButton("Sugestões de Consultas")
        self.help_button.clicked.connect(self.show_help)

        # Layout para botões de ação
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.help_button)

        # Adicionar widgets ao layout
        layout.addWidget(query_label)
        layout.addWidget(self.query_input)
        layout.addWidget(period_group)
        layout.addWidget(quick_actions_group)
        layout.addWidget(response_label)
        layout.addWidget(self.response_text)
        layout.addLayout(button_layout)

        # Status do servidor
        server_status = self.parent().ai_assistant.detect_server()
        if server_status:
            server_type = "local" if server_status == "local" else "Tor"
            self.status_label = QLabel(f"Conectado ao servidor {server_type}")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label = QLabel("Não conectado a nenhum servidor. Configure nas opções de IA.")
            self.status_label.setStyleSheet("color: red;")

        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def populate_years(self):
        """Preencher o combobox de anos com os anos disponíveis no banco de dados"""
        try:
            if not self.parent().db_connection:
                self.year_combo.addItem(str(datetime.now().year))
                return

            years = self.parent().db_connection.execute(
                '''
                SELECT DISTINCT strftime('%Y', date) as year
                FROM transactions
                WHERE user_id = ?
                ORDER BY year DESC
                ''', (self.parent().user_id,)
            ).fetchall()

            self.year_combo.addItem("Todos")
            for year in years:
                self.year_combo.addItem(year['year'])

            # Selecionar o ano atual por padrão
            current_year = str(datetime.now().year)
            index = self.year_combo.findText(current_year)
            if index >= 0:
                self.year_combo.setCurrentIndex(index)
        except:
            # Fallback para o ano atual
            self.year_combo.addItem(str(datetime.now().year))

    def get_financial_context(self):
        """Obter contexto financeiro do usuário com filtros de período"""
        if not self.parent().db_connection:
            return "Não há dados financeiros disponíveis."

        try:
            # Obter filtros de período
            selected_year = self.year_combo.currentText()
            selected_month = self.month_combo.currentIndex()  # 0 = Todos, 1-12 = meses

            # Construir condições de filtro
            year_condition = ""
            if selected_year != "Todos":
                year_condition = f"AND strftime('%Y', t.date) = '{selected_year}'"

            month_condition = ""
            if selected_month > 0:  # Se não for "Todos"
                month_condition = f"AND strftime('%m', t.date) = '{selected_month:02d}'"

            # Criar descrição do período para contexto
            period_description = "todos os registros"
            if selected_year != "Todos" and selected_month > 0:
                period_description = f"{self.month_combo.currentText()} de {selected_year}"
            elif selected_year != "Todos":
                period_description = f"ano de {selected_year}"
            elif selected_month > 0:
                period_description = f"{self.month_combo.currentText()} (todos os anos)"

            # Obter saldo no período
            query = f'''
                SELECT
                    SUM(CASE WHEN t.transaction_type = 'entrada' THEN t.amount ELSE 0 END) as total_income,
                    SUM(CASE WHEN t.transaction_type = 'saida' THEN t.amount ELSE 0 END) as total_expense
                FROM transactions t
                WHERE t.user_id = ? {year_condition} {month_condition}
            '''

            financials = self.parent().db_connection.execute(query, (self.parent().user_id,)).fetchone()

            total_income = financials['total_income'] or 0
            total_expense = financials['total_expense'] or 0
            balance = total_income - total_expense

            # Obter transações do período
            query = f'''
                SELECT t.*, c.name AS category_name
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? {year_condition} {month_condition}
                ORDER BY t.date DESC
                LIMIT 15
            '''

            transactions = self.parent().db_connection.execute(query, (self.parent().user_id,)).fetchall()

            # Obter gastos por categoria no período
            query = f'''
                SELECT c.name, SUM(t.amount) AS total_spent
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.transaction_type = 'saida' {year_condition} {month_condition}
                GROUP BY c.name
                ORDER BY total_spent DESC
            '''

            categories = self.parent().db_connection.execute(query, (self.parent().user_id,)).fetchall()

            # Montar o contexto com explicação clara
            context = f"RESUMO FINANCEIRO PARA {period_description.upper()}:\n"
            context += f"Total de receitas: R$ {total_income:.2f}\n"
            context += f"Total de despesas: R$ {total_expense:.2f}\n"
            context += f"Saldo no período: R$ {balance:.2f}\n\n"

            context += "IMPORTANTE: As transações abaixo mostram RECEITAS (dinheiro recebido) ou DESPESAS (dinheiro gasto).\n\n"

            context += f"Transações do período ({len(transactions)} mais recentes):\n"
            for t in transactions:
                tipo = "RECEITA" if t['transaction_type'] == 'entrada' else "DESPESA"
                context += f"- {t['date']}: {t['description']} - R$ {t['amount']:.2f} ({tipo}) {t['category_name'] or ''}\n"

            context += "\nDespesas por categoria (apenas saídas de dinheiro):\n"
            for cat in categories:
                percentage = (cat[1] / total_expense * 100) if total_expense > 0 else 0
                context += f"- {cat[0]}: R$ {cat[1]:.2f} ({percentage:.1f}% do total)\n"

            return context

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return f"Erro ao obter contexto financeiro: {str(e)}"

    def send_query(self):
        """Enviar pergunta para a IA"""
        query = self.query_input.text()
        if not query:
            self.response_text.setPlainText("Por favor, digite uma pergunta.")
            return

        # Verificar configurações
        if not self.parent().ai_assistant.selected_model:
            self.response_text.setPlainText("Erro: Nenhum modelo de IA selecionado. Configure nas opções de IA primeiro.")
            return

        server_status = self.parent().ai_assistant.detect_server()
        if not server_status:
            self.response_text.setPlainText("Erro: Nenhum servidor Ollama disponível. Configure nas opções de IA primeiro.")
            return

        # Mostrar processamento
        self.response_text.setPlainText("Processando consulta...\nEsta operação pode levar alguns segundos.")
        QApplication.processEvents()

        # Obter o período selecionado para incluir na consulta
        selected_year = self.year_combo.currentText()
        selected_month = self.month_combo.currentText()
        period_info = ""

        if selected_year != "Todos" and selected_month != "Todos":
            period_info = f" para {selected_month} de {selected_year}"
        elif selected_year != "Todos":
            period_info = f" para o ano de {selected_year}"
        elif selected_month != "Todos":
            period_info = f" para {selected_month} (todos os anos)"

        # Adicionar o período à consulta
        full_query = query
        if period_info and period_info not in query.lower():
            full_query = f"{query}{period_info}"

        print(f"Enviando consulta: {full_query}")

        try:
            context = self.get_financial_context()

            # Função de callback para atualização em tempo real
            def update_response(text):
                self.response_text.setPlainText(text)
                QApplication.processEvents()

            response = self.parent().ai_assistant.ask_ai(full_query, context, callback=update_response)
            print("Resposta completa recebida")
        except Exception as e:
            import traceback
            error_msg = f"Erro ao processar consulta: {str(e)}"
            self.response_text.setPlainText(error_msg)
            print(error_msg)
            print(traceback.format_exc())

    def show_help(self):
        """Mostrar sugestões de consultas possíveis"""
        help_text = """
<b>SUGESTÕES DE CONSULTAS PARA A IA FINANCEIRA</b>

<b>Análises Básicas:</b>
• Analise meus gastos
• Quais são minhas maiores despesas?
• Como está meu balanço de receitas e despesas?
• Identifique padrões em meus gastos

<b>Análises por Categoria:</b>
• Quais categorias consomem mais recursos?
• Como meus gastos com [categoria] se comparam com outras categorias?
• Meus gastos com [categoria] estão razoáveis?

<b>Análises por Período:</b>
• Como meus gastos mudaram ao longo do tempo?
• Qual foi o mês com maiores despesas?
• Compare meus gastos atuais com o mesmo período do ano passado

<b>Sugestões e Planejamento:</b>
• Sugira um orçamento baseado nos meus hábitos
• Como posso economizar em [categoria]?
• Quais despesas devo priorizar reduzir?
• Qual seria um bom valor para guardar mensalmente?

<b>Objetivos Financeiros:</b>
• Ajude-me a economizar para [objetivo]
• Quanto preciso economizar por mês para atingir [valor] em [tempo]?
• Como posso equilibrar minhas dívidas e poupança?

<b>Dicas:</b>
• Você pode selecionar ano e mês específicos antes de fazer sua consulta
• Seja específico sobre qual categoria ou período deseja analisar
• Experimente as ações rápidas para análises comuns
        """

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Sugestões de Consultas")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(help_text)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    # Ações rápidas
    def analyze_spending(self):
        """Analisar gastos no período selecionado"""
        self.query_input.setText("Analise meus gastos e identifique onde posso economizar")
        self.send_query()

    def suggest_budget(self):
        """Sugerir orçamento com base nos gastos"""
        self.query_input.setText("Sugira um orçamento mensal com base nos meus padrões de gastos")
        self.send_query()

    def get_saving_tips(self):
        """Obter dicas de economia"""
        self.query_input.setText("Dê-me dicas práticas para economizar nas categorias onde gasto mais")
        self.send_query()

    def analyze_categories(self):
        """Análise detalhada por categoria"""
        self.query_input.setText("Analise detalhadamente meus gastos por categoria e sugira onde posso reduzir")
        self.send_query()

    def analyze_trends(self):
        """Analisar tendências de gastos"""
        self.query_input.setText("Identifique tendências nos meus gastos e se estou melhorando ou piorando financeiramente")
        self.send_query()

    def suggest_investments(self):
        """Sugestões de investimento"""
        self.query_input.setText("Com base no meu perfil de gastos, que tipo de investimentos seriam adequados?")
        self.send_query()

class AddTransactionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Transação")

        self.amount_label = QLabel("Valor:")
        self.amount_input = QLineEdit()
        self.description_label = QLabel("Descrição:")
        self.description_input = QLineEdit()
        self.type_label = QLabel("Tipo:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["entrada", "saida"])
        self.date_label = QLabel("Data:")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.category_label = QLabel("Categoria:")
        self.category_combobox = QComboBox()

        # Carregar categorias do banco de dados
        categories = parent.db_connection.execute('SELECT name FROM categories WHERE user_id = ?', (parent.user_id,)).fetchall()
        category_names = [category['name'] for category in categories]
        self.category_combobox.addItems(category_names)

        self.add_button = QPushButton("Adicionar")
        self.cancel_button = QPushButton("Cancelar")

        layout = QVBoxLayout()
        layout.addWidget(self.amount_label)
        layout.addWidget(self.amount_input)
        layout.addWidget(self.description_label)
        layout.addWidget(self.description_input)
        layout.addWidget(self.type_label)
        layout.addWidget(self.type_combobox)
        layout.addWidget(self.date_label)
        layout.addWidget(self.date_edit)
        layout.addWidget(self.category_label)
        layout.addWidget(self.category_combobox)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.add_button.clicked.connect(self.add_transaction)
        self.cancel_button.clicked.connect(self.reject)

    def add_transaction(self):
        # Adicionar nova transação ao banco de dados
        try:
            amount = float(self.amount_input.text())
            if amount <= 0:
                QMessageBox.warning(self, "Erro", "O valor da transação deve ser positivo.")
                return
        except ValueError:
            QMessageBox.warning(self, "Erro", "O valor da transação deve ser um número válido.")
            return

        description = self.description_input.text()
        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText()

        # Obter o ID da categoria
        category_id = self.parent().db_connection.execute('SELECT id FROM categories WHERE user_id = ? AND name = ?', (self.parent().user_id, category_name)).fetchone()
        if category_id:
            category_id = category_id['id']
        else:
            # Se a categoria não existir, adicioná-la
            self.parent().db_connection.execute('INSERT INTO categories (user_id, name) VALUES (?, ?)', (self.parent().user_id, category_name))
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute('SELECT id FROM categories WHERE user_id = ? AND name = ?', (self.parent().user_id, category_name)).fetchone()['id']

        self.parent().db_connection.execute('INSERT INTO transactions (user_id, amount, description, transaction_type, date, category_id) VALUES (?, ?, ?, ?, ?, ?)',
                     (self.parent().user_id, amount, description, transaction_type, date, category_id))
        self.parent().db_connection.commit()
        self.accept()


class EditTransactionDialog(QDialog):
    def __init__(self, parent=None, transaction_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Transação")
        self.transaction_id = transaction_id

        self.amount_label = QLabel("Valor:")
        self.amount_input = QLineEdit()
        self.description_label = QLabel("Descrição:")
        self.description_input = QLineEdit()
        self.type_label = QLabel("Tipo:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["entrada", "saida"])
        self.date_label = QLabel("Data:")
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.category_label = QLabel("Categoria:")
        self.category_combobox = QComboBox()

        # Carregar categorias do banco de dados
        categories = parent.db_connection.execute('SELECT name FROM categories WHERE user_id = ?', (parent.user_id,)).fetchall()
        category_names = [category['name'] for category in categories]
        self.category_combobox.addItems(category_names)

        self.save_button = QPushButton("Salvar")
        self.cancel_button = QPushButton("Cancelar")

        layout = QVBoxLayout()
        layout.addWidget(self.amount_label)
        layout.addWidget(self.amount_input)
        layout.addWidget(self.description_label)
        layout.addWidget(self.description_input)
        layout.addWidget(self.type_label)
        layout.addWidget(self.type_combobox)
        layout.addWidget(self.date_label)
        layout.addWidget(self.date_edit)
        layout.addWidget(self.category_label)
        layout.addWidget(self.category_combobox)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.save_button.clicked.connect(self.save_transaction)
        self.cancel_button.clicked.connect(self.reject)

        self.load_transaction_data()

    def load_transaction_data(self):
        # Carregar dados da transação do banco de dados
        transaction = self.parent().db_connection.execute('SELECT * FROM transactions WHERE id = ?', (self.transaction_id,)).fetchone()
        self.amount_input.setText(str(transaction['amount']))
        self.description_input.setText(transaction['description'])
        self.type_combobox.setCurrentText(transaction['transaction_type'])
        date = datetime.strptime(transaction['date'], '%Y-%m-%d').date()
        self.date_edit.setDate(date)

        # Definir a categoria selecionada no combobox
        category_id = transaction['category_id']
        category_name = self.parent().db_connection.execute('SELECT name FROM categories WHERE id = ?', (category_id,)).fetchone()
        if category_name:
            self.category_combobox.setCurrentText(category_name['name'])

    def save_transaction(self):
        # Salvar transação editada no banco de dados
        try:
            amount = float(self.amount_input.text())
            if amount <= 0:
                QMessageBox.warning(self, "Erro", "O valor da transação deve ser positivo.")
                return
        except ValueError:
            QMessageBox.warning(self, "Erro", "O valor da transação deve ser um número válido.")
            return

        description = self.description_input.text()
        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText()

        # Obter o ID da categoria
        category_id = self.parent().db_connection.execute('SELECT id FROM categories WHERE user_id = ? AND name = ?', (self.parent().user_id, category_name)).fetchone()
        if category_id:
            category_id = category_id['id']
        else:
            # Se a categoria não existir, adicioná-la
            self.parent().db_connection.execute('INSERT INTO categories (user_id, name) VALUES (?, ?)', (self.parent().user_id, category_name))
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute('SELECT id FROM categories WHERE user_id = ? AND name = ?', (self.parent().user_id, category_name)).fetchone()['id']

        self.parent().db_connection.execute('UPDATE transactions SET amount = ?, description = ?, transaction_type = ?, date = ?, category_id = ? WHERE id = ?',
                     (amount, description, transaction_type, date, category_id, self.transaction_id))
        self.parent().db_connection.commit()
        self.accept()


class AddNoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Nota")

        self.note_label = QLabel("Nota:")
        self.note_input = QLineEdit()
        self.add_button = QPushButton("Adicionar")
        self.cancel_button = QPushButton("Cancelar")

        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.add_button.clicked.connect(self.add_note)
        self.cancel_button.clicked.connect(self.reject)

    def add_note(self):
        # Adicionar nova nota ao banco de dados
        note = self.note_input.text()
        self.parent().db_connection.execute('INSERT INTO notes (user_id, note) VALUES (?, ?)',
                     (self.parent().user_id, note))
        self.parent().db_connection.commit()
        self.accept()


class EditNoteDialog(QDialog):
    def __init__(self, parent=None, note_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Nota")
        self.note_id = note_id

        self.note_label = QLabel("Nota:")
        self.note_input = QLineEdit()
        self.save_button = QPushButton("Salvar")
        self.cancel_button = QPushButton("Cancelar")

        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.save_button.clicked.connect(self.save_note)
        self.cancel_button.clicked.connect(self.reject)

        self.load_note_data()

    def load_note_data(self):
        # Carregar dados da nota do banco de dados
        note = self.parent().db_connection.execute('SELECT * FROM notes WHERE id = ?', (self.note_id,)).fetchone()
        self.note_input.setText(note['note'])

    def save_note(self):
        # Salvar nota editada no banco de dados
        note = self.note_input.text()
        self.parent().db_connection.execute('UPDATE notes SET note = ? WHERE id = ?', (note, self.note_id))
        self.parent().db_connection.commit()
        self.accept()


class AddCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Categoria")

        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()
        self.add_button = QPushButton("Adicionar")
        self.cancel_button = QPushButton("Cancelar")

        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.add_button.clicked.connect(self.add_category)
        self.cancel_button.clicked.connect(self.reject)

    def add_category(self):
        # Adicionar nova categoria ao banco de dados
        category_name = self.category_name_input.text()
        self.parent().db_connection.execute('INSERT INTO categories (user_id, name) VALUES (?, ?)', (self.parent().user_id, category_name))
        self.parent().db_connection.commit()
        self.accept()


class EditCategoryDialog(QDialog):
    def __init__(self, parent=None, category_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Categoria")
        self.category_id = category_id

        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()
        self.save_button = QPushButton("Salvar")
        self.cancel_button = QPushButton("Cancelar")

        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.save_button.clicked.connect(self.save_category)
        self.cancel_button.clicked.connect(self.reject)

        self.load_category_data()

    def load_category_data(self):
        # Carregar dados da categoria do banco de dados
        category = self.parent().db_connection.execute('SELECT * FROM categories WHERE id = ?', (self.category_id,)).fetchone()
        self.category_name_input.setText(category['name'])

    def save_category(self):
        # Salvar categoria editada no banco de dados
        category_name = self.category_name_input.text()
        self.parent().db_connection.execute('UPDATE categories SET name = ? WHERE id = ?', (category_name, self.category_id))
        self.parent().db_connection.commit()
        self.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())

import sys
import os
import sqlite3
import json
import socket
import subprocess
import threading
import re
import socks
from datetime import datetime, timedelta
import calendar
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np
import requests

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
                            QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QDateEdit, QDialog,
                            QTabWidget, QGroupBox, QRadioButton, QTextEdit, QFileDialog, QScrollArea,
                            QFrame, QSplitter, QCalendarWidget, QProgressBar, QSystemTrayIcon, QMenu,
                            QAction, QCheckBox, QSpinBox, QDoubleSpinBox, QSlider, QGridLayout, QColorDialog,
                            QStyleFactory, QFormLayout, QMainWindow, QDockWidget)
from PyQt5.QtCore import Qt, QDate, QSize, QRect, QTimer, QSettings, QPoint, QUrl, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QTextCharFormat, QTextCursor, QPixmap, QDesktopServices

# Versão do banco de dados
DB_VERSION = 2

class DBUpdater:
    """Classe responsável por atualizar o esquema do banco de dados quando necessário"""

    @staticmethod
    def check_and_update(db_connection, username):
        """Verifica a versão do banco de dados e atualiza se necessário"""
        cursor = db_connection.cursor()

        # Verificar se a tabela de versão existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'")
        if not cursor.fetchone():
            # Criar tabela de versão se não existir
            cursor.execute('CREATE TABLE db_version (version INTEGER)')
            cursor.execute('INSERT INTO db_version VALUES (1)')
            db_connection.commit()
            current_version = 1
        else:
            # Verificar se a tabela contém registros
            version_record = cursor.execute('SELECT version FROM db_version').fetchone()
            if version_record is None:
                # A tabela existe mas está vazia, inserir versão 1
                cursor.execute('INSERT INTO db_version VALUES (1)')
                db_connection.commit()
                current_version = 1
            else:
                current_version = version_record[0]

        # Se a versão atual for menor que a versão esperada, atualizar
        if current_version < DB_VERSION:
            print(f"Atualizando banco de dados de versão {current_version} para versão {DB_VERSION}")

            # Atualização da versão 1 para 2
            if current_version == 1:
                try:
                    # Backup antes da atualização
                    db_path = os.path.join('dados', f'{username}.db')
                    backup_path = os.path.join('dados', f'{username}_backup_v1.db')
                    import shutil
                    shutil.copy2(db_path, backup_path)
                    print(f"Backup criado em: {backup_path}")

                    # Iniciar transação para garantir consistência
                    db_connection.execute("BEGIN TRANSACTION")

                    # Verificar se as colunas já existem (evitar erro)
                    cursor.execute("PRAGMA table_info(categories)")
                    columns = [info[1] for info in cursor.fetchall()]

                    # Adicionar coluna para valor de quitação às categorias se não existir
                    if 'total_amount' not in columns:
                        cursor.execute('ALTER TABLE categories ADD COLUMN total_amount REAL DEFAULT 0')

                    if 'is_payment_goal' not in columns:
                        cursor.execute('ALTER TABLE categories ADD COLUMN is_payment_goal INTEGER DEFAULT 0')

                    # Criar tabela de orçamentos mensais se não existir
                    cursor.execute('''CREATE TABLE IF NOT EXISTS category_budgets
                                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_id INTEGER NOT NULL,
                                    category_id INTEGER NOT NULL,
                                    month INTEGER NOT NULL,
                                    year INTEGER NOT NULL,
                                    amount REAL NOT NULL,
                                    FOREIGN KEY (user_id) REFERENCES users (id),
                                    FOREIGN KEY (category_id) REFERENCES categories (id),
                                    UNIQUE(user_id, category_id, month, year))''')

                    # Criar tabela de metas de economia se não existir
                    cursor.execute('''CREATE TABLE IF NOT EXISTS savings_goals
                                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_id INTEGER NOT NULL,
                                    name TEXT NOT NULL,
                                    target_amount REAL NOT NULL,
                                    current_amount REAL DEFAULT 0,
                                    start_date TEXT NOT NULL,
                                    deadline TEXT,
                                    category_id INTEGER,
                                    notes TEXT,
                                    FOREIGN KEY (user_id) REFERENCES users (id),
                                    FOREIGN KEY (category_id) REFERENCES categories (id))''')

                    # Criar tabela de configurações do usuário se não existir
                    cursor.execute('''CREATE TABLE IF NOT EXISTS user_settings
                                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_id INTEGER NOT NULL,
                                    setting_key TEXT NOT NULL,
                                    setting_value TEXT,
                                    FOREIGN KEY (user_id) REFERENCES users (id),
                                    UNIQUE(user_id, setting_key))''')

                    # Atualizar a versão no banco de dados
                    cursor.execute('UPDATE db_version SET version = 2')
                    db_connection.commit()

                    print("Banco de dados atualizado com sucesso para a versão 2")
                except Exception as e:
                    db_connection.rollback()
                    print(f"Erro ao atualizar banco de dados: {e}")
                    import traceback
                    traceback.print_exc()
                    return False

            # Adicionar mais atualizações para versões futuras aqui...

        return True

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
        # Carregar configurações do arquivo
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
        # Histórico de diálogo para contexto
        self.conversation_history = []
        # Máximo de mensagens para manter no histórico
        self.max_history = 10

    def load_config(self):
        """
        Carrega as configurações do assistente de IA do arquivo
        """
        if os.path.exists("ai_config.json"):
            try:
                with open("ai_config.json", "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def detect_server(self):
        """
        Detecta automaticamente qual servidor está disponível
        Retorna: "local", "tor", "manual" ou None
        """
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
        """
        Retorna a URL base do servidor atual
        """
        config = self.load_config()
        server_type = self.detect_server()

        if server_type == "local" or (server_type == "manual" and not config.get("auto_select", True)):
            return f"http://{config.get('local_ip', '')}:{config.get('local_port', '')}"
        elif server_type == "tor":
            try:
                # Configurar proxy SOCKS para Tor
                import socks
                import socket
                socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
                socket.socket = socks.socksocket

                return f"http://{config.get('tor_address', '')}:{config.get('tor_port', '')}"
            except ImportError:
                print("Módulo PySocks não encontrado. A funcionalidade Tor não estará disponível.")
                print("Para usar Tor, instale o pacote PySocks: pip install PySocks")
                return None

    def add_to_history(self, role, content):
        """
        Adiciona uma mensagem ao histórico de conversação
        Mantém o histórico dentro do limite máximo
        """
        self.conversation_history.append({"role": role, "content": content})
        # Manter apenas as últimas N mensagens
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

    def get_conversation_context(self):
        """
        Retorna o contexto da conversa para incluir nas chamadas à IA
        """
        if not self.conversation_history:
            return ""

        context = "Histórico de conversa recente:\n\n"
        for msg in self.conversation_history:
            prefix = "Usuário: " if msg["role"] == "user" else "Assistente: "
            context += f"{prefix}{msg['content']}\n\n"

        return context

    def analyze_for_category_action(self, user_query, ai_response, financial_context, db_connection, user_id):
        """
        Analisa a consulta do usuário e a resposta da IA para detectar sugestões de categoria
        Retorna uma tupla (ação, detalhes) se uma ação for detectada, ou (None, None) caso contrário

        Ações possíveis:
        - create: Criar nova categoria
        - rename: Renomear categoria existente
        - delete: Excluir categoria
        """
        # Padrões para detectar menções a categorias na resposta da IA
        create_patterns = [
            r"cria(?:r|) (?:uma |)categoria (?:chamada |)['\"]?([\w\s\-]+)['\"]?",
            r"suger(?:e|o|ia|iria) (?:cria(?:r|)|adiciona(?:r|)) (?:uma |a |)categoria (?:chamada |de |)['\"]?([\w\s\-]+)['\"]?",
            r"(?:seria bom|poderia|vale a pena) (?:ter|criar) (?:uma |)categoria (?:para |de |chamada |)['\"]?([\w\s\-]+)['\"]?"
        ]

        rename_patterns = [
            r"renomea(?:r|) a categoria ['\"]?([\w\s\-]+)['\"]? para ['\"]?([\w\s\-]+)['\"]?",
            r"altera(?:r|) (?:o nome d|)a categoria ['\"]?([\w\s\-]+)['\"]? para ['\"]?([\w\s\-]+)['\"]?",
            r"mudar? (?:o nome d|)a categoria ['\"]?([\w\s\-]+)['\"]? para ['\"]?([\w\s\-]+)['\"]?"
        ]

        delete_patterns = [
            r"(?:excluir|apagar|deletar|remover) a categoria ['\"]?([\w\s\-]+)['\"]?",
            r"(?:não precisa|desnecessária) a categoria ['\"]?([\w\s\-]+)['\"]?"
        ]

        # Verificar padrões de criação
        for pattern in create_patterns:
            matches = re.findall(pattern, ai_response.lower())
            if matches:
                category_name = matches[0].strip()
                # Verificar se a categoria já existe
                cursor = db_connection.cursor()
                existing = cursor.execute("SELECT id FROM categories WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                                        (user_id, category_name)).fetchone()
                if existing:
                    return None, None  # Categoria já existe
                return "create", {"name": category_name}

        # Verificar padrões de renomeação
        for pattern in rename_patterns:
            matches = re.findall(pattern, ai_response.lower())
            if matches:
                old_name, new_name = matches[0]
                old_name = old_name.strip()
                new_name = new_name.strip()
                # Verificar se a categoria antiga existe
                cursor = db_connection.cursor()
                existing = cursor.execute("SELECT id FROM categories WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                                        (user_id, old_name)).fetchone()
                if not existing:
                    return None, None  # Categoria original não existe
                return "rename", {"old_name": old_name, "new_name": new_name}

        # Verificar padrões de exclusão
        for pattern in delete_patterns:
            matches = re.findall(pattern, ai_response.lower())
            if matches:
                category_name = matches[0].strip()
                # Verificar se a categoria existe
                cursor = db_connection.cursor()
                existing = cursor.execute("SELECT id FROM categories WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                                        (user_id, category_name)).fetchone()
                if not existing:
                    return None, None  # Categoria não existe
                return "delete", {"name": category_name}

        return None, None

    def create_category(self, db_connection, user_id, category_name):
        """
        Cria uma nova categoria no banco de dados
        Retorna: (sucesso, mensagem)
        """
        try:
            cursor = db_connection.cursor()
            # Verificar se já existe
            existing = cursor.execute("SELECT id FROM categories WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                                     (user_id, category_name)).fetchone()
            if existing:
                return False, f"A categoria '{category_name}' já existe."

            # Criar nova categoria
            cursor.execute("INSERT INTO categories (user_id, name) VALUES (?, ?)",
                          (user_id, category_name))
            db_connection.commit()
            return True, f"Categoria '{category_name}' criada com sucesso!"
        except Exception as e:
            return False, f"Erro ao criar categoria: {str(e)}"

    def rename_category(self, db_connection, user_id, old_name, new_name):
        """
        Renomeia uma categoria existente
        Retorna: (sucesso, mensagem)
        """
        try:
            cursor = db_connection.cursor()
            # Verificar se categoria original existe
            existing = cursor.execute("SELECT id FROM categories WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                                     (user_id, old_name)).fetchone()
            if not existing:
                return False, f"A categoria '{old_name}' não foi encontrada."

            # Verificar se novo nome já existe
            duplicate = cursor.execute("SELECT id FROM categories WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                                      (user_id, new_name)).fetchone()
            if duplicate:
                return False, f"Já existe uma categoria chamada '{new_name}'."

            # Renomear categoria
            cursor.execute("UPDATE categories SET name = ? WHERE id = ?",
                          (new_name, existing[0]))
            db_connection.commit()
            return True, f"Categoria renomeada de '{old_name}' para '{new_name}' com sucesso!"
        except Exception as e:
            return False, f"Erro ao renomear categoria: {str(e)}"

    def delete_category(self, db_connection, user_id, category_name):
        """
        Exclui uma categoria
        Retorna: (sucesso, mensagem)
        """
        try:
            cursor = db_connection.cursor()
            # Verificar se categoria existe
            existing = cursor.execute("SELECT id FROM categories WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                                     (user_id, category_name)).fetchone()
            if not existing:
                return False, f"A categoria '{category_name}' não foi encontrada."

            # Verificar se há transações usando esta categoria
            transactions = cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND category_id = ?",
                                         (user_id, existing[0])).fetchone()
            if transactions[0] > 0:
                return False, f"Não é possível excluir a categoria '{category_name}' pois existem {transactions[0]} transações vinculadas a ela."

            # Excluir categoria
            cursor.execute("DELETE FROM categories WHERE id = ?", (existing[0],))
            db_connection.commit()
            return True, f"Categoria '{category_name}' excluída com sucesso!"
        except Exception as e:
            return False, f"Erro ao excluir categoria: {str(e)}"

    def ask_ai(self, prompt, context=None, callback=None, db_connection=None, user_id=None):
        """
        Envia uma pergunta para a IA e retorna a resposta

        Args:
            prompt (str): A pergunta ou instrução para a IA
            context (str, optional): Contexto adicional para a IA
            callback (function, optional): Função de callback para streaming
            db_connection: Conexão com banco de dados para ações da IA
            user_id: ID do usuário para ações da IA

        Returns:
            str: Resposta da IA ou mensagem de erro
        """
        server_url = self.get_server_url()
        if not server_url:
            return "Não foi possível conectar a um servidor Ollama. Verifique suas configurações."

        model = self.selected_model
        if not model:
            return "Nenhum modelo de IA selecionado. Configure nas opções de IA."

        # Adicionar a consulta atual ao histórico
        self.add_to_history("user", prompt)

        # Construir contexto completo combinando:
        # 1. Histórico de conversa
        # 2. Contexto financeiro específico fornecido
        full_context = ""
        conversation_context = self.get_conversation_context()
        if conversation_context:
            full_context += conversation_context + "\n\n"

        if context:
            full_context += "CONTEXTO FINANCEIRO ATUAL:\n" + context

        # Adicionar instruções especiais para a IA sobre ações permitidas
        full_context += "\n\nINSTRUÇÕES ESPECIAIS:\n"
        full_context += "- Você é um assistente financeiro especializado em ajudar com gestão financeira pessoal.\n"
        full_context += "- Se identificar que uma nova categoria financeira poderia beneficiar o usuário, você pode sugerir criá-la. Exemplo: 'Baseado em seus gastos, sugiro criar uma categoria \"Investimentos\" para acompanhar melhor seu progresso.'\n"
        full_context += "- Se identificar categorias que deveriam ser renomeadas, você pode sugerir isso. Exemplo: 'A categoria \"Comida\" poderia ser renomeada para \"Alimentação\" para ser mais específica.'\n"
        full_context += "- Se identificar categorias desnecessárias, você pode sugerir excluí-las, mas com cautela.\n"
        full_context += "- Lembre-se que o usuário tem o controle final - faça sugestões, não tome ações sozinho.\n"
        full_context += "- Seja conciso e direto em suas respostas, mas completo e útil.\n"

        try:
            url = f"{server_url}/api/generate"

            # Se tiver contexto, incluir no prompt
            full_prompt = prompt
            if full_context:
                full_prompt = f"{full_context}\n\nPergunta do usuário: {prompt}"

            # Iniciar a thread separada para não bloquear a interface
            if callback:
                # Criar uma thread para processar a solicitação
                threading.Thread(
                    target=self._process_ai_request_threaded,
                    args=(url, model, full_prompt, callback, db_connection, user_id, prompt),
                    daemon=True
                ).start()

                # Retornar imediatamente - a thread vai atualizar a UI
                return "Processando..."
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
                    ai_response = response_json.get("response", "Sem resposta da IA")

                    # Adicionar resposta ao histórico
                    self.add_to_history("assistant", ai_response)

                    # Verificar se a resposta sugere criar/renomear/excluir categorias
                    if db_connection and user_id:
                        action, details = self.analyze_for_category_action(prompt, ai_response, context, db_connection, user_id)
                        if action:
                            # Prepara resposta com sugestão de ação
                            ai_response = self._handle_category_action(action, details, ai_response, db_connection, user_id)

                    return ai_response
                else:
                    return f"Erro ao comunicar com a IA: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Erro ao comunicar com o servidor: {str(e)}"

    def _process_ai_request_threaded(self, url, model, full_prompt, callback, db_connection, user_id, original_prompt):
        """
        Processa a solicitação à IA em uma thread separada para não bloquear a UI
        """
        try:
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
                    error_msg = f"Erro ao comunicar com a IA: {response.status_code} - {response.text}"
                    # Usar QTimer.singleShot para atualizar a UI da thread principal
                    QTimer.singleShot(0, lambda: callback(error_msg))
                    return

                # Processar cada linha da resposta
                for line in response.iter_lines():
                    if line:
                        json_response = json.loads(line)
                        chunk = json_response.get("response", "")
                        full_response += chunk
                        # Usar QTimer.singleShot para atualizar a UI da thread principal
                        QTimer.singleShot(0, lambda resp=full_response: callback(resp))

            # Adicionar resposta completa ao histórico
            self.add_to_history("assistant", full_response)

            # Verificar se a resposta sugere criar/renomear/excluir categorias
            if db_connection and user_id:
                action, details = self.analyze_for_category_action(original_prompt, full_response, "", db_connection, user_id)
                if action:
                    # Prepara resposta com sugestão de ação
                    final_response = self._handle_category_action(action, details, full_response, db_connection, user_id)
                    # Atualizar a resposta final no callback
                    QTimer.singleShot(0, lambda: callback(final_response))

        except Exception as e:
            import traceback
            error_msg = f"Erro ao processar a consulta: {str(e)}\n{traceback.format_exc()}"
            QTimer.singleShot(0, lambda: callback(error_msg))

    def _handle_category_action(self, action, details, ai_response, db_connection, user_id):
        """
        Adiciona informações sobre a ação de categoria sugerida à resposta da IA
        """
        if action == "create":
            category_name = details["name"]
            # Adiciona ao final da resposta uma sugestão clara
            suggestion = f"\n\n---\n📋 **Sugestão de categoria:** Criar categoria '{category_name}'\n\n"
            suggestion += "Deseja que eu crie esta categoria para você? Responda 'sim criar categoria' para confirmar."
            return ai_response + suggestion

        elif action == "rename":
            old_name = details["old_name"]
            new_name = details["new_name"]
            suggestion = f"\n\n---\n📋 **Sugestão de categoria:** Renomear categoria '{old_name}' para '{new_name}'\n\n"
            suggestion += "Deseja que eu renomeie esta categoria? Responda 'sim renomear categoria' para confirmar."
            return ai_response + suggestion

        elif action == "delete":
            category_name = details["name"]
            suggestion = f"\n\n---\n📋 **Sugestão de categoria:** Excluir categoria '{category_name}'\n\n"
            suggestion += "Deseja que eu exclua esta categoria? Responda 'sim excluir categoria' para confirmar."
            return ai_response + suggestion

        return ai_response


class ChatMessage(QFrame):
    """
    Widget personalizado para exibir mensagens de chat com estilo melhorado
    """
    def __init__(self, content, is_user=True, parent=None):
        super().__init__(parent)
        # Configuração do layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.is_user = is_user

        # Adicionar texto da mensagem
        self.message = QTextEdit()
        self.message.setReadOnly(True)
        self.message.setHtml(content)
        self.message.setFrameStyle(QFrame.NoFrame)
        self.message.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Ajustar altura automaticamente
        doc_height = self.message.document().size().height()
        self.message.setMinimumHeight(min(150, max(50, doc_height + 10)))

        # Aplicar estilo baseado em quem enviou a mensagem
        # Estilos definidos no método apply_theme
        self.layout.addWidget(self.message)
        self.setLayout(self.layout)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro à mensagem de chat"""
        if is_dark_mode:
            if self.is_user:
                self.setStyleSheet("""
                    ChatMessage {
                        background-color: #2c3e50;
                        border-radius: 10px;
                        margin: 5px;
                        padding: 5px;
                    }
                    QTextEdit {
                        background-color: transparent;
                        color: #ecf0f1;
                        border: none;
                        font-size: 14px;
                    }
                """)
            else:
                self.setStyleSheet("""
                    ChatMessage {
                        background-color: #34495e;
                        border-radius: 10px;
                        margin: 5px;
                        padding: 5px;
                    }
                    QTextEdit {
                        background-color: transparent;
                        color: #ecf0f1;
                        border: none;
                        font-size: 14px;
                    }
                """)
        else:
            if self.is_user:
                self.setStyleSheet("""
                    ChatMessage {
                        background-color: #e1f5fe;
                        border-radius: 10px;
                        margin: 5px;
                        padding: 5px;
                    }
                    QTextEdit {
                        background-color: transparent;
                        color: #01579b;
                        border: none;
                        font-size: 14px;
                    }
                """)
            else:
                self.setStyleSheet("""
                    ChatMessage {
                        background-color: #f1f8e9;
                        border-radius: 10px;
                        margin: 5px;
                        padding: 5px;
                    }
                    QTextEdit {
                        background-color: transparent;
                        color: #33691e;
                        border: none;
                        font-size: 14px;
                    }
                """)


class ImprovedScrollArea(QScrollArea):
    """
    ScrollArea melhorada com autoscroll e estilos mais modernos
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.apply_theme(False)  # Inicialmente tema claro

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro à área de rolagem"""
        if is_dark_mode:
            self.setStyleSheet("""
                QScrollArea {
                    border: none;
                    background-color: #1e272e;
                }
                QScrollBar:vertical {
                    border: none;
                    background: #2d3436;
                    width: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #576574;
                    min-height: 20px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #7f8c8d;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """)
        else:
            self.setStyleSheet("""
                QScrollArea {
                    border: none;
                    background-color: #ffffff;
                }
                QScrollBar:vertical {
                    border: none;
                    background: #f0f0f0;
                    width: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #a0a0a0;
                    min-height: 20px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #808080;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """)

class AIQueryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assistente Financeiro IA")
        self.setGeometry(200, 200, 800, 700)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Layout principal
        main_layout = QVBoxLayout()

        # Splitter para dividir o chat e os controles de entrada
        self.splitter = QSplitter(Qt.Vertical)

        # Container para a área de chat
        self.chat_container = QWidget()
        chat_container_layout = QVBoxLayout(self.chat_container)

        # Área de rolagem melhorada para as mensagens
        self.chat_scroll = ImprovedScrollArea()
        self.chat_scroll.apply_theme(self.is_dark_mode)

        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setSpacing(10)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.addStretch()  # Força as mensagens para o topo

        self.chat_scroll.setWidget(self.chat_content)
        chat_container_layout.addWidget(self.chat_scroll)

        # Área de entrada e botões
        self.input_container = QWidget()
        input_layout = QVBoxLayout(self.input_container)

        # Grupo para período de análise
        period_group = QGroupBox("Período para análise:")
        period_layout = QHBoxLayout()

        # Seleção de ano
        year_label = QLabel("Ano:")
        self.year_combo = QComboBox()
        self.populate_years()

        # Seleção de mês
        month_label = QLabel("Mês:")
        self.month_combo = QComboBox()
        self.month_combo.addItems(["Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio",
                                  "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])

        period_layout.addWidget(year_label)
        period_layout.addWidget(self.year_combo)
        period_layout.addWidget(month_label)
        period_layout.addWidget(self.month_combo)
        period_group.setLayout(period_layout)

        # Grupo de ações rápidas
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

        quick_actions_layout.addLayout(quick_row1)
        quick_actions_layout.addLayout(quick_row2)
        quick_actions_group.setLayout(quick_actions_layout)

        # Campo de entrada com botão de envio
        input_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Digite sua pergunta ou comando aqui...")
        self.query_input.returnPressed.connect(self.send_query)

        self.send_button = QPushButton("Enviar")
        self.send_button.setIcon(QIcon.fromTheme("document-send"))
        self.send_button.clicked.connect(self.send_query)

        self.clear_button = QPushButton("Limpar Chat")
        self.clear_button.clicked.connect(self.clear_chat)

        input_row.addWidget(self.query_input, 8)  # Proporção maior para a entrada
        input_row.addWidget(self.send_button, 1)
        input_row.addWidget(self.clear_button, 1)

        # Adicionar widgets ao layout de entrada
        input_layout.addWidget(period_group)
        input_layout.addWidget(quick_actions_group)
        input_layout.addLayout(input_row)

        # Status da conexão
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-style: italic;")
        self.update_status_label()
        input_layout.addWidget(self.status_label)

        # Adicionar containers ao splitter
        self.splitter.addWidget(self.chat_container)
        self.splitter.addWidget(self.input_container)

        # Definir tamanho relativo das seções
        self.splitter.setSizes([500, 200])

        # Adicionar splitter ao layout principal
        main_layout.addWidget(self.splitter)

        self.setLayout(main_layout)

        # Timer para verificar o status da conexão periodicamente
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status_label)
        self.status_timer.start(30000)  # Atualizar a cada 30 segundos

        # Adicionar mensagem de boas vindas
        self.add_message("Olá! Sou seu assistente financeiro pessoal. Como posso ajudar você hoje?", False)

        # Flag para acompanhar se estamos processando uma ação de categoria
        self.pending_category_action = None

        # Aplicar tema inicial
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema (claro ou escuro) a todos os componentes"""
        self.is_dark_mode = is_dark_mode

        # Estilo para o diálogo principal
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                }
                QGroupBox {
                    color: #ecf0f1;
                    font-weight: bold;
                    border: 1px solid #4b6584;
                }
                QLineEdit {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                }
                QComboBox {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                }
                QPushButton {
                    background-color: #3498db;
                    color: #ecf0f1;
                    padding: 8px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QWidget {
                    color: #ecf0f1;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f5f5f5;
                    color: #333333;
                }
                QLabel {
                    color: #333333;
                    font-weight: bold;
                }
                QGroupBox {
                    color: #333333;
                    font-weight: bold;
                    border: 1px solid #ccc;
                }
                QLineEdit {
                    background-color: white;
                    color: #333333;
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                }
                QComboBox {
                    background-color: white;
                    color: #333333;
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    padding: 8px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QWidget {
                    color: #333333;
                }
            """)

        # Estilo específico para botões de ação
        button_style = """
            QPushButton {
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
                min-height: 30px;
            }
        """

        if is_dark_mode:
            button_style += """
                background-color: #3498db;
                color: #ecf0f1;
            """
            self.send_button.setStyleSheet(button_style + "background-color: #2ecc71;")
            self.clear_button.setStyleSheet(button_style + "background-color: #e74c3c;")
        else:
            button_style += """
                background-color: #4CAF50;
                color: white;
            """
            self.send_button.setStyleSheet(button_style + "background-color: #4CAF50;")
            self.clear_button.setStyleSheet(button_style + "background-color: #f44336;")

        # Aplicar estilo aos botões de ação rápida
        for button in [self.analyze_spending_button, self.budget_suggestion_button,
                      self.saving_tips_button, self.category_analysis_button,
                      self.trends_button, self.investment_button]:
            button.setStyleSheet(button_style)

        # Atualizar estilo dos componentes filhos
        self.chat_scroll.apply_theme(is_dark_mode)

        # Atualizar estilo das mensagens existentes
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ChatMessage):
                item.widget().apply_theme(is_dark_mode)

        # Estilo dos containers
        if is_dark_mode:
            self.chat_container.setStyleSheet("background-color: #1e272e; color: #ecf0f1;")
            self.chat_content.setStyleSheet("background-color: #1e272e; color: #ecf0f1;")
            self.input_container.setStyleSheet("background-color: #2d3436; color: #ecf0f1;")
        else:
            self.chat_container.setStyleSheet("background-color: white; color: #333333;")
            self.chat_content.setStyleSheet("background-color: white; color: #333333;")
            self.input_container.setStyleSheet("background-color: #f0f0f0; color: #333333;")

    def update_status_label(self):
        """Atualiza o status da conexão com o servidor de IA"""
        server_status = self.parent().ai_assistant.detect_server()
        if server_status:
            server_type = "local" if server_status == "local" else "Tor"
            self.status_label.setText(f"Conectado ao servidor {server_type}")
            self.status_label.setStyleSheet("color: green; font-style: italic;")
        else:
            self.status_label.setText("Não conectado a nenhum servidor. Configure nas opções de IA.")
            self.status_label.setStyleSheet("color: red; font-style: italic;")

    def add_message(self, message, is_user=True):
        """
        Adiciona uma mensagem ao chat

        Args:
            message (str): Conteúdo da mensagem
            is_user (bool): True se a mensagem foi enviada pelo usuário, False se pela IA
        """
        # Formatar o texto com markdown básico
        formatted_message = self.format_message_markdown(message)

        # Criar widget de mensagem
        msg_widget = ChatMessage(formatted_message, is_user)
        msg_widget.apply_theme(self.is_dark_mode)

        # Remover o espaço flexível
        if self.chat_layout.count() > 0 and self.chat_layout.itemAt(self.chat_layout.count() - 1).spacerItem():
            self.chat_layout.removeItem(self.chat_layout.itemAt(self.chat_layout.count() - 1))

        # Adicionar a mensagem
        self.chat_layout.addWidget(msg_widget)

        # Adicionar espaço flexível para empurrar as mensagens para cima
        self.chat_layout.addStretch()

        # Rolar para a mensagem mais recente
        QTimer.singleShot(50, self.scroll_to_bottom)

    def format_message_markdown(self, text):
        """
        Formata texto com markdown básico para HTML
        """
        # Substituir ** ** por negrito
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)

        # Substituir * * ou _ _ por itálico
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)

        # Substituir quebras de linha por <br>
        text = text.replace('\n', '<br>')

        # Formatação de listas
        lines = text.split('<br>')
        formatted_lines = []
        in_list = False

        for line in lines:
            if line.strip().startswith('- '):
                if not in_list:
                    formatted_lines.append('<ul>')
                    in_list = True
                formatted_lines.append(f'<li>{line.strip()[2:]}</li>')
            elif in_list:
                formatted_lines.append('</ul>')
                formatted_lines.append(line)
                in_list = False
            else:
                formatted_lines.append(line)

        if in_list:
            formatted_lines.append('</ul>')

        return ''.join(formatted_lines)

    def scroll_to_bottom(self):
        """Rola a área de chat para a última mensagem"""
        self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        )

    def clear_chat(self):
        """Limpa o histórico de chat"""
        # Remover todas as mensagens, exceto o espaço flexível
        while self.chat_layout.count() > 0:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Adicionar espaço flexível novamente
        self.chat_layout.addStretch()

        # Resetar o histórico de conversa da IA
        self.parent().ai_assistant.conversation_history = []

        # Adicionar mensagem de boas vindas
        self.add_message("Chat limpo. Como posso ajudar você hoje?", False)

    def populate_years(self):
        """Preenche o combobox de anos com os anos disponíveis no banco de dados"""
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
        """
        Obtém contexto financeiro do usuário com filtros de período
        Retorna uma string formatada com as informações financeiras
        """
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
                SELECT c.name, SUM(t.amount) AS total_spent, c.total_amount, c.is_payment_goal
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.transaction_type = 'saida' {year_condition} {month_condition}
                GROUP BY c.name
                ORDER BY total_spent DESC
            '''

            categories = self.parent().db_connection.execute(query, (self.parent().user_id,)).fetchall()

            # Obter informações de orçamento mensal (se aplicável)
            budget_info = ""
            if selected_year != "Todos" and selected_month > 0:
                budget_query = f'''
                    SELECT c.name, cb.amount AS budget_amount,
                           SUM(t.amount) AS spent_amount
                    FROM category_budgets cb
                    JOIN categories c ON cb.category_id = c.id
                    LEFT JOIN transactions t ON t.category_id = c.id
                           AND t.transaction_type = 'saida'
                           AND strftime('%Y', t.date) = '{selected_year}'
                           AND strftime('%m', t.date) = '{selected_month:02d}'
                    WHERE cb.user_id = ?
                          AND cb.year = '{selected_year}'
                          AND cb.month = {selected_month}
                    GROUP BY c.name
                    ORDER BY c.name
                '''

                budgets = self.parent().db_connection.execute(budget_query, (self.parent().user_id,)).fetchall()

                if budgets:
                    budget_info = "\nInformações de orçamento mensal:\n"
                    for b in budgets:
                        spent = b['spent_amount'] or 0
                        budget = b['budget_amount']
                        percentage = (spent / budget * 100) if budget > 0 else 0
                        remaining = budget - spent
                        status = "DENTRO DO ORÇAMENTO" if spent <= budget else "ACIMA DO ORÇAMENTO"
                        budget_info += f"- {b['name']}: Orçado R$ {budget:.2f}, Gasto R$ {spent:.2f} ({percentage:.1f}%), Restante R$ {remaining:.2f} - {status}\n"

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
                context += f"- {cat[0]}: R$ {cat[1]:.2f} ({percentage:.1f}% do total)"

                # Adicionar informações de metas de quitação
                if cat[3] == 1 and cat[2] > 0:  # Se for meta de pagamento e tiver valor total
                    total_paid = self.parent().db_connection.execute(
                        "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'",
                        (self.parent().user_id, cat['category_id'])
                    ).fetchone()[0] or 0

                    remaining = cat[2] - total_paid
                    progress = (total_paid / cat[2] * 100) if cat[2] > 0 else 0

                    context += f" - META DE QUITAÇÃO: R$ {cat[2]:.2f}, Pago: R$ {total_paid:.2f} ({progress:.1f}%), Restante: R$ {remaining:.2f}"

                context += "\n"

            # Adicionar informações de orçamento mensal
            if budget_info:
                context += "\n" + budget_info

            # Adicionar informações sobre categorias existentes
            all_categories = self.parent().db_connection.execute(
                "SELECT name FROM categories WHERE user_id = ? ORDER BY name",
                (self.parent().user_id,)
            ).fetchall()

            context += "\nCategorias disponíveis:\n"
            cat_names = [cat['name'] for cat in all_categories]
            context += ", ".join(cat_names)

            # Adicionar metas de economia
            savings_goals = self.parent().db_connection.execute(
                "SELECT name, target_amount, current_amount, deadline FROM savings_goals WHERE user_id = ?",
                (self.parent().user_id,)
            ).fetchall()

            if savings_goals:
                context += "\n\nMetas de economia:\n"
                for goal in savings_goals:
                    progress = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
                    remaining = goal['target_amount'] - goal['current_amount']
                    deadline = f", Prazo: {goal['deadline']}" if goal['deadline'] else ""
                    context += f"- {goal['name']}: Meta: R$ {goal['target_amount']:.2f}, Atual: R$ {goal['current_amount']:.2f} ({progress:.1f}%), Falta: R$ {remaining:.2f}{deadline}\n"

            return context

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return f"Erro ao obter contexto financeiro: {str(e)}"

    def process_category_action(self, query):
        """
        Processa uma ação de categoria solicitada pelo usuário
        Retorna True se uma ação foi processada, False caso contrário
        """
        # Verificar comandos de categoria
        query_lower = query.lower().strip()

        # Verificar se é uma resposta para uma ação pendente
        if "sim criar categoria" in query_lower and self.pending_category_action:
            if self.pending_category_action["action"] == "create":
                success, message = self.parent().ai_assistant.create_category(
                    self.parent().db_connection,
                    self.parent().user_id,
                    self.pending_category_action["details"]["name"]
                )
                self.add_message(f"🤖 {message}", False)
                # Atualizar lista de categorias no aplicativo principal
                self.parent().load_categories()
                self.pending_category_action = None
                return True

        elif "sim renomear categoria" in query_lower and self.pending_category_action:
            if self.pending_category_action["action"] == "rename":
                success, message = self.parent().ai_assistant.rename_category(
                    self.parent().db_connection,
                    self.parent().user_id,
                    self.pending_category_action["details"]["old_name"],
                    self.pending_category_action["details"]["new_name"]
                )
                self.add_message(f"🤖 {message}", False)
                # Atualizar lista de categorias no aplicativo principal
                self.parent().load_categories()
                self.pending_category_action = None
                return True

        elif "sim excluir categoria" in query_lower and self.pending_category_action:
            if self.pending_category_action["action"] == "delete":
                success, message = self.parent().ai_assistant.delete_category(
                    self.parent().db_connection,
                    self.parent().user_id,
                    self.pending_category_action["details"]["name"]
                )
                self.add_message(f"🤖 {message}", False)
                # Atualizar lista de categorias no aplicativo principal
                self.parent().load_categories()
                self.pending_category_action = None
                return True

        # Verificar se o usuário está solicitando criar categoria diretamente
        create_match = re.search(r"(?:cria|adiciona)(?:r|) (?:uma |a |)categoria (?:chamada |de |)['\"]?([\w\s\-]+)['\"]?", query_lower)
        if create_match:
            category_name = create_match.group(1).strip()
            success, message = self.parent().ai_assistant.create_category(
                self.parent().db_connection,
                self.parent().user_id,
                category_name
            )
            self.add_message(f"🤖 {message}", False)
            # Atualizar lista de categorias no aplicativo principal
            self.parent().load_categories()
            return True

        # Verificar se o usuário está solicitando renomear categoria diretamente
        rename_match = re.search(r"(?:renomea|altera|muda)(?:r|) (?:o nome d|)a categoria ['\"]?([\w\s\-]+)['\"]? para ['\"]?([\w\s\-]+)['\"]?", query_lower)
        if rename_match:
            old_name, new_name = rename_match.groups()
            success, message = self.parent().ai_assistant.rename_category(
                self.parent().db_connection,
                self.parent().user_id,
                old_name.strip(),
                new_name.strip()
            )
            self.add_message(f"🤖 {message}", False)
            # Atualizar lista de categorias no aplicativo principal
            self.parent().load_categories()
            return True

        # Verificar se o usuário está solicitando excluir categoria diretamente
        delete_match = re.search(r"(?:exclui|apaga|deleta|remove)(?:r|) (?:a |)categoria ['\"]?([\w\s\-]+)['\"]?", query_lower)
        if delete_match:
            category_name = delete_match.group(1).strip()
            success, message = self.parent().ai_assistant.delete_category(
                self.parent().db_connection,
                self.parent().user_id,
                category_name
            )
            self.add_message(f"🤖 {message}", False)
            # Atualizar lista de categorias no aplicativo principal
            self.parent().load_categories()
            return True

        return False

    def send_query(self):
        """Envia a pergunta do usuário para a IA e exibe a resposta"""
        query = self.query_input.text().strip()
        if not query:
            return

        # Limpar o campo de entrada
        self.query_input.setText("")

        # Adicionar a mensagem do usuário ao chat
        self.add_message(query, True)

        # Verificar se é um comando de categoria
        if self.process_category_action(query):
            return

        # Verificar configurações
        if not self.parent().ai_assistant.selected_model:
            self.add_message("Erro: Nenhum modelo de IA selecionado. Configure nas opções de IA primeiro.", False)
            return

        server_status = self.parent().ai_assistant.detect_server()
        if not server_status:
            self.add_message("Erro: Nenhum servidor Ollama disponível. Configure nas opções de IA primeiro.", False)
            return

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

        # Adicionar o período à consulta se não estiver explícito
        full_query = query
        if period_info and period_info not in query.lower():
            full_query = f"{query}{period_info}"

        try:
            # Obter contexto financeiro
            context = self.get_financial_context()

            # Função de callback para atualização em tempo real
            def update_response(text):
                # Encontrar a última mensagem da IA, se existir
                ai_message = None
                ai_message_index = -1

                for i in range(self.chat_layout.count()):
                    item = self.chat_layout.itemAt(i)
                    if item and item.widget() and isinstance(item.widget(), ChatMessage) and not item.widget().is_user:
                        ai_message = item.widget()
                        ai_message_index = i
                        break

                # Se já existir uma mensagem da IA, atualize-a, caso contrário, crie uma nova
                if ai_message:
                    # Atualizar o conteúdo
                    formatted_message = self.format_message_markdown(text)
                    ai_message.message.setHtml(formatted_message)
                    ai_message.apply_theme(self.is_dark_mode)
                else:
                    # Adicionar nova mensagem
                    self.add_message(text, False)

                # Verificar se a resposta contém sugestões de categoria
                if "**Sugestão de categoria:**" in text:
                    # Extrair a ação de categoria da resposta
                    if "Criar categoria" in text:
                        category_name = re.search(r"Criar categoria '([^']+)'", text).group(1)
                        self.pending_category_action = {
                            "action": "create",
                            "details": {"name": category_name}
                        }
                    elif "Renomear categoria" in text:
                        match = re.search(r"Renomear categoria '([^']+)' para '([^']+)'", text)
                        old_name, new_name = match.groups()
                        self.pending_category_action = {
                            "action": "rename",
                            "details": {"old_name": old_name, "new_name": new_name}
                        }
                    elif "Excluir categoria" in text:
                        category_name = re.search(r"Excluir categoria '([^']+)'", text).group(1)
                        self.pending_category_action = {
                            "action": "delete",
                            "details": {"name": category_name}
                        }

                # Rolar para o final
                self.scroll_to_bottom()

            # Mostrar mensagem de processamento apenas se não houver nenhuma mensagem da IA
            ai_message_exists = False
            for i in range(self.chat_layout.count()):
                item = self.chat_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), ChatMessage) and not item.widget().is_user:
                    ai_message_exists = True
                    break

            if not ai_message_exists:
                self.add_message("Processando sua consulta...", False)

            # Iniciar consulta em segundo plano
            self.parent().ai_assistant.ask_ai(
                full_query,
                context,
                callback=update_response,
                db_connection=self.parent().db_connection,
                user_id=self.parent().user_id
            )

        except Exception as e:
            import traceback
            error_msg = f"Erro ao processar consulta: {str(e)}"
            self.add_message(error_msg, False)
            print(traceback.format_exc())

    # Implementação das ações rápidas
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
        self.setMinimumWidth(400)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.amount_label = QLabel("Valor:")
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("Digite o valor (ex: 150.00)")

        self.description_label = QLabel("Descrição:")
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Digite a descrição da transação")

        self.type_label = QLabel("Tipo:")
        self.type_combobox = QComboBox()
        self.type_combobox.addItems(["entrada", "saida"])
        self.type_combobox.setCurrentIndex(1)  # Saída como padrão (mais comum)

        self.date_label = QLabel("Data:")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)

        self.category_label = QLabel("Categoria:")
        self.category_combobox = QComboBox()
        self.category_combobox.setEditable(True)  # Permitir criar nova categoria

        # Carregar categorias do banco de dados
        categories = parent.db_connection.execute('SELECT name FROM categories WHERE user_id = ? ORDER BY name',
                                                (parent.user_id,)).fetchall()
        category_names = [category['name'] for category in categories]
        self.category_combobox.addItems(category_names)

        # Botões
        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_transaction)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
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

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.add_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def add_transaction(self):
        """
        Adiciona uma nova transação ao banco de dados
        Valida os dados antes de adicionar
        """
        try:
            amount = float(self.amount_input.text().replace(',', '.'))
            if amount <= 0:
                QMessageBox.warning(self, "Erro", "O valor da transação deve ser positivo.")
                return
        except ValueError:
            QMessageBox.warning(self, "Erro", "O valor da transação deve ser um número válido.")
            return

        description = self.description_input.text().strip()
        if not description:
            QMessageBox.warning(self, "Erro", "A descrição não pode estar vazia.")
            return

        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText().strip()

        if not category_name:
            QMessageBox.warning(self, "Erro", "A categoria não pode estar vazia.")
            return

        # Obter o ID da categoria ou criar uma nova
        category_id = self.parent().db_connection.execute(
            'SELECT id FROM categories WHERE user_id = ? AND name = ?',
            (self.parent().user_id, category_name)
        ).fetchone()

        if category_id:
            category_id = category_id['id']
        else:
            # Se a categoria não existir, adicioná-la
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name) VALUES (?, ?)',
                (self.parent().user_id, category_name)
            )
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.parent().user_id, category_name)
            ).fetchone()['id']

        # Inserir a transação
        self.parent().db_connection.execute(
            'INSERT INTO transactions (user_id, amount, description, transaction_type, date, category_id) VALUES (?, ?, ?, ?, ?, ?)',
            (self.parent().user_id, amount, description, transaction_type, date, category_id)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(self, "Sucesso", "Transação adicionada com sucesso!")
        self.accept()


class EditTransactionDialog(QDialog):
    def __init__(self, parent=None, transaction_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Transação")
        self.setMinimumWidth(400)
        self.transaction_id = transaction_id
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
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
        self.date_edit.setCalendarPopup(True)

        self.category_label = QLabel("Categoria:")
        self.category_combobox = QComboBox()
        self.category_combobox.setEditable(True)  # Permitir editar categoria

        # Carregar categorias do banco de dados
        categories = parent.db_connection.execute('SELECT name FROM categories WHERE user_id = ? ORDER BY name',
                                                (parent.user_id,)).fetchall()
        category_names = [category['name'] for category in categories]
        self.category_combobox.addItems(category_names)

        # Botões
        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_transaction)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
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

        # Carregar dados da transação
        self.load_transaction_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def load_transaction_data(self):
        """
        Carrega dados da transação do banco de dados para o formulário
        """
        transaction = self.parent().db_connection.execute(
            'SELECT * FROM transactions WHERE id = ?',
            (self.transaction_id,)
        ).fetchone()

        self.amount_input.setText(str(transaction['amount']))
        self.description_input.setText(transaction['description'])
        self.type_combobox.setCurrentText(transaction['transaction_type'])

        date = datetime.strptime(transaction['date'], '%Y-%m-%d').date()
        self.date_edit.setDate(date)

        # Definir a categoria selecionada no combobox
        category_id = transaction['category_id']
        if category_id:
            category_name = self.parent().db_connection.execute(
                'SELECT name FROM categories WHERE id = ?',
                (category_id,)
            ).fetchone()
            if category_name:
                self.category_combobox.setCurrentText(category_name['name'])

    def save_transaction(self):
        """
        Salva as alterações na transação
        """
        try:
            amount = float(self.amount_input.text().replace(',', '.'))
            if amount <= 0:
                QMessageBox.warning(self, "Erro", "O valor da transação deve ser positivo.")
                return
        except ValueError:
            QMessageBox.warning(self, "Erro", "O valor da transação deve ser um número válido.")
            return

        description = self.description_input.text().strip()
        if not description:
            QMessageBox.warning(self, "Erro", "A descrição não pode estar vazia.")
            return

        transaction_type = self.type_combobox.currentText()
        date = self.date_edit.date().toString("yyyy-MM-dd")
        category_name = self.category_combobox.currentText().strip()

        if not category_name:
            QMessageBox.warning(self, "Erro", "A categoria não pode estar vazia.")
            return

        # Obter o ID da categoria ou criar uma nova
        category_id = self.parent().db_connection.execute(
            'SELECT id FROM categories WHERE user_id = ? AND name = ?',
            (self.parent().user_id, category_name)
        ).fetchone()

        if category_id:
            category_id = category_id['id']
        else:
            # Se a categoria não existir, adicioná-la
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name) VALUES (?, ?)',
                (self.parent().user_id, category_name)
            )
            self.parent().db_connection.commit()
            category_id = self.parent().db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.parent().user_id, category_name)
            ).fetchone()['id']

        # Atualizar a transação
        self.parent().db_connection.execute(
            'UPDATE transactions SET amount = ?, description = ?, transaction_type = ?, date = ?, category_id = ? WHERE id = ?',
            (amount, description, transaction_type, date, category_id, self.transaction_id)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(self, "Sucesso", "Transação atualizada com sucesso!")
        self.accept()


class AddNoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Nota")
        self.setMinimumWidth(400)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()  # Usar QTextEdit para notas mais longas
        self.note_input.setMinimumHeight(150)
        self.note_input.setPlaceholderText("Digite sua nota aqui...")

        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.add_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def add_note(self):
        """
        Adiciona uma nova nota ao banco de dados
        """
        note = self.note_input.toPlainText().strip()
        if not note:
            QMessageBox.warning(self, "Erro", "A nota não pode estar vazia.")
            return

        self.parent().db_connection.execute(
            'INSERT INTO notes (user_id, note) VALUES (?, ?)',
            (self.parent().user_id, note)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(self, "Sucesso", "Nota adicionada com sucesso!")
        self.accept()


class EditNoteDialog(QDialog):
    def __init__(self, parent=None, note_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Nota")
        self.setMinimumWidth(400)
        self.note_id = note_id
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()
        self.note_input.setMinimumHeight(150)

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Carregar dados da nota
        self.load_note_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def load_note_data(self):
        """
        Carrega dados da nota do banco de dados para o formulário
        """
        note = self.parent().db_connection.execute(
            'SELECT * FROM notes WHERE id = ?',
            (self.note_id,)
        ).fetchone()

        self.note_input.setText(note['note'])

    def save_note(self):
        """
        Salva as alterações na nota
        """
        note = self.note_input.toPlainText().strip()
        if not note:
            QMessageBox.warning(self, "Erro", "A nota não pode estar vazia.")
            return

        self.parent().db_connection.execute(
            'UPDATE notes SET note = ? WHERE id = ?',
            (note, self.note_id)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(self, "Sucesso", "Nota atualizada com sucesso!")
        self.accept()


class AddCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Categoria")
        self.setMinimumWidth(400)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()
        self.category_name_input.setPlaceholderText("Digite o nome da categoria")

        # Adicionar opção de meta de quitação
        self.payment_goal_check = QCheckBox("Esta categoria é uma meta de quitação")
        self.payment_goal_check.toggled.connect(self.toggle_payment_goal)

        self.total_amount_label = QLabel("Valor Total da Meta:")
        self.total_amount_input = QLineEdit()
        self.total_amount_input.setPlaceholderText("Valor total a ser quitado (ex: 20000.00)")
        self.total_amount_input.setEnabled(False)

        # Botões
        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)
        layout.addWidget(self.payment_goal_check)
        layout.addWidget(self.total_amount_label)
        layout.addWidget(self.total_amount_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCheckBox {
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.add_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def toggle_payment_goal(self, checked):
        """Ativa/desativa o campo de valor total de acordo com o checkbox"""
        self.total_amount_input.setEnabled(checked)

    def add_category(self):
        """
        Adiciona uma nova categoria ao banco de dados
        """
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(self, "Erro", "O nome da categoria não pode estar vazio.")
            return

        # Verificar o valor total se for meta de quitação
        total_amount = 0
        is_payment_goal = 0

        if self.payment_goal_check.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(self.total_amount_input.text().replace(',', '.'))
                if total_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor total da meta deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor total deve ser um número válido.")
                return

        try:
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name, total_amount, is_payment_goal) VALUES (?, ?, ?, ?)',
                (self.parent().user_id, category_name, total_amount, is_payment_goal)
            )
            self.parent().db_connection.commit()

            QMessageBox.information(self, "Sucesso", "Categoria adicionada com sucesso!")
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Erro", f"A categoria '{category_name}' já existe.")


class EditCategoryDialog(QDialog):
    def __init__(self, parent=None, category_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Categoria")
        self.setMinimumWidth(400)
        self.category_id = category_id
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()

        # Adicionar opção de meta de quitação
        self.payment_goal_check = QCheckBox("Esta categoria é uma meta de quitação")
        self.payment_goal_check.toggled.connect(self.toggle_payment_goal)

        self.total_amount_label = QLabel("Valor Total da Meta:")
        self.total_amount_input = QLineEdit()
        self.total_amount_input.setPlaceholderText("Valor total a ser quitado (ex: 20000.00)")

        # Mostrar progresso
        self.progress_label = QLabel("Progresso da Quitação:")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_info = QLabel()

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)
        layout.addWidget(self.payment_goal_check)
        layout.addWidget(self.total_amount_label)
        layout.addWidget(self.total_amount_input)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_info)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Carregar dados da categoria
        self.load_category_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCheckBox {
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QProgressBar {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    text-align: center;
                    background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QProgressBar {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def toggle_payment_goal(self, checked):
        """Ativa/desativa o campo de valor total de acordo com o checkbox"""
        self.total_amount_input.setEnabled(checked)
        self.progress_bar.setVisible(checked)
        self.progress_label.setVisible(checked)
        self.progress_info.setVisible(checked)

    def load_category_data(self):
        """
        Carrega dados da categoria do banco de dados para o formulário
        """
        category = self.parent().db_connection.execute(
            'SELECT * FROM categories WHERE id = ?',
            (self.category_id,)
        ).fetchone()

        self.category_name_input.setText(category['name'])

        # Configurar opções de meta de quitação
        is_payment_goal = category['is_payment_goal'] == 1
        self.payment_goal_check.setChecked(is_payment_goal)

        total_amount = category['total_amount'] or 0
        self.total_amount_input.setText(str(total_amount))
        self.total_amount_input.setEnabled(is_payment_goal)

        # Mostrar progresso se for meta de quitação
        self.progress_bar.setVisible(is_payment_goal)
        self.progress_label.setVisible(is_payment_goal)
        self.progress_info.setVisible(is_payment_goal)

        if is_payment_goal and total_amount > 0:
            # Calcular total já pago
            total_paid = self.parent().db_connection.execute(
                "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'",
                (self.parent().user_id, self.category_id)
            ).fetchone()[0] or 0

            # Atualizar barra de progresso
            progress_percentage = min(100, int((total_paid / total_amount) * 100)) if total_amount > 0 else 0
            self.progress_bar.setValue(progress_percentage)

            # Informações de progresso
            remaining = total_amount - total_paid
            self.progress_info.setText(
                f"Pago: R$ {total_paid:.2f} de R$ {total_amount:.2f} ({progress_percentage}%)\n"
                f"Restante: R$ {remaining:.2f}"
            )

    def save_category(self):
        """
        Salva as alterações na categoria
        """
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(self, "Erro", "O nome da categoria não pode estar vazio.")
            return

        # Verificar o valor total se for meta de quitação
        total_amount = 0
        is_payment_goal = 0

        if self.payment_goal_check.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(self.total_amount_input.text().replace(',', '.'))
                if total_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor total da meta deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor total deve ser um número válido.")
                return

        try:
            self.parent().db_connection.execute(
                'UPDATE categories SET name = ?, total_amount = ?, is_payment_goal = ? WHERE id = ?',
                (category_name, total_amount, is_payment_goal, self.category_id)
            )
            self.parent().db_connection.commit()

            QMessageBox.information(self, "Sucesso", "Categoria atualizada com sucesso!")
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Erro", f"A categoria '{category_name}' já existe.")


class BudgetDialog(QDialog):
    """Diálogo para definir orçamentos mensais por categoria"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Definir Orçamento Mensal")
        self.setMinimumWidth(500)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.month_label = QLabel("Mês:")
        self.month_combo = QComboBox()
        self.month_combo.addItems(["Janeiro", "Fevereiro", "Março", "Abril", "Maio",
                                  "Junho", "Julho", "Agosto", "Setembro", "Outubro",
                                  "Novembro", "Dezembro"])
        # Definir mês atual
        current_month = datetime.now().month
        self.month_combo.setCurrentIndex(current_month - 1)

        self.year_label = QLabel("Ano:")
        self.year_combo = QComboBox()
        current_year = datetime.now().year
        # Adicionar anos (atual, próximo e anteriores)
        for year in range(current_year - 2, current_year + 3):
            self.year_combo.addItem(str(year))
        # Definir ano atual
        self.year_combo.setCurrentText(str(current_year))

        # Botão para carregar orçamentos existentes
        self.load_button = QPushButton("Carregar Orçamentos Existentes")
        self.load_button.clicked.connect(self.load_existing_budgets)

        # Tabela de categorias e orçamentos
        self.budget_table = QTableWidget()
        self.budget_table.setColumnCount(3)
        self.budget_table.setHorizontalHeaderLabels(["Categoria", "Orçamento (R$)", "Gastos Médios (R$)"])
        self.budget_table.horizontalHeader().setStretchLastSection(True)

        # Botões
        self.save_button = QPushButton("Salvar Orçamentos")
        self.save_button.clicked.connect(self.save_budgets)

        self.suggest_button = QPushButton("Sugerir com Base nos Gastos")
        self.suggest_button.clicked.connect(self.suggest_budgets)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()

        # Layout para mês e ano
        date_layout = QHBoxLayout()
        date_layout.addWidget(self.month_label)
        date_layout.addWidget(self.month_combo)
        date_layout.addWidget(self.year_label)
        date_layout.addWidget(self.year_combo)
        date_layout.addWidget(self.load_button)

        layout.addLayout(date_layout)
        layout.addWidget(self.budget_table)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.suggest_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Carregar categorias
        self.load_categories()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                    selection-background-color: #3498db;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    padding: 5px;
                    border: 1px solid #4b6584;
                }
            """)
            self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QTableWidget {
                    background-color: white;
                    alternate-background-color: #f9f9f9;
                    selection-background-color: #e3f2fd;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
            self.suggest_button.setStyleSheet("background-color: #2196F3; color: white;")

    def load_categories(self):
        """Carrega as categorias do usuário para a tabela"""
        try:
            categories = self.parent().db_connection.execute(
                'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
                (self.parent().user_id,)
            ).fetchall()

            self.budget_table.setRowCount(len(categories))

            for i, category in enumerate(categories):
                # Salvar o ID da categoria como dados do item
                category_item = QTableWidgetItem(category['name'])
                category_item.setData(Qt.UserRole, category['id'])

                # Adicionar campo de entrada para orçamento
                budget_input = QLineEdit()
                budget_input.setPlaceholderText("0.00")

                # Calcular média de gastos dos últimos 3 meses
                avg_expense = self.calculate_average_expense(category['id'])
                avg_expense_item = QTableWidgetItem(f"{avg_expense:.2f}")

                self.budget_table.setItem(i, 0, category_item)
                self.budget_table.setCellWidget(i, 1, budget_input)
                self.budget_table.setItem(i, 2, avg_expense_item)

            self.budget_table.resizeColumnsToContents()

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível carregar as categorias: {str(e)}")

    def calculate_average_expense(self, category_id):
        """Calcula a média de gastos dos últimos 3 meses para uma categoria"""
        try:
            # Obter data de 3 meses atrás
            today = datetime.now()
            three_months_ago = today.replace(day=1) - timedelta(days=1)
            three_months_ago = three_months_ago.replace(day=1)
            three_months_ago = three_months_ago.replace(day=1) - timedelta(days=1)
            three_months_ago = three_months_ago.replace(day=1)
            three_months_ago_str = three_months_ago.strftime('%Y-%m-%d')

            # Consultar gastos dos últimos 3 meses
            result = self.parent().db_connection.execute(
                '''
                SELECT SUM(amount) as total, COUNT(DISTINCT strftime('%Y-%m', date)) as months
                FROM transactions
                WHERE user_id = ? AND category_id = ? AND transaction_type = 'saida'
                AND date >= ?
                ''',
                (self.parent().user_id, category_id, three_months_ago_str)
            ).fetchone()

            total = result['total'] or 0
            months = result['months'] or 1  # Evitar divisão por zero

            return total / months

        except Exception as e:
            print(f"Erro ao calcular média de gastos: {e}")
            return 0.0

    def load_existing_budgets(self):
        """Carrega orçamentos existentes para o mês/ano selecionado"""
        try:
            selected_month = self.month_combo.currentIndex() + 1  # Mês começa em 1
            selected_year = self.year_combo.currentText()

            budgets = self.parent().db_connection.execute(
                '''
                SELECT cb.category_id, cb.amount
                FROM category_budgets cb
                WHERE cb.user_id = ? AND cb.month = ? AND cb.year = ?
                ''',
                (self.parent().user_id, selected_month, selected_year)
            ).fetchall()

            # Mapear orçamentos por ID de categoria
            budget_map = {b['category_id']: b['amount'] for b in budgets}

            # Preencher a tabela com os valores existentes
            for i in range(self.budget_table.rowCount()):
                category_id = self.budget_table.item(i, 0).data(Qt.UserRole)
                if category_id in budget_map:
                    budget_input = self.budget_table.cellWidget(i, 1)
                    budget_input.setText(str(budget_map[category_id]))

            QMessageBox.information(self, "Sucesso",
                                  f"Orçamentos carregados para {self.month_combo.currentText()} de {selected_year}.")

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível carregar os orçamentos: {str(e)}")

    def suggest_budgets(self):
        """Sugere orçamentos com base nos gastos médios"""
        try:
            for i in range(self.budget_table.rowCount()):
                avg_expense_text = self.budget_table.item(i, 2).text()
                try:
                    avg_expense = float(avg_expense_text.replace(',', '.'))
                    # Adicionar 10% de margem aos gastos médios
                    suggested_budget = avg_expense * 1.1
                    budget_input = self.budget_table.cellWidget(i, 1)
                    budget_input.setText(f"{suggested_budget:.2f}")
                except:
                    continue
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível sugerir orçamentos: {str(e)}")

    def save_budgets(self):
        """Salva os orçamentos definidos no banco de dados"""
        try:
            selected_month = self.month_combo.currentIndex() + 1  # Mês começa em 1
            selected_year = self.year_combo.currentText()

            # Começar uma transação
            self.parent().db_connection.execute("BEGIN TRANSACTION")

            # Deletar orçamentos existentes para este mês/ano
            self.parent().db_connection.execute(
                "DELETE FROM category_budgets WHERE user_id = ? AND month = ? AND year = ?",
                (self.parent().user_id, selected_month, selected_year)
            )

            # Inserir novos orçamentos
            count = 0
            for i in range(self.budget_table.rowCount()):
                category_id = self.budget_table.item(i, 0).data(Qt.UserRole)
                budget_input = self.budget_table.cellWidget(i, 1)
                budget_text = budget_input.text().strip()

                if budget_text:
                    try:
                        budget_amount = float(budget_text.replace(',', '.'))
                        if budget_amount > 0:
                            self.parent().db_connection.execute(
                                '''
                                INSERT INTO category_budgets
                                (user_id, category_id, month, year, amount)
                                VALUES (?, ?, ?, ?, ?)
                                ''',
                                (self.parent().user_id, category_id, selected_month, selected_year, budget_amount)
                            )
                            count += 1
                    except ValueError:
                        continue

            # Confirmar transação
            self.parent().db_connection.commit()

            QMessageBox.information(self, "Sucesso",
                                  f"Foram salvos {count} orçamentos para {self.month_combo.currentText()} de {selected_year}.")
            self.accept()

        except Exception as e:
            # Reverter em caso de erro
            self.parent().db_connection.rollback()
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar os orçamentos: {str(e)}")


class SavingsGoalDialog(QDialog):
    """Diálogo para gerenciar metas de economia"""
    def __init__(self, parent=None, goal_id=None):
        super().__init__(parent)
        self.goal_id = goal_id
        self.is_edit_mode = goal_id is not None
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        self.setWindowTitle("Meta de Economia" if self.is_edit_mode else "Nova Meta de Economia")
        self.setMinimumWidth(450)

        # Widgets
        self.name_label = QLabel("Nome da Meta:")
        self.name_input = QLineEdit()

        self.target_label = QLabel("Valor Alvo (R$):")
        self.target_input = QLineEdit()

        self.current_label = QLabel("Valor Atual (R$):")
        self.current_input = QLineEdit()
        self.current_input.setPlaceholderText("0.00")

        self.deadline_label = QLabel("Prazo (opcional):")
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setDisplayFormat("yyyy-MM-dd")
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setDate(QDate.currentDate().addMonths(6))  # Padrão: 6 meses a partir de hoje

        self.has_deadline_check = QCheckBox("Definir prazo")
        self.has_deadline_check.toggled.connect(self.toggle_deadline)
        self.has_deadline_check.setChecked(False)
        self.deadline_edit.setEnabled(False)

        self.category_label = QLabel("Categoria relacionada (opcional):")
        self.category_combo = QComboBox()
        self.category_combo.addItem("Nenhuma", None)

        # Carregar categorias
        if parent and hasattr(parent, 'db_connection') and hasattr(parent, 'user_id'):
            categories = parent.db_connection.execute(
                'SELECT id, name FROM categories WHERE user_id = ? ORDER BY name',
                (parent.user_id,)
            ).fetchall()

            for category in categories:
                self.category_combo.addItem(category['name'], category['id'])

        self.notes_label = QLabel("Notas:")
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Observações, detalhes ou motivação para esta meta...")
        self.notes_input.setMaximumHeight(100)

        # Widgets de progresso (visíveis apenas no modo de edição)
        self.progress_label = QLabel("Progresso:")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)

        self.time_progress_label = QLabel("Progresso de tempo:")
        self.time_progress_bar = QProgressBar()
        self.time_progress_bar.setMaximum(100)
        self.time_progress_bar.setTextVisible(True)

        self.summary_label = QLabel()

        # Botões
        if self.is_edit_mode:
            self.save_button = QPushButton("Atualizar Meta")
            self.deposit_button = QPushButton("Adicionar Depósito")
            self.deposit_button.clicked.connect(self.add_deposit)

            button_layout = QHBoxLayout()
            button_layout.addWidget(self.deposit_button)
            button_layout.addWidget(self.save_button)
        else:
            self.save_button = QPushButton("Criar Meta")
            button_layout = QHBoxLayout()
            button_layout.addWidget(self.save_button)

        self.save_button.clicked.connect(self.save_goal)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.cancel_button)

        # Layout
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.addRow(self.name_label, self.name_input)
        form_layout.addRow(self.target_label, self.target_input)
        form_layout.addRow(self.current_label, self.current_input)
        form_layout.addRow(self.has_deadline_check)
        form_layout.addRow(self.deadline_label, self.deadline_edit)
        form_layout.addRow(self.category_label, self.category_combo)
        form_layout.addRow(self.notes_label, self.notes_input)

        layout.addLayout(form_layout)

        # Adicionar widgets de progresso apenas no modo de edição
        if self.is_edit_mode:
            progress_layout = QVBoxLayout()
            progress_layout.addWidget(self.progress_label)
            progress_layout.addWidget(self.progress_bar)
            progress_layout.addWidget(self.time_progress_label)
            progress_layout.addWidget(self.time_progress_bar)
            progress_layout.addWidget(self.summary_label)

            layout.addLayout(progress_layout)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Se estamos editando, carregar dados da meta existente
        if self.is_edit_mode:
            self.load_goal_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCheckBox {
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QProgressBar {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    text-align: center;
                    background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            if hasattr(self, 'save_button'):
                self.save_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")
            if hasattr(self, 'deposit_button'):
                self.deposit_button.setStyleSheet("background-color: #f39c12; color: #ecf0f1;")
            self.cancel_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QProgressBar {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            if hasattr(self, 'save_button'):
                self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
            if hasattr(self, 'deposit_button'):
                self.deposit_button.setStyleSheet("background-color: #FF9800; color: white;")
            self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")

    def toggle_deadline(self, checked):
        """Ativa/desativa o campo de prazo"""
        self.deadline_edit.setEnabled(checked)
        if hasattr(self, 'time_progress_label'):
            self.time_progress_label.setVisible(checked)
            self.time_progress_bar.setVisible(checked)

    def load_goal_data(self):
        """Carrega os dados da meta existente"""
        try:
            goal = self.parent().db_connection.execute(
                '''
                SELECT * FROM savings_goals
                WHERE id = ? AND user_id = ?
                ''',
                (self.goal_id, self.parent().user_id)
            ).fetchone()

            if not goal:
                QMessageBox.warning(self, "Erro", "Meta não encontrada.")
                self.reject()
                return

            # Preencher campos com dados da meta
            self.name_input.setText(goal['name'])
            self.target_input.setText(str(goal['target_amount']))
            self.current_input.setText(str(goal['current_amount']))

            # Se tiver prazo, configurar
            if goal['deadline']:
                self.has_deadline_check.setChecked(True)
                deadline_date = QDate.fromString(goal['deadline'], "yyyy-MM-dd")
                self.deadline_edit.setDate(deadline_date)

                # Calcular progresso de tempo
                start_date = datetime.strptime(goal['start_date'], '%Y-%m-%d').date()
                deadline_date = datetime.strptime(goal['deadline'], '%Y-%m-%d').date()
                today = datetime.now().date()

                total_days = (deadline_date - start_date).days
                days_passed = (today - start_date).days

                if total_days > 0:
                    time_progress = min(100, int((days_passed / total_days) * 100))
                    self.time_progress_bar.setValue(time_progress)

                    days_left = (deadline_date - today).days
                    if days_left > 0:
                        self.time_progress_bar.setFormat(f"{time_progress}% ({days_left} dias restantes)")
                    else:
                        self.time_progress_bar.setFormat("Prazo expirado!")
                        self.time_progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #e74c3c; }")
            else:
                self.time_progress_label.setVisible(False)
                self.time_progress_bar.setVisible(False)

            # Configurar categoria se existir
            if goal['category_id']:
                index = self.category_combo.findData(goal['category_id'])
                if index >= 0:
                    self.category_combo.setCurrentIndex(index)

            # Notas
            if goal['notes']:
                self.notes_input.setText(goal['notes'])

            # Calcular progresso financeiro
            target = goal['target_amount']
            current = goal['current_amount']

            if target > 0:
                progress = min(100, int((current / target) * 100))
                self.progress_bar.setValue(progress)
                self.progress_bar.setFormat(f"{progress}% (R$ {current:.2f} de R$ {target:.2f})")

                remaining = target - current
                self.summary_label.setText(f"Faltam R$ {remaining:.2f} para atingir a meta.")

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível carregar os dados da meta: {str(e)}")
            self.reject()

    def save_goal(self):
        """Salva ou atualiza a meta de economia"""
        try:
            # Validar campos obrigatórios
            name = self.name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "Erro", "O nome da meta não pode estar vazio.")
                return

            # Validar valor alvo
            try:
                target_amount = float(self.target_input.text().replace(',', '.'))
                if target_amount <= 0:
                    QMessageBox.warning(self, "Erro", "O valor alvo deve ser positivo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor alvo deve ser um número válido.")
                return

            # Validar valor atual
            try:
                current_text = self.current_input.text().strip()
                current_amount = float(current_text.replace(',', '.')) if current_text else 0
                if current_amount < 0:
                    QMessageBox.warning(self, "Erro", "O valor atual não pode ser negativo.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Erro", "O valor atual deve ser um número válido.")
                return

            # Obter prazo se configurado
            deadline = None
            if self.has_deadline_check.isChecked():
                deadline = self.deadline_edit.date().toString("yyyy-MM-dd")

            # Obter categoria selecionada
            category_id = self.category_combo.currentData()

            # Obter notas
            notes = self.notes_input.toPlainText().strip()

            # Salvar no banco de dados
            if self.is_edit_mode:
                # Atualizar meta existente
                self.parent().db_connection.execute(
                    '''
                    UPDATE savings_goals
                    SET name = ?, target_amount = ?, current_amount = ?,
                        deadline = ?, category_id = ?, notes = ?
                    WHERE id = ? AND user_id = ?
                    ''',
                    (name, target_amount, current_amount, deadline, category_id, notes,
                     self.goal_id, self.parent().user_id)
                )

                message = "Meta de economia atualizada com sucesso!"
            else:
                # Criar nova meta
                start_date = datetime.now().strftime("%Y-%m-%d")

                self.parent().db_connection.execute(
                    '''
                    INSERT INTO savings_goals
                    (user_id, name, target_amount, current_amount, start_date, deadline, category_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (self.parent().user_id, name, target_amount, current_amount,
                     start_date, deadline, category_id, notes)
                )

                message = "Nova meta de economia criada com sucesso!"

            self.parent().db_connection.commit()
            QMessageBox.information(self, "Sucesso", message)
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar a meta: {str(e)}")

    def add_deposit(self):
        """Adiciona um depósito à meta de economia"""
        # Mostrar diálogo para informar o valor do depósito
        amount, ok = QInputDialog.getDouble(
            self, "Adicionar Depósito",
            "Informe o valor do depósito (R$):",
            0, 0, 1000000, 2
        )

        if ok and amount > 0:
            try:
                # Atualizar valor atual
                goal = self.parent().db_connection.execute(
                    'SELECT current_amount, target_amount FROM savings_goals WHERE id = ?',
                    (self.goal_id,)
                ).fetchone()

                new_amount = goal['current_amount'] + amount

                # Não deixar ultrapassar o valor alvo
                if new_amount > goal['target_amount']:
                    excess = new_amount - goal['target_amount']
                    new_amount = goal['target_amount']
                    QMessageBox.information(
                        self, "Aviso",
                        f"O depósito excede o valor alvo em R$ {excess:.2f}. "
                        f"O valor atual foi ajustado para o valor alvo."
                    )

                # Atualizar no banco de dados
                self.parent().db_connection.execute(
                    'UPDATE savings_goals SET current_amount = ? WHERE id = ?',
                    (new_amount, self.goal_id)
                )
                self.parent().db_connection.commit()

                # Atualizar interface
                self.current_input.setText(str(new_amount))

                # Atualizar barra de progresso
                progress = min(100, int((new_amount / goal['target_amount']) * 100))
                self.progress_bar.setValue(progress)
                self.progress_bar.setFormat(f"{progress}% (R$ {new_amount:.2f} de R$ {goal['target_amount']:.2f})")

                # Atualizar resumo
                remaining = goal['target_amount'] - new_amount
                self.summary_label.setText(f"Faltam R$ {remaining:.2f} para atingir a meta.")

                QMessageBox.information(self, "Sucesso", f"Depósito de R$ {amount:.2f} adicionado com sucesso!")

                # Se atingiu a meta, celebrar!
                if new_amount >= goal['target_amount']:
                    QMessageBox.information(
                        self, "Parabéns!",
                        "Você atingiu sua meta de economia! 🎉"
                    )

            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Não foi possível adicionar o depósito: {str(e)}")


class CalendarDialog(QDialog):
    """Diálogo para visualizar transações em formato de calendário"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calendário Financeiro")
        self.resize(800, 600)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setSelectionMode(QCalendarWidget.SingleSelection)

        # Configurar formato personalizado para as datas
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

        # Lista de transações para o dia selecionado
        self.transactions_label = QLabel("Transações do dia selecionado:")
        self.transactions_list = QTextEdit()
        self.transactions_list.setReadOnly(True)

        # Estatísticas do mês
        self.month_stats_label = QLabel("Estatísticas do Mês:")
        self.month_stats = QTextEdit()
        self.month_stats.setReadOnly(True)
        self.month_stats.setMaximumHeight(100)

        # Botões
        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        # Conexão de sinais
        self.calendar.selectionChanged.connect(self.update_day_transactions)
        self.calendar.currentPageChanged.connect(self.update_calendar_data)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.calendar)

        # Layout dividido para transações e estatísticas
        split_layout = QHBoxLayout()

        # Layout para transações
        trans_layout = QVBoxLayout()
        trans_layout.addWidget(self.transactions_label)
        trans_layout.addWidget(self.transactions_list)

        # Layout para estatísticas
        stats_layout = QVBoxLayout()
        stats_layout.addWidget(self.month_stats_label)
        stats_layout.addWidget(self.month_stats)

        # Adicionar os layouts divididos
        split_layout.addLayout(trans_layout, 7)  # 70% para transações
        split_layout.addLayout(stats_layout, 3)  # 30% para estatísticas

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)

        # Carregar dados para o mês atual
        self.update_calendar_data()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QCalendarWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCalendarWidget QWidget {
                    alternate-background-color: #1e272e;
                }
                QCalendarWidget QAbstractItemView:enabled {
                    color: #ecf0f1;
                    background-color: #2d3436;
                    selection-background-color: #3498db;
                    selection-color: #ecf0f1;
                }
                QCalendarWidget QMenu {
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QCalendarWidget QToolButton {
                    color: #ecf0f1;
                    background-color: #2d3436;
                }
            """)
            self.close_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QCalendarWidget {
                    background-color: white;
                }
                QCalendarWidget QAbstractItemView:enabled {
                    color: #333;
                    selection-background-color: #4CAF50;
                    selection-color: white;
                }
            """)
            self.close_button.setStyleSheet("background-color: #f44336; color: white;")

    def update_calendar_data(self):
        """Atualiza os dados do calendário para o mês exibido"""
        try:
            current_date = self.calendar.selectedDate()
            year = current_date.year()
            month = current_date.month()

            # Limpar formatos anteriores
            self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

            # Obter todas as transações do mês
            transactions = self.parent().db_connection.execute(
                '''
                SELECT t.*, c.name as category_name
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND strftime('%Y', t.date) = ? AND strftime('%m', t.date) = ?
                ORDER BY t.date
                ''',
                (self.parent().user_id, f"{year:04d}", f"{month:02d}")
            ).fetchall()

            # Calcular saldo por dia
            day_balances = {}
            day_transactions = {}

            for t in transactions:
                date = QDate.fromString(t['date'], "yyyy-MM-dd")
                day_key = date.toString("yyyy-MM-dd")

                # Inicializar se necessário
                if day_key not in day_balances:
                    day_balances[day_key] = 0
                    day_transactions[day_key] = []

                # Adicionar valor (positivo para entradas, negativo para saídas)
                amount = t['amount']
                if t['transaction_type'] == 'saida':
                    amount = -amount

                day_balances[day_key] += amount
                day_transactions[day_key].append(t)

            # Definir formato para cada dia com transações
            positive_format = QTextCharFormat()
            positive_format.setBackground(QColor(200, 255, 200))  # Verde claro
            positive_format.setForeground(QColor(0, 100, 0))      # Verde escuro

            negative_format = QTextCharFormat()
            negative_format.setBackground(QColor(255, 200, 200))  # Vermelho claro
            negative_format.setForeground(QColor(150, 0, 0))      # Vermelho escuro

            neutral_format = QTextCharFormat()
            neutral_format.setBackground(QColor(220, 220, 220))   # Cinza claro
            neutral_format.setForeground(QColor(50, 50, 50))      # Cinza escuro

            # Aplicar formato a cada dia
            for day_key, balance in day_balances.items():
                date = QDate.fromString(day_key, "yyyy-MM-dd")

                if balance > 0:
                    self.calendar.setDateTextFormat(date, positive_format)
                elif balance < 0:
                    self.calendar.setDateTextFormat(date, negative_format)
                else:
                    self.calendar.setDateTextFormat(date, neutral_format)

            # Calcular estatísticas do mês
            total_income = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
            total_expense = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
            balance = total_income - total_expense

            # Número de dias com transações
            active_days = len(day_balances)

            # Calcular dia com maior entrada e maior saída
            if transactions:
                max_income_day = max(
                    [t for t in transactions if t['transaction_type'] == 'entrada'],
                    key=lambda x: x['amount'],
                    default=None
                )

                max_expense_day = max(
                    [t for t in transactions if t['transaction_type'] == 'saida'],
                    key=lambda x: x['amount'],
                    default=None
                )
            else:
                max_income_day = None
                max_expense_day = None

            # Atualizar estatísticas do mês
            stats_text = f"<b>Estatísticas de {current_date.toString('MMMM yyyy').capitalize()}:</b><br>"
            stats_text += f"Total de receitas: <span style='color: green;'>R$ {total_income:.2f}</span><br>"
            stats_text += f"Total de despesas: <span style='color: red;'>R$ {total_expense:.2f}</span><br>"

            if balance >= 0:
                stats_text += f"Saldo do mês: <span style='color: green;'>R$ {balance:.2f}</span><br>"
            else:
                stats_text += f"Saldo do mês: <span style='color: red;'>R$ {balance:.2f}</span><br>"

            stats_text += f"Dias com movimento: {active_days}<br>"

            if max_income_day:
                stats_text += f"Maior receita: R$ {max_income_day['amount']:.2f} ({max_income_day['date']})<br>"

            if max_expense_day:
                stats_text += f"Maior despesa: R$ {max_expense_day['amount']:.2f} ({max_expense_day['date']})<br>"

            self.month_stats.setHtml(stats_text)

            # Atualizar transações do dia selecionado
            self.update_day_transactions()

        except Exception as e:
            import traceback
            print(f"Erro ao atualizar dados do calendário: {e}")
            print(traceback.format_exc())
            self.month_stats.setText(f"Erro ao carregar estatísticas: {str(e)}")

    def update_day_transactions(self):
        """Atualiza a lista de transações para o dia selecionado"""
        try:
            selected_date = self.calendar.selectedDate().toString("yyyy-MM-dd")

            transactions = self.parent().db_connection.execute(
                '''
                SELECT t.*, c.name as category_name
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.date = ?
                ORDER BY t.transaction_type, t.amount DESC
                ''',
                (self.parent().user_id, selected_date)
            ).fetchall()

            if not transactions:
                self.transactions_list.setHtml("<i>Nenhuma transação neste dia.</i>")
                return

            # Calcular totais do dia
            total_income = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
            total_expense = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
            day_balance = total_income - total_expense

            # Gerar HTML para a lista de transações
            html = f"<h3>Transações de {self.calendar.selectedDate().toString('dd/MM/yyyy')}</h3>"

            # Resumo do dia
            html += "<p>"
            html += f"Receitas: <b style='color: green;'>R$ {total_income:.2f}</b> | "
            html += f"Despesas: <b style='color: red;'>R$ {total_expense:.2f}</b> | "

            if day_balance >= 0:
                html += f"Saldo: <b style='color: green;'>R$ {day_balance:.2f}</b>"
            else:
                html += f"Saldo: <b style='color: red;'>R$ {day_balance:.2f}</b>"

            html += "</p>"

            # Tabela de transações
            html += "<table width='100%' cellspacing='0' cellpadding='4' style='border: 1px solid #ccc;'>"
            html += "<tr style='background-color: #f0f0f0;'>"
            html += "<th align='left'>Descrição</th>"
            html += "<th align='right'>Valor</th>"
            html += "<th align='left'>Tipo</th>"
            html += "<th align='left'>Categoria</th>"
            html += "</tr>"

            row_style1 = "background-color: #ffffff;"
            row_style2 = "background-color: #f9f9f9;"
            current_style = row_style1

            for t in transactions:
                html += f"<tr style='{current_style}'>"
                html += f"<td>{t['description']}</td>"

                if t['transaction_type'] == 'entrada':
                    html += f"<td align='right' style='color: green;'>R$ {t['amount']:.2f}</td>"
                    html += "<td>Receita</td>"
                else:
                    html += f"<td align='right' style='color: red;'>R$ {t['amount']:.2f}</td>"
                    html += "<td>Despesa</td>"

                html += f"<td>{t['category_name'] or 'Sem categoria'}</td>"
                html += "</tr>"

                # Alternar estilos de linha
                current_style = row_style2 if current_style == row_style1 else row_style1

            html += "</table>"

            self.transactions_list.setHtml(html)

        except Exception as e:
            self.transactions_list.setText(f"Erro ao carregar transações: {str(e)}")


class CashFlowDialog(QDialog):
    """Diálogo para visualizar e projetar fluxo de caixa"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Previsão de Fluxo de Caixa")
        self.resize(800, 600)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.months_label = QLabel("Meses para projetar:")
        self.months_slider = QSlider(Qt.Horizontal)
        self.months_slider.setMinimum(1)
        self.months_slider.setMaximum(12)
        self.months_slider.setValue(3)
        self.months_slider.setTickPosition(QSlider.TicksBelow)
        self.months_slider.setTickInterval(1)
        self.months_value_label = QLabel("3 meses")

        # Botão para gerar projeção
        self.generate_button = QPushButton("Gerar Projeção")
        self.generate_button.clicked.connect(self.generate_projection)

        # Área para o gráfico
        self.figure = plt.figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)

        # Tabela de projeção detalhada
        self.projection_table = QTableWidget()
        self.projection_table.setColumnCount(4)
        self.projection_table.setHorizontalHeaderLabels(["Mês", "Receitas", "Despesas", "Saldo"])
        self.projection_table.horizontalHeader().setStretchLastSection(True)

        # Textos de resumo
        self.summary_label = QLabel("Resumo da Projeção:")
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(100)

        # Botão para fechar
        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        # Conectar sinal do slider
        self.months_slider.valueChanged.connect(self.update_months_label)

        # Layout
        layout = QVBoxLayout()

        # Layout para controles
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.months_label)
        controls_layout.addWidget(self.months_slider)
        controls_layout.addWidget(self.months_value_label)
        controls_layout.addWidget(self.generate_button)

        layout.addLayout(controls_layout)

        # Layout dividido para gráfico e tabela
        split_layout = QHBoxLayout()

        # Layout para gráfico
        chart_layout = QVBoxLayout()
        chart_layout.addWidget(self.canvas)

        # Layout para tabela e resumo
        table_layout = QVBoxLayout()
        table_layout.addWidget(self.projection_table)
        table_layout.addWidget(self.summary_label)
        table_layout.addWidget(self.summary_text)

        # Adicionar os layouts divididos
        split_layout.addLayout(chart_layout, 6)  # 60% para gráfico
        split_layout.addLayout(table_layout, 4)  # 40% para tabela e resumo

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)

        # Gerar projeção inicial
        self.generate_projection()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QTableWidget {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QSlider {
                    background-color: transparent;
                }
                QSlider::groove:horizontal {
                    height: 8px;
                    background: #4b6584;
                    margin: 2px 0;
                }
                QSlider::handle:horizontal {
                    background: #3498db;
                    border: 1px solid #2980b9;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 9px;
                }
                QTableWidget {
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    padding: 5px;
                    border: 1px solid #4b6584;
                }
            """)
            self.close_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
            self.generate_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")

            # Configurar cores para o gráfico
            plt.style.use('dark_background')
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QTableWidget {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QSlider::groove:horizontal {
                    height: 8px;
                    background: #ccc;
                    margin: 2px 0;
                }
                QSlider::handle:horizontal {
                    background: #4CAF50;
                    border: 1px solid #3d8b40;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 9px;
                }
                QTableWidget {
                    gridline-color: #ccc;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 5px;
                    border: 1px solid #ccc;
                }
            """)
            self.close_button.setStyleSheet("background-color: #f44336; color: white;")
            self.generate_button.setStyleSheet("background-color: #4CAF50; color: white;")

            # Configurar cores para o gráfico
            plt.style.use('default')

    def update_months_label(self, value):
        """Atualiza o label com o valor selecionado no slider"""
        self.months_value_label.setText(f"{value} {'mês' if value == 1 else 'meses'}")

    def generate_projection(self):
        """Gera a projeção de fluxo de caixa"""
        try:
            # Número de meses a projetar
            months_to_project = self.months_slider.value()

            # Obter mês e ano atuais
            today = datetime.now()
            current_month = today.month
            current_year = today.year

            # Calcular médias dos últimos 6 meses
            six_months_ago = today.replace(day=1) - timedelta(days=1)  # Último dia do mês anterior
            for _ in range(5):  # Voltar mais 5 meses (total 6)
                six_months_ago = six_months_ago.replace(day=1) - timedelta(days=1)

            six_months_ago_str = six_months_ago.strftime('%Y-%m-%d')

            # Obter receitas e despesas médias por mês dos últimos 6 meses
            monthly_stats = self.parent().db_connection.execute(
                '''
                SELECT
                    strftime('%Y-%m', date) as month,
                    SUM(CASE WHEN transaction_type = 'entrada' THEN amount ELSE 0 END) as income,
                    SUM(CASE WHEN transaction_type = 'saida' THEN amount ELSE 0 END) as expense
                FROM transactions
                WHERE user_id = ? AND date >= ?
                GROUP BY month
                ORDER BY month
                ''',
                (self.parent().user_id, six_months_ago_str)
            ).fetchall()

            # Se não houver dados suficientes, usar valores padrão
            if not monthly_stats:
                QMessageBox.warning(
                    self,
                    "Dados Insuficientes",
                    "Não há dados suficientes para uma projeção precisa. "
                    "Será mostrada uma estimativa baseada em valores fictícios."
                )
                avg_income = 1000
                avg_expense = 800
            else:
                # Calcular médias
                total_income = sum(month['income'] for month in monthly_stats)
                total_expense = sum(month['expense'] for month in monthly_stats)
                num_months = len(monthly_stats)

                avg_income = total_income / num_months
                avg_expense = total_expense / num_months

            # Obter saldo atual
            transactions = self.parent().db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?',
                (self.parent().user_id,)
            ).fetchall()

            entries_total = sum(t['amount'] for t in transactions if t['transaction_type'] == 'entrada')
            exits_total = sum(t['amount'] for t in transactions if t['transaction_type'] == 'saida')
            current_balance = entries_total - exits_total

            # Gerar projeção
            months = []
            incomes = []
            expenses = []
            balances = []

            running_balance = current_balance

            for i in range(months_to_project):
                # Calcular mês e ano
                month_num = (current_month + i) % 12
                if month_num == 0:
                    month_num = 12
                year_num = current_year + (current_month + i - 1) // 12

                month_name = QDate(year_num, month_num, 1).toString("MMM yyyy")
                months.append(month_name)

                # Adicionar variação aleatória às médias (entre -5% e +5%)
                variation = 0.1  # 10% de variação máxima
                income_variation = 1 + (random.random() * variation - variation / 2)
                expense_variation = 1 + (random.random() * variation - variation / 2)

                month_income = avg_income * income_variation
                month_expense = avg_expense * expense_variation

                # Adicionar valores previstos
                incomes.append(month_income)
                expenses.append(month_expense)

                # Calcular saldo do mês
                month_balance = month_income - month_expense
                running_balance += month_balance
                balances.append(running_balance)

            # Atualizar tabela
            self.projection_table.setRowCount(months_to_project)

            for i in range(months_to_project):
                # Coluna do mês
                self.projection_table.setItem(i, 0, QTableWidgetItem(months[i]))

                # Coluna de receitas
                income_item = QTableWidgetItem(f"R$ {incomes[i]:.2f}")
                income_item.setForeground(QColor(0, 128, 0))  # Verde
                self.projection_table.setItem(i, 1, income_item)

                # Coluna de despesas
                expense_item = QTableWidgetItem(f"R$ {expenses[i]:.2f}")
                expense_item.setForeground(QColor(200, 0, 0))  # Vermelho
                self.projection_table.setItem(i, 2, expense_item)

                # Coluna de saldo
                balance = balances[i]
                balance_item = QTableWidgetItem(f"R$ {balance:.2f}")
                if balance >= 0:
                    balance_item.setForeground(QColor(0, 128, 0))  # Verde
                else:
                    balance_item.setForeground(QColor(200, 0, 0))  # Vermelho
                self.projection_table.setItem(i, 3, balance_item)

            self.projection_table.resizeColumnsToContents()

            # Gerar resumo
            final_balance = balances[-1]
            total_projected_income = sum(incomes)
            total_projected_expense = sum(expenses)
            monthly_avg_balance = sum(income - expense for income, expense in zip(incomes, expenses)) / months_to_project

            summary_html = "<b>Resumo da Projeção:</b><br>"
            summary_html += f"Saldo atual: <b>R$ {current_balance:.2f}</b><br>"
            summary_html += f"Saldo projetado em {months_to_project} meses: <b>R$ {final_balance:.2f}</b><br>"
            summary_html += f"Total de receitas projetadas: <b style='color:green;'>R$ {total_projected_income:.2f}</b><br>"
            summary_html += f"Total de despesas projetadas: <b style='color:red;'>R$ {total_projected_expense:.2f}</b><br>"

            if monthly_avg_balance >= 0:
                summary_html += f"Saldo médio mensal: <b style='color:green;'>R$ {monthly_avg_balance:.2f}</b>"
            else:
                summary_html += f"Saldo médio mensal: <b style='color:red;'>R$ {monthly_avg_balance:.2f}</b>"

            self.summary_text.setHtml(summary_html)

            # Criar gráfico
            self.figure.clear()
            ax = self.figure.add_subplot(111)

            # Configuração das barras
            bar_width = 0.35
            x = np.arange(len(months))

            # Criar barras
            income_bars = ax.bar(x - bar_width/2, incomes, bar_width, label='Receitas', color='green', alpha=0.7)
            expense_bars = ax.bar(x + bar_width/2, expenses, bar_width, label='Despesas', color='red', alpha=0.7)

            # Adicionar linha de saldo
            ax.plot(x, balances, 'b-', marker='o', label='Saldo Acumulado')

            # Adicionar linha do zero
            ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)

            # Rótulos e legenda
            ax.set_xlabel('Mês')
            ax.set_ylabel('Valores (R$)')
            ax.set_title('Projeção de Fluxo de Caixa')
            ax.set_xticks(x)
            ax.set_xticklabels(months, rotation=45, ha='right')

            # Adicionar valores nas barras
            for bar in income_bars:
                height = bar.get_height()
                ax.annotate(f'R${height:.0f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  # 3 pontos de deslocamento vertical
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=8)

            for bar in expense_bars:
                height = bar.get_height()
                ax.annotate(f'R${height:.0f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  # 3 pontos de deslocamento vertical
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=8)

            ax.legend()
            self.figure.tight_layout()

            # Atualizar o canvas
            self.canvas.draw()

        except Exception as e:
            import traceback
            print(f"Erro ao gerar projeção: {e}")
            print(traceback.format_exc())
            QMessageBox.warning(self, "Erro", f"Não foi possível gerar a projeção: {str(e)}")


class TrendsDialog(QDialog):
    """Diálogo para visualizar tendências de gastos ao longo do tempo"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tendências de Gastos")
        self.resize(900, 600)
        self.is_dark_mode = parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False

        # Widgets
        self.period_label = QLabel("Período de Análise:")
        self.period_combo = QComboBox()
        self.period_combo.addItems(["Últimos 6 meses", "Último ano", "Últimos 2 anos", "Todo o histórico"])
        self.period_combo.setCurrentIndex(0)

        self.trend_type_label = QLabel("Tipo de Análise:")
        self.trend_type_combo = QComboBox()
        self.trend_type_combo.addItems([
            "Gastos por Mês",
            "Gastos por Categoria",
            "Evolução do Saldo",
            "Top Categorias por Mês"
        ])

        # Botão para gerar análise
        self.generate_button = QPushButton("Gerar Análise")
        self.generate_button.clicked.connect(self.generate_trends)

        # Área para o gráfico
        self.figure = plt.figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)

        # Texto de análise
        self.analysis_label = QLabel("Análise de Tendências:")
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)

        # Botão para fechar
        self.close_button = QPushButton("Fechar")
        self.close_button.clicked.connect(self.accept)

        # Layout
        layout = QVBoxLayout()

        # Layout para controles
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.period_label)
        controls_layout.addWidget(self.period_combo)
        controls_layout.addWidget(self.trend_type_label)
        controls_layout.addWidget(self.trend_type_combo)
        controls_layout.addWidget(self.generate_button)

        layout.addLayout(controls_layout)

        # Layout dividido para gráfico e análise
        split_layout = QVBoxLayout()
        split_layout.addWidget(self.canvas, 7)  # 70% para o gráfico

        analysis_layout = QVBoxLayout()
        analysis_layout.addWidget(self.analysis_label)
        analysis_layout.addWidget(self.analysis_text)

        split_layout.addLayout(analysis_layout, 3)  # 30% para a análise

        layout.addLayout(split_layout)
        layout.addWidget(self.close_button, 0, Qt.AlignRight)

        self.setLayout(layout)

        # Gerar análise inicial
        self.generate_trends()

        # Aplicar tema
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema claro ou escuro ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QComboBox {
                    padding: 8px;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436;
                    color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db;
                    color: #ecf0f1;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            self.close_button.setStyleSheet("background-color: #e74c3c; color: #ecf0f1;")
            self.generate_button.setStyleSheet("background-color: #2ecc71; color: #ecf0f1;")

            # Configurar cores para o gráfico
            plt.style.use('dark_background')
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f9f9f9;
                }
                QLabel {
                    font-weight: bold;
                    margin-top: 5px;
                }
                QTextEdit, QComboBox {
                    padding: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: white;
                }
                QPushButton {
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.close_button.setStyleSheet("background-color: #f44336; color: white;")
            self.generate_button.setStyleSheet("background-color: #4CAF50; color: white;")

            # Configurar cores para o gráfico
            plt.style.use('default')

    def get_period_date(self):
        """Retorna a data de início do período selecionado"""
        today = datetime.now()
        period_index = self.period_combo.currentIndex()

        if period_index == 0:  # Últimos 6 meses
            start_date = today - timedelta(days=180)
        elif period_index == 1:  # Último ano
            start_date = today - timedelta(days=365)
        elif period_index == 2:  # Últimos 2 anos
            start_date = today - timedelta(days=730)
        else:  # Todo o histórico
            return None

        return start_date.strftime('%Y-%m-%d')

    def generate_trends(self):
        """Gera a análise de tendências de gastos"""
        try:
            # Obter período selecionado
            start_date = self.get_period_date()

            # Tipo de análise selecionada
            trend_type = self.trend_type_combo.currentIndex()

            if trend_type == 0:  # Gastos por Mês
                self.analyze_monthly_expenses(start_date)
            elif trend_type == 1:  # Gastos por Categoria
                self.analyze_category_expenses(start_date)
            elif trend_type == 2:  # Evolução do Saldo
                self.analyze_balance_evolution(start_date)
            elif trend_type == 3:  # Top Categorias por Mês
                self.analyze_top_categories_by_month(start_date)

        except Exception as e:
            import traceback
            print(f"Erro ao gerar análise de tendências: {e}")
            print(traceback.format_exc())
            QMessageBox.warning(self, "Erro", f"Não foi possível gerar a análise: {str(e)}")

    def analyze_monthly_expenses(self, start_date):
        """Analisa gastos mensais ao longo do tempo"""
        # Construir a consulta SQL
        query = '''
            SELECT
                strftime('%Y-%m', date) as month,
                SUM(CASE WHEN transaction_type = 'entrada' THEN amount ELSE 0 END) as income,
                SUM(CASE WHEN transaction_type = 'saida' THEN amount ELSE 0 END) as expense
            FROM transactions
            WHERE user_id = ?
        '''

        params = [self.parent().user_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        query += " GROUP BY month ORDER BY month"

        # Executar consulta
        monthly_data = self.parent().db_connection.execute(query, params).fetchall()

        if not monthly_data:
            self.analysis_text.setHtml("<i>Não há dados suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Preparar dados para o gráfico
        months = [datetime.strptime(m['month'], '%Y-%m').strftime('%b %Y') for m in monthly_data]
        incomes = [m['income'] for m in monthly_data]
        expenses = [m['expense'] for m in monthly_data]
        balances = [inc - exp for inc, exp in zip(incomes, expenses)]

        # Criar gráfico
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Configuração das barras
        bar_width = 0.35
        x = np.arange(len(months))

        # Criar barras
        income_bars = ax.bar(x - bar_width/2, incomes, bar_width, label='Receitas', color='green', alpha=0.7)
        expense_bars = ax.bar(x + bar_width/2, expenses, bar_width, label='Despesas', color='red', alpha=0.7)

        # Adicionar linha de saldo
        ax.plot(x, balances, 'b-', marker='o', label='Saldo Mensal')

        # Adicionar linha do zero
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)

        # Rótulos e legenda
        ax.set_xlabel('Mês')
        ax.set_ylabel('Valores (R$)')
        ax.set_title('Evolução de Receitas e Despesas')
        ax.set_xticks(x)
        ax.set_xticklabels(months, rotation=45, ha='right')

        ax.legend()
        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        avg_income = sum(incomes) / len(incomes)
        avg_expense = sum(expenses) / len(expenses)
        avg_balance = sum(balances) / len(balances)

        # Calcular tendências
        if len(incomes) >= 3:
            income_trend = self.calculate_trend(incomes)
            expense_trend = self.calculate_trend(expenses)
            balance_trend = self.calculate_trend(balances)
        else:
            income_trend = expense_trend = balance_trend = 0

        # Mês com maior receita, despesa e saldo
        max_income_month = months[incomes.index(max(incomes))]
        max_expense_month = months[expenses.index(max(expenses))]
        max_balance_month = months[balances.index(max(balances))]
        min_balance_month = months[balances.index(min(balances))]

        # Texto da análise
        analysis_html = "<h3>Análise de Receitas e Despesas Mensais</h3>"

        analysis_html += "<p><b>Valores médios:</b><br>"
        analysis_html += f"Receita média mensal: <span style='color:green;'>R$ {avg_income:.2f}</span><br>"
        analysis_html += f"Despesa média mensal: <span style='color:red;'>R$ {avg_expense:.2f}</span><br>"

        if avg_balance >= 0:
            analysis_html += f"Saldo médio mensal: <span style='color:green;'>R$ {avg_balance:.2f}</span></p>"
        else:
            analysis_html += f"Saldo médio mensal: <span style='color:red;'>R$ {avg_balance:.2f}</span></p>"

        analysis_html += "<p><b>Destaques:</b><br>"
        analysis_html += f"Mês com maior receita: {max_income_month} (R$ {max(incomes):.2f})<br>"
        analysis_html += f"Mês com maior despesa: {max_expense_month} (R$ {max(expenses):.2f})<br>"
        analysis_html += f"Mês com melhor saldo: {max_balance_month} (R$ {max(balances):.2f})<br>"
        analysis_html += f"Mês com pior saldo: {min_balance_month} (R$ {min(balances):.2f})</p>"

        analysis_html += "<p><b>Tendências:</b><br>"

        if income_trend > 0:
            analysis_html += f"Suas receitas estão <span style='color:green;'>aumentando</span> ao longo do tempo.<br>"
        elif income_trend < 0:
            analysis_html += f"Suas receitas estão <span style='color:red;'>diminuindo</span> ao longo do tempo.<br>"
        else:
            analysis_html += f"Suas receitas estão <span style='color:blue;'>estáveis</span> ao longo do tempo.<br>"

        if expense_trend > 0:
            analysis_html += f"Suas despesas estão <span style='color:red;'>aumentando</span> ao longo do tempo.<br>"
        elif expense_trend < 0:
            analysis_html += f"Suas despesas estão <span style='color:green;'>diminuindo</span> ao longo do tempo.<br>"
        else:
            analysis_html += f"Suas despesas estão <span style='color:blue;'>estáveis</span> ao longo do tempo.<br>"

        if balance_trend > 0:
            analysis_html += f"Seu saldo mensal está <span style='color:green;'>melhorando</span> ao longo do tempo.</p>"
        elif balance_trend < 0:
            analysis_html += f"Seu saldo mensal está <span style='color:red;'>piorando</span> ao longo do tempo.</p>"
        else:
            analysis_html += f"Seu saldo mensal está <span style='color:blue;'>estável</span> ao longo do tempo.</p>"

        self.analysis_text.setHtml(analysis_html)

    def analyze_category_expenses(self, start_date):
        """Analisa gastos por categoria ao longo do tempo"""
        # Construir a consulta SQL para obter categorias
        category_query = '''
            SELECT id, name FROM categories
            WHERE user_id = ?
            ORDER BY name
        '''

        categories = self.parent().db_connection.execute(category_query, [self.parent().user_id]).fetchall()

        if not categories:
            self.analysis_text.setHtml("<i>Não há categorias definidas para análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Construir a consulta SQL para obter gastos por categoria e mês
        expense_query = '''
            SELECT
                strftime('%Y-%m', date) as month,
                category_id,
                SUM(amount) as total
            FROM transactions
            WHERE user_id = ? AND transaction_type = 'saida'
        '''

        params = [self.parent().user_id]

        if start_date:
            expense_query += " AND date >= ?"
            params.append(start_date)

        expense_query += " GROUP BY month, category_id ORDER BY month, category_id"

        # Executar consulta
        expenses_data = self.parent().db_connection.execute(expense_query, params).fetchall()

        if not expenses_data:
            self.analysis_text.setHtml("<i>Não há dados de despesas suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Organizar dados por mês e categoria
        months = sorted(set(e['month'] for e in expenses_data))
        formatted_months = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months]

        # Criar um dicionário para armazenar gastos por categoria e mês
        category_expenses = {cat['id']: [0] * len(months) for cat in categories}
        category_names = {cat['id']: cat['name'] for cat in categories}

        # Preencher os dados
        for expense in expenses_data:
            if expense['category_id'] in category_expenses:
                month_index = months.index(expense['month'])
                category_expenses[expense['category_id']][month_index] = expense['total']

        # Filtrar apenas as top 5 categorias por gasto total
        category_totals = {cat_id: sum(expenses) for cat_id, expenses in category_expenses.items()}
        top_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]

        # Criar gráfico
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Cores para as categorias
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

        # Criar linhas para cada categoria
        for i, (cat_id, _) in enumerate(top_categories):
            cat_name = category_names[cat_id]
            cat_data = category_expenses[cat_id]
            ax.plot(range(len(months)), cat_data, marker='o', linewidth=2, label=cat_name, color=colors[i % len(colors)])

        # Rótulos e legenda
        ax.set_xlabel('Mês')
        ax.set_ylabel('Despesas (R$)')
        ax.set_title('Evolução de Despesas por Categoria')
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(formatted_months, rotation=45, ha='right')

        ax.legend()
        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        analysis_html = "<h3>Análise de Despesas por Categoria</h3>"

        # Resumo das categorias principais
        analysis_html += "<p><b>Top 5 categorias com maior despesa:</b></p>"
        analysis_html += "<ol>"

        for cat_id, total in top_categories:
            cat_name = category_names[cat_id]
            cat_data = category_expenses[cat_id]

            # Calcular tendência
            if len(cat_data) >= 3:
                cat_trend = self.calculate_trend(cat_data)

                if cat_trend > 0:
                    trend_text = "<span style='color:red;'>aumentando</span>"
                elif cat_trend < 0:
                    trend_text = "<span style='color:green;'>diminuindo</span>"
                else:
                    trend_text = "<span style='color:blue;'>estável</span>"
            else:
                trend_text = "insuficiente para análise de tendência"

            # Calcular média mensal
            cat_avg = sum(cat_data) / len(cat_data)

            analysis_html += f"<li><b>{cat_name}</b>: Total de R$ {total:.2f}, média mensal de R$ {cat_avg:.2f}<br>"
            analysis_html += f"Tendência: {trend_text}</li>"

        analysis_html += "</ol>"

        # Recomendações
        analysis_html += "<p><b>Recomendações:</b></p><ul>"

        # Analisar categorias com tendência de aumento
        increasing_cats = []
        for cat_id, total in top_categories:
            cat_data = category_expenses[cat_id]
            if len(cat_data) >= 3 and self.calculate_trend(cat_data) > 0:
                increasing_cats.append(category_names[cat_id])

        if increasing_cats:
            analysis_html += f"<li>Considere reduzir gastos nas categorias com tendência de aumento: {', '.join(increasing_cats)}</li>"

        # Identificar categorias de maior impacto
        if top_categories:
            top_cat_id, _ = top_categories[0]
            top_cat_name = category_names[top_cat_id]
            analysis_html += f"<li>Sua maior categoria de despesa é <b>{top_cat_name}</b>. Foque em reduzir estes gastos para maior impacto no seu orçamento.</li>"

        analysis_html += "</ul>"

        self.analysis_text.setHtml(analysis_html)

    def analyze_balance_evolution(self, start_date):
        """Analisa a evolução do saldo ao longo do tempo"""
        # Construir a consulta SQL
        query = '''
            SELECT
                date,
                transaction_type,
                amount
            FROM transactions
            WHERE user_id = ?
        '''

        params = [self.parent().user_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        query += " ORDER BY date"

        # Executar consulta
        transactions = self.parent().db_connection.execute(query, params).fetchall()

        if not transactions:
            self.analysis_text.setHtml("<i>Não há dados suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Calcular saldo acumulado ao longo do tempo
        dates = []
        balances = []
        cumulative_balance = 0

        for t in transactions:
            date = datetime.strptime(t['date'], '%Y-%m-%d')

            amount = t['amount']
            if t['transaction_type'] == 'saida':
                amount = -amount

            cumulative_balance += amount

            dates.append(date)
            balances.append(cumulative_balance)

        # Criar gráfico
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Criar linha do saldo
        ax.plot(dates, balances, 'b-', linewidth=2)

        # Adicionar área preenchida
        ax.fill_between(dates, balances, 0, where=[b >= 0 for b in balances], color='green', alpha=0.3)
        ax.fill_between(dates, balances, 0, where=[b < 0 for b in balances], color='red', alpha=0.3)

        # Adicionar linha do zero
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)

        # Rótulos e formatação
        ax.set_xlabel('Data')
        ax.set_ylabel('Saldo (R$)')
        ax.set_title('Evolução do Saldo ao Longo do Tempo')

        # Formatar eixo X para mostrar datas
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        plt.xticks(rotation=45, ha='right')

        # Adicionar grade
        ax.grid(True, linestyle='--', alpha=0.7)

        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        analysis_html = "<h3>Análise da Evolução do Saldo</h3>"

        # Dados iniciais e finais
        initial_date = dates[0].strftime('%d/%m/%Y')
        final_date = dates[-1].strftime('%d/%m/%Y')
        initial_balance = balances[0]
        final_balance = balances[-1]

        # Calcular variação
        total_variation = final_balance - initial_balance
        percentage_variation = (total_variation / abs(initial_balance) * 100) if initial_balance != 0 else 0

        # Calcular tendência
        if len(balances) >= 10:
            # Usar os últimos 10 pontos para calcular a tendência recente
            recent_trend = self.calculate_trend(balances[-10:])
        else:
            recent_trend = self.calculate_trend(balances)

        # Identificar pontos de maior e menor saldo
        max_balance = max(balances)
        min_balance = min(balances)
        max_date = dates[balances.index(max_balance)].strftime('%d/%m/%Y')
        min_date = dates[balances.index(min_balance)].strftime('%d/%m/%Y')

        # Resumo geral
        analysis_html += "<p><b>Resumo:</b><br>"
        analysis_html += f"Período de análise: de {initial_date} a {final_date}<br>"

        if initial_balance >= 0:
            analysis_html += f"Saldo inicial: <span style='color:green;'>R$ {initial_balance:.2f}</span><br>"
        else:
            analysis_html += f"Saldo inicial: <span style='color:red;'>R$ {initial_balance:.2f}</span><br>"

        if final_balance >= 0:
            analysis_html += f"Saldo atual: <span style='color:green;'>R$ {final_balance:.2f}</span><br>"
        else:
            analysis_html += f"Saldo atual: <span style='color:red;'>R$ {final_balance:.2f}</span><br>"

        if total_variation >= 0:
            analysis_html += f"Variação total: <span style='color:green;'>+R$ {total_variation:.2f}</span> "
            analysis_html += f"(<span style='color:green;'>+{percentage_variation:.1f}%</span>)</p>"
        else:
            analysis_html += f"Variação total: <span style='color:red;'>-R$ {abs(total_variation):.2f}</span> "
            analysis_html += f"(<span style='color:red;'>{percentage_variation:.1f}%</span>)</p>"

        # Destaques
        analysis_html += "<p><b>Destaques:</b><br>"
        analysis_html += f"Maior saldo registrado: <span style='color:green;'>R$ {max_balance:.2f}</span> em {max_date}<br>"
        analysis_html += f"Menor saldo registrado: <span style='color:red;'>R$ {min_balance:.2f}</span> em {min_date}</p>"

        # Tendência
        analysis_html += "<p><b>Tendência atual:</b><br>"

        if recent_trend > 0:
            analysis_html += f"Seu saldo está com tendência de <span style='color:green;'>crescimento</span>.<br>"
            analysis_html += "Continue com o bom trabalho mantendo suas receitas acima das despesas!"
        elif recent_trend < 0:
            analysis_html += f"Seu saldo está com tendência de <span style='color:red;'>queda</span>.<br>"
            analysis_html += "Considere reduzir despesas ou aumentar receitas para reverter esta tendência."
        else:
            analysis_html += f"Seu saldo está <span style='color:blue;'>estável</span>.<br>"
            analysis_html += "Você está conseguindo manter um equilíbrio entre receitas e despesas."

        analysis_html += "</p>"

        # Períodos negativos
        negative_periods = []
        current_negative_start = None

        for i, balance in enumerate(balances):
            if balance < 0 and (i == 0 or balances[i-1] >= 0):
                current_negative_start = dates[i]
            elif balance >= 0 and i > 0 and balances[i-1] < 0 and current_negative_start:
                negative_periods.append((current_negative_start, dates[i-1]))
                current_negative_start = None

        # Se terminar em período negativo
        if balances[-1] < 0 and current_negative_start:
            negative_periods.append((current_negative_start, dates[-1]))

        if negative_periods:
            analysis_html += "<p><b>Períodos com saldo negativo:</b><ul>"

            for start, end in negative_periods:
                start_str = start.strftime('%d/%m/%Y')
                end_str = end.strftime('%d/%m/%Y')
                analysis_html += f"<li>De {start_str} a {end_str}</li>"

            analysis_html += "</ul></p>"

        self.analysis_text.setHtml(analysis_html)

    def analyze_top_categories_by_month(self, start_date):
        """Analisa as principais categorias de despesa por mês"""
        # Construir a consulta SQL
        query = '''
            SELECT
                strftime('%Y-%m', t.date) as month,
                c.name as category_name,
                SUM(t.amount) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND t.transaction_type = 'saida'
        '''

        params = [self.parent().user_id]

        if start_date:
            query += " AND t.date >= ?"
            params.append(start_date)

        query += " GROUP BY month, category_name ORDER BY month, total DESC"

        # Executar consulta
        expenses_data = self.parent().db_connection.execute(query, params).fetchall()

        if not expenses_data:
            self.analysis_text.setHtml("<i>Não há dados suficientes para esta análise.</i>")
            self.figure.clear()
            self.canvas.draw()
            return

        # Organizar dados por mês
        months = sorted(set(e['month'] for e in expenses_data))
        formatted_months = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months]

        # Para cada mês, obter as top 5 categorias
        month_categories = {}

        for month in months:
            month_data = [e for e in expenses_data if e['month'] == month]
            # Ordenar por total e pegar as top 5
            top_categories = sorted(month_data, key=lambda x: x['total'], reverse=True)[:5]
            month_categories[month] = top_categories

        # Criar gráfico
        self.figure.clear()

        # Definir o número de linhas e colunas para os subplots
        n_months = len(months)
        if n_months <= 3:
            rows, cols = 1, n_months
        elif n_months <= 6:
            rows, cols = 2, 3
        else:
            rows, cols = (n_months + 3) // 4, 4

        # Cores para as categorias
        colors = plt.cm.tab10.colors

        # Criar um subplot para cada mês
        for i, month in enumerate(months):
            ax = self.figure.add_subplot(rows, cols, i+1)

            # Dados para o mês
            categories = [c['category_name'] for c in month_categories[month]]
            values = [c['total'] for c in month_categories[month]]

            # Criar gráfico de pizza
            wedges, texts, autotexts = ax.pie(
                values,
                autopct='%1.1f%%',
                textprops={'fontsize': 8},
                colors=colors[:len(categories)]
            )

            # Ajustar textos
            for autotext in autotexts:
                autotext.set_fontsize(6)

            ax.set_title(formatted_months[i], fontsize=10)

            # Legenda separada para cada gráfico
            if categories:
                ax.legend(
                    wedges, categories,
                    loc="center left",
                    bbox_to_anchor=(1, 0, 0.5, 1),
                    fontsize=6
                )

        self.figure.tight_layout()

        # Atualizar o canvas
        self.canvas.draw()

        # Gerar análise textual
        analysis_html = "<h3>Análise das Principais Categorias de Despesa por Mês</h3>"

        # Resumo por mês
        analysis_html += "<p><b>Resumo das principais categorias de despesa:</b></p>"

        for i, month in enumerate(months):
            formatted_month = formatted_months[i]
            analysis_html += f"<p><b>{formatted_month}</b>:<br>"

            # Total do mês
            month_total = sum(c['total'] for c in month_categories[month])
            analysis_html += f"Total de despesas: R$ {month_total:.2f}<br>"

            # Listar principais categorias
            for j, category in enumerate(month_categories[month]):
                percentage = (category['total'] / month_total * 100)
                analysis_html += f"{j+1}. {category['category_name']}: R$ {category['total']:.2f} ({percentage:.1f}%)<br>"

            analysis_html += "</p>"

        # Análise de padrões
        analysis_html += "<p><b>Análise de Padrões:</b></p>"

        # Identificar categorias que aparecem consistentemente nos tops
        all_categories = set()
        for month_data in month_categories.values():
            for category in month_data:
                all_categories.add(category['category_name'])

        consistent_categories = []
        for category in all_categories:
            appearances = sum(1 for month_data in month_categories.values()
                             if any(c['category_name'] == category for c in month_data))

            # Se aparece em pelo menos 75% dos meses
            if appearances >= len(months) * 0.75:
                consistent_categories.append(category)

        if consistent_categories:
            analysis_html += "<p>Categorias que aparecem consistentemente entre as principais despesas:<ul>"
            for category in consistent_categories:
                analysis_html += f"<li>{category}</li>"
            analysis_html += "</ul></p>"

        # Categorias que tiveram mudanças significativas
        if len(months) >= 2:
            analysis_html += "<p>Mudanças significativas entre meses:</p><ul>"

            significant_changes = False

            for category in all_categories:
                monthly_values = []

                for month in months:
                    category_data = next((c for c in month_categories[month] if c['category_name'] == category), None)
                    if category_data:
                        monthly_values.append(category_data['total'])
                    else:
                        monthly_values.append(0)

                # Se tiver pelo menos 2 valores para comparar
                if len(monthly_values) >= 2 and sum(monthly_values) > 0:
                    max_value = max(monthly_values)
                    min_value = min(v for v in monthly_values if v > 0) if any(v > 0 for v in monthly_values) else 0

                    # Se a diferença for significativa (mais de 50%)
                    if min_value > 0 and max_value / min_value >= 1.5:
                        max_month = formatted_months[monthly_values.index(max_value)]
                        min_month = formatted_months[monthly_values.index(min_value)]

                        analysis_html += f"<li><b>{category}</b>: Variou de R$ {min_value:.2f} em {min_month} "
                        analysis_html += f"para R$ {max_value:.2f} em {max_month} "
                        analysis_html += f"(aumento de {(max_value/min_value - 1)*100:.1f}%)</li>"

                        significant_changes = True

            if not significant_changes:
                analysis_html += "<li>Não foram identificadas mudanças significativas entre os meses analisados.</li>"

            analysis_html += "</ul>"

        self.analysis_text.setHtml(analysis_html)

    def calculate_trend(self, values):
        """
        Calcula a tendência de uma série de valores
        Retorna um valor positivo se a tendência for de aumento, negativo se for de queda, ou zero se for estável
        """
        if len(values) < 2:
            return 0

        # Calcular coeficiente de inclinação da reta de tendência
        x = np.arange(len(values))
        y = np.array(values)

        # Remover valores NaN
        valid = ~np.isnan(y)
        if not np.any(valid) or np.sum(valid) < 2:
            return 0

        x = x[valid]
        y = y[valid]

        try:
            slope, _ = np.polyfit(x, y, 1)

            # Normalizar a inclinação em relação à média dos valores
            avg = np.mean(y)
            if avg != 0:
                normalized_slope = slope / abs(avg)
            else:
                normalized_slope = slope

            # Classificar a tendência
            if abs(normalized_slope) < 0.05:  # Se a variação for menor que 5% da média, considerar estável
                return 0
            else:
                return normalized_slope
        except:
            return 0


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestão Financeira Pessoal")
        self.setGeometry(100, 100, 800, 600)

        # Configurações de tema
        self.settings = QSettings("FinanceApp", "FinanceTracker")
        self.is_dark_mode = self.settings.value("dark_mode", False, type=bool)

        # Criar pasta 'dados' se não existir
        if not os.path.exists('dados'):
            os.makedirs('dados')

        self.db_connection = None
        self.user_id = None
        self.selected_year = datetime.now().year

        # Inicializar o assistente de IA
        self.ai_assistant = AIAssistant()

        # Criar ícone para a aplicação
        self.app_icon = QIcon('finance_icon.png')
        self.setWindowIcon(self.app_icon)

        # Inicializar system tray icon
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("Gestão Financeira Pessoal")

        # Menu para o ícone da bandeja
        tray_menu = QMenu()

        # Ações do menu
        show_action = QAction("Abrir", self)
        show_action.triggered.connect(self.show)

        hide_action = QAction("Minimizar", self)
        hide_action.triggered.connect(self.hide)

        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self.close_application)

        # Adicionar ações ao menu
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)

        # Configurar menu
        self.tray_icon.setContextMenu(tray_menu)

        # Evento ao clicar no ícone
        self.tray_icon.activated.connect(self.tray_icon_activated)

        # Ativar o ícone da bandeja
        self.tray_icon.show()

        # Widget central
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

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

        # Botão de modo escuro
        self.dark_mode_button = QPushButton("Modo Escuro: Desativado" if not self.is_dark_mode else "Modo Escuro: Ativado")
        self.dark_mode_button.clicked.connect(self.toggle_dark_mode)

        # Botão de configuração da IA
        self.ai_config_button = QPushButton("Configurar IA")
        self.ai_config_button.clicked.connect(self.show_ai_config)

        # Botão de consulta à IA
        self.ai_query_button = QPushButton("Consultar IA")
        self.ai_query_button.clicked.connect(self.show_ai_query_dialog)

        # Botões para novas funcionalidades
        self.budget_button = QPushButton("Orçamento Mensal")
        self.budget_button.clicked.connect(self.show_budget_dialog)

        self.cashflow_button = QPushButton("Fluxo de Caixa")
        self.cashflow_button.clicked.connect(self.show_cashflow_dialog)

        self.calendar_button = QPushButton("Calendário Financeiro")
        self.calendar_button.clicked.connect(self.show_calendar_dialog)

        self.trends_button = QPushButton("Tendências")
        self.trends_button.clicked.connect(self.show_trends_dialog)

        self.savings_goals_button = QPushButton("Metas de Economia")
        self.savings_goals_button.clicked.connect(self.show_savings_goals)

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

        # Aplicar tema inicial
        self.apply_theme()

        # Definir comportamento ao fechar a janela
        self.setMinimizeToTray()

        # Definir flag para iniciar minimizado
        self.start_minimized = True

    def closeEvent(self, event):
        """Controla o comportamento ao fechar a janela"""
        # Minimizar para a bandeja em vez de fechar
        if self.minimizeToTray:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Gestão Financeira",
                "Aplicativo minimizado para a bandeja do sistema.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            # Salvar configurações
            self.settings.setValue("dark_mode", self.is_dark_mode)

            # Se houver conexão com banco de dados, fechá-la
            if self.db_connection:
                self.db_connection.close()

            event.accept()

    def tray_icon_activated(self, reason):
        """Gerencia os eventos do ícone da bandeja"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()

    def close_application(self):
        """Fecha a aplicação completamente"""
        self.minimizeToTray = False
        self.close()

    def setMinimizeToTray(self):
        """Define se o aplicativo minimiza para a bandeja"""
        self.minimizeToTray = True

    def toggle_dark_mode(self):
        """Alterna entre modo claro e escuro"""
        self.is_dark_mode = not self.is_dark_mode

        # Atualizar texto do botão
        self.dark_mode_button.setText("Modo Escuro: Ativado" if self.is_dark_mode else "Modo Escuro: Desativado")

        # Aplicar o tema
        self.apply_theme()

        # Salvar configuração
        self.settings.setValue("dark_mode", self.is_dark_mode)

    def apply_theme(self):
        """Aplica o tema (claro ou escuro) a toda a aplicação"""
        if self.is_dark_mode:
            # Tema escuro
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)

            self.setPalette(palette)

            # Estilo para controles
            self.setStyleSheet("""
                QMainWindow, QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                    selection-background-color: #3498db;
                    selection-color: white;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    padding: 5px;
                    border: 1px solid #4b6584;
                }
                QTabWidget::pane {
                    border: 1px solid #4b6584;
                    background-color: #1e272e;
                }
                QTabBar::tab {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    padding: 8px 12px;
                    border: 1px solid #4b6584;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #3498db;
                }
            """)
        else:
            # Tema claro
            palette = QPalette()
            self.setPalette(palette)

            # Estilo para controles
            self.setStyleSheet("""
                QMainWindow, QDialog {
                    background-color: #f9f9f9;
                    color: #333333;
                }
                QLabel {
                    color: #333333;
                }
                QLineEdit, QComboBox, QDateEdit, QTextEdit {
                    background-color: white;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QTableWidget {
                    background-color: white;
                    color: #333333;
                    gridline-color: #ddd;
                    selection-background-color: #e3f2fd;
                    selection-color: #333333;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    color: #333333;
                    padding: 5px;
                    border: 1px solid #ccc;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0;
                    color: #333333;
                    padding: 8px 12px;
                    border: 1px solid #ccc;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #4CAF50;
                    color: white;
                }
            """)

    def show_ai_config(self):
        """
        Mostra o diálogo de configuração da IA
        """
        dialog = ConfigDialog(self)
        dialog.exec_()

        # Atualizar o assistente de IA com as novas configurações
        self.ai_assistant = AIAssistant()

    def show_ai_query_dialog(self):
        """
        Mostra o diálogo para consultar a IA
        """
        dialog = AIQueryDialog(self)
        dialog.exec_()

    def create_login_layout(self):
        """
        Cria o layout da tela de login
        Retorna: QVBoxLayout com os widgets de login
        """
        login_layout = QVBoxLayout()

        # Criar container para melhor organização
        login_container = QWidget()
        container_layout = QVBoxLayout(login_container)

        # Título
        title_label = QLabel("Sistema de Gestão Financeira")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 20px;")
        title_label.setAlignment(Qt.AlignCenter)

        # Adicionar widgets ao layout do container
        container_layout.addWidget(title_label)
        container_layout.addWidget(self.username_label)
        container_layout.addWidget(self.username_input)
        container_layout.addWidget(self.password_label)
        container_layout.addWidget(self.password_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.register_button)
        container_layout.addLayout(button_layout)
        container_layout.addWidget(self.save_login_button)

        # Centralizar o container no layout principal
        login_layout.addStretch(1)
        login_layout.addWidget(login_container, 0, Qt.AlignCenter)
        login_layout.addStretch(1)

        return login_layout

    def get_db_path(self, username):
        """
        Retorna o caminho para o banco de dados do usuário
        """
        return os.path.join('dados', f'{username}.db')

    def create_tables(self):
        """
        Cria as tabelas necessárias no banco de dados se não existirem
        """
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
                         name TEXT NOT NULL,
                         total_amount REAL DEFAULT 0,
                         is_payment_goal INTEGER DEFAULT 0,
                         FOREIGN KEY (user_id) REFERENCES users (id))''')

        # Tabela para orçamentos mensais
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS category_budgets
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         category_id INTEGER NOT NULL,
                         month INTEGER NOT NULL,
                         year INTEGER NOT NULL,
                         amount REAL NOT NULL,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         FOREIGN KEY (category_id) REFERENCES categories (id),
                         UNIQUE(user_id, category_id, month, year))''')

        # Tabela para metas de economia
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS savings_goals
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         name TEXT NOT NULL,
                         target_amount REAL NOT NULL,
                         current_amount REAL DEFAULT 0,
                         start_date TEXT NOT NULL,
                         deadline TEXT,
                         category_id INTEGER,
                         notes TEXT,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         FOREIGN KEY (category_id) REFERENCES categories (id))''')

        # Tabela de configurações do usuário
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS user_settings
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         setting_key TEXT NOT NULL,
                         setting_value TEXT,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         UNIQUE(user_id, setting_key))''')

        # Tabela de versão do banco de dados
        self.db_connection.execute('''CREATE TABLE IF NOT EXISTS db_version
                        (version INTEGER)''')

    def login(self):
        """
        Realiza o login do usuário
        Verifica credenciais e carrega o dashboard se autenticado
        """
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Erro", "Por favor, preencha todos os campos.")
            return

        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        # Criar tabelas se não existirem
        self.create_tables()

        # Verificar e atualizar esquema do banco de dados se necessário
        if not DBUpdater.check_and_update(self.db_connection, username):
            QMessageBox.critical(self, "Erro", "Não foi possível atualizar o banco de dados. Contate o suporte.")
            self.db_connection.close()
            return

        user = self.db_connection.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                            (username, password)).fetchone()
        if user:
            self.user_id = user['id']
            # Remover o layout de login
            self.clear_layout(self.main_layout)
            self.load_dashboard()

            # Carregar preferências do usuário
            self.load_user_preferences()
        else:
            QMessageBox.warning(self, "Erro", "Usuário ou senha incorretos.")
            self.db_connection.close()

    def load_user_preferences(self):
        """Carrega preferências do usuário do banco de dados"""
        try:
            # Carregar tema
            theme_setting = self.db_connection.execute(
                "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = 'dark_mode'",
                (self.user_id,)
            ).fetchone()

            if theme_setting:
                self.is_dark_mode = theme_setting['setting_value'].lower() == 'true'
                self.dark_mode_button.setText("Modo Escuro: Ativado" if self.is_dark_mode else "Modo Escuro: Desativado")
                self.apply_theme()
        except:
            pass

    def save_user_preferences(self):
        """Salva preferências do usuário no banco de dados"""
        try:
            # Verificar se já existe uma configuração
            existing = self.db_connection.execute(
                "SELECT id FROM user_settings WHERE user_id = ? AND setting_key = 'dark_mode'",
                (self.user_id,)
            ).fetchone()

            if existing:
                # Atualizar configuração existente
                self.db_connection.execute(
                    "UPDATE user_settings SET setting_value = ? WHERE user_id = ? AND setting_key = 'dark_mode'",
                    (str(self.is_dark_mode), self.user_id)
                )
            else:
                # Criar nova configuração
                self.db_connection.execute(
                    "INSERT INTO user_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
                    (self.user_id, 'dark_mode', str(self.is_dark_mode))
                )

            self.db_connection.commit()
        except:
            pass

    def register(self):
        """
        Registra um novo usuário
        Cria um novo banco de dados para o usuário
        """
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Erro", "Por favor, preencha todos os campos.")
            return

        db_path = self.get_db_path(username)
        self.db_connection = sqlite3.connect(db_path)
        self.db_connection.row_factory = sqlite3.Row

        self.create_tables()

        # Definir versão do banco de dados
        self.db_connection.execute('INSERT INTO db_version VALUES (?)', (DB_VERSION,))

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
        """
        Carrega o dashboard principal com todos os widgets e dados
        """
        # Layout principal
        dashboard_layout = QVBoxLayout()

        # Adicionar um título
        title_label = QLabel(f"Gestão Financeira - {self.username_input.text()}")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px 0;")
        dashboard_layout.addWidget(title_label)

        # Saldo e pesquisa em um layout horizontal
        top_layout = QHBoxLayout()

        # Estilizar o label de saldo
        self.balance_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            padding: 10px;
            border-radius: 4px;
        """)

        top_layout.addWidget(self.balance_label)

        # Estilizar o campo de pesquisa
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_icon_label = QLabel("🔍")
        search_layout.addWidget(search_icon_label)
        search_layout.addWidget(self.search_input)

        top_layout.addWidget(search_container)
        dashboard_layout.addLayout(top_layout)

        # Adicionar botões de ano
        year_group = QGroupBox("Filtrar por Ano:")
        dashboard_layout.addLayout(self.year_buttons_layout)

        # Layout para botões de ferramentas
        tools_layout = QHBoxLayout()

        # Adicionar os novos botões
        tools_layout.addWidget(self.budget_button)
        tools_layout.addWidget(self.cashflow_button)
        tools_layout.addWidget(self.calendar_button)
        tools_layout.addWidget(self.trends_button)
        tools_layout.addWidget(self.savings_goals_button)

        dashboard_layout.addLayout(tools_layout)

        # Transações
        transactions_group = QGroupBox("Transações")
        transactions_layout = QVBoxLayout()
        transactions_layout.addWidget(self.transactions_table)

        transaction_button_layout = QHBoxLayout()
        transaction_button_layout.addWidget(self.add_transaction_button)
        transaction_button_layout.addWidget(self.edit_transaction_button)
        transaction_button_layout.addWidget(self.delete_transaction_button)

        transactions_layout.addLayout(transaction_button_layout)
        transactions_group.setLayout(transactions_layout)

        dashboard_layout.addWidget(transactions_group)

        # Categorias e Notas em um layout horizontal
        bottom_layout = QHBoxLayout()

        # Categorias
        categories_group = QGroupBox("Categorias")
        categories_layout = QVBoxLayout()
        categories_layout.addWidget(self.categories_table)

        category_button_layout = QHBoxLayout()
        category_button_layout.addWidget(self.add_category_button)
        category_button_layout.addWidget(self.edit_category_button)
        category_button_layout.addWidget(self.delete_category_button)

        categories_layout.addLayout(category_button_layout)
        categories_group.setLayout(categories_layout)

        # Notas
        notes_group = QGroupBox("Notas")
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(self.notes_table)

        note_button_layout = QHBoxLayout()
        note_button_layout.addWidget(self.add_note_button)
        note_button_layout.addWidget(self.edit_note_button)
        note_button_layout.addWidget(self.delete_note_button)

        notes_layout.addLayout(note_button_layout)
        notes_group.setLayout(notes_layout)

        bottom_layout.addWidget(categories_group)
        bottom_layout.addWidget(notes_group)

        dashboard_layout.addLayout(bottom_layout)

        # Botões de relatórios, gráficos e IA
        ai_layout = QHBoxLayout()

        # Botões para relatórios e gráficos
        report_button = QPushButton("📊 Gerar Relatório")
        report_button.clicked.connect(self.generate_category_report)

        graph_button = QPushButton("📈 Gerar Gráfico")
        graph_button.clicked.connect(self.generate_category_graph)

        export_report_button = QPushButton("📋 Exportar Relatório")
        export_report_button.clicked.connect(self.export_report)

        ai_layout.addWidget(report_button)
        ai_layout.addWidget(graph_button)
        ai_layout.addWidget(export_report_button)
        ai_layout.addWidget(self.ai_config_button)
        ai_layout.addWidget(self.ai_query_button)

        dashboard_layout.addLayout(ai_layout)

        # Layout para botões de modo e logout
        action_layout = QHBoxLayout()
        action_layout.addWidget(self.dark_mode_button)
        action_layout.addStretch()
        action_layout.addWidget(self.logout_button)

        dashboard_layout.addLayout(action_layout)

        # Adicionar o layout do dashboard ao layout principal
        self.main_layout.addLayout(dashboard_layout)

        # Carregar dados
        self.load_transactions()
        self.load_notes()
        self.load_categories()
        self.update_balance()
        self.update_year_buttons()  # Atualizar botões de ano

    def export_report(self):
        """
        Exporta um relatório financeiro completo para um arquivo de texto ou CSV
        """
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

        if not transactions:
            QMessageBox.information(self, "Informação", "Não há transações para exportar no período selecionado.")
            return

        # Perguntar ao usuário qual formato deseja exportar
        format_dialog = QDialog(self)
        format_dialog.setWindowTitle("Escolher Formato de Exportação")
        format_dialog.setFixedSize(400, 150)

        layout = QVBoxLayout()

        # Título e instruções
        title_label = QLabel("Escolha o formato de exportação:")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Botões de formato
        buttons_layout = QHBoxLayout()

        txt_button = QPushButton("Texto (.txt)")
        txt_button.clicked.connect(lambda: format_dialog.done(1))  # 1 para TXT

        csv_button = QPushButton("Excel (.csv)")
        csv_button.clicked.connect(lambda: format_dialog.done(2))  # 2 para CSV

        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(format_dialog.reject)

        buttons_layout.addWidget(txt_button)
        buttons_layout.addWidget(csv_button)
        buttons_layout.addWidget(cancel_button)

        layout.addLayout(buttons_layout)
        format_dialog.setLayout(layout)

        # Mostrar diálogo e obter escolha
        result = format_dialog.exec_()

        if result == 0:  # Cancelado
            return

        # Determinar o formato e extensão
        if result == 1:  # TXT
            file_extension = "txt"
            file_filter = "Arquivos de Texto (*.txt)"
        else:  # CSV
            file_extension = "csv"
            file_filter = "Arquivos CSV (*.csv)"

        # Abrir diálogo para salvar arquivo
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório",
            f"relatorio_{self.selected_year}.{file_extension}",
            file_filter
        )

        if not file_path:
            return

        try:
            if result == 1:  # TXT
                self.export_txt_report(file_path, transactions)
            else:  # CSV
                self.export_csv_report(file_path, transactions)

            QMessageBox.information(self, "Sucesso", f"Relatório exportado com sucesso!\nArquivo: {file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível exportar o relatório.\nErro: {str(e)}")

    def export_txt_report(self, file_path, transactions):
        """
        Exporta o relatório em formato de texto
        """
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

        # Escrever no arquivo
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    def export_csv_report(self, file_path, transactions):
        """
        Exporta o relatório em formato CSV para Excel
        """
        import csv

        # Abrir arquivo CSV para escrita
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as csv_file:
            # Criar escritor CSV
            csv_writer = csv.writer(csv_file, delimiter=';')  # Usar ponto e vírgula como delimitador para melhor compatibilidade com Excel brasileiro

            # Escrever cabeçalho do relatório
            csv_writer.writerow([f"RELATÓRIO DE TRANSAÇÕES - Ano: {self.selected_year}"])
            csv_writer.writerow([])  # Linha em branco

            # Escrever cabeçalho das transações
            csv_writer.writerow(["ID", "Descrição", "Valor (R$)", "Tipo", "Data", "Categoria"])

            # Escrever dados das transações
            for t in transactions:
                csv_writer.writerow([
                    t['id'],
                    t['description'],
                    f"{t['amount']:.2f}".replace('.', ','),  # Usar vírgula como separador decimal para Excel brasileiro
                    t['transaction_type'],
                    t['date'],
                    t['category_name'] or ""
                ])

            csv_writer.writerow([])  # Linha em branco
            csv_writer.writerow(["RESUMO POR CATEGORIA"])

            # Consultar o resumo de gastos por categoria
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

            # Escrever resumo por categoria
            csv_writer.writerow(["Categoria", "Total Gasto (R$)"])
            for cat in categories:
                csv_writer.writerow([
                    cat[0],
                    f"{cat[1]:.2f}".replace('.', ',')
                ])

            csv_writer.writerow([])  # Linha em branco

            # Informações de saldo geral
            transactions_all = self.db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?', (self.user_id,)
            ).fetchall()
            entries_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'entrada')
            exits_total = sum(t['amount'] for t in transactions_all if t['transaction_type'] == 'saida')
            balance = entries_total - exits_total

            # Escrever saldo geral
            csv_writer.writerow(["RESUMO GERAL"])
            csv_writer.writerow(["Total de Entradas (R$)", f"{entries_total:.2f}".replace('.', ',')])
            csv_writer.writerow(["Total de Saídas (R$)", f"{exits_total:.2f}".replace('.', ',')])
            csv_writer.writerow(["Saldo Total (R$)", f"{balance:.2f}".replace('.', ',')])

    def update_year_buttons(self):
        """
        Atualiza os botões de ano com base nas transações existentes
        """
        # Limpar botões existentes
        while self.year_buttons_layout.count():
            child = self.year_buttons_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Obter anos disponíveis
        years = self.db_connection.execute(
            '''
            SELECT DISTINCT strftime('%Y', date) as year
            FROM transactions
            WHERE user_id = ?
            ORDER BY year DESC
            ''', (self.user_id,)
        ).fetchall()

        # Adicionar botão para cada ano
        for year in years:
            year_button = QPushButton(year['year'])
            year_button.setCheckable(True)
            year_button.setChecked(year['year'] == str(self.selected_year))
            year_button.toggled.connect(lambda checked, y=year['year']: self.toggle_year(y, checked))
            self.year_buttons_layout.addWidget(year_button)

    def toggle_year(self, year, checked):
        """
        Alterna o ano selecionado para filtrar transações
        """
        if checked:
            self.selected_year = int(year)
            self.load_transactions()
        else:
            # Verificar se algum botão está marcado
            any_checked = False
            for i in range(self.year_buttons_layout.count()):
                button = self.year_buttons_layout.itemAt(i).widget()
                if button and button.isChecked():
                    any_checked = True
                    break

            # Se nenhum botão estiver marcado, voltar para o ano atual
            if not any_checked:
                self.selected_year = datetime.now().year
                self.load_transactions()

    def load_transactions(self):
        """
        Carrega as transações do usuário com filtragem por ano e texto de pesquisa
        """
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

        # Configurar a tabela
        self.transactions_table.setRowCount(len(transactions))
        for i, transaction in enumerate(transactions):
            # Definir cor de fundo com base no tipo (entrada/saída)
            entry_color = QColor("#E8F5E9")  # Verde claro para entradas
            exit_color = QColor("#FFEBEE")   # Vermelho claro para saídas

            # Ajustar cores para o tema escuro
            if self.is_dark_mode:
                entry_color = QColor("#1B5E20")  # Verde escuro para entradas
                exit_color = QColor("#B71C1C")   # Vermelho escuro para saídas

            # Criar itens da tabela
            id_item = QTableWidgetItem(str(transaction['id']))
            desc_item = QTableWidgetItem(transaction['description'])

            # Formatar valor com 2 casas decimais
            amount_text = f"R$ {transaction['amount']:.2f}"
            amount_item = QTableWidgetItem(amount_text)

            type_item = QTableWidgetItem(transaction['transaction_type'])
            date_item = QTableWidgetItem(transaction['date'])
            category_item = QTableWidgetItem(transaction['category_name'] or "")

            # Definir cor de fundo com base no tipo
            row_color = entry_color if transaction['transaction_type'] == 'entrada' else exit_color

            # Aplicar cor aos itens
            for item in [id_item, desc_item, amount_item, type_item, date_item, category_item]:
                item.setBackground(row_color)

            # Adicionar itens à tabela
            self.transactions_table.setItem(i, 0, id_item)
            self.transactions_table.setItem(i, 1, desc_item)
            self.transactions_table.setItem(i, 2, amount_item)
            self.transactions_table.setItem(i, 3, type_item)
            self.transactions_table.setItem(i, 4, date_item)
            self.transactions_table.setItem(i, 5, category_item)

        # Ajustar largura das colunas
        self.transactions_table.resizeColumnsToContents()

    def load_notes(self):
        """
        Carrega as notas do usuário
        """
        notes = self.db_connection.execute('SELECT * FROM notes WHERE user_id = ?', (self.user_id,)).fetchall()
        self.notes_table.setRowCount(len(notes))
        for i, note in enumerate(notes):
            id_item = QTableWidgetItem(str(note['id']))
            note_item = QTableWidgetItem(note['note'])

            # Adicionar itens à tabela
            self.notes_table.setItem(i, 0, id_item)
            self.notes_table.setItem(i, 1, note_item)

        # Ajustar largura das colunas
        self.notes_table.resizeColumnsToContents()

    def load_categories(self):
        """
        Carrega as categorias do usuário
        """
        categories = self.db_connection.execute('SELECT * FROM categories WHERE user_id = ?', (self.user_id,)).fetchall()
        self.categories_table.setRowCount(len(categories))
        for i, category in enumerate(categories):
            id_item = QTableWidgetItem(str(category['id']))
            name_item = QTableWidgetItem(category['name'])

            # Destacar visualmente categorias com meta de quitação
            if category['is_payment_goal'] == 1:
                payment_color = QColor("#E8F5FE") if not self.is_dark_mode else QColor("#01579B")
                id_item.setBackground(payment_color)
                name_item.setBackground(payment_color)

                # Incluir indicador visual de meta de quitação
                name_item.setText(f"{category['name']} 🎯")

            # Adicionar itens à tabela
            self.categories_table.setItem(i, 0, id_item)
            self.categories_table.setItem(i, 1, name_item)

        # Ajustar largura das colunas
        self.categories_table.resizeColumnsToContents()

    def update_balance(self):
        """
        Atualiza o saldo total do usuário
        """
        transactions = self.db_connection.execute('SELECT * FROM transactions WHERE user_id = ?', (self.user_id,)).fetchall()
        entries_total = sum(transaction['amount'] for transaction in transactions if transaction['transaction_type'] == 'entrada')
        exits_total = sum(transaction['amount'] for transaction in transactions if transaction['transaction_type'] == 'saida')
        balance = entries_total - exits_total

        # Definir cor com base no saldo (positivo ou negativo)
        if self.is_dark_mode:
            if balance >= 0:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #4CAF50;
                    background-color: #263238;
                    padding: 10px;
                    border-radius: 4px;
                """)
            else:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #F44336;
                    background-color: #263238;
                    padding: 10px;
                    border-radius: 4px;
                """)
        else:
            if balance >= 0:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #2e7d32;
                    background-color: #e8f5e9;
                    padding: 10px;
                    border-radius: 4px;
                """)
            else:
                self.balance_label.setStyleSheet("""
                    font-size: 16px;
                    font-weight: bold;
                    color: #c62828;
                    background-color: #ffebee;
                    padding: 10px;
                    border-radius: 4px;
                """)

        self.balance_label.setText(f"Saldo: R$ {balance:.2f}")

    def show_add_transaction_dialog(self):
        """
        Mostra diálogo para adicionar uma nova transação
        """
        dialog = AddTransactionDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_transactions()
            self.update_balance()
            self.update_year_buttons()

    def show_edit_transaction_dialog(self):
        """
        Mostra diálogo para editar uma transação existente
        """
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(self.transactions_table.item(selected_row, 0).text())
            dialog = EditTransactionDialog(self, transaction_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma transação para editar.")

    def delete_transaction(self):
        """
        Exclui a transação selecionada
        """
        selected_row = self.transactions_table.currentRow()
        if selected_row != -1:
            transaction_id = int(self.transactions_table.item(selected_row, 0).text())

            # Pedir confirmação
            reply = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                "Tem certeza que deseja excluir esta transação?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.db_connection.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
                self.db_connection.commit()
                self.load_transactions()
                self.update_balance()
                self.update_year_buttons()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma transação para excluir.")

    def show_add_note_dialog(self):
        """
        Mostra diálogo para adicionar uma nova nota
        """
        dialog = AddNoteDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_notes()

    def show_edit_note_dialog(self):
        """
        Mostra diálogo para editar uma nota existente
        """
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())
            dialog = EditNoteDialog(self, note_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_notes()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma nota para editar.")

    def delete_note(self):
        """
        Exclui a nota selecionada
        """
        selected_row = self.notes_table.currentRow()
        if selected_row != -1:
            note_id = int(self.notes_table.item(selected_row, 0).text())

            # Pedir confirmação
            reply = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                "Tem certeza que deseja excluir esta nota?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.db_connection.execute('DELETE FROM notes WHERE id = ?', (note_id,))
                self.db_connection.commit()
                self.load_notes()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma nota para excluir.")

    def show_add_category_dialog(self):
        """
        Mostra diálogo para adicionar uma nova categoria
        """
        dialog = AddCategoryDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.load_categories()

    def show_edit_category_dialog(self):
        """
        Mostra diálogo para editar uma categoria existente
        """
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(self.categories_table.item(selected_row, 0).text())
            dialog = EditCategoryDialog(self, category_id)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.load_categories()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma categoria para editar.")

    def delete_category(self):
        """
        Exclui a categoria selecionada se não houver transações associadas
        """
        selected_row = self.categories_table.currentRow()
        if selected_row != -1:
            category_id = int(self.categories_table.item(selected_row, 0).text())
            category_name = self.categories_table.item(selected_row, 1).text()

            # Verificar se há transações usando esta categoria
            transactions = self.db_connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE category_id = ?",
                (category_id,)
            ).fetchone()

            if transactions[0] > 0:
                QMessageBox.warning(
                    self,
                    "Erro",
                    f"Não é possível excluir a categoria '{category_name}' pois existem {transactions[0]} transações vinculadas a ela."
                )
                return

            # Pedir confirmação
            reply = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                f"Tem certeza que deseja excluir a categoria '{category_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.db_connection.execute('DELETE FROM categories WHERE id = ?', (category_id,))
                self.db_connection.commit()
                self.load_categories()
        else:
            QMessageBox.warning(self, "Aviso", "Selecione uma categoria para excluir.")

    def save_login(self):
        """
        Salva as credenciais de login em um arquivo local
        """
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Erro", "Por favor, preencha todos os campos.")
            return

        with open("login.txt", "w") as f:
            f.write(f"{username},{password}")

        QMessageBox.information(self, "Sucesso", "Login salvo com sucesso.")

    def load_saved_login(self):
        """
        Carrega as credenciais de login salvas
        """
        if os.path.exists("login.txt"):
            with open("login.txt", "r") as f:
                try:
                    username, password = f.read().split(",")
                    self.username_input.setText(username)
                    self.password_input.setText(password)
                except:
                    pass  # Ignora erros de formato no arquivo

    def generate_category_report(self):
        """
        Gera um relatório de gastos por categoria
        """
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

        if not categories:
            QMessageBox.information(self, "Informação", "Não há dados de categorias para o período selecionado.")
            return

        report_dialog = QDialog(self)
        report_dialog.setWindowTitle(f"Relatório de Gastos por Categoria - {self.selected_year}")
        report_dialog.setMinimumSize(500, 400)
        report_layout = QVBoxLayout()

        # Título
        title_label = QLabel(f"Relatório de Gastos por Categoria - {self.selected_year}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignCenter)
        report_layout.addWidget(title_label)

        # Tabela de relatório
        report_table = QTableWidget(report_dialog)
        report_table.setColumnCount(3)
        report_table.setHorizontalHeaderLabels(["Categoria", "Total Gasto", "Porcentagem"])

        report_table.setAlternatingRowColors(True)
        report_table.setEditTriggers(QTableWidget.NoEditTriggers)
        report_table.setSelectionBehavior(QTableWidget.SelectRows)
        report_table.horizontalHeader().setStretchLastSection(True)

        # Calcular total geral
        total_amount = sum(category[1] for category in categories)

        # Preencher tabela
        report_table.setRowCount(len(categories))
        for i, category in enumerate(categories):
            name_item = QTableWidgetItem(category[0])
            amount_item = QTableWidgetItem(f"R$ {category[1]:.2f}")

            # Calcular porcentagem
            percentage = (category[1] / total_amount * 100) if total_amount > 0 else 0
            percentage_item = QTableWidgetItem(f"{percentage:.2f}%")

            report_table.setItem(i, 0, name_item)
            report_table.setItem(i, 1, amount_item)
            report_table.setItem(i, 2, percentage_item)

        report_layout.addWidget(report_table)

        # Botão de fechar
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(report_dialog.accept)

        report_layout.addWidget(close_button, 0, Qt.AlignCenter)

        report_dialog.setLayout(report_layout)

        # Aplicar tema
        if self.is_dark_mode:
            report_dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                }
                QPushButton {
                    background-color: #3498db;
                    color: #ecf0f1;
                    padding: 8px 15px;
                    border-radius: 4px;
                }
            """)

        report_dialog.exec_()

    def generate_category_graph(self):
        """
        Gera um gráfico de gastos por categoria
        """
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

        if not categories:
            QMessageBox.information(self, "Informação", "Não há dados de categorias para o período selecionado.")
            return

        # Limitar a 10 categorias para melhor visualização
        if len(categories) > 10:
            top_categories = categories[:9]
            # Agrupar o restante como "Outros"
            others_total = sum(category[1] for category in categories[9:])
            categories = top_categories + [("Outros", others_total)]

        category_names = [category[0] for category in categories]
        total_spent = [category[1] for category in categories]

        # Configurar o gráfico
        plt.figure(figsize=(10, 6))

        # Configurar o estilo baseado no tema
        if self.is_dark_mode:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        # Gráfico de barras
        bars = plt.bar(category_names, total_spent, color='#4CAF50')

        # Adicionar valores acima das barras
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'R${height:.2f}', ha='center', va='bottom', rotation=0)

        plt.xlabel("Categoria")
        plt.ylabel("Total Gasto (R$)")
        plt.title(f"Gastos por Categoria - {self.selected_year}")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        # Adicionar grade para facilitar leitura
        plt.grid(axis='y', linestyle='--', alpha=0.7)

        plt.show()

    def show_budget_dialog(self):
        """Mostra o diálogo de orçamento mensal"""
        dialog = BudgetDialog(self)
        dialog.exec_()

    def show_cashflow_dialog(self):
        """Mostra o diálogo de projeção de fluxo de caixa"""
        dialog = CashFlowDialog(self)
        dialog.exec_()

    def show_calendar_dialog(self):
        """Mostra o diálogo de calendário financeiro"""
        dialog = CalendarDialog(self)
        dialog.exec_()

    def show_trends_dialog(self):
        """Mostra o diálogo de análise de tendências"""
        dialog = TrendsDialog(self)
        dialog.exec_()

    def show_savings_goals(self):
        """Mostra o gerenciador de metas de economia"""
        # Primeiro mostrar lista de metas existentes
        goals = self.db_connection.execute(
            '''
            SELECT id, name, target_amount, current_amount,
                (current_amount / target_amount * 100) as progress
            FROM savings_goals
            WHERE user_id = ?
            ORDER BY deadline IS NULL, deadline, progress DESC
            ''',
            (self.user_id,)
        ).fetchall()

        # Criar diálogo
        goals_dialog = QDialog(self)
        goals_dialog.setWindowTitle("Metas de Economia")
        goals_dialog.resize(600, 400)

        # Layout
        layout = QVBoxLayout()

        # Título
        title_label = QLabel("Minhas Metas de Economia")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        # Tabela de metas
        goals_table = QTableWidget()
        goals_table.setColumnCount(5)
        goals_table.setHorizontalHeaderLabels(["Nome", "Meta (R$)", "Atual (R$)", "Progresso", "Ações"])
        goals_table.horizontalHeader().setStretchLastSection(True)
        goals_table.setEditTriggers(QTableWidget.NoEditTriggers)
        goals_table.setSelectionBehavior(QTableWidget.SelectRows)

        # Preencher tabela
        goals_table.setRowCount(len(goals))
        for i, goal in enumerate(goals):
            name_item = QTableWidgetItem(goal['name'])
            target_item = QTableWidgetItem(f"R$ {goal['target_amount']:.2f}")
            current_item = QTableWidgetItem(f"R$ {goal['current_amount']:.2f}")

            # Criar barra de progresso
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_bar = QProgressBar()
            progress_bar.setMaximum(100)
            progress_value = int(goal['progress'])
            progress_bar.setValue(progress_value)
            progress_bar.setFormat(f"{progress_value}%")
            progress_layout.addWidget(progress_bar)
            progress_layout.setContentsMargins(4, 4, 4, 4)

            # Botões de ação
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)

            edit_button = QPushButton("✏️")
            edit_button.setToolTip("Editar Meta")
            edit_button.clicked.connect(lambda _, goal_id=goal['id']: self.edit_savings_goal(goal_id))

            delete_button = QPushButton("🗑️")
            delete_button.setToolTip("Excluir Meta")
            delete_button.clicked.connect(lambda _, goal_id=goal['id']: self.delete_savings_goal(goal_id, goals_table))

            action_layout.addWidget(edit_button)
            action_layout.addWidget(delete_button)
            action_layout.setContentsMargins(2, 2, 2, 2)

            # Adicionar itens à tabela
            goals_table.setItem(i, 0, name_item)
            goals_table.setItem(i, 1, target_item)
            goals_table.setItem(i, 2, current_item)
            goals_table.setCellWidget(i, 3, progress_widget)
            goals_table.setCellWidget(i, 4, action_widget)

        layout.addWidget(goals_table)

        # Botões
        button_layout = QHBoxLayout()

        add_button = QPushButton("Nova Meta")
        add_button.clicked.connect(self.add_savings_goal)

        close_button = QPushButton("Fechar")
        close_button.clicked.connect(goals_dialog.accept)

        button_layout.addWidget(add_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        goals_dialog.setLayout(layout)

        # Aplicar tema
        if self.is_dark_mode:
            goals_dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QLabel {
                    color: #ecf0f1;
                }
                QTableWidget {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                }
                QPushButton {
                    background-color: #3498db;
                    color: #ecf0f1;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #4b6584;
                    border-radius: 5px;
                    text-align: center;
                    background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71;
                    width: 10px;
                    margin: 0.5px;
                }
            """)

        goals_dialog.exec_()

    def add_savings_goal(self):
        """Adiciona uma nova meta de economia"""
        dialog = SavingsGoalDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.show_savings_goals()  # Recarregar a lista

    def edit_savings_goal(self, goal_id):
        """Edita uma meta de economia existente"""
        dialog = SavingsGoalDialog(self, goal_id)
        if dialog.exec_() == QDialog.Accepted:
            self.show_savings_goals()  # Recarregar a lista

    def delete_savings_goal(self, goal_id, table):
        """Exclui uma meta de economia"""
        # Confirmar exclusão
        reply = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            "Tem certeza que deseja excluir esta meta de economia?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Excluir a meta
            self.db_connection.execute(
                "DELETE FROM savings_goals WHERE id = ? AND user_id = ?",
                (goal_id, self.user_id)
            )
            self.db_connection.commit()

            # Recarregar a lista
            self.show_savings_goals()

    def logout(self):
        """
        Realiza o logout do usuário
        """
        # Salvar configurações do usuário
        self.save_user_preferences()

        if self.db_connection:
            self.db_connection.close()

        self.user_id = None

        # Limpar o layout do dashboard e voltar para o layout de login
        self.clear_layout(self.main_layout)

        self.login_layout = self.create_login_layout()
        self.main_layout.addLayout(self.login_layout)

    def clear_layout(self, layout):
        """
        Limpa todos os widgets de um layout
        """
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self.clear_layout(child.layout())


if __name__ == '__main__':
    import sys
    import random

    app = QApplication(sys.argv)

    # Verificar se existe o ícone, caso contrário, criar um padrão
    if not os.path.exists('finance_icon.png'):
        # Criar um ícone temporário básico
        from PyQt5.QtGui import QPainter, QPixmap

        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))  # Transparente

        painter = QPainter(pixmap)
        painter.setPen(QColor(0, 128, 0))  # Verde
        painter.setBrush(QColor(0, 128, 0, 100))  # Verde com transparência

        # Desenhar símbolo de cifrão
        painter.drawEllipse(5, 5, 54, 54)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 40, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "$")

        painter.end()

        # Salvar o ícone
        pixmap.save('finance_icon.png')

    # Iniciar a janela principal
    main_window = MainWindow()

    # Iniciar minimizado
    if hasattr(main_window, 'start_minimized') and main_window.start_minimized:
        main_window.hide()
        main_window.tray_icon.showMessage(
            "Gestão Financeira",
            "Aplicativo iniciado e minimizado na bandeja do sistema.",
            QSystemTrayIcon.Information,
            2000
        )
    else:
        main_window.show()

    sys.exit(app.exec_())

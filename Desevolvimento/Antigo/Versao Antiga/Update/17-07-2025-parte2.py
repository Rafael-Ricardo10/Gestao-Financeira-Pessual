import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QMessageBox, QComboBox, QDateEdit, QDialog, QTabWidget, QGroupBox, QRadioButton, QTextEdit, QFileDialog, QScrollArea, QFrame, QSplitter
from PyQt5.QtCore import Qt, QDate, QSize, QRect, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QTextCharFormat, QTextCursor
import sqlite3
from datetime import datetime
import os
import matplotlib.pyplot as plt
import requests
import json
import socket
import subprocess
import threading
import re

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
            # Configurar proxy SOCKS para Tor
            import socks
            import socket
            socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
            socket.socket = socks.socksocket

            return f"http://{config.get('tor_address', '')}:{config.get('tor_port', '')}"

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
                    callback(error_msg)
                    return

                # Processar cada linha da resposta
                for line in response.iter_lines():
                    if line:
                        json_response = json.loads(line)
                        chunk = json_response.get("response", "")
                        full_response += chunk
                        # Chamar o callback com o texto acumulado até agora
                        callback(full_response)

            # Adicionar resposta completa ao histórico
            self.add_to_history("assistant", full_response)

            # Verificar se a resposta sugere criar/renomear/excluir categorias
            if db_connection and user_id:
                action, details = self.analyze_for_category_action(original_prompt, full_response, "", db_connection, user_id)
                if action:
                    # Prepara resposta com sugestão de ação
                    final_response = self._handle_category_action(action, details, full_response, db_connection, user_id)
                    # Atualizar a resposta final no callback
                    callback(final_response)

        except Exception as e:
            import traceback
            error_msg = f"Erro ao processar a consulta: {str(e)}\n{traceback.format_exc()}"
            callback(error_msg)

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
        if is_user:
            self.setStyleSheet("""
                ChatMessage {
                    background-color: #e1f5fe;
                    border-radius: 10px;
                    margin: 5px;
                    padding: 5px;
                }
                QTextEdit {
                    background-color: transparent;
                    color: #01579b;  /* Azul escuro para garantir visibilidade */
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
                    color: #33691e;  /* Verde escuro para garantir visibilidade */
                    border: none;
                    font-size: 14px;
                }
            """)

        # Adicionar widgets ao layout
        self.layout.addWidget(self.message)
        self.setLayout(self.layout)

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
        if is_user:
            self.setStyleSheet("""
                ChatMessage {
                    background-color: #e1f5fe;
                    border-radius: 10px;
                    margin: 5px;
                    padding: 5px;
                }
                QTextEdit {
                    background-color: transparent;
                    color: #01579b;  /* Azul escuro para garantir visibilidade */
                    border: none;
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
                    color: #33691e;  /* Verde escuro para garantir visibilidade */
                    border: none;
                }
            """)

        # Adicionar widgets ao layout
        self.layout.addWidget(self.message)
        self.setLayout(self.layout)


class ImprovedScrollArea(QScrollArea):
    """
    ScrollArea melhorada com autoscroll e estilos mais modernos
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Aplicar estilo mais agradável para a barra de rolagem
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

        # Estilo global para o diálogo
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
                color: #ffffff;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QWidget {
                color: #333333;
            }
        """)

        # Layout principal
        main_layout = QVBoxLayout()

        # Splitter para dividir o chat e os controles de entrada
        self.splitter = QSplitter(Qt.Vertical)

        # Container para a área de chat
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: white; color: #333333;")
        chat_container_layout = QVBoxLayout(self.chat_container)

        # Área de rolagem melhorada para as mensagens
        self.chat_scroll = ImprovedScrollArea()
        self.chat_content = QWidget()
        self.chat_content.setStyleSheet("background-color: white; color: #333333;")
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setSpacing(10)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.addStretch()  # Força as mensagens para o topo

        self.chat_scroll.setWidget(self.chat_content)
        chat_container_layout.addWidget(self.chat_scroll)

        # Área de entrada e botões
        self.input_container = QWidget()
        self.input_container.setStyleSheet("background-color: #f0f0f0; color: #333333;")
        input_layout = QVBoxLayout(self.input_container)

        # Grupo para período de análise
        period_group = QGroupBox("Período para análise:")
        period_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 4px;
                margin-top: 1ex;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #333333;
            }
        """)
        period_layout = QHBoxLayout()

        # Seleção de ano
        year_label = QLabel("Ano:")
        year_label.setStyleSheet("color: #333333;")
        self.year_combo = QComboBox()
        self.year_combo.setStyleSheet("background-color: white; color: #333333;")
        self.populate_years()

        # Seleção de mês
        month_label = QLabel("Mês:")
        month_label.setStyleSheet("color: #333333;")
        self.month_combo = QComboBox()
        self.month_combo.setStyleSheet("background-color: white; color: #333333;")
        self.month_combo.addItems(["Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio",
                                  "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])

        period_layout.addWidget(year_label)
        period_layout.addWidget(self.year_combo)
        period_layout.addWidget(month_label)
        period_layout.addWidget(self.month_combo)
        period_group.setLayout(period_layout)

        # Grupo de ações rápidas
        quick_actions_group = QGroupBox("Ações Rápidas:")
        quick_actions_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 4px;
                margin-top: 1ex;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #333333;
            }
        """)
        quick_actions_layout = QVBoxLayout()

        button_style = """
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
        """

        # Linha 1 - Análises gerais
        quick_row1 = QHBoxLayout()
        self.analyze_spending_button = QPushButton("Analisar Gastos")
        self.analyze_spending_button.setStyleSheet(button_style)
        self.analyze_spending_button.clicked.connect(self.analyze_spending)

        self.budget_suggestion_button = QPushButton("Sugerir Orçamento")
        self.budget_suggestion_button.setStyleSheet(button_style)
        self.budget_suggestion_button.clicked.connect(self.suggest_budget)

        self.saving_tips_button = QPushButton("Dicas de Economia")
        self.saving_tips_button.setStyleSheet(button_style)
        self.saving_tips_button.clicked.connect(self.get_saving_tips)

        quick_row1.addWidget(self.analyze_spending_button)
        quick_row1.addWidget(self.budget_suggestion_button)
        quick_row1.addWidget(self.saving_tips_button)

        # Linha 2 - Análises específicas
        quick_row2 = QHBoxLayout()
        self.category_analysis_button = QPushButton("Análise por Categoria")
        self.category_analysis_button.setStyleSheet(button_style)
        self.category_analysis_button.clicked.connect(self.analyze_categories)

        self.trends_button = QPushButton("Tendências de Gastos")
        self.trends_button.setStyleSheet(button_style)
        self.trends_button.clicked.connect(self.analyze_trends)

        self.investment_button = QPushButton("Sugestões de Investimento")
        self.investment_button.setStyleSheet(button_style)
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
        self.query_input.setStyleSheet("background-color: white; color: #333333; padding: 10px;")
        self.query_input.setPlaceholderText("Digite sua pergunta ou comando aqui...")
        self.query_input.returnPressed.connect(self.send_query)

        self.send_button = QPushButton("Enviar")
        self.send_button.setIcon(QIcon.fromTheme("document-send"))
        self.send_button.clicked.connect(self.send_query)
        self.send_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")

        self.clear_button = QPushButton("Limpar Chat")
        self.clear_button.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
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

            # Adicionar informações sobre categorias existentes
            all_categories = self.parent().db_connection.execute(
                "SELECT name FROM categories WHERE user_id = ? ORDER BY name",
                (self.parent().user_id,)
            ).fetchall()

            context += "\nCategorias disponíveis:\n"
            cat_names = [cat['name'] for cat in all_categories]
            context += ", ".join(cat_names)

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
                # Atualizar apenas a última mensagem (da IA)
                # Primeiro remover a mensagem atual da IA
                if self.chat_layout.count() > 1:  # Pelo menos a mensagem do usuário + stretch
                    # Procurar a última mensagem da IA
                    for i in range(self.chat_layout.count() - 1, -1, -1):
                        item = self.chat_layout.itemAt(i)
                        if item.widget() and isinstance(item.widget(), ChatMessage) and not item.widget().is_user:
                            # Remover a mensagem antiga
                            old_widget = item.widget()
                            self.chat_layout.removeWidget(old_widget)
                            old_widget.deleteLater()
                            break

                # Adicionar a mensagem atualizada
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

            # Mostrar mensagem de processamento
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


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestão Financeira Pessoal")
        self.setGeometry(100, 100, 800, 600)

        # Aplicar estilo global para garantir visibilidade do texto
        self.setStyleSheet("""
            QWidget {
                color: #333333;  /* Cor de texto escura para todo o aplicativo */
                background-color: #f5f5f5;
            }
            QLineEdit, QTextEdit, QComboBox {
                color: #000000;  /* Preto para campos de entrada */
                background-color: #ffffff;
            }
            QLabel {
                color: #333333;  /* Cor escura para labels */
            }
        """)

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

        # Adicionar estilo aos widgets de login
        self.username_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.password_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.username_input.setStyleSheet("padding: 8px; border: 1px solid #ccc; border-radius: 4px;")
        self.password_input.setStyleSheet("padding: 8px; border: 1px solid #ccc; border-radius: 4px;")

        # Estilizar botões
        button_style = """
            QPushButton {
                padding: 8px 15px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """
        self.login_button.setStyleSheet(button_style)
        self.register_button.setStyleSheet(button_style.replace("#4CAF50", "#2196F3").replace("#45a049", "#1976D2").replace("#3d8b40", "#1565C0"))
        self.save_login_button.setStyleSheet(button_style.replace("#4CAF50", "#FF9800").replace("#45a049", "#FB8C00").replace("#3d8b40", "#F57C00"))

        # Criar container para melhor organização
        login_container = QWidget()
        login_container.setStyleSheet("""
            background-color: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            max-width: 400px;
        """)
        container_layout = QVBoxLayout(login_container)

        # Título
        title_label = QLabel("Sistema de Gestão Financeira")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 20px; color: #333;")
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
                         name TEXT UNIQUE NOT NULL,
                         FOREIGN KEY (user_id) REFERENCES users (id))''')

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
        # Estilizar as tabelas para melhor aparência
        table_style = """
            QTableWidget {
                background-color: white;
                alternate-background-color: #f9f9f9;
                selection-background-color: #e3f2fd;
                gridline-color: #ddd;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid #eee;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #ccc;
                font-weight: bold;
            }
        """
        self.transactions_table.setStyleSheet(table_style)
        self.notes_table.setStyleSheet(table_style)
        self.categories_table.setStyleSheet(table_style)

        # Ajustar comportamento das tabelas
        for table in [self.transactions_table, self.notes_table, self.categories_table]:
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
            table.setShowGrid(True)

        # Estilizar botões
        button_style = """
            QPushButton {
                padding: 6px 12px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """

        # Aplicar estilos aos botões
        for button in [self.add_transaction_button, self.add_note_button, self.add_category_button]:
            button.setStyleSheet(button_style)

        edit_button_style = button_style.replace("#4CAF50", "#2196F3").replace("#45a049", "#1976D2").replace("#3d8b40", "#1565C0")
        for button in [self.edit_transaction_button, self.edit_note_button, self.edit_category_button]:
            button.setStyleSheet(edit_button_style)

        delete_button_style = button_style.replace("#4CAF50", "#F44336").replace("#45a049", "#E53935").replace("#3d8b40", "#D32F2F")
        for button in [self.delete_transaction_button, self.delete_note_button, self.delete_category_button]:
            button.setStyleSheet(delete_button_style)

        # Criar o layout do dashboard
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
            color: #2e7d32;
            background-color: #e8f5e9;
            padding: 10px;
            border-radius: 4px;
        """)

        top_layout.addWidget(self.balance_label)

        # Estilizar o campo de pesquisa
        self.search_input.setStyleSheet("""
            padding: 8px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 14px;
        """)

        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_icon_label = QLabel("🔍")
        search_layout.addWidget(search_icon_label)
        search_layout.addWidget(self.search_input)

        top_layout.addWidget(search_container)
        dashboard_layout.addLayout(top_layout)

        # Adicionar botões de ano com estilo
        year_group = QGroupBox("Filtrar por Ano:")
        year_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        dashboard_layout.addLayout(self.year_buttons_layout)

        # Transações
        transactions_group = QGroupBox("Transações")
        transactions_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

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
        categories_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

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
        notes_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

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
        tools_layout = QHBoxLayout()

        # Estilizar botões de ferramentas
        tools_button_style = """
            QPushButton {
                padding: 8px 15px;
                background-color: #673AB7;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E35B1;
            }
            QPushButton:pressed {
                background-color: #512DA8;
            }
        """

        # Botões para relatórios e gráficos
        report_button = QPushButton("📊 Gerar Relatório")
        report_button.setStyleSheet(tools_button_style)
        report_button.clicked.connect(self.generate_category_report)

        graph_button = QPushButton("📈 Gerar Gráfico")
        graph_button.setStyleSheet(tools_button_style)
        graph_button.clicked.connect(self.generate_category_graph)

        export_report_button = QPushButton("📋 Exportar Relatório")
        export_report_button.setStyleSheet(tools_button_style)
        export_report_button.clicked.connect(self.export_report)

        # Botões de IA
        self.ai_config_button.setStyleSheet(tools_button_style.replace("#673AB7", "#00BCD4").replace("#5E35B1", "#00ACC1").replace("#512DA8", "#0097A7"))
        self.ai_query_button.setStyleSheet(tools_button_style.replace("#673AB7", "#00BCD4").replace("#5E35B1", "#00ACC1").replace("#512DA8", "#0097A7"))

        tools_layout.addWidget(report_button)
        tools_layout.addWidget(graph_button)
        tools_layout.addWidget(export_report_button)
        tools_layout.addWidget(self.ai_config_button)
        tools_layout.addWidget(self.ai_query_button)

        dashboard_layout.addLayout(tools_layout)

        # Botão de logout
        self.logout_button.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                background-color: #F44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #E53935;
            }
            QPushButton:pressed {
                background-color: #D32F2F;
            }
        """)

        dashboard_layout.addWidget(self.logout_button, 0, Qt.AlignRight)

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
        format_dialog.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel {
                font-weight: bold;
                color: #333333;
            }
            QPushButton {
                padding: 8px 15px;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout()

        # Título e instruções
        title_label = QLabel("Escolha o formato de exportação:")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Botões de formato
        buttons_layout = QHBoxLayout()

        txt_button = QPushButton("Texto (.txt)")
        txt_button.setStyleSheet("background-color: #4CAF50;")
        txt_button.clicked.connect(lambda: format_dialog.done(1))  # 1 para TXT

        csv_button = QPushButton("Excel (.csv)")
        csv_button.setStyleSheet("background-color: #2196F3;")
        csv_button.clicked.connect(lambda: format_dialog.done(2))  # 2 para CSV

        cancel_button = QPushButton("Cancelar")
        cancel_button.setStyleSheet("background-color: #f44336;")
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
                export_txt_report(file_path, transactions, self.selected_year, self.user_id, self.db_connection)
            else:  # CSV
                export_csv_report(file_path, transactions, self.selected_year, self.user_id, self.db_connection)

            QMessageBox.information(self, "Sucesso", f"Relatório exportado com sucesso!\nArquivo: {file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível exportar o relatório.\nErro: {str(e)}")

    def export_txt_report(file_path, transactions, selected_year, user_id, db_connection):
        """
        Exporta o relatório em formato de texto
        """
        # Montar o conteúdo do relatório
        report_lines = []
        report_lines.append(f"RELATÓRIO DE TRANSAÇÕES - Ano: {selected_year}")
        report_lines.append("=" * 50)
        report_lines.append("ID | Descrição | Valor | Tipo | Data | Categoria")
        report_lines.append("-" * 50)

        for t in transactions:
            line = f"{t['id']} | {t['description']} | R$ {t['amount']:.2f} | {t['transaction_type']} | {t['date']} | {t['category_name']}"
            report_lines.append(line)

        report_lines.append("=" * 50)
        report_lines.append("RESUMO POR CATEGORIA")

        # Consultar o resumo de gastos por categoria para o ano selecionado
        categories = db_connection.execute(
            """
            SELECT c.name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
            GROUP BY c.name
            ORDER BY total_spent DESC
            """,
            (user_id, str(selected_year))
        ).fetchall()

        for cat in categories:
            report_lines.append(f"{cat[0]}: R$ {cat[1]:.2f}")

        report_lines.append("=" * 50)

        # Informações de saldo geral
        transactions_all = db_connection.execute(
            'SELECT * FROM transactions WHERE user_id = ?', (user_id,)
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

    def export_csv_report(file_path, transactions, selected_year, user_id, db_connection):
        """
        Exporta o relatório em formato CSV para Excel
        """
        import csv

        # Abrir arquivo CSV para escrita
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as csv_file:
            # Criar escritor CSV
            csv_writer = csv.writer(csv_file, delimiter=';')  # Usar ponto e vírgula como delimitador para melhor compatibilidade com Excel brasileiro

            # Escrever cabeçalho do relatório
            csv_writer.writerow([f"RELATÓRIO DE TRANSAÇÕES - Ano: {selected_year}"])
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
            categories = db_connection.execute(
                """
                SELECT c.name, SUM(t.amount) AS total_spent
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND strftime('%Y', t.date) = ?
                GROUP BY c.name
                ORDER BY total_spent DESC
                """,
                (user_id, str(selected_year))
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
            transactions_all = db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?', (user_id,)
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

        # Estilo para botões de ano
        button_style = """
            QPushButton {
                padding: 5px 10px;
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin: 2px;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """

        # Adicionar botão para cada ano
        for year in years:
            year_button = QPushButton(year['year'])
            year_button.setCheckable(True)
            year_button.setChecked(year['year'] == str(self.selected_year))
            year_button.toggled.connect(lambda checked, y=year['year']: self.toggle_year(y, checked))
            year_button.setStyleSheet(button_style)
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
        report_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #f9f9f9;
                selection-background-color: #e3f2fd;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #ccc;
                font-weight: bold;
            }
        """)

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
        close_button.setStyleSheet("""
            QPushButton {
                padding: 8px 15px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        report_layout.addWidget(close_button, 0, Qt.AlignCenter)

        report_dialog.setLayout(report_layout)
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

    def logout(self):
        """
        Realiza o logout do usuário
        """
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


class AddTransactionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Transação")
        self.setMinimumWidth(400)

        # Estilizar o diálogo
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
        self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.add_button.clicked.connect(self.add_transaction)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
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

        # Estilizar o diálogo
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
        self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.save_button.clicked.connect(self.save_transaction)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
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

        # Estilizar o diálogo
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

        # Widgets
        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()  # Usar QTextEdit para notas mais longas
        self.note_input.setMinimumHeight(150)
        self.note_input.setPlaceholderText("Digite sua nota aqui...")

        self.add_button = QPushButton("Adicionar")
        self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.add_button.clicked.connect(self.add_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
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

        # Estilizar o diálogo
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

        # Widgets
        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()
        self.note_input.setMinimumHeight(150)

        self.save_button = QPushButton("Salvar")
        self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.save_button.clicked.connect(self.save_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
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
        self.setMinimumWidth(350)

        # Estilizar o diálogo
        self.setStyleSheet("""
            QDialog {
                background-color: #f9f9f9;
            }
            QLabel {
                font-weight: bold;
                margin-top: 5px;
            }
            QLineEdit {
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

        # Widgets
        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()
        self.category_name_input.setPlaceholderText("Digite o nome da categoria")

        self.add_button = QPushButton("Adicionar")
        self.add_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.add_button.clicked.connect(self.add_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def add_category(self):
        """
        Adiciona uma nova categoria ao banco de dados
        """
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(self, "Erro", "O nome da categoria não pode estar vazio.")
            return

        try:
            self.parent().db_connection.execute(
                'INSERT INTO categories (user_id, name) VALUES (?, ?)',
                (self.parent().user_id, category_name)
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
        self.setMinimumWidth(350)
        self.category_id = category_id

        # Estilizar o diálogo
        self.setStyleSheet("""
            QDialog {
                background-color: #f9f9f9;
            }
            QLabel {
                font-weight: bold;
                margin-top: 5px;
            }
            QLineEdit {
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

        # Widgets
        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()

        self.save_button = QPushButton("Salvar")
        self.save_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.save_button.clicked.connect(self.save_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")
        self.cancel_button.clicked.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        # Carregar dados da categoria
        self.load_category_data()

    def load_category_data(self):
        """
        Carrega dados da categoria do banco de dados para o formulário
        """
        category = self.parent().db_connection.execute(
            'SELECT * FROM categories WHERE id = ?',
            (self.category_id,)
        ).fetchone()

        self.category_name_input.setText(category['name'])

    def save_category(self):
        """
        Salva as alterações na categoria
        """
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(self, "Erro", "O nome da categoria não pode estar vazio.")
            return

        try:
            self.parent().db_connection.execute(
                'UPDATE categories SET name = ? WHERE id = ?',
                (category_name, self.category_id)
            )
            self.parent().db_connection.commit()

            QMessageBox.information(self, "Sucesso", "Categoria atualizada com sucesso!")
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Erro", f"A categoria '{category_name}' já existe.")


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Definir estilo global
    app.setStyle("Fusion")

    # Iniciar a janela principal
    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())

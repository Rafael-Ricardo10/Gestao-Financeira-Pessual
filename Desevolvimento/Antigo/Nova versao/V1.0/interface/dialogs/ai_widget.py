"""
Widget do Assistente de IA Financeiro
"""
import json
import re
import sys
from datetime import datetime, timedelta

import requests

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QMessageBox, QDialog,
    QApplication
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QShortcut

from interface.dialogs.ai_dialogs import ApiConfigDialog
from modulos.finance_utils import FinanceDataUtility


class ChatMessage:
    """Representa uma mensagem no chat"""

    def __init__(self, text, is_user=True):
        self.text = text
        self.is_user = is_user
        self.timestamp = datetime.now()

    def formatted_html(self, dark_mode=False):
        """Retorna a mensagem formatada em HTML"""
        timestamp = self.timestamp.strftime("%H:%M:%S")

        if dark_mode:
            user_style = (
                "background-color: #2c3e50; color: #ecf0f1; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-left: 20%;"
            )
            ai_style = (
                "background-color: #34495e; color: #ecf0f1; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-right: 20%;"
            )
            time_style = (
                "color: #7f8c8d; font-size: 10px; "
                "text-align: right; margin-top: 2px;"
            )
        else:
            user_style = (
                "background-color: #e3f2fd; color: #0d47a1; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-left: 20%;"
            )
            ai_style = (
                "background-color: #f1f8e9; color: #33691e; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-right: 20%;"
            )
            time_style = (
                "color: #757575; font-size: 10px; "
                "text-align: right; margin-top: 2px;"
            )

        style = user_style if self.is_user else ai_style
        align = "right" if self.is_user else "left"
        name = "Você" if self.is_user else "Assistente IA"

        return f"""
        <div style="text-align: {align};">
            <div style="{style}">
                <div><b>{name}</b></div>
                <div style="white-space: pre-wrap;">{self.text}</div>
                <div style="{time_style}">{timestamp}</div>
            </div>
        </div>
        """


class AIAssistantThread(QThread):
    """Thread para processar requisições à API de IA"""

    update_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, config, model, prompt, parent=None):
        super().__init__(parent)
        self.config = config
        self.model = model
        self.prompt = prompt
        self.running = True

    def run(self):
        """Executa a consulta à API"""
        try:
            if self.config.get('type') == 'tor':
                base_url = (
                    f"http://{self.config.get('onion')}:"
                    f"{self.config.get('onion_port')}"
                )
                use_tor = True
            else:
                base_url = (
                    f"http://{self.config.get('host')}:"
                    f"{self.config.get('port')}"
                )
                use_tor = False

            api_key = self.config.get('api_key', '')

            session = requests.Session()
            if use_tor:
                session.proxies = {
                    'http': 'socks5h://localhost:9050',
                    'https': 'socks5h://localhost:9050'
                }

            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'

            payload = {
                "model": self.model,
                "prompt": self.prompt,
                "stream": True
            }

            response = session.post(
                f"{base_url}/api/generate",
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            response.raise_for_status()

            full_response = ""
            for line in response.iter_lines():
                if not self.running:
                    break
                if line:
                    try:
                        line_data = json.loads(line.decode('utf-8'))
                        if 'response' in line_data:
                            chunk = line_data.get('response', '')
                        elif (
                            'choices' in line_data and
                            len(line_data['choices']) > 0
                        ):
                            delta = line_data['choices'][0].get('delta', {})
                            chunk = delta.get('content', '')
                        else:
                            chunk = line_data.get('text', '')

                        if chunk:
                            full_response += chunk
                            self.update_signal.emit(full_response)
                    except Exception:
                        continue

            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit()

    def stop(self):
        """Para a thread"""
        self.running = False


class AIAssistantWidget(QWidget):
    """Widget principal do assistente de IA"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )
        self.messages = []
        self.api_thread = None

        self.load_config()
        self.init_ui()

        welcome = (
            "Olá! Sou seu assistente financeiro. Como posso ajudar?\n\n"
            "Você pode me perguntar sobre:\n"
            "• Análise dos seus gastos\n"
            "• Sugestões para economizar\n"
            "• Categorização de transações\n"
            "• Previsões financeiras\n"
            "• Cotações e conversão de moedas"
        )
        self.add_message(welcome, is_user=False)

    def init_ui(self):
        """Inicializa a interface"""
        layout = QVBoxLayout(self)

        # Título
        title_layout = QHBoxLayout()

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray; font-size: 18px;")

        title_label = QLabel("Assistente Financeiro IA")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        config_button = QPushButton("⚙️")
        config_button.setToolTip("Configurar API")
        config_button.setFixedSize(30, 30)
        config_button.clicked.connect(self.show_config_dialog)

        title_layout.addWidget(self.status_indicator)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(config_button)

        layout.addLayout(title_layout)

        # Área de chat
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setMinimumHeight(300)

        # Entrada
        self.input_area = QTextEdit()
        self.input_area.setPlaceholderText("Digite sua pergunta aqui...")
        self.input_area.setMaximumHeight(100)
        self.input_area.setAcceptRichText(False)

        # Botões
        self.send_button = QPushButton("Enviar")
        self.send_button.clicked.connect(self.send_message)

        self.clear_button = QPushButton("Limpar Chat")
        self.clear_button.clicked.connect(self.clear_chat)

        send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.input_area)
        send_shortcut.activated.connect(self.send_message)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)

        layout.addWidget(self.chat_area, 1)
        layout.addWidget(self.input_area, 0)
        layout.addLayout(button_layout)

        self.apply_theme()

    def apply_theme(self):
        """Aplica o tema ao widget"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QWidget { background-color: #1e272e; color: #ecf0f1; }
                QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px; padding: 8px;
                }
                QPushButton {
                    background-color: #3498db; color: #ecf0f1;
                    border: none; border-radius: 4px;
                    padding: 8px 15px; font-weight: bold;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            self.send_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.clear_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QTextEdit {
                    background-color: white; color: #333333;
                    border: 1px solid #ccc; border-radius: 4px; padding: 8px;
                }
                QPushButton {
                    background-color: #4CAF50; color: white;
                    border: none; border-radius: 4px;
                    padding: 8px 15px; font-weight: bold;
                }
                QPushButton:hover { background-color: #45a049; }
            """)
            self.send_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.clear_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def load_config(self):
        """Carrega as configurações da API"""
        self.api_config = None
        self.selected_model = None

        if not (
            hasattr(self.parent_window, 'db_connection') and
            hasattr(self.parent_window, 'user_id')
        ):
            return

        try:
            endpoint_config = self.parent_window.db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'ai_endpoint_config'""",
                (self.parent_window.user_id,)
            ).fetchone()

            if endpoint_config:
                self.api_config = json.loads(endpoint_config[0])

            selected_model = self.parent_window.db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'ai_selected_model'""",
                (self.parent_window.user_id,)
            ).fetchone()

            if selected_model:
                self.selected_model = selected_model[0]

            self.update_status_indicator()

        except Exception as e:
            print(f"Erro ao carregar config IA: {e}")

    def update_status_indicator(self):
        """Atualiza o indicador de status"""
        if self.api_config and self.selected_model:
            self.status_indicator.setStyleSheet(
                "color: green; font-size: 18px;"
            )
            self.status_indicator.setToolTip("Conectado")
        else:
            self.status_indicator.setStyleSheet(
                "color: gray; font-size: 18px;"
            )
            self.status_indicator.setToolTip("Não configurado")

    def show_config_dialog(self):
        """Mostra o diálogo de configuração"""
        dialog = ApiConfigDialog(self.parent_window)
        if dialog.exec_() == QDialog.Accepted:
            self.load_config()

    def add_message(self, text, is_user=True):
        """Adiciona uma mensagem ao chat"""
        message = ChatMessage(text, is_user)
        self.messages.append(message)
        self.update_chat_view()

    def update_chat_view(self):
        """Atualiza a visualização do chat"""
        scrollbar = self.chat_area.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        html = "".join(
            msg.formatted_html(self.is_dark_mode) for msg in self.messages
        )
        self.chat_area.setHtml(html)

        if was_at_bottom:
            QTimer.singleShot(
                0, lambda: scrollbar.setValue(scrollbar.maximum())
            )

    def send_message(self):
        """Envia a mensagem para a API"""
        text = self.input_area.toPlainText().strip()
        if not text:
            return

        if not self.api_config or not self.selected_model:
            QMessageBox.warning(
                self, "API não configurada",
                "Por favor, configure a API antes de enviar mensagens."
            )
            return

        self.add_message(text, is_user=True)
        self.input_area.clear()
        self.add_message("Gerando resposta...", is_user=False)

        context = self.build_financial_context()
        additional_context = self.analyze_time_references(text)
        finance_context = self.check_for_finance_queries(text)

        if additional_context:
            context += (
                "\n\nAnálise de dados específicos solicitados:"
                + additional_context
            )
        if finance_context:
            context += "\n\n" + finance_context

        full_prompt = f"{context}\n\nUsuário: {text}\n\nAssistente:"

        if self.api_thread:
            self.api_thread.stop()

        self.api_thread = AIAssistantThread(
            self.api_config, self.selected_model, full_prompt, self
        )
        self.api_thread.update_signal.connect(self.update_ai_response)
        self.api_thread.error_signal.connect(self.handle_api_error)
        self.api_thread.finished_signal.connect(self.api_request_finished)

        self.send_button.setEnabled(False)
        self.api_thread.start()

    def update_ai_response(self, text):
        """Atualiza a resposta da IA em tempo real"""
        self.messages[-1].text = text
        self.update_chat_view()
        scrollbar = self.chat_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def handle_api_error(self, error_message):
        """Trata erros da API"""
        self.messages[-1].text = f"Erro ao gerar resposta: {error_message}"
        self.update_chat_view()

    def api_request_finished(self):
        """Chamado quando a requisição é finalizada"""
        self.send_button.setEnabled(True)

    def clear_chat(self):
        """Limpa o histórico de chat"""
        reply = QMessageBox.question(
            self, "Limpar Chat",
            "Tem certeza que deseja limpar todo o histórico?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            welcome = self.messages[0] if self.messages else None
            self.messages = []
            if welcome:
                self.messages.append(welcome)
            self.update_chat_view()

    def analyze_time_references(self, text):
        """Analisa referências de tempo na mensagem"""
        additional_context = ""
        today = datetime.now()
        current_year = today.year
        current_month = today.month

        time_indicators = {
            'ontem': 'yesterday',
            'semana': 'week',
            'mês atual': 'month',
            'mês passado': 'last_month',
            'ano atual': 'year',
            'ano passado': 'last_year'
        }

        for indicator, period_type in time_indicators.items():
            if indicator.lower() in text.lower():
                period_data = self.get_transactions_by_period(period_type)
                if period_data:
                    additional_context += (
                        f"\nDados para {indicator}:\n"
                        f"Receitas: R$ {period_data['summary']['total_income']:.2f}\n"
                        f"Despesas: R$ {period_data['summary']['total_expense']:.2f}\n"
                        f"Saldo: R$ {period_data['summary']['net_change']:.2f}\n"
                    )

        months_map = {
            'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4,
            'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
            'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
        }

        for month_name, month_num in months_map.items():
            if month_name.lower() in text.lower():
                year = current_year
                for y in range(current_year - 5, current_year + 1):
                    if str(y) in text:
                        year = y
                        break

                month_data = self.analyze_specific_month(month_num, year)
                if month_data:
                    additional_context += (
                        f"\nDados para {month_name} de {year}:\n"
                        f"Receitas: R$ {month_data['summary']['total_income']:.2f}\n"
                        f"Despesas: R$ {month_data['summary']['total_expense']:.2f}\n"
                        f"Saldo: R$ {month_data['summary']['net_change']:.2f}\n"
                    )
                    if month_data['top_categories']:
                        additional_context += "Principais categorias:\n"
                        for cat, amount in month_data['top_categories']:
                            additional_context += f"- {cat}: R$ {amount:.2f}\n"

        return additional_context

    def get_transactions_by_period(self, period_type, start_date=None, end_date=None):
        """Obtém transações para um período específico"""
        if not (
            hasattr(self.parent_window, 'db_connection') and
            hasattr(self.parent_window, 'user_id')
        ):
            return None

        try:
            today = datetime.now()

            if period_type == 'day':
                start_date = end_date = today.strftime('%Y-%m-%d')
            elif period_type == 'yesterday':
                yesterday = today - timedelta(days=1)
                start_date = end_date = yesterday.strftime('%Y-%m-%d')
            elif period_type == 'week':
                start_of_week = today - timedelta(days=today.weekday())
                start_date = start_of_week.strftime('%Y-%m-%d')
                end_date = today.strftime('%Y-%m-%d')
            elif period_type == 'month':
                start_date = today.strftime('%Y-%m-01')
                end_date = today.strftime('%Y-%m-%d')
            elif period_type == 'last_month':
                first_current = today.replace(day=1)
                last_prev = first_current - timedelta(days=1)
                first_prev = last_prev.replace(day=1)
                start_date = first_prev.strftime('%Y-%m-%d')
                end_date = last_prev.strftime('%Y-%m-%d')
            elif period_type == 'year':
                start_date = f"{today.year}-01-01"
                end_date = today.strftime('%Y-%m-%d')
            elif period_type == 'last_year':
                start_date = f"{today.year - 1}-01-01"
                end_date = f"{today.year - 1}-12-31"

            transactions = self.parent_window.db_connection.execute(
                '''SELECT t.amount, t.description, t.transaction_type,
                          t.date, c.name as category
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ? AND t.date BETWEEN ? AND ?
                   ORDER BY t.date''',
                (self.parent_window.user_id, start_date, end_date)
            ).fetchall()

            total_income = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )
            total_expense = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'saida'
            )

            categories = {}
            for t in transactions:
                if t['transaction_type'] == 'saida':
                    cat_name = t['category'] or "Sem categoria"
                    categories[cat_name] = (
                        categories.get(cat_name, 0) + t['amount']
                    )

            top_categories = sorted(
                categories.items(), key=lambda x: x[1], reverse=True
            )[:5]

            return {
                'period': {
                    'start': start_date,
                    'end': end_date,
                    'type': period_type
                },
                'summary': {
                    'total_income': total_income,
                    'total_expense': total_expense,
                    'net_change': total_income - total_expense,
                    'transaction_count': len(transactions)
                },
                'top_categories': top_categories,
                'transactions': transactions
            }

        except Exception as e:
            print(f"Erro ao obter transações: {e}")
            return None

    def analyze_specific_month(self, month, year=None):
        """Analisa dados de um mês específico"""
        if not year:
            year = datetime.now().year

        try:
            first_day = datetime(year, month, 1)
            if month == 12:
                last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(year, month + 1, 1) - timedelta(days=1)

            return self.get_transactions_by_period(
                'custom',
                first_day.strftime('%Y-%m-%d'),
                last_day.strftime('%Y-%m-%d')
            )
        except Exception as e:
            print(f"Erro ao analisar mês: {e}")
            return None

    def check_for_finance_queries(self, text):
        """Verifica se a mensagem contém consultas financeiras"""
        additional_context = ""

        currency_patterns = [
            r'(?:converter|converta|quanto vale|qual o valor de) '
            r'(\d+(?:[\.,]\d+)?) ([A-Za-z]{3}) (?:para|em) ([A-Za-z]{3})',
            r'(\d+(?:[\.,]\d+)?) ([A-Za-z]{3}) (?:em|para|vale quantos) ([A-Za-z]{3})',
        ]

        for pattern in currency_patterns:
            matches = re.findall(pattern, text.lower())
            if matches:
                try:
                    amount = float(matches[0][0].replace(',', '.'))
                    from_cur = matches[0][1].upper()
                    to_cur = matches[0][2].upper()

                    conversion = FinanceDataUtility.convert_currency(
                        amount, from_cur, to_cur
                    )
                    if conversion.get('success'):
                        additional_context += (
                            f"\nConversão: {amount:.2f} {from_cur} = "
                            f"{conversion['converted_amount']:.2f} {to_cur}\n"
                            f"Taxa: 1 {from_cur} = "
                            f"{conversion['exchange_rate']:.4f} {to_cur}\n"
                        )
                except Exception:
                    pass

        market_keywords = [
            'mercado', 'ibovespa', 'nasdaq', 'bolsa', 'índice'
        ]
        if any(kw in text.lower() for kw in market_keywords):
            market_data = FinanceDataUtility.get_market_summary()
            if market_data.get('success'):
                additional_context += "\nResumo do mercado:\n"
                for index in market_data['indices']:
                    direction = "▲" if index['change_percent'] > 0 else "▼"
                    additional_context += (
                        f"{index['name']}: {index['current_price']:.2f} "
                        f"{direction} {abs(index['change_percent']):.2f}%\n"
                    )

        return additional_context

    def build_financial_context(self):
        """Constrói contexto financeiro personalizado"""
        context = "Você é um assistente financeiro inteligente. "

        if not (
            hasattr(self.parent_window, 'db_connection') and
            hasattr(self.parent_window, 'user_id')
        ):
            return context

        try:
            transactions = self.parent_window.db_connection.execute(
                'SELECT * FROM transactions WHERE user_id = ?',
                (self.parent_window.user_id,)
            ).fetchall()

            entries_total = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )
            exits_total = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'saida'
            )
            balance = entries_total - exits_total

            context += f"O usuário tem um saldo de R$ {balance:.2f}. "

            three_months_ago = (
                datetime.now() - timedelta(days=90)
            ).strftime('%Y-%m-%d')

            category_expenses = self.parent_window.db_connection.execute(
                '''SELECT c.name, SUM(t.amount) as total
                   FROM transactions t
                   JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ? AND t.transaction_type = 'saida'
                   AND t.date >= ?
                   GROUP BY c.name ORDER BY total DESC LIMIT 5''',
                (self.parent_window.user_id, three_months_ago)
            ).fetchall()

            if category_expenses:
                context += "Principais despesas (3 meses): "
                context += ", ".join([
                    f"{c['name']} (R$ {c['total']:.2f})"
                    for c in category_expenses
                ]) + ". "

            recent_transactions = self.parent_window.db_connection.execute(
                '''SELECT t.amount, t.description, t.transaction_type,
                          t.date, c.name as category
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   ORDER BY t.date DESC LIMIT 5''',
                (self.parent_window.user_id,)
            ).fetchall()

            if recent_transactions:
                context += "Transações recentes: "
                context += ", ".join([
                    f"{t['description']} ({t['transaction_type']}, "
                    f"R$ {t['amount']:.2f}, {t['date']})"
                    for t in recent_transactions
                ]) + ". "

        except Exception as e:
            print(f"Erro ao construir contexto: {e}")

        context += (
            "Use essas informações para fornecer conselhos personalizados. "
            "Seja conciso e prático."
        )

        return context

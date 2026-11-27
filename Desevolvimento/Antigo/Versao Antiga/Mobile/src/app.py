import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import os
import sqlite3
import threading
from datetime import datetime, timedelta
import json

# Importar módulos de ajuda
from .db_helper import DatabaseHelper
from .android_helpers import authenticate_with_biometrics, select_database_directory

class FinanceManagerApp(toga.App):
    def startup(self):
        """Inicialização do aplicativo"""
        # Configuração principal
        self.main_window = toga.MainWindow(title="Gestão Financeira")
        self.is_dark_mode = False
        self.db = None
        self.user_id = None
        self.selected_year = datetime.now().year
        self.selected_month = 0  # 0 = todos os meses

        # Criar pasta de dados
        os.makedirs('dados', exist_ok=True)

        # Inicializar tela de login
        self.show_login_screen()

        # Exibir janela principal
        self.main_window.show()

    def show_login_screen(self):
        """Mostra a tela de login"""
        # Container principal
        main_box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        # Título
        title_label = toga.Label("Gestão Financeira Pessoal", style=Pack(text_align="center", font_size=20, padding_bottom=20))

        # Campos de login
        username_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
        username_label = toga.Label("Usuário:", style=Pack(padding_bottom=5))
        self.username_input = toga.TextInput(style=Pack(padding=5, width=250))
        username_box.add(username_label)
        username_box.add(self.username_input)

        password_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
        password_label = toga.Label("Senha:", style=Pack(padding_bottom=5))
        self.password_input = toga.PasswordInput(style=Pack(padding=5, width=250))
        password_box.add(password_label)
        password_box.add(self.password_input)

        # Botões
        button_box = toga.Box(style=Pack(direction=ROW, padding_top=10))
        login_button = toga.Button("Login", on_press=self.login, style=Pack(padding=5, width=120))
        register_button = toga.Button("Registrar", on_press=self.register, style=Pack(padding=5, width=120))
        button_box.add(login_button)
        button_box.add(register_button)

        # Botões adicionais para Android
        android_box = toga.Box(style=Pack(direction=COLUMN, padding_top=20))

        biometric_button = toga.Button("🔐 Usar Biometria", on_press=self.biometric_login, style=Pack(padding=5, width=250))
        android_box.add(biometric_button)

        select_db_button = toga.Button("📁 Selecionar Pasta do Banco", on_press=self.select_db_folder, style=Pack(padding=5, width=250))
        android_box.add(select_db_button)

        # Adicionar widgets ao container principal
        main_box.add(title_label)
        main_box.add(username_box)
        main_box.add(password_box)
        main_box.add(button_box)
        main_box.add(android_box)

        # Definir como conteúdo da janela
        self.main_window.content = main_box

        # Carregar credenciais salvas
        self.load_saved_credentials()

    def load_saved_credentials(self):
        """Carrega credenciais salvas"""
        try:
            saved_login = self.retrieve_value("saved_credentials")
            if saved_login:
                credentials = json.loads(saved_login)
                self.username_input.value = credentials.get("username", "")
                self.password_input.value = credentials.get("password", "")
        except:
            pass

    def save_credentials(self, username, password):
        """Salva credenciais do usuário"""
        credentials = {
            "username": username,
            "password": password
        }
        self.store_value("saved_credentials", json.dumps(credentials))

    def biometric_login(self, widget):
        """Realiza login usando biometria"""
        if not self.username_input.value:
            self.main_window.info_dialog(
                "Informação",
                "Por favor, digite seu nome de usuário primeiro ou faça login pelo menos uma vez."
            )
            return

        def auth_callback(success):
            if success:
                # Autenticação biométrica bem-sucedida
                self.login(None, use_saved_password=True)
            else:
                self.main_window.error_dialog(
                    "Erro de Autenticação",
                    "A autenticação biométrica falhou. Por favor, tente novamente ou use senha."
                )

        # Chamar função específica para Android
        authenticate_with_biometrics(
            "Autenticação Biométrica",
            "Use sua impressão digital para entrar",
            auth_callback
        )

    def select_db_folder(self, widget):
        """Seleciona pasta do banco de dados"""
        def on_select(path):
            if path:
                self.store_value("db_folder", path)
                self.main_window.info_dialog(
                    "Pasta Selecionada",
                    f"Pasta de banco de dados definida para: {path}"
                )

        # Função específica para Android
        select_database_directory(self, on_select)

    def login(self, widget, use_saved_password=False):
        """Realiza login do usuário"""
        username = self.username_input.value
        password = self.password_input.value if not use_saved_password else self.retrieve_value("saved_password")

        if not username or not password:
            self.main_window.error_dialog("Erro", "Por favor, preencha todos os campos.")
            return

        # Exibir indicador de progresso
        self.main_window.info_dialog("Aguarde", "Conectando ao banco de dados...")

        # Iniciar login em thread separada
        threading.Thread(target=self._perform_login, args=(username, password)).start()

    def _perform_login(self, username, password):
        """Processa login em background"""
        try:
            # Obter caminho do banco
            db_path = self.get_db_path(username)

            # Inicializar helper de banco de dados
            self.db = DatabaseHelper(db_path)

            # Autenticar usuário
            user = self.db.authenticate_user(username, password)

            if user:
                # Login bem-sucedido
                self.user_id = user['id']

                # Salvar credenciais
                self.save_credentials(username, password)

                # Carregar dashboard na thread principal
                self.add_background_task(self.load_dashboard)
            else:
                self.db.close()
                self.db = None
                self.add_background_task(lambda: self.main_window.error_dialog(
                    "Erro de Login",
                    "Usuário ou senha incorretos."
                ))
        except Exception as e:
            self.add_background_task(lambda: self.main_window.error_dialog(
                "Erro",
                f"Erro ao conectar ao banco de dados: {str(e)}"
            ))

    def register(self, widget):
        """Registra novo usuário"""
        username = self.username_input.value
        password = self.password_input.value

        if not username or not password:
            self.main_window.error_dialog("Erro", "Por favor, preencha todos os campos.")
            return

        # Verificar se usuário já existe
        db_path = self.get_db_path(username)
        if os.path.exists(db_path):
            self.main_window.error_dialog("Erro", "Este nome de usuário já existe.")
            return

        # Criar banco de dados e usuário
        try:
            db = DatabaseHelper(db_path)
            db.create_user(username, password)
            db.close()

            self.main_window.info_dialog(
                "Sucesso",
                "Usuário registrado com sucesso. Agora você pode fazer login."
            )
        except Exception as e:
            self.main_window.error_dialog(
                "Erro",
                f"Erro ao registrar usuário: {str(e)}"
            )

    def get_db_path(self, username):
        """Retorna caminho do banco de dados"""
        # Verificar se há pasta personalizada
        custom_folder = self.retrieve_value("db_folder")

        if custom_folder and os.path.exists(custom_folder):
            return os.path.join(custom_folder, f'{username}.db')
        else:
            return os.path.join('dados', f'{username}.db')

    def load_dashboard(self):
        """Carrega o dashboard principal"""
        # Container principal
        main_box = toga.Box(style=Pack(direction=COLUMN))

        # Barra superior
        top_bar = toga.Box(style=Pack(direction=ROW, padding=5))

        # Título
        title_label = toga.Label(f"Gestão Financeira - {self.username_input.value}",
                                style=Pack(flex=1, font_size=16, font_weight='bold'))

        # Botão de tema
        self.theme_button = toga.Button(
            "☀️" if self.is_dark_mode else "🌙",
            on_press=self.toggle_theme,
            style=Pack(width=40)
        )

        # Botão de logout
        logout_button = toga.Button("Sair", on_press=self.logout, style=Pack(width=60))

        top_bar.add(title_label)
        top_bar.add(self.theme_button)
        top_bar.add(logout_button)

        # Filtros
        filter_box = toga.Box(style=Pack(direction=ROW, padding=5))

        # Filtro de ano
        year_label = toga.Label("Ano:", style=Pack(padding_top=7))

        # Obter anos disponíveis
        available_years = self.db.get_available_years(self.user_id)
        if not available_years:
            available_years = [str(datetime.now().year)]

        self.year_selection = toga.Selection(
            items=available_years,
            on_select=self.on_year_changed,
            style=Pack(width=100)
        )

        # Filtro de mês
        month_label = toga.Label("Mês:", style=Pack(padding_top=7, padding_left=10))
        self.month_selection = toga.Selection(
            items=[
                "Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ],
            on_select=self.on_month_changed,
            style=Pack(width=120)
        )

        # Campo de busca
        search_label = toga.Label("Buscar:", style=Pack(padding_top=7, padding_left=10))
        self.search_input = toga.TextInput(style=Pack(width=150))
        search_button = toga.Button("🔍", on_press=self.search_transactions, style=Pack(width=40))

        filter_box.add(year_label)
        filter_box.add(self.year_selection)
        filter_box.add(month_label)
        filter_box.add(self.month_selection)
        filter_box.add(search_label)
        filter_box.add(self.search_input)
        filter_box.add(search_button)

        # Informações de saldo
        self.balance_box = toga.Box(style=Pack(direction=ROW, padding=5))
        self.balance_label = toga.Label("Saldo: R$ 0.00", style=Pack(padding=5, font_weight='bold'))
        self.balance_box.add(self.balance_label)

        # Abas principais
        self.tab_view = toga.OptionContainer(style=Pack(flex=1))

        # Aba de transações
        transactions_box = toga.Box(style=Pack(direction=COLUMN))

        # Tabela de transações
        self.transactions_table = toga.Table(
            headings=["ID", "Descrição", "Valor (R$)", "Tipo", "Data", "Categoria"],
            accessors=["id", "description", "amount_fmt", "type", "date", "category"],
            data=[],
            style=Pack(flex=1),
            on_select=self.on_transaction_selected
        )

        # Botões de ação para transações
        transaction_actions = toga.Box(style=Pack(direction=ROW, padding=5))
        add_trans_button = toga.Button("+ Adicionar", on_press=self.show_add_transaction, style=Pack(flex=1))
        edit_trans_button = toga.Button("✏️ Editar", on_press=self.show_edit_transaction, style=Pack(flex=1))
        delete_trans_button = toga.Button("🗑️ Excluir", on_press=self.delete_transaction, style=Pack(flex=1))

        transaction_actions.add(add_trans_button)
        transaction_actions.add(edit_trans_button)
        transaction_actions.add(delete_trans_button)

        transactions_box.add(self.transactions_table)
        transactions_box.add(transaction_actions)

        # Aba de categorias
        categories_box = toga.Box(style=Pack(direction=COLUMN))

        # Tabela de categorias
        self.categories_table = toga.Table(
            headings=["ID", "Nome", "Tipo"],
            accessors=["id", "name", "type"],
            data=[],
            style=Pack(flex=1),
            on_select=self.on_category_selected
        )

        # Botões de ação para categorias
        category_actions = toga.Box(style=Pack(direction=ROW, padding=5))
        add_cat_button = toga.Button("+ Adicionar", on_press=self.show_add_category, style=Pack(flex=1))
        edit_cat_button = toga.Button("✏️ Editar", on_press=self.show_edit_category, style=Pack(flex=1))
        delete_cat_button = toga.Button("🗑️ Excluir", on_press=self.delete_category, style=Pack(flex=1))

        category_actions.add(add_cat_button)
        category_actions.add(edit_cat_button)
        category_actions.add(delete_cat_button)

        categories_box.add(self.categories_table)
        categories_box.add(category_actions)

        # Aba de notas
        notes_box = toga.Box(style=Pack(direction=COLUMN))

        # Lista de notas
        self.notes_list = toga.Table(
            headings=["ID", "Nota", "Data"],
            accessors=["id", "note", "date"],
            data=[],
            style=Pack(flex=1),
            on_select=self.on_note_selected
        )

        # Botões de ação para notas
        note_actions = toga.Box(style=Pack(direction=ROW, padding=5))
        add_note_button = toga.Button("+ Adicionar", on_press=self.show_add_note, style=Pack(flex=1))
        edit_note_button = toga.Button("✏️ Editar", on_press=self.show_edit_note, style=Pack(flex=1))
        delete_note_button = toga.Button("🗑️ Excluir", on_press=self.delete_note, style=Pack(flex=1))

        note_actions.add(add_note_button)
        note_actions.add(edit_note_button)
        note_actions.add(delete_note_button)

        notes_box.add(self.notes_list)
        notes_box.add(note_actions)

        # Adicionar abas ao container
        self.tab_view.add("Transações", transactions_box)
        self.tab_view.add("Categorias", categories_box)
        self.tab_view.add("Notas", notes_box)

        # Rodapé com botões de relatório
        footer_box = toga.Box(style=Pack(direction=ROW, padding=5))
        report_button = toga.Button("📊 Relatório", on_press=self.show_report, style=Pack(flex=1))
        export_button = toga.Button("📥 Exportar", on_press=self.export_data, style=Pack(flex=1))
        footer_box.add(report_button)
        footer_box.add(export_button)

        # Montar layout completo
        main_box.add(top_bar)
        main_box.add(filter_box)
        main_box.add(self.balance_box)
        main_box.add(self.tab_view)
        main_box.add(footer_box)

        # Definir como conteúdo da janela
        self.main_window.content = main_box

        # Carregar dados
        self.refresh_data()

    def toggle_theme(self, widget):
        """Alterna entre tema claro e escuro"""
        self.is_dark_mode = not self.is_dark_mode
        self.theme_button.label = "☀️" if self.is_dark_mode else "🌙"

        # Na versão Android, implementamos apenas o ícone de alternância
        # O BeeWare no Android não permite personalizar totalmente o tema

        # Salvar preferência
        self.store_value("is_dark_mode", json.dumps(self.is_dark_mode))

    def refresh_data(self):
        """Atualiza todos os dados do dashboard"""
        self.load_transactions()
        self.load_categories()
        self.load_notes()
        self.update_balance()

    def on_year_changed(self, widget):
        """Quando o ano selecionado muda"""
        if widget.value:
            self.selected_year = int(widget.value)
            self.load_transactions()
            self.update_balance()

    def on_month_changed(self, widget):
        """Quando o mês selecionado muda"""
        if widget.value:
            month_names = [
                "Todos", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
            ]
            self.selected_month = month_names.index(widget.value)
            self.load_transactions()
            self.update_balance()

    def search_transactions(self, widget):
        """Pesquisa transações"""
        self.load_transactions(search_text=self.search_input.value)

    def load_transactions(self, search_text=None):
        """Carrega transações com base nos filtros"""
        # Montar parâmetros de consulta
        params = {
            'user_id': self.user_id,
            'year': self.selected_year
        }

        # Adicionar filtro de mês se selecionado
        if self.selected_month > 0:
            params['month'] = self.selected_month

        # Adicionar termo de busca
        if search_text:
            params['search'] = search_text

        # Buscar transações
        transactions = self.db.get_transactions(**params)

        # Formatar para exibição
        formatted_transactions = []
        for t in transactions:
            formatted_transactions.append({
                'id': t['id'],
                'description': t['description'],
                'amount': t['amount'],
                'amount_fmt': f"R$ {t['amount']:.2f}",
                'type': t['transaction_type'],
                'date': t['date'],
                'category': t['category_name'] or "Sem categoria",
                'category_id': t['category_id']
            })

        # Atualizar tabela
        self.transactions_table.data = formatted_transactions

    def load_categories(self):
        """Carrega categorias do usuário"""
        categories = self.db.get_categories(self.user_id)

        # Formatar para exibição
        formatted_categories = []
        for c in categories:
            # Determinar tipo de categoria
            category_type = "Normal"
            if c['is_payment_goal'] == 1:
                category_type = "Meta de Quitação 🎯"
            elif c.get('is_savings_goal') == 1:  # Verificar se a coluna existe
                category_type = "Meta de Guardar 💰"

            formatted_categories.append({
                'id': c['id'],
                'name': c['name'],
                'type': category_type,
                'is_payment_goal': c['is_payment_goal'],
                'is_savings_goal': c.get('is_savings_goal', 0),
                'total_amount': c.get('total_amount', 0)
            })

        # Atualizar tabela
        self.categories_table.data = formatted_categories

    def load_notes(self):
        """Carrega notas do usuário"""
        notes = self.db.get_notes(self.user_id)

        # Formatar para exibição
        formatted_notes = []
        for n in notes:
            note_text = n['note']
            if len(note_text) > 50:
                note_text = note_text[:47] + "..."

            formatted_notes.append({
                'id': n['id'],
                'note': note_text,
                'full_note': n['note'],
                'date': n.get('created_at', 'N/A')
            })

        # Atualizar lista
        self.notes_list.data = formatted_notes

    def update_balance(self):
        """Atualiza informações de saldo"""
        # Obter saldo geral
        balance_info = self.db.get_balance(self.user_id, year=self.selected_year, month=self.selected_month)

        # Formatar texto de saldo
        balance_text = f"Saldo: R$ {balance_info['balance']:.2f}"

        if balance_info.get('total_income') is not None:
            balance_text += f" | Receitas: R$ {balance_info['total_income']:.2f}"

        if balance_info.get('total_expense') is not None:
            balance_text += f" | Despesas: R$ {balance_info['total_expense']:.2f}"

        # Atualizar label
        self.balance_label.text = balance_text

    def on_transaction_selected(self, widget, row=None):
        """Quando uma transação é selecionada"""
        # Implementado para eventos de clique na tabela
        pass

    def on_category_selected(self, widget, row=None):
        """Quando uma categoria é selecionada"""
        # Implementado para eventos de clique na tabela
        pass

    def on_note_selected(self, widget, row=None):
        """Quando uma nota é selecionada"""
        # Implementado para eventos de clique na tabela
        pass

    def show_add_transaction(self, widget):
        """Exibe diálogo para adicionar transação"""
        self.main_window.info_dialog(
            "Funcionalidade em Desenvolvimento",
            "Você implementará esta funcionalidade de acordo com a estrutura do BeeWare."
        )

        # Exemplo básico:
        # dialog = TransactionDialog(self, self.db, self.user_id)
        # dialog.show()

    def show_edit_transaction(self, widget):
        """Exibe diálogo para editar transação"""
        if not self.transactions_table.selection:
            self.main_window.error_dialog("Erro", "Selecione uma transação para editar.")
            return

        # Implementação básica do diálogo

    def delete_transaction(self, widget):
        """Exclui a transação selecionada"""
        if not self.transactions_table.selection:
            self.main_window.error_dialog("Erro", "Selecione uma transação para excluir.")
            return

        transaction = self.transactions_table.selection

        def confirm_handler(dialog):
            try:
                self.db.delete_transaction(transaction['id'])
                self.refresh_data()
                self.main_window.info_dialog("Sucesso", "Transação excluída com sucesso.")
            except Exception as e:
                self.main_window.error_dialog("Erro", f"Erro ao excluir: {str(e)}")

        self.main_window.confirm_dialog(
            "Confirmar Exclusão",
            "Tem certeza que deseja excluir esta transação?",
            confirm_handler
        )

    def show_add_category(self, widget):
        """Exibe diálogo para adicionar categoria"""
        # Implementação básica do diálogo

    def show_edit_category(self, widget):
        """Exibe diálogo para editar categoria"""
        if not self.categories_table.selection:
            self.main_window.error_dialog("Erro", "Selecione uma categoria para editar.")
            return

        # Implementação básica do diálogo

    def delete_category(self, widget):
        """Exclui a categoria selecionada"""
        if not self.categories_table.selection:
            self.main_window.error_dialog("Erro", "Selecione uma categoria para excluir.")
            return

        # Implementação da exclusão

    def show_add_note(self, widget):
        """Exibe diálogo para adicionar nota"""
        # Implementação básica do diálogo

    def show_edit_note(self, widget):
        """Exibe diálogo para editar nota"""
        if not self.notes_list.selection:
            self.main_window.error_dialog("Erro", "Selecione uma nota para editar.")
            return

        # Implementação básica do diálogo

    def delete_note(self, widget):
        """Exclui a nota selecionada"""
        if not self.notes_list.selection:
            self.main_window.error_dialog("Erro", "Selecione uma nota para excluir.")
            return

        # Implementação da exclusão

    def show_report(self, widget):
        """Exibe relatório de gastos por categoria"""
        # Implementação básica do relatório

    def export_data(self, widget):
        """Exporta dados para CSV"""
        # Implementação básica da exportação

    def logout(self, widget):
        """Realiza logout do usuário"""
        if self.db:
            self.db.close()
            self.db = None

        self.user_id = None
        self.show_login_screen()


def main():
    return FinanceManagerApp('financeapp', 'Gestão Financeira')

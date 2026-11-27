"""
RRFS Gestão Financeira - App Mobile Android
Kivy + KivyMD - Material Design Dark Mode
"""

import os
import sys
import threading

# Android específico
try:
    from android.permissions import request_permissions, Permission
    from android.runnable import run_on_ui_thread
    IS_ANDROID = True
except ImportError:
    IS_ANDROID = False

# Kivy config ANTES de importar kivy
from kivy.config import Config
Config.set('graphics', 'resizable', '1')
Config.set('kivy', 'keyboard_mode', 'system')
Config.set('input', 'mouse', 'mouse,disable_multitouch')

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.lang import Builder

# KivyMD
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.navigationdrawer import MDNavigationDrawer, MDNavigationDrawerMenu
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem
from kivymd.uix.list import MDList, OneLineListItem, TwoLineListItem, ThreeLineListItem
from kivymd.uix.dialog import MDDialog
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.spinner import MDSpinner
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.chip import MDChip

# Adiciona path do core compartilhado
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import APP_NOME, APP_VERSAO
from core.conexao import conexao, TipoConexao
from core.tor_manager import tor
from core.cache_local import cache_local
from core.sessao import sessao
from core.sync import sync

# ==================== KV LANGUAGE ====================
KV = '''
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp

<BotaoGrande@MDRaisedButton>:
    size_hint_x: 1
    height: dp(50)
    font_size: sp(15)
    elevation: 2

<CampoTexto@MDTextField>:
    mode: "outlined"
    size_hint_x: 1
    line_color_focus: app.theme_cls.primary_color

<CardFinanceiro@MDCard>:
    elevation: 3
    radius: [dp(12)]
    padding: dp(16)
    size_hint_y: None
    height: dp(100)
    md_bg_color: 0.11, 0.13, 0.17, 1
    line_color: 0.19, 0.21, 0.25, 1

<ItemTransacao@MDCard>:
    elevation: 1
    radius: [dp(10)]
    padding: dp(12)
    size_hint_y: None
    height: dp(72)
    md_bg_color: 0.11, 0.13, 0.17, 1
    line_color: 0.19, 0.21, 0.25, 1
'''

Builder.load_string(KV)


# ==================== TELA LOGIN ====================

class TelaLogin(MDScreen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.name    = 'login'
        self.app_ref = app_ref
        self._construir()

    def _construir(self):
        # Fundo
        layout = BoxLayout(
            orientation='vertical',
            padding=dp(24),
            spacing=dp(16)
        )
        self.add_widget(layout)

        # Logo
        layout.add_widget(BoxLayout(size_hint_y=0.08))

        logo_box = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(120)
        )

        lbl_emoji = MDLabel(
            text="💰",
            halign='center',
            font_size=sp(52),
            size_hint_y=None,
            height=dp(70)
        )
        logo_box.add_widget(lbl_emoji)

        lbl_titulo = MDLabel(
            text="RRFS Gestão Financeira",
            halign='center',
            theme_text_color="Primary",
            font_style="H6",
            size_hint_y=None,
            height=dp(32)
        )
        logo_box.add_widget(lbl_titulo)

        lbl_sub = MDLabel(
            text="Pessoal e Familiar · Seguro",
            halign='center',
            theme_text_color="Secondary",
            font_style="Caption",
            size_hint_y=None,
            height=dp(20)
        )
        logo_box.add_widget(lbl_sub)
        layout.add_widget(logo_box)

        # Status conexão
        self.lbl_conn = MDLabel(
            text="⏳ Verificando conexão...",
            halign='center',
            theme_text_color="Custom",
            text_color=(0.89, 0.7, 0.25, 1),
            font_style="Caption",
            size_hint_y=None,
            height=dp(24)
        )
        layout.add_widget(self.lbl_conn)

        # Card formulário
        card = MDCard(
            orientation='vertical',
            padding=dp(20),
            spacing=dp(12),
            elevation=4,
            radius=[dp(16)],
            md_bg_color=(0.11, 0.13, 0.17, 1),
            size_hint_y=None,
            height=dp(340)
        )

        # Abas
        abas = BoxLayout(
            size_hint_y=None,
            height=dp(44),
            spacing=dp(4)
        )
        self.btn_aba_login = MDRaisedButton(
            text="Entrar",
            on_release=lambda x: self._aba('login'),
            size_hint_x=0.5,
            elevation=0
        )
        self.btn_aba_reg = MDFlatButton(
            text="Criar Conta",
            on_release=lambda x: self._aba('registro'),
            size_hint_x=0.5
        )
        abas.add_widget(self.btn_aba_login)
        abas.add_widget(self.btn_aba_reg)
        card.add_widget(abas)

        # Alerta
        self.lbl_alerta = MDLabel(
            text="",
            halign='center',
            theme_text_color="Custom",
            text_color=(0.97, 0.32, 0.29, 1),
            font_style="Caption",
            size_hint_y=None,
            height=dp(20)
        )
        card.add_widget(self.lbl_alerta)

        # ===== CAMPOS LOGIN =====
        self.frame_login = BoxLayout(
            orientation='vertical',
            spacing=dp(10),
            size_hint_y=None,
            height=dp(200)
        )

        self.entry_user = MDTextField(
            hint_text="Usuário",
            icon_right="account",
            mode="outlined"
        )
        self.frame_login.add_widget(self.entry_user)

        self.entry_senha = MDTextField(
            hint_text="Senha",
            icon_right="lock",
            password=True,
            mode="outlined"
        )
        self.frame_login.add_widget(self.entry_senha)

        self.btn_login = MDRaisedButton(
            text="🚀 ENTRAR",
            on_release=lambda x: self._fazer_login(),
            size_hint_x=1,
            height=dp(48),
            font_size=sp(14)
        )
        self.frame_login.add_widget(self.btn_login)
        card.add_widget(self.frame_login)

        # ===== CAMPOS REGISTRO =====
        self.frame_reg = BoxLayout(
            orientation='vertical',
            spacing=dp(8),
            size_hint_y=None,
            height=dp(240)
        )
        self.frame_reg.opacity = 0

        self.entry_reg_user = MDTextField(
            hint_text="Usuário (3-50 chars)",
            icon_right="account",
            mode="outlined"
        )
        self.frame_reg.add_widget(self.entry_reg_user)

        self.entry_reg_senha = MDTextField(
            hint_text="Senha (mín. 8 chars)",
            password=True,
            icon_right="lock",
            mode="outlined"
        )
        self.frame_reg.add_widget(self.entry_reg_senha)

        self.entry_reg_confirm = MDTextField(
            hint_text="Confirmar Senha",
            password=True,
            icon_right="lock",
            mode="outlined"
        )
        self.frame_reg.add_widget(self.entry_reg_confirm)

        self.btn_reg = MDRaisedButton(
            text="✅ CRIAR CONTA",
            on_release=lambda x: self._fazer_registro(),
            size_hint_x=1,
            height=dp(48),
            md_bg_color=(0.14, 0.52, 0.21, 1)
        )
        self.frame_reg.add_widget(self.btn_reg)
        card.add_widget(self.frame_reg)

        layout.add_widget(card)

        lbl_footer = MDLabel(
            text="🔒 AES-256 · Tor · RRFS v" + APP_VERSAO,
            halign='center',
            theme_text_color="Secondary",
            font_style="Caption",
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(lbl_footer)
        layout.add_widget(BoxLayout(size_hint_y=0.05))

    def _aba(self, aba: str):
        self.lbl_alerta.text = ""
        if aba == 'login':
            self.frame_login.opacity = 1
            self.frame_login.disabled = False
            self.frame_reg.opacity   = 0
            self.frame_reg.disabled  = True
            self.btn_aba_login.elevation = 4
            self.btn_aba_reg.elevation   = 0
        else:
            self.frame_login.opacity = 0
            self.frame_login.disabled = True
            self.frame_reg.opacity   = 1
            self.frame_reg.disabled  = False
            self.btn_aba_reg.elevation   = 4
            self.btn_aba_login.elevation = 0

    def _alerta(self, msg: str, cor=(0.97,0.32,0.29,1)):
        self.lbl_alerta.text       = msg
        self.lbl_alerta.text_color = cor

    def atualizar_status_conexao(self, tipo: TipoConexao):
        msgs = {
            TipoConexao.DIRETA    : ("✅ Conexão direta",   (0.25, 0.73, 0.31, 1)),
            TipoConexao.TOR       : ("🧅 Via Tor",           (0.89, 0.70, 0.25, 1)),
            TipoConexao.OFFLINE   : ("❌ Sem conexão",       (0.97, 0.32, 0.29, 1)),
            TipoConexao.CONECTANDO: ("⏳ Conectando...",     (0.89, 0.70, 0.25, 1)),
        }
        txt, cor = msgs.get(tipo, ("—", (1,1,1,1)))
        self.lbl_conn.text       = txt
        self.lbl_conn.text_color = cor

    def _fazer_login(self):
        username = self.entry_user.text.strip()
        senha    = self.entry_senha.text

        if not username or not senha:
            self._alerta("❌ Preencha usuário e senha")
            return

        if not conexao.esta_online():
            self._alerta("❌ Sem conexão com servidor")
            return

        self.btn_login.text     = "⏳ Aguarde..."
        self.btn_login.disabled = True
        self.lbl_alerta.text    = ""

        def _login():
            ok, msg = sessao.fazer_login(username, senha)

            def _atualizar(dt):
                self.btn_login.text     = "🚀 ENTRAR"
                self.btn_login.disabled = False
                if ok:
                    if msg == "TROCAR_SENHA":
                        self._alerta("⚠️ Troque sua senha pelo app web",
                                     (0.89, 0.70, 0.25, 1))
                    else:
                        self.app_ref.ir_para_principal()
                else:
                    self._alerta(f"❌ {msg}")

            Clock.schedule_once(_atualizar, 0)

        threading.Thread(target=_login, daemon=True).start()

    def _fazer_registro(self):
        username = self.entry_reg_user.text.strip()
        senha    = self.entry_reg_senha.text
        confirm  = self.entry_reg_confirm.text

        if not username or not senha or not confirm:
            self._alerta("❌ Preencha todos os campos")
            return
        if senha != confirm:
            self._alerta("❌ Senhas não coincidem")
            return
        if len(senha) < 8:
            self._alerta("❌ Mínimo 8 caracteres")
            return

        self.btn_reg.text     = "⏳ Aguarde..."
        self.btn_reg.disabled = True

        def _reg():
            resp = conexao.post('/api/registro', {
                'username': username,
                'password': senha
            })

            def _atualizar(dt):
                self.btn_reg.text     = "✅ CRIAR CONTA"
                self.btn_reg.disabled = False
                if resp and resp.get('sucesso'):
                    self._alerta("✅ Conta criada! Faça login.",
                                 (0.25, 0.73, 0.31, 1))
                    Clock.schedule_once(lambda dt: self._aba('login'), 1.5)
                else:
                    self._alerta(f"❌ {resp.get('erro','Erro') if resp else 'Sem conexão'}")

            Clock.schedule_once(_atualizar, 0)

        threading.Thread(target=_reg, daemon=True).start()


# ==================== TELA PRINCIPAL ====================

class TelaPrincipal(MDScreen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.name    = 'principal'
        self.app_ref = app_ref
        self._construir()

    def _construir(self):
        layout = BoxLayout(orientation='vertical')
        self.add_widget(layout)

        # Topbar
        self.topbar = MDTopAppBar(
            title="RRFS Financeiro",
            elevation=4,
            md_bg_color=(0.09, 0.10, 0.14, 1)
        )
        self.topbar.right_action_items = [
            ["logout", lambda x: self.app_ref.fazer_logout()],
            ["refresh", lambda x: self._atualizar()],
        ]
        layout.add_widget(self.topbar)

        # Status conexão
        self.lbl_conn = MDLabel(
            text="⏳ Conectando...",
            halign='center',
            theme_text_color="Custom",
            text_color=(0.89, 0.70, 0.25, 1),
            font_style="Caption",
            size_hint_y=None,
            height=dp(22)
        )
        layout.add_widget(self.lbl_conn)

        # Bottom Navigation
        self.nav = MDBottomNavigation(
            panel_color=(0.09, 0.10, 0.14, 1),
            selected_color_background=(0.12, 0.44, 0.92, 0.15)
        )

        # Tabs
        tab_dash  = MDBottomNavigationItem(name='dashboard',  text='Dashboard',  icon='view-dashboard')
        tab_trans = MDBottomNavigationItem(name='transacoes', text='Transações', icon='bank-transfer')
        tab_cats  = MDBottomNavigationItem(name='categorias', text='Categorias', icon='tag-multiple')
        tab_chat  = MDBottomNavigationItem(name='chat',       text='IA Chat',    icon='robot')

        # Conteúdo de cada tab
        self._conteudo_dashboard  = ConteudoDashboard(self)
        self._conteudo_transacoes = ConteudoTransacoes(self)
        self._conteudo_categorias = ConteudoCategorias(self)
        self._conteudo_chat       = ConteudoChat(self)

        tab_dash.add_widget(self._conteudo_dashboard)
        tab_trans.add_widget(self._conteudo_transacoes)
        tab_cats.add_widget(self._conteudo_categorias)
        tab_chat.add_widget(self._conteudo_chat)

        self.nav.add_widget(tab_dash)
        self.nav.add_widget(tab_trans)
        self.nav.add_widget(tab_cats)
        self.nav.add_widget(tab_chat)

        layout.add_widget(self.nav)

    def carregar_dados(self):
        """Carrega todos os dados ao entrar"""
        self._conteudo_dashboard.carregar()
        self._conteudo_transacoes.carregar()
        self._conteudo_categorias.carregar()

    def _atualizar(self):
        """Força atualização de dados"""
        self._conteudo_dashboard.carregar(forcar=True)
        self._conteudo_transacoes.carregar(forcar=True)
        self._conteudo_categorias.carregar(forcar=True)
        Snackbar(text="🔄 Dados atualizados").open()

    def atualizar_status_conexao(self, tipo: TipoConexao):
        msgs = {
            TipoConexao.DIRETA    : ("✅ Direto",   (0.25, 0.73, 0.31, 1)),
            TipoConexao.TOR       : ("🧅 Via Tor",  (0.89, 0.70, 0.25, 1)),
            TipoConexao.OFFLINE   : ("❌ Offline",  (0.97, 0.32, 0.29, 1)),
            TipoConexao.CONECTANDO: ("⏳...",        (0.89, 0.70, 0.25, 1)),
        }
        txt, cor = msgs.get(tipo, ("—", (1,1,1,1)))
        self.lbl_conn.text       = txt
        self.lbl_conn.text_color = cor


# ==================== CONTEÚDO DASHBOARD ====================

class ConteudoDashboard(BoxLayout):
    def __init__(self, tela_ref, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.tela_ref = tela_ref
        self._construir()

    def _construir(self):
        scroll = ScrollView()
        self.layout_inner = BoxLayout(
            orientation='vertical',
            padding=dp(12),
            spacing=dp(12),
            size_hint_y=None
        )
        self.layout_inner.bind(
            minimum_height=self.layout_inner.setter('height')
        )
        scroll.add_widget(self.layout_inner)
        self.add_widget(scroll)
        self._criar_cards_placeholder()

    def _criar_cards_placeholder(self):
        self.layout_inner.clear_widgets()

        # Cards de saldo
        grid_cards = GridLayout(
            cols=2, spacing=dp(8),
            size_hint_y=None, height=dp(220)
        )

        dados_cards = [
            ("💰 Saldo", "R$ 0,00", (0.12, 0.44, 0.92, 1)),
            ("📈 Entradas", "R$ 0,00", (0.14, 0.52, 0.21, 1)),
            ("📉 Saídas", "R$ 0,00", (0.85, 0.21, 0.20, 1)),
            ("📋 Transações", "0", (0.89, 0.70, 0.25, 1)),
        ]

        self.cards_refs = {}
        for titulo, valor, cor in dados_cards:
            card = MDCard(
                orientation='vertical',
                elevation=3,
                radius=[dp(12)],
                padding=dp(14),
                md_bg_color=(0.11, 0.13, 0.17, 1),
                line_color=cor
            )
            lbl_t = MDLabel(
                text=titulo,
                font_style="Caption",
                theme_text_color="Secondary",
                halign='left'
            )
            lbl_v = MDLabel(
                text=valor,
                font_style="H6",
                theme_text_color="Custom",
                text_color=cor,
                halign='left',
                bold=True
            )
            card.add_widget(lbl_t)
            card.add_widget(lbl_v)
            grid_cards.add_widget(card)
            self.cards_refs[titulo] = lbl_v

        self.layout_inner.add_widget(grid_cards)

        # Título últimas
        lbl_ult = MDLabel(
            text="📋 Últimas Transações",
            font_style="Subtitle1",
            theme_text_color="Primary",
            size_hint_y=None,
            height=dp(36),
            bold=True
        )
        self.layout_inner.add_widget(lbl_ult)

        # Lista transações
        self.lista_trans = MDList()
        self.layout_inner.add_widget(self.lista_trans)

    def carregar(self, forcar: bool = False):
        def _buscar():
            saldo = sync.obter_saldo(forcar)
            trans = sync.obter_transacoes(forcar)
            cats  = sync.obter_categorias(forcar)
            cat_map = {c['id']: c['nome'] for c in cats}

            Clock.schedule_once(
                lambda dt: self._atualizar_ui(saldo, trans[:8], cat_map), 0
            )

        threading.Thread(target=_buscar, daemon=True).start()

    def _atualizar_ui(self, saldo: dict, trans: list, cat_map: dict):
        def fmt(v):
            return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')

        # Atualiza cards
        refs = self.cards_refs
        if "💰 Saldo" in refs:
            cor = (0.14,0.52,0.21,1) if saldo.get('saldo',0) >= 0 else (0.85,0.21,0.20,1)
            refs["💰 Saldo"].text       = fmt(saldo.get('saldo', 0))
            refs["💰 Saldo"].text_color = cor
        if "📈 Entradas" in refs:
            refs["📈 Entradas"].text = fmt(saldo.get('total_entrada', 0))
        if "📉 Saídas" in refs:
            refs["📉 Saídas"].text = fmt(saldo.get('total_saida', 0))
        if "📋 Transações" in refs:
            refs["📋 Transações"].text = str(saldo.get('quantidade', len(trans)))

        # Lista transações
        self.lista_trans.clear_widgets()
        for t in trans:
            cor  = "[color=#3fb950]" if t.get('tipo') == 'entrada' else "[color=#f85149]"
            sina = "+" if t.get('tipo') == 'entrada' else "−"
            cat  = cat_map.get(t.get('categoria_id'), '')
            data = t.get('data','')[:10] if t.get('data') else ''

            item = TwoLineListItem(
                text=f"[b]{t.get('nome_fantasia','')[:28]}[/b]  "
                     f"{cor}{sina} {fmt(t.get('valor',0))}[/color]",
                secondary_text=f"{data}  {cat}",
            )
            self.lista_trans.add_widget(item)


# ==================== CONTEÚDO TRANSAÇÕES ====================

class ConteudoTransacoes(BoxLayout):
    def __init__(self, tela_ref, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.tela_ref    = tela_ref
        self._transacoes = []
        self._categorias = []
        self._cat_map    = {}
        self._construir()

    def _construir(self):
        # Botão adicionar
        btn_add = MDRaisedButton(
            text="+ Nova Transação",
            on_release=lambda x: self._modal_nova(),
            size_hint_y=None,
            height=dp(48),
            size_hint_x=1,
            font_size=sp(14)
        )
        self.add_widget(btn_add)

        # Campo busca
        self.entry_busca = MDTextField(
            hint_text="🔍 Buscar transações...",
            mode="outlined",
            size_hint_y=None,
            height=dp(48)
        )
        self.entry_busca.bind(text=lambda i, v: self._filtrar(v))
        self.add_widget(self.entry_busca)

        # Label total
        self.lbl_total = MDLabel(
            text="",
            font_style="Caption",
            theme_text_color="Secondary",
            halign='right',
            size_hint_y=None,
            height=dp(20)
        )
        self.add_widget(self.lbl_total)

        # Lista scroll
        scroll = ScrollView()
        self.lista = MDList()
        scroll.add_widget(self.lista)
        self.add_widget(scroll)

    def carregar(self, forcar: bool = False):
        def _buscar():
            self._transacoes = sync.obter_transacoes(forcar)
            self._categorias = sync.obter_categorias(forcar)
            self._cat_map    = {c['id']: c['nome'] for c in self._categorias}
            Clock.schedule_once(lambda dt: self._renderizar(), 0)

        threading.Thread(target=_buscar, daemon=True).start()

    def _filtrar(self, texto: str):
        texto = texto.lower()
        filtrada = [
            t for t in self._transacoes
            if texto in t.get('nome_fantasia','').lower() or
               texto in t.get('descricao','').lower()
        ] if texto else self._transacoes
        self._renderizar(filtrada)

    def _renderizar(self, lista: list = None):
        if lista is None:
            lista = self._transacoes

        self.lista.clear_widgets()
        self.lbl_total.text = f"{len(lista)} transações"

        def fmt(v):
            return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')

        for t in lista:
            cor  = "(+)" if t.get('tipo') == 'entrada' else "(−)"
            val  = fmt(t.get('valor', 0))
            cat  = self._cat_map.get(t.get('categoria_id'), '')
            data = t.get('data','')[:10]
            tid  = t['id']

            item = ThreeLineListItem(
                text=f"[b]{t.get('nome_fantasia','')[:24]}[/b]  {cor} {val}",
                secondary_text=f"📅 {data}",
                tertiary_text=f"🏷️ {cat}" if cat else "Sem categoria",
                on_release=lambda x, t=t: self._opcoes_transacao(t)
            )
            self.lista.add_widget(item)

    def _opcoes_transacao(self, t: dict):
        """Dialog com opções para a transação"""
        def fmt(v):
            return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')

        dialog = MDDialog(
            title=t.get('nome_fantasia', ''),
            text=f"Valor: {fmt(t.get('valor',0))}\nData: {t.get('data','')[:10]}",
            buttons=[
                MDFlatButton(
                    text="Fechar",
                    on_release=lambda x: dialog.dismiss()
                ),
                MDFlatButton(
                    text="🗑️ Excluir",
                    theme_text_color="Custom",
                    text_color=(0.97, 0.32, 0.29, 1),
                    on_release=lambda x: self._excluir(t['id'], dialog)
                ),
            ]
        )
        dialog.open()

    def _excluir(self, tid: str, dialog):
        dialog.dismiss()

        def _del():
            ok, _ = sync.excluir_transacao(tid)
            if ok:
                Clock.schedule_once(lambda dt: self.carregar(True), 0)
                Clock.schedule_once(
                    lambda dt: Snackbar(text="🗑️ Transação excluída").open(), 0
                )

        threading.Thread(target=_del, daemon=True).start()

    def _modal_nova(self):
        """Popup para adicionar transação"""
        content = BoxLayout(
            orientation='vertical',
            spacing=dp(10),
            padding=dp(16),
            size_hint_y=None,
            height=dp(420)
        )

        # Tipo
        lbl_tipo = MDLabel(
            text="Tipo:",
            font_style="Caption",
            size_hint_y=None, height=dp(20)
        )
        content.add_widget(lbl_tipo)

        from kivymd.uix.segmentedcontrol import MDSegmentedControl
        # Fallback simples se não tiver MDSegmentedControl
        from kivy.uix.togglebutton import ToggleButton
        frame_tipo = BoxLayout(
            size_hint_y=None, height=dp(40), spacing=dp(8)
        )
        self._tipo_var = ['saida']
        btn_saida  = ToggleButton(text='📉 Saída',   group='tipo', state='down')
        btn_entrada = ToggleButton(text='📈 Entrada', group='tipo')
        btn_saida.bind(on_press=lambda x: self._tipo_var.__setitem__(0,'saida'))
        btn_entrada.bind(on_press=lambda x: self._tipo_var.__setitem__(0,'entrada'))
        frame_tipo.add_widget(btn_saida)
        frame_tipo.add_widget(btn_entrada)
        content.add_widget(frame_tipo)

        # Valor
        entry_valor = MDTextField(
            hint_text="Valor (R$)",
            input_filter='float',
            mode="outlined",
            size_hint_y=None, height=dp(52)
        )
        content.add_widget(entry_valor)

        # Nome
        entry_nome = MDTextField(
            hint_text="Nome / Estabelecimento",
            mode="outlined",
            size_hint_y=None, height=dp(52)
        )
        content.add_widget(entry_nome)

        # Categoria
        from kivy.uix.spinner import Spinner as KSpinner
        nomes_cats = ['Sem categoria'] + [c['nome'] for c in self._categorias]
        spinner_cat = KSpinner(
            text='Sem categoria',
            values=nomes_cats,
            size_hint_y=None, height=dp(44)
        )
        content.add_widget(spinner_cat)

        # Data
        from datetime import datetime
        entry_data = MDTextField(
            hint_text="Data (AAAA-MM-DD)",
            text=datetime.now().strftime('%Y-%m-%d'),
            mode="outlined",
            size_hint_y=None, height=dp(52)
        )
        content.add_widget(entry_data)

        # Label erro
        lbl_err = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=(0.97, 0.32, 0.29, 1),
            font_style="Caption",
            size_hint_y=None, height=dp(20)
        )
        content.add_widget(lbl_err)

        def _salvar(dialog_ref):
            nome  = entry_nome.text.strip()
            valor = entry_valor.text.strip()
            data  = entry_data.text.strip()
            tipo  = self._tipo_var[0]

            if not nome:
                lbl_err.text = "❌ Nome é obrigatório"; return
            try:
                vf = float(valor.replace(',','.'))
                if vf <= 0: raise ValueError
            except Exception:
                lbl_err.text = "❌ Valor inválido"; return

            # Categoria
            cat_id = None
            cat_sel = spinner_cat.text
            for c in self._categorias:
                if c['nome'] == cat_sel:
                    cat_id = c['id']
                    break

            dados = {
                'tipo': tipo, 'valor': vf,
                'nome_fantasia': nome,
                'categoria_id': cat_id,
                'data': data, 'descricao': ''
            }

            def _enviar():
                ok, msg = sync.adicionar_transacao(dados)
                def _fim(dt):
                    if ok:
                        dialog_ref.dismiss()
                        self.carregar(True)
                        self.tela_ref._conteudo_dashboard.carregar(True)
                        Snackbar(text="✅ Transação adicionada!").open()
                    else:
                        lbl_err.text = f"❌ {msg}"

                Clock.schedule_once(_fim, 0)

            threading.Thread(target=_enviar, daemon=True).start()

        dialog = MDDialog(
            title="Nova Transação",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancelar",
                             on_release=lambda x: dialog.dismiss()),
                MDRaisedButton(text="💾 Salvar",
                               on_release=lambda x: _salvar(dialog)),
            ]
        )
        dialog.open()


# ==================== CONTEÚDO CATEGORIAS ====================

class ConteudoCategorias(BoxLayout):
    def __init__(self, tela_ref, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.tela_ref    = tela_ref
        self._categorias = []
        self._construir()

    def _construir(self):
        btn_add = MDRaisedButton(
            text="+ Nova Categoria",
            on_release=lambda x: self._modal_nova(),
            size_hint_y=None,
            height=dp(48),
            size_hint_x=1
        )
        self.add_widget(btn_add)

        scroll = ScrollView()
        self.lista = MDList()
        scroll.add_widget(self.lista)
        self.add_widget(scroll)

    def carregar(self, forcar: bool = False):
        def _buscar():
            self._categorias = sync.obter_categorias(forcar)
            Clock.schedule_once(lambda dt: self._renderizar(), 0)

        threading.Thread(target=_buscar, daemon=True).start()

    def _renderizar(self):
        self.lista.clear_widgets()

        def fmt(v):
            return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')

        if not self._categorias:
            self.lista.add_widget(TwoLineListItem(
                text="Nenhuma categoria",
                secondary_text="Crie uma para organizar seus gastos"
            ))
            return

        icos = {
            'emprestimo': '💸', 'quitacao': '✅', 'organizacao': '📁'
        }
        for cat in self._categorias:
            ico  = icos.get(cat.get('tipo'), '📁')
            saldo_txt = fmt(cat.get('saldo', 0))
            pct = cat.get('percentual_quitado', 0)

            linha2 = (
                f"Saldo: {saldo_txt}  ↑{fmt(cat.get('total_entrada',0))}  "
                f"↓{fmt(cat.get('total_saida',0))}"
            )
            linha3 = f"{pct:.0f}% da meta" if cat.get('meta_valor') else cat.get('tipo','')

            item = ThreeLineListItem(
                text=f"[b]{ico} {cat.get('nome','')}[/b]",
                secondary_text=linha2,
                tertiary_text=linha3,
                on_release=lambda x, c=cat: self._detalhe(c)
            )
            self.lista.add_widget(item)

    def _detalhe(self, cat: dict):
        def fmt(v):
            return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')

        txt = (
            f"Tipo: {cat.get('tipo','')}\n"
            f"Entradas: {fmt(cat.get('total_entrada',0))}\n"
            f"Saídas: {fmt(cat.get('total_saida',0))}\n"
            f"Saldo: {fmt(cat.get('saldo',0))}\n"
            f"Transações: {cat.get('qtd_transacoes',0)}"
        )
        if cat.get('meta_valor'):
            txt += f"\nMeta: {fmt(cat['meta_valor'])} ({cat.get('percentual_quitado',0):.1f}%)"

        dialog = MDDialog(
            title=cat.get('nome',''),
            text=txt,
            buttons=[
                MDFlatButton(text="Fechar",
                             on_release=lambda x: dialog.dismiss()),
                MDFlatButton(
                    text="🗑️ Excluir",
                    theme_text_color="Custom",
                    text_color=(0.97, 0.32, 0.29, 1),
                    on_release=lambda x: self._excluir(cat['id'], dialog)
                ),
            ]
        )
        dialog.open()

    def _excluir(self, cid: str, dialog):
        dialog.dismiss()

        def _del():
            resp = conexao.delete(f'/api/categorias/{cid}')
            if resp and resp.get('sucesso'):
                Clock.schedule_once(lambda dt: self.carregar(True), 0)
                Clock.schedule_once(
                    lambda dt: Snackbar(text="🗑️ Categoria excluída").open(), 0
                )

        threading.Thread(target=_del, daemon=True).start()

    def _modal_nova(self):
        content = BoxLayout(
            orientation='vertical',
            spacing=dp(10),
            padding=dp(16),
            size_hint_y=None,
            height=dp(280)
        )

        entry_nome = MDTextField(
            hint_text="Nome da categoria",
            mode="outlined",
            size_hint_y=None, height=dp(52)
        )
        content.add_widget(entry_nome)

        from kivy.uix.spinner import Spinner as KSpinner
        spinner_tipo = KSpinner(
            text='organizacao',
            values=['organizacao', 'quitacao', 'emprestimo'],
            size_hint_y=None, height=dp(44)
        )
        content.add_widget(spinner_tipo)

        entry_meta = MDTextField(
            hint_text="Meta / Valor Total (R$) - opcional",
            input_filter='float',
            mode="outlined",
            size_hint_y=None, height=dp(52)
        )
        content.add_widget(entry_meta)

        entry_desc = MDTextField(
            hint_text="Descrição (opcional)",
            mode="outlined",
            size_hint_y=None, height=dp(52)
        )
        content.add_widget(entry_desc)

        lbl_err = MDLabel(
            text="", theme_text_color="Custom",
            text_color=(0.97, 0.32, 0.29, 1),
            font_style="Caption",
            size_hint_y=None, height=dp(20)
        )
        content.add_widget(lbl_err)

        def _salvar(dialog_ref):
            nome = entry_nome.text.strip()
            if not nome:
                lbl_err.text = "❌ Nome é obrigatório"; return

            dados = {
                'nome': nome,
                'tipo': spinner_tipo.text,
                'descricao': entry_desc.text.strip()
            }
            try:
                meta = entry_meta.text.strip()
                if meta:
                    dados['meta_valor'] = float(meta.replace(',','.'))
            except Exception:
                pass

            def _enviar():
                ok, msg = sync.adicionar_categoria(dados)
                def _fim(dt):
                    if ok:
                        dialog_ref.dismiss()
                        self.carregar(True)
                        Snackbar(text="✅ Categoria criada!").open()
                    else:
                        lbl_err.text = f"❌ {msg}"
                Clock.schedule_once(_fim, 0)

            threading.Thread(target=_enviar, daemon=True).start()

        dialog = MDDialog(
            title="Nova Categoria",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancelar",
                             on_release=lambda x: dialog.dismiss()),
                MDRaisedButton(text="💾 Salvar",
                               on_release=lambda x: _salvar(dialog)),
            ]
        )
        dialog.open()


# ==================== CONTEÚDO CHAT IA ====================

class ConteudoChat(BoxLayout):
    def __init__(self, tela_ref, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.tela_ref = tela_ref
        self._construir()
        self._msg_boas_vindas()

    def _construir(self):
        # Header
        hdr = MDLabel(
            text="🤖 Assistente IA Financeiro",
            font_style="Subtitle1",
            halign='center',
            theme_text_color="Primary",
            size_hint_y=None,
            height=dp(40),
            bold=True
        )
        self.add_widget(hdr)

        # Área de chat
        scroll = ScrollView(size_hint_y=1)
        self._scroll = scroll
        self.chat_box = BoxLayout(
            orientation='vertical',
            padding=dp(8),
            spacing=dp(8),
            size_hint_y=None
        )
        self.chat_box.bind(
            minimum_height=self.chat_box.setter('height')
        )
        scroll.add_widget(self.chat_box)
        self.add_widget(scroll)

        # Input
        frame_input = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(58),
            padding=dp(8),
            spacing=dp(8)
        )

        self.entry_msg = MDTextField(
            hint_text="Mensagem...",
            mode="outlined",
            multiline=False
        )
        self.entry_msg.bind(
            on_text_validate=lambda x: self._enviar()
        )
        frame_input.add_widget(self.entry_msg)

        btn_env = MDRaisedButton(
            text="➤",
            on_release=lambda x: self._enviar(),
            size_hint_x=None,
            width=dp(52),
            height=dp(44)
        )
        frame_input.add_widget(btn_env)
        self.add_widget(frame_input)

    def _msg_boas_vindas(self):
        self._add_msg(
            "Olá! Sou seu assistente RRFS. "
            "Pergunte sobre seus gastos, peça dicas "
            "ou análises financeiras!",
            'agent'
        )

    def _add_msg(self, texto: str, quem: str):
        alinha = 'right' if quem == 'user' else 'left'
        cor    = (0.12, 0.44, 0.92, 1) if quem == 'user' else (0.11, 0.13, 0.17, 1)

        card = MDCard(
            elevation=2,
            radius=[dp(12)],
            padding=dp(12),
            md_bg_color=cor,
            size_hint_x=0.80,
            size_hint_y=None,
            pos_hint={'right':1} if quem == 'user' else {'left':0}
        )

        lbl = MDLabel(
            text=("👤  " if quem == 'user' else "🤖  ") + texto,
            theme_text_color="Primary",
            font_style="Body2",
            size_hint_y=None,
            halign=alinha
        )
        lbl.bind(texture_size=lambda i, v: lbl.setter('height')(i, v[1]+dp(10)))
        card.bind(minimum_height=card.setter('height'))
        card.add_widget(lbl)

        wrapper = BoxLayout(
            size_hint_y=None,
            height=dp(60)
        )
        wrapper.bind(minimum_height=wrapper.setter('height'))

        if quem == 'user':
            wrapper.add_widget(BoxLayout())
            wrapper.add_widget(card)
        else:
            wrapper.add_widget(card)
            wrapper.add_widget(BoxLayout())

        self.chat_box.add_widget(wrapper)

        # Scroll para baixo
        Clock.schedule_once(
            lambda dt: self._scroll.scroll_to(wrapper), 0.1
        )
        return wrapper

    def _enviar(self):
        msg = self.entry_msg.text.strip()
        if not msg:
            return

        self.entry_msg.text = ""
        self._add_msg(msg, 'user')
        digitando = self._add_msg("⏳ Pensando...", 'agent')

        def _chat():
            resposta = sync.chat_ia(msg, {})

            def _mostrar(dt):
                self.chat_box.remove_widget(digitando)
                self._add_msg(resposta or "Sem resposta", 'agent')

            Clock.schedule_once(_mostrar, 0)

        threading.Thread(target=_chat, daemon=True).start()


# ==================== APP PRINCIPAL ====================

class RRFSApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title     = APP_NOME
        self._sm       = None
        self._tela_login     = None
        self._tela_principal = None

    def build(self):
        # Tema escuro
        self.theme_cls.theme_style   = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.accent_palette  = "Green"

        # Fundo escuro
        Window.clearcolor = (0.05, 0.07, 0.09, 1)

        # Screen Manager
        self._sm = ScreenManager(
            transition=SlideTransition(duration=0.25)
        )

        # Cria telas
        self._tela_login     = TelaLogin(self)
        self._tela_principal = TelaPrincipal(self)

        self._sm.add_widget(self._tela_login)
        self._sm.add_widget(self._tela_principal)
        self._sm.current = 'login'

        return self._sm

    def on_start(self):
        """Chamado quando o app inicia"""
        if IS_ANDROID:
            request_permissions([
                Permission.INTERNET,
                Permission.ACCESS_NETWORK_STATE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])

        # Inicia Tor em background
        print("[APP] Iniciando Tor...")
        tor.set_callback_status(self._tor_status)
        tor.iniciar_em_thread(callback_concluido=self._tor_pronto)

        # Inicia conexão
        threading.Thread(target=self._iniciar_conexao, daemon=True).start()

        # Loop de monitoramento
        Clock.schedule_interval(self._monitor_conexao, 5)

        # Inicia sync automático
        sync.iniciar_sync_automatico()

    def _tor_status(self, msg: str):
        print(f"[TOR] {msg}")

    def _tor_pronto(self, sucesso: bool):
        print(f"[APP] Tor: {'OK' if sucesso else 'FALHOU'}")

    def _iniciar_conexao(self):
        tipo = conexao.conectar()
        Clock.schedule_once(
            lambda dt: self._atualizar_status_ui(tipo), 0
        )

    def _monitor_conexao(self, dt):
        tipo = conexao.tipo_atual
        self._atualizar_status_ui(tipo)
        if tipo == TipoConexao.OFFLINE:
            conexao.reconectar_se_necessario()

    def _atualizar_status_ui(self, tipo: TipoConexao):
        if self._tela_login:
            self._tela_login.atualizar_status_conexao(tipo)
        if self._tela_principal:
            self._tela_principal.atualizar_status_conexao(tipo)

    def ir_para_principal(self):
        """Vai para tela principal após login"""
        self._sm.current = 'principal'
        self._tela_principal.carregar_dados()

    def fazer_logout(self):
        """Logout e volta para login"""
        sessao.logout()
        sync.parar_sync()
        self._sm.current = 'login'
        Snackbar(text="👋 Você saiu com segurança").open()

    def on_pause(self):
        """App minimizado - mantém dados"""
        return True

    def on_resume(self):
        """App voltou ao foco"""
        if sessao.logado:
            self._tela_principal._atualizar()


def main():
    RRFSApp().run()


if __name__ == '__main__':
    main()

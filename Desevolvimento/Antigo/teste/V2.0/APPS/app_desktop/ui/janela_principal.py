"""
Janela principal com sidebar e todas as telas
"""

import threading
import customtkinter as ctk
from core.sessao import sessao
from core.sync import sync
from core.conexao import conexao, TipoConexao
from ui.tela_dashboard import TelaDashboard
from ui.tela_transacoes import TelaTransacoes
from ui.tela_categorias import TelaCategorias
from ui.tela_chat import TelaChat

C = {
    'bg'    : '#0d1117',
    'bg2'   : '#161b22',
    'card'  : '#1c2128',
    'border': '#30363d',
    'text'  : '#e6edf3',
    'text2' : '#8b949e',
    'muted' : '#484f58',
    'green' : '#238636',
    'blue'  : '#1f6feb',
    'red'   : '#da3633',
    'gold'  : '#e3b341',
    'input' : '#21262d',
}

class JanelaPrincipal(ctk.CTkFrame):
    def __init__(self, parent, callback_logout):
        super().__init__(parent, fg_color=C['bg'])
        self.parent          = parent
        self.callback_logout = callback_logout
        self._tela_atual     = None
        self._btns_nav       = {}

        parent.title(f"RRFS Gestão Financeira - {sessao.username}")
        parent.geometry("1200x750")
        parent.resizable(True, True)
        parent.configure(bg=C['bg'])

        self.pack(fill='both', expand=True)
        self._construir()
        self._registrar_sync_callback()

        # Abre dashboard
        self.after(100, lambda: self._navegar('dashboard'))

        # Verifica conexão periodicamente
        self._verificar_conexao_loop()

    def _construir(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(
            self, fg_color=C['bg2'], width=220,
            corner_radius=0,
            border_width=1, border_color=C['border']
        )
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        # Logo sidebar
        frame_logo = ctk.CTkFrame(self.sidebar, fg_color='transparent')
        frame_logo.pack(padx=12, pady=16, fill='x')

        ctk.CTkLabel(
            frame_logo, text="💰 RRFS",
            font=ctk.CTkFont(size=16, weight='bold'),
            text_color=C['text']
        ).pack(anchor='w')

        ctk.CTkLabel(
            frame_logo, text="Gestão Financeira",
            font=ctk.CTkFont(size=11),
            text_color=C['text2']
        ).pack(anchor='w')

        ctk.CTkFrame(
            self.sidebar, fg_color=C['border'], height=1
        ).pack(fill='x', padx=0)

        # Status conexão
        self.lbl_conn = ctk.CTkLabel(
            self.sidebar, text="⏳ Conectando...",
            font=ctk.CTkFont(size=10),
            text_color=C['gold']
        )
        self.lbl_conn.pack(pady=6)

        # Nav frame
        nav_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color='transparent'
        )
        nav_frame.pack(fill='both', expand=True, padx=6, pady=4)

        # Seções de navegação
        self._secao(nav_frame, "Principal")
        self._btn_nav(nav_frame, "dashboard",   "📊", "Dashboard")
        self._btn_nav(nav_frame, "transacoes",  "💳", "Transações")
        self._btn_nav(nav_frame, "categorias",  "🏷️", "Categorias")

        self._secao(nav_frame, "Análises")
        self._btn_nav(nav_frame, "projecoes",   "📈", "Projeções")
        self._btn_nav(nav_frame, "anomalias",   "🔍", "Anomalias")
        self._btn_nav(nav_frame, "chat",        "🤖", "Assistente IA")

        self._secao(nav_frame, "Conta")
        self._btn_nav(nav_frame, "senha",       "🔑", "Alterar Senha")

        # Rodapé sidebar
        ctk.CTkFrame(self.sidebar, fg_color=C['border'], height=1).pack(fill='x')

        frame_user = ctk.CTkFrame(self.sidebar, fg_color='transparent')
        frame_user.pack(padx=10, pady=12, fill='x')

        ctk.CTkLabel(
            frame_user,
            text=f"👤 {sessao.username}",
            font=ctk.CTkFont(size=13, weight='bold'),
            text_color=C['text']
        ).pack(anchor='w')

        ctk.CTkButton(
            frame_user,
            text="🚪 Sair",
            command=self._logout,
            fg_color='transparent',
            hover_color='#3a1a1a',
            text_color=C['text2'],
            height=32, corner_radius=6,
            font=ctk.CTkFont(size=12)
        ).pack(anchor='w', pady=(6, 0))

        # Área de conteúdo
        self.area_conteudo = ctk.CTkFrame(
            self, fg_color=C['bg'], corner_radius=0
        )
        self.area_conteudo.pack(side='right', fill='both', expand=True)

    def _secao(self, parent, texto: str):
        ctk.CTkLabel(
            parent, text=texto.upper(),
            font=ctk.CTkFont(size=10, weight='bold'),
            text_color=C['muted']
        ).pack(anchor='w', padx=10, pady=(10, 2))

    def _btn_nav(self, parent, tela: str, icone: str, texto: str):
        btn = ctk.CTkButton(
            parent,
            text=f"  {icone}  {texto}",
            command=lambda t=tela: self._navegar(t),
            fg_color='transparent',
            hover_color=C['card'],
            text_color=C['text2'],
            anchor='w', height=38,
            corner_radius=8,
            font=ctk.CTkFont(size=13)
        )
        btn.pack(fill='x', pady=1)
        self._btns_nav[tela] = btn

    def _navegar(self, tela: str):
        # Atualiza botões
        for nome, btn in self._btns_nav.items():
            if nome == tela:
                btn.configure(
                    fg_color='rgba(31,111,235,0.15)',
                    text_color=C['blue']
                )
            else:
                btn.configure(fg_color='transparent', text_color=C['text2'])

        # Remove tela atual
        for widget in self.area_conteudo.winfo_children():
            widget.destroy()

        # Cria nova tela
        TELAS = {
            'dashboard' : TelaDashboard,
            'transacoes': TelaTransacoes,
            'categorias': TelaCategorias,
            'chat'      : TelaChat,
            'projecoes' : self._tela_projecoes,
            'anomalias' : self._tela_anomalias,
            'senha'     : self._tela_senha,
        }

        cls = TELAS.get(tela)
        if cls and callable(cls) and isinstance(cls, type):
            self._tela_atual = cls(self.area_conteudo)
            self._tela_atual.pack(fill='both', expand=True)
        elif cls:
            cls()  # Função simples

    def _tela_projecoes(self):
        from ui.tela_projecoes import TelaProjecoes
        t = TelaProjecoes(self.area_conteudo)
        t.pack(fill='both', expand=True)

    def _tela_anomalias(self):
        from ui.tela_anomalias import TelaAnomalias
        t = TelaAnomalias(self.area_conteudo)
        t.pack(fill='both', expand=True)

    def _tela_senha(self):
        from ui.tela_senha import TelaSenha
        t = TelaSenha(self.area_conteudo)
        t.pack(fill='both', expand=True)

    def _registrar_sync_callback(self):
        def _on_sync(tipo: str, dados=None):
            if tipo in ('transacao_adicionada', 'transacao_editada',
                        'transacao_excluida', 'sync_concluido'):
                self.after(0, lambda: self._navegar(
                    'dashboard'
                ) if self._tela_atual else None)

        sync.adicionar_callback_ui(_on_sync)

    def _verificar_conexao_loop(self):
        tipo = conexao.tipo_atual
        textos = {
            TipoConexao.DIRETA    : ("✅ Direto", '#3fb950'),
            TipoConexao.TOR       : ("🧅 Via Tor", '#e3b341'),
            TipoConexao.OFFLINE   : ("❌ Offline", '#f85149'),
            TipoConexao.CONECTANDO: ("⏳...", '#e3b341'),
        }
        txt, cor = textos.get(tipo, ("—", C['text2']))
        self.lbl_conn.configure(text=txt, text_color=cor)

        # Tenta reconectar se offline
        if tipo == TipoConexao.OFFLINE:
            conexao.reconectar_se_necessario()

        self.after(5000, self._verificar_conexao_loop)

    def _logout(self):
        self.callback_logout()

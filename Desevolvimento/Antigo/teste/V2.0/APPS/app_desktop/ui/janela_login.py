"""
Tela de Login - Desktop
"""

import threading
import customtkinter as ctk
from core.conexao import conexao, TipoConexao
from core.sessao import sessao


class JanelaLogin(ctk.CTkFrame):
    CORES = {
        'bg'     : '#0d1117',
        'card'   : '#1c2128',
        'border' : '#30363d',
        'text'   : '#e6edf3',
        'text2'  : '#8b949e',
        'green'  : '#238636',
        'blue'   : '#1f6feb',
        'red'    : '#da3633',
        'gold'   : '#e3b341',
        'input'  : '#21262d',
    }

    def __init__(self, parent, callback_login_ok):
        super().__init__(parent, fg_color=self.CORES['bg'])
        self.parent           = parent
        self.callback_login_ok = callback_login_ok
        self._aba_atual       = 'login'

        parent.title("RRFS Gestão Financeira - Login")
        parent.geometry("460x620")
        parent.resizable(False, False)
        parent.configure(bg=self.CORES['bg'])
        parent.deiconify()

        self.pack(fill='both', expand=True)
        self._construir()
        self._verificar_conexao()

    def _construir(self):
        C = self.CORES

        # Logo
        frame_logo = ctk.CTkFrame(self, fg_color='transparent')
        frame_logo.pack(pady=(40, 20))

        ctk.CTkLabel(
            frame_logo, text="💰",
            font=ctk.CTkFont(size=48)
        ).pack()

        ctk.CTkLabel(
            frame_logo,
            text="RRFS Gestão Financeira",
            font=ctk.CTkFont(size=20, weight='bold'),
            text_color=C['text']
        ).pack(pady=(8, 0))

        ctk.CTkLabel(
            frame_logo,
            text="Pessoal e Familiar · Seguro · Inteligente",
            font=ctk.CTkFont(size=12),
            text_color=C['text2']
        ).pack()

        # Status conexão
        self.lbl_conexao = ctk.CTkLabel(
            self,
            text="⏳ Verificando conexão...",
            font=ctk.CTkFont(size=11),
            text_color=C['gold']
        )
        self.lbl_conexao.pack(pady=(0, 10))

        # Card
        self.card = ctk.CTkFrame(
            self,
            fg_color=C['card'],
            corner_radius=16,
            border_width=1,
            border_color=C['border']
        )
        self.card.pack(padx=40, fill='x')

        # Abas
        frame_abas = ctk.CTkFrame(self.card, fg_color='#161b22', corner_radius=10)
        frame_abas.pack(padx=16, pady=(16, 0), fill='x')

        self.btn_aba_login = ctk.CTkButton(
            frame_abas, text="Entrar",
            command=lambda: self._trocar_aba('login'),
            fg_color=C['card'], hover_color='#30363d',
            text_color=C['text'], corner_radius=8,
            font=ctk.CTkFont(size=13, weight='bold')
        )
        self.btn_aba_login.pack(side='left', padx=4, pady=4, expand=True, fill='x')

        self.btn_aba_reg = ctk.CTkButton(
            frame_abas, text="Criar Conta",
            command=lambda: self._trocar_aba('registro'),
            fg_color='transparent', hover_color='#30363d',
            text_color=C['text2'], corner_radius=8,
            font=ctk.CTkFont(size=13)
        )
        self.btn_aba_reg.pack(side='left', padx=4, pady=4, expand=True, fill='x')

        # Alerta
        self.lbl_alerta = ctk.CTkLabel(
            self.card, text="",
            font=ctk.CTkFont(size=12),
            text_color=C['red'],
            wraplength=340
        )
        self.lbl_alerta.pack(pady=(10, 0), padx=16)

        # ===== FRAME LOGIN =====
        self.frame_login = ctk.CTkFrame(self.card, fg_color='transparent')
        self.frame_login.pack(padx=16, pady=10, fill='x')

        ctk.CTkLabel(
            self.frame_login, text="Usuário",
            font=ctk.CTkFont(size=12), text_color=C['text2']
        ).pack(anchor='w')

        self.entry_user = ctk.CTkEntry(
            self.frame_login,
            placeholder_text="👤 Seu usuário",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=42,
            font=ctk.CTkFont(size=13)
        )
        self.entry_user.pack(fill='x', pady=(4, 10))
        self.entry_user.bind('<Return>', lambda e: self.entry_senha.focus())

        ctk.CTkLabel(
            self.frame_login, text="Senha",
            font=ctk.CTkFont(size=12), text_color=C['text2']
        ).pack(anchor='w')

        self.entry_senha = ctk.CTkEntry(
            self.frame_login,
            placeholder_text="🔒 Sua senha",
            show="●",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=42,
            font=ctk.CTkFont(size=13)
        )
        self.entry_senha.pack(fill='x', pady=(4, 16))
        self.entry_senha.bind('<Return>', lambda e: self._fazer_login())

        self.btn_login = ctk.CTkButton(
            self.frame_login,
            text="🚀 Entrar",
            command=self._fazer_login,
            fg_color=C['blue'], hover_color='#388bfd',
            height=44, corner_radius=8,
            font=ctk.CTkFont(size=14, weight='bold')
        )
        self.btn_login.pack(fill='x')

        # ===== FRAME REGISTRO =====
        self.frame_reg = ctk.CTkFrame(self.card, fg_color='transparent')

        ctk.CTkLabel(
            self.frame_reg, text="Usuário (3–50 caracteres)",
            font=ctk.CTkFont(size=12), text_color=C['text2']
        ).pack(anchor='w')

        self.entry_reg_user = ctk.CTkEntry(
            self.frame_reg,
            placeholder_text="👤 Escolha um usuário",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=42
        )
        self.entry_reg_user.pack(fill='x', pady=(4, 10))

        ctk.CTkLabel(
            self.frame_reg, text="Senha (mín. 8 caracteres)",
            font=ctk.CTkFont(size=12), text_color=C['text2']
        ).pack(anchor='w')

        self.entry_reg_senha = ctk.CTkEntry(
            self.frame_reg,
            placeholder_text="🔒 Senha forte",
            show="●",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=42
        )
        self.entry_reg_senha.pack(fill='x', pady=(4, 10))

        ctk.CTkLabel(
            self.frame_reg, text="Confirmar Senha",
            font=ctk.CTkFont(size=12), text_color=C['text2']
        ).pack(anchor='w')

        self.entry_reg_confirm = ctk.CTkEntry(
            self.frame_reg,
            placeholder_text="🔒 Repita a senha",
            show="●",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=42
        )
        self.entry_reg_confirm.pack(fill='x', pady=(4, 16))
        self.entry_reg_confirm.bind('<Return>', lambda e: self._fazer_registro())

        self.btn_reg = ctk.CTkButton(
            self.frame_reg,
            text="✅ Criar Conta",
            command=self._fazer_registro,
            fg_color=C['green'], hover_color='#2ea043',
            height=44, corner_radius=8,
            font=ctk.CTkFont(size=14, weight='bold')
        )
        self.btn_reg.pack(fill='x')

        # Rodapé
        ctk.CTkLabel(
            self,
            text="🔒 AES-256 · Argon2id · TLS · Tor · RRFS v2.0",
            font=ctk.CTkFont(size=11),
            text_color=C['text2']
        ).pack(pady=16)

    def _trocar_aba(self, aba: str):
        self._aba_atual = aba
        self.lbl_alerta.configure(text='')

        if aba == 'login':
            self.frame_reg.pack_forget()
            self.frame_login.pack(padx=16, pady=10, fill='x')
            self.btn_aba_login.configure(
                fg_color=self.CORES['card'], text_color=self.CORES['text']
            )
            self.btn_aba_reg.configure(
                fg_color='transparent', text_color=self.CORES['text2']
            )
        else:
            self.frame_login.pack_forget()
            self.frame_reg.pack(padx=16, pady=10, fill='x')
            self.btn_aba_reg.configure(
                fg_color=self.CORES['card'], text_color=self.CORES['text']
            )
            self.btn_aba_login.configure(
                fg_color='transparent', text_color=self.CORES['text2']
            )

    def _alerta(self, msg: str, cor: str = None):
        cor = cor or self.CORES['red']
        self.lbl_alerta.configure(text=msg, text_color=cor)

    def _verificar_conexao(self):
        """Verifica status da conexão periodicamente"""
        tipo = conexao.tipo_atual
        msgs = {
            TipoConexao.DIRETA    : ("✅ Conexão direta com servidor", '#3fb950'),
            TipoConexao.TOR       : ("🧅 Conectado via Tor",           '#e3b341'),
            TipoConexao.OFFLINE   : ("❌ Sem conexão - verifique rede", '#f85149'),
            TipoConexao.CONECTANDO: ("⏳ Conectando...",                '#e3b341'),
        }
        txt, cor = msgs.get(tipo, ("⏳ Aguardando...", '#e3b341'))
        self.lbl_conexao.configure(text=txt, text_color=cor)

        # Agenda próxima verificação
        self.after(3000, self._verificar_conexao)

    def _fazer_login(self):
        username = self.entry_user.get().strip()
        senha    = self.entry_senha.get()

        if not username or not senha:
            self._alerta("❌ Preencha usuário e senha")
            return

        if not conexao.esta_online():
            self._alerta("❌ Sem conexão com o servidor")
            return

        self.btn_login.configure(text="⏳ Aguarde...", state='disabled')
        self.lbl_alerta.configure(text='')

        def _login():
            ok, msg = sessao.fazer_login(username, senha)

            def _atualizar():
                self.btn_login.configure(text="🚀 Entrar", state='normal')
                if ok:
                    if msg == "TROCAR_SENHA":
                        self._alerta(
                            "⚠️ Você precisa trocar sua senha. Use o app web.",
                            cor=self.CORES['gold']
                        )
                    else:
                        self._alerta("✅ Login realizado!", cor='#3fb950')
                        self.after(500, lambda: self.callback_login_ok({
                            'username' : sessao.username,
                            'is_admin' : sessao.is_admin
                        }))
                else:
                    self._alerta(f"❌ {msg}")

            self.after(0, _atualizar)

        threading.Thread(target=_login, daemon=True).start()

    def _fazer_registro(self):
        username = self.entry_reg_user.get().strip()
        senha    = self.entry_reg_senha.get()
        confirm  = self.entry_reg_confirm.get()

        if not username or not senha or not confirm:
            self._alerta("❌ Preencha todos os campos")
            return
        if senha != confirm:
            self._alerta("❌ As senhas não coincidem")
            return
        if len(senha) < 8:
            self._alerta("❌ Mínimo 8 caracteres")
            return

        self.btn_reg.configure(text="⏳ Aguarde...", state='disabled')

        def _reg():
            resp = conexao.post('/api/registro', {
                'username': username,
                'password': senha
            })

            def _atualizar():
                self.btn_reg.configure(text="✅ Criar Conta", state='normal')
                if resp and resp.get('sucesso'):
                    self._alerta("✅ Conta criada! Faça o login.", cor='#3fb950')
                    self.after(1500, lambda: self._trocar_aba('login'))
                else:
                    self._alerta(f"❌ {resp.get('erro', 'Erro') if resp else 'Sem conexão'}")

            self.after(0, _atualizar)

        threading.Thread(target=_reg, daemon=True).start()

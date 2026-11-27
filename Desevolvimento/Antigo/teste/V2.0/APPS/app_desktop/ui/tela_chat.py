"""
Tela Chat IA - Desktop
"""

import threading
import customtkinter as ctk
from core.sync import sync
from core.sessao import sessao

C = {
    'bg':'#0d1117','card':'#1c2128','border':'#30363d',
    'text':'#e6edf3','text2':'#8b949e',
    'blue':'#1f6feb','blue-h':'#388bfd',
    'purple':'#8957e5','input':'#21262d',
}


class TelaChat(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg'])
        self._construir()
        self._msg_boas_vindas()

    def _construir(self):
        # Topbar
        top = ctk.CTkFrame(self, fg_color='#161b22', corner_radius=0, height=56)
        top.pack(fill='x')
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text="🤖 Assistente IA Financeiro",
            font=ctk.CTkFont(size=18, weight='bold'),
            text_color=C['text']
        ).pack(side='left', padx=20, pady=16)

        # Área de mensagens
        self.chat_area = ctk.CTkScrollableFrame(
            self, fg_color='#161b22'
        )
        self.chat_area.pack(fill='both', expand=True, padx=16, pady=16)

        # Área de input
        frame_input = ctk.CTkFrame(self, fg_color='#161b22', height=70)
        frame_input.pack(fill='x', padx=16, pady=(0, 16))
        frame_input.pack_propagate(False)

        self.entry_msg = ctk.CTkEntry(
            frame_input,
            placeholder_text="Digite sua mensagem... (ex: Como estão meus gastos este mês?)",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=44,
            font=ctk.CTkFont(size=13)
        )
        self.entry_msg.pack(side='left', fill='both', expand=True, pady=13, padx=(12,8))
        self.entry_msg.bind('<Return>', lambda e: self._enviar())

        self.btn_enviar = ctk.CTkButton(
            frame_input, text="Enviar ➤",
            command=self._enviar,
            fg_color=C['blue'], hover_color=C['blue-h'],
            text_color='#fff', width=100, height=44,
            font=ctk.CTkFont(size=13, weight='bold')
        )
        self.btn_enviar.pack(side='right', pady=13, padx=(0, 12))

    def _msg_boas_vindas(self):
        self._add_msg(
            "Olá! Sou seu assistente financeiro RRFS. "
            "Posso analisar seus gastos, dar dicas de economia "
            "e responder perguntas sobre suas finanças. "
            "Como posso ajudar?",
            'agent'
        )

    def _add_msg(self, texto: str, quem: str) -> ctk.CTkFrame:
        """Adiciona mensagem ao chat"""
        frame_ext = ctk.CTkFrame(self.chat_area, fg_color='transparent')
        frame_ext.pack(fill='x', pady=4)

        if quem == 'user':
            # Alinha à direita
            frame_msg = ctk.CTkFrame(
                frame_ext,
                fg_color=C['blue'], corner_radius=12
            )
            frame_msg.pack(side='right', padx=(60, 0))

            ctk.CTkLabel(
                frame_msg, text=texto,
                font=ctk.CTkFont(size=13),
                text_color='#fff',
                wraplength=380, justify='left',
                anchor='w'
            ).pack(padx=14, pady=10)

        else:
            # Alinha à esquerda
            frame_row = ctk.CTkFrame(frame_ext, fg_color='transparent')
            frame_row.pack(side='left')

            ctk.CTkLabel(
                frame_row, text="🤖",
                font=ctk.CTkFont(size=20)
            ).pack(side='left', anchor='n', padx=(0, 8), pady=4)

            frame_msg = ctk.CTkFrame(
                frame_row,
                fg_color=C['card'],
                corner_radius=12,
                border_width=1, border_color=C['border']
            )
            frame_msg.pack(side='left')

            ctk.CTkLabel(
                frame_msg, text=texto,
                font=ctk.CTkFont(size=13),
                text_color=C['text'],
                wraplength=400, justify='left',
                anchor='w'
            ).pack(padx=14, pady=10)

        # Scroll para baixo
        self.after(100, lambda: self.chat_area._parent_canvas.yview_moveto(1.0))
        return frame_ext

    def _enviar(self):
        msg = self.entry_msg.get().strip()
        if not msg:
            return

        self.entry_msg.delete(0, 'end')
        self._add_msg(msg, 'user')

        # Indicador de digitação
        digitando = self._add_msg("⏳ Pensando...", 'agent')

        self.btn_enviar.configure(state='disabled')
        self.entry_msg.configure(state='disabled')

        def _chat():
            resposta = sync.chat_ia(msg, {})

            def _mostrar():
                digitando.destroy()
                self._add_msg(resposta or "Sem resposta", 'agent')
                self.btn_enviar.configure(state='normal')
                self.entry_msg.configure(state='normal')
                self.entry_msg.focus()

            self.after(0, _mostrar)

        threading.Thread(target=_chat, daemon=True).start()

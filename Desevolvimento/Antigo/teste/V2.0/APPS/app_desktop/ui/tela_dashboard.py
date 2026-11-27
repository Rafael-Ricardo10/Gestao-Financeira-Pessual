"""
Tela Dashboard - Desktop
"""

import threading
import customtkinter as ctk
from core.sync import sync

C = {
    'bg':'#0d1117','card':'#1c2128','border':'#30363d',
    'text':'#e6edf3','text2':'#8b949e','muted':'#484f58',
    'green':'#3fb950','blue':'#388bfd','red':'#f85149','gold':'#e3b341',
}

def fmt_moeda(v):
    return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')

def fmt_data(d):
    if not d: return '—'
    try:
        parts = d[:10].split('-')
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        return d


class TelaDashboard(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg'])
        self._construir()
        self._carregar_dados()

    def _construir(self):
        # Topbar
        topbar = ctk.CTkFrame(self, fg_color='#161b22', corner_radius=0, height=56)
        topbar.pack(fill='x')
        topbar.pack_propagate(False)

        ctk.CTkLabel(
            topbar, text="📊 Dashboard",
            font=ctk.CTkFont(size=18, weight='bold'),
            text_color=C['text']
        ).pack(side='left', padx=20, pady=16)

        ctk.CTkButton(
            topbar, text="🔄 Atualizar",
            command=lambda: self._carregar_dados(forcar=True),
            fg_color='#21262d', hover_color='#30363d',
            text_color=C['text2'], height=32,
            font=ctk.CTkFont(size=12)
        ).pack(side='right', padx=16, pady=12)

        # Scroll
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C['bg'])
        self.scroll.pack(fill='both', expand=True, padx=16, pady=16)

        # Cards saldo
        self.frame_cards = ctk.CTkFrame(self.scroll, fg_color='transparent')
        self.frame_cards.pack(fill='x', pady=(0, 16))

        self.card_saldo  = self._criar_card("💰 Saldo Total",   "R$ 0,00", C['blue'])
        self.card_entr   = self._criar_card("📈 Entradas",      "R$ 0,00", C['green'])
        self.card_said   = self._criar_card("📉 Saídas",        "R$ 0,00", C['red'])
        self.card_qtd    = self._criar_card("📋 Transações",    "0",       C['gold'])

        # Últimas transações
        ctk.CTkLabel(
            self.scroll,
            text="📋 Últimas Transações",
            font=ctk.CTkFont(size=15, weight='bold'),
            text_color=C['text']
        ).pack(anchor='w', pady=(0, 8))

        self.frame_trans = ctk.CTkFrame(
            self.scroll, fg_color='#1c2128',
            corner_radius=12, border_width=1,
            border_color=C['border']
        )
        self.frame_trans.pack(fill='x')

        self.lbl_loading = ctk.CTkLabel(
            self.frame_trans, text="⏳ Carregando...",
            font=ctk.CTkFont(size=13), text_color=C['text2']
        )
        self.lbl_loading.pack(pady=30)

    def _criar_card(self, titulo: str, valor: str, cor: str) -> dict:
        frame = ctk.CTkFrame(
            self.frame_cards,
            fg_color='#1c2128', corner_radius=12,
            border_width=1, border_color='#30363d'
        )
        frame.pack(side='left', fill='both', expand=True, padx=(0, 8))

        ctk.CTkFrame(
            frame, fg_color=cor, width=3,
            corner_radius=0
        ).pack(side='left', fill='y')

        inner = ctk.CTkFrame(frame, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            inner, text=titulo,
            font=ctk.CTkFont(size=11),
            text_color=C['text2']
        ).pack(anchor='w')

        lbl_valor = ctk.CTkLabel(
            inner, text=valor,
            font=ctk.CTkFont(size=22, weight='bold'),
            text_color=cor
        )
        lbl_valor.pack(anchor='w', pady=(4, 0))

        return {'frame': frame, 'lbl': lbl_valor}

    def _atualizar_card(self, card: dict, valor: str):
        card['lbl'].configure(text=valor)

    def _carregar_dados(self, forcar: bool = False):
        def _buscar():
            saldo    = sync.obter_saldo(forcar)
            trans    = sync.obter_transacoes(forcar)
            cats     = sync.obter_categorias(forcar)
            cat_map  = {c['id']: c['nome'] for c in cats}

            self.after(0, lambda: self._atualizar_ui(saldo, trans, cat_map))

        threading.Thread(target=_buscar, daemon=True).start()

    def _atualizar_ui(self, saldo: dict, trans: list, cat_map: dict):
        # Atualiza cards
        self._atualizar_card(self.card_saldo, fmt_moeda(saldo.get('saldo', 0)))
        self._atualizar_card(self.card_entr,  fmt_moeda(saldo.get('total_entrada', 0)))
        self._atualizar_card(self.card_said,  fmt_moeda(saldo.get('total_saida', 0)))
        self._atualizar_card(self.card_qtd,   str(saldo.get('quantidade', len(trans))))

        # Limpa frame transações
        for w in self.frame_trans.winfo_children():
            w.destroy()

        ultimas = trans[:10]
        if not ultimas:
            ctk.CTkLabel(
                self.frame_trans,
                text="📭 Nenhuma transação. Comece adicionando uma!",
                font=ctk.CTkFont(size=13), text_color=C['text2']
            ).pack(pady=30)
            return

        # Cabeçalho
        hdr = ctk.CTkFrame(self.frame_trans, fg_color='#161b22')
        hdr.pack(fill='x')
        for col, w in [("Data",20),("Nome",35),("Categoria",20),("Valor",15),("Tipo",10)]:
            ctk.CTkLabel(
                hdr, text=col,
                font=ctk.CTkFont(size=11, weight='bold'),
                text_color=C['text2'], width=int(w*8)
            ).pack(side='left', padx=12, pady=8)

        # Linhas
        for t in ultimas:
            cor_val  = C['green'] if t.get('tipo') == 'entrada' else C['red']
            sinal    = "+" if t.get('tipo') == 'entrada' else "−"
            cat_nome = cat_map.get(t.get('categoria_id'), '—')

            linha = ctk.CTkFrame(
                self.frame_trans, fg_color='transparent',
                cursor='hand2'
            )
            linha.pack(fill='x')

            ctk.CTkFrame(
                self.frame_trans, fg_color='#30363d', height=1
            ).pack(fill='x', padx=12)

            for txt, w, cor in [
                (fmt_data(t.get('data')), 160, C['text2']),
                (t.get('nome_fantasia','')[:28], 280, C['text']),
                (cat_nome[:18], 160, C['text2']),
                (f"{sinal} {fmt_moeda(t.get('valor',0))}", 120, cor_val),
            ]:
                ctk.CTkLabel(
                    linha, text=txt, width=w,
                    font=ctk.CTkFont(size=12),
                    text_color=cor, anchor='w'
                ).pack(side='left', padx=12, pady=8)

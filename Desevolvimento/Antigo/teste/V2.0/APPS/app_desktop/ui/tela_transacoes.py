"""
Tela de Transações - Desktop
"""

import threading
import customtkinter as ctk
from datetime import datetime
from core.sync import sync
from core.conexao import conexao

C = {
    'bg':'#0d1117','card':'#1c2128','border':'#30363d',
    'text':'#e6edf3','text2':'#8b949e','muted':'#484f58',
    'green':'#3fb950','blue':'#388bfd','red':'#f85149',
    'gold':'#e3b341','input':'#21262d',
}

def fmt_moeda(v):
    return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')

def fmt_data(d):
    if not d: return '—'
    try:
        p = d[:10].split('-')
        return f"{p[2]}/{p[1]}/{p[0]}"
    except Exception:
        return d


class TelaTransacoes(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg'])
        self._transacoes = []
        self._categorias = []
        self._cat_map    = {}
        self._construir()
        self._carregar()

    def _construir(self):
        # Topbar
        top = ctk.CTkFrame(self, fg_color='#161b22', corner_radius=0, height=56)
        top.pack(fill='x')
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text="💳 Transações",
            font=ctk.CTkFont(size=18, weight='bold'),
            text_color=C['text']
        ).pack(side='left', padx=20, pady=16)

        ctk.CTkButton(
            top, text="+ Nova Transação",
            command=self._abrir_modal_nova,
            fg_color=C['blue'], hover_color='#388bfd',
            text_color='#fff', height=34,
            font=ctk.CTkFont(size=13, weight='bold')
        ).pack(side='right', padx=16, pady=10)

        # Filtros
        frame_filtros = ctk.CTkFrame(self, fg_color='#161b22', height=52)
        frame_filtros.pack(fill='x')
        frame_filtros.pack_propagate(False)

        self.entry_busca = ctk.CTkEntry(
            frame_filtros, placeholder_text="🔍 Buscar...",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=34, width=220,
            font=ctk.CTkFont(size=12)
        )
        self.entry_busca.pack(side='left', padx=12, pady=9)
        self.entry_busca.bind('<KeyRelease>', lambda e: self._filtrar())

        self.combo_tipo = ctk.CTkComboBox(
            frame_filtros,
            values=['Todos', 'Entradas', 'Saídas'],
            command=lambda v: self._filtrar(),
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], width=130, height=34
        )
        self.combo_tipo.pack(side='left', padx=4, pady=9)
        self.combo_tipo.set('Todos')

        ctk.CTkButton(
            frame_filtros, text="✖ Limpar",
            command=self._limpar_filtros,
            fg_color='transparent', hover_color=C['card'],
            text_color=C['text2'], height=34, width=80
        ).pack(side='left', padx=4)

        self.lbl_total = ctk.CTkLabel(
            frame_filtros, text="",
            font=ctk.CTkFont(size=12), text_color=C['text2']
        )
        self.lbl_total.pack(side='right', padx=16)

        # Lista scroll
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C['bg'])
        self.scroll.pack(fill='both', expand=True, padx=16, pady=16)

        self.lbl_loading = ctk.CTkLabel(
            self.scroll, text="⏳ Carregando...",
            font=ctk.CTkFont(size=14), text_color=C['text2']
        )
        self.lbl_loading.pack(pady=40)

    def _carregar(self):
        def _buscar():
            self._transacoes = sync.obter_transacoes()
            self._categorias = sync.obter_categorias()
            self._cat_map    = {c['id']: c['nome'] for c in self._categorias}
            self.after(0, self._renderizar)

        threading.Thread(target=_buscar, daemon=True).start()

    def _filtrar(self):
        texto = self.entry_busca.get().lower()
        tipo  = self.combo_tipo.get()

        lista = self._transacoes

        if texto:
            lista = [t for t in lista if
                texto in t.get('nome_fantasia','').lower() or
                texto in t.get('descricao','').lower()]

        if tipo == 'Entradas':
            lista = [t for t in lista if t.get('tipo') == 'entrada']
        elif tipo == 'Saídas':
            lista = [t for t in lista if t.get('tipo') == 'saida']

        self._renderizar(lista)

    def _limpar_filtros(self):
        self.entry_busca.delete(0, 'end')
        self.combo_tipo.set('Todos')
        self._renderizar()

    def _renderizar(self, lista: list = None):
        if lista is None:
            lista = self._transacoes

        # Limpa
        for w in self.scroll.winfo_children():
            w.destroy()

        self.lbl_total.configure(
            text=f"{len(lista)} de {len(self._transacoes)}"
        )

        if not lista:
            ctk.CTkLabel(
                self.scroll,
                text="💳 Nenhuma transação encontrada",
                font=ctk.CTkFont(size=14), text_color=C['text2']
            ).pack(pady=40)
            return

        # Cabeçalho
        hdr = ctk.CTkFrame(
            self.scroll, fg_color='#161b22',
            corner_radius=8
        )
        hdr.pack(fill='x', pady=(0,4))

        for col, larg in [("Data",100),("Nome/Desc",280),("Categoria",150),("Valor",130),("",80)]:
            ctk.CTkLabel(
                hdr, text=col, width=larg,
                font=ctk.CTkFont(size=11, weight='bold'),
                text_color=C['text2'], anchor='w'
            ).pack(side='left', padx=10, pady=8)

        # Itens
        for t in lista:
            self._item_transacao(t)

    def _item_transacao(self, t: dict):
        cor  = C['green'] if t.get('tipo') == 'entrada' else C['red']
        sina = "+" if t.get('tipo') == 'entrada' else "−"
        cat  = self._cat_map.get(t.get('categoria_id'), '—')

        frame = ctk.CTkFrame(
            self.scroll, fg_color=C['card'],
            corner_radius=8, border_width=1,
            border_color=C['border']
        )
        frame.pack(fill='x', pady=2)

        # Barra lateral colorida
        ctk.CTkFrame(
            frame, fg_color=cor, width=3, corner_radius=0
        ).pack(side='left', fill='y')

        inner = ctk.CTkFrame(frame, fg_color='transparent')
        inner.pack(fill='x', expand=True)

        # Linha principal
        linha1 = ctk.CTkFrame(inner, fg_color='transparent')
        linha1.pack(fill='x', padx=10, pady=(8, 2))

        ctk.CTkLabel(
            linha1, text=fmt_data(t.get('data')),
            font=ctk.CTkFont(size=11), text_color=C['text2'],
            width=100, anchor='w'
        ).pack(side='left')

        ctk.CTkLabel(
            linha1,
            text=t.get('nome_fantasia', '')[:30],
            font=ctk.CTkFont(size=13, weight='bold'),
            text_color=C['text'], anchor='w', width=280
        ).pack(side='left', padx=8)

        ctk.CTkLabel(
            linha1, text=cat[:18],
            font=ctk.CTkFont(size=11), text_color=C['blue'],
            width=150, anchor='w'
        ).pack(side='left')

        ctk.CTkLabel(
            linha1,
            text=f"{sina} {fmt_moeda(t.get('valor', 0))}",
            font=ctk.CTkFont(size=14, weight='bold'),
            text_color=cor, width=130, anchor='e'
        ).pack(side='left')

        # Botões
        frame_btns = ctk.CTkFrame(linha1, fg_color='transparent')
        frame_btns.pack(side='right')

        ctk.CTkButton(
            frame_btns, text="✏️",
            command=lambda tid=t['id']: self._editar(tid),
            fg_color='transparent', hover_color=C['card'],
            text_color=C['text2'], width=32, height=28
        ).pack(side='left')

        ctk.CTkButton(
            frame_btns, text="🗑️",
            command=lambda tid=t['id']: self._excluir(tid),
            fg_color='transparent', hover_color='#3a1a1a',
            text_color=C['text2'], width=32, height=28
        ).pack(side='left')

        # Descrição
        if t.get('descricao'):
            ctk.CTkLabel(
                inner,
                text=t['descricao'][:80],
                font=ctk.CTkFont(size=11),
                text_color=C['text2'], anchor='w'
            ).pack(anchor='w', padx=14, pady=(0, 8))

    def _abrir_modal_nova(self):
        self._modal_transacao()

    def _editar(self, tid: str):
        t = next((x for x in self._transacoes if x['id'] == tid), None)
        if t:
            self._modal_transacao(t)

    def _modal_transacao(self, transacao: dict = None):
        """Modal para adicionar/editar transação"""
        modal = ctk.CTkToplevel(self)
        modal.title("Nova Transação" if not transacao else "Editar Transação")
        modal.geometry("480x520")
        modal.configure(fg_color=C['card'])
        modal.transient(self.winfo_toplevel())
        modal.grab_set()

        ctk.CTkLabel(
            modal,
            text="Nova Transação" if not transacao else "Editar Transação",
            font=ctk.CTkFont(size=17, weight='bold'),
            text_color=C['text']
        ).pack(padx=24, pady=(20, 4), anchor='w')

        lbl_err = ctk.CTkLabel(
            modal, text="",
            font=ctk.CTkFont(size=12), text_color=C['red']
        )
        lbl_err.pack(padx=24, anchor='w')

        content = ctk.CTkScrollableFrame(modal, fg_color='transparent')
        content.pack(fill='both', expand=True, padx=24, pady=8)

        # Tipo + Valor
        row1 = ctk.CTkFrame(content, fg_color='transparent')
        row1.pack(fill='x', pady=4)

        ctk.CTkLabel(row1, text="Tipo", font=ctk.CTkFont(size=12),
                     text_color=C['text2']).pack(anchor='w')
        combo_tipo = ctk.CTkComboBox(
            row1, values=['saida', 'entrada'],
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=38
        )
        combo_tipo.set(transacao.get('tipo', 'saida') if transacao else 'saida')
        combo_tipo.pack(fill='x', pady=(4,8))

        ctk.CTkLabel(row1, text="Valor (R$)", font=ctk.CTkFont(size=12),
                     text_color=C['text2']).pack(anchor='w')
        entry_valor = ctk.CTkEntry(
            row1, placeholder_text="0.00",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=38
        )
        if transacao: entry_valor.insert(0, str(transacao.get('valor', '')))
        entry_valor.pack(fill='x', pady=(4,8))

        # Nome
        ctk.CTkLabel(content, text="Nome / Estabelecimento",
                     font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        entry_nome = ctk.CTkEntry(
            content, placeholder_text="Ex: Supermercado",
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=38
        )
        if transacao: entry_nome.insert(0, transacao.get('nome_fantasia', ''))
        entry_nome.pack(fill='x', pady=(4,8))

        # Categoria
        ctk.CTkLabel(content, text="Categoria",
                     font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        nomes_cats = ['Sem categoria'] + [c['nome'] for c in self._categorias]
        combo_cat = ctk.CTkComboBox(
            content, values=nomes_cats,
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=38
        )
        cat_atual = '—'
        if transacao and transacao.get('categoria_id'):
            cat_atual = self._cat_map.get(transacao['categoria_id'], 'Sem categoria')
        combo_cat.set(cat_atual if cat_atual != '—' else 'Sem categoria')
        combo_cat.pack(fill='x', pady=(4,8))

        # Data
        ctk.CTkLabel(content, text="Data (AAAA-MM-DD)",
                     font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        entry_data = ctk.CTkEntry(
            content, placeholder_text=datetime.now().strftime('%Y-%m-%d'),
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], height=38
        )
        if transacao: entry_data.insert(0, transacao.get('data', ''))
        else: entry_data.insert(0, datetime.now().strftime('%Y-%m-%d'))
        entry_data.pack(fill='x', pady=(4,8))

        # Descrição
        ctk.CTkLabel(content, text="Descrição (opcional)",
                     font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        entry_desc = ctk.CTkTextbox(
            content, height=70,
            fg_color=C['input'], border_color=C['border'],
            text_color=C['text'], border_width=1
        )
        if transacao and transacao.get('descricao'):
            entry_desc.insert('0.0', transacao['descricao'])
        entry_desc.pack(fill='x', pady=(4,8))

        # Botões
        frame_btns = ctk.CTkFrame(modal, fg_color='transparent')
        frame_btns.pack(fill='x', padx=24, pady=16)

        def _salvar():
            tipo   = combo_tipo.get()
            valor  = entry_valor.get().strip().replace(',', '.')
            nome   = entry_nome.get().strip()
            data   = entry_data.get().strip()
            desc   = entry_desc.get('0.0', 'end').strip()
            cat_n  = combo_cat.get()

            if not nome:
                lbl_err.configure(text="❌ Nome é obrigatório")
                return
            try:
                valor_f = float(valor)
                if valor_f <= 0: raise ValueError
            except Exception:
                lbl_err.configure(text="❌ Valor inválido")
                return

            # Encontra categoria_id
            cat_id = None
            for c in self._categorias:
                if c['nome'] == cat_n:
                    cat_id = c['id']
                    break

            dados = {
                'tipo': tipo, 'valor': valor_f,
                'nome_fantasia': nome, 'descricao': desc,
                'categoria_id': cat_id, 'data': data
            }

            btn_salvar.configure(text="⏳", state='disabled')

            def _enviar():
                if transacao:
                    ok, msg = sync.editar_transacao(transacao['id'], dados)
                else:
                    ok, msg = sync.adicionar_transacao(dados)

                def _fim():
                    btn_salvar.configure(text="💾 Salvar", state='normal')
                    if ok:
                        modal.destroy()
                        self._carregar()
                    else:
                        lbl_err.configure(text=f"❌ {msg}")

                self.after(0, _fim)

            threading.Thread(target=_enviar, daemon=True).start()

        ctk.CTkButton(
            frame_btns, text="Cancelar",
            command=modal.destroy,
            fg_color=C['input'], hover_color=C['border'],
            text_color=C['text2'], height=40
        ).pack(side='left', expand=True, padx=(0, 8))

        btn_salvar = ctk.CTkButton(
            frame_btns, text="💾 Salvar",
            command=_salvar,
            fg_color=C['blue'], hover_color='#388bfd',
            text_color='#fff', height=40,
            font=ctk.CTkFont(size=13, weight='bold')
        )
        btn_salvar.pack(side='right', expand=True)

    def _excluir(self, tid: str):
        from tkinter import messagebox
        if not messagebox.askyesno("Confirmar", "Excluir esta transação?"):
            return

        def _del():
            ok, msg = sync.excluir_transacao(tid)
            def _fim():
                if ok:
                    self._carregar()

            self.after(0, _fim)

        threading.Thread(target=_del, daemon=True).start()

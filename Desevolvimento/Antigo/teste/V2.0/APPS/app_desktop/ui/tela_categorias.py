"""
Tela de Categorias - Desktop
"""

import threading
import customtkinter as ctk
from core.sync import sync
from core.conexao import conexao

C = {
    'bg':'#0d1117','card':'#1c2128','border':'#30363d',
    'text':'#e6edf3','text2':'#8b949e','muted':'#484f58',
    'green':'#3fb950','blue':'#388bfd','red':'#f85149',
    'gold':'#e3b341','purple':'#bc8cff','input':'#21262d',
}

def fmt_moeda(v):
    return f"R$ {float(v or 0):,.2f}".replace(',','X').replace('.',',').replace('X','.')


class TelaCategorias(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg'])
        self._categorias = []
        self._construir()
        self._carregar()

    def _construir(self):
        top = ctk.CTkFrame(self, fg_color='#161b22', corner_radius=0, height=56)
        top.pack(fill='x')
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text="🏷️ Categorias",
            font=ctk.CTkFont(size=18, weight='bold'),
            text_color=C['text']
        ).pack(side='left', padx=20, pady=16)

        ctk.CTkButton(
            top, text="+ Nova Categoria",
            command=self._modal_categoria,
            fg_color=C['blue'], hover_color='#388bfd',
            text_color='#fff', height=34,
            font=ctk.CTkFont(size=13, weight='bold')
        ).pack(side='right', padx=16, pady=10)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C['bg'])
        self.scroll.pack(fill='both', expand=True, padx=16, pady=16)

    def _carregar(self):
        def _buscar():
            self._categorias = sync.obter_categorias()
            self.after(0, self._renderizar)

        threading.Thread(target=_buscar, daemon=True).start()

    def _renderizar(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        if not self._categorias:
            ctk.CTkLabel(
                self.scroll,
                text="🏷️ Nenhuma categoria. Crie uma para organizar!",
                font=ctk.CTkFont(size=14), text_color=C['text2']
            ).pack(pady=40)
            return

        # Grid 2 colunas
        frame_grid = ctk.CTkFrame(self.scroll, fg_color='transparent')
        frame_grid.pack(fill='x')
        frame_grid.columnconfigure((0, 1), weight=1)

        for i, cat in enumerate(self._categorias):
            self._card_categoria(frame_grid, cat, i)

    def _card_categoria(self, parent, cat: dict, idx: int):
        ico = {'emprestimo': '💸', 'quitacao': '✅', 'organizacao': '📁'}.get(cat.get('tipo'), '📁')
        cor = {'emprestimo': C['purple'], 'quitacao': C['gold'], 'organizacao': C['blue']}.get(cat.get('tipo'), C['blue'])

        frame = ctk.CTkFrame(
            parent, fg_color=C['card'],
            corner_radius=12, border_width=1,
            border_color=C['border']
        )
        frame.grid(row=idx//2, column=idx%2, padx=6, pady=6, sticky='nsew')

        # Barra colorida topo
        ctk.CTkFrame(frame, fg_color=cor, height=3, corner_radius=0).pack(fill='x')

        inner = ctk.CTkFrame(frame, fg_color='transparent')
        inner.pack(fill='x', padx=14, pady=12)

        # Título
        titulo = ctk.CTkFrame(inner, fg_color='transparent')
        titulo.pack(fill='x')

        ctk.CTkLabel(
            titulo, text=f"{ico} {cat['nome']}",
            font=ctk.CTkFont(size=14, weight='bold'),
            text_color=C['text']
        ).pack(side='left')

        # Botões
        frame_btns = ctk.CTkFrame(titulo, fg_color='transparent')
        frame_btns.pack(side='right')

        ctk.CTkButton(
            frame_btns, text="🗑️",
            command=lambda cid=cat['id']: self._excluir(cid),
            fg_color='transparent', hover_color='#3a1a1a',
            text_color=C['text2'], width=30, height=26
        ).pack(side='right')

        # Saldo
        saldo_cor = C['green'] if cat.get('saldo', 0) >= 0 else C['red']
        ctk.CTkLabel(
            inner,
            text=f"Saldo: {fmt_moeda(cat.get('saldo', 0))}",
            font=ctk.CTkFont(size=13, weight='bold'),
            text_color=saldo_cor
        ).pack(anchor='w', pady=(8, 4))

        # Entradas / Saídas
        row_es = ctk.CTkFrame(inner, fg_color='transparent')
        row_es.pack(fill='x')

        ctk.CTkLabel(
            row_es, text=f"↑ {fmt_moeda(cat.get('total_entrada', 0))}",
            font=ctk.CTkFont(size=11), text_color=C['green']
        ).pack(side='left')

        ctk.CTkLabel(
            row_es, text=f"  ↓ {fmt_moeda(cat.get('total_saida', 0))}",
            font=ctk.CTkFont(size=11), text_color=C['red']
        ).pack(side='left')

        ctk.CTkLabel(
            row_es,
            text=f"  · {cat.get('qtd_transacoes', 0)} trans.",
            font=ctk.CTkFont(size=11), text_color=C['text2']
        ).pack(side='left')

        # Progress bar (se tiver meta)
        if cat.get('meta_valor') and cat['meta_valor'] > 0:
            pct = min(cat.get('percentual_quitado', 0), 100)
            ctk.CTkLabel(
                inner,
                text=f"Meta: {fmt_moeda(cat['meta_valor'])} · {pct:.1f}%",
                font=ctk.CTkFont(size=11), text_color=C['text2']
            ).pack(anchor='w', pady=(6, 2))
            ctk.CTkProgressBar(
                inner, height=6,
                progress_color=C['green'] if pct >= 100 else C['blue'],
                fg_color=C['input']
            ).pack(fill='x')

        # Tipo badge
        tipo_txt = {'emprestimo':'💸 Empréstimo', 'quitacao':'✅ Quitação', 'organizacao':'📁 Organização'}.get(cat.get('tipo'), cat.get('tipo', ''))
        ctk.CTkLabel(
            inner, text=tipo_txt,
            font=ctk.CTkFont(size=10), text_color=cor
        ).pack(anchor='e', pady=(6, 0))

    def _modal_categoria(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Nova Categoria")
        modal.geometry("420x440")
        modal.configure(fg_color=C['card'])
        modal.transient(self.winfo_toplevel())
        modal.grab_set()

        ctk.CTkLabel(
            modal, text="Nova Categoria",
            font=ctk.CTkFont(size=17, weight='bold'),
            text_color=C['text']
        ).pack(padx=24, pady=(20, 4), anchor='w')

        lbl_err = ctk.CTkLabel(
            modal, text="",
            font=ctk.CTkFont(size=12), text_color=C['red']
        )
        lbl_err.pack(padx=24, anchor='w')

        cont = ctk.CTkScrollableFrame(modal, fg_color='transparent')
        cont.pack(fill='both', expand=True, padx=24, pady=8)

        # Nome
        ctk.CTkLabel(cont, text="Nome", font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        entry_nome = ctk.CTkEntry(cont, fg_color=C['input'], border_color=C['border'], text_color=C['text'], height=38)
        entry_nome.pack(fill='x', pady=(4, 10))

        # Tipo
        ctk.CTkLabel(cont, text="Tipo", font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        combo_tipo = ctk.CTkComboBox(
            cont, values=['organizacao', 'quitacao', 'emprestimo'],
            fg_color=C['input'], border_color=C['border'], text_color=C['text'], height=38
        )
        combo_tipo.set('organizacao')
        combo_tipo.pack(fill='x', pady=(4, 10))

        # Meta
        ctk.CTkLabel(cont, text="Meta / Valor Total (R$)", font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        entry_meta = ctk.CTkEntry(cont, placeholder_text="0.00", fg_color=C['input'], border_color=C['border'], text_color=C['text'], height=38)
        entry_meta.pack(fill='x', pady=(4, 10))

        # Descrição
        ctk.CTkLabel(cont, text="Descrição", font=ctk.CTkFont(size=12), text_color=C['text2']).pack(anchor='w')
        entry_desc = ctk.CTkEntry(cont, fg_color=C['input'], border_color=C['border'], text_color=C['text'], height=38)
        entry_desc.pack(fill='x', pady=(4, 10))

        def _salvar():
            nome = entry_nome.get().strip()
            if not nome:
                lbl_err.configure(text="❌ Nome é obrigatório")
                return

            dados = {
                'nome': nome,
                'tipo': combo_tipo.get(),
                'descricao': entry_desc.get().strip()
            }
            try:
                meta = entry_meta.get().strip()
                if meta:
                    dados['meta_valor'] = float(meta.replace(',', '.'))
            except Exception:
                pass

            def _enviar():
                ok, msg = sync.adicionar_categoria(dados)
                def _fim():
                    if ok:
                        modal.destroy()
                        self._carregar()
                    else:
                        lbl_err.configure(text=f"❌ {msg}")
                self.after(0, _fim)

            threading.Thread(target=_enviar, daemon=True).start()

        frame_btns = ctk.CTkFrame(modal, fg_color='transparent')
        frame_btns.pack(fill='x', padx=24, pady=16)

        ctk.CTkButton(frame_btns, text="Cancelar", command=modal.destroy,
                      fg_color=C['input'], hover_color=C['border'], text_color=C['text2'], height=40
                      ).pack(side='left', expand=True, padx=(0,8))

        ctk.CTkButton(frame_btns, text="💾 Salvar", command=_salvar,
                      fg_color=C['blue'], hover_color='#388bfd', text_color='#fff', height=40,
                      font=ctk.CTkFont(size=13, weight='bold')
                      ).pack(side='right', expand=True)

    def _excluir(self, cid: str):
        from tkinter import messagebox
        if not messagebox.askyesno("Confirmar", "Excluir esta categoria?"):
            return

        def _del():
            resp = conexao.delete(f'/api/categorias/{cid}')
            if resp and resp.get('sucesso'):
                self.after(0, self._carregar)

        threading.Thread(target=_del, daemon=True).start()

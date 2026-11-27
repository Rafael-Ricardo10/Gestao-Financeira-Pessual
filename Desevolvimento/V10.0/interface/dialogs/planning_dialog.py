"""
Planejamento financeiro: simulação de gastos por plano (não cria transações).

O período (dias/semanas/meses/anos) é escolhido NO PLANO. Cada categoria do
plano tem preço, quantidade opcional (kg, litros, unidades...) e frequência;
o sistema multiplica tudo e mostra o total de cada categoria e do plano.
"""
from datetime import timedelta

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox,
    QDateEdit, QMessageBox, QInputDialog, QSplitter, QWidget, QHeaderView,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QDate, QLocale

from modulos import planejamento as pl

LOCALE_BR = QLocale(QLocale.Portuguese, QLocale.Brazil)


def brl(v):
    s = f'{(v or 0):,.2f}'
    return 'R$ ' + s.replace(',', 'X').replace('.', ',').replace('X', '.')


def num(v, dec=3):
    s = f'{(v or 0):.{dec}f}'
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return (s or '0').replace('.', ',')


ROTULO_FREQ = dict(pl.FREQUENCIAS)
ROTULO_PERIODO = {'dia': 'dia(s)', 'semana': 'semana(s)',
                  'mes': 'mês(es)', 'ano': 'ano(s)'}


def _rep_texto(freq, per):
    r = pl.repeticoes(freq, per)
    if freq == 'dia':
        return f'{num(r, 0)} dia(s)'
    if freq == 'semana':
        return f'{num(r, 2)} semana(s)'
    if freq == 'mes':
        return f'{num(r, 2)} mês(es)'
    return '1 vez'


# ══════════════════════════════════════════════════════════════
# Diálogo de categoria
# ══════════════════════════════════════════════════════════════

class PlanCategoryDialog(QDialog):

    def __init__(self, parent, per, dados=None):
        super().__init__(parent)
        self.per = per
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)
        self.setWindowTitle('Categoria do plano' if not dados
                            else 'Editar categoria do plano')
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        dica = QLabel(
            'O período vem do plano. Informe o preço de 1 unidade (ou 1 kg, '
            '1 litro...). Se preencher a quantidade, ela também multiplica.')
        dica.setWordWrap(True)
        dica.setStyleSheet('color: #2196F3; font-style: italic;')
        lay.addWidget(dica)

        form = QFormLayout()
        self.nome = QLineEdit()
        self.nome.setPlaceholderText('Ex.: Carne de frango')
        self.preco = QDoubleSpinBox()
        self.preco.setLocale(LOCALE_BR)
        self.preco.setRange(0, 99999999)
        self.preco.setDecimals(2)
        self.preco.setPrefix('R$ ')
        self.qtd = QDoubleSpinBox()
        self.qtd.setLocale(LOCALE_BR)
        self.qtd.setRange(0, 9999999)
        self.qtd.setDecimals(3)
        self.qtd.setSpecialValueText('Não usar (×1)')
        self.unidade = QComboBox()
        self.unidade.setEditable(True)
        self.unidade.addItems(pl.UNIDADES_MEDIDA)
        self.freq = QComboBox()
        for k, rot in pl.FREQUENCIAS:
            self.freq.addItem(rot, k)
        form.addRow('Nome:', self.nome)
        form.addRow('Preço de 1 unidade/kg/litro:', self.preco)
        form.addRow('Quantidade (opcional):', self.qtd)
        form.addRow('Unidade de medida:', self.unidade)
        form.addRow('Frequência:', self.freq)
        lay.addLayout(form)

        self.l_previa = QLabel()
        self.l_previa.setWordWrap(True)
        self.l_previa.setStyleSheet('font-weight: bold; padding: 6px;')
        lay.addWidget(self.l_previa)

        row = QHBoxLayout()
        ok = QPushButton('Salvar')
        ok.clicked.connect(self._salvar)
        cancel = QPushButton('Cancelar')
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

        if dados:
            self.nome.setText(dados['name'])
            self.preco.setValue(dados['unit_price'] or 0)
            self.qtd.setValue(dados['quantity'] or 0)
            self.unidade.setCurrentText(dados['unit'] or 'unidade')
            i = self.freq.findData(dados['frequency'])
            self.freq.setCurrentIndex(max(0, i))
        for w in (self.preco, self.qtd):
            w.valueChanged.connect(self._previa)
        self.freq.currentIndexChanged.connect(self._previa)
        self._previa()
        self.apply_theme()

    def _previa(self):
        f = self.freq.currentData()
        v = pl.custo(self.preco.value(), self.qtd.value(), f, self.per)
        q = (f' × {num(self.qtd.value())} {self.unidade.currentText()}'
             if self.qtd.value() > 0 else '')
        self.l_previa.setText(
            f'{brl(self.preco.value())}{q} × {_rep_texto(f, self.per)}'
            f'  =  {brl(v)}')

    def _salvar(self):
        if not self.nome.text().strip():
            QMessageBox.warning(self, 'Aviso', 'Informe o nome da categoria.')
            return
        self.accept()

    def valores(self):
        return (self.nome.text().strip(), round(self.preco.value(), 2),
                round(self.qtd.value(), 3),
                self.unidade.currentText().strip(), self.freq.currentData())

    def apply_theme(self):
        _tema(self, self.is_dark_mode)


# ══════════════════════════════════════════════════════════════
# Diálogo principal
# ══════════════════════════════════════════════════════════════

class PlanningDialog(QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.db = parent.db_connection
        self.user_id = parent.user_id
        self.is_dark_mode = getattr(parent, 'is_dark_mode', False)
        self.plan_id = None
        self._carregando = False
        self.setWindowTitle('🧮 Planejamento Financeiro')
        self.setMinimumSize(1050, 640)
        pl.criar_tabelas(self.db)
        self._build()
        self.apply_theme()
        self._carregar_lista()

    # ── construção ─────────────────────────────────────────

    def _build(self):
        raiz = QVBoxLayout(self)
        topo = QLabel(
            'Planeje seus gastos sem lançar transações: crie um plano, '
            'escolha o período e adicione as categorias com preço e '
            'quantidade. O sistema calcula quanto você vai gastar.')
        topo.setWordWrap(True)
        topo.setStyleSheet('color: #2196F3; font-style: italic;')
        raiz.addWidget(topo)

        split = QSplitter(Qt.Horizontal)
        raiz.addWidget(split, 1)

        # esquerda: planos
        esq = QWidget()
        le = QVBoxLayout(esq)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(QLabel('Meus planos:'))
        self.lista = QListWidget()
        self.lista.currentItemChanged.connect(self._ao_escolher_plano)
        le.addWidget(self.lista, 1)
        for txt, fn in (('Novo plano', self.novo_plano),
                        ('Duplicar', self.duplicar),
                        ('Excluir plano', self.excluir_plano)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            le.addWidget(b)
        split.addWidget(esq)

        # direita: plano atual
        self.direita = QWidget()
        ld = QVBoxLayout(self.direita)
        ld.setContentsMargins(0, 0, 0, 0)

        g = QGroupBox('Plano')
        f = QFormLayout(g)
        self.e_nome = QLineEdit()
        self.e_nome.editingFinished.connect(self._salvar_cabecalho)
        self.e_inicio = QDateEdit(QDate.currentDate())
        self.e_inicio.setCalendarPopup(True)
        self.e_inicio.setDisplayFormat('dd/MM/yyyy')
        self.e_inicio.dateChanged.connect(self._salvar_cabecalho)
        self.e_qtd = QSpinBox()
        self.e_qtd.setRange(1, 9999)
        self.e_qtd.valueChanged.connect(self._salvar_cabecalho)
        self.e_unid = QComboBox()
        for k, rot in pl.UNIDADES_PERIODO:
            self.e_unid.addItem(rot, k)
        self.e_unid.currentIndexChanged.connect(self._salvar_cabecalho)
        per_row = QHBoxLayout()
        per_row.addWidget(self.e_qtd)
        per_row.addWidget(self.e_unid)
        per_row.addStretch()
        self.e_notas = QLineEdit()
        self.e_notas.setPlaceholderText('Observações (opcional)')
        self.e_notas.editingFinished.connect(self._salvar_cabecalho)
        self.l_periodo = QLabel()
        self.l_periodo.setStyleSheet('font-weight: bold; color: #16a085;')
        f.addRow('Nome do plano:', self.e_nome)
        f.addRow('Início:', self.e_inicio)
        f.addRow('Duração:', per_row)
        f.addRow('', self.l_periodo)
        f.addRow('Notas:', self.e_notas)
        ld.addWidget(g)

        ld.addWidget(QLabel('Categorias do plano (clique duas vezes para '
                            'editar; selecione várias para somar):'))
        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels([
            'Categoria', 'Preço unit.', 'Quantidade', 'Frequência',
            'Cálculo', 'Total', '% do plano'])
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.doubleClicked.connect(self.editar_categoria)
        self.tabela.itemSelectionChanged.connect(self._atualizar_selecao)
        ld.addWidget(self.tabela, 1)

        bl = QHBoxLayout()
        for txt, fn in (('Adicionar categoria', self.add_categoria),
                        ('Editar', self.editar_categoria),
                        ('Excluir categoria', self.excluir_categoria)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            bl.addWidget(b)
        bl.addStretch()
        ld.addLayout(bl)

        self.l_total = QLabel()
        self.l_total.setStyleSheet('font-size: 18px; font-weight: bold;')
        self.l_medias = QLabel()
        self.l_sel = QLabel()
        self.l_sel.setStyleSheet('color: #f39c12; font-weight: bold;')
        ld.addWidget(self.l_total)
        ld.addWidget(self.l_medias)
        ld.addWidget(self.l_sel)

        split.addWidget(self.direita)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)

        fechar = QPushButton('Fechar')
        fechar.clicked.connect(self.accept)
        r = QHBoxLayout()
        r.addStretch()
        r.addWidget(fechar)
        raiz.addLayout(r)
        self.direita.setEnabled(False)

    # ── planos ─────────────────────────────────────────────

    def _carregar_lista(self, selecionar=None):
        self.lista.blockSignals(True)
        self.lista.clear()
        for p in pl.listar_planos(self.db, self.user_id):
            r = pl.resumo(p, pl.listar_categorias(self.db, p['id']))
            it = QListWidgetItem(
                f"{p['name']}\n{p['period_amount']} "
                f"{ROTULO_PERIODO.get(p['period_unit'], '')} · "
                f"{brl(r['total'])}")
            it.setData(Qt.UserRole, p['id'])
            self.lista.addItem(it)
            if selecionar == p['id']:
                self.lista.setCurrentItem(it)
        self.lista.blockSignals(False)
        if selecionar is None and self.lista.count():
            self.lista.setCurrentRow(0)
        if self.lista.count() == 0:
            self.plan_id = None
            self.direita.setEnabled(False)
            self.tabela.setRowCount(0)
            self.l_total.setText('Crie um plano para começar.')
            self.l_medias.setText('')
            self.l_sel.setText('')
        else:
            self._ao_escolher_plano(self.lista.currentItem(), None)

    def _ao_escolher_plano(self, atual, _antes):
        if atual is None:
            return
        self.plan_id = atual.data(Qt.UserRole)
        p = pl.obter_plano(self.db, self.plan_id)
        if not p:
            return
        self._carregando = True
        self.e_nome.setText(p['name'])
        self.e_inicio.setDate(QDate.fromString(p['start_date'][:10],
                                               'yyyy-MM-dd'))
        self.e_qtd.setValue(int(p['period_amount'] or 1))
        self.e_unid.setCurrentIndex(
            max(0, self.e_unid.findData(p['period_unit'])))
        self.e_notas.setText(p['notes'] or '')
        self._carregando = False
        self.direita.setEnabled(True)
        self._recalcular()

    def _salvar_cabecalho(self, *_):
        if self._carregando or self.plan_id is None:
            return
        nome = self.e_nome.text().strip()
        if not nome:
            p = pl.obter_plano(self.db, self.plan_id)
            self.e_nome.setText(p['name'])
            return
        pl.atualizar_plano(
            self.db, self.plan_id, nome, self.e_inicio.date().toPyDate(),
            self.e_qtd.value(), self.e_unid.currentData(),
            self.e_notas.text().strip())
        self._recalcular()
        self._atualizar_item_lista()

    def _atualizar_item_lista(self):
        it = self.lista.currentItem()
        if it is None or self.plan_id is None:
            return
        p = pl.obter_plano(self.db, self.plan_id)
        r = pl.resumo(p, pl.listar_categorias(self.db, self.plan_id))
        it.setText(f"{p['name']}\n{p['period_amount']} "
                   f"{ROTULO_PERIODO.get(p['period_unit'], '')} · "
                   f"{brl(r['total'])}")

    def novo_plano(self):
        nome, ok = QInputDialog.getText(self, 'Novo plano', 'Nome do plano:')
        if not ok or not nome.strip():
            return
        pid = pl.criar_plano(self.db, self.user_id, nome)
        self._carregar_lista(pid)

    def duplicar(self):
        if self.plan_id is None:
            return
        p = pl.obter_plano(self.db, self.plan_id)
        nome, ok = QInputDialog.getText(
            self, 'Duplicar plano', 'Nome da cópia:', QLineEdit.Normal,
            f"{p['name']} (cópia)")
        if not ok or not nome.strip():
            return
        pid = pl.duplicar_plano(self.db, self.user_id, self.plan_id, nome)
        self._carregar_lista(pid)

    def excluir_plano(self):
        if self.plan_id is None:
            return
        p = pl.obter_plano(self.db, self.plan_id)
        if QMessageBox.question(
                self, 'Excluir plano',
                f"Excluir o plano '{p['name']}' e todas as suas "
                f"categorias?\n\nIsso não afeta suas transações.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        pl.excluir_plano(self.db, self.plan_id)
        self.plan_id = None
        self._carregar_lista()

    # ── categorias ─────────────────────────────────────────

    def _periodo_atual(self):
        p = pl.obter_plano(self.db, self.plan_id)
        return pl.periodo(p['start_date'], p['period_amount'],
                          p['period_unit'])

    def add_categoria(self):
        if self.plan_id is None:
            return
        d = PlanCategoryDialog(self, self._periodo_atual())
        if d.exec_() == QDialog.Accepted:
            nome, preco, qtd, un, fr = d.valores()
            pl.salvar_categoria(self.db, self.plan_id, nome, preco, qtd,
                                un, fr)
            self._recalcular()
            self._atualizar_item_lista()

    def _categoria_selecionada(self):
        r = self.tabela.currentRow()
        if r < 0:
            return None
        return self.tabela.item(r, 0).data(Qt.UserRole)

    def editar_categoria(self, *_):
        cid = self._categoria_selecionada()
        if cid is None:
            QMessageBox.warning(self, 'Aviso',
                                'Selecione uma categoria para editar.')
            return
        c = self.db.execute('SELECT * FROM plan_categories WHERE id=?',
                            (cid,)).fetchone()
        if not c:
            return
        d = PlanCategoryDialog(self, self._periodo_atual(), c)
        if d.exec_() == QDialog.Accepted:
            nome, preco, qtd, un, fr = d.valores()
            pl.salvar_categoria(self.db, self.plan_id, nome, preco, qtd,
                                un, fr, cat_id=cid)
            self._recalcular()
            self._atualizar_item_lista()

    def excluir_categoria(self):
        ids = sorted({self.tabela.item(i.row(), 0).data(Qt.UserRole)
                      for i in self.tabela.selectedIndexes()})
        if not ids:
            QMessageBox.warning(self, 'Aviso',
                                'Selecione uma categoria para excluir.')
            return
        if QMessageBox.question(
                self, 'Excluir categoria',
                f'Excluir {len(ids)} categoria(s) do plano?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        for cid in ids:
            pl.excluir_categoria(self.db, cid)
        self._recalcular()
        self._atualizar_item_lista()

    # ── cálculo / tela ─────────────────────────────────────

    def _recalcular(self):
        if self.plan_id is None:
            return
        p = pl.obter_plano(self.db, self.plan_id)
        cats = pl.listar_categorias(self.db, self.plan_id)
        r = pl.resumo(p, cats)
        per = r['periodo']
        fim = per['fim'] - timedelta(days=1)
        self.l_periodo.setText(
            f"De {per['inicio'].strftime('%d/%m/%Y')} até "
            f"{fim.strftime('%d/%m/%Y')} · {per['dias']} dias")

        valores = {l['id']: l for l in r['linhas']}
        t = self.tabela
        t.setUpdatesEnabled(False)
        try:
            t.setRowCount(len(cats))
            h = t.horizontalHeader()
            for col in (0, 1, 2, 3, 5, 6):
                h.setSectionResizeMode(col, QHeaderView.Fixed)
            for col, w in ((0, 180), (1, 105), (2, 110), (3, 115),
                           (5, 115), (6, 85)):
                t.setColumnWidth(col, w)
            h.setSectionResizeMode(4, QHeaderView.Stretch)
            for i, c in enumerate(cats):
                lin = valores[c['id']]
                qtd = c['quantity'] or 0
                un = c['unit'] or ''
                q_txt = f'{num(qtd)} {un}'.strip() if qtd > 0 else '—'
                q_calc = f' × {num(qtd)} {un}' if qtd > 0 else ''
                calc = (f"{brl(c['unit_price'])}{q_calc} × "
                        f"{_rep_texto(c['frequency'], per)}")
                cel = [c['name'], brl(c['unit_price']), q_txt,
                       ROTULO_FREQ.get(c['frequency'], ''), calc,
                       brl(lin['valor']), f"{lin['pct']:.1f}%".replace(
                           '.', ',')]
                for j, txt in enumerate(cel):
                    it = QTableWidgetItem(txt)
                    if j in (1, 2, 5, 6):
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if j == 5:
                        f = it.font()
                        f.setBold(True)
                        it.setFont(f)
                    if j == 0:
                        it.setData(Qt.UserRole, c['id'])
                    t.setItem(i, j, it)
        finally:
            t.setUpdatesEnabled(True)

        n = len(cats)
        self.l_total.setText(
            f"Total do plano: {brl(r['total'])}   "
            f"({n} categoria{'s' if n != 1 else ''})")
        self.l_medias.setText(
            f"Média: {brl(r['por_dia'])} por dia  ·  "
            f"{brl(r['por_semana'])} por semana  ·  "
            f"{brl(r['por_mes'])} por mês")
        self._valores = {c['id']: valores[c['id']]['valor'] for c in cats}
        self._atualizar_selecao()

    def _atualizar_selecao(self):
        ids = {self.tabela.item(i.row(), 0).data(Qt.UserRole)
               for i in self.tabela.selectedIndexes()}
        if len(ids) >= 1 and hasattr(self, '_valores'):
            soma = sum(self._valores.get(i, 0) for i in ids)
            self.l_sel.setText(
                f"Selecionadas ({len(ids)}): {brl(soma)}")
        else:
            self.l_sel.setText('')

    def apply_theme(self):
        _tema(self, self.is_dark_mode)


def _tema(dlg, dark):
    if dark:
        dlg.setStyleSheet("""
            QDialog { background-color: #1e272e; color: #ecf0f1; }
            QLabel { color: #ecf0f1; }
            QGroupBox { border: 1px solid #4b6584; margin-top: 10px;
                        padding-top: 10px; color: #ecf0f1; }
            QListWidget, QTableWidget { background: #2d3436; color: #ecf0f1;
                        border: 1px solid #4b6584;
                        gridline-color: #4b6584; }
            QHeaderView::section { background: #34495e; color: #ecf0f1;
                        padding: 4px; border: 1px solid #4b6584; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {
                        background: #2d3436; color: #ecf0f1;
                        border: 1px solid #4b6584; padding: 4px; }
            QPushButton { background: #3498db; color: white;
                        border-radius: 4px; padding: 7px 14px;
                        font-weight: bold; }
            QPushButton:hover { background: #2980b9; }
        """)
    else:
        dlg.setStyleSheet("""
            QGroupBox { margin-top: 10px; padding-top: 10px; }
            QPushButton { background: #4CAF50; color: white;
                        border-radius: 4px; padding: 7px 14px;
                        font-weight: bold; }
            QPushButton:hover { background: #45a049; }
        """)

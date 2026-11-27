"""
Diálogo de Análise de Tendências
Detecta padrões de alta/baixa baseado em histórico real
Filtros por categoria e descrição
"""
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas
)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QGroupBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QFrame, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class TrendsDialog(QDialog):
    """
    Diálogo de análise de tendências financeiras.
    Filtros por categoria, descrição e tipo de transação.
    Detecta padrões de alta/baixa automaticamente.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('📈 Análise de Tendências')
        self.setMinimumSize(950, 700)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )
        self.db  = parent.db_connection
        self.uid = parent.user_id

        self.current_result = {}

        self._build_ui()
        self._load_filter_options()
        self.generate_analysis()
        self.apply_theme()

    # ══════════════════════════════════════════════════════
    # INTERFACE
    # ══════════════════════════════════════════════════════

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout(self)

        # ── Cabeçalho ─────────────────────────────────────
        header = QHBoxLayout()
        title  = QLabel('📈 Análise de Tendências')
        title.setStyleSheet(
            'font-size: 18px; font-weight: bold;'
        )
        header.addWidget(title)

        badge = QLabel('📊 Análise Estatística')
        badge.setStyleSheet(
            'background-color: #3498db; color: white;'
            'padding: 4px 8px; border-radius: 10px;'
            'font-size: 11px; font-weight: bold;'
        )
        header.addWidget(badge)
        header.addStretch()
        layout.addLayout(header)

        # ── Filtros ───────────────────────────────────────
        filters_group  = QGroupBox('🔍 Filtros de Análise')
        filters_layout = QHBoxLayout()

        filters_layout.addWidget(QLabel('Período:'))
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            '3 meses', '6 meses', '12 meses', 'Todo histórico'
        ])
        self.period_combo.setCurrentIndex(1)
        filters_layout.addWidget(self.period_combo)

        filters_layout.addWidget(QLabel('Tipo:'))
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            'Entrada e Saída', 'Apenas Entrada', 'Apenas Saída'
        ])
        filters_layout.addWidget(self.type_combo)

        filters_layout.addWidget(QLabel('Categoria:'))
        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(180)
        filters_layout.addWidget(self.category_combo)

        filters_layout.addWidget(QLabel('Descrição:'))
        self.description_combo = QComboBox()
        self.description_combo.setEditable(True)
        self.description_combo.setMinimumWidth(180)
        self.description_combo.lineEdit().setPlaceholderText(
            'Buscar por descrição...'
        )
        filters_layout.addWidget(self.description_combo)

        self.analyze_btn = QPushButton('🔍 Analisar')
        self.analyze_btn.clicked.connect(self.generate_analysis)
        self.analyze_btn.setMinimumWidth(100)
        filters_layout.addWidget(self.analyze_btn)

        filters_group.setLayout(filters_layout)
        layout.addWidget(filters_group)

        # ── Cards de resumo ───────────────────────────────
        self.summary_layout = QHBoxLayout()
        layout.addLayout(self.summary_layout)

        # ── Abas ──────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(
            self._build_chart_tab(), '📊 Gráficos'
        )
        self.tabs.addTab(
            self._build_details_tab(), '📋 Detalhes'
        )
        self.tabs.addTab(
            self._build_insights_tab(), '💡 Insights'
        )
        self.tabs.addTab(
            self._build_categories_tab(), '📂 Por Categoria'
        )
        layout.addWidget(self.tabs)

        # ── Botões rodapé ─────────────────────────────────
        btn_layout = QHBoxLayout()
        self.export_btn = QPushButton('📋 Exportar Análise')
        self.export_btn.clicked.connect(self.export_analysis)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addStretch()

        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _build_chart_tab(self) -> QWidget:
        """Aba de gráficos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        chart_selector = QHBoxLayout()
        chart_selector.addWidget(QLabel('Visualização:'))
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems([
            'Barras (Entrada vs Saída)',
            'Linha (Evolução do Saldo)',
            'Linha (Tendências)',
            'Área (Acumulado)',
        ])
        self.chart_type_combo.currentIndexChanged.connect(
            self._update_chart
        )
        chart_selector.addWidget(self.chart_type_combo)
        chart_selector.addStretch()
        layout.addLayout(chart_selector)

        self.figure = plt.figure(figsize=(9, 4), dpi=95)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(280)
        layout.addWidget(self.canvas)

        self.trend_legend = QLabel()
        self.trend_legend.setAlignment(Qt.AlignCenter)
        self.trend_legend.setWordWrap(True)
        self.trend_legend.setStyleSheet(
            'padding: 8px; border-radius: 4px;'
            'font-size: 12px; font-weight: bold;'
        )
        layout.addWidget(self.trend_legend)

        return widget

    def _build_details_tab(self) -> QWidget:
        """Aba de detalhes numéricos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        monthly_group  = QGroupBox('📅 Dados Mensais')
        monthly_layout = QVBoxLayout()

        self.monthly_table = QTableWidget()
        self.monthly_table.setColumnCount(7)
        self.monthly_table.setHorizontalHeaderLabels([
            'Mês', 'Entrada', 'Saída', 'Saldo',
            'Var. Entrada %', 'Var. Saída %', 'Tendência'
        ])
        self.monthly_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.monthly_table.horizontalHeader(
        ).setStretchLastSection(True)
        monthly_layout.addWidget(self.monthly_table)
        monthly_group.setLayout(monthly_layout)
        layout.addWidget(monthly_group)

        stats_group  = QGroupBox('📊 Estatísticas do Período')
        stats_layout = QHBoxLayout()

        self.stats_income_text  = QTextEdit()
        self.stats_expense_text = QTextEdit()
        self.stats_balance_text = QTextEdit()

        for te in [
            self.stats_income_text,
            self.stats_expense_text,
            self.stats_balance_text
        ]:
            te.setReadOnly(True)
            te.setMaximumHeight(120)

        stats_layout.addWidget(self.stats_income_text)
        stats_layout.addWidget(self.stats_expense_text)
        stats_layout.addWidget(self.stats_balance_text)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        return widget

    def _build_insights_tab(self) -> QWidget:
        """Aba de insights automáticos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        hint_label = QLabel(
            '💡 Insights gerados automaticamente com base '
            'no seu histórico financeiro.'
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet(
            'color: #3498db; font-style: italic; padding: 5px;'
        )
        layout.addWidget(hint_label)

        self.insights_text = QTextEdit()
        self.insights_text.setReadOnly(True)
        layout.addWidget(self.insights_text)

        anomaly_group  = QGroupBox('🔍 Anomalias Detectadas')
        anomaly_layout = QVBoxLayout()

        self.anomaly_table = QTableWidget()
        self.anomaly_table.setColumnCount(4)
        self.anomaly_table.setHorizontalHeaderLabels([
            'Mês', 'Tipo', 'Valor', 'Desvio (Z-Score)'
        ])
        self.anomaly_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.anomaly_table.setMaximumHeight(150)
        self.anomaly_table.horizontalHeader(
        ).setStretchLastSection(True)
        anomaly_layout.addWidget(self.anomaly_table)
        anomaly_group.setLayout(anomaly_layout)
        layout.addWidget(anomaly_group)

        return widget

    def _build_categories_tab(self) -> QWidget:
        """Aba de tendências por categoria"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        hint = QLabel(
            '📂 Resumo das tendências de todas as categorias.'
        )
        hint.setStyleSheet(
            'color: #7f8c8d; font-style: italic;'
        )
        layout.addWidget(hint)

        self.categories_trend_table = QTableWidget()
        self.categories_trend_table.setColumnCount(5)
        self.categories_trend_table.setHorizontalHeaderLabels([
            'Categoria', 'Média Saída', 'Média Entrada',
            'Tendência', 'Situação'
        ])
        self.categories_trend_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.categories_trend_table.horizontalHeader(
        ).setStretchLastSection(True)
        layout.addWidget(self.categories_trend_table)

        return widget

    # ══════════════════════════════════════════════════════
    # FILTROS
    # ══════════════════════════════════════════════════════

    def _load_filter_options(self):
        """Carrega opções nos combos de filtro"""
        self.category_combo.clear()
        self.category_combo.addItem('Todas as categorias', None)

        categories = self.db.execute(
            '''SELECT id, name FROM categories
               WHERE user_id = ? ORDER BY name''',
            (self.uid,)
        ).fetchall()
        for cat in categories:
            self.category_combo.addItem(cat['name'], cat['id'])

        self.description_combo.clear()
        self.description_combo.addItem('Todas as descrições')

        descriptions = self.db.execute(
            '''SELECT DISTINCT description FROM transactions
               WHERE user_id = ?
               ORDER BY description LIMIT 100''',
            (self.uid,)
        ).fetchall()
        for desc in descriptions:
            if desc['description']:
                self.description_combo.addItem(
                    desc['description']
                )

    # ══════════════════════════════════════════════════════
    # CÁLCULOS ESTATÍSTICOS
    # ══════════════════════════════════════════════════════

    def _get_direction(
        self, values: list, reverse: bool = False
    ) -> dict:
        """
        Determina a direção da tendência.

        Args:
            values  : Lista de valores numéricos
            reverse : Se True, alta é negativo (ex: saídas)

        Returns:
            Dicionário com label, emoji e cor da tendência
        """
        if len(values) < 2:
            return {
                'label': 'Estável', 'emoji': '➡️',
                'color': '#7f8c8d'
            }

        slope = np.polyfit(np.arange(len(values)), values, 1)[0]
        avg   = np.mean(values) if np.mean(values) != 0 else 1
        pct   = (slope / abs(avg)) * 100

        if pct > 5:
            if reverse:
                return {
                    'label': 'Alta ⚠️', 'emoji': '📈',
                    'color': '#e74c3c'
                }
            return {
                'label': 'Alta', 'emoji': '📈',
                'color': '#27ae60'
            }
        elif pct < -5:
            if reverse:
                return {
                    'label': 'Queda ✅', 'emoji': '📉',
                    'color': '#27ae60'
                }
            return {
                'label': 'Queda', 'emoji': '📉',
                'color': '#e74c3c'
            }
        else:
            return {
                'label': 'Estável', 'emoji': '➡️',
                'color': '#7f8c8d'
            }

    def _detect_anomalies(
        self, values: list, labels: list,
        trans_type: str, threshold: float = 2.0
    ) -> list:
        """
        Detecta anomalias usando Z-Score.

        Args:
            values     : Lista de valores
            labels     : Rótulos dos meses
            trans_type : Tipo de transação
            threshold  : Limiar do Z-Score

        Returns:
            Lista de anomalias detectadas
        """
        if len(values) < 3:
            return []

        arr    = np.array(values, dtype=float)
        mean   = np.mean(arr)
        std    = np.std(arr)

        if std == 0:
            return []

        anomalies = []
        for i, (val, label) in enumerate(zip(values, labels)):
            z_score = abs((val - mean) / std)
            if z_score >= threshold:
                anomalies.append({
                    'month':      label,
                    'label':      label,
                    'value':      val,
                    'z_score':    round(z_score, 2),
                    'type':       (
                        'alto' if val > mean else 'baixo'
                    ),
                    'trans_type': trans_type,
                })
        return anomalies

    def _generate_insights(self, r: dict) -> list:
        """
        Gera insights automáticos baseados nos dados.

        Args:
            r: Dicionário com resultado da análise

        Returns:
            Lista de insights com tipo, emoji e mensagem
        """
        insights    = []
        avg_income  = r.get('avg_income',  0)
        avg_expense = r.get('avg_expense', 0)
        avg_balance = r.get('avg_balance', 0)
        income_dir  = r.get('income_direction',  {})
        expense_dir = r.get('expense_direction', {})

        # Saldo médio
        if avg_balance > 0:
            insights.append({
                'type':    'positive',
                'emoji':   '✅',
                'message': (
                    f'Saldo médio positivo de '
                    f'R$ {avg_balance:,.2f} no período.'
                )
            })
        else:
            insights.append({
                'type':    'critical',
                'emoji':   '🚨',
                'message': (
                    f'Saldo médio negativo de '
                    f'R$ {avg_balance:,.2f}. '
                    f'Atenção aos gastos!'
                )
            })

        # Tendência de saídas
        if expense_dir.get('label', '').startswith('Alta'):
            insights.append({
                'type':    'warning',
                'emoji':   '⚠️',
                'message': (
                    'Gastos em tendência de alta. '
                    'Revise suas despesas.'
                )
            })
        elif expense_dir.get('label', '').startswith('Queda'):
            insights.append({
                'type':    'positive',
                'emoji':   '✅',
                'message': (
                    'Gastos em queda. '
                    'Continue controlando suas despesas!'
                )
            })

        # Tendência de entradas
        if income_dir.get('label', '').startswith('Alta'):
            insights.append({
                'type':    'positive',
                'emoji':   '📈',
                'message': (
                    'Receitas em tendência de crescimento!'
                )
            })
        elif income_dir.get('label', '').startswith('Queda'):
            insights.append({
                'type':    'attention',
                'emoji':   '⚠️',
                'message': (
                    'Receitas em queda. '
                    'Atenção ao seu fluxo de entrada.'
                )
            })

        # Proporção gastos/renda
        if avg_income > 0:
            ratio = avg_expense / avg_income
            if ratio > 0.9:
                insights.append({
                    'type':    'critical',
                    'emoji':   '🚨',
                    'message': (
                        f'Gastos representam '
                        f'{ratio*100:.0f}% da renda. '
                        f'Situação crítica!'
                    )
                })
            elif ratio > 0.7:
                insights.append({
                    'type':    'warning',
                    'emoji':   '⚠️',
                    'message': (
                        f'Gastos representam '
                        f'{ratio*100:.0f}% da renda. '
                        f'Tente reduzir despesas.'
                    )
                })
            else:
                insights.append({
                    'type':    'positive',
                    'emoji':   '✅',
                    'message': (
                        f'Gastos representam '
                        f'{ratio*100:.0f}% da renda. '
                        f'Situação saudável!'
                    )
                })

        # Anomalias
        all_anomalies = (
            r.get('income_anomalies', []) +
            r.get('expense_anomalies', [])
        )
        if all_anomalies:
            insights.append({
                'type':    'info',
                'emoji':   '🔍',
                'message': (
                    f'{len(all_anomalies)} anomalia(s) '
                    f'detectada(s) no período.'
                )
            })

        return insights

    def _analyze_data(
        self,
        months: int,
        category_id,
        trans_type,
        description
    ) -> dict:
        """
        Executa a análise estatística dos dados.

        Args:
            months      : Quantidade de meses a analisar
            category_id : Filtro de categoria (None = todas)
            trans_type  : Filtro de tipo (None = todos)
            description : Filtro de descrição (None = todas)

        Returns:
            Dicionário completo com resultado da análise
        """
        since = (
            datetime.now() - relativedelta(months=months)
        ).strftime('%Y-%m-%d')

        # Montar query dinâmica
        query  = '''
            SELECT
                strftime('%Y-%m', t.date) AS month,
                t.transaction_type,
                SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND t.date >= ?
        '''
        params = [self.uid, since]

        if category_id is not None:
            query  += ' AND t.category_id = ?'
            params.append(category_id)

        if trans_type is not None:
            query  += ' AND t.transaction_type = ?'
            params.append(trans_type)

        if description:
            query  += ' AND LOWER(t.description) LIKE ?'
            params.append(f'%{description.lower()}%')

        query += ' GROUP BY month, t.transaction_type ORDER BY month'

        rows = self.db.execute(query, params).fetchall()

        if not rows:
            return {'has_data': False}

        # Organizar dados por mês
        monthly = {}
        for row in rows:
            m = row['month']
            if m not in monthly:
                monthly[m] = {'entrada': 0.0, 'saida': 0.0}
            monthly[m][row['transaction_type']] = (
                float(row['total'])
            )

        months_list = sorted(monthly.keys())
        labels      = [
            datetime.strptime(m, '%Y-%m').strftime('%b/%Y')
            for m in months_list
        ]
        income_vals  = [monthly[m]['entrada'] for m in months_list]
        expense_vals = [monthly[m]['saida']   for m in months_list]
        balance_vals = [
            monthly[m]['entrada'] - monthly[m]['saida']
            for m in months_list
        ]

        # Variações mês a mês
        def mom_variation(vals):
            result = [0.0]
            for i in range(1, len(vals)):
                if vals[i-1] != 0:
                    result.append(
                        ((vals[i] - vals[i-1]) / vals[i-1]) * 100
                    )
                else:
                    result.append(0.0)
            return result

        income_mom  = mom_variation(income_vals)
        expense_mom = mom_variation(expense_vals)

        # Médias
        avg_income  = float(np.mean(income_vals))  if income_vals  else 0
        avg_expense = float(np.mean(expense_vals)) if expense_vals else 0
        avg_balance = float(np.mean(balance_vals)) if balance_vals else 0

        # Direções
        income_dir  = self._get_direction(income_vals,  reverse=False)
        expense_dir = self._get_direction(expense_vals, reverse=True)
        balance_dir = self._get_direction(balance_vals, reverse=False)

        # Anomalias
        income_anomalies  = self._detect_anomalies(
            income_vals,  labels, 'entrada'
        )
        expense_anomalies = self._detect_anomalies(
            expense_vals, labels, 'saida'
        )

        result = {
            'has_data':          True,
            'months':            months_list,
            'month_labels':      labels,
            'income_totals':     income_vals,
            'expense_totals':    expense_vals,
            'balance_totals':    balance_vals,
            'income_mom':        income_mom,
            'expense_mom':       expense_mom,
            'avg_income':        avg_income,
            'avg_expense':       avg_expense,
            'avg_balance':       avg_balance,
            'income_direction':  income_dir,
            'expense_direction': expense_dir,
            'balance_direction': balance_dir,
            'income_anomalies':  income_anomalies,
            'expense_anomalies': expense_anomalies,
        }

        result['insights'] = self._generate_insights(result)

        return result

    def _get_category_trends(self) -> list:
        """
        Calcula tendências por categoria.

        Returns:
            Lista de categorias com dados de tendência
        """
        since = (
            datetime.now() - relativedelta(months=3)
        ).strftime('%Y-%m-%d')

        rows = self.db.execute(
            '''SELECT
                c.name AS category_name,
                t.transaction_type,
                strftime('%Y-%m', t.date) AS month,
                SUM(t.amount) AS total
               FROM transactions t
               JOIN categories c ON t.category_id = c.id
               WHERE t.user_id = ? AND t.date >= ?
               GROUP BY c.name, t.transaction_type, month
               ORDER BY c.name, month''',
            (self.uid, since)
        ).fetchall()

        # Agrupar por categoria
        cats = {}
        for row in rows:
            key = row['category_name']
            if key not in cats:
                cats[key] = {'entrada': [], 'saida': []}
            cats[key][row['transaction_type']].append(
                float(row['total'])
            )

        result = []
        for name, data in cats.items():
            inc_vals = data['entrada']
            exp_vals = data['saida']

            avg_income  = float(np.mean(inc_vals)) if inc_vals else 0
            avg_expense = float(np.mean(exp_vals)) if exp_vals else 0
            income_dir  = self._get_direction(inc_vals, reverse=False)
            expense_dir = self._get_direction(exp_vals, reverse=True)

            # Situação geral
            if avg_income > avg_expense:
                situacao = '✅ Superávit'
                color    = '#27ae60'
            elif avg_expense > avg_income and avg_income == 0:
                situacao = '💸 Apenas gastos'
                color    = '#e74c3c'
            else:
                situacao = '⚖️ Equilibrado'
                color    = '#f39c12'

            result.append({
                'category_name': name,
                'avg_income':    avg_income,
                'avg_expense':   avg_expense,
                'income_dir':    income_dir,
                'expense_dir':   expense_dir,
                'situacao':      situacao,
                'color':         color,
            })

        return sorted(
            result,
            key=lambda x: x['avg_expense'],
            reverse=True
        )

    # ══════════════════════════════════════════════════════
    # ANÁLISE PRINCIPAL
    # ══════════════════════════════════════════════════════

    def generate_analysis(self):
        """Gera análise completa com os filtros selecionados"""
        try:
            period_map = {0: 3, 1: 6, 2: 12, 3: 60}
            months     = period_map.get(
                self.period_combo.currentIndex(), 6
            )

            type_map   = {0: None, 1: 'entrada', 2: 'saida'}
            trans_type = type_map.get(
                self.type_combo.currentIndex(), None
            )

            category_id = self.category_combo.currentData()

            desc_text   = self.description_combo.currentText(
            ).strip()
            description = (
                desc_text
                if desc_text and
                desc_text != 'Todas as descrições'
                else None
            )

            self.current_result = self._analyze_data(
                months, category_id, trans_type, description
            )

            if not self.current_result.get('has_data'):
                self._show_no_data()
                return

            self._update_summary_cards()
            self._update_chart()
            self._update_details_table()
            self._update_insights()
            self._update_categories_tab()

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[TrendsDialog] Erro: {e}')

    def _show_no_data(self):
        """Exibe mensagem quando não há dados"""
        self.insights_text.setHtml(
            '<p style="color:gray; text-align:center;">'
            'ℹ️ Não há dados suficientes para os filtros '
            'selecionados. Tente ajustar os filtros.</p>'
        )
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(
            0.5, 0.5,
            'Sem dados para os filtros selecionados',
            ha='center', va='center',
            transform=ax.transAxes,
            color='gray', fontsize=14
        )
        self.canvas.draw()

    # ══════════════════════════════════════════════════════
    # ATUALIZAÇÃO DA INTERFACE
    # ══════════════════════════════════════════════════════

    def _update_summary_cards(self):
        """Atualiza os cards de resumo"""
        while self.summary_layout.count():
            child = self.summary_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        r = self.current_result

        cards_data = [
            (
                '💰 Média de Entrada',
                f"R$ {r.get('avg_income', 0):,.2f}",
                r.get('income_direction', {}).get(
                    'color', '#2ecc71'
                )
            ),
            (
                '💸 Média de Saída',
                f"R$ {r.get('avg_expense', 0):,.2f}",
                r.get('expense_direction', {}).get(
                    'color', '#e74c3c'
                )
            ),
            (
                '📊 Saldo Médio',
                f"R$ {r.get('avg_balance', 0):,.2f}",
                '#3498db'
                if r.get('avg_balance', 0) >= 0
                else '#e74c3c'
            ),
            (
                '📈 Tend. Entrada',
                (
                    r.get('income_direction', {}).get(
                        'emoji', '➡️'
                    ) + ' ' +
                    r.get('income_direction', {}).get(
                        'label', 'Estável'
                    )
                ),
                r.get('income_direction', {}).get(
                    'color', '#2ecc71'
                )
            ),
            (
                '📉 Tend. Saída',
                (
                    r.get('expense_direction', {}).get(
                        'emoji', '➡️'
                    ) + ' ' +
                    r.get('expense_direction', {}).get(
                        'label', 'Estável'
                    )
                ),
                r.get('expense_direction', {}).get(
                    'color', '#e74c3c'
                )
            ),
        ]

        for title, value, color in cards_data:
            card = QFrame()
            card.setFrameStyle(QFrame.Box | QFrame.Raised)
            card.setLineWidth(1)
            card.setStyleSheet(
                f'border: 1px solid {color}; border-radius: 6px;'
            )
            card.setMinimumWidth(140)
            card.setMaximumHeight(80)

            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(8, 6, 8, 6)
            c_layout.setSpacing(2)

            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(
                'font-size: 10px; color: #7f8c8d; '
                'font-weight: bold; border: none;'
            )
            t_lbl.setAlignment(Qt.AlignCenter)

            v_lbl = QLabel(value)
            v_lbl.setStyleSheet(
                f'font-size: 13px; font-weight: bold; '
                f'color: {color}; border: none;'
            )
            v_lbl.setAlignment(Qt.AlignCenter)
            v_lbl.setWordWrap(True)

            c_layout.addWidget(t_lbl)
            c_layout.addWidget(v_lbl)
            self.summary_layout.addWidget(card)

    def _update_chart(self):
        """Atualiza o gráfico conforme tipo selecionado"""
        if not self.current_result.get('has_data'):
            return

        r          = self.current_result
        months     = r.get('month_labels', [])
        income     = r.get('income_totals',  [])
        expense    = r.get('expense_totals', [])
        balance    = r.get('balance_totals', [])
        chart_type = self.chart_type_combo.currentIndex()

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if self.is_dark_mode:
            plt.style.use('dark_background')
            income_color  = '#2ecc71'
            expense_color = '#e74c3c'
            balance_color = '#3498db'
        else:
            plt.style.use('default')
            income_color  = '#27ae60'
            expense_color = '#c0392b'
            balance_color = '#2980b9'

        x = np.arange(len(months))

        if chart_type == 0:
            width = 0.35
            ax.bar(
                x - width/2, income, width,
                label='Entrada', color=income_color, alpha=0.8
            )
            ax.bar(
                x + width/2, expense, width,
                label='Saída', color=expense_color, alpha=0.8
            )
            if len(expense) >= 2:
                z = np.polyfit(x, expense, 1)
                p = np.poly1d(z)
                ax.plot(
                    x, p(x), '--',
                    color=expense_color, alpha=0.7,
                    label='Tend. Saída', linewidth=2
                )
            ax.set_title('Entrada vs Saída por Mês')

        elif chart_type == 1:
            ax.plot(
                x, balance, 'o-',
                color=balance_color, linewidth=2.5,
                markersize=6, label='Saldo'
            )
            ax.fill_between(
                x, balance, 0,
                where=[b >= 0 for b in balance],
                color=income_color, alpha=0.2, label='Positivo'
            )
            ax.fill_between(
                x, balance, 0,
                where=[b < 0 for b in balance],
                color=expense_color, alpha=0.2, label='Negativo'
            )
            ax.axhline(
                y=0, color='gray', linestyle='-', alpha=0.4
            )
            ax.set_title('Evolução do Saldo Mensal')

        elif chart_type == 2:
            ax.plot(
                x, income, 'o-',
                color=income_color, linewidth=2,
                markersize=5, label='Entrada'
            )
            ax.plot(
                x, expense, 's-',
                color=expense_color, linewidth=2,
                markersize=5, label='Saída'
            )
            if len(income) >= 2:
                zi = np.polyfit(x, income, 1)
                pi = np.poly1d(zi)
                ax.plot(
                    x, pi(x), '--',
                    color=income_color, alpha=0.6,
                    linewidth=1.5, label='Tend. Entrada'
                )
            if len(expense) >= 2:
                ze = np.polyfit(x, expense, 1)
                pe = np.poly1d(ze)
                ax.plot(
                    x, pe(x), '--',
                    color=expense_color, alpha=0.6,
                    linewidth=1.5, label='Tend. Saída'
                )
            ax.set_title('Tendências de Entrada e Saída')

        elif chart_type == 3:
            cum_income  = np.cumsum(income)
            cum_expense = np.cumsum(expense)
            ax.fill_between(
                x, cum_income, alpha=0.4,
                color=income_color, label='Entrada Acumulada'
            )
            ax.fill_between(
                x, cum_expense, alpha=0.4,
                color=expense_color, label='Saída Acumulada'
            )
            ax.plot(
                x, cum_income,
                color=income_color, linewidth=2
            )
            ax.plot(
                x, cum_expense,
                color=expense_color, linewidth=2
            )
            ax.set_title('Acumulado de Entradas e Saídas')

        # Configurações comuns
        ax.set_xticks(x)
        ax.set_xticklabels(
            months, rotation=45, ha='right', fontsize=8
        )
        ax.set_ylabel('Valores (R$)')
        ax.legend(fontsize=8)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(
                lambda val, _: f'R${val:,.0f}'
            )
        )

        self.figure.tight_layout()
        self.canvas.draw()

        # Atualizar legenda de tendência
        income_dir  = r.get('income_direction',  {})
        expense_dir = r.get('expense_direction', {})
        balance_dir = r.get('balance_direction', {})

        legend_html = (
            f"<b>Entrada:</b> "
            f"<span style='color:"
            f"{income_dir.get('color','#333')};'>"
            f"{income_dir.get('emoji','➡️')} "
            f"{income_dir.get('label','Estável')}</span>  |  "
            f"<b>Saída:</b> "
            f"<span style='color:"
            f"{expense_dir.get('color','#333')};'>"
            f"{expense_dir.get('emoji','➡️')} "
            f"{expense_dir.get('label','Estável')}</span>  |  "
            f"<b>Saldo:</b> "
            f"<span style='color:"
            f"{balance_dir.get('color','#333')};'>"
            f"{balance_dir.get('emoji','➡️')} "
            f"{balance_dir.get('label','Estável')}</span>"
        )
        self.trend_legend.setText(legend_html)
        self.trend_legend.setTextFormat(Qt.RichText)

    def _update_details_table(self):
        """Atualiza tabela de dados mensais"""
        r       = self.current_result
        months  = r.get('months',        [])
        labels  = r.get('month_labels',  [])
        income  = r.get('income_totals', [])
        expense = r.get('expense_totals',[])
        balance = r.get('balance_totals',[])
        i_mom   = r.get('income_mom',    [])
        e_mom   = r.get('expense_mom',   [])

        self.monthly_table.setRowCount(len(months))

        for i, (month, label) in enumerate(zip(months, labels)):
            inc = income[i]  if i < len(income)  else 0
            exp = expense[i] if i < len(expense) else 0
            bal = balance[i] if i < len(balance) else 0
            im  = i_mom[i]   if i < len(i_mom)   else 0
            em  = e_mom[i]   if i < len(e_mom)   else 0

            row_color = (
                QColor('#1B5E20') if (bal > 0 and self.is_dark_mode)
                else QColor('#E8F5E9') if bal > 0
                else QColor('#B71C1C') if (
                    bal < 0 and self.is_dark_mode
                )
                else QColor('#FFEBEE') if bal < 0
                else QColor('transparent')
            )

            if i >= 1:
                prev = balance[i-1] if i-1 < len(balance) else 0
                trend = (
                    '📈 Melhora' if bal > prev
                    else '📉 Piora' if bal < prev
                    else '➡️ Igual'
                )
            else:
                trend = '—'

            items = [
                QTableWidgetItem(label),
                QTableWidgetItem(f'R$ {inc:,.2f}'),
                QTableWidgetItem(f'R$ {exp:,.2f}'),
                QTableWidgetItem(f'R$ {bal:,.2f}'),
                QTableWidgetItem(
                    f'{im:+.1f}%' if im != 0 else '—'
                ),
                QTableWidgetItem(
                    f'{em:+.1f}%' if em != 0 else '—'
                ),
                QTableWidgetItem(trend),
            ]

            for j, item in enumerate(items):
                item.setBackground(row_color)
                self.monthly_table.setItem(i, j, item)

            if i < len(i_mom) and i_mom[i] != 0:
                self.monthly_table.item(i, 4).setForeground(
                    QColor('#2ecc71') if i_mom[i] > 0
                    else QColor('#e74c3c')
                )

            if i < len(e_mom) and e_mom[i] != 0:
                self.monthly_table.item(i, 5).setForeground(
                    QColor('#e74c3c') if e_mom[i] > 0
                    else QColor('#2ecc71')
                )

        self.monthly_table.resizeColumnsToContents()

        # Estatísticas
        avg_i = r.get('avg_income',  0)
        avg_e = r.get('avg_expense', 0)
        avg_b = r.get('avg_balance', 0)

        income_vals  = r.get('income_totals',  [0])
        expense_vals = r.get('expense_totals', [0])
        balance_vals = r.get('balance_totals', [0])

        self.stats_income_text.setHtml(f'''
            <b>💰 Estatísticas de Entrada</b><br>
            Média: <b>R$ {avg_i:,.2f}</b><br>
            Maior: <b>R$ {max(income_vals):,.2f}</b><br>
            Menor: <b>R$ {min(income_vals):,.2f}</b><br>
            Tendência: <b>
            {r.get('income_direction',{}).get('label','—')}</b>
        ''')

        self.stats_expense_text.setHtml(f'''
            <b>💸 Estatísticas de Saída</b><br>
            Média: <b>R$ {avg_e:,.2f}</b><br>
            Maior: <b>R$ {max(expense_vals):,.2f}</b><br>
            Menor: <b>R$ {min(expense_vals):,.2f}</b><br>
            Tendência: <b>
            {r.get('expense_direction',{}).get('label','—')}</b>
        ''')

        color = '#27ae60' if avg_b >= 0 else '#c0392b'
        self.stats_balance_text.setHtml(f'''
            <b>⚖️ Estatísticas de Saldo</b><br>
            Média: <b style="color:{color};">
            R$ {avg_b:,.2f}</b><br>
            Melhor mês: <b>R$ {max(balance_vals):,.2f}</b><br>
            Pior mês:   <b>R$ {min(balance_vals):,.2f}</b><br>
            Tendência: <b>
            {r.get('balance_direction',{}).get('label','—')}</b>
        ''')

    def _update_insights(self):
        """Atualiza aba de insights"""
        r        = self.current_result
        insights = r.get('insights', [])

        html = '<div style="font-size:13px;">'

        if not insights:
            html += (
                '<p style="color:gray;">'
                'ℹ️ Sem insights para os filtros selecionados.'
                '</p>'
            )
        else:
            color_map = {
                'positive':  '#27ae60',
                'warning':   '#e67e22',
                'attention': '#f39c12',
                'critical':  '#e74c3c',
                'info':      '#3498db'
            }
            bg_map = {
                'positive':  '#eafaf1',
                'warning':   '#fef9e7',
                'attention': '#fef5e4',
                'critical':  '#fdedec',
                'info':      '#ebf5fb'
            }

            for ins in insights:
                color = color_map.get(
                    ins.get('type', 'info'), '#333'
                )
                bg = (
                    'transparent' if self.is_dark_mode
                    else bg_map.get(
                        ins.get('type', 'info'), '#f9f9f9'
                    )
                )
                html += (
                    f'<div style="margin:6px 0; padding:8px; '
                    f'border-left: 4px solid {color}; '
                    f'background-color:{bg}; border-radius:4px;">'
                    f'<span style="color:{color}; font-size:15px;">'
                    f'{ins.get("emoji","")}</span> '
                    f'<span style="color:{color}; '
                    f'font-weight:bold;">'
                    f'{ins.get("message","")}</span>'
                    f'</div>'
                )

        html += '</div>'
        self.insights_text.setHtml(html)

        # Anomalias
        all_anomalies = (
            r.get('income_anomalies',  []) +
            r.get('expense_anomalies', [])
        )
        self.anomaly_table.setRowCount(len(all_anomalies))

        for i, anomaly in enumerate(all_anomalies):
            self.anomaly_table.setItem(
                i, 0,
                QTableWidgetItem(anomaly.get('label', ''))
            )
            tipo_item = QTableWidgetItem(
                '📈 Alta' if anomaly.get('type') == 'alto'
                else '📉 Baixa'
            )
            tipo_item.setForeground(
                QColor('#e74c3c')
                if anomaly.get('type') == 'alto'
                else QColor('#2ecc71')
            )
            self.anomaly_table.setItem(i, 1, tipo_item)
            self.anomaly_table.setItem(
                i, 2,
                QTableWidgetItem(
                    f"R$ {anomaly.get('value', 0):,.2f}"
                )
            )
            self.anomaly_table.setItem(
                i, 3,
                QTableWidgetItem(
                    str(anomaly.get('z_score', 0))
                )
            )

        self.anomaly_table.resizeColumnsToContents()

    def _update_categories_tab(self):
        """Atualiza aba de tendências por categoria"""
        summaries = self._get_category_trends()
        self.categories_trend_table.setRowCount(len(summaries))

        for i, cat in enumerate(summaries):
            self.categories_trend_table.setItem(
                i, 0,
                QTableWidgetItem(cat['category_name'])
            )
            self.categories_trend_table.setItem(
                i, 1,
                QTableWidgetItem(
                    f"R$ {cat.get('avg_expense', 0):,.2f}"
                )
            )
            self.categories_trend_table.setItem(
                i, 2,
                QTableWidgetItem(
                    f"R$ {cat.get('avg_income', 0):,.2f}"
                )
            )

            # Tendência (saída ou entrada dependendo do maior)
            if cat.get('avg_expense', 0) > 0:
                exp_dir  = cat.get('expense_dir', {})
                dir_item = QTableWidgetItem(
                    f"{exp_dir.get('emoji','➡️')} "
                    f"{exp_dir.get('label','Estável')}"
                )
                dir_item.setForeground(
                    QColor(exp_dir.get('color', '#333'))
                )
            else:
                inc_dir  = cat.get('income_dir', {})
                dir_item = QTableWidgetItem(
                    f"{inc_dir.get('emoji','➡️')} "
                    f"{inc_dir.get('label','Estável')}"
                )
                dir_item.setForeground(
                    QColor(inc_dir.get('color', '#333'))
                )
            self.categories_trend_table.setItem(i, 3, dir_item)

            sit_item = QTableWidgetItem(
                cat.get('situacao', '—')
            )
            sit_item.setForeground(
                QColor(cat.get('color', '#333'))
            )
            self.categories_trend_table.setItem(i, 4, sit_item)

        self.categories_trend_table.resizeColumnsToContents()

    # ══════════════════════════════════════════════════════
    # EXPORTAR
    # ══════════════════════════════════════════════════════

    def export_analysis(self):
        """Exporta a análise atual para arquivo texto"""
        if not self.current_result.get('has_data'):
            QMessageBox.warning(
                self, 'Aviso',
                'Não há dados para exportar.'
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Exportar Análise de Tendências',
            f'tendencias_{datetime.now().strftime("%Y%m%d")}.txt',
            'Arquivos de Texto (*.txt)'
        )
        if not file_path:
            return

        r     = self.current_result
        lines = [
            'ANÁLISE DE TENDÊNCIAS FINANCEIRAS',
            f'Gerado em: '
            f'{datetime.now().strftime("%d/%m/%Y %H:%M")}',
            '=' * 50,
            '',
            f'Média de Entrada: R$ {r.get("avg_income",0):,.2f}',
            f'Média de Saída:   R$ {r.get("avg_expense",0):,.2f}',
            f'Saldo Médio:      R$ {r.get("avg_balance",0):,.2f}',
            '',
            f'Tendência Entrada: '
            f'{r.get("income_direction",{}).get("label","—")}',
            f'Tendência Saída:   '
            f'{r.get("expense_direction",{}).get("label","—")}',
            '',
            'DADOS MENSAIS:',
            '-' * 50
        ]

        months  = r.get('month_labels',  [])
        income  = r.get('income_totals', [])
        expense = r.get('expense_totals',[])
        balance = r.get('balance_totals',[])

        for i, label in enumerate(months):
            inc = income[i]  if i < len(income)  else 0
            exp = expense[i] if i < len(expense) else 0
            bal = balance[i] if i < len(balance) else 0
            lines.append(
                f'{label}: Entrada R${inc:,.2f} | '
                f'Saída R${exp:,.2f} | Saldo R${bal:,.2f}'
            )

        lines += ['', 'INSIGHTS:', '-' * 50]
        for ins in r.get('insights', []):
            lines.append(f'• {ins.get("message", "")}')

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            QMessageBox.information(
                self, 'Sucesso',
                f'Análise exportada para:\n{file_path}'
            )
        except Exception as e:
            QMessageBox.warning(
                self, 'Erro',
                f'Erro ao exportar: {str(e)}'
            )

    # ══════════════════════════════════════════════════════
    # TEMA
    # ══════════════════════════════════════════════════════

    def apply_theme(self):
        """Aplica o tema claro ou escuro"""
        if self.is_dark_mode:
            self.setStyleSheet('''
                QDialog {
                    background-color: #1e272e; color: #ecf0f1;
                }
                QLabel { color: #ecf0f1; }
                QComboBox {
                    padding: 6px; border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QGroupBox {
                    border: 1px solid #4b6584;
                    border-radius: 5px; margin-top: 10px;
                    color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px; padding: 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                }
                QHeaderView::section {
                    background-color: #2c3e50; color: #ecf0f1;
                    padding: 5px; border: 1px solid #4b6584;
                }
                QTabWidget::pane {
                    border: 1px solid #4b6584;
                    background-color: #1e272e;
                }
                QTabBar::tab {
                    background-color: #2d3436; color: #ecf0f1;
                    padding: 8px 12px; border: 1px solid #4b6584;
                }
                QTabBar::tab:selected {
                    background-color: #3498db;
                }
                QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                }
            ''')
            plt.style.use('dark_background')
        else:
            self.setStyleSheet('''
                QDialog { background-color: #f9f9f9; }
                QLabel { color: #333; }
                QComboBox {
                    padding: 6px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #2196F3; color: white;
                }
                QPushButton:hover { background-color: #1976D2; }
                QTableWidget { background-color: white; }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333;
                    padding: 8px 12px; border: 1px solid #ccc;
                }
                QTabBar::tab:selected {
                    background-color: #2196F3; color: white;
                }
                QTextEdit {
                    background-color: white;
                    border: 1px solid #ccc; border-radius: 4px;
                }
            ''')
            plt.style.use('default')

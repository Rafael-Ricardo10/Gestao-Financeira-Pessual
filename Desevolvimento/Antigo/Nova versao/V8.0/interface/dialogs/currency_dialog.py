"""
Diálogo de Cotações e Análise Cambial
Mostra cotações em tempo real e histórico de USD, EUR e BTC para BRL
BTC-BRL calculado via BTC-USD × USDBRL (Yahoo Finance não tem BTC-BRL direto)
"""
import sqlite3
import threading
from datetime import datetime, timedelta

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas
)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTabWidget, QWidget,
    QGroupBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QFrame, QSplitter, QScrollArea,
    QMessageBox, QApplication
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor


# ── Mapa de pares monitorados ─────────────────────────────────
CURRENCY_PAIRS = {
    'USDBRL': {'label': 'USD/BRL', 'emoji': '🇺🇸', 'color': '#2980b9'},
    'EURBRL': {'label': 'EUR/BRL', 'emoji': '🇪🇺', 'color': '#8e44ad'},
    'BTCBRL': {'label': 'BTC/BRL', 'emoji': '₿',  'color': '#f39c12'},
}


def _get_btc_brl_via_usd(thread_conn) -> bool:
    """
    Busca BTC-USD e converte para BRL usando USDBRL.
    Salva na tabela currency_rates como par 'BTCBRL'.
    Retorna True se salvou novos dados.
    """
    try:
        import yfinance as yf

        # Verificar se precisa atualizar
        from modulos.currency_tracker import needs_update
        if not needs_update(thread_conn, 'BTCBRL'):
            return False

        # Buscar BTC-USD
        btc_ticker = yf.Ticker('BTC-USD')
        btc_hist   = btc_ticker.history(period='5d')
        if btc_hist.empty:
            print('[Currency] BTC-USD sem dados.')
            return False

        # Buscar USDBRL para conversão
        usd_ticker = yf.Ticker('USDBRL=X')
        usd_hist   = usd_ticker.history(period='5d')
        if usd_hist.empty:
            print('[Currency] USDBRL sem dados para conversão BTC.')
            return False

        fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        count      = 0

        for idx, row in btc_hist.iterrows():
            rate_date = idx.strftime('%Y-%m-%d')

            # Buscar taxa USD/BRL mais próxima desta data
            usd_row = None
            if rate_date in usd_hist.index.strftime('%Y-%m-%d').tolist():
                date_idx = usd_hist.index.strftime(
                    '%Y-%m-%d'
                ).tolist().index(rate_date)
                usd_row = usd_hist.iloc[date_idx]
            else:
                # Usar última taxa disponível
                usd_row = usd_hist.iloc[-1]

            if usd_row is None:
                continue

            usd_brl = float(usd_row['Close'])

            try:
                thread_conn.execute(
                    '''INSERT OR REPLACE INTO currency_rates
                       (pair, rate_date, open_rate, close_rate,
                        high_rate, low_rate, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        'BTCBRL',
                        rate_date,
                        round(float(row['Open'])  * usd_brl, 2),
                        round(float(row['Close']) * usd_brl, 2),
                        round(float(row['High'])  * usd_brl, 2),
                        round(float(row['Low'])   * usd_brl, 2),
                        fetched_at
                    )
                )
                count += 1
            except Exception:
                pass

        thread_conn.commit()
        print(f'[Currency] BTC/BRL: {count} registros via conversão USD.')
        return count > 0

    except Exception as e:
        print(f'[Currency] Erro ao buscar BTC via USD: {e}')
        return False


def _fetch_btc_history_via_usd(
    thread_conn, since_date: str
) -> bool:
    """
    Busca histórico completo de BTC-BRL via conversão BTC-USD × USDBRL.
    Verifica o que já existe antes de buscar.
    """
    try:
        import yfinance as yf

        # Verificar dados existentes
        existing = thread_conn.execute(
            '''SELECT COUNT(*) FROM currency_rates
               WHERE pair = 'BTCBRL' AND rate_date >= ?''',
            (since_date,)
        ).fetchone()[0]

        since_dt = datetime.strptime(since_date, '%Y-%m-%d')
        days     = (datetime.now() - since_dt).days + 5

        if existing > (days * 0.7):
            print(f'[Currency] BTC/BRL já tem {existing} registros.')
            return False

        print(
            f'[Currency] Baixando histórico BTC/BRL desde '
            f'{since_date} via BTC-USD × USDBRL...'
        )

        end_date = datetime.now().strftime('%Y-%m-%d')

        # Buscar histórico BTC-USD
        btc_ticker = yf.Ticker('BTC-USD')
        btc_hist   = btc_ticker.history(
            start=since_date, end=end_date
        )
        if btc_hist.empty:
            print('[Currency] BTC-USD sem histórico.')
            return False

        # Buscar histórico USDBRL
        usd_ticker = yf.Ticker('USDBRL=X')
        usd_hist   = usd_ticker.history(
            start=since_date, end=end_date
        )
        if usd_hist.empty:
            print('[Currency] USDBRL sem histórico para conversão.')
            return False

        # Criar mapa de datas USDBRL
        usd_map = {}
        for idx, row in usd_hist.iterrows():
            usd_map[idx.strftime('%Y-%m-%d')] = float(row['Close'])

        fetched_at  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        count       = 0
        last_usd_brl = list(usd_map.values())[-1] if usd_map else 5.0

        for idx, row in btc_hist.iterrows():
            rate_date = idx.strftime('%Y-%m-%d')

            # Taxa USD/BRL do dia ou a mais recente disponível
            usd_brl = usd_map.get(rate_date, last_usd_brl)
            # Atualizar último valor conhecido
            if rate_date in usd_map:
                last_usd_brl = usd_map[rate_date]

            try:
                thread_conn.execute(
                    '''INSERT OR IGNORE INTO currency_rates
                       (pair, rate_date, open_rate, close_rate,
                        high_rate, low_rate, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        'BTCBRL',
                        rate_date,
                        round(float(row['Open'])  * usd_brl, 2),
                        round(float(row['Close']) * usd_brl, 2),
                        round(float(row['High'])  * usd_brl, 2),
                        round(float(row['Low'])   * usd_brl, 2),
                        fetched_at
                    )
                )
                count += 1
            except Exception:
                pass

        thread_conn.commit()
        print(
            f'[Currency] BTC/BRL histórico: {count} registros salvos.'
        )
        return True

    except Exception as e:
        print(f'[Currency] Erro no histórico BTC via USD: {e}')
        return False


# ══════════════════════════════════════════════════════════════
# DIÁLOGO PRINCIPAL
# ══════════════════════════════════════════════════════════════

class CurrencyDialog(QDialog):
    """
    Diálogo de Cotações e Análise Cambial.
    Mostra cotações atuais, histórico e correlação com gastos.
    BTC/BRL calculado via BTC-USD × USDBRL.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('💱 Cotações e Análise Cambial')
        self.setMinimumSize(1000, 700)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )
        self.db      = parent.db_connection
        self.user_id = parent.user_id
        self.db_path = self._find_db_path()

        self._build_ui()
        self.apply_theme()

        # Carregar dados do banco primeiro (rápido)
        self._load_from_db()

        # Atualizar em background se necessário
        self._start_background_update()

        # Auto-refresh a cada 5 minutos
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._load_from_db)
        self.refresh_timer.start(300_000)

    # ══════════════════════════════════════════════════════
    # SETUP
    # ══════════════════════════════════════════════════════

    def _find_db_path(self) -> str:
        """Encontra o caminho do banco de dados do usuário"""
        import os
        dados_dir = 'dados'
        if os.path.exists(dados_dir):
            for fname in os.listdir(dados_dir):
                if fname.endswith('.db'):
                    test_path = os.path.join(dados_dir, fname)
                    try:
                        test_conn = sqlite3.connect(test_path)
                        test_conn.row_factory = sqlite3.Row
                        user = test_conn.execute(
                            'SELECT id FROM users WHERE id = ?',
                            (self.user_id,)
                        ).fetchone()
                        test_conn.close()
                        if user:
                            return test_path
                    except Exception:
                        pass
        return ''

    def _build_ui(self):
        """Constrói a interface completa"""
        layout = QVBoxLayout(self)

        # ── Cabeçalho ────────────────────────────────────────
        header = QHBoxLayout()
        title  = QLabel('💱 Cotações e Análise Cambial')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        header.addWidget(title)

        badge = QLabel('🤖 Correlação com IA')
        badge.setStyleSheet(
            'background-color: #16a085; color: white;'
            'padding: 4px 8px; border-radius: 10px;'
            'font-size: 11px; font-weight: bold;'
        )
        header.addWidget(badge)
        header.addStretch()

        self.status_label = QLabel('Carregando...')
        self.status_label.setStyleSheet('color: #7f8c8d; font-size: 11px;')
        header.addWidget(self.status_label)

        self.refresh_btn = QPushButton('🔄 Atualizar')
        self.refresh_btn.clicked.connect(self._force_update)
        header.addWidget(self.refresh_btn)

        layout.addLayout(header)

        # ── Cards de cotação atual ────────────────────────────
        self.cards_layout = QHBoxLayout()
        self.rate_cards   = {}

        for pair, info in CURRENCY_PAIRS.items():
            card = self._make_rate_card(
                info['emoji'] + ' ' + info['label'],
                'Carregando...',
                info['color']
            )
            self.rate_cards[pair] = card
            self.cards_layout.addWidget(card)

        layout.addLayout(self.cards_layout)

        # ── Barra de progresso (atualização) ─────────────────
        self.update_bar = QProgressBar()
        self.update_bar.setRange(0, 0)
        self.update_bar.setMaximumHeight(6)
        self.update_bar.setVisible(False)
        layout.addWidget(self.update_bar)

        # ── Abas ─────────────────────────────────────────────
        self.tabs = QTabWidget()

        self.tabs.addTab(
            self._build_history_tab(), '📊 Histórico'
        )
        self.tabs.addTab(
            self._build_correlation_tab(), '🔗 Correlação com Gastos'
        )
        self.tabs.addTab(
            self._build_table_tab(), '📋 Tabela de Cotações'
        )
        self.tabs.addTab(
            self._build_info_tab(), 'ℹ️ Informações'
        )

        layout.addWidget(self.tabs)

        # ── Rodapé ───────────────────────────────────────────
        footer = QHBoxLayout()
        self.last_update_label = QLabel('Última atualização: —')
        self.last_update_label.setStyleSheet(
            'color: #7f8c8d; font-size: 10px;'
        )
        footer.addWidget(self.last_update_label)
        footer.addStretch()

        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

    def _make_rate_card(
        self, title: str, value: str, color: str
    ) -> QFrame:
        """Cria um card de cotação"""
        card = QFrame()
        card.setFrameStyle(QFrame.Box | QFrame.Raised)
        card.setLineWidth(1)
        card.setMinimumWidth(200)
        card.setMaximumHeight(130)
        card.setStyleSheet(
            f'border: 2px solid {color}; border-radius: 8px;'
        )

        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 8, 12, 8)
        c_layout.setSpacing(2)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(
            f'font-size: 13px; font-weight: bold; '
            f'color: {color}; border: none;'
        )
        t_lbl.setAlignment(Qt.AlignCenter)
        t_lbl.setObjectName('title_label')

        v_lbl = QLabel(value)
        v_lbl.setStyleSheet(
            f'font-size: 20px; font-weight: bold; '
            f'color: {color}; border: none;'
        )
        v_lbl.setAlignment(Qt.AlignCenter)
        v_lbl.setObjectName('value_label')

        change_lbl = QLabel('')
        change_lbl.setStyleSheet('font-size: 11px; border: none;')
        change_lbl.setAlignment(Qt.AlignCenter)
        change_lbl.setObjectName('change_label')

        date_lbl = QLabel('')
        date_lbl.setStyleSheet(
            'font-size: 10px; color: #7f8c8d; border: none;'
        )
        date_lbl.setAlignment(Qt.AlignCenter)
        date_lbl.setObjectName('date_label')

        c_layout.addWidget(t_lbl)
        c_layout.addWidget(v_lbl)
        c_layout.addWidget(change_lbl)
        c_layout.addWidget(date_lbl)

        return card

    def _build_history_tab(self) -> QWidget:
        """Aba de histórico gráfico"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Controles
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Par:'))

        self.pair_combo = QComboBox()
        for pair, info in CURRENCY_PAIRS.items():
            self.pair_combo.addItem(
                info['emoji'] + ' ' + info['label'], pair
            )
        self.pair_combo.currentIndexChanged.connect(
            self._update_history_chart
        )
        controls.addWidget(self.pair_combo)

        controls.addWidget(QLabel('Período:'))
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            '30 dias', '90 dias', '180 dias', '1 ano', 'Tudo'
        ])
        self.period_combo.setCurrentIndex(1)
        self.period_combo.currentIndexChanged.connect(
            self._update_history_chart
        )
        controls.addWidget(self.period_combo)

        controls.addWidget(QLabel('Visualização:'))
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems([
            'Linha (Fechamento)',
            'Candlestick Simplificado',
            'Área',
            'Variação Diária %',
        ])
        self.chart_type_combo.currentIndexChanged.connect(
            self._update_history_chart
        )
        controls.addWidget(self.chart_type_combo)
        controls.addStretch()
        layout.addLayout(controls)

        # Gráfico
        self.hist_figure = plt.figure(figsize=(9, 4), dpi=95)
        self.hist_canvas = FigureCanvas(self.hist_figure)
        self.hist_canvas.setMinimumHeight(300)
        layout.addWidget(self.hist_canvas)

        # Estatísticas do período
        stats_group  = QGroupBox('📊 Estatísticas do Período')
        stats_layout = QHBoxLayout()

        self.hist_stats_labels = {}
        for key, label in [
            ('open',   'Abertura'),
            ('close',  'Fechamento'),
            ('high',   'Máxima'),
            ('low',    'Mínima'),
            ('change', 'Variação'),
            ('avg',    'Média'),
        ]:
            frame   = QFrame()
            f_lay   = QVBoxLayout(frame)
            f_lay.setContentsMargins(4, 4, 4, 4)
            f_lay.setSpacing(1)

            k_lbl = QLabel(label)
            k_lbl.setStyleSheet(
                'font-size: 10px; color: #7f8c8d; font-weight: bold;'
            )
            k_lbl.setAlignment(Qt.AlignCenter)

            v_lbl = QLabel('—')
            v_lbl.setStyleSheet('font-size: 13px; font-weight: bold;')
            v_lbl.setAlignment(Qt.AlignCenter)
            v_lbl.setObjectName(f'stat_{key}')

            f_lay.addWidget(k_lbl)
            f_lay.addWidget(v_lbl)
            self.hist_stats_labels[key] = v_lbl
            stats_layout.addWidget(frame)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        return widget

    def _build_correlation_tab(self) -> QWidget:
        """Aba de correlação câmbio × gastos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Controles
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Analisar par:'))

        self.corr_pair_combo = QComboBox()
        for pair, info in CURRENCY_PAIRS.items():
            self.corr_pair_combo.addItem(
                info['emoji'] + ' ' + info['label'], pair
            )
        self.corr_pair_combo.currentIndexChanged.connect(
            self._update_correlation
        )
        controls.addWidget(self.corr_pair_combo)
        controls.addStretch()

        analyze_btn = QPushButton('🔍 Analisar Correlação')
        analyze_btn.clicked.connect(self._update_correlation)
        controls.addWidget(analyze_btn)
        layout.addLayout(controls)

        # Gráfico de correlação
        self.corr_figure = plt.figure(figsize=(9, 3.5), dpi=95)
        self.corr_canvas = FigureCanvas(self.corr_figure)
        self.corr_canvas.setMinimumHeight(220)
        layout.addWidget(self.corr_canvas)

        # Resultado da análise
        result_group  = QGroupBox('🔗 Resultado da Análise de Correlação')
        result_layout = QVBoxLayout()

        self.corr_result_text = QTextEdit()
        self.corr_result_text.setReadOnly(True)
        self.corr_result_text.setMaximumHeight(180)
        result_layout.addWidget(self.corr_result_text)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        return widget

    def _build_table_tab(self) -> QWidget:
        """Aba de tabela com dados históricos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Filtro de par
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel('Par:'))

        self.table_pair_combo = QComboBox()
        self.table_pair_combo.addItem('Todos os pares', None)
        for pair, info in CURRENCY_PAIRS.items():
            self.table_pair_combo.addItem(
                info['emoji'] + ' ' + info['label'], pair
            )
        self.table_pair_combo.currentIndexChanged.connect(
            self._update_rates_table
        )
        filter_layout.addWidget(self.table_pair_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Tabela
        self.rates_table = QTableWidget()
        self.rates_table.setColumnCount(7)
        self.rates_table.setHorizontalHeaderLabels([
            'Par', 'Data', 'Abertura', 'Fechamento',
            'Máxima', 'Mínima', 'Variação'
        ])
        self.rates_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rates_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rates_table.setSortingEnabled(True)
        self.rates_table.horizontalHeader().setStretchLastSection(True)
        self.rates_table.verticalHeader().setVisible(False)
        self.rates_table.setAlternatingRowColors(True)
        layout.addWidget(self.rates_table)

        return widget

    def _build_info_tab(self) -> QWidget:
        """Aba de informações sobre o sistema de cotações"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll  = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        c_lay   = QVBoxLayout(content)

        info_html = '''
        <h2>💱 Sistema de Cotações</h2>

        <h3>📡 Fonte de Dados</h3>
        <p>As cotações são obtidas via <b>Yahoo Finance (yfinance)</b>
        e salvas localmente no banco de dados SQLite para acesso offline
        e análise histórica.</p>

        <h3>🔄 Frequência de Atualização</h3>
        <ul>
            <li><b>USD/BRL e EUR/BRL:</b> Uma vez por dia
            (após fechamento do mercado às 18h BRT)</li>
            <li><b>BTC/BRL:</b> Calculado via
            <code>BTC-USD × USDBRL</code> pois o Yahoo Finance
            não disponibiliza BTC-BRL diretamente</li>
        </ul>

        <h3>🧮 Cálculo BTC/BRL</h3>
        <p>Como o Yahoo Finance retorna erro 404 para o símbolo
        <code>BTC-BRL</code>, utilizamos a seguinte fórmula:</p>
        <p style="background:#f0f0f0; padding:8px; border-radius:4px;">
        <b>BTC/BRL = BTC/USD × USD/BRL</b>
        </p>
        <p>Isso garante dados precisos e atualizados para análise.</p>

        <h3>🔗 Correlação com Gastos</h3>
        <p>O sistema analisa a correlação entre a variação cambial
        e seus gastos mensais, identificando se as oscilações do
        câmbio impactam seu padrão de consumo.</p>

        <h3>📊 Interpretação da Correlação</h3>
        <ul>
            <li><b>> 0.5:</b> Alta correlação positiva —
            quando o câmbio sobe, seus gastos tendem a subir</li>
            <li><b>< -0.5:</b> Alta correlação negativa —
            quando o câmbio sobe, seus gastos tendem a cair</li>
            <li><b>-0.2 a 0.2:</b> Baixa correlação —
            o câmbio não influencia muito seus gastos</li>
        </ul>

        <h3>⚙️ Requisitos</h3>
        <ul>
            <li>Python: <code>pip install yfinance</code></li>
            <li>Python: <code>pip install numpy</code></li>
        </ul>
        '''

        info_label = QTextEdit()
        info_label.setReadOnly(True)
        info_label.setHtml(info_html)
        c_lay.addWidget(info_label)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        return widget

    # ══════════════════════════════════════════════════════
    # CARREGAMENTO DE DADOS
    # ══════════════════════════════════════════════════════

    def _load_from_db(self):
        """Carrega todos os dados do banco (sem network)"""
        try:
            self._update_rate_cards()
            self._update_history_chart()
            self._update_rates_table()
            self._update_correlation()

            # Última atualização
            last = self.db.execute(
                '''SELECT MAX(fetched_at) as last
                   FROM currency_rates'''
            ).fetchone()
            if last and last['last']:
                try:
                    dt = datetime.strptime(
                        last['last'], '%Y-%m-%d %H:%M:%S'
                    )
                    self.last_update_label.setText(
                        f'Última atualização: '
                        f'{dt.strftime("%d/%m/%Y %H:%M")}'
                    )
                except Exception:
                    pass

        except Exception as e:
            print(f'[CurrencyDialog] Erro ao carregar: {e}')

    def _update_rate_cards(self):
        """Atualiza os cards de cotação atual"""
        for pair, info in CURRENCY_PAIRS.items():
            row = self.db.execute(
                '''SELECT * FROM currency_rates
                   WHERE pair = ?
                   ORDER BY rate_date DESC LIMIT 1''',
                (pair,)
            ).fetchone()

            card       = self.rate_cards[pair]
            val_label  = card.findChild(QLabel, 'value_label')
            chg_label  = card.findChild(QLabel, 'change_label')
            date_label = card.findChild(QLabel, 'date_label')

            if not row:
                if val_label:
                    val_label.setText('Sem dados')
                continue

            rate = row['close_rate']
            color = info['color']

            # Formatação por par
            if pair == 'BTCBRL':
                formatted = f'R$ {rate:,.0f}'
            else:
                formatted = f'R$ {rate:.4f}'

            if val_label:
                val_label.setText(formatted)

            # Variação vs ontem
            prev = self.db.execute(
                '''SELECT close_rate FROM currency_rates
                   WHERE pair = ?
                   ORDER BY rate_date DESC LIMIT 1 OFFSET 1''',
                (pair,)
            ).fetchone()

            if prev and prev['close_rate']:
                change = (rate - prev['close_rate']) / \
                         prev['close_rate'] * 100
                arrow  = '▲' if change >= 0 else '▼'
                chg_color = '#27ae60' if change >= 0 else '#e74c3c'
                if chg_label:
                    chg_label.setText(
                        f'<span style="color:{chg_color};">'
                        f'{arrow} {abs(change):.2f}%</span>'
                    )
                    chg_label.setTextFormat(Qt.RichText)

            if date_label:
                try:
                    dt = datetime.strptime(
                        row['rate_date'], '%Y-%m-%d'
                    )
                    date_label.setText(dt.strftime('%d/%m/%Y'))
                except Exception:
                    date_label.setText(row['rate_date'])

    def _update_history_chart(self):
        """Atualiza o gráfico de histórico"""
        pair       = self.pair_combo.currentData()
        period_idx = self.period_combo.currentIndex()
        chart_type = self.chart_type_combo.currentIndex()

        period_days = {0: 30, 1: 90, 2: 180, 3: 365, 4: 9999}
        days        = period_days.get(period_idx, 90)

        since_date = (
            datetime.now() - timedelta(days=days)
        ).strftime('%Y-%m-%d')

        rows = self.db.execute(
            '''SELECT rate_date, open_rate, close_rate,
                      high_rate, low_rate
               FROM currency_rates
               WHERE pair = ? AND rate_date >= ?
               ORDER BY rate_date ASC''',
            (pair, since_date)
        ).fetchall()

        self.hist_figure.clear()
        ax = self.hist_figure.add_subplot(111)

        if not rows:
            ax.text(
                0.5, 0.5,
                'Sem dados históricos para este par.\n'
                'Clique em 🔄 Atualizar para buscar.',
                ha='center', va='center',
                transform=ax.transAxes,
                color='gray', fontsize=12
            )
            self.hist_canvas.draw()
            return

        dates  = [r['rate_date']  for r in rows]
        closes = [r['close_rate'] for r in rows]
        opens  = [r['open_rate']  for r in rows]
        highs  = [r['high_rate']  for r in rows]
        lows   = [r['low_rate']   for r in rows]

        pair_info = CURRENCY_PAIRS.get(pair, {})
        color     = pair_info.get('color', '#16a085')
        label     = pair_info.get('label', pair)

        # Eixo X - mostrar datas selecionadas
        x     = range(len(dates))
        n     = len(dates)
        step  = max(1, n // 8)
        xtick_positions = list(range(0, n, step))
        xtick_labels    = [dates[i][:10] for i in xtick_positions]

        if chart_type == 0:
            # Linha de fechamento
            ax.plot(x, closes, color=color, linewidth=2, label=label)
            ax.fill_between(x, closes, min(closes), alpha=0.15, color=color)
            ax.set_title(f'Histórico {label} - Fechamento')

        elif chart_type == 1:
            # Candlestick simplificado (barras coloridas)
            for i, (o, c, h, l) in enumerate(
                zip(opens, closes, highs, lows)
            ):
                clr = '#27ae60' if c >= o else '#e74c3c'
                ax.bar(i, abs(c - o), bottom=min(o, c),
                       color=clr, width=0.6, alpha=0.8)
                ax.plot([i, i], [l, min(o, c)],
                        color=clr, linewidth=1)
                ax.plot([i, i], [max(o, c), h],
                        color=clr, linewidth=1)
            ax.set_title(f'Histórico {label} - Candlestick')

        elif chart_type == 2:
            # Área
            ax.fill_between(
                x, closes, min(closes),
                alpha=0.4, color=color
            )
            ax.plot(x, closes, color=color, linewidth=1.5)
            ax.set_title(f'Histórico {label} - Área')

        elif chart_type == 3:
            # Variação diária %
            if len(closes) >= 2:
                variations = [0.0] + [
                    (closes[i] - closes[i-1]) / closes[i-1] * 100
                    for i in range(1, len(closes))
                ]
                bar_colors = [
                    '#27ae60' if v >= 0 else '#e74c3c'
                    for v in variations
                ]
                ax.bar(x, variations, color=bar_colors, alpha=0.8)
                ax.axhline(y=0, color='gray', linewidth=0.8)
                ax.set_title(f'Variação Diária % - {label}')
                ax.set_ylabel('Variação %')

        # Config comuns
        ax.set_xticks(xtick_positions)
        ax.set_xticklabels(xtick_labels, rotation=45, ha='right', fontsize=7)
        ax.grid(True, linestyle='--', alpha=0.4)

        if chart_type != 3:
            ax.set_ylabel(f'R$ ({label})')
            # Formatação eixo Y para BTC
            if pair == 'BTCBRL':
                ax.yaxis.set_major_formatter(
                    plt.FuncFormatter(lambda v, _: f'R${v:,.0f}')
                )
            else:
                ax.yaxis.set_major_formatter(
                    plt.FuncFormatter(lambda v, _: f'R${v:.3f}')
                )

        self.hist_figure.tight_layout()
        self.hist_canvas.draw()

        # Atualizar estatísticas
        if closes:
            first_close = closes[0]
            last_close  = closes[-1]
            change_pct  = (
                (last_close - first_close) / first_close * 100
                if first_close > 0 else 0
            )

            def fmt(v):
                if pair == 'BTCBRL':
                    return f'R$ {v:,.0f}'
                return f'R$ {v:.4f}'

            stats = {
                'open':   fmt(opens[0]   if opens   else 0),
                'close':  fmt(last_close),
                'high':   fmt(max(highs) if highs   else 0),
                'low':    fmt(min(lows)  if lows    else 0),
                'change': f'{change_pct:+.2f}%',
                'avg':    fmt(np.mean(closes)),
            }

            chg_color = (
                '#27ae60' if change_pct >= 0 else '#e74c3c'
            )

            for key, val in stats.items():
                lbl = self.hist_stats_labels.get(key)
                if lbl:
                    if key == 'change':
                        lbl.setStyleSheet(
                            f'font-size: 13px; font-weight: bold;'
                            f'color: {chg_color};'
                        )
                    lbl.setText(val)

    def _update_rates_table(self):
        """Atualiza a tabela de cotações históricas"""
        pair = self.table_pair_combo.currentData()

        if pair:
            rows = self.db.execute(
                '''SELECT * FROM currency_rates
                   WHERE pair = ?
                   ORDER BY rate_date DESC LIMIT 200''',
                (pair,)
            ).fetchall()
        else:
            rows = self.db.execute(
                '''SELECT * FROM currency_rates
                   ORDER BY rate_date DESC, pair ASC
                   LIMIT 500'''
            ).fetchall()

        self.rates_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            pair_info = CURRENCY_PAIRS.get(row['pair'], {})
            pair_lbl  = pair_info.get('label', row['pair'])
            emoji     = pair_info.get('emoji', '')

            is_btc   = row['pair'] == 'BTCBRL'
            fmt_rate = (
                (lambda v: f'R$ {v:,.0f}') if is_btc
                else (lambda v: f'R$ {v:.4f}')
            )

            close = row['close_rate'] or 0
            open_ = row['open_rate']  or 0
            change = (
                (close - open_) / open_ * 100
                if open_ > 0 else 0
            )

            items = [
                QTableWidgetItem(f'{emoji} {pair_lbl}'),
                QTableWidgetItem(row['rate_date']),
                QTableWidgetItem(fmt_rate(open_)),
                QTableWidgetItem(fmt_rate(close)),
                QTableWidgetItem(
                    fmt_rate(row['high_rate'] or 0)
                ),
                QTableWidgetItem(
                    fmt_rate(row['low_rate']  or 0)
                ),
                QTableWidgetItem(f'{change:+.2f}%'),
            ]

            # Cor da linha por variação
            row_color = (
                QColor('#1B5E20') if (
                    change >= 0 and self.is_dark_mode
                )
                else QColor('#E8F5E9') if change >= 0
                else QColor('#B71C1C') if self.is_dark_mode
                else QColor('#FFEBEE')
            )

            for j, item in enumerate(items):
                item.setBackground(row_color)
                self.rates_table.setItem(i, j, item)

            # Colorir variação
            chg_item = self.rates_table.item(i, 6)
            if chg_item:
                chg_item.setForeground(
                    QColor('#2ecc71') if change >= 0
                    else QColor('#e74c3c')
                )

        self.rates_table.resizeColumnsToContents()

    def _update_correlation(self):
        """Atualiza a análise de correlação câmbio × gastos"""
        try:
            from modulos.currency_tracker import analyze_currency_impact
            pair   = self.corr_pair_combo.currentData()
            result = analyze_currency_impact(
                self.db, self.user_id, pair
            )

            self.corr_figure.clear()

            if not result.get('has_data'):
                ax = self.corr_figure.add_subplot(111)
                ax.text(
                    0.5, 0.5,
                    result.get('message', 'Sem dados suficientes'),
                    ha='center', va='center',
                    transform=ax.transAxes,
                    color='gray', fontsize=12
                )
                self.corr_canvas.draw()
                self.corr_result_text.setHtml(
                    '<p style="color:gray;">Sem dados para análise.</p>'
                )
                return

            combined = result.get('combined', [])
            if not combined:
                self.corr_canvas.draw()
                return

            months   = [c['month']    for c in combined]
            expenses = [c['expenses'] for c in combined]
            rates    = [c['rate']     for c in combined]

            # Gráfico de dois eixos
            ax1 = self.corr_figure.add_subplot(111)
            ax2 = ax1.twinx()

            pair_info    = CURRENCY_PAIRS.get(pair, {})
            pair_color   = pair_info.get('color', '#16a085')
            expense_color = '#e74c3c'

            x    = range(len(months))
            step = max(1, len(months) // 8)

            bars = ax1.bar(
                x, expenses,
                alpha=0.5, color=expense_color,
                label='Gastos (R$)'
            )
            line = ax2.plot(
                x, rates,
                color=pair_color, linewidth=2.5,
                marker='o', markersize=4,
                label=f'{pair_info.get("label", pair)}'
            )

            ax1.set_ylabel('Gastos Mensais (R$)', color=expense_color)
            ax2.set_ylabel(
                f'Taxa {pair_info.get("label", pair)}',
                color=pair_color
            )
            ax1.tick_params(axis='y', labelcolor=expense_color)
            ax2.tick_params(axis='y', labelcolor=pair_color)

            ax1.set_xticks(list(x)[::step])
            ax1.set_xticklabels(
                months[::step], rotation=45, ha='right', fontsize=7
            )
            ax1.set_title(
                f'Gastos vs {pair_info.get("label", pair)}'
            )

            # Legenda combinada
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(
                lines1 + lines2, labels1 + labels2,
                loc='upper left', fontsize=8
            )
            ax1.grid(True, linestyle='--', alpha=0.3)

            self.corr_figure.tight_layout()
            self.corr_canvas.draw()

            # Resultado textual
            correlation   = result.get('correlation', 0)
            interpretation = result.get('interpretation', '')
            rate_dir      = result.get('rate_direction', 'estável')
            rate_chg      = result.get('rate_change_pct', 0)
            exp_chg       = result.get('expense_change_pct', 0)
            months_n      = result.get('months_analyzed', 0)
            first_rate    = result.get('first_rate', 0)
            last_rate_val = result.get('last_rate', 0)
            inf_impact    = result.get('inflation_impact', 0)

            # Cor da correlação
            if abs(correlation) > 0.5:
                corr_color = '#e74c3c'
            elif abs(correlation) > 0.2:
                corr_color = '#f39c12'
            else:
                corr_color = '#27ae60'

            dir_color = (
                '#e74c3c' if rate_dir == 'subindo' else
                '#27ae60' if rate_dir == 'caindo'  else
                '#7f8c8d'
            )

            is_btc = (pair == 'BTCBRL')
            fmt_r  = (
                (lambda v: f'R$ {v:,.0f}') if is_btc
                else (lambda v: f'R$ {v:.4f}')
            )

            html = f'''
            <h3>📊 Resultado da Análise — {months_n} meses</h3>
            <table width="100%" cellpadding="5">
                <tr>
                    <td><b>Correlação:</b></td>
                    <td><span style="color:{corr_color};
                        font-size:16px; font-weight:bold;">
                        {correlation:+.3f}</span></td>
                    <td><b>Câmbio atual:</b></td>
                    <td>{fmt_r(last_rate_val)}</td>
                </tr>
                <tr>
                    <td><b>Tendência do câmbio:</b></td>
                    <td><span style="color:{dir_color};">
                        {rate_dir.title()}</span></td>
                    <td><b>Câmbio inicial:</b></td>
                    <td>{fmt_r(first_rate)}</td>
                </tr>
                <tr>
                    <td><b>Variação do câmbio:</b></td>
                    <td>{rate_chg:+.2f}%</td>
                    <td><b>Variação dos gastos:</b></td>
                    <td>{exp_chg:+.2f}%</td>
                </tr>
            </table>
            <br>
            <div style="padding:8px; border-left:4px solid {corr_color};
                border-radius:4px; background:#f9f9f9;">
                <b>📝 Interpretação:</b> {interpretation}
            </div>
            '''

            if inf_impact > 0:
                html += f'''
                <br>
                <div style="padding:8px; border-left:4px solid #e67e22;
                    border-radius:4px;">
                    <b>⚠️ Impacto de inflação importada estimado:
                    {inf_impact:.1f}%</b>
                    <br><small>Baseado na correlação e variação
                    cambial no período.</small>
                </div>
                '''

            self.corr_result_text.setHtml(html)

        except Exception as e:
            print(f'[CurrencyDialog] Erro correlação: {e}')
            import traceback
            traceback.print_exc()

    # ══════════════════════════════════════════════════════
    # ATUALIZAÇÃO EM BACKGROUND
    # ══════════════════════════════════════════════════════

    def _start_background_update(self):
        """Inicia atualização em background se necessário"""
        self.update_bar.setVisible(True)
        self.status_label.setText('Verificando atualizações...')
        self.refresh_btn.setEnabled(False)

        t = threading.Thread(
            target=self._background_update_worker,
            daemon=True
        )
        t.start()

    def _background_update_worker(self):
        """Worker que roda em background para atualizar cotações"""
        try:
            if not self.db_path:
                return

            thread_conn = sqlite3.connect(self.db_path)
            thread_conn.row_factory = sqlite3.Row

            from modulos.currency_tracker import (
                create_currency_tables,
                fetch_and_save_latest,
                fetch_history_since,
                needs_update,
            )

            create_currency_tables(thread_conn)

            # Data da primeira transação para histórico
            first = thread_conn.execute(
                '''SELECT MIN(date) as first_date
                   FROM transactions WHERE user_id = ?''',
                (self.user_id,)
            ).fetchone()
            since_date = (
                first['first_date']
                if first and first['first_date']
                else (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            )

            # USD e EUR: usar o tracker padrão
            for pair in ['USDBRL', 'EURBRL']:
                fetch_history_since(thread_conn, pair, since_date)
                fetch_and_save_latest(thread_conn, pair)

            # BTC: usar conversão via USD
            _fetch_btc_history_via_usd(thread_conn, since_date)
            _get_btc_brl_via_usd(thread_conn)

            thread_conn.close()

            # Retornar para thread principal
            QTimer.singleShot(100, self._after_background_update)

        except Exception as e:
            print(f'[CurrencyDialog] Erro background: {e}')
            QTimer.singleShot(
                100, self._after_background_update_error
            )

    def _after_background_update(self):
        """Chamado na thread principal após atualização"""
        self.update_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        self.status_label.setText('✅ Atualizado')
        self._load_from_db()

    def _after_background_update_error(self):
        """Chamado em caso de erro na atualização"""
        self.update_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        self.status_label.setText('⚠️ Erro na atualização')

    def _force_update(self):
        """Força atualização dos dados"""
        self.status_label.setText('Atualizando...')
        self._start_background_update()

    # ══════════════════════════════════════════════════════
    # TEMA
    # ══════════════════════════════════════════════════════

    def apply_theme(self):
        """Aplica o tema ao diálogo"""
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
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px; padding: 0 3px;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #16a085; color: white;
                }
                QPushButton:hover { background-color: #1abc9c; }
                QTableWidget {
                    background-color: #2d3436; color: #ecf0f1;
                    gridline-color: #4b6584;
                    alternate-background-color: #263238;
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
                    border-bottom: none;
                }
                QTabBar::tab:selected {
                    background-color: #16a085;
                }
                QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 3px;
                    background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #16a085;
                }
                QScrollArea {
                    border: none;
                    background-color: #1e272e;
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
                    background-color: #16a085; color: white;
                }
                QPushButton:hover { background-color: #1abc9c; }
                QTableWidget {
                    background-color: white;
                    alternate-background-color: #f8f9fa;
                }
                QHeaderView::section {
                    background-color: #f0f0f0; padding: 5px;
                    border: 1px solid #ccc; font-weight: bold;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333;
                    padding: 8px 12px; border: 1px solid #ccc;
                    border-bottom: none;
                }
                QTabBar::tab:selected {
                    background-color: #16a085; color: white;
                }
                QTextEdit {
                    background-color: white; border: 1px solid #ccc;
                    border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #16a085;
                }
                QScrollArea { border: none; }
            ''')
            plt.style.use('default')

    def closeEvent(self, event):
        """Para os timers ao fechar"""
        self.refresh_timer.stop()
        super().closeEvent(event)

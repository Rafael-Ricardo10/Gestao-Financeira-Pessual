"""
Painel completo da IA - Status, previsões, acurácia e insights
"""
import json
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas
)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QProgressBar, QGroupBox,
    QTextEdit, QScrollArea, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont

from modulos.ai import (
    FinanceAIEngine, TrendAnalyzer, FinanceForecaster,
    get_unread_notifications, mark_notification_read
)


class AIStatusCard(QFrame):
    """Card visual para exibir métricas da IA"""

    def __init__(
        self, title: str, value: str,
        subtitle: str = '', color: str = '#3498db',
        parent=None
    ):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(1)
        self.setMinimumWidth(150)
        self.setMaximumHeight(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            'font-size: 11px; color: #7f8c8d; font-weight: bold;'
        )
        title_label.setAlignment(Qt.AlignCenter)

        value_label = QLabel(value)
        value_label.setStyleSheet(
            f'font-size: 22px; font-weight: bold; color: {color};'
        )
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setObjectName('value_label')

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        if subtitle:
            sub_label = QLabel(subtitle)
            sub_label.setStyleSheet(
                'font-size: 10px; color: #95a5a6;'
            )
            sub_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(sub_label)

        self.setStyleSheet(f'''
            AIStatusCard {{
                border: 1px solid {color};
                border-radius: 8px;
                background-color: transparent;
            }}
        ''')


class AIPanelDialog(QDialog):
    """
    Painel completo da IA com:
    - Status e saúde do modelo
    - Taxa de acerto geral e por tipo
    - Previsões ativas e histórico
    - Notificações da IA
    - Score financeiro
    - Insights automáticos
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('🤖 Painel de Inteligência Artificial')
        self.setMinimumSize(900, 650)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )

        # Inicializar módulos IA
        self.ai_engine  = FinanceAIEngine(
            parent.db_connection, parent.user_id
        )
        self.analyzer   = TrendAnalyzer(
            parent.db_connection, parent.user_id, self.ai_engine
        )
        self.forecaster = FinanceForecaster(
            parent.db_connection, parent.user_id, self.ai_engine
        )

        self._build_ui()
        self.load_all_data()
        self.apply_theme()

        # Auto-refresh a cada 30 segundos
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_all_data)
        self.refresh_timer.start(30000)

    def _build_ui(self):
        """Constrói a interface completa"""
        layout = QVBoxLayout(self)

        # ── Cabeçalho ────────────────────────────────────────
        header = QHBoxLayout()
        title  = QLabel('🤖 Central de Inteligência Artificial')
        title.setStyleSheet(
            'font-size: 18px; font-weight: bold;'
        )
        header.addWidget(title)
        header.addStretch()

        self.refresh_btn = QPushButton('🔄 Atualizar')
        self.refresh_btn.clicked.connect(self.load_all_data)
        header.addWidget(self.refresh_btn)

        self.notif_btn = QPushButton('🔔 Notificações (0)')
        self.notif_btn.clicked.connect(self.show_notifications)
        header.addWidget(self.notif_btn)

        layout.addLayout(header)

        # ── Cards de status ───────────────────────────────────
        self.cards_layout = QHBoxLayout()
        self.card_health  = AIStatusCard(
            'Saúde do Modelo', '...', color='#2ecc71'
        )
        self.card_accuracy = AIStatusCard(
            'Taxa de Acerto', '...%', color='#3498db'
        )
        self.card_predictions = AIStatusCard(
            'Previsões Ativas', '...', color='#f39c12'
        )
        self.card_transactions = AIStatusCard(
            'Transações Vistas', '...', color='#9b59b6'
        )
        self.card_score = AIStatusCard(
            'Score Financeiro', '...', color='#e74c3c'
        )
        self.card_patterns = AIStatusCard(
            'Padrões Aprendidos', '...', color='#1abc9c'
        )

        for card in [
            self.card_health, self.card_accuracy,
            self.card_predictions, self.card_transactions,
            self.card_score, self.card_patterns
        ]:
            self.cards_layout.addWidget(card)

        layout.addLayout(self.cards_layout)

        # ── Abas ─────────────────────────────────────────────
        self.tabs = QTabWidget()

        # Aba 1: Overview
        self.tabs.addTab(self._build_overview_tab(), '📊 Overview')

        # Aba 2: Previsões
        self.tabs.addTab(
            self._build_predictions_tab(), '🔮 Previsões'
        )

        # Aba 3: Acurácia
        self.tabs.addTab(
            self._build_accuracy_tab(), '🎯 Acurácia'
        )

        # Aba 4: Score
        self.tabs.addTab(
            self._build_score_tab(), '🏆 Score Financeiro'
        )

        # Aba 5: Insights
        self.tabs.addTab(
            self._build_insights_tab(), '💡 Insights'
        )

        layout.addWidget(self.tabs)

        # ── Botão fechar ──────────────────────────────────────
        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

    # ══════════════════════════════════════════════════════
    # CONSTRUÇÃO DAS ABAS
    # ══════════════════════════════════════════════════════

    def _build_overview_tab(self) -> QWidget:
        """Aba de visão geral do modelo"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Status do modelo
        status_group  = QGroupBox('📡 Status do Modelo')
        status_layout = QVBoxLayout()

        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        status_layout.addWidget(self.status_text)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Gráfico de acurácia ao longo do tempo
        chart_group  = QGroupBox('📈 Evolução da Acurácia')
        chart_layout = QVBoxLayout()

        self.overview_figure = plt.figure(figsize=(8, 3), dpi=90)
        self.overview_canvas = FigureCanvas(self.overview_figure)
        self.overview_canvas.setMinimumHeight(200)
        chart_layout.addWidget(self.overview_canvas)
        chart_group.setLayout(chart_layout)
        layout.addWidget(chart_group)

        # Padrões aprendidos
        patterns_group  = QGroupBox('🧠 Padrões Aprendidos')
        patterns_layout = QVBoxLayout()

        self.patterns_table = QTableWidget()
        self.patterns_table.setColumnCount(4)
        self.patterns_table.setHorizontalHeaderLabels([
            'Tipo', 'Padrão', 'Amostras', 'Confiança'
        ])
        self.patterns_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.patterns_table.setMaximumHeight(200)
        self.patterns_table.horizontalHeader().setStretchLastSection(
            True
        )
        patterns_layout.addWidget(self.patterns_table)
        patterns_group.setLayout(patterns_layout)
        layout.addWidget(patterns_group)

        return widget

    def _build_predictions_tab(self) -> QWidget:
        """Aba de previsões da IA"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Previsões pendentes
        pending_group  = QGroupBox('⏳ Previsões Pendentes (aguardando confirmação)')
        pending_layout = QVBoxLayout()

        self.pending_table = QTableWidget()
        self.pending_table.setColumnCount(6)
        self.pending_table.setHorizontalHeaderLabels([
            'Data Prevista', 'Tipo', 'Categoria/Descrição',
            'Valor Previsto', 'Confiança', 'Status'
        ])
        self.pending_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.pending_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.pending_table.horizontalHeader().setStretchLastSection(
            True
        )
        pending_layout.addWidget(self.pending_table)
        pending_group.setLayout(pending_layout)
        layout.addWidget(pending_group)

        # Histórico de previsões validadas
        history_group  = QGroupBox('✅ Histórico de Previsões Validadas')
        history_layout = QVBoxLayout()

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels([
            'Data', 'Tipo', 'Previsto', 'Real',
            'Erro %', 'Resultado'
        ])
        self.history_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.history_table.horizontalHeader().setStretchLastSection(
            True
        )
        history_layout.addWidget(self.history_table)
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)

        return widget

    def _build_accuracy_tab(self) -> QWidget:
        """Aba de métricas de acurácia"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Acurácia geral
        general_group  = QGroupBox('🎯 Acurácia Geral')
        general_layout = QVBoxLayout()

        self.accuracy_bar = QProgressBar()
        self.accuracy_bar.setMaximum(100)
        self.accuracy_bar.setMinimumHeight(30)
        self.accuracy_bar.setTextVisible(True)
        general_layout.addWidget(self.accuracy_bar)

        self.accuracy_detail = QLabel()
        self.accuracy_detail.setWordWrap(True)
        general_layout.addWidget(self.accuracy_detail)
        general_group.setLayout(general_layout)
        layout.addWidget(general_group)

        # Acurácia por tipo
        bytype_group  = QGroupBox('📂 Acurácia por Tipo de Previsão')
        bytype_layout = QVBoxLayout()

        self.accuracy_table = QTableWidget()
        self.accuracy_table.setColumnCount(5)
        self.accuracy_table.setHorizontalHeaderLabels([
            'Tipo', 'Total', 'Corretas', 'Acurácia %', 'Erro Médio %'
        ])
        self.accuracy_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.accuracy_table.horizontalHeader().setStretchLastSection(
            True
        )
        bytype_layout.addWidget(self.accuracy_table)
        bytype_group.setLayout(bytype_layout)
        layout.addWidget(bytype_group)

        # Gráfico de acurácia por tipo
        chart_group  = QGroupBox('📊 Distribuição de Resultados')
        chart_layout = QVBoxLayout()

        self.accuracy_figure = plt.figure(figsize=(7, 3), dpi=90)
        self.accuracy_canvas = FigureCanvas(self.accuracy_figure)
        self.accuracy_canvas.setMinimumHeight(200)
        chart_layout.addWidget(self.accuracy_canvas)
        chart_group.setLayout(chart_layout)
        layout.addWidget(chart_group)

        return widget

    def _build_score_tab(self) -> QWidget:
        """Aba do score financeiro"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Score principal
        score_group  = QGroupBox('🏆 Score de Saúde Financeira')
        score_layout = QVBoxLayout()

        score_header = QHBoxLayout()

        self.score_value_label = QLabel('---')
        self.score_value_label.setStyleSheet(
            'font-size: 48px; font-weight: bold; color: #3498db;'
        )
        self.score_value_label.setAlignment(Qt.AlignCenter)

        self.score_class_label = QLabel('Calculando...')
        self.score_class_label.setStyleSheet(
            'font-size: 18px; font-weight: bold;'
        )
        self.score_class_label.setAlignment(Qt.AlignCenter)

        score_header.addWidget(self.score_value_label)
        score_header.addWidget(self.score_class_label)
        score_layout.addLayout(score_header)

        self.score_bar = QProgressBar()
        self.score_bar.setMaximum(1000)
        self.score_bar.setMinimumHeight(25)
        score_layout.addWidget(self.score_bar)
        score_group.setLayout(score_layout)
        layout.addWidget(score_group)

        # Detalhes do score
        details_group  = QGroupBox('📋 Detalhes do Score')
        details_layout = QVBoxLayout()

        self.score_details_table = QTableWidget()
        self.score_details_table.setColumnCount(3)
        self.score_details_table.setHorizontalHeaderLabels([
            'Componente', 'Pontos', 'Barra'
        ])
        self.score_details_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.score_details_table.horizontalHeader().setStretchLastSection(
            True
        )
        details_layout.addWidget(self.score_details_table)
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)

        # Sugestões
        suggest_group  = QGroupBox('💡 Sugestões para Melhorar')
        suggest_layout = QVBoxLayout()

        self.suggestions_text = QTextEdit()
        self.suggestions_text.setReadOnly(True)
        self.suggestions_text.setMaximumHeight(120)
        suggest_layout.addWidget(self.suggestions_text)
        suggest_group.setLayout(suggest_layout)
        layout.addWidget(suggest_group)

        return widget

    def _build_insights_tab(self) -> QWidget:
        """Aba de insights automáticos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel(
            '💡 Insights gerados automaticamente pela IA '
            'com base no seu histórico financeiro'
        )
        title.setWordWrap(True)
        title.setStyleSheet('color: #3498db; font-style: italic;')
        layout.addWidget(title)

        self.insights_text = QTextEdit()
        self.insights_text.setReadOnly(True)
        layout.addWidget(self.insights_text)

        return widget

    # ══════════════════════════════════════════════════════
    # CARREGAMENTO DE DADOS
    # ══════════════════════════════════════════════════════

    def load_all_data(self):
        """Carrega todos os dados do painel"""
        try:
            self._load_status_cards()
            self._load_overview()
            self._load_predictions()
            self._load_accuracy()
            self._load_score()
            self._load_insights()
            self._update_notification_badge()
        except Exception as e:
            print(f'[AIPanelDialog] Erro ao carregar: {e}')
            import traceback
            traceback.print_exc()

    def _load_status_cards(self):
        """Atualiza os cards de status"""
        status = self.ai_engine.get_model_status()
        score  = self.ai_engine.get_financial_score()

        # Saúde
        health_map = {
            'iniciando':    ('Iniciando', '#e74c3c'),
            'aprendendo':   ('Aprendendo', '#e67e22'),
            'desenvolvendo': ('Desenvolvendo', '#f1c40f'),
            'treinado':     ('Treinado', '#2ecc71'),
            'maduro':       ('Maduro ⭐', '#27ae60'),
        }
        health_label, health_color = health_map.get(
            status.get('health', 'iniciando'),
            ('Iniciando', '#e74c3c')
        )

        self._update_card(
            self.card_health, health_label, health_color
        )
        self._update_card(
            self.card_accuracy,
            f"{status.get('accuracy_general', 0):.1f}%",
            '#3498db'
        )
        self._update_card(
            self.card_predictions,
            str(status.get('pending_predictions', 0)),
            '#f39c12'
        )
        self._update_card(
            self.card_transactions,
            str(status.get('transactions_seen', 0)),
            '#9b59b6'
        )
        self._update_card(
            self.card_score,
            str(score.get('score', 0)),
            '#e74c3c'
        )
        self._update_card(
            self.card_patterns,
            str(status.get('patterns_learned', 0)),
            '#1abc9c'
        )

    def _update_card(self, card, value: str, color: str):
        """Atualiza valor de um card"""
        label = card.findChild(QLabel, 'value_label')
        if label:
            label.setText(value)
            label.setStyleSheet(
                f'font-size: 22px; font-weight: bold; color: {color};'
            )

    def _load_overview(self):
        """Carrega aba de visão geral"""
        status = self.ai_engine.get_model_status()

        last_trained = status.get('last_trained', 'Nunca')
        if last_trained and last_trained != 'Nunca':
            try:
                dt           = datetime.strptime(
                    last_trained, '%Y-%m-%d %H:%M:%S'
                )
                last_trained = dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                pass

        status_html = f'''
        <table style="width:100%">
            <tr>
                <td><b>🔬 Saúde do Modelo:</b></td>
                <td>{status.get('health', 'iniciando').title()}</td>
                <td><b>📚 Transações Aprendidas:</b></td>
                <td>{status.get('transactions_seen', 0)}</td>
            </tr>
            <tr>
                <td><b>🎯 Acurácia Geral:</b></td>
                <td>{status.get('accuracy_general', 0):.1f}%</td>
                <td><b>⏰ Último Treino:</b></td>
                <td>{last_trained}</td>
            </tr>
            <tr>
                <td><b>🔮 Total de Previsões:</b></td>
                <td>{status.get('total_predictions', 0)}</td>
                <td><b>✅ Previsões Corretas:</b></td>
                <td>{status.get('correct_predictions', 0)}</td>
            </tr>
            <tr>
                <td><b>⏳ Pendentes:</b></td>
                <td>{status.get('pending_predictions', 0)}</td>
                <td><b>🧠 Padrões:</b></td>
                <td>{status.get('patterns_learned', 0)}</td>
            </tr>
        </table>
        '''
        self.status_text.setHtml(status_html)

        # Gráfico de acurácia ao longo do tempo
        accuracy_log = self.parent().db_connection.execute(
            '''SELECT log_date, accuracy_general
               FROM ai_accuracy_log
               WHERE user_id = ?
               ORDER BY log_date DESC
               LIMIT 20''',
            (self.parent().user_id,)
        ).fetchall()

        self.overview_figure.clear()
        ax = self.overview_figure.add_subplot(111)

        if accuracy_log:
            dates  = [r['log_date'][:10]  for r in reversed(accuracy_log)]
            values = [r['accuracy_general'] for r in reversed(accuracy_log)]
            ax.plot(dates, values, 'b-o', linewidth=2, markersize=5)
            ax.fill_between(
                range(len(dates)), values, alpha=0.3, color='blue'
            )
            ax.set_xticks(range(len(dates)))
            ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=8)
            ax.set_ylabel('Acurácia %')
            ax.set_title('Evolução da Acurácia da IA')
            ax.set_ylim(0, 100)
            ax.grid(True, linestyle='--', alpha=0.5)
        else:
            ax.text(
                0.5, 0.5,
                'Aguardando dados para plotar acurácia...',
                ha='center', va='center',
                transform=ax.transAxes, color='gray'
            )
            ax.set_title('Evolução da Acurácia da IA')

        self.overview_figure.tight_layout()
        self.overview_canvas.draw()

        # Padrões aprendidos
        patterns_rows = self.parent().db_connection.execute(
            '''SELECT pattern_type, pattern_key,
                      sample_count, confidence
               FROM ai_patterns
               WHERE user_id = ?
               ORDER BY sample_count DESC
               LIMIT 50''',
            (self.parent().user_id,)
        ).fetchall()

        self.patterns_table.setRowCount(len(patterns_rows))
        for i, row in enumerate(patterns_rows):
            type_map = {
                'category':    'Categoria',
                'description': 'Descrição',
                'weekly':      'Semanal',
                'monthly':     'Mensal'
            }
            self.patterns_table.setItem(
                i, 0,
                QTableWidgetItem(
                    type_map.get(row['pattern_type'], row['pattern_type'])
                )
            )
            self.patterns_table.setItem(
                i, 1, QTableWidgetItem(str(row['pattern_key'])[:40])
            )
            self.patterns_table.setItem(
                i, 2, QTableWidgetItem(str(row['sample_count']))
            )

            conf_pct = int((row['confidence'] or 0) * 100)
            conf_bar = QProgressBar()
            conf_bar.setMaximum(100)
            conf_bar.setValue(conf_pct)
            conf_bar.setFormat(f'{conf_pct}%')
            self.patterns_table.setCellWidget(i, 3, conf_bar)

        self.patterns_table.resizeColumnsToContents()

    def _load_predictions(self):
        """Carrega previsões pendentes e histórico"""
        # Pendentes
        pending = self.parent().db_connection.execute(
            '''SELECT p.*, c.name AS cat_name
               FROM ai_predictions p
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.user_id = ? AND p.status = 'pendente'
               ORDER BY p.target_date ASC''',
            (self.parent().user_id,)
        ).fetchall()

        self.pending_table.setRowCount(len(pending))
        for i, p in enumerate(pending):
            self.pending_table.setItem(
                i, 0, QTableWidgetItem(p['target_date'])
            )

            type_map = {
                'entrada': '💰 Entrada',
                'saida':   '💸 Saída'
            }
            self.pending_table.setItem(
                i, 1,
                QTableWidgetItem(
                    type_map.get(p['predicted_type'], p['predicted_type'])
                )
            )

            ref = (
                p['cat_name'] or p['description'] or 'Desconhecido'
            )
            self.pending_table.setItem(
                i, 2, QTableWidgetItem(str(ref)[:40])
            )
            self.pending_table.setItem(
                i, 3,
                QTableWidgetItem(f"R$ {p['predicted_amount']:,.2f}")
            )

            conf_pct  = int((p['confidence'] or 0) * 100)
            conf_item = QTableWidgetItem(f'{conf_pct}%')
            conf_item.setForeground(
                QColor('#2ecc71') if conf_pct >= 70 else
                QColor('#e67e22') if conf_pct >= 40 else
                QColor('#e74c3c')
            )
            self.pending_table.setItem(i, 4, conf_item)
            self.pending_table.setItem(
                i, 5, QTableWidgetItem('⏳ Aguardando')
            )

        self.pending_table.resizeColumnsToContents()

        # Histórico validado
        history = self.parent().db_connection.execute(
            '''SELECT p.*, v.actual_amount, v.error_percentage,
                      v.is_correct, c.name AS cat_name
               FROM ai_predictions p
               JOIN ai_validations v ON v.prediction_id = p.id
               LEFT JOIN categories c ON p.category_id = c.id
               WHERE p.user_id = ?
               ORDER BY v.validation_date DESC
               LIMIT 30''',
            (self.parent().user_id,)
        ).fetchall()

        self.history_table.setRowCount(len(history))
        for i, h in enumerate(history):
            self.history_table.setItem(
                i, 0, QTableWidgetItem(h['actual_date'] or h['target_date'])
            )
            ref = h['cat_name'] or h['description'] or '---'
            self.history_table.setItem(
                i, 1, QTableWidgetItem(str(ref)[:30])
            )
            self.history_table.setItem(
                i, 2,
                QTableWidgetItem(f"R$ {h['predicted_amount']:,.2f}")
            )
            self.history_table.setItem(
                i, 3,
                QTableWidgetItem(
                    f"R$ {h['actual_amount']:,.2f}"
                    if h['actual_amount'] else '---'
                )
            )
            self.history_table.setItem(
                i, 4,
                QTableWidgetItem(
                    f"{h['error_percentage']:.1f}%"
                    if h['error_percentage'] is not None else '---'
                )
            )

            result_item = QTableWidgetItem(
                '✅ Correto' if h['is_correct'] else '❌ Incorreto'
            )
            result_item.setForeground(
                QColor('#2ecc71') if h['is_correct']
                else QColor('#e74c3c')
            )
            self.history_table.setItem(i, 5, result_item)

        self.history_table.resizeColumnsToContents()

    def _load_accuracy(self):
        """Carrega métricas de acurácia"""
        acc = self.forecaster.get_prediction_accuracy()

        accuracy = acc.get('accuracy', 0)
        self.accuracy_bar.setValue(int(accuracy))
        self.accuracy_bar.setFormat(f'{accuracy:.1f}%')

        if accuracy >= 80:
            color = '#2ecc71'
        elif accuracy >= 60:
            color = '#f1c40f'
        else:
            color = '#e74c3c'

        self.accuracy_bar.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {color}; }}'
        )

        total   = acc.get('total', 0)
        correct = acc.get('correct', 0)
        wrong   = total - correct
        avg_err = acc.get('avg_error', 0)

        self.accuracy_detail.setText(
            f'Total de previsões validadas: {total} | '
            f'Corretas: {correct} | '
            f'Incorretas: {wrong} | '
            f'Erro médio: {avg_err:.1f}%'
        )

        # Tabela por tipo
        by_type = acc.get('by_type', {})
        self.accuracy_table.setRowCount(len(by_type))

        type_labels = {
            'category':    'Por Categoria',
            'description': 'Por Descrição',
            'weekly':      'Padrão Semanal',
            'monthly':     'Padrão Mensal'
        }

        for i, (tipo, data) in enumerate(by_type.items()):
            self.accuracy_table.setItem(
                i, 0,
                QTableWidgetItem(type_labels.get(tipo, tipo))
            )
            self.accuracy_table.setItem(
                i, 1, QTableWidgetItem(str(data.get('total', 0)))
            )
            self.accuracy_table.setItem(
                i, 2, QTableWidgetItem(str(data.get('correct', 0)))
            )

            acc_pct = data.get('accuracy', 0)
            acc_item = QTableWidgetItem(f"{acc_pct:.1f}%")
            acc_item.setForeground(
                QColor('#2ecc71') if acc_pct >= 70 else
                QColor('#e67e22') if acc_pct >= 50 else
                QColor('#e74c3c')
            )
            self.accuracy_table.setItem(i, 3, acc_item)
            self.accuracy_table.setItem(
                i, 4,
                QTableWidgetItem(
                    f"{data.get('avg_error', 0):.1f}%"
                )
            )

        self.accuracy_table.resizeColumnsToContents()

        # Gráfico pizza - corretas vs incorretas
        self.accuracy_figure.clear()
        ax = self.accuracy_figure.add_subplot(111)

        if total > 0:
            sizes  = [correct, wrong]
            labels = [
                f'Corretas\n({correct})',
                f'Incorretas\n({wrong})'
            ]
            colors = ['#2ecc71', '#e74c3c']
            explode = (0.05, 0)

            ax.pie(
                sizes, labels=labels, colors=colors,
                autopct='%1.1f%%', explode=explode,
                startangle=90,
                textprops={'fontsize': 9}
            )
            ax.set_title('Distribuição de Resultados das Previsões')
        else:
            ax.text(
                0.5, 0.5,
                'Sem previsões validadas ainda',
                ha='center', va='center',
                transform=ax.transAxes, color='gray'
            )

        self.accuracy_figure.tight_layout()
        self.accuracy_canvas.draw()

    def _load_score(self):
        """Carrega score financeiro"""
        score_data = self.ai_engine.get_financial_score()

        score    = score_data.get('score', 0)
        class_   = score_data.get('classification', '---')
        details  = score_data.get('details', {})
        suggests = score_data.get('suggestions', [])

        self.score_value_label.setText(str(score))
        self.score_class_label.setText(class_)
        self.score_bar.setValue(score)

        # Cor do score
        if score >= 700:
            color = '#2ecc71'
        elif score >= 500:
            color = '#f1c40f'
        else:
            color = '#e74c3c'

        self.score_value_label.setStyleSheet(
            f'font-size: 48px; font-weight: bold; color: {color};'
        )
        self.score_bar.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {color}; }}'
        )

        # Tabela de detalhes
        components = [
            ('💰 Taxa de Poupança',    'savings_score',      250),
            ('📊 Consistência Receita', 'income_consistency', 200),
            ('✂️ Controle de Gastos',  'expense_control',    200),
            ('📂 Uso de Categorias',   'category_score',     150),
            ('🤖 Bônus IA',            'ai_score',           100),
            ('📈 Tendência Positiva',  'trend_score',        100),
        ]

        self.score_details_table.setRowCount(len(components))

        for i, (label, key, max_pts) in enumerate(components):
            pts = details.get(key, 0)
            self.score_details_table.setItem(
                i, 0, QTableWidgetItem(label)
            )
            self.score_details_table.setItem(
                i, 1, QTableWidgetItem(f'{pts}/{max_pts}')
            )

            bar = QProgressBar()
            bar.setMaximum(max_pts)
            bar.setValue(pts)
            bar.setFormat(f'{pts}/{max_pts}')
            self.score_details_table.setCellWidget(i, 2, bar)

        self.score_details_table.resizeColumnsToContents()

        # Sugestões
        suggestions_html = '<ul>'
        for s in suggests:
            suggestions_html += f'<li>{s}</li>'
        suggestions_html += '</ul>'
        self.suggestions_text.setHtml(suggestions_html)

    def _load_insights(self):
        """Carrega insights automáticos"""
        trend_result = self.analyzer.analyze(months=6)
        cat_summaries = self.analyzer.get_category_trend_summary()

        html = '<h3>🔍 Análise Geral do Período (6 meses)</h3>'

        if trend_result.get('has_data'):
            insights = trend_result.get('insights', [])
            for ins in insights:
                color_map = {
                    'positive':  '#27ae60',
                    'warning':   '#e67e22',
                    'attention': '#f39c12',
                    'critical':  '#e74c3c',
                    'info':      '#3498db'
                }
                color = color_map.get(ins.get('type', 'info'), '#333')
                html += (
                    f'<p style="color:{color}; margin:5px 0;">'
                    f'{ins.get("emoji", "")} {ins.get("message", "")}'
                    f'</p>'
                )
        else:
            html += (
                '<p style="color:gray;">'
                'ℹ️ Adicione mais transações para gerar insights.'
                '</p>'
            )

        if cat_summaries:
            html += '<h3>📂 Tendências por Categoria</h3>'
            for cat in cat_summaries[:8]:
                expense_dir = cat.get('expense_dir', {})
                emoji       = expense_dir.get('emoji', '➡️')
                label       = expense_dir.get('label', 'Estável')
                color       = expense_dir.get('color', '#333')
                avg         = cat.get('avg_expense', 0)

                html += (
                    f'<p style="margin:3px 0;">'
                    f'<b>{cat["category_name"]}</b>: '
                    f'<span style="color:{color};">'
                    f'{emoji} {label}</span> '
                    f'| Média: R$ {avg:,.2f}'
                    f'</p>'
                )

                for ins in cat.get('insights', []):
                    ins_color = '#e67e22'
                    html += (
                        f'<p style="color:{ins_color}; '
                        f'margin-left:15px; font-size:12px;">'
                        f'↳ {ins.get("emoji", "")} '
                        f'{ins.get("message", "")}'
                        f'</p>'
                    )

        self.insights_text.setHtml(html)

    # ══════════════════════════════════════════════════════
    # NOTIFICAÇÕES
    # ══════════════════════════════════════════════════════

    def _update_notification_badge(self):
        """Atualiza badge de notificações"""
        notifs = get_unread_notifications(
            self.parent().db_connection,
            self.parent().user_id
        )
        count = len(notifs)
        self.notif_btn.setText(
            f'🔔 Notificações ({count})'
            if count > 0 else '🔔 Notificações'
        )
        if count > 0:
            self.notif_btn.setStyleSheet(
                'background-color: #e74c3c; color: white;'
            )
        else:
            self.notif_btn.setStyleSheet('')

    def show_notifications(self):
        """Mostra painel de notificações da IA"""
        notifs = get_unread_notifications(
            self.parent().db_connection,
            self.parent().user_id
        )

        dialog = QDialog(self)
        dialog.setWindowTitle('🔔 Notificações da IA')
        dialog.setMinimumSize(500, 400)
        layout = QVBoxLayout(dialog)

        if not notifs:
            label = QLabel('✅ Nenhuma notificação nova.')
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            c_layout = QVBoxLayout(content)

            for notif in notifs:
                card   = QFrame()
                card.setFrameStyle(QFrame.Box)
                c_card = QVBoxLayout(card)

                priority_colors = {
                    'high':   '#e74c3c',
                    'normal': '#3498db',
                    'low':    '#2ecc71'
                }
                color = priority_colors.get(
                    notif['priority'], '#3498db'
                )

                title_lbl = QLabel(
                    f'<b style="color:{color};">'
                    f'{notif["title"]}</b>'
                )
                msg_lbl   = QLabel(notif['message'])
                msg_lbl.setWordWrap(True)
                date_lbl  = QLabel(
                    f'<small style="color:gray;">'
                    f'{notif["created_at"]}</small>'
                )

                mark_btn = QPushButton('✓ Marcar como lida')
                mark_btn.clicked.connect(
                    lambda _, nid=notif['id']:
                    self._mark_read_and_refresh(nid, dialog)
                )

                c_card.addWidget(title_lbl)
                c_card.addWidget(msg_lbl)
                c_card.addWidget(date_lbl)
                c_card.addWidget(mark_btn)
                c_layout.addWidget(card)

            scroll.setWidget(content)
            layout.addWidget(scroll)

        close_btn = QPushButton('Fechar')
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)
        dialog.exec_()
        self._update_notification_badge()

    def _mark_read_and_refresh(self, notif_id: int, dialog):
        """Marca notificação como lida e fecha dialog"""
        mark_notification_read(
            self.parent().db_connection, notif_id
        )
        self._update_notification_badge()
        dialog.accept()

    # ══════════════════════════════════════════════════════
    # TEMA
    # ══════════════════════════════════════════════════════

    def apply_theme(self):
        """Aplica o tema ao painel"""
        if self.is_dark_mode:
            self.setStyleSheet('''
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px; color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px;
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
                QTabBar::tab:selected { background-color: #3498db; }
                QTextEdit {
                    background-color: #2d3436; color: #ecf0f1;
                    border: 1px solid #4b6584; border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 5px;
                    text-align: center; background-color: #2d3436;
                    color: #ecf0f1;
                }
                AIStatusCard {
                    background-color: #2d3436;
                }
            ''')
            plt.style.use('dark_background')
        else:
            self.setStyleSheet('''
                QDialog { background-color: #f9f9f9; }
                QLabel { color: #333; }
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
                    border: 1px solid #ccc; background-color: white;
                }
                QTabBar::tab {
                    background-color: #f0f0f0; color: #333;
                    padding: 8px 12px; border: 1px solid #ccc;
                }
                QTabBar::tab:selected {
                    background-color: #2196F3; color: white;
                }
                QTextEdit {
                    background-color: white; border: 1px solid #ccc;
                    border-radius: 4px;
                }
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 5px;
                    text-align: center;
                }
            ''')
            plt.style.use('default')

    def closeEvent(self, event):
        """Para o timer ao fechar"""
        self.refresh_timer.stop()
        super().closeEvent(event)

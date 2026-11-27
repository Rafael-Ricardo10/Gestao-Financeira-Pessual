"""
Diálogos para gerenciamento de categorias
"""
import sqlite3

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QRadioButton, QProgressBar,
    QMessageBox, QTableWidget, QTableWidgetItem,
    QWidget, QComboBox, QListWidget, QListWidgetItem,
    QAbstractItemView
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


def apply_category_rules(db_connection, user_id: int,
                          category_id: int = None):
    """
    Aplica as regras de categoria automaticamente.
    Ignora APENAS as transações ESPECÍFICAS vinculadas
    a empréstimos, não todas com o mesmo nome.
    """
    try:
        if category_id:
            rules = db_connection.execute(
                """SELECT cr.*, c.name as cat_name
                   FROM category_rules cr
                   JOIN categories c ON cr.category_id = c.id
                   WHERE cr.user_id = ? AND cr.category_id = ?
                   ORDER BY cr.id""",
                (user_id, category_id)
            ).fetchall()
        else:
            rules = db_connection.execute(
                """SELECT cr.*, c.name as cat_name
                   FROM category_rules cr
                   JOIN categories c ON cr.category_id = c.id
                   WHERE cr.user_id = ?
                   ORDER BY cr.id""",
                (user_id,)
            ).fetchall()

        if not rules:
            return 0

        # IDs de categorias de empréstimo (protegidas)
        loan_category_ids    = set()
        # IDs ESPECÍFICOS de transações de empréstimo
        loan_transaction_ids = set()

        try:
            tabela_loans = db_connection.execute(
                """SELECT COUNT(*) FROM sqlite_master
                   WHERE type='table' AND name='loans'"""
            ).fetchone()[0] > 0

            if tabela_loans:
                loans = db_connection.execute(
                    """SELECT category_id FROM loans
                       WHERE user_id = ? AND category_id IS NOT NULL""",
                    (user_id,)
                ).fetchall()
                loan_category_ids = {
                    l['category_id'] for l in loans
                }

                # Apenas a transação ESPECÍFICA de recebimento
                recv = db_connection.execute(
                    """SELECT transaction_id FROM loans
                       WHERE user_id = ?
                       AND transaction_id IS NOT NULL""",
                    (user_id,)
                ).fetchall()
                loan_transaction_ids.update(
                    r['transaction_id'] for r in recv
                )

                # Apenas as transações ESPECÍFICAS de pagamento
                pays = db_connection.execute(
                    """SELECT lp.transaction_id
                       FROM loan_payments lp
                       JOIN loans l ON lp.loan_id = l.id
                       WHERE l.user_id = ?
                       AND lp.transaction_id IS NOT NULL""",
                    (user_id,)
                ).fetchall()
                loan_transaction_ids.update(
                    p['transaction_id'] for p in pays
                )
        except Exception:
            pass

        total_atualizadas = 0

        for rule in rules:
            # Não aplicar em categorias de empréstimo
            if rule['category_id'] in loan_category_ids:
                continue

            rule_text  = rule['rule_text'].lower()
            match_type = rule['match_type']

            # Buscar transações que NÃO são de empréstimo
            # pelo ID específico, não pelo nome
            if loan_transaction_ids:
                placeholders = ','.join(
                    '?' * len(loan_transaction_ids)
                )
                transactions = db_connection.execute(
                    f"""SELECT id, description, category_id
                        FROM transactions
                        WHERE user_id = ?
                        AND (category_id IS NULL
                             OR category_id != ?)
                        AND id NOT IN ({placeholders})
                        AND (category_id IS NULL
                             OR category_id NOT IN (
                                 SELECT category_id FROM loans
                                 WHERE user_id = ?
                                 AND category_id IS NOT NULL
                             ))""",
                    [user_id, rule['category_id']]
                    + list(loan_transaction_ids)
                    + [user_id]
                ).fetchall()
            else:
                transactions = db_connection.execute(
                    """SELECT id, description, category_id
                       FROM transactions
                       WHERE user_id = ?
                       AND (category_id IS NULL
                            OR category_id != ?)""",
                    (user_id, rule['category_id'])
                ).fetchall()

            for trans in transactions:
                desc  = trans['description'].lower()
                match = False

                if match_type == 'contains':
                    match = rule_text in desc
                elif match_type == 'starts_with':
                    match = desc.startswith(rule_text)
                elif match_type == 'exact':
                    match = desc == rule_text

                if match:
                    db_connection.execute(
                        """UPDATE transactions
                           SET category_id = ?
                           WHERE id = ?""",
                        (rule['category_id'], trans['id'])
                    )
                    total_atualizadas += 1

        if total_atualizadas > 0:
            db_connection.commit()

        return total_atualizadas

    except Exception as e:
        print(f"[category_dialogs] Erro ao aplicar regras: {e}")
        return 0


class DescriptionSelectorWidget(QWidget):
    """
    Widget para selecionar descrições reais das transações
    como regras de categorização automática.

    - Lista esquerda: descrições disponíveis
      (com busca, ocultando as já usadas em outras categorias)
    - Lista direita: descrições selecionadas
    - Botões para mover entre as listas
    """

    def __init__(self, db_connection, user_id,
                 parent=None, is_dark_mode=False,
                 current_category_id=None):
        super().__init__(parent)
        self.db_connection       = db_connection
        self.user_id             = user_id
        self.is_dark_mode        = is_dark_mode
        self.current_category_id = current_category_id
        self._all_descriptions   = []
        self._used_descriptions  = set()

        self._build_ui()
        self._load_used_descriptions()
        self._load_descriptions()

    def _build_ui(self):
        """Constrói a interface do seletor"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(
            "💡 Selecione as descrições para categorizar "
            "automaticamente as transações.\n"
            "Descrições já usadas em outras categorias "
            "não aparecem na lista."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #2196F3; font-style: italic;")
        main_layout.addWidget(hint)

        # ── Busca ─────────────────────────────────────────────
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "🔍 Filtrar descrições disponíveis..."
        )
        self.search_input.textChanged.connect(self._filter_available)
        main_layout.addWidget(self.search_input)

        # ── Duas listas lado a lado ───────────────────────────
        lists_layout = QHBoxLayout()

        # Lista esquerda - disponíveis
        left_layout = QVBoxLayout()
        left_label  = QLabel("📋 Descrições disponíveis:")
        left_label.setStyleSheet("font-weight: bold;")

        self.count_available_label = QLabel("0 disponíveis")
        self.count_available_label.setStyleSheet(
            "color: gray; font-size: 11px;"
        )

        self.available_list = QListWidget()
        self.available_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.available_list.setMinimumHeight(180)
        self.available_list.doubleClicked.connect(self._add_selected)

        left_layout.addWidget(left_label)
        left_layout.addWidget(self.count_available_label)
        left_layout.addWidget(self.available_list)
        lists_layout.addLayout(left_layout)

        # Botões do meio
        mid_layout = QVBoxLayout()
        mid_layout.addStretch()

        self.add_btn = QPushButton("▶")
        self.add_btn.setToolTip(
            "Adicionar selecionadas (duplo clique também funciona)"
        )
        self.add_btn.setFixedWidth(40)
        self.add_btn.clicked.connect(self._add_selected)

        self.add_all_btn = QPushButton("▶▶")
        self.add_all_btn.setToolTip("Adicionar todas visíveis")
        self.add_all_btn.setFixedWidth(40)
        self.add_all_btn.clicked.connect(self._add_all_visible)

        self.remove_btn = QPushButton("◀")
        self.remove_btn.setToolTip(
            "Remover selecionadas (duplo clique também funciona)"
        )
        self.remove_btn.setFixedWidth(40)
        self.remove_btn.clicked.connect(self._remove_selected)

        self.remove_all_btn = QPushButton("◀◀")
        self.remove_all_btn.setToolTip("Remover todas")
        self.remove_all_btn.setFixedWidth(40)
        self.remove_all_btn.clicked.connect(self._remove_all)

        mid_layout.addWidget(self.add_btn)
        mid_layout.addWidget(self.add_all_btn)
        mid_layout.addSpacing(10)
        mid_layout.addWidget(self.remove_btn)
        mid_layout.addWidget(self.remove_all_btn)
        mid_layout.addStretch()
        lists_layout.addLayout(mid_layout)

        # Lista direita - selecionadas
        right_layout = QVBoxLayout()
        right_label  = QLabel("✅ Descrições selecionadas:")
        right_label.setStyleSheet("font-weight: bold;")

        self.counter_label = QLabel("0 selecionadas")
        self.counter_label.setStyleSheet(
            "color: gray; font-size: 11px;"
        )

        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.selected_list.setMinimumHeight(180)
        self.selected_list.doubleClicked.connect(self._remove_selected)

        right_layout.addWidget(right_label)
        right_layout.addWidget(self.counter_label)
        right_layout.addWidget(self.selected_list)
        lists_layout.addLayout(right_layout)

        main_layout.addLayout(lists_layout)

    def _load_used_descriptions(self):
        """
        Carrega descrições já vinculadas a OUTRAS categorias.
        A categoria atual (em edição) é excluída desta verificação
        para que suas próprias descrições apareçam na lista direita.
        """
        try:
            rules_table_exists = self.db_connection.execute(
                """SELECT COUNT(*) FROM sqlite_master
                   WHERE type='table' AND name='category_rules'"""
            ).fetchone()[0] > 0

            if not rules_table_exists:
                self._used_descriptions = set()
                return

            if self.current_category_id:
                # Edição: excluir regras da categoria atual
                rules = self.db_connection.execute(
                    """SELECT rule_text FROM category_rules
                       WHERE user_id = ?
                       AND category_id != ?""",
                    (self.user_id, self.current_category_id)
                ).fetchall()
            else:
                # Criação: todas as regras existentes
                rules = self.db_connection.execute(
                    """SELECT rule_text FROM category_rules
                       WHERE user_id = ?""",
                    (self.user_id,)
                ).fetchall()

            self._used_descriptions = {
                r['rule_text'] for r in rules
            }

        except Exception as e:
            print(
                f"[DescriptionSelector] Erro ao carregar usadas: {e}"
            )
            self._used_descriptions = set()

    def _load_descriptions(self):
        """
        Carrega descrições únicas das transações.

        Regras:
        1. Ignora transações ESPECÍFICAS de empréstimo (por ID)
        2. Ignora descrições já usadas em OUTRAS categorias
        3. Descrições da categoria atual ficam disponíveis
           (aparecerão na lista direita ao chamar
            set_selected_descriptions)
        """
        try:
            # IDs específicos de transações de empréstimo
            loan_transaction_ids = set()
            try:
                tabela_loans = self.db_connection.execute(
                    """SELECT COUNT(*) FROM sqlite_master
                       WHERE type='table' AND name='loans'"""
                ).fetchone()[0] > 0

                if tabela_loans:
                    recv = self.db_connection.execute(
                        """SELECT transaction_id FROM loans
                           WHERE user_id = ?
                           AND transaction_id IS NOT NULL""",
                        (self.user_id,)
                    ).fetchall()
                    loan_transaction_ids.update(
                        r['transaction_id'] for r in recv
                    )

                    pays = self.db_connection.execute(
                        """SELECT lp.transaction_id
                           FROM loan_payments lp
                           JOIN loans l ON lp.loan_id = l.id
                           WHERE l.user_id = ?
                           AND lp.transaction_id IS NOT NULL""",
                        (self.user_id,)
                    ).fetchall()
                    loan_transaction_ids.update(
                        p['transaction_id'] for p in pays
                    )
            except Exception:
                pass

            # Buscar descrições únicas excluindo transações
            # específicas de empréstimo (pelo ID, não pelo nome)
            if loan_transaction_ids:
                placeholders = ','.join(
                    '?' * len(loan_transaction_ids)
                )
                rows = self.db_connection.execute(
                    f"""SELECT DISTINCT description
                        FROM transactions
                        WHERE user_id = ?
                        AND id NOT IN ({placeholders})
                        ORDER BY description COLLATE NOCASE""",
                    [self.user_id] + list(loan_transaction_ids)
                ).fetchall()
            else:
                rows = self.db_connection.execute(
                    """SELECT DISTINCT description
                       FROM transactions
                       WHERE user_id = ?
                       ORDER BY description COLLATE NOCASE""",
                    (self.user_id,)
                ).fetchall()

            # Filtrar descrições já usadas em OUTRAS categorias
            self._all_descriptions = [
                r['description'] for r in rows
                if r['description'] not in self._used_descriptions
            ]

            self._refresh_available_list()

        except Exception as e:
            print(f"[DescriptionSelector] Erro ao carregar: {e}")

    def _refresh_available_list(self, filter_text=""):
        """
        Atualiza a lista de disponíveis respeitando:
        1. Filtro de busca
        2. Descrições já selecionadas (lista direita)
        3. Descrições usadas em outras categorias
        """
        self.available_list.clear()

        # Descrições já na lista direita
        selected = set(self.get_selected_descriptions())

        count = 0
        for desc in self._all_descriptions:
            # Não mostrar as já selecionadas na lista direita
            if desc in selected:
                continue
            # Aplicar filtro de busca
            if (filter_text and
                    filter_text.lower() not in desc.lower()):
                continue

            item = QListWidgetItem(desc)
            item.setToolTip(desc)
            self.available_list.addItem(item)
            count += 1

        self.count_available_label.setText(f"{count} disponíveis")

    def _filter_available(self, text):
        """Filtra a lista de disponíveis"""
        self._refresh_available_list(text)

    def _add_selected(self):
        """Move itens selecionados para a lista direita"""
        items = self.available_list.selectedItems()
        if not items:
            return

        for item in items:
            desc = item.text()
            existing = self.selected_list.findItems(
                desc, Qt.MatchExactly
            )
            if not existing:
                new_item = QListWidgetItem(desc)
                new_item.setToolTip(desc)
                self.selected_list.addItem(new_item)

        self._refresh_available_list(self.search_input.text())
        self._update_counter()

    def _add_all_visible(self):
        """Adiciona todos os itens visíveis da lista esquerda"""
        for i in range(self.available_list.count()):
            item = self.available_list.item(i)
            desc = item.text()
            existing = self.selected_list.findItems(
                desc, Qt.MatchExactly
            )
            if not existing:
                new_item = QListWidgetItem(desc)
                new_item.setToolTip(desc)
                self.selected_list.addItem(new_item)

        self._refresh_available_list(self.search_input.text())
        self._update_counter()

    def _remove_selected(self):
        """Remove itens selecionados da lista direita"""
        items = self.selected_list.selectedItems()
        if not items:
            return

        for item in items:
            self.selected_list.takeItem(
                self.selected_list.row(item)
            )

        self._refresh_available_list(self.search_input.text())
        self._update_counter()

    def _remove_all(self):
        """Remove todos os itens da lista direita"""
        self.selected_list.clear()
        self._refresh_available_list(self.search_input.text())
        self._update_counter()

    def _update_counter(self):
        """Atualiza o contador de selecionadas"""
        count = self.selected_list.count()
        self.counter_label.setText(f"{count} selecionada(s)")

    def get_selected_descriptions(self) -> list:
        """Retorna lista de descrições selecionadas"""
        return [
            self.selected_list.item(i).text()
            for i in range(self.selected_list.count())
        ]

    def set_selected_descriptions(self, descriptions: list):
        """
        Define as descrições já selecionadas (para edição).
        Estas aparecem na lista direita e somem da esquerda.
        """
        self.selected_list.clear()
        for desc in descriptions:
            item = QListWidgetItem(desc)
            item.setToolTip(desc)
            self.selected_list.addItem(item)

        self._refresh_available_list(self.search_input.text())
        self._update_counter()


class AddCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Categoria")
        self.setMinimumWidth(600)
        self.setMinimumHeight(650)
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )

        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()
        self.category_name_input.setPlaceholderText(
            "Digite o nome da categoria"
        )

        # Grupo de tipo de meta
        self.goal_group  = QGroupBox("Tipo de Meta:")
        self.goal_layout = QVBoxLayout()

        self.no_goal_radio      = QRadioButton("Sem Meta")
        self.payment_goal_radio = QRadioButton("Meta de Quitação")
        self.savings_goal_radio = QRadioButton(
            "Meta de Guardar Dinheiro"
        )

        self.no_goal_radio.setChecked(True)
        self.no_goal_radio.toggled.connect(self.toggle_goal_options)
        self.payment_goal_radio.toggled.connect(self.toggle_goal_options)
        self.savings_goal_radio.toggled.connect(self.toggle_goal_options)

        self.goal_layout.addWidget(self.no_goal_radio)
        self.goal_layout.addWidget(self.payment_goal_radio)
        self.goal_layout.addWidget(self.savings_goal_radio)
        self.goal_group.setLayout(self.goal_layout)

        self.total_amount_label = QLabel("Valor Total da Meta:")
        self.total_amount_input = QLineEdit()
        self.total_amount_input.setPlaceholderText(
            "Valor total da meta (ex: 20000.00)"
        )
        self.total_amount_input.setEnabled(False)

        # ── Seletor de descrições ─────────────────────────────
        self.rules_group  = QGroupBox(
            "Categorização Automática por Descrição:"
        )
        self.rules_layout = QVBoxLayout()

        # current_category_id=None pois é criação nova
        self.desc_selector = DescriptionSelectorWidget(
            db_connection       = parent.db_connection,
            user_id             = parent.user_id,
            parent              = self,
            is_dark_mode        = self.is_dark_mode,
            current_category_id = None
        )
        self.rules_layout.addWidget(self.desc_selector)
        self.rules_group.setLayout(self.rules_layout)

        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)
        layout.addWidget(self.goal_group)
        layout.addWidget(self.total_amount_label)
        layout.addWidget(self.total_amount_input)
        layout.addWidget(self.rules_group)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QListWidget {
                    padding: 6px; border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QListWidget::item:selected {
                    background-color: #3498db; color: #ecf0f1;
                }
                QListWidget::item:hover {
                    background-color: #2c3e50;
                }
                QRadioButton { color: #ecf0f1; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px;
                    color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 6px 12px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            self.add_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
                "padding: 8px 15px;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
                "padding: 8px 15px;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QLineEdit, QListWidget {
                    padding: 6px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QListWidget::item:selected {
                    background-color: #2196F3; color: white;
                }
                QListWidget::item:hover {
                    background-color: #e3f2fd;
                }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 6px 12px; border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
                "padding: 8px 15px;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
                "padding: 8px 15px;"
            )

    def toggle_goal_options(self, checked):
        """Ativa/desativa campo de valor total"""
        self.total_amount_input.setEnabled(
            self.payment_goal_radio.isChecked() or
            self.savings_goal_radio.isChecked()
        )

    def add_category(self):
        """Adiciona uma nova categoria ao banco de dados"""
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(
                self, "Erro",
                "O nome da categoria não pode estar vazio."
            )
            return

        total_amount    = 0
        is_payment_goal = 0
        is_savings_goal = 0

        if self.payment_goal_radio.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro",
                        "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro",
                    "O valor total deve ser um número válido."
                )
                return

        elif self.savings_goal_radio.isChecked():
            is_savings_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro",
                        "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro",
                    "O valor total deve ser um número válido."
                )
                return

        try:
            column_exists = self.parent().db_connection.execute(
                "SELECT COUNT(*) FROM pragma_table_info('categories') "
                "WHERE name='is_savings_goal'"
            ).fetchone()[0] > 0

            if column_exists:
                self.parent().db_connection.execute(
                    '''INSERT INTO categories
                       (user_id, name, total_amount,
                        is_payment_goal, is_savings_goal)
                       VALUES (?, ?, ?, ?, ?)''',
                    (self.parent().user_id, category_name,
                     total_amount, is_payment_goal, is_savings_goal)
                )
            else:
                self.parent().db_connection.execute(
                    '''INSERT INTO categories
                       (user_id, name, total_amount, is_payment_goal)
                       VALUES (?, ?, ?, ?)''',
                    (self.parent().user_id, category_name,
                     total_amount, is_payment_goal)
                )

            self.parent().db_connection.commit()

            # Buscar ID da categoria criada
            category_id = self.parent().db_connection.execute(
                'SELECT id FROM categories '
                'WHERE user_id = ? AND name = ?',
                (self.parent().user_id, category_name)
            ).fetchone()['id']

            # Salvar descrições selecionadas como regras
            descriptions = self.desc_selector.get_selected_descriptions()
            rules_salvas = 0

            for desc in descriptions:
                try:
                    self.parent().db_connection.execute(
                        """INSERT OR IGNORE INTO category_rules
                           (user_id, category_id, rule_text,
                            match_type)
                           VALUES (?, ?, ?, 'exact')""",
                        (self.parent().user_id, category_id, desc)
                    )
                    rules_salvas += 1
                except Exception:
                    pass

            if rules_salvas > 0:
                self.parent().db_connection.commit()

            # Aplicar regras imediatamente
            atualizadas = apply_category_rules(
                self.parent().db_connection,
                self.parent().user_id,
                category_id
            )

            msg = "Categoria adicionada com sucesso!"
            if rules_salvas > 0:
                msg += (
                    f"\n\n✅ {rules_salvas} descrição(ões) vinculada(s)."
                )
            if atualizadas > 0:
                msg += (
                    f"\n🔄 {atualizadas} transação(ões) "
                    f"categorizadas automaticamente!"
                )

            QMessageBox.information(self, "Sucesso", msg)
            self.accept()

        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Erro",
                f"A categoria '{category_name}' já existe."
            )


class EditCategoryDialog(QDialog):
    def __init__(self, parent=None, category_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Categoria")
        self.setMinimumWidth(600)
        self.setMinimumHeight(680)
        self.category_id  = category_id
        self.is_dark_mode = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )

        self.category_name_label = QLabel("Nome da Categoria:")
        self.category_name_input = QLineEdit()

        # Grupo de tipo de meta
        self.goal_group  = QGroupBox("Tipo de Meta:")
        self.goal_layout = QVBoxLayout()

        self.no_goal_radio      = QRadioButton("Sem Meta")
        self.payment_goal_radio = QRadioButton("Meta de Quitação")
        self.savings_goal_radio = QRadioButton(
            "Meta de Guardar Dinheiro"
        )

        self.no_goal_radio.toggled.connect(self.toggle_goal_options)
        self.payment_goal_radio.toggled.connect(self.toggle_goal_options)
        self.savings_goal_radio.toggled.connect(self.toggle_goal_options)

        self.goal_layout.addWidget(self.no_goal_radio)
        self.goal_layout.addWidget(self.payment_goal_radio)
        self.goal_layout.addWidget(self.savings_goal_radio)
        self.goal_group.setLayout(self.goal_layout)

        self.total_amount_label = QLabel("Valor Total da Meta:")
        self.total_amount_input = QLineEdit()
        self.total_amount_input.setPlaceholderText(
            "Valor total da meta (ex: 20000.00)"
        )

        self.progress_label = QLabel("Progresso da Meta:")
        self.progress_bar   = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_info  = QLabel()

        # ── Seletor de descrições ─────────────────────────────
        self.rules_group  = QGroupBox(
            "Categorização Automática por Descrição:"
        )
        self.rules_layout = QVBoxLayout()

        # current_category_id=category_id para edição
        self.desc_selector = DescriptionSelectorWidget(
            db_connection       = parent.db_connection,
            user_id             = parent.user_id,
            parent              = self,
            is_dark_mode        = self.is_dark_mode,
            current_category_id = category_id
        )
        self.rules_layout.addWidget(self.desc_selector)

        apply_btn = QPushButton("🔄 Aplicar Regras Agora")
        apply_btn.clicked.connect(self.apply_rules_now)
        self.rules_layout.addWidget(apply_btn)

        self.rules_group.setLayout(self.rules_layout)

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_category)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.category_name_label)
        layout.addWidget(self.category_name_input)
        layout.addWidget(self.goal_group)
        layout.addWidget(self.total_amount_label)
        layout.addWidget(self.total_amount_input)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_info)
        layout.addWidget(self.rules_group)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.load_category_data()
        self.load_rules()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel {
                    color: #ecf0f1;
                    font-weight: bold;
                    margin-top: 5px;
                }
                QLineEdit, QListWidget {
                    padding: 6px; border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QListWidget::item:selected {
                    background-color: #3498db; color: #ecf0f1;
                }
                QListWidget::item:hover {
                    background-color: #2c3e50;
                }
                QRadioButton { color: #ecf0f1; }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px;
                    color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 6px 12px; border-radius: 4px;
                    font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
                QProgressBar {
                    border: 1px solid #4b6584; border-radius: 5px;
                    text-align: center; background-color: #2d3436;
                }
                QProgressBar::chunk {
                    background-color: #2ecc71;
                    width: 10px; margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
                "padding: 8px 15px;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
                "padding: 8px 15px;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QLineEdit, QListWidget {
                    padding: 6px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QListWidget::item:selected {
                    background-color: #2196F3; color: white;
                }
                QListWidget::item:hover {
                    background-color: #e3f2fd;
                }
                QGroupBox {
                    border: 1px solid #ccc; border-radius: 5px;
                    margin-top: 10px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    padding: 6px 12px; border-radius: 4px;
                    font-weight: bold;
                }
                QProgressBar {
                    border: 1px solid #ccc; border-radius: 5px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    width: 10px; margin: 0.5px;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
                "padding: 8px 15px;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
                "padding: 8px 15px;"
            )

    def toggle_goal_options(self, checked):
        """Ativa/desativa campos de meta"""
        has_goal = (
            self.payment_goal_radio.isChecked() or
            self.savings_goal_radio.isChecked()
        )
        self.total_amount_input.setEnabled(has_goal)
        self.progress_bar.setVisible(has_goal)
        self.progress_label.setVisible(has_goal)
        self.progress_info.setVisible(has_goal)

    def load_rules(self):
        """Carrega as regras existentes como descrições selecionadas"""
        try:
            rules = self.parent().db_connection.execute(
                """SELECT rule_text FROM category_rules
                   WHERE user_id = ? AND category_id = ?
                   ORDER BY rule_text""",
                (self.parent().user_id, self.category_id)
            ).fetchall()

            descriptions = [r['rule_text'] for r in rules]
            self.desc_selector.set_selected_descriptions(descriptions)

        except Exception as e:
            print(f"[EditCategory] Erro ao carregar regras: {e}")

    def apply_rules_now(self):
        """Aplica as regras imediatamente"""
        self._save_rules_to_db()

        atualizadas = apply_category_rules(
            self.parent().db_connection,
            self.parent().user_id,
            self.category_id
        )

        if atualizadas > 0:
            QMessageBox.information(
                self, "Regras Aplicadas",
                f"✅ {atualizadas} transação(ões) categorizadas!"
            )
        else:
            QMessageBox.information(
                self, "Regras Aplicadas",
                "Nenhuma transação nova encontrada para categorizar."
            )

    def _save_rules_to_db(self):
        """
        Sincroniza as regras do banco com as selecionadas no widget.
        Remove as que foram removidas e adiciona as novas.
        """
        try:
            descriptions_atuais = set(
                self.desc_selector.get_selected_descriptions()
            )

            # Buscar regras existentes
            rules_existentes = self.parent().db_connection.execute(
                """SELECT rule_text FROM category_rules
                   WHERE user_id = ? AND category_id = ?""",
                (self.parent().user_id, self.category_id)
            ).fetchall()
            rules_existentes_set = {
                r['rule_text'] for r in rules_existentes
            }

            # Remover as que não estão mais selecionadas
            para_remover = rules_existentes_set - descriptions_atuais
            for rule_text in para_remover:
                self.parent().db_connection.execute(
                    """DELETE FROM category_rules
                       WHERE user_id = ? AND category_id = ?
                       AND rule_text = ?""",
                    (self.parent().user_id,
                     self.category_id, rule_text)
                )

            # Adicionar as novas
            para_adicionar = descriptions_atuais - rules_existentes_set
            for desc in para_adicionar:
                self.parent().db_connection.execute(
                    """INSERT OR IGNORE INTO category_rules
                       (user_id, category_id, rule_text, match_type)
                       VALUES (?, ?, ?, 'exact')""",
                    (self.parent().user_id,
                     self.category_id, desc)
                )

            self.parent().db_connection.commit()

        except Exception as e:
            print(f"[EditCategory] Erro ao salvar regras: {e}")

    def load_category_data(self):
        """Carrega dados da categoria"""
        category = self.parent().db_connection.execute(
            'SELECT * FROM categories WHERE id = ?',
            (self.category_id,)
        ).fetchone()

        self.category_name_input.setText(category['name'])

        column_exists = self.parent().db_connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('categories') "
            "WHERE name='is_savings_goal'"
        ).fetchone()[0] > 0

        is_payment_goal = category['is_payment_goal'] == 1
        is_savings_goal = (
            category['is_savings_goal'] == 1
            if column_exists else False
        )

        if is_payment_goal:
            self.payment_goal_radio.setChecked(True)
        elif is_savings_goal:
            self.savings_goal_radio.setChecked(True)
        else:
            self.no_goal_radio.setChecked(True)

        total_amount = category['total_amount'] or 0
        self.total_amount_input.setText(str(total_amount))
        self.total_amount_input.setEnabled(
            is_payment_goal or is_savings_goal
        )

        has_goal = is_payment_goal or is_savings_goal
        self.progress_bar.setVisible(has_goal)
        self.progress_label.setVisible(has_goal)
        self.progress_info.setVisible(has_goal)

        if has_goal and total_amount > 0:
            if is_payment_goal:
                total_accumulated = self.parent().db_connection.execute(
                    """SELECT SUM(amount) FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'saida'""",
                    (self.parent().user_id, self.category_id)
                ).fetchone()[0] or 0
            else:
                total_accumulated = self.parent().db_connection.execute(
                    """SELECT SUM(amount) FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'entrada'""",
                    (self.parent().user_id, self.category_id)
                ).fetchone()[0] or 0

            progress_percentage = min(
                100,
                int((total_accumulated / total_amount) * 100)
            ) if total_amount > 0 else 0

            self.progress_bar.setValue(progress_percentage)
            remaining = total_amount - total_accumulated

            if is_payment_goal:
                self.progress_info.setText(
                    f"Pago: R$ {total_accumulated:.2f} de "
                    f"R$ {total_amount:.2f} ({progress_percentage}%)\n"
                    f"Restante: R$ {remaining:.2f}"
                )
            else:
                self.progress_info.setText(
                    f"Guardado: R$ {total_accumulated:.2f} de "
                    f"R$ {total_amount:.2f} ({progress_percentage}%)\n"
                    f"Restante: R$ {remaining:.2f}"
                )

    def save_category(self):
        """Salva as alterações na categoria"""
        category_name = self.category_name_input.text().strip()
        if not category_name:
            QMessageBox.warning(
                self, "Erro",
                "O nome da categoria não pode estar vazio."
            )
            return

        total_amount    = 0
        is_payment_goal = 0
        is_savings_goal = 0

        if self.payment_goal_radio.isChecked():
            is_payment_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro",
                        "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro",
                    "O valor total deve ser um número válido."
                )
                return

        elif self.savings_goal_radio.isChecked():
            is_savings_goal = 1
            try:
                total_amount = float(
                    self.total_amount_input.text().replace(',', '.')
                )
                if total_amount <= 0:
                    QMessageBox.warning(
                        self, "Erro",
                        "O valor total deve ser positivo."
                    )
                    return
            except ValueError:
                QMessageBox.warning(
                    self, "Erro",
                    "O valor total deve ser um número válido."
                )
                return

        try:
            column_exists = self.parent().db_connection.execute(
                "SELECT COUNT(*) FROM pragma_table_info('categories') "
                "WHERE name='is_savings_goal'"
            ).fetchone()[0] > 0

            if column_exists:
                self.parent().db_connection.execute(
                    '''UPDATE categories
                       SET name=?, total_amount=?,
                           is_payment_goal=?, is_savings_goal=?
                       WHERE id=?''',
                    (category_name, total_amount,
                     is_payment_goal, is_savings_goal,
                     self.category_id)
                )
            else:
                self.parent().db_connection.execute(
                    '''UPDATE categories
                       SET name=?, total_amount=?,
                           is_payment_goal=?
                       WHERE id=?''',
                    (category_name, total_amount,
                     is_payment_goal, self.category_id)
                )

            self.parent().db_connection.commit()

            # Sincronizar regras
            self._save_rules_to_db()

            # Aplicar automaticamente
            atualizadas = apply_category_rules(
                self.parent().db_connection,
                self.parent().user_id,
                self.category_id
            )

            msg = "Categoria atualizada com sucesso!"
            if atualizadas > 0:
                msg += (
                    f"\n\n🔄 {atualizadas} transação(ões) "
                    f"categorizadas automaticamente!"
                )

            QMessageBox.information(self, "Sucesso", msg)
            self.accept()

        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Erro",
                f"A categoria '{category_name}' já existe."
            )


class CategoryTransactionsDialog(QDialog):
    """
    Diálogo para ver transações de uma categoria
    com opção de mover para outra categoria.
    """

    def __init__(self, parent=None, category_id=None,
                 category_name=None):
        super().__init__(parent)
        self.category_id   = category_id
        self.category_name = category_name
        self.is_dark_mode  = (
            parent.is_dark_mode
            if hasattr(parent, 'is_dark_mode') else False
        )
        self.setWindowTitle(f"Transações: {category_name}")
        self.resize(750, 580)

        self._build_ui()
        self.load_data()
        self.apply_theme()

    def _build_ui(self):
        """Constrói a interface"""
        layout = QVBoxLayout()

        title = QLabel(f"Categoria: {self.category_name}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Filtros
        filter_layout = QHBoxLayout()
        self.year_combo  = QComboBox()
        self.month_combo = QComboBox()

        from datetime import datetime
        current_year = datetime.now().year
        self.year_combo.addItem("Todos os anos", 0)
        for year in range(current_year, current_year - 5, -1):
            self.year_combo.addItem(str(year), year)
        self.year_combo.setCurrentIndex(1)

        self.month_combo.addItem("Todos os meses", 0)
        for month in range(1, 13):
            from PyQt5.QtCore import QDate
            month_name = QDate(
                2000, month, 1
            ).toString("MMMM").capitalize()
            self.month_combo.addItem(month_name, month)

        self.year_combo.currentIndexChanged.connect(self.load_data)
        self.month_combo.currentIndexChanged.connect(self.load_data)

        filter_layout.addWidget(QLabel("Ano:"))
        filter_layout.addWidget(self.year_combo)
        filter_layout.addWidget(QLabel("Mês:"))
        filter_layout.addWidget(self.month_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Tabela
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "ID", "Data", "Descrição", "Valor", "Tipo"
        ])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # Estatísticas
        stats_group  = QGroupBox("Estatísticas")
        stats_layout = QHBoxLayout()
        self.entries_label = QLabel("Entradas: R$ 0,00")
        self.exits_label   = QLabel("Saídas: R$ 0,00")
        self.balance_label = QLabel("Saldo: R$ 0,00")
        stats_layout.addWidget(self.entries_label)
        stats_layout.addWidget(self.exits_label)
        stats_layout.addWidget(self.balance_label)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Mover transações
        move_group  = QGroupBox(
            "Mover Transação(ões) Selecionada(s)"
        )
        move_layout = QHBoxLayout()

        self.target_category_combo = QComboBox()
        self.load_categories_combo()

        self.move_btn = QPushButton("↔️ Mover para Categoria")
        self.move_btn.clicked.connect(self.move_transactions)

        move_layout.addWidget(QLabel("Para:"))
        move_layout.addWidget(self.target_category_combo, 1)
        move_layout.addWidget(self.move_btn)
        move_group.setLayout(move_layout)
        layout.addWidget(move_group)

        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

        self.setLayout(layout)

    def load_categories_combo(self):
        """Carrega categorias no combo de destino"""
        self.target_category_combo.clear()
        self.target_category_combo.addItem(
            "Selecione uma categoria...", None
        )

        # Excluir categorias de empréstimo do combo
        loan_category_ids = set()
        try:
            tabela_loans = self.parent().db_connection.execute(
                """SELECT COUNT(*) FROM sqlite_master
                   WHERE type='table' AND name='loans'"""
            ).fetchone()[0] > 0
            if tabela_loans:
                loans = self.parent().db_connection.execute(
                    """SELECT category_id FROM loans
                       WHERE user_id = ? AND category_id IS NOT NULL""",
                    (self.parent().user_id,)
                ).fetchall()
                loan_category_ids = {
                    l['category_id'] for l in loans
                }
        except Exception:
            pass

        categories = self.parent().db_connection.execute(
            """SELECT id, name FROM categories
               WHERE user_id = ?
               AND id != ?
               AND (is_hidden = 0 OR is_hidden IS NULL)
               ORDER BY name""",
            (self.parent().user_id, self.category_id)
        ).fetchall()

        for cat in categories:
            if cat['id'] not in loan_category_ids:
                self.target_category_combo.addItem(
                    cat['name'], cat['id']
                )

    def load_data(self):
        """Carrega as transações da categoria"""
        year_val  = self.year_combo.currentData()
        month_val = self.month_combo.currentData()

        query  = """SELECT t.id, t.date, t.description,
                           t.amount, t.transaction_type
                    FROM transactions t
                    WHERE t.user_id = ? AND t.category_id = ?"""
        params = [self.parent().user_id, self.category_id]

        if year_val and year_val > 0:
            query += " AND strftime('%Y', t.date) = ?"
            params.append(str(year_val))
        if month_val and month_val > 0:
            query += " AND strftime('%m', t.date) = ?"
            params.append(f"{month_val:02d}")

        query += " ORDER BY t.date DESC"
        transactions = self.parent().db_connection.execute(
            query, params
        ).fetchall()

        self.table.setRowCount(len(transactions))
        total_entries = total_exits = 0

        for i, t in enumerate(transactions):
            row_color = (
                QColor("#1B5E20") if self.is_dark_mode
                else QColor("#E8F5E9")
            ) if t['transaction_type'] == 'entrada' else (
                QColor("#B71C1C") if self.is_dark_mode
                else QColor("#FFEBEE")
            )

            id_item   = QTableWidgetItem(str(t['id']))
            date_item = QTableWidgetItem(t['date'])
            desc_item = QTableWidgetItem(t['description'])
            val_item  = QTableWidgetItem(f"R$ {t['amount']:,.2f}")
            tipo_item = QTableWidgetItem(t['transaction_type'])

            id_item.setData(Qt.UserRole, t['id'])

            for item in [id_item, date_item, desc_item,
                         val_item, tipo_item]:
                item.setBackground(row_color)

            self.table.setItem(i, 0, id_item)
            self.table.setItem(i, 1, date_item)
            self.table.setItem(i, 2, desc_item)
            self.table.setItem(i, 3, val_item)
            self.table.setItem(i, 4, tipo_item)

            if t['transaction_type'] == 'entrada':
                total_entries += t['amount']
            else:
                total_exits += t['amount']

        self.table.resizeColumnsToContents()

        balance = total_entries - total_exits
        self.entries_label.setText(
            f"Entradas: R$ {total_entries:,.2f}"
        )
        self.exits_label.setText(
            f"Saídas: R$ {total_exits:,.2f}"
        )
        self.balance_label.setText(f"Saldo: R$ {balance:,.2f}")
        self.balance_label.setStyleSheet(
            "color: green; font-weight: bold;"
            if balance >= 0 else
            "color: red; font-weight: bold;"
        )

    def move_transactions(self):
        """Move as transações selecionadas para outra categoria"""
        target_id = self.target_category_combo.currentData()
        if not target_id:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione uma categoria de destino."
            )
            return

        selected_rows = self.table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(
                self, "Aviso",
                "Selecione ao menos uma transação."
            )
            return

        selected_ids = set()
        for item in selected_rows:
            row     = item.row()
            id_item = self.table.item(row, 0)
            if id_item:
                selected_ids.add(id_item.data(Qt.UserRole))

        if not selected_ids:
            return

        # Verificar transações de empréstimo pelo ID específico
        loan_protected = []
        try:
            from modulos.loans import is_loan_transaction
            for trans_id in selected_ids:
                result = is_loan_transaction(
                    self.parent().db_connection, trans_id
                )
                if result.get('is_loan'):
                    loan_protected.append(
                        (trans_id, result.get('loan_name', '?'))
                    )
        except ImportError:
            pass

        ids_para_mover = selected_ids - {
            t[0] for t in loan_protected
        }

        if loan_protected:
            nomes = "\n".join(
                f"• Empréstimo: {nome}"
                for _, nome in loan_protected
            )
            QMessageBox.warning(
                self, "Transações Protegidas",
                f"As seguintes transações fazem parte de empréstimos "
                f"e não podem ser movidas:\n\n{nomes}\n\n"
                f"Apenas as demais serão movidas."
            )

        if not ids_para_mover:
            return

        target_name = self.target_category_combo.currentText()
        reply = QMessageBox.question(
            self, "Confirmar",
            f"Mover {len(ids_para_mover)} transação(ões) para "
            f"'{target_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply != QMessageBox.Yes:
            return

        try:
            for trans_id in ids_para_mover:
                self.parent().db_connection.execute(
                    """UPDATE transactions
                       SET category_id = ?
                       WHERE id = ?""",
                    (target_id, trans_id)
                )
            self.parent().db_connection.commit()

            QMessageBox.information(
                self, "Sucesso",
                f"✅ {len(ids_para_mover)} transação(ões) movidas "
                f"para '{target_name}'!"
            )
            self.load_data()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro",
                f"Erro ao mover transações: {str(e)}"
            )

    def apply_theme(self):
        """Aplica o tema ao diálogo"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QComboBox {
                    padding: 6px; border: 1px solid #4b6584;
                    border-radius: 4px;
                    background-color: #2d3436; color: #ecf0f1;
                }
                QGroupBox {
                    border: 1px solid #4b6584; border-radius: 5px;
                    margin-top: 10px;
                    color: #ecf0f1; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
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
            """)
            self.move_btn.setStyleSheet(
                "background-color: #f39c12; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
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
                QGroupBox::title {
                    subcontrol-origin: margin; left: 10px;
                    padding: 0 3px 0 3px;
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
            """)
            self.move_btn.setStyleSheet(
                "background-color: #FF9800; color: white;"
            )

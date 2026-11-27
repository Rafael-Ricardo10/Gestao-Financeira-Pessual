"""
Diálogos para gerenciamento de notas
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QMessageBox
)


class AddNoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar Nota")
        self.setMinimumWidth(400)
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()
        self.note_input.setMinimumHeight(150)
        self.note_input.setPlaceholderText("Digite sua nota aqui...")

        self.add_button = QPushButton("Adicionar")
        self.add_button.clicked.connect(self.add_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

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
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QTextEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            self.add_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QTextEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
            """)
            self.add_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def add_note(self):
        """Adiciona uma nova nota ao banco de dados"""
        note = self.note_input.toPlainText().strip()
        if not note:
            QMessageBox.warning(
                self, "Erro", "A nota não pode estar vazia."
            )
            return

        self.parent().db_connection.execute(
            'INSERT INTO notes (user_id, note) VALUES (?, ?)',
            (self.parent().user_id, note)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(
            self, "Sucesso", "Nota adicionada com sucesso!"
        )
        self.accept()


class EditNoteDialog(QDialog):
    def __init__(self, parent=None, note_id=None):
        super().__init__(parent)
        self.setWindowTitle("Editar Nota")
        self.setMinimumWidth(400)
        self.note_id = note_id
        self.is_dark_mode = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )

        self.note_label = QLabel("Nota:")
        self.note_input = QTextEdit()
        self.note_input.setMinimumHeight(150)

        self.save_button = QPushButton("Salvar")
        self.save_button.clicked.connect(self.save_note)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.note_label)
        layout.addWidget(self.note_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.load_note_data()
        self.apply_theme(self.is_dark_mode)

    def apply_theme(self, is_dark_mode):
        """Aplica o tema ao diálogo"""
        if is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1e272e; color: #ecf0f1; }
                QLabel { color: #ecf0f1; font-weight: bold; margin-top: 5px; }
                QTextEdit {
                    padding: 8px; border: 1px solid #4b6584;
                    border-radius: 4px; background-color: #2d3436; color: #ecf0f1;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                    background-color: #3498db; color: #ecf0f1;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            self.save_button.setStyleSheet(
                "background-color: #2ecc71; color: #ecf0f1;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1;"
            )
        else:
            self.setStyleSheet("""
                QDialog { background-color: #f9f9f9; }
                QLabel { font-weight: bold; margin-top: 5px; }
                QTextEdit {
                    padding: 8px; border: 1px solid #ccc;
                    border-radius: 4px; background-color: white;
                }
                QPushButton {
                    padding: 8px 15px; border-radius: 4px; font-weight: bold;
                }
            """)
            self.save_button.setStyleSheet(
                "background-color: #4CAF50; color: white;"
            )
            self.cancel_button.setStyleSheet(
                "background-color: #f44336; color: white;"
            )

    def load_note_data(self):
        """Carrega dados da nota"""
        note = self.parent().db_connection.execute(
            'SELECT * FROM notes WHERE id = ?',
            (self.note_id,)
        ).fetchone()
        self.note_input.setText(note['note'])

    def save_note(self):
        """Salva as alterações na nota"""
        note = self.note_input.toPlainText().strip()
        if not note:
            QMessageBox.warning(
                self, "Erro", "A nota não pode estar vazia."
            )
            return

        self.parent().db_connection.execute(
            'UPDATE notes SET note = ? WHERE id = ?',
            (note, self.note_id)
        )
        self.parent().db_connection.commit()

        QMessageBox.information(
            self, "Sucesso", "Nota atualizada com sucesso!"
        )
        self.accept()

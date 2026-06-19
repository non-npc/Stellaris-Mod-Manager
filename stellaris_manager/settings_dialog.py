from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .models import AppPaths


class SettingsDialog(QDialog):
    def __init__(self, paths: AppPaths, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(720, 150)

        self.game_edit = QLineEdit(str(paths.game_dir))
        self.user_edit = QLineEdit(str(paths.user_data_dir))

        form = QFormLayout()
        form.addRow("Stellaris game folder:", self._path_row(self.game_edit, self._browse_game))
        form.addRow("Stellaris user-data folder:", self._path_row(self.user_edit, self._browse_user))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch()
        layout.addWidget(buttons)

    def paths(self) -> AppPaths:
        return AppPaths(
            game_dir=Path(self.game_edit.text().strip()).expanduser(),
            user_data_dir=Path(self.user_edit.text().strip()).expanduser(),
        )

    def _path_row(self, edit: QLineEdit, callback) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(callback)
        layout.addWidget(edit)
        layout.addWidget(button)
        return widget

    def _browse_game(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select Stellaris game folder", self.game_edit.text()
        )
        if directory:
            self.game_edit.setText(directory)

    def _browse_user(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select Stellaris user-data folder", self.user_edit.text()
        )
        if directory:
            self.user_edit.setText(directory)

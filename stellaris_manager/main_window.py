from __future__ import annotations

import subprocess

from PyQt6.QtCore import QSignalBlocker, QThreadPool, Qt
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .compatibility import compatibility_counts, compatibility_label
from .data_store import (
    ModDataError,
    apply_saved_mod_state,
    load_mods,
    read_game_version,
    read_launch_arguments,
    save_enabled_registry_ids,
    save_mod_state,
)
from .models import AppPaths, ModInfo
from .platform_paths import executable_path, save_paths
from .settings_dialog import SettingsDialog
from .workers import FunctionWorker


class MainWindow(QMainWindow):
    ENABLED_COLUMN = 0
    NAME_COLUMN = 1
    VERSION_COLUMN = 2
    REQUIRED_COLUMN = 3
    COMPATIBILITY_COLUMN = 4
    SOURCE_COLUMN = 5
    STATUS_COLUMN = 6

    def __init__(self, paths: AppPaths) -> None:
        super().__init__()
        self.paths = paths
        self.game_version = ""
        self.mods: list[ModInfo] = []
        self.dirty = False
        self.busy = False
        self.launch_after_save = False
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[FunctionWorker] = set()

        self.setWindowTitle("Stellaris Mod Manager")
        self.resize(1120, 720)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.refresh)
        toolbar.addAction(refresh_action)

        central = QWidget()
        layout = QVBoxLayout(central)

        summary = QHBoxLayout()
        self.version_label = QLabel("Game version: unknown")
        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.addWidget(self.version_label)
        summary.addStretch()
        summary.addWidget(self.path_label)
        layout.addLayout(summary)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter mods by name, version, source, or registry ID…")
        self.search_edit.textChanged.connect(self.apply_filter)
        layout.addWidget(self.search_edit)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Enabled", "Mod", "Version", "For Stellaris", "Compatibility", "Source", "Status"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.NAME_COLUMN, QHeaderView.ResizeMode.Stretch)
        for column in (
            self.ENABLED_COLUMN,
            self.VERSION_COLUMN,
            self.REQUIRED_COLUMN,
            self.COMPATIBILITY_COLUMN,
            self.SOURCE_COLUMN,
            self.STATUS_COLUMN,
        ):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        self.up_button = QPushButton("Move Up")
        self.down_button = QPushButton("Move Down")
        self.save_button = QPushButton("Save Mod List")
        self.launch_button = QPushButton("Launch Stellaris")
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        self.save_button.clicked.connect(self.save_mod_list)
        self.launch_button.clicked.connect(self.launch_stellaris)
        controls.addWidget(self.up_button)
        controls.addWidget(self.down_button)
        controls.addStretch()
        controls.addWidget(self.save_button)
        controls.addWidget(self.launch_button)
        layout.addLayout(controls)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

    def refresh(self) -> None:
        if self.busy:
            return
        if self.dirty and not self._confirm_discard_changes():
            return
        self._set_busy(True, "Reading launcher database…")
        worker = FunctionWorker(self._load_snapshot, self.paths)
        worker.signals.succeeded.connect(self._finish_refresh)
        worker.signals.failed.connect(self._refresh_failed)
        self._start_worker(worker)

    def _populate_table(self) -> None:
        blocker = QSignalBlocker(self.table)
        self.table.setRowCount(0)
        for mod in self._ordered_mods():
            row = self.table.rowCount()
            self.table.insertRow(row)

            checkbox = QCheckBox()
            checkbox.setChecked(mod.enabled)
            checkbox.stateChanged.connect(
                lambda state, registry_id=mod.registry_id: self.toggle_mod(registry_id, state)
            )
            checkbox_container = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            self.table.setCellWidget(row, self.ENABLED_COLUMN, checkbox_container)

            name_item = QTableWidgetItem(mod.display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, mod.registry_id)
            name_item.setToolTip(
                f"{mod.registry_id}\n{mod.directory or 'No mod path recorded by launcher'}"
            )
            self.table.setItem(row, self.NAME_COLUMN, name_item)
            self.table.setItem(row, self.VERSION_COLUMN, QTableWidgetItem(mod.version))
            self.table.setItem(row, self.REQUIRED_COLUMN, QTableWidgetItem(mod.required_version))

            label, compatible = compatibility_label(mod.required_version, self.game_version)
            compatibility_item = QTableWidgetItem(label)
            if compatible is True:
                compatibility_item.setForeground(QColor("#2e9f58"))
            elif compatible is False:
                compatibility_item.setForeground(QColor("#d04a4a"))
            else:
                compatibility_item.setForeground(QColor("#b58b2a"))
            self.table.setItem(row, self.COMPATIBILITY_COLUMN, compatibility_item)
            self.table.setItem(row, self.SOURCE_COLUMN, QTableWidgetItem(mod.source))
            self.table.setItem(row, self.STATUS_COLUMN, QTableWidgetItem(mod.status))
        del blocker
        self.apply_filter()

    def toggle_mod(self, registry_id: str, state: int) -> None:
        mod = next((item for item in self.mods if item.registry_id == registry_id), None)
        if not mod:
            return
        enabled = state == Qt.CheckState.Checked.value
        if mod.enabled == enabled:
            return
        self.mods.remove(mod)
        mod.enabled = enabled
        insert_at = sum(item.enabled for item in self.mods)
        self.mods.insert(insert_at, mod)
        self._reindex_mods()
        self.dirty = True
        self._populate_table()
        self._select_registry_id(registry_id)
        self.statusBar().showMessage("Unsaved changes")

    def move_selected(self, direction: int) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, self.NAME_COLUMN)
        if item is None:
            return
        registry_id = str(item.data(Qt.ItemDataRole.UserRole))
        enabled = self._enabled_mods()
        index = next((i for i, mod in enumerate(enabled) if mod.registry_id == registry_id), -1)
        target = index + direction
        if index < 0 or target < 0 or target >= len(enabled):
            self.statusBar().showMessage("Only enabled mods can be reordered")
            return
        enabled[index], enabled[target] = enabled[target], enabled[index]
        disabled = [mod for mod in self.mods if not mod.enabled]
        self.mods = [*enabled, *disabled]
        self._reindex_mods()
        self.dirty = True
        self._populate_table()
        self._select_registry_id(registry_id)
        self.statusBar().showMessage("Unsaved load-order changes")

    def save_mod_list(self) -> bool:
        if self.busy:
            return False
        enabled_ids = [mod.registry_id for mod in self._enabled_mods()]
        ordered_state = [
            (mod.registry_id, mod.enabled) for mod in self._ordered_mods()
        ]
        self._set_busy(True, "Saving mod list…")
        worker = FunctionWorker(
            self._save_snapshot,
            self.paths.dlc_load_file,
            self.paths.manager_database,
            enabled_ids,
            ordered_state,
        )
        worker.signals.succeeded.connect(
            lambda backup, count=len(enabled_ids): self._finish_save(backup, count)
        )
        worker.signals.failed.connect(self._save_failed)
        self._start_worker(worker)
        return True

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.paths, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        new_paths = dialog.paths()
        if not new_paths.game_dir.exists():
            QMessageBox.warning(self, "Invalid game folder", "The selected game folder does not exist.")
            return
        if not new_paths.user_data_dir.exists():
            QMessageBox.warning(
                self, "Invalid user-data folder", "The selected Stellaris user-data folder does not exist."
            )
            return
        self.paths = new_paths
        save_paths(new_paths)
        self.dirty = False
        self.refresh()

    def launch_stellaris(self) -> None:
        if self.busy:
            return
        if self.dirty:
            answer = QMessageBox.question(
                self,
                "Save changes?",
                "Save your mod-list changes before launching Stellaris?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save:
                self.launch_after_save = True
                self.save_mod_list()
                return

        self._launch_process()

    def _launch_process(self) -> None:
        executable = executable_path(self.paths.game_dir)
        if not executable.exists():
            QMessageBox.critical(
                self,
                "Stellaris executable not found",
                f"Expected executable:\n{executable}\n\nChoose the correct game folder in Settings.",
            )
            return
        args = read_launch_arguments(self.paths.launcher_settings)
        try:
            subprocess.Popen(
                [str(executable), *args],
                cwd=self.paths.game_dir,
                start_new_session=True,
            )
        except OSError as exc:
            QMessageBox.critical(self, "Could not launch Stellaris", str(exc))
            return
        self.statusBar().showMessage("Stellaris launched", 10000)

    def apply_filter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        for row in range(self.table.rowCount()):
            values = []
            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)
                if item:
                    values.append(item.text())
                    if column == self.NAME_COLUMN:
                        values.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
            self.table.setRowHidden(row, bool(query) and query not in " ".join(values).casefold())

    def closeEvent(self, event) -> None:
        if self.busy:
            self.statusBar().showMessage("Please wait for the current operation to finish.", 5000)
            event.ignore()
            return
        if self.dirty and not self._confirm_discard_changes():
            event.ignore()
            return
        event.accept()

    def _enabled_mods(self) -> list[ModInfo]:
        return [mod for mod in self._ordered_mods() if mod.enabled]

    def _ordered_mods(self) -> list[ModInfo]:
        return sorted(self.mods, key=lambda mod: mod.sort_order)

    def _reindex_mods(self) -> None:
        enabled_position = 0
        for position, mod in enumerate(self.mods):
            mod.sort_order = position
            if mod.enabled:
                mod.load_order = enabled_position
                enabled_position += 1
            else:
                mod.load_order = None

    def _select_registry_id(self, registry_id: str) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.NAME_COLUMN)
            if item and item.data(Qt.ItemDataRole.UserRole) == registry_id:
                self.table.selectRow(row)
                break

    def _confirm_discard_changes(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Discard changes?",
            "There are unsaved mod-list changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def _show_path_error(self, detail: str) -> None:
        self.version_label.setText("Game version: unavailable")
        self.path_label.setText(str(self.paths.user_data_dir))
        QMessageBox.warning(
            self,
            "Stellaris data not found",
            f"{detail}\n\nOpen Settings and choose the Stellaris game and user-data folders.",
        )

    @staticmethod
    def _load_snapshot(paths: AppPaths) -> tuple[str, list[ModInfo]]:
        version = read_game_version(paths.launcher_settings)
        mods = load_mods(paths.launcher_database, paths.dlc_load_file)
        mods = apply_saved_mod_state(mods, paths.manager_database)
        return version, mods

    @staticmethod
    def _save_snapshot(
        dlc_load_file,
        manager_database,
        enabled_ids: list[str],
        ordered_state: list[tuple[str, bool]],
    ):
        backup = save_enabled_registry_ids(dlc_load_file, enabled_ids)
        save_mod_state(manager_database, ordered_state)
        return backup

    def _finish_refresh(self, result: object) -> None:
        self.game_version, self.mods = result
        self.dirty = False
        self._populate_table()
        self.version_label.setText(f"Game version: {self.game_version or 'unknown'}")
        self.path_label.setText(str(self.paths.user_data_dir))
        enabled_count = sum(mod.enabled for mod in self.mods)
        counts = compatibility_counts(
            [mod.required_version for mod in self.mods], self.game_version
        )
        self.statusBar().showMessage(
            f"{len(self.mods)} available · {enabled_count} enabled · "
            f"{counts['compatible']} compatible · {counts['incompatible']} incompatible · "
            f"{counts['unknown']} unknown"
        )
        self._set_busy(False)

    def _refresh_failed(self, traceback_text: str) -> None:
        self.mods = []
        self._populate_table()
        self._set_busy(False)
        detail = traceback_text.strip().splitlines()[-1]
        self._show_path_error(detail)

    def _finish_save(self, backup: object, count: int) -> None:
        self.dirty = False
        message = f"Saved {count} enabled mods."
        if backup:
            message += f" Backup: {backup.name}"
        self._set_busy(False)
        self.statusBar().showMessage(message, 10000)
        if self.launch_after_save:
            self.launch_after_save = False
            self._launch_process()

    def _save_failed(self, traceback_text: str) -> None:
        self.launch_after_save = False
        self._set_busy(False)
        detail = traceback_text.strip().splitlines()[-1]
        QMessageBox.critical(self, "Could not save mod list", detail)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.busy = busy
        self.table.setEnabled(not busy)
        self.up_button.setEnabled(not busy)
        self.down_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.launch_button.setEnabled(not busy)
        if message:
            self.statusBar().showMessage(message)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor) if busy else self._restore_cursor()

    @staticmethod
    def _restore_cursor() -> None:
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()

    def _start_worker(self, worker: FunctionWorker) -> None:
        self._workers.add(worker)
        worker.signals.finished.connect(lambda current=worker: self._workers.discard(current))
        self.thread_pool.start(worker)


def run_application() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Stellaris Mod Manager")
    app.setOrganizationName("Local")
    from .first_run import resolve_startup_paths

    paths = resolve_startup_paths()
    if paths is None:
        return 0
    window = MainWindow(paths)
    window.show()
    return app.exec()

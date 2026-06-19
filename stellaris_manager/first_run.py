from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from .models import AppPaths
from .platform_paths import (
    default_game_candidates,
    default_user_data_candidates,
    executable_path,
    load_saved_paths,
    save_paths,
)


def resolve_startup_paths() -> AppPaths | None:
    saved = load_saved_paths()
    if saved is not None:
        return saved

    game_hint = _first_existing(default_game_candidates())
    game_dir = _ask_for_game_folder(game_hint)
    if game_dir is None:
        return None

    user_data_dir = _first_valid_user_data(default_user_data_candidates())
    if user_data_dir is None:
        user_data_dir = _ask_for_user_data_folder()
        if user_data_dir is None:
            return None

    paths = AppPaths(game_dir=game_dir, user_data_dir=user_data_dir)
    save_paths(paths)
    return paths


def _ask_for_game_folder(initial: Path | None) -> Path | None:
    current = str(initial or Path.home())
    while True:
        selected = QFileDialog.getExistingDirectory(
            None,
            "Locate your Stellaris game folder",
            current,
        )
        if not selected:
            return None

        game_dir = Path(selected)
        if executable_path(game_dir).exists() and (game_dir / "launcher-settings.json").exists():
            return game_dir

        QMessageBox.warning(
            None,
            "Invalid Stellaris game folder",
            "That folder does not contain the Stellaris executable and "
            "launcher-settings.json. Please select the main Stellaris installation folder.",
        )
        current = selected


def _ask_for_user_data_folder() -> Path | None:
    current = str(Path.home())
    while True:
        selected = QFileDialog.getExistingDirectory(
            None,
            "Locate your Stellaris user-data folder",
            current,
        )
        if not selected:
            return None

        user_dir = Path(selected)
        if (user_dir / "launcher-v2.sqlite").exists():
            return user_dir

        QMessageBox.warning(
            None,
            "Invalid Stellaris user-data folder",
            "That folder does not contain launcher-v2.sqlite. Select the Stellaris folder "
            "inside your Paradox Interactive user-data directory.",
        )
        current = selected


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _first_valid_user_data(candidates: list[Path]) -> Path | None:
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.exists() and (candidate / "launcher-v2.sqlite").exists()
        ),
        None,
    )

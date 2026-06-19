from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from .models import AppPaths


APP_NAME = "StellarisModManager"


def config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "stellaris-mod-manager"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def default_user_data_candidates() -> list[Path]:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        candidates = [
            home / "Documents" / "Paradox Interactive" / "Stellaris",
        ]
        one_drive = os.environ.get("OneDrive")
        if one_drive:
            candidates.append(
                Path(one_drive) / "Documents" / "Paradox Interactive" / "Stellaris"
            )
    elif system == "Darwin":
        candidates = [
            home / "Documents" / "Paradox Interactive" / "Stellaris",
            home / "Library" / "Application Support" / "Paradox Interactive" / "Stellaris",
        ]
    else:
        candidates = [
            home / ".local" / "share" / "Paradox Interactive" / "Stellaris",
            home / "Documents" / "Paradox Interactive" / "Stellaris",
        ]
    return _unique(candidates)


def default_game_candidates() -> list[Path]:
    home = Path.home()
    system = platform.system()
    candidates: list[Path] = []

    if system == "Windows":
        for root in _windows_steam_libraries():
            candidates.append(root / "steamapps" / "common" / "Stellaris")
    elif system == "Darwin":
        candidates.append(
            home
            / "Library"
            / "Application Support"
            / "Steam"
            / "steamapps"
            / "common"
            / "Stellaris"
        )
    else:
        candidates.extend(
            [
                home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Stellaris",
                home / ".steam" / "steam" / "steamapps" / "common" / "Stellaris",
                home / ".steam" / "root" / "steamapps" / "common" / "Stellaris",
            ]
        )
    return _unique(candidates)


def detect_paths() -> AppPaths:
    saved = load_saved_paths()
    game_dir = saved.game_dir if saved and saved.game_dir.exists() else _first_existing(default_game_candidates())
    user_dir = (
        saved.user_data_dir
        if saved and saved.user_data_dir.exists()
        else _first_existing(default_user_data_candidates())
    )
    return AppPaths(game_dir=game_dir or Path(), user_data_dir=user_dir or Path())


def load_saved_paths() -> AppPaths | None:
    path = settings_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppPaths(
            game_dir=Path(data.get("game_dir", "")).expanduser(),
            user_data_dir=Path(data.get("user_data_dir", "")).expanduser(),
        )
    except (OSError, ValueError, TypeError):
        return None


def save_paths(paths: AppPaths) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "game_dir": str(paths.game_dir),
        "user_data_dir": str(paths.user_data_dir),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def executable_path(game_dir: Path) -> Path:
    system = platform.system()
    if system == "Windows":
        return game_dir / "stellaris.exe"
    if system == "Darwin":
        app_binary = game_dir / "stellaris.app" / "Contents" / "MacOS" / "stellaris"
        return app_binary if app_binary.exists() else game_dir / "stellaris"
    return game_dir / "stellaris"


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _windows_steam_libraries() -> list[Path]:
    roots: list[Path] = []
    try:
        import winreg

        registry_locations = [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ]
        for hive, key_name in registry_locations:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    for value_name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(Path(winreg.QueryValueEx(key, value_name)[0]))
                            break
                        except OSError:
                            continue
            except OSError:
                continue
    except ImportError:
        pass

    steam_roots = []
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        program_files = os.environ.get(variable)
        if program_files:
            steam_roots.append(Path(program_files) / "Steam")
    steam_roots = _unique([*roots, *steam_roots])
    for steam_root in steam_roots:
        if steam_root.exists():
            roots.append(steam_root)
            roots.extend(_parse_library_folders(steam_root / "steamapps" / "libraryfolders.vdf"))
    return _unique(roots)


def _parse_library_folders(path: Path) -> list[Path]:
    if not path.exists():
        return []
    roots: list[Path] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith('"path"'):
                pieces = stripped.split('"')
                if len(pieces) >= 4:
                    roots.append(Path(pieces[3].replace("\\\\", "\\")))
    except OSError:
        return []
    return roots

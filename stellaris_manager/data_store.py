from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ModInfo


class ModDataError(RuntimeError):
    pass


def read_game_version(launcher_settings: Path) -> str:
    try:
        payload = json.loads(launcher_settings.read_text(encoding="utf-8-sig"))
        return str(payload.get("rawVersion") or payload.get("version") or "").lstrip("v")
    except (OSError, ValueError, TypeError):
        return ""


def read_launch_arguments(launcher_settings: Path) -> list[str]:
    try:
        payload = json.loads(launcher_settings.read_text(encoding="utf-8-sig"))
        args = payload.get("exeArgs", ["-gdpr-compliant"])
        return [str(item) for item in args] if isinstance(args, list) else ["-gdpr-compliant"]
    except (OSError, ValueError, TypeError):
        return ["-gdpr-compliant"]


def load_enabled_registry_ids(dlc_load_file: Path) -> list[str]:
    payload = _read_dlc_payload(dlc_load_file)
    enabled = payload.get("enabled_mods", [])
    return [str(item) for item in enabled] if isinstance(enabled, list) else []


def load_mods(database: Path, dlc_load_file: Path) -> list[ModInfo]:
    if not database.exists():
        raise ModDataError(f"Launcher database not found: {database}")

    enabled_ids = load_enabled_registry_ids(dlc_load_file)
    enabled_positions = {registry_id: index for index, registry_id in enumerate(enabled_ids)}
    connection = _open_read_only(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                id, steamId, gameRegistryId, displayName, name, version,
                requiredVersion, source, status, dirPath, archivePath
            FROM mods
            ORDER BY lower(COALESCE(displayName, name, gameRegistryId, steamId))
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise ModDataError(f"Could not read launcher database: {exc}") from exc
    finally:
        connection.close()

    mods: list[ModInfo] = []
    seen: set[str] = set()
    for row in rows:
        registry_id = _registry_id(row)
        if not registry_id or registry_id in seen:
            continue
        seen.add(registry_id)
        directory_value = row["dirPath"] or row["archivePath"]
        mods.append(
            ModInfo(
                database_id=str(row["id"]),
                registry_id=registry_id,
                display_name=str(
                    row["displayName"] or row["name"] or row["steamId"] or registry_id
                ),
                version=str(row["version"] or "—"),
                required_version=str(row["requiredVersion"] or "—"),
                source=str(row["source"] or "unknown"),
                status=str(row["status"] or "unknown"),
                directory=Path(directory_value) if directory_value else None,
                enabled=registry_id in enabled_positions,
                load_order=enabled_positions.get(registry_id),
            )
        )

    known = {mod.registry_id for mod in mods}
    for registry_id in enabled_ids:
        if registry_id not in known:
            mods.append(
                ModInfo(
                    database_id="",
                    registry_id=registry_id,
                    display_name=f"Missing launcher entry: {registry_id}",
                    version="—",
                    required_version="—",
                    source="unknown",
                    status="missing",
                    directory=None,
                    enabled=True,
                    load_order=enabled_positions[registry_id],
                )
            )

    return sorted(
        mods,
        key=lambda mod: (
            not mod.enabled,
            mod.load_order if mod.load_order is not None else 10**9,
            mod.display_name.casefold(),
        ),
    )


def load_saved_mod_state(database: Path) -> dict[str, tuple[bool, int]]:
    if not database.exists():
        return {}
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database, timeout=2)
        rows = connection.execute(
            """
            SELECT registry_id, enabled, position
            FROM mod_order
            ORDER BY position
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise ModDataError(f"Could not read mod-manager database: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
    return {
        str(registry_id): (bool(enabled), int(position))
        for registry_id, enabled, position in rows
    }


def apply_saved_mod_state(mods: list[ModInfo], database: Path) -> list[ModInfo]:
    saved = load_saved_mod_state(database)
    if not saved:
        ordered = sorted(
            mods,
            key=lambda mod: (
                not mod.enabled,
                mod.load_order if mod.load_order is not None else 10**9,
                mod.display_name.casefold(),
            ),
        )
    else:
        saved_enabled_ids = {
            registry_id for registry_id, (enabled, _) in saved.items() if enabled
        }
        known_ids = {mod.registry_id for mod in mods}
        for registry_id in saved_enabled_ids - known_ids:
            mods.append(
                ModInfo(
                    database_id="",
                    registry_id=registry_id,
                    display_name=f"Missing launcher entry: {registry_id}",
                    version="—",
                    required_version="—",
                    source="unknown",
                    status="missing",
                    directory=None,
                )
            )

        fallback_position = len(saved)
        for mod in mods:
            state = saved.get(mod.registry_id)
            if state is None:
                mod.enabled = False
                mod.load_order = None
                mod.sort_order = fallback_position
                fallback_position += 1
            else:
                mod.enabled, mod.sort_order = state

        ordered = sorted(
            mods,
            key=lambda mod: (
                not mod.enabled,
                mod.sort_order,
                mod.display_name.casefold(),
            ),
        )

    enabled_position = 0
    for position, mod in enumerate(ordered):
        mod.sort_order = position
        if mod.enabled:
            mod.load_order = enabled_position
            enabled_position += 1
        else:
            mod.load_order = None
    return ordered


def save_mod_state(database: Path, ordered_state: list[tuple[str, bool]]) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database, timeout=2)
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mod_order (
                    registry_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL,
                    position INTEGER NOT NULL
                )
                """
            )
            connection.execute("DELETE FROM mod_order")
            connection.executemany(
                """
                INSERT INTO mod_order (registry_id, enabled, position)
                VALUES (?, ?, ?)
                """,
                [
                    (registry_id, int(enabled), position)
                    for position, (registry_id, enabled) in enumerate(ordered_state)
                ],
            )
    except sqlite3.Error as exc:
        raise ModDataError(f"Could not save mod-manager database: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def save_enabled_registry_ids(dlc_load_file: Path, enabled_ids: list[str]) -> Path | None:
    dlc_load_file.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_dlc_payload(dlc_load_file)
    backup: Path | None = None
    if dlc_load_file.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = dlc_load_file.with_name(f"{dlc_load_file.name}.backup-{timestamp}")
        shutil.copy2(dlc_load_file, backup)

    payload["enabled_mods"] = list(dict.fromkeys(enabled_ids))
    payload.setdefault("disabled_dlcs", [])
    temporary = dlc_load_file.with_suffix(dlc_load_file.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(dlc_load_file)
    return backup


def _open_read_only(database: Path) -> sqlite3.Connection:
    uri = database.resolve().as_uri() + "?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True, timeout=2)
    except sqlite3.Error as exc:
        raise ModDataError(f"Could not open launcher database: {exc}") from exc


def _registry_id(row: sqlite3.Row) -> str:
    if row["gameRegistryId"]:
        return str(row["gameRegistryId"]).replace("\\", "/")
    if row["steamId"]:
        return f"mod/ugc_{row['steamId']}.mod"
    return ""


def _read_dlc_payload(dlc_load_file: Path) -> dict[str, Any]:
    if not dlc_load_file.exists():
        return {"enabled_mods": [], "disabled_dlcs": []}
    try:
        payload = json.loads(dlc_load_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ModDataError(f"Could not read {dlc_load_file}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ModDataError(f"{dlc_load_file} does not contain a JSON object.")
    return payload

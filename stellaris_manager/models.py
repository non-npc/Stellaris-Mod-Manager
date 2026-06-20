from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ModInfo:
    database_id: str
    registry_id: str
    display_name: str
    version: str
    required_version: str
    source: str
    status: str
    directory: Path | None
    enabled: bool = False
    load_order: int | None = None
    sort_order: int = 0


@dataclass(slots=True)
class AppPaths:
    game_dir: Path
    user_data_dir: Path

    @property
    def launcher_database(self) -> Path:
        return self.user_data_dir / "launcher-v2.sqlite"

    @property
    def manager_database(self) -> Path:
        return self.user_data_dir / "stellaris-mod-manager.sqlite"

    @property
    def dlc_load_file(self) -> Path:
        return self.user_data_dir / "dlc_load.json"

    @property
    def launcher_settings(self) -> Path:
        return self.game_dir / "launcher-settings.json"

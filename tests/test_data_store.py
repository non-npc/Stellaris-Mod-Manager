import json
import tempfile
from pathlib import Path
from unittest import TestCase

from stellaris_manager.data_store import (
    apply_saved_mod_state,
    load_enabled_registry_ids,
    load_saved_mod_state,
    save_enabled_registry_ids,
    save_mod_state,
)
from stellaris_manager.models import ModInfo


class DlcLoadTests(TestCase):
    def test_save_preserves_other_fields_and_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dlc_load.json"
            path.write_text(
                json.dumps(
                    {
                        "enabled_mods": ["mod/old.mod"],
                        "disabled_dlcs": ["dlc/test"],
                        "custom": "preserved",
                    }
                ),
                encoding="utf-8",
            )

            backup = save_enabled_registry_ids(path, ["mod/new.mod", "mod/new.mod"])
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(load_enabled_registry_ids(path), ["mod/new.mod"])
            self.assertEqual(payload["disabled_dlcs"], ["dlc/test"])
            self.assertEqual(payload["custom"], "preserved")
            self.assertIsNotNone(backup)
            self.assertTrue(backup.exists())

    def test_mod_manager_database_preserves_enabled_state_and_full_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "manager.sqlite"
            save_mod_state(
                database,
                [
                    ("mod/second.mod", True),
                    ("mod/first.mod", True),
                    ("mod/disabled.mod", False),
                ],
            )

            self.assertEqual(
                load_saved_mod_state(database),
                {
                    "mod/second.mod": (True, 0),
                    "mod/first.mod": (True, 1),
                    "mod/disabled.mod": (False, 2),
                },
            )

    def test_saved_state_is_applied_with_enabled_mods_first(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "manager.sqlite"
            save_mod_state(
                database,
                [
                    ("mod/disabled.mod", False),
                    ("mod/enabled.mod", True),
                ],
            )
            mods = [
                self._mod("mod/enabled.mod", "Enabled"),
                self._mod("mod/disabled.mod", "Disabled"),
                self._mod("mod/new.mod", "New"),
            ]

            ordered = apply_saved_mod_state(mods, database)

            self.assertEqual(
                [mod.registry_id for mod in ordered],
                ["mod/enabled.mod", "mod/disabled.mod", "mod/new.mod"],
            )
            self.assertEqual([mod.enabled for mod in ordered], [True, False, False])
            self.assertEqual([mod.sort_order for mod in ordered], [0, 1, 2])

    @staticmethod
    def _mod(registry_id: str, name: str) -> ModInfo:
        return ModInfo(
            database_id=registry_id,
            registry_id=registry_id,
            display_name=name,
            version="1",
            required_version="1",
            source="local",
            status="ready",
            directory=None,
        )

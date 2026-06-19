import json
import tempfile
from pathlib import Path
from unittest import TestCase

from stellaris_manager.data_store import (
    load_enabled_registry_ids,
    save_enabled_registry_ids,
)


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

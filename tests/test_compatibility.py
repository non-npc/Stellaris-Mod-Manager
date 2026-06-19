from unittest import TestCase

from stellaris_manager.compatibility import compatibility_counts, compatibility_label


class CompatibilityTests(TestCase):
    def test_wildcards_and_exact_versions(self) -> None:
        self.assertEqual(compatibility_label("v4.4.*", "4.4.3"), ("Compatible", True))
        self.assertEqual(compatibility_label("v4.*", "4.4.3"), ("Compatible", True))
        self.assertEqual(compatibility_label("v4.3.*", "4.4.3"), ("Incompatible", False))
        self.assertEqual(compatibility_label("v4.4.3", "4.4.3"), ("Compatible", True))

    def test_numpy_summary(self) -> None:
        self.assertEqual(
            compatibility_counts(["4.4.*", "4.3.*", "—"], "4.4.3"),
            {"compatible": 1, "incompatible": 1, "unknown": 1},
        )

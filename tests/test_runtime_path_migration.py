from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config.settings import migrate_legacy_api_config


class RuntimePathMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_legacy_api_config_moves_atomically_to_runtime_data(self) -> None:
        legacy = self.root / "_internal" / "config" / "api_config.ini"
        runtime = self.root / ".learnanything" / "config" / "api_config.ini"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("[llm]\napi_key = secret\n", encoding="utf-8")

        changed = migrate_legacy_api_config(
            runtime_path=runtime,
            legacy_path=legacy,
            remove_source=True,
        )

        self.assertTrue(changed)
        self.assertEqual(
            runtime.read_text(encoding="utf-8"), "[llm]\napi_key = secret\n"
        )
        self.assertFalse(legacy.exists())

    def test_existing_runtime_config_wins_over_legacy_copy(self) -> None:
        legacy = self.root / "_internal" / "config" / "api_config.ini"
        runtime = self.root / ".learnanything" / "config" / "api_config.ini"
        legacy.parent.mkdir(parents=True)
        runtime.parent.mkdir(parents=True)
        legacy.write_text("legacy", encoding="utf-8")
        runtime.write_text("current", encoding="utf-8")

        changed = migrate_legacy_api_config(
            runtime_path=runtime,
            legacy_path=legacy,
            remove_source=True,
        )

        self.assertFalse(changed)
        self.assertEqual(runtime.read_text(encoding="utf-8"), "current")
        self.assertEqual(legacy.read_text(encoding="utf-8"), "legacy")


if __name__ == "__main__":
    unittest.main()

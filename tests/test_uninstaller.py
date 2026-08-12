from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "uninstaller.py"
SPEC = importlib.util.spec_from_file_location("learnanything_uninstaller", MODULE_PATH)
assert SPEC and SPEC.loader
uninstaller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uninstaller)


class UninstallerSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_manifest(self, install_dir: Path, files: list[str] | None = None) -> Path:
        install_dir.mkdir(parents=True, exist_ok=True)
        (install_dir / uninstaller.MAIN_EXE_NAME).write_bytes(b"main")
        (install_dir / uninstaller.UNINSTALLER_NAME).write_bytes(b"uninstall")
        payload = {
            "product": uninstaller.PRODUCT_NAME,
            "kind": "portable-install",
            "format_version": uninstaller.MANIFEST_FORMAT_VERSION,
            "version": "test",
            "files": files
            or [
                uninstaller.MAIN_EXE_NAME,
                uninstaller.UNINSTALLER_NAME,
                uninstaller.INSTALL_MANIFEST_NAME,
            ],
        }
        path = install_dir / uninstaller.INSTALL_MANIFEST_NAME
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def write_data_marker(self, data_root: Path) -> None:
        data_root.mkdir(parents=True, exist_ok=True)
        (data_root / uninstaller.DATA_MARKER_NAME).write_text(
            json.dumps(
                {
                    "product": uninstaller.PRODUCT_NAME,
                    "kind": "data-root",
                    "format_version": uninstaller.MANIFEST_FORMAT_VERSION,
                }
            ),
            encoding="utf-8",
        )

    def test_load_install_manifest_accepts_owned_release(self) -> None:
        install_dir = self.root / "LearnAnything"
        self.write_manifest(install_dir)

        manifest, files = uninstaller.load_install_manifest(install_dir)

        self.assertEqual(manifest["product"], uninstaller.PRODUCT_NAME)
        self.assertIn(install_dir / uninstaller.MAIN_EXE_NAME, files)
        self.assertIn(install_dir / uninstaller.UNINSTALLER_NAME, files)

    def test_load_install_manifest_rejects_relative_escape(self) -> None:
        install_dir = self.root / "LearnAnything"
        self.write_manifest(
            install_dir,
            [
                uninstaller.MAIN_EXE_NAME,
                uninstaller.UNINSTALLER_NAME,
                uninstaller.INSTALL_MANIFEST_NAME,
                "../outside.txt",
            ],
        )
        with self.assertRaisesRegex(uninstaller.UninstallSafetyError, "越界"):
            uninstaller.load_install_manifest(install_dir)

    def test_load_install_manifest_rejects_absolute_path(self) -> None:
        install_dir = self.root / "LearnAnything"
        self.write_manifest(
            install_dir,
            [
                uninstaller.MAIN_EXE_NAME,
                uninstaller.UNINSTALLER_NAME,
                uninstaller.INSTALL_MANIFEST_NAME,
                "C:/Windows/System32/a.dll",
            ],
        )
        with self.assertRaisesRegex(uninstaller.UninstallSafetyError, "越界"):
            uninstaller.load_install_manifest(install_dir)

    def test_load_install_manifest_rejects_unmarked_directory(self) -> None:
        install_dir = self.root / "random-folder"
        install_dir.mkdir()
        (install_dir / uninstaller.MAIN_EXE_NAME).write_bytes(b"main")
        with self.assertRaisesRegex(uninstaller.UninstallSafetyError, "缺少安全标记"):
            uninstaller.load_install_manifest(install_dir)

    def test_validate_data_root_requires_exact_home_path_and_marker(self) -> None:
        home = self.root / "home"
        data_root = home / ".learnanything"
        self.write_data_marker(data_root)
        self.assertEqual(
            uninstaller.validate_data_root(data_root, home_dir=home), data_root
        )
        with self.assertRaisesRegex(uninstaller.UninstallSafetyError, "不是当前用户"):
            uninstaller.validate_data_root(
                self.root / "other" / ".learnanything", home_dir=home
            )

    def test_validate_data_root_rejects_missing_or_forged_marker(self) -> None:
        home = self.root / "home"
        data_root = home / ".learnanything"
        data_root.mkdir(parents=True)
        with self.assertRaisesRegex(uninstaller.UninstallSafetyError, "缺少安全标记"):
            uninstaller.validate_data_root(data_root, home_dir=home)

        (data_root / uninstaller.DATA_MARKER_NAME).write_text(
            json.dumps({"product": "AnotherApp", "kind": "data-root"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(uninstaller.UninstallSafetyError, "身份标记"):
            uninstaller.validate_data_root(data_root, home_dir=home)

    def test_legacy_config_is_migrated_when_user_data_is_kept(self) -> None:
        home = self.root / "home"
        install_dir = self.root / "LearnAnything"
        legacy_config = install_dir / uninstaller.LEGACY_API_CONFIG_RELATIVE
        legacy_config.parent.mkdir(parents=True)
        legacy_config.write_text("[llm]\napi_key=secret\n", encoding="utf-8")
        (install_dir / uninstaller.LEGACY_API_KEYS_RELATIVE).write_text(
            "[api_keys]\ndeepseek_api_key=old\n", encoding="utf-8"
        )
        data_root = home / ".learnanything"

        pending, directories = uninstaller.handle_legacy_runtime_artifacts(
            install_dir,
            data_root,
            delete_data=False,
            home_dir=home,
        )

        self.assertEqual(pending, [])
        self.assertIn(legacy_config.parent, directories)
        self.assertFalse(legacy_config.exists())
        self.assertEqual(
            (data_root / "config" / "api_config.ini").read_text(encoding="utf-8"),
            "[llm]\napi_key=secret\n",
        )
        self.assertTrue((data_root / uninstaller.DATA_MARKER_NAME).is_file())

    def test_legacy_config_is_deleted_not_migrated_when_data_is_removed(self) -> None:
        home = self.root / "home"
        install_dir = self.root / "LearnAnything"
        legacy_config = install_dir / uninstaller.LEGACY_API_CONFIG_RELATIVE
        legacy_config.parent.mkdir(parents=True)
        legacy_config.write_text("secret", encoding="utf-8")
        data_root = home / ".learnanything"

        pending, _ = uninstaller.handle_legacy_runtime_artifacts(
            install_dir,
            data_root,
            delete_data=True,
            home_dir=home,
        )

        self.assertEqual(pending, [])
        self.assertFalse(legacy_config.exists())
        self.assertFalse(data_root.exists())

    def test_empty_legacy_models_directory_is_removed(self) -> None:
        home = self.root / "home"
        install_dir = self.root / "LearnAnything"
        model_dir = install_dir / uninstaller.LEGACY_MODEL_DIR_RELATIVE
        model_dir.mkdir(parents=True)

        uninstaller.handle_legacy_runtime_artifacts(
            install_dir,
            home / ".learnanything",
            delete_data=False,
            home_dir=home,
        )

        self.assertFalse(model_dir.exists())

    def test_nonempty_legacy_models_directory_is_preserved(self) -> None:
        home = self.root / "home"
        install_dir = self.root / "LearnAnything"
        model_dir = install_dir / uninstaller.LEGACY_MODEL_DIR_RELATIVE
        model_dir.mkdir(parents=True)
        unknown = model_dir / "unknown.bin"
        unknown.write_bytes(b"keep")

        uninstaller.handle_legacy_runtime_artifacts(
            install_dir,
            home / ".learnanything",
            delete_data=False,
            home_dir=home,
        )

        self.assertEqual(unknown.read_bytes(), b"keep")

    def test_manifest_deletion_preserves_unknown_user_file(self) -> None:
        install_dir = self.root / "LearnAnything"
        internal = install_dir / "_internal"
        internal.mkdir(parents=True)
        packaged = internal / "runtime.dll"
        packaged.write_bytes(b"runtime")
        unknown = install_dir / "my-notes.txt"
        unknown.write_text("keep me", encoding="utf-8")
        manifest_path = self.write_manifest(
            install_dir,
            [
                uninstaller.MAIN_EXE_NAME,
                uninstaller.UNINSTALLER_NAME,
                "_internal/runtime.dll",
                uninstaller.INSTALL_MANIFEST_NAME,
            ],
        )
        _, files = uninstaller.load_install_manifest(install_dir)
        deferred = {manifest_path, install_dir / uninstaller.UNINSTALLER_NAME}

        pending = uninstaller.delete_manifest_files(files, deferred=deferred)
        uninstaller.remove_empty_dirs(
            uninstaller.collect_install_dirs(install_dir, files)
        )

        self.assertFalse((install_dir / uninstaller.MAIN_EXE_NAME).exists())
        self.assertFalse(packaged.exists())
        self.assertEqual(unknown.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(set(pending), deferred)

    def test_parse_options(self) -> None:
        cases = [
            ([], (False, False)),
            (["/S"], (True, False)),
            (["--silent", "--delete-data"], (True, True)),
            (["/silent", "/delete-data"], (True, True)),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(uninstaller.parse_options(args), expected)

    def test_deferred_cleanup_script_waits_for_parent_then_retries(self) -> None:
        captured: dict[str, object] = {}

        class DummyProcess:
            pass

        original_popen = uninstaller.subprocess.Popen
        original_tempdir = uninstaller.tempfile.gettempdir
        try:
            uninstaller.tempfile.gettempdir = lambda: str(self.root)

            def fake_popen(args, **kwargs):
                captured["args"] = args
                captured["kwargs"] = kwargs
                return DummyProcess()

            uninstaller.subprocess.Popen = fake_popen
            uninstaller.schedule_deferred_cleanup(
                [self.root / "uninstall.exe"], [self.root / "install"]
            )
        finally:
            uninstaller.subprocess.Popen = original_popen
            uninstaller.tempfile.gettempdir = original_tempdir

        scripts = list(self.root.glob("learnanything-uninstall-*.ps1"))
        self.assertEqual(len(scripts), 1)
        content = scripts[0].read_text(encoding="utf-8-sig")
        self.assertNotIn("Wait-Process", content)
        self.assertIn("Get-Process -Id ([int]$cfg.pid)", content)
        self.assertIn("$wait -lt 1200", content)
        self.assertIn("$attempt -lt 40", content)
        self.assertIn("Test-Path", content)
        self.assertIn("powershell.exe", captured["args"])
        self.assertEqual(Path(captured["kwargs"]["cwd"]), self.root)

    def test_uninstall_shows_final_message_before_scheduling_self_cleanup(self) -> None:
        install_dir = self.root / "LearnAnything"
        self.write_manifest(install_dir)
        events: list[str] = []

        originals = {
            "get_install_dir": uninstaller.get_install_dir,
            "get_data_root": uninstaller.get_data_root,
            "find_running_main_processes": uninstaller.find_running_main_processes,
            "confirm_options": uninstaller.confirm_options,
            "show_info": uninstaller.show_info,
            "schedule_deferred_cleanup": uninstaller.schedule_deferred_cleanup,
        }
        try:
            uninstaller.get_install_dir = lambda: install_dir
            uninstaller.get_data_root = lambda: self.root / "home" / ".learnanything"
            uninstaller.find_running_main_processes = lambda _install_dir: []
            uninstaller.confirm_options = lambda _data_root: (True, False)
            uninstaller.show_info = lambda _message: events.append("message_closed")
            uninstaller.schedule_deferred_cleanup = (
                lambda _files, _directories: events.append("cleanup_scheduled")
            )

            result = uninstaller.uninstall(silent=False, delete_data=False)
        finally:
            for name, value in originals.items():
                setattr(uninstaller, name, value)

        self.assertEqual(result, 0)
        self.assertEqual(events, ["message_closed", "cleanup_scheduled"])


if __name__ == "__main__":
    unittest.main()

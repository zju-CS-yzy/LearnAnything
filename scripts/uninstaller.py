#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LearnAnything portable desktop uninstaller.

The release is distributed as a ZIP instead of a traditional MSI installer.
This program therefore removes only files recorded in the release manifest.
Unknown files placed beside LearnAnything are deliberately preserved.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Iterable, Sequence


PRODUCT_NAME = "LearnAnything"
MAIN_EXE_NAME = "LearnAnything.exe"
UNINSTALLER_NAME = "uninstall.exe"
INSTALL_MANIFEST_NAME = ".learnanything-install.json"
DATA_MARKER_NAME = ".learnanything-data.json"
MANIFEST_FORMAT_VERSION = 1
LEGACY_API_CONFIG_RELATIVE = Path("_internal/config/api_config.ini")
LEGACY_API_KEYS_RELATIVE = Path("_internal/config/api_keys.ini")
LEGACY_MODEL_DIR_RELATIVE = Path("models")

MB_OK = 0x00000000
MB_ICONINFORMATION = 0x00000040
MB_ICONWARNING = 0x00000030
MB_ICONERROR = 0x00000010
MB_YESNO = 0x00000004
MB_YESNOCANCEL = 0x00000003
MB_DEFBUTTON2 = 0x00000100
IDYES = 6
IDNO = 7
IDCANCEL = 2


class UninstallSafetyError(RuntimeError):
    """Raised when an uninstall target fails a safety check."""


def _message_box(message: str, title: str, flags: int = MB_OK) -> int:
    if sys.platform == "win32":
        return ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    print(f"[{title}] {message}")
    return IDYES


def show_error(message: str) -> None:
    _message_box(message, "LearnAnything 卸载失败", MB_OK | MB_ICONERROR)


def show_info(message: str) -> None:
    _message_box(message, "LearnAnything 卸载", MB_OK | MB_ICONINFORMATION)


def get_install_dir() -> Path:
    if not getattr(sys, "frozen", False):
        raise UninstallSafetyError("卸载器只能以打包后的 uninstall.exe 形式运行。")
    return Path(sys.executable).resolve().parent


def get_data_root() -> Path:
    override = os.getenv("LEARNANYTHING_USER_HOME")
    home = Path(override).expanduser() if override else Path.home()
    return home / ".learnanything"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _has_reparse_point(path: Path) -> bool:
    """Reject symlinks/junctions before recursive user-data removal."""
    if path.is_symlink():
        return True
    if sys.platform != "win32" or not path.exists():
        return False
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        invalid = 0xFFFFFFFF
        reparse = 0x0400
        return attrs != invalid and bool(attrs & reparse)
    except Exception:
        return True


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UninstallSafetyError(f"缺少安全标记：{path.name}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise UninstallSafetyError(f"无法读取安全标记：{path.name}") from exc
    if not isinstance(value, dict):
        raise UninstallSafetyError(f"安全标记格式无效：{path.name}")
    return value


def load_install_manifest(install_dir: Path) -> tuple[dict, list[Path]]:
    """Validate the release marker and return safe absolute file targets."""
    install_dir = install_dir.resolve()
    manifest_path = install_dir / INSTALL_MANIFEST_NAME
    manifest = _read_json(manifest_path)

    if manifest.get("product") != PRODUCT_NAME:
        raise UninstallSafetyError("安装清单不属于 LearnAnything。")
    if manifest.get("kind") != "portable-install":
        raise UninstallSafetyError("安装清单类型无效。")
    if manifest.get("format_version") != MANIFEST_FORMAT_VERSION:
        raise UninstallSafetyError("安装清单版本不受支持，请使用同一发布包内的卸载器。")
    if not (install_dir / MAIN_EXE_NAME).is_file():
        raise UninstallSafetyError(f"当前目录中未找到 {MAIN_EXE_NAME}。")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise UninstallSafetyError("安装清单中没有可卸载文件。")

    files: list[Path] = []
    names: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, str) or not raw.strip():
            raise UninstallSafetyError("安装清单包含无效文件名。")
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise UninstallSafetyError(f"安装清单包含越界路径：{raw}")
        target = (install_dir / relative).resolve()
        if not _is_relative_to(target, install_dir):
            raise UninstallSafetyError(f"安装清单包含越界路径：{raw}")
        files.append(target)
        names.add(relative.as_posix().casefold())

    required = {MAIN_EXE_NAME.casefold(), UNINSTALLER_NAME.casefold()}
    if not required.issubset(names):
        raise UninstallSafetyError("安装清单缺少主程序或卸载器记录。")
    return manifest, files


def validate_data_root(data_root: Path, home_dir: Path | None = None) -> Path:
    """Return a validated app-owned data root or raise.

    Recursive deletion is allowed only for the exact current-user path and an
    app-created marker. Reparse points are rejected to avoid following a
    redirected directory into an unrelated location.
    """
    home = (home_dir or Path.home()).resolve()
    expected = home / ".learnanything"
    if data_root.parent.resolve() != home or data_root.name != ".learnanything":
        raise UninstallSafetyError("用户数据目录不是当前用户的 ~/.learnanything，已拒绝删除。")
    if data_root.resolve() != expected.resolve():
        raise UninstallSafetyError("用户数据目录解析到意外位置，已拒绝删除。")
    if _has_reparse_point(data_root):
        raise UninstallSafetyError("用户数据目录是符号链接或目录联接，已拒绝自动删除。")

    marker = _read_json(data_root / DATA_MARKER_NAME)
    if marker.get("product") != PRODUCT_NAME or marker.get("kind") != "data-root":
        raise UninstallSafetyError("用户数据目录缺少有效的 LearnAnything 身份标记。")
    return data_root


def ensure_data_root_for_migration(data_root: Path, home_dir: Path | None = None) -> Path:
    """Create/validate the app data root before preserving a legacy config."""
    home = (home_dir or Path.home()).resolve()
    expected = home / ".learnanything"
    if data_root.parent.resolve() != home or data_root.name != ".learnanything":
        raise UninstallSafetyError("旧配置的迁移目标不是当前用户的 ~/.learnanything。")
    if data_root.exists() and _has_reparse_point(data_root):
        raise UninstallSafetyError("用户数据目录是符号链接或目录联接，无法安全迁移旧配置。")
    data_root.mkdir(parents=True, exist_ok=True)
    if data_root.resolve() != expected.resolve():
        raise UninstallSafetyError("用户数据目录解析到意外位置，无法安全迁移旧配置。")

    marker_path = data_root / DATA_MARKER_NAME
    if marker_path.exists():
        marker = _read_json(marker_path)
        if marker.get("product") != PRODUCT_NAME or marker.get("kind") != "data-root":
            raise UninstallSafetyError("用户数据目录包含无效的 LearnAnything 身份标记。")
    else:
        marker_path.write_text(
            json.dumps(
                {
                    "product": PRODUCT_NAME,
                    "kind": "data-root",
                    "format_version": MANIFEST_FORMAT_VERSION,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return data_root


def handle_legacy_runtime_artifacts(
    install_dir: Path,
    data_root: Path,
    delete_data: bool,
    home_dir: Path | None = None,
) -> tuple[list[Path], list[Path]]:
    """Migrate/delete runtime files created by releases before the manifest.

    These paths are exact, app-owned historical locations. The top-level
    ``models`` directory is removed only when empty; any content is preserved.
    """
    pending: list[Path] = []
    legacy_dirs: list[Path] = []
    config_paths = [
        install_dir / LEGACY_API_CONFIG_RELATIVE,
        install_dir / LEGACY_API_KEYS_RELATIVE,
    ]

    existing_configs = [path for path in config_paths if path.is_file()]
    if existing_configs and not delete_data:
        safe_root = ensure_data_root_for_migration(data_root, home_dir=home_dir)
        target_dir = safe_root / "config"
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in existing_configs:
            target = target_dir / source.name
            if not target.exists():
                temp_target = target.with_name(f".{target.name}.{os.getpid()}.tmp")
                try:
                    shutil.copyfile(source, temp_target)
                    os.replace(temp_target, target)
                finally:
                    if temp_target.exists():
                        temp_target.unlink()

    for path in existing_configs:
        try:
            path.unlink()
        except OSError:
            pending.append(path)
        legacy_dirs.append(path.parent)

    model_dir = install_dir / LEGACY_MODEL_DIR_RELATIVE
    if model_dir.is_dir():
        try:
            model_dir.rmdir()
        except OSError:
            # A non-empty models directory was not used by current releases;
            # preserve its unknown contents instead of deleting recursively.
            pass
    return pending, legacy_dirs


def _normalise_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def find_running_main_processes(install_dir: Path) -> list[int]:
    """Find running LearnAnything.exe processes launched from this package."""
    if sys.platform != "win32":
        return []

    TH32CS_SNAPPROCESS = 0x00000002
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []

    expected = _normalise_path(install_dir / MAIN_EXE_NAME)
    found: list[int] = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.casefold() == MAIN_EXE_NAME.casefold():
                handle = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, entry.th32ProcessID
                )
                if handle:
                    try:
                        size = wintypes.DWORD(32768)
                        buffer = ctypes.create_unicode_buffer(size.value)
                        if kernel32.QueryFullProcessImageNameW(
                            handle, 0, buffer, ctypes.byref(size)
                        ):
                            if _normalise_path(Path(buffer.value)) == expected:
                                found.append(int(entry.th32ProcessID))
                    finally:
                        kernel32.CloseHandle(handle)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def collect_install_dirs(install_dir: Path, files: Iterable[Path]) -> list[Path]:
    dirs: set[Path] = set()
    for file_path in files:
        parent = file_path.parent
        while parent != install_dir and _is_relative_to(parent, install_dir):
            dirs.add(parent)
            parent = parent.parent
    dirs.add(install_dir)
    return sorted(dirs, key=lambda item: len(item.parts), reverse=True)


def delete_manifest_files(
    files: Sequence[Path], deferred: set[Path] | None = None
) -> list[Path]:
    """Delete listed files only, returning files that need a deferred retry."""
    deferred = deferred or set()
    pending: list[Path] = []
    for file_path in files:
        if file_path in deferred:
            pending.append(file_path)
            continue
        try:
            if file_path.is_file() or file_path.is_symlink():
                file_path.unlink()
        except OSError:
            pending.append(file_path)
    return pending


def remove_empty_dirs(directories: Iterable[Path]) -> None:
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            # Unknown user files and non-empty folders are intentionally kept.
            pass


def schedule_deferred_cleanup(files: Sequence[Path], directories: Sequence[Path]) -> None:
    """Use a temporary PowerShell helper after uninstall.exe exits."""
    task_id = uuid.uuid4().hex
    temp_dir = Path(tempfile.gettempdir())
    config_path = temp_dir / f"learnanything-uninstall-{task_id}.json"
    script_path = temp_dir / f"learnanything-uninstall-{task_id}.ps1"
    payload = {
        "pid": os.getpid(),
        "files": [str(path) for path in files],
        "directories": [str(path) for path in directories],
        "config": str(config_path),
        "script": str(script_path),
    }
    config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    script_path.write_text(
        "$ErrorActionPreference = 'SilentlyContinue'\n"
        "$cfg = Get-Content -LiteralPath $args[0] -Raw -Encoding UTF8 | ConvertFrom-Json\n"
        # Polling Get-Process avoids Wait-Process edge cases with a PyInstaller
        # one-file parent, while still guaranteeing that uninstall.exe has
        # released its own executable before deletion begins.
        "for ($wait = 0; $wait -lt 1200; $wait++) {\n"
        "  if (-not (Get-Process -Id ([int]$cfg.pid) -ErrorAction SilentlyContinue)) { break }\n"
        "  Start-Sleep -Milliseconds 250\n"
        "}\n"
        "for ($attempt = 0; $attempt -lt 40; $attempt++) {\n"
        "  foreach ($file in $cfg.files) { Remove-Item -LiteralPath ([string]$file) -Force -ErrorAction SilentlyContinue }\n"
        "  foreach ($dir in $cfg.directories) { Remove-Item -LiteralPath ([string]$dir) -Force -ErrorAction SilentlyContinue }\n"
        "  $remaining = @($cfg.files | Where-Object { Test-Path -LiteralPath ([string]$_) })\n"
        "  if ($remaining.Count -eq 0) { break }\n"
        "  Start-Sleep -Milliseconds 500\n"
        "}\n"
        "Remove-Item -LiteralPath ([string]$cfg.config) -Force -ErrorAction SilentlyContinue\n"
        "Remove-Item -LiteralPath ([string]$cfg.script) -Force -ErrorAction SilentlyContinue\n",
        encoding="utf-8-sig",
    )
    creationflags = 0
    if sys.platform == "win32":
        # CREATE_NO_WINDOW keeps the helper invisible. Do not combine it with
        # DETACHED_PROCESS: that combination is unreliable for one-file
        # PyInstaller children on some Windows builds.
        creationflags = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            str(config_path),
        ],
        # Never inherit the installation directory as the helper's working
        # directory. Windows cannot remove a directory that the cleanup
        # process itself is using as its current directory.
        cwd=str(temp_dir),
        close_fds=True,
        creationflags=creationflags,
    )


def parse_options(argv: Sequence[str]) -> tuple[bool, bool]:
    normalised = {arg.strip().casefold() for arg in argv}
    silent = bool(normalised & {"/s", "/silent", "--silent"})
    delete_data = bool(normalised & {"/delete-data", "--delete-data"})
    return silent, delete_data


def confirm_options(data_root: Path) -> tuple[bool, bool]:
    answer = _message_box(
        "将卸载 LearnAnything 桌面程序。\n\n"
        "卸载器只删除发布清单中的程序文件，不会删除您后来放入程序目录的其他文件。\n\n"
        "是否继续？",
        "卸载 LearnAnything",
        MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
    )
    if answer != IDYES:
        return False, False

    answer = _message_box(
        "是否同时永久删除全部本机学习数据？\n\n"
        f"数据目录：{data_root}\n\n"
        "其中包括账号、API 配置、知识库、原始文档、对话、题库、错题和学习记录。\n"
        "此操作不可恢复。\n\n"
        "“是”＝删除全部数据\n"
        "“否”＝保留数据，仅卸载程序\n"
        "“取消”＝取消整个卸载",
        "选择数据保留方式",
        MB_YESNOCANCEL | MB_ICONWARNING | MB_DEFBUTTON2,
    )
    if answer == IDCANCEL:
        return False, False
    return True, answer == IDYES


def uninstall(silent: bool, delete_data: bool) -> int:
    install_dir = get_install_dir()
    data_root = get_data_root()
    _, files = load_install_manifest(install_dir)

    running = find_running_main_processes(install_dir)
    if running:
        raise UninstallSafetyError(
            "LearnAnything 主程序仍在运行。请先关闭程序窗口，再重新运行 uninstall.exe。"
        )

    if not silent:
        proceed, delete_data = confirm_options(data_root)
        if not proceed:
            return 0

    data_warning = ""
    legacy_pending, legacy_dirs = handle_legacy_runtime_artifacts(
        install_dir, data_root, delete_data
    )
    if delete_data and data_root.exists():
        try:
            safe_data_root = validate_data_root(data_root)
            shutil.rmtree(safe_data_root)
        except (OSError, UninstallSafetyError) as exc:
            data_warning = f"\n\n用户数据未能自动删除：\n{exc}\n请检查后手动处理：{data_root}"

    manifest_path = install_dir / INSTALL_MANIFEST_NAME
    uninstaller_path = install_dir / UNINSTALLER_NAME
    deferred = {manifest_path, uninstaller_path}
    directories = collect_install_dirs(install_dir, files)
    pending = legacy_pending + delete_manifest_files(files, deferred=deferred)
    directories.extend(legacy_dirs)
    directories = sorted(set(directories), key=lambda item: len(item.parts), reverse=True)
    remove_empty_dirs(directories)

    if not silent:
        kept = "用户数据已删除。" if delete_data and not data_warning else f"用户数据已保留在：\n{data_root}"
        show_info(
            "LearnAnything 程序卸载已开始，剩余文件将在本窗口关闭后清理。\n\n"
            f"{kept}{data_warning}"
        )

    # The final modal dialog must be closed before the helper is launched.
    # Otherwise a user who reads the message for longer than the helper's
    # retry window leaves uninstall.exe and the installation directory behind.
    # The helper then waits for this process to exit before deleting both.
    schedule_deferred_cleanup(pending, directories)
    return 0


def main() -> int:
    silent, delete_data = parse_options(sys.argv[1:])
    try:
        return uninstall(silent=silent, delete_data=delete_data)
    except UninstallSafetyError as exc:
        if not silent:
            show_error(str(exc))
        return 2
    except Exception as exc:
        if not silent:
            show_error(f"发生未预期错误：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Uninstaller Script (LA-051-STRUCT)

将 uninstaller.py 打包为独立的 uninstall.exe，
用于 LearnAnything 分发版本的卸载。

前置条件：
  - pip install pyinstaller

使用方式：
  cd PROJECT_ROOT
  python scripts/build_uninstaller.py

输出：
  dist/uninstall.exe
"""

import argparse
import subprocess
import sys
from pathlib import Path


def build(output_dir: Path | None = None):
    project_root = Path(__file__).parent.parent.resolve()
    uninstaller_script = project_root / "scripts" / "uninstaller.py"
    output_dir = (output_dir or (project_root / "dist")).resolve()

    if not uninstaller_script.exists():
        print(f"[ERROR] 找不到卸载脚本: {uninstaller_script}")
        sys.exit(1)

    print(f"[*] 构建 uninstall.exe...")
    print(f"[*] 源文件: {uninstaller_script}")

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "uninstall",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath", str(output_dir),
        "--workpath", str(project_root / "build_uninstaller"),
        "--specpath", str(project_root / "build_uninstaller"),
        str(uninstaller_script),
    ]

    print(f"[*] 命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(project_root))

    if result.returncode == 0:
        output = output_dir / "uninstall.exe"
        if output.exists():
            print(f"[+] 构建成功: {output}")
            print(f"[*] 使用方式:")
            print(f"    交互式: .\\dist\\uninstall.exe")
            print(f"    静默模式: .\\dist\\uninstall.exe /S")
            print(f"    删除数据: .\\dist\\uninstall.exe /S --delete-data")
        else:
            print("[WARN] 构建完成但找不到输出文件")
    else:
        print(f"[ERROR] 构建失败 (exit code: {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build LearnAnything uninstall.exe")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: PROJECT_ROOT/dist)",
    )
    args = parser.parse_args()
    build(args.output_dir)

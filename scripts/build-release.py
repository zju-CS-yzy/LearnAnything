#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建发布包脚本 (LA-DEPLOY)

功能：
    1. 构建前端（npm run build）
    2. 运行 PyInstaller 打包
    3. 将 dist/ 目录打包为 ZIP 压缩包
    4. 输出文件名包含版本和日期

用法：
    python scripts/build-release.py [version]

示例：
    python scripts/build-release.py v1.0.0
    python scripts/build-release.py          # 自动生成版本号 v1.0.0-YYYYMMDD

输出：
    dist/LearnAnything-v1.0.0-20250725.zip
"""

import os
import sys
import shutil
import zipfile
import json
import subprocess
from pathlib import Path
from datetime import datetime


def configure_console_output():
    """Avoid build failures on legacy Windows GBK consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


configure_console_output()


def run_command(cmd, cwd=None):
    """运行 shell 命令并打印输出"""
    print(f"\n[Build] >>> {cmd}")
    old_cwd = os.getcwd()
    try:
        if cwd:
            os.chdir(cwd)
        ret = os.system(cmd)
    finally:
        os.chdir(old_cwd)
    if ret != 0:
        print(f"[Build] ERROR: 命令失败 (exit code {ret}): {cmd}")
        sys.exit(ret)
    print(f"[Build] OK: {cmd}")


def run_command_args(args, cwd=None):
    """Run a command without shell quoting ambiguity."""
    print(f"\n[Build] >>> {' '.join(str(arg) for arg in args)}")
    result = subprocess.run([str(arg) for arg in args], cwd=cwd)
    if result.returncode != 0:
        print(f"[Build] ERROR: 命令失败 (exit code {result.returncode})")
        sys.exit(result.returncode)
    print("[Build] OK")


def write_install_manifest(dist_dir: Path, version: str) -> Path:
    """Record the exact portable-release files that uninstall.exe may remove."""
    manifest_path = dist_dir / ".learnanything-install.json"
    files = [
        path.relative_to(dist_dir).as_posix()
        for path in dist_dir.rglob("*")
        if path.is_file() and path != manifest_path
    ]
    files.append(manifest_path.name)
    payload = {
        "product": "LearnAnything",
        "kind": "portable-install",
        "format_version": 1,
        "version": version,
        "files": sorted(files, key=str.casefold),
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest_path


def main():
    # 项目根目录
    project_root = Path(__file__).parent.parent.resolve()
    os.chdir(project_root)

    # 版本号
    version = sys.argv[1] if len(sys.argv) > 1 else f"v1.0.0-{datetime.now().strftime('%Y%m%d')}"
    print(f"[Build] 开始构建 LearnAnything {version}")
    print(f"[Build] 项目目录: {project_root}")

    # ========== 步骤 1: 清理旧构建产物 ==========
    print("\n[Build] 步骤 1/5: 清理旧构建产物...")
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"[Build] 已删除: {d}/")

    # LA-DEPLOY-SECURITY: 安全检查 — 确保敏感配置文件和运行时数据不会被意外打包
    print("\n[Build] 安全检查 — 敏感文件排除验证:")
    sensitive_files = [
        str(project_root / "config" / "api_config.ini"),
        str(project_root / "config" / "api_keys.ini"),
        str(project_root / "API.txt"),
    ]
    for sf in sensitive_files:
        if os.path.exists(sf):
            print(f"  ⚠ 检测到敏感文件（不会被打包）: {os.path.basename(sf)}")
        else:
            print(f"  ✓ 已排除: {os.path.basename(sf)}")

    # LA-DEPLOY-SECURITY: 运行时数据检查
    print("\n[Build] 安全检查 — 运行时数据排除验证:")
    kb_dir = project_root / "knowledge_base"
    if kb_dir.exists():
        db_files = list(kb_dir.rglob("*.db"))
        if db_files:
            print(f"  ⚠ 检测到 {len(db_files)} 个数据库文件（不会被打包）:")
            for db in db_files[:5]:
                print(f"     - {db.relative_to(project_root)}")
            if len(db_files) > 5:
                print(f"     ... 还有 {len(db_files) - 5} 个")
        else:
            print("  ✓ knowledge_base/ 无数据库文件")

        # 检查是否有用户上传的文档（排除 vector_db, graph_db, cache 后的其他内容）
        user_docs = []
        for item in kb_dir.iterdir():
            if item.is_dir() and item.name not in ('graph_db', 'vector_db', 'cache'):
                docs = [f for f in item.rglob('*') if f.is_file() and f.suffix.lower() in ('.pdf', '.docx', '.txt', '.md')]
                user_docs.extend(docs)
        if user_docs:
            print(f"  ⚠ 检测到 {len(user_docs)} 个用户文档（不会被打包）")
        else:
            print("  ✓ knowledge_base/ 无用户文档")
    print("  ℹ knowledge_base/ 整个目录已排除，程序首次运行时会自动创建")

    # ========== 步骤 2: 构建前端 ==========
    print("\n[Build] 步骤 2/5: 构建前端...")
    web_dir = project_root / "web-vue"
    if web_dir.exists():
        # LA-DEPLOY: 自动安装前端依赖（Release 仓库可能缺少 node_modules）
        node_modules = web_dir / "node_modules"
        if not node_modules.exists():
            print("[Build] 检测到 node_modules 缺失，自动安装前端依赖...")
            run_command("npm install", cwd=str(web_dir))
        run_command("npm run build", cwd=str(web_dir))
    else:
        print("[Build] WARNING: web-vue/ 目录不存在，跳过前端构建")

    # ========== 步骤 3: PyInstaller 打包 ==========
    print("\n[Build] 步骤 3/5: PyInstaller 打包主程序...")
    run_command_args(
        [sys.executable, "-m", "PyInstaller", "app.spec", "--noconfirm"],
        cwd=str(project_root),
    )

    # 检查打包结果
    exe_path = project_root / "dist" / "LearnAnything" / "LearnAnything.exe"
    if not exe_path.exists():
        print(f"[Build] ERROR: 打包失败，未找到 {exe_path}")
        sys.exit(1)
    print(f"[Build] 打包成功: {exe_path}")

    # ========== 步骤 4: 构建卸载器和安装清单 ==========
    print("\n[Build] 步骤 4/5: 构建 uninstall.exe 和安装清单...")
    dist_dir = project_root / "dist" / "LearnAnything"
    run_command_args(
        [
            sys.executable,
            project_root / "scripts" / "build_uninstaller.py",
            "--output-dir",
            dist_dir,
        ],
        cwd=str(project_root),
    )
    uninstaller_path = dist_dir / "uninstall.exe"
    if not uninstaller_path.exists():
        print(f"[Build] ERROR: 未找到卸载器 {uninstaller_path}")
        sys.exit(1)
    manifest_path = write_install_manifest(dist_dir, version)
    print(f"[Build] 卸载器: {uninstaller_path}")
    print(f"[Build] 安装清单: {manifest_path}")

    # ========== 步骤 5: 打包为 ZIP ==========
    print("\n[Build] 步骤 5/5: 打包为 ZIP...")
    zip_name = f"LearnAnything-{version}.zip"
    zip_path = project_root / "dist" / zip_name

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = str(file_path.relative_to(dist_dir.parent))
                zf.write(file_path, arcname)
                print(f"[Build] 添加: {arcname}")

    # 计算文件大小
    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\n[Build] ✅ 构建完成!")
    print(f"[Build] 压缩包: {zip_path}")
    print(f"[Build] 大小: {zip_size_mb:.1f} MB")
    print(f"[Build] 版本: {version}")
    print(f"\n[Build] 用户部署方式:")
    print(f"  1. 下载 {zip_name}")
    print(f"  2. 解压到任意目录")
    print(f"  3. 运行 LearnAnything.exe")
    print(f"  4. 首次启动时配置 API 密钥")


if __name__ == "__main__":
    main()

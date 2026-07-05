#!/usr/bin/env python3
"""
重新打包 LearnAnything 桌面应用脚本

用法: python scripts/rebuild_executable.py
"""
import subprocess
import shutil
import os
import sys

PROJECT_ROOT = r"D:\MyCS\AI\Project\LearnAnything"

def run_cmd(cmd, cwd=None):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return False
    print(result.stdout[:500] if result.stdout else "OK")
    return True

def main():
    # 1. 清理 pyinstaller 缓存
    print("=== 1. 清理 pyinstaller 缓存 ===")
    for path in ["build", "dist/LearnAnything"]:
        full_path = os.path.join(PROJECT_ROOT, path)
        if os.path.exists(full_path):
            shutil.rmtree(full_path)
            print(f"  删除: {full_path}")
    
    # 2. 构建前端
    print("\n=== 2. 构建前端 ===")
    if not run_cmd("npm run build", cwd=os.path.join(PROJECT_ROOT, "web-vue")):
        print("前端构建失败！")
        return 1
    
    # 3. 重新打包
    print("\n=== 3. 重新打包可执行文件 ===")
    if not run_cmd("pyinstaller LearnAnything.spec"):
        print("打包失败！")
        return 1
    
    print("\n=== ✅ 打包完成 ===")
    print(f"输出目录: {os.path.join(PROJECT_ROOT, 'dist', 'LearnAnything')}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

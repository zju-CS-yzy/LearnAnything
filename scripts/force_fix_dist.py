#!/usr/bin/env python3
"""
强制修复打包版本的所有文件
"""
import shutil
import os

SRC = r"D:\MyCS\AI\Project\LearnAnything"
DIST = r"D:\MyCS\AI\Project\LearnAnything\dist\LearnAnything\_internal"

files_to_copy = [
    ("app\backend_api.py", "app\backend_api.py"),
    ("core\graph_store.py", "core\graph_store.py"),
    ("core\graph_store.py", "app\core\graph_store.py"),
    ("core\semantic_linker.py", "core\semantic_linker.py"),
    ("core\semantic_linker.py", "app\core\semantic_linker.py"),
    ("core\concept_deduper.py", "core\concept_deduper.py"),
    ("core\concept_deduper.py", "app\core\concept_deduper.py"),
    ("core\graph_builder.py", "core\graph_builder.py"),
    ("core\graph_builder.py", "app\core\graph_builder.py"),
]

for src_rel, dst_rel in files_to_copy:
    src_path = os.path.join(SRC, src_rel)
    dst_path = os.path.join(DIST, dst_rel)
    if os.path.exists(src_path):
        shutil.copy2(src_path, dst_path)
        print(f"✅ {src_rel} -> {dst_rel}")
    else:
        print(f"❌ {src_rel} not found")

# 删除所有 .pyc 和 __pycache__
for root, dirs, files in os.walk(DIST):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d))
            print(f"🗑️  Removed __pycache__: {root}")
    for f in files:
        if f.endswith(".pyc"):
            os.remove(os.path.join(root, f))
            print(f"🗑️  Removed .pyc: {os.path.join(root, f)}")

print("\nDone! Please restart the .exe application.")

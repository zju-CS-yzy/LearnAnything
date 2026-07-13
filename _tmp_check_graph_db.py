import sys
import os
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")
from config.settings import GRAPH_DB_DIR

# 使用 os.listdir 获取原始文件名
names = os.listdir(GRAPH_DB_DIR)
for name in names:
    name_bytes = name.encode('utf-8', errors='replace')
    print(f"Raw bytes: {name_bytes}")
    path = GRAPH_DB_DIR / name
    try:
        is_dir = os.path.isdir(path)
        exists = os.path.exists(path)
        print(f"  Is dir: {is_dir}")
        print(f"  Exists: {exists}")
    except Exception as e:
        print(f"  Error: {e}")
    print()

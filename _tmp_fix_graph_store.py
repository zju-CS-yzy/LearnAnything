import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")
from pathlib import Path

file_path = Path("D:\MyCS\AI\Project\LearnAnything\core\graph_store.py")
content = file_path.read_text(encoding='utf-8', errors='replace')

# 找到 __init__ 方法，插入 db_path_str
# 查找 "self.db_path = GRAPH_DB_DIR / f" 这行
target_line = "        self.db_path = GRAPH_DB_DIR / f\"{collection_name}_graph\""
idx = content.find(target_line)
if idx >= 0:
    # 在后面插入 db_path_str
    content = content.replace(
        target_line,
        "        self.db_path = GRAPH_DB_DIR / f\"{collection_name}_graph\"\n        self.db_path_str = str(self.db_path)  # LA-035-P12: 统一使用字符串缓存 key"
    )
    print("[OK] Inserted db_path_str after self.db_path")
else:
    print("[WARN] Could not find self.db_path line")

# 找到 _ensure_db 中 "db_path_str = str(self.db_path)"
# 删除这行，后面的 db_path_str 改为 self.db_path_str
target_ensure = "        db_path_str = str(self.db_path)"
if target_ensure in content:
    content = content.replace(target_ensure, "        # LA-035-P12: 使用 self.db_path_str")
    print("[OK] Replaced db_path_str in _ensure_db")
    
    # 将 if db_path_str 改为 if self.db_path_str
    content = content.replace("if db_path_str not in _db_cache:", "if self.db_path_str not in _db_cache:")
    content = content.replace("_db_cache[db_path_str]", "_db_cache[self.db_path_str]")
    content = content.replace("self._db = _db_cache[db_path_str]", "self._db = _db_cache[self.db_path_str]")
    print("[OK] Replaced all db_path_str -> self.db_path_str in _ensure_db")
else:
    print("[WARN] Could not find db_path_str in _ensure_db")

# 找到 init_schema 中的 "db_path_str = str(self.db_path)"
target_schema = "            db_path_str = str(self.db_path)"
if target_schema in content:
    content = content.replace(target_schema, "            # LA-035-P12: 使用 self.db_path_str")
    print("[OK] Replaced db_path_str in init_schema")
    
    # 将 if db_path_str 改为 if self.db_path_str
    content = content.replace("if db_path_str in _db_cache:", "if self.db_path_str in _db_cache:")
    content = content.replace("del _db_cache[db_path_str]", "del _db_cache[self.db_path_str]")
    print("[OK] Replaced all db_path_str -> self.db_path_str in init_schema")
else:
    print("[WARN] Could not find db_path_str in init_schema")

# 写回文件
file_path.write_text(content, encoding='utf-8')
print("[OK] File written")

# 验证
content2 = file_path.read_text(encoding='utf-8', errors='replace')
if "self.db_path_str = str(self.db_path)" in content2:
    print("[OK] db_path_str in init: found")
else:
    print("[ERR] db_path_str in init: MISSING")
if "if self.db_path_str not in _db_cache" in content2:
    print("[OK] self.db_path_str in _ensure_db: found")
else:
    print("[ERR] self.db_path_str in _ensure_db: MISSING")
if "if self.db_path_str in _db_cache" in content2:
    print("[OK] self.db_path_str in init_schema: found")
else:
    print("[ERR] self.db_path_str in init_schema: MISSING")

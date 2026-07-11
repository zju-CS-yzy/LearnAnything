#!/usr/bin/env python3
import csv
from pathlib import Path

csv_path = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\测试_v1_concepts.csv")
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# 检查 description 字段
empty_desc = [r for r in rows if not r.get("description", "").strip()]
print(f"Total: {len(rows)}, Empty desc: {len(empty_desc)}")

# 打印 name 和 description 长度
for r in rows[:10]:
    name = r["name"]
    desc = r.get("description", "")
    print(f"{name}: desc_len={len(desc)}")

#!/usr/bin/env python3
"""
检查 KùzuDB 中的 CanonicalConcept 节点的 description 字段
以及 CSV ID 与 KùzuDB ID 是否匹配
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore

# 检查 generic_v1 数据库（之前测试通过，可以访问）
gs = GraphStore("generic_v1")
gs.init_schema()
conn = gs._ensure_db()

# 1. 检查 CanonicalConcept 节点数量和 description 字段
print("=== generic_v1 CanonicalConcept ===")
try:
    result = conn.execute("MATCH (c:CanonicalConcept) RETURN count(c)")
    if result.has_next():
        print(f"  总数: {result.get_next()[0]}")
except Exception as e:
    print(f"  错误: {e}")

# 2. 检查有多少个 description 为空
try:
    result = conn.execute("""
        MATCH (c:CanonicalConcept)
        WHERE c.description IS NULL OR c.description = ''
        RETURN count(c)
    """)
    if result.has_next():
        print(f"  空 description: {result.get_next()[0]}")
except Exception as e:
    print(f"  错误: {e}")

# 3. 打印前5个节点的 description
try:
    result = conn.execute("MATCH (c:CanonicalConcept) RETURN c.canonical_id, c.name, c.description LIMIT 5")
    while result.has_next():
        row = result.get_next()
        cid, name, desc = row[0], row[1], row[2]
        print(f"  {cid}: {name} | desc={repr(desc) if desc else '(空)'}")
except Exception as e:
    print(f"  错误: {e}")

# 4. 检查 CSV 中的 ID 是否与 KùzuDB 一致
print("\n=== CSV ID 对比 ===")
import csv
from pathlib import Path

csv_path = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\generic_v1_concepts.csv")
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    csv_rows = list(reader)

print(f"CSV 记录数: {len(csv_rows)}")

# 检查 KùzuDB 中的 ID
try:
    result = conn.execute("MATCH (c:CanonicalConcept) RETURN c.canonical_id LIMIT 100")
    db_ids = set()
    while result.has_next():
        db_ids.add(result.get_next()[0])
    
    csv_ids = {r["id"] for r in csv_rows}
    
    print(f"KùzuDB ID 数: {len(db_ids)}")
    print(f"CSV ID 数: {len(csv_ids)}")
    print(f"共同 ID: {len(db_ids & csv_ids)}")
    print(f"只在 KùzuDB: {len(db_ids - csv_ids)}")
    print(f"只在 CSV: {len(csv_ids - db_ids)}")
    
    if db_ids - csv_ids:
        print(f"KùzuDB 独有样本: {list(db_ids - csv_ids)[:3]}")
    if csv_ids - db_ids:
        print(f"CSV 独有样本: {list(csv_ids - db_ids)[:3]}")
        
except Exception as e:
    print(f"  错误: {e}")

#!/usr/bin/env python3
"""
检查 API 返回的概念数据中 description 字段
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)

# 1. 检查 generic 学科的 description 字段
print("=== generic 学科 ===")
resp = client.get('/api/knowledge-graph/generic/concepts?limit=2000')
data = resp.json()
concepts = data.get('concepts', [])

empty_desc = [c for c in concepts if not c.get('description', '').strip()]
print(f"总概念数: {len(concepts)}")
print(f"空 description: {len(empty_desc)} ({len(empty_desc)/len(concepts)*100:.1f}%)")

# 打印几个有 description 和空 description 的样本
print("\n有 description 的样本:")
for c in concepts:
    if c.get('description', '').strip():
        print(f"  {c['name']}: {c['description'][:60]}...")
        break

print("\n空 description 的样本:")
for c in concepts[:5]:
    if not c.get('description', '').strip():
        print(f"  {c['name']}: desc='{c.get('description', '')}'")

# 2. 检查 CSV 中的 description
print("\n=== 直接检查 CSV ===")
import csv
from pathlib import Path

csv_path = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\generic_v1_concepts.csv")
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

csv_empty_desc = [r for r in rows if not r.get('description', '').strip()]
print(f"CSV 总记录数: {len(rows)}")
print(f"CSV 空 description: {len(csv_empty_desc)} ({len(csv_empty_desc)/len(rows)*100:.1f}%)")

print("\nCSV 中空 description 的样本:")
for r in rows[:10]:
    if not r.get('description', '').strip():
        print(f"  {r['name']}: desc='{r.get('description', '')}'")

# 3. 检查 list_graph_concepts 函数的合并逻辑
print("\n=== 检查 API 合并逻辑 ===")
# 打印第一个概念的所有字段
if concepts:
    c = concepts[0]
    print(f"API 返回的第一个概念:")
    for k, v in c.items():
        v_str = str(v)[:60] if v else '(空)'
        print(f"  {k}: {v_str}")

#!/usr/bin/env python3
"""
检查 测试 学科的 description 字段
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)

# 检查 测试 学科的 concepts API
print("=== 测试 学科 ===")
resp = client.get('/api/knowledge-graph/%E6%B5%8B%E8%AF%95/concepts?limit=200')
print(f"Status: {resp.status_code}")

data = resp.json()
concepts = data.get('concepts', [])
print(f"总概念数: {len(concepts)}")

if concepts:
    empty_desc = [c for c in concepts if not c.get('description', '').strip()]
    print(f"空 description: {len(empty_desc)} / {len(concepts)}")
    
    # 打印第一个概念的所有字段
    print("\n第一个概念的完整字段:")
    for k, v in concepts[0].items():
        v_str = str(v)[:50] if v is not None else 'None'
        print(f"  {k}: {repr(v_str)}")
    
    # 检查数据检索、文本分块、关键词检索
    keywords = ["数据检索", "文本分块", "关键词检索"]
    for kw in keywords:
        for c in concepts:
            if kw in c.get('name', '') or kw in c.get('aliases', ''):
                print(f"\n找到 '{kw}':")
                print(f"  id={c['id']}")
                print(f"  name={c.get('name','')}")
                print(f"  description={repr(c.get('description',''))}")
                break
else:
    print("无概念数据")

# 直接检查 CSV
print("\n=== 测试 CSV 直接检查 ===")
import csv
from pathlib import Path

csv_path = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\测试_v1_concepts.csv")
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"CSV 记录数: {len(rows)}")
for r in rows[:5]:
    print(f"  {r['name']}: desc={repr(r.get('description',''))}")

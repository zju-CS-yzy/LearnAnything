#!/usr/bin/env python3
"""
检查 测试_v1 数据库 - 避免锁，直接检查文件
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore

# 先检查 generic_v1（不锁定）
gs = GraphStore("generic_v1")
gs.init_schema()
conn = gs._ensure_db()

print("=== generic_v1 数据库 ===")

for label in ["Chunk", "Concept", "CanonicalConcept", "ExtractedConcept"]:
    try:
        result = conn.execute(f"MATCH (n:{label}) RETURN count(n)")
        if result.has_next():
            count = result.get_next()[0]
            print(f"  {label}: {count}")
    except Exception as e:
        print(f"  {label}: {e}")

# 检查边
try:
    result = conn.execute("MATCH ()-[r:SOLUTION]->() RETURN count(r)")
    if result.has_next():
        print(f"  SOLUTION: {result.get_next()[0]}")
except Exception as e:
    print(f"  SOLUTION: {e}")

try:
    result = conn.execute("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)")
    if result.has_next():
        print(f"  DEPENDS_ON: {result.get_next()[0]}")
except Exception as e:
    print(f"  DEPENDS_ON: {e}")

# 检查 concept_canonical_2e3b5de367
for label, idf in [("CanonicalConcept", "canonical_id"), ("Concept", "concept_id"), ("ExtractedConcept", "extracted_id")]:
    try:
        result = conn.execute(f"MATCH (c:{label} {{{idf}: 'concept_canonical_2e3b5de367'}}) RETURN c.{idf}, c.name")
        if result.has_next():
            row = result.get_next()
            print(f"  {label}: {row[0]} = {row[1]}")
        else:
            print(f"  {label}: not found")
    except Exception as e:
        print(f"  {label}: {e}")

print("\n=== generic_v1 concepts API 测试 ===")
from fastapi.testclient import TestClient
from app.backend_api import app
client = TestClient(app)

resp = client.get('/api/knowledge-graph/generic/concepts?limit=5')
data = resp.json()
print(f"API 返回: {len(data.get('concepts', []))} 个概念")
for c in data.get('concepts', [])[:3]:
    print(f"  {c['id']}: {c['name']}")

"""
测试后端 API 返回的字段格式
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from app.backend_api import app
from fastapi.testclient import TestClient

client = TestClient(app)
resp = client.get('/api/knowledge-graph/generic_v1/concepts?limit=3')
data = resp.json()

print("=== concepts API 返回格式 ===")
for c in data.get('concepts', [])[:2]:
    print(f"id={c['id'][:20]}")
    print(f"  name={c['name']}")
    print(f"  type={c['type']}")
    print(f"  description={repr(c.get('description', ''))[:40]}")
    print(f"  parent_hint={repr(c.get('parent_hint', ''))[:40]}")
    print(f"  source_chunks={repr(c.get('source_chunks', ''))[:60]}")
    print()

# 测试 concept-links API
resp2 = client.get('/api/knowledge-graph/generic_v1/concept-links?limit=3')
data2 = resp2.json()
print("=== concept-links API 返回格式 ===")
for e in data2.get('edges', [])[:3]:
    print(f"  source={e['source'][:20]}, target={e['target'][:20]}, type={e['type']}, confidence={e.get('confidence', 0)}")

#!/usr/bin/env python3
"""
测试修复后的 API
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)

# 测试 generic 学科的 subgraph API
print("=== Test: generic subgraph ===")
resp = client.get('/api/knowledge-graph/generic/subgraph/concept_canonical_20ff4a8b2b?depth=1')
print(f"Status: {resp.status_code}")
print(f"Response: {resp.json()}")

print()

# 测试 generic 学科的 concepts API
print("=== Test: generic concepts ===")
resp = client.get('/api/knowledge-graph/generic/concepts?limit=5')
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Count: {data.get('count')}")
for c in data.get('concepts', [])[:2]:
    print(f"  {c['id']}: {c['name']}")

print()

# 测试 concept-links API
print("=== Test: generic concept-links ===")
resp = client.get('/api/knowledge-graph/generic/concept-links?limit=5')
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Count: {len(data.get('edges', []))}")
for e in data.get('edges', [])[:2]:
    print(f"  {e['source']} -> {e['target']} ({e['type']})")

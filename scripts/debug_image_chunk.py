#!/usr/bin/env python3
"""
检查 图像测试 学科的后端数据
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from fastapi.testclient import TestClient
from app.backend_api import app

client = TestClient(app)

# 1. 检查 nodes API
print("=== /api/knowledge-graph/图像测试/nodes ===")
resp = client.get('/api/knowledge-graph/%E5%9B%BE%E5%83%8F%E6%B5%8B%E8%AF%95/nodes?limit=500')
print(f"Status: {resp.status_code}")
data = resp.json()
nodes = data.get('nodes', [])
print(f"Total nodes: {len(nodes)}")

# 统计 chunk_type
from collections import Counter
type_counts = Counter(n.get('chunk_type', '') for n in nodes)
print(f"\nChunk type distribution:")
for t, c in type_counts.most_common():
    print(f"  {t}: {c}")

# 检查 image chunk
image_nodes = [n for n in nodes if n.get('chunk_type') == 'image']
print(f"\nImage nodes: {len(image_nodes)}")
if image_nodes:
    for n in image_nodes[:3]:
        print(f"  {n['id']}: {n.get('text', '')[:60]}")
        print(f"    image_path={n.get('image_path')}")
        print(f"    thumbnail_path={n.get('thumbnail_path')}")
        print(f"    width={n.get('width')}, height={n.get('height')}")
else:
    print("  无 image chunk!")

# 2. 检查 chunks API（VectorStore）
print("\n=== /api/knowledge-base/图像测试/chunks ===")
resp = client.get('/api/knowledge-base/%E5%9B%BE%E5%83%8F%E6%B5%8B%E8%AF%95/chunks?limit=50')
print(f"Status: {resp.status_code}")
data = resp.json()
chunks = data.get('chunks', [])
print(f"Total chunks: {len(chunks)}")

image_chunks = [c for c in chunks if c.get('metadata', {}).get('chunk_type') == 'image']
print(f"Image chunks: {len(image_chunks)}")
if image_chunks:
    for c in image_chunks[:3]:
        print(f"  {c['id']}: text={c.get('text', '')[:60]}")
        print(f"    metadata chunk_type={c.get('metadata', {}).get('chunk_type')}")
        print(f"    metadata image_path={c.get('metadata', {}).get('image_path')}")

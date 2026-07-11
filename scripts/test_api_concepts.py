#!/usr/bin/env python3
"""
测试 API 返回的概念数据 — 使用正确的 subject
"""
import json
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from fastapi.testclient import TestClient
from app.backend_api import app
from collections import Counter

client = TestClient(app)

# 使用 generic（不是 generic_v1）
resp = client.get('/api/knowledge-graph/generic/concepts?limit=2000')
print(f"Status: {resp.status_code}")

data = resp.json()
concepts = data.get('concepts', [])
print(f"Total concepts: {len(concepts)}")

# 统计
empty_names = [c for c in concepts if not c.get('name', '').strip()]
empty_types = [c for c in concepts if not c.get('type', '').strip()]
empty_descs = [c for c in concepts if not c.get('description', '').strip()]

print(f"Empty names: {len(empty_names)}")
print(f"Empty types: {len(empty_types)}")
print(f"Empty descriptions: {len(empty_descs)}")

type_counts = Counter(c.get('type', '') for c in concepts)
print(f"\nType distribution (top 10):")
for t, count in type_counts.most_common(10):
    print(f"  {repr(t)}: {count}")

# 检查 name 长度分布
name_lengths = [len(c.get('name', '')) for c in concepts]
print(f"\nName length stats:")
print(f"  Min: {min(name_lengths)}")
print(f"  Max: {max(name_lengths)}")
print(f"  Avg: {sum(name_lengths)/len(name_lengths):.1f}")

# 检查是否有 name 很短（1-2个字符）的情况
short_names = [c for c in concepts if 0 < len(c.get('name', '')) <= 2]
print(f"\nShort names (1-2 chars): {len(short_names)}")
if short_names:
    for c in short_names[:5]:
        print(f"  id={c['id']}, name={repr(c['name'])}, type={repr(c['type'])}")

# 写入文件以便查看
with open(r"D:\MyCS\AI\Project\LearnAnything\scripts\concepts_sample.json", "w", encoding="utf-8") as f:
    json.dump(concepts[:20], f, ensure_ascii=False, indent=2)
print("\nSample written to concepts_sample.json")

#!/usr/bin/env python3
"""
诊断孤立 paragraph chunk: md_RAG关键痛点和解决方案面试题_p_1_110631
"""
import urllib.request
import json
import sys

# 修复 Windows 控制台编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:5001"
SUBJECT = "rag"
TARGET_ID = "md_RAG关键痛点和解决方案面试题_p_1_110631"

def api_get(path):
    url = f"{BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None

print(f"诊断孤立节点: {TARGET_ID}")
print("=" * 60)

# 1. 获取所有节点
nodes = api_get(f"/api/knowledge-graph/{SUBJECT}/nodes?limit=5000")
target = None
if nodes:
    for n in nodes.get('nodes', []):
        if n['id'] == TARGET_ID:
            target = n
            break
    
    if target:
        print(f"\n--- 节点信息 ---")
        print(f"  ID: {target['id']}")
        print(f"  chunk_type: {target.get('chunk_type')}")
        print(f"  heading_path: '{target.get('heading_path', '')}'")
        print(f"  source: {target.get('source')}")
        text = target.get('text', '')
        print(f"  text 前120字符: {text[:120]}")
    else:
        print(f"  [WARN] 节点 {TARGET_ID} 未在 nodes API 返回中")

# 2. 统计 heading_path 为空的 paragraph 数量
if nodes:
    empty_heading_paragraphs = []
    for n in nodes.get('nodes', []):
        if n.get('chunk_type') == 'paragraph' and not n.get('heading_path'):
            empty_heading_paragraphs.append(n['id'])
    
    print(f"\n--- 全局统计 ---")
    print(f"  heading_path 为空的 paragraph 数量: {len(empty_heading_paragraphs)}")
    if len(empty_heading_paragraphs) <= 10:
        for pid in empty_heading_paragraphs:
            print(f"    - {pid}")
    else:
        for pid in empty_heading_paragraphs[:5]:
            print(f"    - {pid}")
        print(f"    ... 等共 {len(empty_heading_paragraphs)} 个")

# 3. 获取所有边，查找目标节点的边关系
edges = api_get(f"/api/knowledge-graph/{SUBJECT}/edges?limit=5000")
if edges:
    incoming = []
    outgoing = []
    for e in edges.get('edges', []):
        if e['target'] == TARGET_ID:
            incoming.append(e)
        if e['source'] == TARGET_ID:
            outgoing.append(e)
    
    print(f"\n--- 边关系 ---")
    print(f"  入边 (指向该节点): {len(incoming)}")
    for e in incoming:
        print(f"    {e['source']} -> {TARGET_ID} ({e['type']})")
    print(f"  出边 (从该节点发出): {len(outgoing)}")
    for e in outgoing:
        print(f"    {TARGET_ID} -> {e['target']} ({e['type']})")

# 4. 查找该 source 对应的 document 节点
if target:
    source_file = target.get('source')
    if nodes:
        doc_nodes = [n for n in nodes.get('nodes', []) if n.get('chunk_type') == 'document' and n.get('source') == source_file]
        print(f"\n--- 同 source 的 document 节点 ---")
        print(f"  source={source_file}, document 节点数: {len(doc_nodes)}")
        for d in doc_nodes:
            print(f"    - {d['id']}: heading_path='{d.get('heading_path', '')}'")

# 5. 子图查询
print(f"\n--- 子图查询 (depth=2) ---")
subgraph = api_get(f"/api/knowledge-graph/{SUBJECT}/subgraph/{TARGET_ID}?depth=2")
if subgraph:
    print(f"  子图节点数: {len(subgraph.get('nodes', []))}")
    print(f"  子图边数: {len(subgraph.get('edges', []))}")
    for e in subgraph.get('edges', [])[:10]:
        print(f"    {e.get('source')} -> {e.get('target')} ({e.get('type')})")

print("\n" + "=" * 60)
print("诊断完成")

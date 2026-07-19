#!/usr/bin/env python3
"""
诊断脚本：通过后端 API 检查文档树状态
（不直接访问 KuzuDB，避免文件锁冲突）
"""
import urllib.request
import json
import sys

BASE_URL = "http://127.0.0.1:5001"  # 或 5000，根据实际端口
SUBJECT = "rag"

def api_get(path):
    url = f"{BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [ERROR] {url}: {e}")
        return None

def diagnose():
    print(f"\n{'='*60}")
    print(f"API 诊断: 学科={SUBJECT}, 后端={BASE_URL}")
    print(f"{'='*60}")
    
    # 1. 健康检查
    print("\n--- 健康检查 ---")
    health = api_get("/api/health")
    if health:
        print(f"  状态: {health.get('status')}")
        print(f"  版本: {health.get('version')}")
    else:
        print("  后端未响应！请确认后端服务正在运行")
        return
    
    # 2. 节点统计
    print("\n--- Chunk 节点 ---")
    nodes = api_get(f"/api/knowledge-graph/{SUBJECT}/nodes?limit=5000")
    if nodes:
        total = nodes.get('total', 0)
        count = nodes.get('count', 0)
        print(f"  数据库总数: {total}")
        print(f"  返回数量: {count}")
        
        # 统计类型分布
        type_dist = {}
        for n in nodes.get('nodes', []):
            t = n.get('chunk_type') or '(null)'
            type_dist[t] = type_dist.get(t, 0) + 1
        for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
            print(f"    {t}: {c}")
        
        # 检查是否有 parent_id 字段
        has_parent_id = sum(1 for n in nodes.get('nodes', []) if n.get('parent_id'))
        print(f"  有 parent_id 的节点: {has_parent_id}/{count}")
    
    # 3. 边统计
    print("\n--- Chunk 边 ---")
    edges = api_get(f"/api/knowledge-graph/{SUBJECT}/edges?limit=5000")
    if edges:
        count = edges.get('count', 0)
        print(f"  返回边数: {count}")
        
        type_dist = {}
        for e in edges.get('edges', []):
            t = e.get('type', 'unknown')
            type_dist[t] = type_dist.get(t, 0) + 1
        for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
            print(f"    {t}: {c}")
        
        # 样本边
        print(f"\n  样本边 (前 5 条):")
        for e in edges.get('edges', [])[:5]:
            print(f"    {e['source']} -> {e['target']} ({e['type']})")
    
    # 4. 图谱总体统计
    print("\n--- 图谱总体统计 ---")
    stats = api_get(f"/api/knowledge-graph/{SUBJECT}/stats")
    if stats:
        for k, v in stats.items():
            if k != 'subject':
                print(f"  {k}: {v}")
    
    print(f"\n{'='*60}")
    print("诊断完成")
    print(f"{'='*60}")

if __name__ == "__main__":
    diagnose()

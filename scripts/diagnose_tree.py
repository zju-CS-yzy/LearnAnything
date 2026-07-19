#!/usr/bin/env python3
"""
诊断脚本：检查 KuzuDB 中文档树的边和节点状态
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore
from config.settings import KNOWLEDGE_BASE_DIR

SUBJECT = "rag"  # 请根据实际学科修改

def diagnose(subject):
    print(f"\n{'='*60}")
    print(f"诊断学科: {subject}")
    print(f"{'='*60}")
    
    store = GraphStore(f"{subject}_v1")
    store.init_schema()
    conn = store._ensure_db()
    
    # 1. Chunk 节点统计
    print("\n--- Chunk 节点统计 ---")
    result = conn.execute("""
        MATCH (c:Chunk)
        RETURN c.chunk_type, COUNT(c) AS cnt
    """)
    total_chunks = 0
    while result.has_next():
        row = result.get_next()
        print(f"  {row[0] or '(null)'}: {row[1]}")
        total_chunks += row[1]
    print(f"  总计: {total_chunks}")
    
    # 2. BELONGS_TO 边统计
    print("\n--- BELONGS_TO 边统计 ---")
    result = conn.execute("""
        MATCH (a:Chunk)-[r:BELONGS_TO]->(b:Chunk)
        RETURN COUNT(r) AS cnt
    """)
    belongs_count = result.get_next()[0] if result.has_next() else 0
    print(f"  总数: {belongs_count}")
    
    # 3. 按源 chunk_type 分布
    result = conn.execute("""
        MATCH (a:Chunk)-[r:BELONGS_TO]->(b:Chunk)
        RETURN a.chunk_type, COUNT(r) AS cnt
    """)
    while result.has_next():
        row = result.get_next()
        print(f"  {row[0]} -> ?: {row[1]}")
    
    # 4. 按目标 chunk_type 分布
    result = conn.execute("""
        MATCH (a:Chunk)-[r:BELONGS_TO]->(b:Chunk)
        RETURN b.chunk_type, COUNT(r) AS cnt
    """)
    while result.has_next():
        row = result.get_next()
        print(f"  ? -> {row[0]}: {row[1]}")
    
    # 5. ADJACENT_TO 边统计
    print("\n--- ADJACENT_TO 边统计 ---")
    result = conn.execute("""
        MATCH (a:Chunk)-[r:ADJACENT_TO]->(b:Chunk)
        RETURN COUNT(r) AS cnt
    """)
    adj_count = result.get_next()[0] if result.has_next() else 0
    print(f"  总数: {adj_count}")
    
    # 6. 样本 BELONGS_TO 边
    print("\n--- BELONGS_TO 样本 (前 10 条) ---")
    result = conn.execute("""
        MATCH (a:Chunk)-[r:BELONGS_TO]->(b:Chunk)
        RETURN a.chunk_id, a.chunk_type, b.chunk_id, b.chunk_type
        LIMIT 10
    """)
    while result.has_next():
        row = result.get_next()
        print(f"  {row[0]} ({row[1]}) -> {row[2]} ({row[3]})")
    
    # 7. document 节点数量
    print("\n--- Document 节点 ---")
    result = conn.execute("""
        MATCH (c:Chunk {chunk_type: 'document'})
        RETURN COUNT(c) AS cnt
    """)
    doc_count = result.get_next()[0] if result.has_next() else 0
    print(f"  document 节点数: {doc_count}")
    
    # 8. 无 BELONGS_TO 出边的节点（可能的孤立节点）
    print("\n--- 无 BELONGS_TO 入边的节点（可能的根） ---")
    result = conn.execute("""
        MATCH (c:Chunk)
        WHERE NOT EXISTS {
            MATCH (c)<-[r:BELONGS_TO]-(:Chunk)
        }
        RETURN c.chunk_type, COUNT(c) AS cnt
    """)
    while result.has_next():
        row = result.get_next()
        print(f"  {row[0] or '(null)'}: {row[1]}")
    
    # 9. 检查是否有 chunk_type 为空的节点
    print("\n--- chunk_type 为空的节点 ---")
    result = conn.execute("""
        MATCH (c:Chunk)
        WHERE c.chunk_type IS NULL OR c.chunk_type = ''
        RETURN COUNT(c) AS cnt
    """)
    null_type_count = result.get_next()[0] if result.has_next() else 0
    print(f"  数量: {null_type_count}")
    
    # 10. 图数据库文件路径
    print(f"\n--- 数据库路径 ---")
    db_path = KNOWLEDGE_BASE_DIR / "graph_db" / f"{subject}_v1_graph"
    print(f"  {db_path}")
    print(f"  存在: {db_path.exists()}")
    if db_path.exists():
        import os
        print(f"  大小: {os.path.getsize(str(db_path))} bytes")
    
    print(f"\n{'='*60}")
    print("诊断完成")
    print(f"{'='*60}")

if __name__ == "__main__":
    diagnose(SUBJECT)

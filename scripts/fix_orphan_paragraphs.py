#!/usr/bin/env python3
"""
修复脚本：为 heading_path 为空的 paragraph 补建到 document 的 BELONGS_TO 关系

使用方法：
  1. 先停止后端服务（释放 KuzuDB 文件锁）
  2. 运行: python scripts/fix_orphan_paragraphs.py rag
  3. 重新启动后端服务
"""
import sys
import re

sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore

def fix_orphan_paragraphs(subject):
    print(f"修复学科: {subject}")
    print("=" * 60)
    
    store = GraphStore(f"{subject}_v1")
    store.init_schema()
    conn = store._ensure_db()
    esc = store._escape_cypher_string
    
    # 1. 加载所有 chunks
    chunks = {}
    result = conn.execute("""
        MATCH (c:Chunk)
        RETURN c.chunk_id, c.chunk_type, c.heading_path, c.source
    """)
    while result.has_next():
        row = result.get_next()
        chunks[row[0]] = {
            'id': row[0], 'type': row[1], 'heading_path': row[2] or '',
            'source': row[3] or ''
        }
    
    docs = [c for c in chunks.values() if c['type'] == 'document']
    paragraphs = [c for c in chunks.values() if c['type'] == 'paragraph']
    images = [c for c in chunks.values() if c['type'] == 'image_pseudo']
    
    doc_by_source = {d['source']: d['id'] for d in docs}
    
    # 2. 找出已经存在的 BELONGS_TO 关系（避免重复创建）
    existing = set()
    result = conn.execute("""
        MATCH (a:Chunk)-[r:BELONGS_TO]->(b:Chunk)
        RETURN a.chunk_id, b.chunk_id
    """)
    while result.has_next():
        row = result.get_next()
        existing.add((row[0], row[1]))
    
    print(f"已有 BELONGS_TO 关系: {len(existing)} 条")
    print(f"document 节点: {len(docs)}")
    print(f"paragraph 节点: {len(paragraphs)}")
    print(f"image_pseudo 节点: {len(images)}")
    
    # 3. 为 heading_path 为空的 paragraph/image_pseudo 建立到 document 的关系
    orphans = []
    for child in paragraphs + images:
        hp = child['heading_path'].strip()
        if not hp:
            doc_id = doc_by_source.get(child['source'])
            if doc_id and (doc_id, child['id']) not in existing:
                orphans.append((doc_id, child['id'], child['source']))
    
    print(f"\n需要修复的孤立节点: {len(orphans)}")
    for doc_id, child_id, src in orphans[:10]:
        print(f"  {doc_id} -> {child_id} (source={src})")
    if len(orphans) > 10:
        print(f"  ... 等共 {len(orphans)} 个")
    
    # 4. 创建关系
    created = 0
    skipped = 0
    failed = 0
    for doc_id, child_id, src in orphans:
        try:
            conn.execute(f"""
                MATCH (a:Chunk {{chunk_id: '{esc(doc_id)}'}}), (b:Chunk {{chunk_id: '{esc(child_id)}'}})
                CREATE (a)-[:BELONGS_TO]->(b)
            """)
            created += 1
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  [WARN] 创建关系失败: {doc_id} -> {child_id}: {e}")
    
    print(f"\n修复结果:")
    print(f"  新建关系: {created}")
    print(f"  跳过(已存在): {skipped}")
    print(f"  失败: {failed}")
    
    # 5. 验证修复结果
    print(f"\n修复后验证:")
    result = conn.execute("""
        MATCH (a:Chunk)-[r:BELONGS_TO]->(b:Chunk)
        RETURN COUNT(r) AS cnt
    """)
    total = result.get_next()[0] if result.has_next() else 0
    print(f"  BELONGS_TO 总数: {total}")
    
    # 统计无入边的 paragraph
    result = conn.execute("""
        MATCH (c:Chunk {chunk_type: 'paragraph'})
        WHERE NOT EXISTS {
            MATCH (:Chunk)-[:BELONGS_TO]->(c)
        }
        RETURN COUNT(c) AS cnt
    """)
    orphan_count = result.get_next()[0] if result.has_next() else 0
    print(f"  无入边的 paragraph: {orphan_count}")

if __name__ == "__main__":
    subject = sys.argv[1] if len(sys.argv) > 1 else "rag"
    fix_orphan_paragraphs(subject)

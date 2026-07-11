#!/usr/bin/env python3
"""
诊断脚本：检查数据库中概念节点的 name/description 为空的情况
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore

def diagnose_concepts(subject: str = "generic_v1"):
    gs = GraphStore(subject)
    gs.init_schema()
    
    print(f"数据库路径: {gs.db_path}")
    print(f"数据库存在: {gs.db_path.exists()}")
    
    # 先检查所有节点类型
    conn = gs._ensure_db()
    
    try:
        result = conn.execute("MATCH (n) RETURN labels(n), count(n)")
        print("\n所有节点类型及数量:")
        while result.has_next():
            row = result.get_next()
            print(f"  {row[0]}: {row[1]}")
    except Exception as e:
        print(f"查询所有节点类型失败: {e}")
    
    # 查询 CanonicalConcept
    nodes = gs.get_canonical_concepts(limit=2000)
    
    total = len(nodes)
    print(f"\nCanonicalConcept 总数: {total}")
    
    if total == 0:
        # 尝试查询 ExtractedConcept
        extracted = gs.get_extracted_concepts(limit=2000)
        print(f"ExtractedConcept 总数: {len(extracted)}")
        if extracted:
            print("\nExtractedConcept 前3个:")
            for node in extracted[:3]:
                print(f"  {node}")
        return
    
    empty_name = 0
    empty_desc = 0
    empty_type = 0
    type_counts = {}
    
    for node in nodes:
        name = node.get("name") or ""
        desc = node.get("description") or ""
        ctype = node.get("type") or ""
        
        if not name.strip():
            empty_name += 1
        if not desc.strip():
            empty_desc += 1
        if not ctype.strip():
            empty_type += 1
            
        type_counts[ctype] = type_counts.get(ctype, 0) + 1
    
    print(f"\n空 name: {empty_name} ({empty_name/total*100:.1f}%)")
    print(f"空 description: {empty_desc} ({empty_desc/total*100:.1f}%)")
    print(f"空 type: {empty_type} ({empty_type/total*100:.1f}%)")
    print(f"\n类型分布:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t or '(空)'}: {c}")
    
    # 打印一些空 name 的示例
    print(f"\n空 name 示例 (前10个):")
    for node in nodes:
        name = node.get("name") or ""
        if not name.strip():
            print(f"  id={node['id']}, type={node.get('type')}, desc={node.get('description','')[:50]}")

if __name__ == "__main__":
    diagnose_concepts()

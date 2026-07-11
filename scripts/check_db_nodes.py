#!/usr/bin/env python3
"""
检查 测试_v1 数据库中的节点和边
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore

def check_subject(subject: str = "测试_v1"):
    gs = GraphStore(subject)
    gs.init_schema()
    
    conn = gs._ensure_db()
    
    # 检查所有节点类型
    print(f"=== {subject} 数据库检查 ===")
    
    node_types = [
        ("Chunk", "chunk_id"),
        ("Concept", "concept_id"),
        ("CanonicalConcept", "canonical_id"),
        ("ExtractedConcept", "extracted_id"),
    ]
    
    for label, id_field in node_types:
        try:
            result = conn.execute(f"MATCH (n:{label}) RETURN count(n)")
            if result.has_next():
                count = result.get_next()[0]
                print(f"  {label}: {count} 个节点")
            else:
                print(f"  {label}: 0 个节点")
        except Exception as e:
            print(f"  {label}: 查询失败 - {e}")
    
    # 检查边
    edge_types = ["BELONGS_TO", "ADJACENT_TO", "SOLUTION", "DEPENDS_ON", "DEFINES", "HAS_LAW", "APPLIES_TO", "EXTENDS"]
    print(f"\n  边类型:")
    for et in edge_types:
        try:
            result = conn.execute(f"MATCH ()-[r:{et}]->() RETURN count(r)")
            if result.has_next():
                count = result.get_next()[0]
                print(f"    {et}: {count}")
        except Exception:
            pass
    
    # 检查 canonical 节点是否有数据
    print(f"\n  CanonicalConcept 前5个:")
    try:
        result = conn.execute("MATCH (c:CanonicalConcept) RETURN c.canonical_id, c.name LIMIT 5")
        while result.has_next():
            row = result.get_next()
            print(f"    {row[0]}: {row[1]}")
    except Exception as e:
        print(f"    查询失败: {e}")
    
    # 检查 concept_canonical_2e3b5de367 是否存在
    print(f"\n  检查 concept_canonical_2e3b5de367:")
    for label in ["CanonicalConcept", "Concept", "ExtractedConcept"]:
        try:
            id_field = "canonical_id" if label == "CanonicalConcept" else "concept_id" if label == "Concept" else "extracted_id"
            result = conn.execute(f"MATCH (c:{label} {{{id_field}: 'concept_canonical_2e3b5de367'}}) RETURN c.{id_field}, c.name")
            if result.has_next():
                row = result.get_next()
                print(f"    在 {label} 中找到: {row[0]} = {row[1]}")
            else:
                print(f"    在 {label} 中: 未找到")
        except Exception as e:
            print(f"    在 {label} 中查询失败: {e}")

if __name__ == "__main__":
    check_subject("测试_v1")
    print("\n---\n")
    check_subject("generic_v1")

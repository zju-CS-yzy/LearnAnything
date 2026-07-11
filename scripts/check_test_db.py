#!/usr/bin/env python3
"""
检查 测试_v1 数据库内容 - 只读查询，避免锁
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

from core.graph_store import GraphStore

gs = GraphStore("测试_v1")
gs.init_schema()
conn = gs._ensure_db()

print("=== 测试_v1 数据库检查 ===")

# 检查节点类型
for label, idf in [
    ("Chunk", "chunk_id"),
    ("Concept", "concept_id"),
    ("CanonicalConcept", "canonical_id"),
    ("ExtractedConcept", "extracted_id"),
]:
    try:
        result = conn.execute(f"MATCH (n:{label}) RETURN count(n)")
        if result.has_next():
            print(f"  {label}: {result.get_next()[0]} 个")
    except Exception as e:
        print(f"  {label}: 错误 - {e}")

# 检查 concept_canonical_2e3b5de367
for label, idf in [
    ("CanonicalConcept", "canonical_id"),
    ("Concept", "concept_id"),
    ("ExtractedConcept", "extracted_id"),
]:
    try:
        result = conn.execute(f"MATCH (c:{label} {{{idf}: 'concept_canonical_2e3b5de367'}}) RETURN c.{idf}, c.name")
        if result.has_next():
            row = result.get_next()
            print(f"  找到 {label}: {row[0]} = {row[1]}")
        else:
            print(f"  {label}: 未找到 concept_canonical_2e3b5de367")
    except Exception as e:
        print(f"  {label}: 查询错误 - {e}")

# 检查 source_chunks 字段（get_subgraph 查询用的）
print("\n  CanonicalConcept 前3个节点:")
try:
    result = conn.execute("MATCH (c:CanonicalConcept) RETURN c.canonical_id, c.name, c.source_chunks LIMIT 3")
    while result.has_next():
        row = result.get_next()
        print(f"    {row[0]}: {row[1]} | source_chunks={row[2]}")
except Exception as e:
    print(f"    错误: {e}")

# 检查边类型
print("\n  边数量:")
for et in ["BELONGS_TO", "ADJACENT_TO", "SOLUTION", "DEPENDS_ON", "DEFINES", "HAS_LAW", "APPLIES_TO", "EXTENDS", "REQUIRES", "IMPLEMENTS", "HAS_SUB", "HAS_IMPL", "DERIVED_FROM"]:
    try:
        result = conn.execute(f"MATCH ()-[r:{et}]->() RETURN count(r)")
        if result.has_next():
            cnt = result.get_next()[0]
            if cnt > 0:
                print(f"    {et}: {cnt}")
    except Exception:
        pass

print("\n  DERIVED_FROM 边 (CanonicalConcept 间):")
try:
    result = conn.execute("MATCH ()-[r:DERIVED_FROM]->() RETURN count(r)")
    if result.has_next():
        print(f"    DERIVED_FROM: {result.get_next()[0]}")
except Exception as e:
    print(f"    错误: {e}")

print("\n  SOLUTION / DEPENDS_ON 边 (CanonicalConcept 间):")
for et in ["SOLUTION", "DEPENDS_ON"]:
    try:
        result = conn.execute(f"MATCH ()-[r:{et}]->() RETURN count(r)")
        if result.has_next():
            print(f"    {et}: {result.get_next()[0]}")
    except Exception as e:
        print(f"    {et}: 错误 - {e}")

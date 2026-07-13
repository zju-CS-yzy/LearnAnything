"""
ConceptDeduper 去重逻辑诊断（修正版：正确解析 JSON）
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import json
from core.graph_store import GraphStore

COLLECTION = "rag技术_v1"

print("=" * 60)
print("ConceptDeduper Dedupe Logic Diagnostic (Corrected)")
print("=" * 60)

store = GraphStore(COLLECTION)
conn = store._ensure_db()

# 1. 统计 ExtractedConcept 的 source_chunk 分布
print("\n[1] ExtractedConcept source_chunk distribution")

result = store._execute(conn, """
    MATCH (e:ExtractedConcept)
    RETURN e.source_chunk, COUNT(e) as cnt
    ORDER BY cnt DESC
    LIMIT 20
""")

source_chunk_dist = {}
while result.has_next():
    row = result.get_next()
    sc = row[0]
    cnt = row[1]
    source_chunk_dist[sc] = cnt

print(f"  Unique source_chunks: {len(source_chunk_dist)}")
for sc, cnt in list(source_chunk_dist.items())[:10]:
    print(f"    {sc[:50]}: {cnt} concepts")

# 2. 检查每个 chunk 提取了多少概念
print("\n[2] Concepts per chunk (top 10)")
for sc, cnt in sorted(source_chunk_dist.items(), key=lambda x: -x[1])[:10]:
    print(f"    {sc[:50]}: {cnt} concepts")

# 3. ExtractedConcept 名称重复情况
print("\n[3] ExtractedConcept name duplication")

result = store._execute(conn, """
    MATCH (e:ExtractedConcept)
    RETURN e.name, COUNT(e) as cnt
    ORDER BY cnt DESC
    LIMIT 20
""")

name_repeats = {}
while result.has_next():
    row = result.get_next()
    name = row[0]
    cnt = row[1]
    name_repeats[name] = cnt

print(f"  Most repeated names:")
for name, cnt in list(name_repeats.items())[:10]:
    print(f"    '{name}': {cnt} times")

# 4. 正确解析 source_chunks JSON
print("\n[4] Corrected CanonicalConcept source_chunks analysis")

result = store._execute(conn, """
    MATCH (c:CanonicalConcept)
    RETURN c.name, c.source_chunks
""")

source_counts = []
while result.has_next():
    row = result.get_next()
    name = row[0]
    source_chunks_str = row[1] or ""
    
    # Parse JSON
    try:
        source_chunks = json.loads(source_chunks_str) if source_chunks_str else []
    except:
        source_chunks = []
    
    source_counts.append((name, len(source_chunks), source_chunks))

# Distribution
from collections import Counter
dist = Counter([sc for _, sc, _ in source_counts])
print(f"  Source count distribution:")
for sc, cnt in sorted(dist.items()):
    print(f"    {sc} sources: {cnt} concepts ({cnt/len(source_counts)*100:.1f}%)")

# Multi-source samples
print(f"\n  Multi-source samples (top 5):")
for name, sc, chunks in sorted(source_counts, key=lambda x: -x[1])[:5]:
    if sc > 1:
        print(f"    '{name}': {sc} sources")
        for c in chunks[:3]:
            print(f"      - {c[:50]}")
        if len(chunks) > 3:
            print(f"      ... and {len(chunks) - 3} more")

# 5. Aliases analysis (corrected)
print("\n[5] Corrected aliases analysis")

result = store._execute(conn, """
    MATCH (c:CanonicalConcept)
    RETURN c.name, c.aliases
    LIMIT 10
""")

while result.has_next():
    row = result.get_next()
    name = row[0]
    aliases_str = row[1] or ""
    try:
        aliases = json.loads(aliases_str) if aliases_str else []
    except:
        aliases = []
    print(f"  '{name}': {len(aliases)} aliases")
    if aliases:
        print(f"    {aliases[:5]}")

# 6. 去重效果分析：ExtractedConcept 185 vs CanonicalConcept 156
print("\n[6] Deduplication effect")
print(f"  ExtractedConcept: 185")
print(f"  CanonicalConcept: 156")
print(f"  Reduction: {(185-156)/185*100:.1f}%")
print(f"  Avg aliases per canonical: {185/156:.1f}")

print("\n" + "=" * 60)
print("Diagnostic complete")
print("=" * 60)

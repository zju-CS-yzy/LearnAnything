"""
LA-035-P12 概念重叠分析：基于 GraphStore 中的 ExtractedConcept
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import json
from collections import defaultdict
from core.graph_store import GraphStore

SUBJECT = "rag技术"
COLLECTION = f"{SUBJECT}_v1"

print("=" * 60)
print("LA-035-P12: Concept Overlap Analysis")
print(f"Collection: {COLLECTION}")
print("=" * 60)

store = GraphStore(COLLECTION)
conn = store._ensure_db()

# 1. 读取所有 Chunk 的 chunk_type
print("\n[1] Loading chunk types...")
chunk_types = {}
result = store._execute(conn, "MATCH (c:Chunk) RETURN c.chunk_id, c.chunk_type, c.heading_path")
while result.has_next():
    row = result.get_next()
    chunk_types[row[0]] = {"type": row[1] or "unknown", "heading_path": row[2] or ""}

print(f"  Total chunks: {len(chunk_types)}")

heading_chunks = {cid: info for cid, info in chunk_types.items() if info["type"] == "heading"}
paragraph_chunks = {cid: info for cid, info in chunk_types.items() if info["type"] == "paragraph"}

print(f"  Heading chunks: {len(heading_chunks)}")
print(f"  Paragraph chunks: {len(paragraph_chunks)}")

# 2. 读取 HAS_CONCEPT 关系，建立 chunk -> concept 映射
print("\n[2] Loading HAS_CONCEPT relations...")
chunk_to_concepts = defaultdict(list)

result = store._execute(conn, """
    MATCH (ch:Chunk)-[:HAS_CONCEPT]->(e:ExtractedConcept)
    RETURN ch.chunk_id, e.extracted_id, e.name, e.concept_type
""")

while result.has_next():
    row = result.get_next()
    chunk_id, extracted_id, name, concept_type = row
    chunk_to_concepts[chunk_id].append({
        "extracted_id": extracted_id,
        "name": name,
        "concept_type": concept_type,
    })

print(f"  Chunks with concepts: {len(chunk_to_concepts)}")

# 3. 分离 Heading 和 Paragraph 的概念
print("\n[3] Separating concepts by chunk type...")

heading_concepts = []  # (name, concept_type, chunk_id, heading_path)
paragraph_concepts = []  # (name, concept_type, chunk_id, heading_path)

for chunk_id, concepts in chunk_to_concepts.items():
    chunk_info = chunk_types.get(chunk_id, {})
    ctype = chunk_info.get("type", "unknown")
    hp = chunk_info.get("heading_path", "")
    
    for c in concepts:
        if ctype == "heading":
            heading_concepts.append((c["name"], c["concept_type"], chunk_id, hp))
        elif ctype == "paragraph":
            paragraph_concepts.append((c["name"], c["concept_type"], chunk_id, hp))

print(f"  Heading concepts: {len(heading_concepts)}")
print(f"  Paragraph concepts: {len(paragraph_concepts)}")

# 4. 去重统计
heading_unique = set(name for name, _, _, _ in heading_concepts)
paragraph_unique = set(name for name, _, _, _ in paragraph_concepts)

print(f"  Unique heading concepts: {len(heading_unique)}")
print(f"  Unique paragraph concepts: {len(paragraph_unique)}")

# 5. 计算重叠率
print("\n[4] Computing overlap rates...")

if heading_unique and paragraph_unique:
    intersection = heading_unique & paragraph_unique
    union = heading_unique | paragraph_unique
    
    jaccard = len(intersection) / len(union) if union else 0
    heading_overlap_rate = len(intersection) / len(heading_unique) if heading_unique else 0
    paragraph_overlap_rate = len(intersection) / len(paragraph_unique) if paragraph_unique else 0
    
    print(f"  Intersection: {len(intersection)}")
    print(f"  Union: {len(union)}")
    print(f"  Jaccard similarity: {jaccard:.2%}")
    print(f"  Heading overlap rate: {heading_overlap_rate:.2%}")
    print(f"  Paragraph overlap rate: {paragraph_overlap_rate:.2%}")
    
    # 重叠概念示例
    print(f"\n  Overlap examples (first 20):")
    for name in sorted(list(intersection))[:20]:
        h_count = sum(1 for n, _, _, _ in heading_concepts if n == name)
        p_count = sum(1 for n, _, _, _ in paragraph_concepts if n == name)
        print(f"    - '{name}' (H:{h_count}, P:{p_count})")
else:
    intersection = set()
    jaccard = 0
    heading_overlap_rate = 0
    paragraph_overlap_rate = 0
    print("  Not enough data to compute overlap")

# 6. 分析同 heading_path 下的概念重叠
print("\n[5] Analyzing overlap within same heading_path...")

# 按 heading_path 分组
heading_path_concepts = defaultdict(lambda: {"heading": set(), "paragraph": set()})

for name, _, chunk_id, hp in heading_concepts:
    if hp:
        heading_path_concepts[hp]["heading"].add(name)

for name, _, chunk_id, hp in paragraph_concepts:
    if hp:
        heading_path_concepts[hp]["paragraph"].add(name)

same_hp_overlaps = 0
same_hp_total_heading = 0
same_hp_details = []

for hp, concepts in heading_path_concepts.items():
    h_set = concepts["heading"]
    p_set = concepts["paragraph"]
    if h_set and p_set:
        overlap = h_set & p_set
        same_hp_total_heading += len(h_set)
        same_hp_overlaps += len(overlap)
        if overlap:
            same_hp_details.append((hp, overlap, h_set, p_set))

if same_hp_total_heading > 0:
    same_hp_rate = same_hp_overlaps / same_hp_total_heading
    print(f"  Same heading_path overlap: {same_hp_overlaps}/{same_hp_total_heading} ({same_hp_rate:.1%})")
    print(f"  Groups with overlap: {len(same_hp_details)}")
    
    for hp, overlap, h_all, p_all in same_hp_details[:5]:
        hp_safe = hp.encode('ascii', 'replace').decode('ascii')[:60]
        print(f"\n    Path: '{hp_safe}'")
        print(f"    Heading concepts ({len(h_all)}):")
        for c in sorted(h_all)[:8]:
            print(f"      - {c}")
        print(f"    Paragraph concepts ({len(p_all)}):")
        for c in sorted(p_all)[:8]:
            print(f"      - {c}")
        print(f"    Overlap ({len(overlap)}):")
        for c in sorted(overlap)[:5]:
            print(f"      >> {c}")
else:
    same_hp_rate = 0
    print("  No same heading_path overlap data")

# 7. 概念抽象度分析
print("\n[6] Concept abstraction analysis...")

# 检查 heading 概念是否包含更抽象的特征
abstract_keywords = ["架构", "框架", "原理", "机制", "方法", "理论", "系统", "模型", "策略", "范式", "流程", " overview", "概述"]

heading_abstract = sum(1 for name, _, _, _ in heading_concepts if any(kw in name for kw in abstract_keywords))
paragraph_abstract = sum(1 for name, _, _, _ in paragraph_concepts if any(kw in name for kw in abstract_keywords))

if heading_concepts:
    print(f"  Heading with abstract keywords: {heading_abstract}/{len(heading_concepts)} ({heading_abstract/len(heading_concepts):.1%})")
if paragraph_concepts:
    print(f"  Paragraph with abstract keywords: {paragraph_abstract}/{len(paragraph_concepts)} ({paragraph_abstract/len(paragraph_concepts):.1%})")

# 概念长度分析
heading_name_lengths = [len(name) for name, _, _, _ in heading_concepts]
paragraph_name_lengths = [len(name) for name, _, _, _ in paragraph_concepts]

if heading_name_lengths:
    avg_h = sum(heading_name_lengths) / len(heading_name_lengths)
    print(f"  Heading concept avg length: {avg_h:.1f} chars")
if paragraph_name_lengths:
    avg_p = sum(paragraph_name_lengths) / len(paragraph_name_lengths)
    print(f"  Paragraph concept avg length: {avg_p:.1f} chars")

# 8. 最终建议
print("\n" + "=" * 60)
print("[CONCLUSION & RECOMMENDATION]")
print("=" * 60)

avg_overlap = (heading_overlap_rate + paragraph_overlap_rate) / 2

print(f"\nKey Metrics:")
print(f"  - Heading chunks: {len(heading_chunks)}")
print(f"  - Paragraph chunks: {len(paragraph_chunks)}")
print(f"  - Heading concepts: {len(heading_unique)}")
print(f"  - Paragraph concepts: {len(paragraph_unique)}")
print(f"  - Jaccard overlap: {jaccard:.1%}")
print(f"  - Average overlap rate: {avg_overlap:.1%}")
print(f"  - Same heading_path overlap: {same_hp_rate:.1%}" if same_hp_total_heading > 0 else "  - Same heading_path overlap: N/A")

print(f"\nRecommendation:")
if avg_overlap > 0.7:
    print("  [SCHEME A] Heading as pure container")
    print("  Reason: Overlap > 70%, heading concepts are highly redundant with paragraphs")
    print("  Action: Do not extract concepts from HeadingChunks")
    print("  Risk: May lose the title's semantic information")
elif avg_overlap > 0.3:
    print("  [SCHEME B] Abstraction-level stratification")
    print("  Reason: Overlap 30-70%, concepts are somewhat complementary")
    print("  Action: Extract abstract concepts from headings, detailed from paragraphs")
    print("  Risk: LLM may not consistently distinguish abstraction levels")
else:
    print("  [SCHEME C] Optimize deduplication")
    print("  Reason: Overlap < 30%, concepts are highly complementary")
    print("  Action: Keep current extraction, improve dedup strategy")
    print("  Risk: Minimal")

print("\n" + "=" * 60)
print("Analysis complete")
print("=" * 60)

"""
诊断：为什么部分 chunk 没有提取出概念
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import json
from collections import Counter
from core.graph_store import GraphStore

COLLECTION = "rag技术_v1"

print("=" * 60)
print("Chunk 概念提取遗漏诊断")
print("=" * 60)

store = GraphStore(COLLECTION)
conn = store._ensure_db()

# 1. 读取所有 Chunk
print("\n[1] 所有 Chunk 分析")
result = store._execute(conn, """
    MATCH (c:Chunk)
    RETURN c.chunk_id, c.chunk_type, c.heading_path, c.text
""")

all_chunks = {}
chunk_types = Counter()
chunk_text_lens = []
while result.has_next():
    row = result.get_next()
    cid = row[0]
    ctype = row[1] or "unknown"
    hp = row[2] or ""
    text = row[3] or ""
    all_chunks[cid] = {"type": ctype, "heading_path": hp, "text": text}
    chunk_types[ctype] += 1
    chunk_text_lens.append(len(text))

print(f"  总 chunk 数: {len(all_chunks)}")
for ctype, cnt in sorted(chunk_types.items(), key=lambda x: -x[1]):
    print(f"    {ctype}: {cnt}")

if chunk_text_lens:
    avg_len = sum(chunk_text_lens) / len(chunk_text_lens)
    print(f"  平均文本长度: {avg_len:.0f} chars")
    print(f"  最小文本长度: {min(chunk_text_lens)}")
    print(f"  最大文本长度: {max(chunk_text_lens)}")

# 2. 读取有概念的 chunk
print("\n[2] 有 ExtractedConcept 的 chunk")
result = store._execute(conn, """
    MATCH (e:ExtractedConcept)
    RETURN DISTINCT e.source_chunk as sc
""")

chunks_with_concepts = set()
while result.has_next():
    row = result.get_next()
    chunks_with_concepts.add(row[0])

print(f"  有概念的 chunk: {len(chunks_with_concepts)}")

# 3. 找出没有概念的 chunk
print("\n[3] 没有概念的 chunk 分析")
chunks_without_concepts = []
for cid, info in all_chunks.items():
    if cid not in chunks_with_concepts:
        chunks_without_concepts.append((cid, info))

print(f"  无概念的 chunk: {len(chunks_without_concepts)}")

# 按类型分组
no_concept_types = Counter()
for cid, info in chunks_without_concepts:
    no_concept_types[info["type"]] += 1

for ctype, cnt in sorted(no_concept_types.items(), key=lambda x: -x[1]):
    print(f"    {ctype}: {cnt}")

# 4. 详细分析每种类型的无概念原因
print("\n[4] 各类型无概念原因分析")

for ctype in sorted(set(no_concept_types.keys())):
    type_chunks = [(cid, info) for cid, info in chunks_without_concepts if info["type"] == ctype]
    print(f"\n  {ctype} ({len(type_chunks)} 个):")
    
    # 文本长度统计
    lens = [len(info["text"]) for _, info in type_chunks]
    if lens:
        avg = sum(lens) / len(lens)
        print(f"    平均文本长度: {avg:.0f} (min={min(lens)}, max={max(lens)})")
    
    # 显示前3个样本
    for cid, info in type_chunks[:3]:
        text_preview = info["text"][:100].encode('ascii', 'replace').decode('ascii')
        print(f"    {cid[:50]}:")
        print(f"      文本: {text_preview}...")

# 5. 检查 heading chunk 的文本内容
print("\n[5] Heading chunk 文本样本（被排除不提取）")
heading_chunks = [(cid, info) for cid, info in chunks_without_concepts if info["type"] == "heading"]
for cid, info in heading_chunks[:5]:
    text_preview = info["text"][:100].encode('ascii', 'replace').decode('ascii')
    print(f"  {cid[:50]}:")
    print(f"    {text_preview}...")

# 6. 检查 image_pseudo chunk 的情况
print("\n[6] image_pseudo chunk 分析")
image_chunks = [(cid, info) for cid, info in chunks_without_concepts if info["type"] == "image_pseudo"]
print(f"  无概念的 image_pseudo: {len(image_chunks)}")

for cid, info in image_chunks[:5]:
    text_preview = info["text"][:100].encode('ascii', 'replace').decode('ascii')
    print(f"  {cid[:50]}:")
    print(f"    文本: {text_preview}...")

# 7. 检查是否有 chunk 文本为空（被过滤）
print("\n[7] 文本为空的 chunk 统计")
empty_text_chunks = [(cid, info) for cid, info in chunks_without_concepts if not info["text"].strip()]
print(f"  文本为空: {len(empty_text_chunks)}")
for cid, info in empty_text_chunks[:5]:
    print(f"    {cid} ({info['type']})")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)

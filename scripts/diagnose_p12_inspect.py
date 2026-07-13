"""
LA-035-P12 诊断脚本：RAG 学科 chunk 结构分析
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import json
import sqlite3
from pathlib import Path
from collections import defaultdict
from config.settings import VECTOR_DB_DIR

# 使用有数据的 collection
SUBJECT = "rag技术"

print("=" * 60)
print("LA-035-P12 Diagnosis: RAG Subject Chunk Structure")
print(f"Subject: {SUBJECT}")
print("=" * 60)

vec_db_path = VECTOR_DB_DIR / f"{SUBJECT}_v1.db"
print(f"\nVector DB: {vec_db_path}")
print(f"Exists: {vec_db_path.exists()}")

if not vec_db_path.exists():
    print("No data found")
    sys.exit(0)

conn = sqlite3.connect(str(vec_db_path))

# 1. 统计文档总数
cursor = conn.execute("SELECT COUNT(*) FROM documents")
total = cursor.fetchone()[0]
print(f"Total documents: {total}")

if total == 0:
    print("Empty database")
    sys.exit(0)

# 2. 读取所有文档并分析类型
cursor = conn.execute("SELECT id, text, metadata FROM documents")

types = defaultdict(int)
heading_chunks = []
paragraph_chunks = []
document_chunks = []
image_chunks = []
other_chunks = []

heading_path_groups = defaultdict(list)

for row in cursor:
    doc_id, text, meta_json = row
    meta = json.loads(meta_json) if meta_json else {}
    ctype = meta.get("type", meta.get("chunk_type", "unknown"))
    hp = meta.get("heading_path", "")
    
    chunk = {"id": doc_id, "text": text[:100] if text else "", "metadata": meta, "heading_path": hp}
    
    types[ctype] += 1
    
    if ctype == "heading":
        heading_chunks.append(chunk)
    elif ctype == "paragraph":
        paragraph_chunks.append(chunk)
    elif ctype == "document":
        document_chunks.append(chunk)
    elif ctype in ("image", "image_pseudo"):
        image_chunks.append(chunk)
    else:
        other_chunks.append(chunk)
    
    if hp:
        heading_path_groups[hp].append(chunk)

print(f"\n--- Type Distribution ---")
for t, c in sorted(types.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

print(f"\n--- Chunk Counts ---")
print(f"  HeadingChunk: {len(heading_chunks)}")
print(f"  ParagraphChunk: {len(paragraph_chunks)}")
print(f"  DocumentChunk: {len(document_chunks)}")
print(f"  ImageChunk: {len(image_chunks)}")
print(f"  Other: {len(other_chunks)}")

print(f"\n--- Heading Path Groups ---")
print(f"  Total groups: {len(heading_path_groups)}")

# 3. 分析 heading 层级深度
heading_levels = defaultdict(int)
for chunk in heading_chunks:
    level = chunk["metadata"].get("heading_level", 0)
    heading_levels[level] += 1

print(f"\n--- Heading Level Distribution ---")
for level, count in sorted(heading_levels.items()):
    print(f"  Level {level}: {count}")

# 4. 分析 heading 和 paragraph 的内容关系
print(f"\n--- Heading vs Paragraph Content Analysis ---")

# 统计 heading 文本长度
heading_text_lengths = [len(c["text"]) for c in heading_chunks]
paragraph_text_lengths = [len(c["text"]) for c in paragraph_chunks]

if heading_text_lengths:
    avg_h = sum(heading_text_lengths) / len(heading_text_lengths)
    print(f"  Heading avg text length: {avg_h:.0f} chars (min={min(heading_text_lengths)}, max={max(heading_text_lengths)})")

if paragraph_text_lengths:
    avg_p = sum(paragraph_text_lengths) / len(paragraph_text_lengths)
    print(f"  Paragraph avg text length: {avg_p:.0f} chars (min={min(paragraph_text_lengths)}, max={max(paragraph_text_lengths)})")

# 5. 分析同 heading_path 下的结构
print(f"\n--- Sample Heading Path Structures (first 5) ---")
for i, (hp, chunks) in enumerate(sorted(heading_path_groups.items(), key=lambda x: -len(x[1]))[:5]):
    hp_safe = hp.encode('ascii', 'replace').decode('ascii')[:80]
    print(f"\n  Group {i+1}: '{hp_safe}' ({len(chunks)} chunks)")
    for c in chunks[:8]:
        ctype = c["metadata"].get("type", c["metadata"].get("chunk_type", "unknown"))
        text_preview = c["text"][:60].encode('ascii', 'replace').decode('ascii') if c["text"] else "(empty)"
        print(f"    [{ctype}] {text_preview}")
    if len(chunks) > 8:
        print(f"    ... and {len(chunks) - 8} more")

# 6. 检查是否有图数据库中的概念
print(f"\n--- Graph DB Check ---")
from core.graph_store import GraphStore

try:
    store = GraphStore(f"{SUBJECT}_v1")
    stats = store.get_graph_stats()
    print(f"  Graph stats: {json.dumps(stats, indent=2)}")
except Exception as e:
    print(f"  Graph DB not available: {e}")

# 7. 文本重叠分析（heading 文本 vs paragraph 文本的相似性）
print(f"\n--- Text Overlap Analysis ---")

# 对于每个 heading，检查其下属 paragraph 是否有文本重叠
overlap_count = 0
total_heading_paragraph_pairs = 0
overlap_examples = []

for hp, group_chunks in heading_path_groups.items():
    if not hp:
        continue
    
    h_texts = [c["text"].lower() for c in group_chunks if c["metadata"].get("type") == "heading"]
    p_texts = [c["text"].lower() for c in group_chunks if c["metadata"].get("type") == "paragraph"]
    
    if h_texts and p_texts:
        for h_text in h_texts:
            for p_text in p_texts:
                total_heading_paragraph_pairs += 1
                # 简单判断：heading 文本是否在 paragraph 文本中出现
                if h_text and p_text and (h_text in p_text or p_text in h_text):
                    overlap_count += 1
                    if len(overlap_examples) < 5:
                        overlap_examples.append((hp, h_text[:50], p_text[:50]))

if total_heading_paragraph_pairs > 0:
    overlap_rate = overlap_count / total_heading_paragraph_pairs
    print(f"  Total H-P pairs: {total_heading_paragraph_pairs}")
    print(f"  Text overlap pairs: {overlap_count}")
    print(f"  Overlap rate: {overlap_rate:.1%}")
    
    if overlap_examples:
        print(f"  Examples:")
        for hp, h, p in overlap_examples:
            print(f"    H: '{h}...'")
            print(f"    P: '{p}...'")
            print(f"    Path: {hp[:60]}")
            print()

print("\n" + "=" * 60)
print("Diagnosis complete")
print("=" * 60)

conn.close()

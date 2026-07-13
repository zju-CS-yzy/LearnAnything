"""
LA-035-P12: 重建 RAG 学科图谱（使用 heading context 注入方案）
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import os

# 设置 API keys
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-68bba93f2b674a5487404da932940a1f")
os.environ.setdefault("ZHIPU_API_KEY", "fc82d87430c445669e54524455d293b0.EDbHDbsyR52hrol6")

from core.graph_builder import GraphBuilder

COLLECTION = "rag技术_v1"

print("=" * 60)
print(f"Rebuilding knowledge graph: {COLLECTION}")
print("=" * 60)

builder = GraphBuilder(COLLECTION, paradigm="theory")

# Phase 1: 结构层
print("\n[Phase 1] Building structure layer...")
result1 = builder.build_all(force_rebuild=True)
print(f"  Chunks: {result1['chunks_total']}")
print(f"  BELONGS_TO edges: {result1['belongs_to_edges']}")
print(f"  ADJACENT_TO edges: {result1['adjacent_to_edges']}")

# Phase 2: 语义层
print("\n[Phase 2] Extracting concepts (with heading context)...")
result2 = builder.extract_all_concepts()
print(f"  Status: {result2['status']}")
print(f"  Chunks processed: {result2['chunks_processed']}")
print(f"  Chunks extracted: {result2['chunks_extracted']}")
print(f"  Chunks failed: {result2['chunks_failed']}")
print(f"  Heading groups: {result2['heading_groups']}")
print(f"  Avg quality: {result2['avg_quality_score']}")

# Phase 2.5: 去重
print("\n[Phase 2.5] Deduplicating concepts...")
result3 = builder.dedupe_concepts()
print(f"  Status: {result3['status']}")

# Phase 2.5: 语义连接
print("\n[Phase 2.5] Linking concepts...")
result4 = builder.link_concepts(paradigm="engineering")
print(f"  Status: {result4['status']}")

# 最终统计
print("\n[Final Stats]")
from core.graph_store import GraphStore
store = GraphStore(COLLECTION)
stats = store.get_graph_stats()
for k, v in stats.items():
    print(f"  {k}: {v}")

print("\n" + "=" * 60)
print("Rebuild complete!")
print("=" * 60)

"""
LA-035-P14 fix: Rebuild RAG with consistent paradigm (theory)
"""
import sys
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

import os

os.environ.setdefault("DEEPSEEK_API_KEY", "sk-68bba93f2b674a5487404da932940a1f")
os.environ.setdefault("ZHIPU_API_KEY", "fc82d87430c445669e54524455d293b0.EDbHDbsyR52hrol6")

from core.graph_builder import GraphBuilder

COLLECTION = "rag技术_v1"

print("=" * 60)
print(f"Rebuilding: {COLLECTION} (theory paradigm)")
print("=" * 60)

builder = GraphBuilder(COLLECTION, paradigm="theory")

# Phase 1
print("\n[Phase 1] Structure layer...")
result1 = builder.build_all(force_rebuild=True)
print(f"  Chunks: {result1['chunks_total']}")

# Phase 2
print("\n[Phase 2] Extracting concepts (with heading context)...")
result2 = builder.extract_all_concepts()
print(f"  Status: {result2['status']}")
print(f"  Extracted: {result2['chunks_extracted']}")

# Phase 2.5
print("\n[Phase 2.5] Deduplicating...")
result3 = builder.dedupe_concepts()
print(f"  Status: {result3['status']}")

# Phase 2.5: Semantic linking (MUST match extraction paradigm)
print("\n[Phase 2.5] Linking concepts (theory paradigm)...")
result4 = builder.link_concepts(paradigm="theory")
print(f"  Status: {result4['status']}")
print(f"  Edges created: {result4.get('edges_created', 0)}")
print(f"  By stage: {result4.get('by_stage', {})}")

# Final stats
print("\n[Final Stats]")
from core.graph_store import GraphStore
store = GraphStore(COLLECTION)
stats = store.get_graph_stats()
for k, v in stats.items():
    print(f"  {k}: {v}")

print("\n" + "=" * 60)
print("Rebuild complete!")
print("=" * 60)

#!/usr/bin/env python3
"""清空 Concept 节点并重新提取（用于修复后重建）"""
import sys, os
sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-68bba93f2b674a5487404da932940a1f")
os.environ.setdefault("ZHIPU_API_KEY", "fc82d87430c445669e54524455d293b0.EDbHDbsyR52hrol6")

from core.graph_builder import GraphBuilder
from core.graph_store import GraphStore

SUBJECT = "generic_v1"

# 1. 初始化 builder（内部会创建 GraphStore）
print("=== 初始化 GraphBuilder ===")
builder = GraphBuilder(SUBJECT, paradigm="engineering")
store = builder.graph_store  # 复用同一个实例
store.init_schema()
conn = store._ensure_db()

# 2. 删除所有 Concept 节点和语义关系
print("=== 清理旧 Concept 数据 ===")
try:
    result = conn.execute("MATCH (c:Concept) RETURN COUNT(c) AS cnt")
    if result.has_next():
        count = result.get_next()[0]
        print(f"  发现 {count} 个旧 Concept 节点，正在删除...")
except Exception as e:
    print(f"  查询失败: {e}")

try:
    conn.execute("MATCH (c:Concept) DETACH DELETE c")
    print("  已删除所有 Concept 节点")
except Exception as e:
    print(f"  删除失败: {e}")

# 3. 清空 JSONL 文件
import json
from config.settings import KNOWLEDGE_BASE_DIR
details_path = KNOWLEDGE_BASE_DIR / "concept_details" / f"{SUBJECT}.jsonl"
if details_path.exists():
    open(details_path, "w").close()
    print("  已清空 concept_details JSONL")

# 4. 重新提取
print("\n=== 重新提取概念（工程分解范式）===")
extract_result = builder.extract_all_concepts()
print(f"\n提取完成:")
print(f"  处理 chunk: {extract_result.get('chunks_processed', 0)}")
print(f"  成功提取: {extract_result.get('chunks_extracted', 0)}")
print(f"  失败: {extract_result.get('chunks_failed', 0)}")
print(f"  平均质量分: {extract_result.get('avg_quality_score', 0)}")

# 5. 去重
print("\n=== 概念去重 ===")
dedupe_result = builder.dedupe_concepts()
print(f"  Canonical 概念: {dedupe_result.get('canonical_concepts', 0)}")
print(f"  CSV 路径: {dedupe_result.get('csv_path', 'N/A')}")

# 6. 语义连接
print("\n=== 全局语义连接 ===")
link_result = builder.link_concepts(paradigm="engineering")
print(f"  创建连接边: {link_result.get('edges_created', 0)}")
print(f"  parent_hint 匹配: {link_result.get('by_stage', {}).get('parent_hint_match', 0)}")
print(f"  embedding+LLM: {link_result.get('by_stage', {}).get('embedding_llm', 0)}")

# 7. 最终统计
print("\n=== 最终统计 ===")
stats = store.get_graph_stats()
print(f"  Chunk 节点: {stats.get('chunk_count', 0)}")
print(f"  Concept 节点: {stats.get('concept_count', 0)}")

links = store.get_concept_links(limit=10000)
print(f"  语义连接边: {len(links)}")

# 概念类型分布
concepts = store.get_concept_nodes(limit=10000)
type_dist = {}
for c in concepts:
    t = c.get('type', 'unknown')
    type_dist[t] = type_dist.get(t, 0) + 1
print(f"\n  概念类型分布: {type_dist}")

# 检查 parent_hint
from core.concept_deduper import ConceptDeduper
deduper = ConceptDeduper(SUBJECT, graph_store=store)
all_concepts = deduper.collect_all_concepts()
concepts_with_hint = [c for c in all_concepts if c.get('parent_hint', '').strip()]
print(f"\n  有 parent_hint 的概念: {len(concepts_with_hint)} / {len(all_concepts)}")
if concepts_with_hint:
    print("  示例:")
    for c in concepts_with_hint[:5]:
        print(f"    [{c.get('concept_type')}] {c.get('name')} -> hint: {c.get('parent_hint')}")

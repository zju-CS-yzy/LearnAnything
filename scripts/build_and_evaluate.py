#!/usr/bin/env python3
"""
工程分解范式知识图谱构建与评估脚本

用法: python build_and_evaluate.py [subject_id]
环境变量: DEEPSEEK_API_KEY, ZHIPU_API_KEY
"""

import sys
import os
import time
import json

sys.path.insert(0, r"D:\MyCS\AI\Project\LearnAnything")

os.environ.setdefault("DEEPSEEK_API_KEY", "sk-68bba93f2b674a5487404da932940a1f")
os.environ.setdefault("ZHIPU_API_KEY", "fc82d87430c445669e54524455d293b0.EDbHDbsyR52hrol6")

from core.graph_builder import GraphBuilder
from core.semantic_linker import SemanticLinker
from core.graph_store import GraphStore
from core.semantic_quality_evaluator import SemanticQualityEvaluator


def build_and_evaluate(subject: str):
    print(f"=== 工程分解范式知识图谱构建: {subject} ===\n")
    
    builder = GraphBuilder(f"{subject}_v1", paradigm="engineering")
    
    # 1. 语义提取
    print("[1/4] 语义提取中...")
    t0 = time.time()
    extract_result = builder.extract_all_concepts()
    t1 = time.time()
    print(f"  处理 chunk: {extract_result.get('chunks_processed', 0)}")
    print(f"  成功提取: {extract_result.get('chunks_extracted', 0)}")
    print(f"  失败: {extract_result.get('chunks_failed', 0)}")
    print(f"  平均质量分: {extract_result.get('avg_quality_score', 0)}")
    print(f"  耗时: {t1-t0:.1f}s\n")
    
    # 2. 去重
    print("[2/4] 概念去重中...")
    t0 = time.time()
    dedupe_result = builder.dedupe_concepts()
    t1 = time.time()
    print(f"  Canonical 概念: {dedupe_result.get('canonical_concepts', 0)}")
    print(f"  类型分布: {dedupe_result.get('type_distribution', {})}")
    print(f"  CSV 路径: {dedupe_result.get('csv_path', 'N/A')}")
    print(f"  耗时: {t1-t0:.1f}s\n")
    
    # 3. 全局语义连接
    print("[3/4] 全局语义连接推断中...")
    t0 = time.time()
    link_result = builder.link_concepts(paradigm="engineering")
    t1 = time.time()
    print(f"  创建连接边: {link_result.get('edges_created', 0)}")
    print(f"  parent_hint 匹配: {link_result.get('by_stage', {}).get('parent_hint_match', 0)}")
    print(f"  embedding+LLM: {link_result.get('by_stage', {}).get('embedding_llm', 0)}")
    print(f"  耗时: {t1-t0:.1f}s\n")
    
    # 4. 评估
    print("[4/4] 构建结果评估...")
    evaluate_build(subject)
    
    return {
        "extract": extract_result,
        "dedupe": dedupe_result,
        "link": link_result,
    }


def evaluate_build(subject: str):
    """评估知识图谱构建结果"""
    store = GraphStore(f"{subject}_v1")
    store.init_schema()
    
    stats = store.get_graph_stats()
    print(f"  图统计:")
    print(f"    Chunk 节点: {stats.get('chunk_count', 0)}")
    print(f"    Concept 节点: {stats.get('concept_count', 0)}")
    print(f"    BELONGS_TO 边: {stats.get('belongs_to_count', 0)}")
    print(f"    ADJACENT_TO 边: {stats.get('adjacent_to_count', 0)}")
    print(f"    SOLUTION 边: {stats.get('solution_count', 0)}")
    print(f"    DEPENDS_ON 边: {stats.get('depends_on_count', 0)}")
    
    # 概念类型分布
    concepts = store.get_concept_nodes(limit=10000)
    type_dist = {}
    for c in concepts:
        t = c.get("type", "unknown")
        type_dist[t] = type_dist.get(t, 0) + 1
    print(f"\n  概念类型分布:")
    for t, count in sorted(type_dist.items()):
        print(f"    {t}: {count}")
    
    # 连接覆盖率评估
    links = store.get_concept_links(limit=10000)
    if concepts and links:
        # 计算每个概念的平均连接数
        connected_concepts = set()
        for e in links:
            connected_concepts.add(e["source"])
            connected_concepts.add(e["target"])
        coverage = len(connected_concepts) / len(concepts) if concepts else 0
        print(f"\n  连接覆盖率:")
        print(f"    有连接的概念数: {len(connected_concepts)} / {len(concepts)}")
        print(f"    覆盖率: {coverage:.1%}")
    
    # 抽样检查：输出一些概念和连接示例
    print(f"\n  概念抽样（前10个）:")
    for c in concepts[:10]:
        print(f"    [{c.get('type', '?')}] {c.get('name', '?')}")
    
    if links:
        print(f"\n  连接抽样（前10条）:")
        for e in links[:10]:
            print(f"    {e['source'][:30]}... -> [{e['type']}] -> {e['target'][:30]}... (confidence: {e.get('confidence', 0):.2f})")


def main():
    subject = sys.argv[1] if len(sys.argv) > 1 else "generic"
    result = build_and_evaluate(subject)
    
    # 保存结果到文件
    output_path = f"D:/MyCS/AI/Project/LearnAnything/knowledge_base/{subject}_build_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
范式对比测试脚本 — 对同一 chunk 用三种范式分别提取概念，生成对比报告。

使用方式:
    cd D:\MyCS\AI\Project\LearnAnything
    python scripts/test_paradigm_comparison.py

输出:
    - 终端对比报告
    - scripts/paradigm_comparison_report.json
"""

import sys
from pathlib import Path
import json
import time

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.vector_store import VectorStore
from core.semantic_extractor import SemanticExtractor, get_paradigm_names


def get_test_chunk(subject: str = "ai_llm_v2", index: int = 3):
    """获取一个 child chunk 用于测试。"""
    store = VectorStore(subject)
    chunks = store.list_all(limit=50)
    children = [c for c in chunks if c.get("metadata", {}).get("type") == "child"]
    if not children or index >= len(children):
        raise ValueError(f"知识库 {subject} 中没有足够的 child chunk")
    return children[index]


def extract_with_paradigm(chunk_text: str, paradigm: str):
    """用指定范式提取概念，返回结果和耗时。"""
    extractor = SemanticExtractor(paradigm=paradigm)
    start = time.time()
    concepts = extractor.extract_concepts(chunk_text)
    elapsed = time.time() - start
    return concepts, elapsed


def analyze_concepts(concepts: list):
    """分析概念列表的统计特征。"""
    if not concepts:
        return {
            "count": 0,
            "types": {},
            "relations": {},
            "avg_name_length": 0,
            "avg_desc_length": 0,
        }

    types = {}
    relations = {}
    name_lengths = []
    desc_lengths = []

    for c in concepts:
        t = c.get("concept_type", "unknown")
        types[t] = types.get(t, 0) + 1

        r = c.get("relation", "UNKNOWN")
        relations[r] = relations.get(r, 0) + 1

        name = c.get("name", "")
        name_lengths.append(len(name))

        desc = c.get("description", "")
        desc_lengths.append(len(desc))

    return {
        "count": len(concepts),
        "types": types,
        "relations": relations,
        "avg_name_length": round(sum(name_lengths) / len(name_lengths), 1) if name_lengths else 0,
        "avg_desc_length": round(sum(desc_lengths) / len(desc_lengths), 1) if desc_lengths else 0,
    }


def print_divider(title: str = ""):
    """打印分隔线。"""
    width = 70
    if title:
        pad = max(1, (width - len(title) - 4) // 2)
        print("\n" + "=" * pad + f"  {title}  " + "=" * pad)
    else:
        print("\n" + "=" * width)


def print_concept_list(concepts: list, indent: int = 2):
    """打印概念列表。"""
    prefix = " " * indent
    for i, c in enumerate(concepts, 1):
        print(f"{prefix}{i}. [{c.get('relation', '?')}] {c.get('name', '?')} ({c.get('concept_type', '?')})")
        desc = c.get("description", "")
        if desc:
            print(f"{prefix}   → {desc}")


def run_comparison(subject: str = "ai_llm_v2", chunk_index: int = 3):
    """
    运行三种范式的对比测试。

    Args:
        subject: 学科名称
        chunk_index: 使用第几个 child chunk（默认第4个，跳过开头的元数据chunk）
    """
    # 获取测试 chunk
    chunk = get_test_chunk(subject, chunk_index)
    chunk_id = chunk["id"]
    chunk_text = chunk.get("text", "")

    print_divider("范式对比测试")
    print(f"\n知识库: {subject}")
    print(f"Chunk ID: {chunk_id}")
    print(f"Chunk 文本长度: {len(chunk_text)} 字符")
    print(f"Chunk 文本预览:\n{'-'*60}")
    print(chunk_text[:500] + ("..." if len(chunk_text) > 500 else ""))
    print("-" * 60)

    # 获取范式列表
    paradigms = get_paradigm_names()
    print(f"\n测试范式: {', '.join([p[1] for p in paradigms])}")

    # 分别用三种范式提取
    results = {}
    for pid, pname, pdesc in paradigms:
        print_divider(f"范式: {pname}")
        print(f"描述: {pdesc}")
        print(f"提取中...")

        try:
            concepts, elapsed = extract_with_paradigm(chunk_text, pid)
            stats = analyze_concepts(concepts)

            results[pid] = {
                "paradigm_name": pname,
                "paradigm_desc": pdesc,
                "concepts": concepts,
                "elapsed_seconds": round(elapsed, 2),
                "stats": stats,
            }

            print(f"[OK] 提取完成！耗时 {elapsed:.2f} 秒，提取 {len(concepts)} 个概念")
            print(f"\n概念分布:")
            for t, count in stats["types"].items():
                print(f"  - {t}: {count} 个")
            print(f"\n概念列表:")
            print_concept_list(concepts)

        except Exception as e:
            print(f"[FAIL] 提取失败: {e}")
            results[pid] = {
                "paradigm_name": pname,
                "error": str(e),
            }

    # 生成对比报告
    print_divider("对比分析")

    # 统计对比表
    print("\n[统计] 统计对比表:")
    print(f"{'范式':<12} {'概念数':<8} {'耗时(s)':<10} {'类型分布':<30}")
    print("-" * 70)
    for pid, r in results.items():
        if "error" in r:
            print(f"{r['paradigm_name']:<12} [FAIL] 失败: {r['error'][:40]}")
            continue
        stats = r["stats"]
        types_str = ", ".join([f"{k}:{v}" for k, v in stats["types"].items()])
        print(f"{r['paradigm_name']:<12} {stats['count']:<8} {r['elapsed_seconds']:<10} {types_str:<30}")

    # 概念重叠分析
    print("\n[分析] 概念重叠分析:")
    valid_results = {k: v for k, v in results.items() if "error" not in v}
    if len(valid_results) >= 2:
        # 提取所有概念名称
        all_names = {}
        for pid, r in valid_results.items():
            names = {c["name"].lower() for c in r["concepts"]}
            all_names[pid] = names

        # 两两交集
        pids = list(all_names.keys())
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                pi, pj = pids[i], pids[j]
                intersection = all_names[pi] & all_names[pj]
                union = all_names[pi] | all_names[pj]
                jaccard = len(intersection) / len(union) if union else 0
                print(f"  {valid_results[pi]['paradigm_name']} vs {valid_results[pj]['paradigm_name']}:")
                print(f"    重叠概念: {len(intersection)} / {len(union)} (Jaccard: {jaccard:.2f})")
                if intersection:
                    print(f"    共同概念: {', '.join(sorted(intersection)[:5])}" + ("..." if len(intersection) > 5 else ""))

    # 独有概念
    print("\n[独有] 各范式独有概念:")
    for pid, r in valid_results.items():
        other_names = set()
        for other_pid, other_r in valid_results.items():
            if other_pid != pid:
                other_names.update(c["name"].lower() for c in other_r["concepts"])
        unique = [c["name"] for c in r["concepts"] if c["name"].lower() not in other_names]
        print(f"  {r['paradigm_name']}: {len(unique)} 个")
        if unique:
            print(f"    -> {', '.join(unique[:5])}" + ("..." if len(unique) > 5 else ""))

    # 保存报告
    report_path = PROJECT_ROOT / "scripts" / "paradigm_comparison_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        # 清理不可序列化的数据后保存
        clean_results = {}
        for pid, r in results.items():
            clean_results[pid] = {
                "paradigm_name": r.get("paradigm_name", ""),
                "paradigm_desc": r.get("paradigm_desc", ""),
                "elapsed_seconds": r.get("elapsed_seconds", 0),
                "stats": r.get("stats", {}),
                "concepts": r.get("concepts", []),
            }

        report = {
            "subject": subject,
            "chunk_id": chunk_id,
            "chunk_text_preview": chunk_text[:300],
            "results": clean_results,
        }
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n[报告] 报告已保存: {report_path}")
    print_divider("测试完成")

    return results


if __name__ == "__main__":
    # 默认使用 ai_llm_v2 知识库的第4个 child chunk（跳过开头的元数据chunk）
    run_comparison(subject="ai_llm_v2", chunk_index=3)

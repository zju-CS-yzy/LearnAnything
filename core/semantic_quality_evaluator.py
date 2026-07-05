"""
语义提取质量评估器 (Semantic Quality Evaluator)

评估 LLM 对 chunk 进行概念提取的结果质量。

设计思路：
基于 NLP 领域的概念提取评估方法（参考 OpenReview 论文、Terminology Extraction 评估框架），
采用多维度自一致性评估方案，无需外部 gold standard。

评估维度：
1. 稳定性 (Stability): 同一 chunk 多次提取，概念集合重叠度
2. 覆盖度 (Coverage): 提取概念数量与文本信息密度的匹配程度
3. 忠实度 (Faithfulness): 提取概念与原文的语义一致性
4. 多样性 (Diversity): 概念类型分布的均衡性
5. 连接覆盖率 (Linkage): 相邻 chunk 概念重叠度，评估逻辑连贯性

综合质量分数 = 0.25 * 稳定性 + 0.20 * 覆盖度 + 0.20 * 忠实度 + 0.15 * 多样性 + 0.20 * 连接覆盖率

连接覆盖率（Chunk Stickiness）设计思路：
参考 ACL 论文 "MoC: Mixtures of Text Chunking Learners" 中的 Chunk Stickiness 概念。
方法：
- 构建 chunk 语义关联图：chunk 为节点，相邻 chunk 之间的概念重叠度为边权重
- 对每对相邻 chunk，计算其概念集合的 Jaccard 相似度
- 如果 Jaccard > 0.3，视为存在逻辑连接
- 连接覆盖率 = 度数 >= 2 的 chunk 数 / 总 chunk 数

使用方式：
    from core.semantic_quality_evaluator import SemanticQualityEvaluator
    evaluator = SemanticQualityEvaluator()
    score = evaluator.evaluate(chunk_text)
    
    # 评估连接覆盖率（需要 chunk 列表）
    linkage = evaluator.evaluate_linkage(chunk_list)
"""

import math
from typing import Dict, List, Any

from core.semantic_extractor import SemanticExtractor
from core.embedding import EmbeddingManager


class SemanticQualityEvaluator:
    """
    语义提取质量评估器。

    通过多维度自一致性评估，判断 LLM 对 chunk 的语义提取结果质量。
    """

    # 维度权重（含连接覆盖率）
    WEIGHTS = {
        "stability": 0.25,
        "coverage": 0.20,
        "faithfulness": 0.20,
        "diversity": 0.15,
        "linkage": 0.20,
    }

    # 多次提取的次数（稳定性评估）
    N_SAMPLES = 3

    # 连接覆盖率阈值：相邻 chunk 概念 Jaccard 相似度 > 此值视为有逻辑连接
    LINKAGE_JACCARD_THRESHOLD = 0.3

    # 连接覆盖率的最小度数要求：每个 chunk 至少需要有这么多条连接边
    MIN_DEGREE = 2

    def __init__(self):
        self.extractor = SemanticExtractor()
        self.embedding = EmbeddingManager()

    def evaluate(self, chunk_text: str) -> Dict[str, Any]:
        """
        对单个 chunk 的语义提取结果进行全面质量评估。

        Args:
            chunk_text: chunk 文本内容

        Returns:
            {
                "overall_score": float,
                "stability": float,
                "coverage": float,
                "faithfulness": float,
                "diversity": float,
                "details": { ... },
                "concepts": [ ... ],
            }
        """
        if not self.extractor.llm.available:
            return {
                "overall_score": 0.0,
                "error": "LLM 不可用，无法评估",
                "concepts": [],
            }

        # 1. 多次提取（稳定性评估）
        extraction_results = []
        for i in range(self.N_SAMPLES):
            try:
                concepts = self.extractor.extract_concepts(chunk_text)
                extraction_results.append(concepts)
            except Exception as e:
                print(f"[QualityEval] 第 {i+1} 次提取失败: {e}")
                extraction_results.append([])

        if all(len(r) == 0 for r in extraction_results):
            return {
                "overall_score": 0.0,
                "error": "全部提取失败",
                "concepts": [],
            }

        # 2. 计算各维度
        stability = self._compute_stability(extraction_results)
        best_result = self._select_best_result(extraction_results)
        coverage = self._compute_coverage(chunk_text, best_result)
        faithfulness = self._compute_faithfulness(chunk_text, best_result)
        diversity = self._compute_diversity(best_result)

        # 连接覆盖率（单 chunk 无法计算，返回 None）
        linkage = None

        # 3. 综合分数（不含连接覆盖率）
        weights = self.WEIGHTS.copy()
        if linkage is None:
            # 重新归一化权重（不含 linkage）
            total = sum(v for k, v in weights.items() if k != "linkage")
            weights = {k: v / total for k, v in weights.items() if k != "linkage"}

        overall = (
            weights["stability"] * stability
            + weights["coverage"] * coverage
            + weights["faithfulness"] * faithfulness
            + weights["diversity"] * diversity
        )

        return {
            "overall_score": round(overall, 3),
            "stability": round(stability, 3),
            "coverage": round(coverage, 3),
            "faithfulness": round(faithfulness, 3),
            "diversity": round(diversity, 3),
            "linkage": None,
            "details": {
                "extraction_count": self.N_SAMPLES,
                "successful_extractions": sum(1 for r in extraction_results if len(r) > 0),
                "concept_count": len(best_result),
                "type_distribution": self._get_type_distribution(best_result),
            },
            "concepts": best_result,
        }

    def evaluate_linkage(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        评估连接覆盖率（Chunk Stickiness）。

        方法：
        1. 提取每个 chunk 的概念
        2. 计算相邻 chunk 之间的概念 Jaccard 相似度
        3. 相似度 > 阈值的视为有逻辑连接
        4. 计算每个 chunk 的度数（连接边数）
        5. 覆盖率 = 度数 >= 2 的 chunk 数 / 总 chunk 数

        Args:
            chunks: chunk 列表，每个包含 "id" 和 "text"

        Returns:
            {
                "linkage_score": float,        # 连接覆盖率 (0-1)
                "connected_chunks": int,       # 有 >=2 条连接的 chunk 数
                "total_chunks": int,           # 总 chunk 数
                "avg_degree": float,           # 平均度数
                "edge_count": int,             # 总边数
                "chunk_degrees": {id: int},    # 每个 chunk 的度数
                "weak_links": [                 # 弱连接：相邻但无逻辑连接
                    {"chunk_a": id, "chunk_b": id, "similarity": float}
                ],
            }
        """
        if not chunks:
            return {"linkage_score": 0.0, "error": "没有 chunk"}

        # 提取每个 chunk 的概念
        chunk_concepts = {}
        for chunk in chunks:
            chunk_id = chunk.get("id", "")
            chunk_text = chunk.get("text", "")
            if not chunk_id or not chunk_text:
                continue
            try:
                concepts = self.extractor.extract_concepts(chunk_text)
                chunk_concepts[chunk_id] = set(c.get("name", "").strip().lower() for c in concepts if c.get("name", "").strip())
            except Exception as e:
                print(f"[QualityEval] 提取概念失败 {chunk_id}: {e}")
                chunk_concepts[chunk_id] = set()

        if not chunk_concepts:
            return {"linkage_score": 0.0, "error": "无法提取概念"}

        # 构建 chunk 序列（按 id 排序，假设 id 包含顺序信息）
        sorted_ids = sorted(chunk_concepts.keys())
        n = len(sorted_ids)

        # 计算相邻 chunk 的 Jaccard 相似度
        degrees = {cid: 0 for cid in sorted_ids}
        edges = 0
        weak_links = []
        strong_links = []

        for i in range(n - 1):
            cid_a = sorted_ids[i]
            cid_b = sorted_ids[i + 1]
            concepts_a = chunk_concepts[cid_a]
            concepts_b = chunk_concepts[cid_b]

            if not concepts_a or not concepts_b:
                similarity = 0.0
            else:
                intersection = len(concepts_a & concepts_b)
                union = len(concepts_a | concepts_b)
                similarity = intersection / union if union > 0 else 0.0

            if similarity >= self.LINKAGE_JACCARD_THRESHOLD:
                degrees[cid_a] += 1
                degrees[cid_b] += 1
                edges += 1
                strong_links.append({
                    "chunk_a": cid_a,
                    "chunk_b": cid_b,
                    "similarity": round(similarity, 3),
                })
            else:
                weak_links.append({
                    "chunk_a": cid_a,
                    "chunk_b": cid_b,
                    "similarity": round(similarity, 3),
                })

        # 计算覆盖率
        connected = sum(1 for d in degrees.values() if d >= self.MIN_DEGREE)
        avg_degree = sum(degrees.values()) / n if n > 0 else 0.0
        linkage_score = connected / n if n > 0 else 0.0

        return {
            "linkage_score": round(linkage_score, 3),
            "connected_chunks": connected,
            "total_chunks": n,
            "avg_degree": round(avg_degree, 2),
            "edge_count": edges,
            "chunk_degrees": degrees,
            "weak_links": weak_links[:20],  # 只返回前20个弱连接
            "strong_links": strong_links[:20],
        }

    # ========== 评估维度计算（保持不变）==========

    def _compute_stability(self, results: List[List[Dict]]) -> float:
        """稳定性：多次提取结果的 Jaccard 相似度均值。"""
        if len(results) < 2:
            return 0.0
        sets = []
        for r in results:
            names = set(c.get("name", "").strip().lower() for c in r if c.get("name", "").strip())
            if names:
                sets.append(names)
        if len(sets) < 2:
            return 0.0
        similarities = []
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                intersection = len(sets[i] & sets[j])
                union = len(sets[i] | sets[j])
                if union > 0:
                    similarities.append(intersection / union)
                else:
                    similarities.append(0.0)
        return sum(similarities) / len(similarities) if similarities else 0.0

    def _select_best_result(self, results: List[List[Dict]]) -> List[Dict]:
        """选择最佳提取结果：与其他结果重叠度最高的。"""
        if len(results) == 1:
            return results[0]
        sets = []
        for r in results:
            names = set(c.get("name", "").strip().lower() for c in r if c.get("name", "").strip())
            sets.append((names, r))
        best_idx = 0
        best_score = -1
        for i in range(len(sets)):
            scores = []
            for j in range(len(sets)):
                if i == j:
                    continue
                intersection = len(sets[i][0] & sets[j][0])
                union = len(sets[i][0] | sets[j][0])
                if union > 0:
                    scores.append(intersection / union)
            avg_score = sum(scores) / len(scores) if scores else 0.0
            if avg_score > best_score:
                best_score = avg_score
                best_idx = i
        return sets[best_idx][1]

    def _compute_coverage(self, chunk_text: str, concepts: List[Dict]) -> float:
        """覆盖度：提取概念数量与文本信息密度的匹配程度。"""
        text_len = len(chunk_text.strip())
        n_concepts = len(concepts)
        if text_len <= 500:
            expected = 3
        elif text_len <= 1500:
            expected = 5
        else:
            expected = 7
        diff = abs(n_concepts - expected)
        if diff == 0:
            return 1.0
        score = max(0.0, 1.0 - diff * 0.15)
        return score

    def _compute_faithfulness(self, chunk_text: str, concepts: List[Dict]) -> float:
        """忠实度：提取概念与原文的语义一致性。"""
        if not concepts:
            return 0.0
        concept_text = " ".join(c.get("name", "").strip() for c in concepts if c.get("name", "").strip())
        if not concept_text:
            return 0.0
        try:
            chunk_emb = self.embedding.embed([chunk_text])[0]
            concept_emb = self.embedding.embed([concept_text])[0]
            import numpy as np
            a = np.array(chunk_emb)
            b = np.array(concept_emb)
            dot = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            sim = dot / (norm_a * norm_b)
            score = max(0.0, min(1.0, (sim - 0.5) / 0.35))
            return score
        except Exception as e:
            print(f"[QualityEval] 忠实度计算失败: {e}")
            return 0.5

    def _compute_diversity(self, concepts: List[Dict]) -> float:
        """多样性：概念类型分布的均衡性。"""
        if not concepts:
            return 0.0
        type_counts = {}
        for c in concepts:
            t = c.get("concept_type", "definition")
            type_counts[t] = type_counts.get(t, 0) + 1
        total = len(concepts)
        if total == 0:
            return 0.0
        entropy = 0.0
        for count in type_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        max_entropy = 2.0
        normalized = entropy / max_entropy
        return max(0.0, min(1.0, normalized))

    def _get_type_distribution(self, concepts: List[Dict]) -> Dict[str, int]:
        """获取概念类型分布统计。"""
        dist = {}
        for c in concepts:
            t = c.get("concept_type", "definition")
            dist[t] = dist.get(t, 0) + 1
        return dist


def main():
    """CLI 测试入口"""
    test_text = """Transformer 是一种基于自注意力机制的深度学习模型架构，由 Vaswani 等人在 2017 年提出。
它彻底改变了自然语言处理领域，引入了"注意力机制"替代传统的循环神经网络（RNN）。
Transformer 的核心创新是"自注意力机制"（Self-Attention），它允许模型在处理每个词时同时关注输入序列中的所有其他词，从而捕捉长距离依赖关系。
这种架构被广泛应用于机器翻译、文本生成、BERT、GPT 等模型中。"""

    evaluator = SemanticQualityEvaluator()
    result = evaluator.evaluate(test_text)

    print("=== 语义提取质量评估 ===")
    print(f"综合分数: {result['overall_score']}")
    print(f"  稳定性: {result['stability']}")
    print(f"  覆盖度: {result['coverage']}")
    print(f"  忠实度: {result['faithfulness']}")
    print(f"  多样性: {result['diversity']}")
    print(f"  概念数: {result['details']['concept_count']}")
    print(f"  类型分布: {result['details']['type_distribution']}")


if __name__ == "__main__":
    main()

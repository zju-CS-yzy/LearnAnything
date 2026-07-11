"""
概念去重器 (Concept Deduplicator)

Phase 2 Step 2：对全局概念空间进行去重合并。

功能：
1. 收集所有 chunk 提取的概念
2. 基于 embedding 相似度合并重复概念
3. 输出去重后的全局概念表

使用方式：
    from core.concept_deduper import ConceptDeduper
    deduper = ConceptDeduper("ai_llm_v1")
    concepts = deduper.dedupe_all()  # 去重后返回概念列表
    deduper.export_table("concepts.csv")  # 导出表格

去重策略：
    1. 为每个概念名称生成智谱 embedding（复用 core/embedding.py）
    2. 计算两两余弦相似度
    3. 相似度 > 0.85 的合并为 canonical 概念
    4. 更新 KùzuDB 中所有 Concept 节点的 ID 和关系
"""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import numpy as np

from config.settings import KNOWLEDGE_BASE_DIR
from core.graph_store import GraphStore
from core.vector_store import VectorStore
from core.embedding import EmbeddingManager


class ConceptDeduper:
    """
    概念去重器。

    基于 embedding 相似度对全局概念进行去重合并。
    """

    # 相似度阈值：超过此值视为同一概念
    SIMILARITY_THRESHOLD = 0.85

    def __init__(self, collection_name: str, similarity_threshold: float = 0.85, graph_store=None):
        """
        Args:
            collection_name: 学科集合名（如 "ai_llm_v1"）
            similarity_threshold: 去重相似度阈值，默认 0.85
            graph_store: 可选的外部 GraphStore 实例（避免重复创建数据库连接）
        """
        self.collection_name = collection_name
        self.similarity_threshold = similarity_threshold
        self.graph_store = graph_store or GraphStore(collection_name)
        self.embedding = EmbeddingManager()
        self._embedding_cache: Dict[str, List[float]] = {}

    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的 embedding，带缓存。"""
        if not text:
            return [0.0] * 2048
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        emb = self.embedding.embed([text])[0]
        self._embedding_cache[text] = emb
        return emb

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算两个向量的余弦相似度。"""
        a_vec = np.array(a)
        b_vec = np.array(b)
        dot = np.dot(a_vec, b_vec)
        norm_a = np.linalg.norm(a_vec)
        norm_b = np.linalg.norm(b_vec)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def _generate_canonical_id(self, name: str) -> str:
        """为概念生成稳定的 canonical ID。"""
        if not name:
            name = "unnamed"
        name_hash = hashlib.md5(name.encode("utf-8")).hexdigest()[:10]
        return f"concept_canonical_{name_hash}"

    def collect_all_concepts(self) -> List[Dict[str, Any]]:
        """
        从 KùzuDB 收集所有已提取的概念，并补充 JSONL 中的详细信息。

        Returns:
            概念列表，每个包含 id, name, concept_type, source_chunk, relation, description, parent_hint
        """
        # 先获取所有 Concept 节点
        nodes = self.graph_store.get_extracted_concepts(limit=10000)

        # 从 JSONL 文件加载详细描述信息
        details = self.graph_store._load_concept_details()

        # 为每个 ExtractedConcept 补充 JSONL 中的详细描述
        concepts = []
        for node in nodes:
            concept_id = node.get("id", "")
            detail = details.get(concept_id, {})
            concepts.append({
                "id": concept_id,
                "name": node.get("name"),
                "concept_type": node.get("type", "definition"),
                "extract_role": node.get("extract_role", "DEFINES"),
                "source_chunk": node.get("source_chunk", ""),
                "description": detail.get("description", node.get("description", "")),
                "parent_hint": detail.get("parent_hint", node.get("parent_hint", "")),
                "media_refs": node.get("media_refs", []),
            })

        return concepts

    def dedupe_all(self) -> List[Dict[str, Any]]:
        """
        执行全局概念去重。

        流程：
        1. 收集所有概念
        2. 为每个概念名称生成 embedding
        3. 基于相似度聚类合并
        4. 更新 KùzuDB 中的概念节点和关系

        Returns:
            去重后的 canonical 概念列表
        """
        print(f"[ConceptDeduper] 开始去重: {self.collection_name}")

        # 1. 收集所有概念
        all_concepts = self.collect_all_concepts()
        if not all_concepts:
            print("[ConceptDeduper] 没有概念可去重")
            return []

        print(f"[ConceptDeduper] 收集到 {len(all_concepts)} 个概念")

        # 2. 为每个唯一概念名称生成 embedding
        unique_names = list(set(c["name"] for c in all_concepts))
        print(f"[ConceptDeduper] 唯一概念名称: {len(unique_names)}")

        name_embeddings = {}
        for name in unique_names:
            try:
                name_embeddings[name] = self._get_embedding(name)
            except Exception as e:
                print(f"[ConceptDeduper] embedding 失败 '{name}': {e}")
                name_embeddings[name] = [0.0] * 2048  # 智谱 embedding-3 维度

        # 3. 基于相似度聚类合并（简单贪婪合并）
        # 维护一个 name -> canonical_name 的映射
        canonical_map: Dict[str, str] = {}
        canonical_groups: Dict[str, List[str]] = {}  # canonical_name -> [merged_names]

        for name in unique_names:
            if name in canonical_map:
                continue  # 已经被合并了

            # 以当前名称为 canonical
            canonical_name = name
            canonical_groups[canonical_name] = [name]
            canonical_map[name] = canonical_name

            # 查找所有相似的概念
            for other_name in unique_names:
                if other_name == name or other_name in canonical_map:
                    continue
                sim = self._cosine_similarity(
                    name_embeddings[name],
                    name_embeddings[other_name]
                )
                if sim >= self.similarity_threshold:
                    canonical_map[other_name] = canonical_name
                    canonical_groups[canonical_name].append(other_name)

        print(f"[ConceptDeduper] 合并为 {len(canonical_groups)} 个 canonical 概念")

        # 4. 构建去重后的 canonical 概念列表
        canonical_concepts = []
        for canonical_name, merged_names in canonical_groups.items():
            # 统计所有来源 chunks
            source_chunks = set()
            for c in all_concepts:
                if c["name"] in merged_names:
                    source_chunks.add(c["source_chunk"])

            # 统计类型分布（取出现最多的类型）
            type_counts = defaultdict(int)
            for c in all_concepts:
                if c["name"] in merged_names:
                    type_counts[c["concept_type"]] += 1
            dominant_type = max(type_counts, key=type_counts.get) if type_counts else "definition"

            # 统计关系分布
            relation_counts = defaultdict(int)
            for c in all_concepts:
                if c["name"] in merged_names:
                    relation_counts[c.get("extract_role", "DEFINES")] += 1
            dominant_relation = max(relation_counts, key=relation_counts.get) if relation_counts else "DEFINES"

            canonical_id = self._generate_canonical_id(canonical_name)

            # 收集所有描述（取最长的一个作为 canonical description）
            all_descriptions = [c["description"] for c in all_concepts if c["name"] in merged_names and c["description"]]
            canonical_description = max(all_descriptions, key=len) if all_descriptions else ""

            # 收集 parent_hint（取最常见的非空值）
            hint_counts = defaultdict(int)
            for c in all_concepts:
                if c["name"] in merged_names and c.get("parent_hint", "").strip():
                    hint_counts[c["parent_hint"].strip()] += 1
            canonical_hint = max(hint_counts, key=hint_counts.get) if hint_counts else ""

            # 生成 canonical embedding
            canonical_embedding = self._get_embedding(canonical_name)

        # 5. 构建 canonical_concepts 列表（含 type_votes）
        canonical_concepts = []
        derived_from_map = {}  # {extracted_id: canonical_id}

        for canonical_name, merged_names in canonical_groups.items():
            # 统计所有来源 chunks 和原始概念
            source_chunks = set()
            original_concepts = []  # 属于这个 canonical group 的所有原始概念
            for c in all_concepts:
                if c["name"] in merged_names:
                    source_chunks.add(c["source_chunk"])
                    original_concepts.append(c)
                    # 建立 extracted_id -> canonical_id 映射
                    derived_from_map[c["id"]] = self._generate_canonical_id(canonical_name)

            # type_votes: 记录类型分布
            type_counts = defaultdict(int)
            for c in original_concepts:
                type_counts[c["concept_type"]] += 1

            # dominant type（投票制）
            dominant_type = max(type_counts, key=type_counts.get) if type_counts else "definition"

            canonical_id = self._generate_canonical_id(canonical_name)

            # 收集所有描述（取最长的一个作为 canonical description）
            all_descriptions = [c["description"] for c in original_concepts if c["description"]]
            canonical_description = max(all_descriptions, key=len) if all_descriptions else ""

            # 收集 parent_hint（取最常见的非空值）
            hint_counts = defaultdict(int)
            for c in original_concepts:
                if c.get("parent_hint", "").strip():
                    hint_counts[c["parent_hint"].strip()] += 1
            canonical_hint = max(hint_counts, key=hint_counts.get) if hint_counts else ""

            # LA-035: 合并 media_refs（去重）
            media_refs = []
            seen_refs = set()
            for c in original_concepts:
                for ref in c.get("media_refs", []) or []:
                    key = f"{ref.get('type', '')}:{ref.get('path', ref.get('description', '')[:50])}"
                    if key not in seen_refs:
                        seen_refs.add(key)
                        media_refs.append(ref)

            # 生成 canonical embedding
            canonical_embedding = self._get_embedding(canonical_name)

            canonical_concepts.append({
                "id": canonical_id,
                "name": canonical_name,
                "aliases": merged_names,
                "alias_count": len(merged_names),
                "concept_type": dominant_type,
                "type_votes": dict(type_counts),
                "source_chunks": list(source_chunks),
                "source_chunk_count": len(source_chunks),
                "description": canonical_description,
                "parent_hint": canonical_hint,
                "media_refs": media_refs,
                "embedding": canonical_embedding,
            })

        # 6. 写入 KùzuDB
        print(f"[ConceptDeduper] 写入 {len(canonical_concepts)} 个 CanonicalConcept 到 KùzuDB...")
        added = self.graph_store.add_canonical_concepts(
            canonical_concepts,
            derived_from_map=derived_from_map,
        )
        print(f"[ConceptDeduper] 成功写入 {added} 个 canonical 概念")

        # 7. 保存 "原始名称 → canonical ID" 映射表（供 SemanticLinker 使用）
        self._save_name_mapping(canonical_map, canonical_groups)

        return canonical_concepts

    def _save_name_mapping(self, canonical_map: Dict[str, str], canonical_groups: Dict[str, List[str]]):
        """
        保存 "原始名称 → canonical ID" 映射表。
        用于 SemanticLinker 在 parent_hint 匹配时查找 canonical 概念。
        """
        # 构建映射: 所有原始名称（包括别名）→ canonical_id
        name_to_id = {}
        for canonical_name, merged_names in canonical_groups.items():
            if not canonical_name:
                continue
            canonical_id = self._generate_canonical_id(canonical_name)
            for original_name in merged_names:
                if original_name and isinstance(original_name, str):
                    name_to_id[original_name.strip().lower()] = canonical_id
            # canonical 名称本身也加入映射
            name_to_id[canonical_name.strip().lower()] = canonical_id

        mapping_path = KNOWLEDGE_BASE_DIR / f"{self.collection_name}_name_mapping.json"
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(name_to_id, f, ensure_ascii=False, indent=2)

        print(f"[ConceptDeduper] 名称映射表已保存: {mapping_path} ({len(name_to_id)} 条映射)")

    def load_name_mapping(self) -> Dict[str, str]:
        """
        加载 "原始名称 → canonical ID" 映射表。
        """
        mapping_path = KNOWLEDGE_BASE_DIR / f"{self.collection_name}_name_mapping.json"
        if not mapping_path.exists():
            return {}

        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def export_table(self, output_path: str = None) -> str:
        """
        导出去重后的概念表。

        Args:
            output_path: 输出文件路径，默认保存到知识库目录

        Returns:
            输出文件路径
        """
        if output_path is None:
            output_path = str(KNOWLEDGE_BASE_DIR / f"{self.collection_name}_concepts.csv")

        concepts = self.dedupe_all()
        if not concepts:
            print("[ConceptDeduper] 没有概念可导出")
            return output_path

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id", "name", "aliases", "alias_count",
                "concept_type", "relation", "source_chunks", "source_chunk_count",
                "description", "parent_hint", "embedding"
            ])
            for c in concepts:
                emb = c.get("embedding", [])
                if emb is not None and len(emb) > 0:
                    if isinstance(emb, np.ndarray):
                        emb = emb.tolist()
                    emb_str = json.dumps(emb)
                else:
                    emb_str = ""
                # 过滤 aliases 和 source_chunks 中的 None
                aliases = [a for a in c.get("aliases", []) if a and isinstance(a, str)]
                source_chunks = [s for s in c.get("source_chunks", []) if s and isinstance(s, str)]
                writer.writerow([
                    c["id"],
                    c["name"],
                    ";".join(aliases),
                    c["alias_count"],
                    c["concept_type"],
                    c.get("extract_role", ""),
                    ",".join(source_chunks),
                    c["source_chunk_count"],
                    c.get("description", ""),
                    c.get("parent_hint", ""),
                    emb_str,
                ])

        print(f"[ConceptDeduper] 概念表已导出: {output_path} ({len(concepts)} 个概念)")
        return output_path

    def get_deduped_stats(self) -> Dict[str, Any]:
        """获取去重统计信息。"""
        concepts = self.dedupe_all()
        if not concepts:
            return {"status": "empty", "concepts": []}

        type_distribution = defaultdict(int)
        for c in concepts:
            type_distribution[c["concept_type"]] += 1

        return {
            "status": "success",
            "canonical_concepts": len(concepts),
            "type_distribution": dict(type_distribution),
            "concepts": concepts[:20],  # 只返回前20个用于预览
        }


def main():
    """CLI 入口"""
    import sys
    collection = sys.argv[1] if len(sys.argv) > 1 else "ai_llm_v1"
    deduper = ConceptDeduper(collection)
    deduper.export_table()


if __name__ == "__main__":
    main()

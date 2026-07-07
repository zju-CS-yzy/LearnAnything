"""
全局语义推断模块 (Semantic Linker)

Phase 2 核心模块：在去重后的概念空间中建立跨文档/跨 chunk 的语义连接。

设计原则：
1. 先提取，后推断 — 提取时不做跨文档推断，避免缺少全局信息
2. 显式标记 — 推断完成后在数据库中持久化连接边，降低后续操作成本
3. DAG 存储 — 允许多父节点，可视化层再做树形渲染

支持的范式（当前先实现工程分解）：
- engineering: requirement → technology → sub_requirement → sub_technology
  - requirement -(SOLUTION)-> technology: 需求被技术解决
  - technology -(DEPENDS_ON)-> sub_requirement: 技术实现依赖于子需求
  - sub_requirement -(SOLUTION)-> sub_technology: 子需求被子技术解决

使用方式：
    from core.semantic_linker import SemanticLinker
    linker = SemanticLinker(subject="ai_llm_v2")
    edges = linker.link_all()

输出格式：
    [
        {
            "parent_id": "concept_xxx",
            "child_id": "concept_yyy",
            "relation_type": "SOLUTION",
            "confidence": 0.92,
            "reason": "Ring AllReduce算法是为了实现多GPU并行训练而提出的具体技术方案"
        }
    ]
"""

import csv
import json
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
from core.graph_store import GraphStore
from core.llm_client import LLMClient
from config.settings import KNOWLEDGE_BASE_DIR


# ========== 范式层级配置 ==========

PARADIGM_LEVELS = {
    "engineering": {
        "levels": ["requirement", "technology", "sub_requirement", "sub_technology"],
        # 层级间允许的连接规则：(上层类型, 下层类型) -> 边类型
        "transitions": {
            ("requirement", "technology"): "SOLUTION",
            ("technology", "sub_requirement"): "DEPENDS_ON",
            ("sub_requirement", "sub_technology"): "SOLUTION",
        },
    },
    "theory": {
        "levels": ["definition", "law", "application", "extension"],
        "transitions": {},  # 暂不支持理论归纳的全局连接
    },
    "hierarchical": {
        "levels": ["fact", "concept", "method", "evaluation"],
        "transitions": {},  # 暂不支持层级归纳的全局连接
    },
}


# ========== LLM 二次确认提示词 ==========

_LINK_JUDGE_PROMPT = """你是一个知识图谱关系判断专家。

请判断以下两个概念之间是否存在"上层→下层"的语义关系。

父概念: {parent_name} (类型: {parent_type})
父概念描述: {parent_description}

子概念: {child_name} (类型: {child_type})
子概念描述: {child_description}

候选连接类型: {relation_type}
连接类型含义: {relation_meaning}

判断标准：
- 子概念是否是为了实现/解决/基于/扩展父概念而存在的？
- 父概念是否是子概念的上层需求/定义/原理/目标？
- 重点关注子概念的描述中是否明确提到与父概念的关联。

返回严格 JSON 格式，不要包含任何解释性文字：
{{"has_relation": true/false, "confidence": 0.0-1.0, "reason": "简要说明判断依据（20-40字）"}}
"""


class SemanticLinker:
    """
    全局语义推断器 — 在概念空间中建立跨 chunk 语义连接。
    """

    def __init__(
        self,
        collection_name: str,
        llm_client: Optional[LLMClient] = None,
        embedding_threshold: float = 0.72,
        llm_threshold: float = 0.80,
        graph_store=None,
    ):
        """
        Args:
            collection_name: 学科集合名（如 "ai_llm_v2"）
            llm_client: 可选的 LLMClient 实例
            embedding_threshold: embedding 相似度阈值，低于此值的候选对不送入 LLM
            llm_threshold: LLM 判断置信度阈值，低于此值不建立连接
            graph_store: 可选的外部 GraphStore 实例（避免重复创建数据库连接）
        """
        self.collection_name = collection_name
        self.graph_store = graph_store or GraphStore(collection_name)
        self.graph_store.init_schema()
        self.llm = llm_client or LLMClient()
        self.embedding_threshold = embedding_threshold
        self.llm_threshold = llm_threshold

    # ========== 核心 API ==========

    def link_all(self, paradigm: str = "engineering") -> Dict[str, Any]:
        """
        对指定范式执行全局语义连接推断。

        流程：
        1. 从数据库读取所有 canonical 概念（去重后的）
        2. 按范式层级分组
        3. 阶段1: parent_hint 精确匹配
        4. 阶段2: embedding 相似度初筛
        5. 阶段3: LLM 二次确认
        6. 写入数据库

        Args:
            paradigm: 分解范式，当前仅支持 "engineering"

        Returns:
            {"edges_created": int, "by_stage": {...}, "paradigm": str}
        """
        config = PARADIGM_LEVELS.get(paradigm)
        if not config:
            raise ValueError(f"不支持的范式: {paradigm}")

        # 1. 读取所有概念
        concepts = self._load_canonical_concepts()
        if not concepts:
            return {"edges_created": 0, "by_stage": {}, "paradigm": paradigm, "message": "无可用概念"}

        # 2. 按层级分组
        level_groups = self._group_by_level(concepts, config["levels"])

        # 3. 阶段1: parent_hint 精确匹配
        edges_stage1 = self._stage1_parent_hint_match(level_groups, config)

        # 4. 阶段2+3: embedding 初筛 + LLM 确认（排除已有连接的节点对）
        existing_pairs = {(e["parent_id"], e["child_id"]) for e in edges_stage1}
        edges_stage23 = self._stage23_embedding_then_llm(
            level_groups, config, existing_pairs
        )

        # 5. 合并并写入数据库
        all_edges = edges_stage1 + edges_stage23
        self._write_edges(all_edges)

        return {
            "edges_created": len(all_edges),
            "by_stage": {
                "parent_hint_match": len(edges_stage1),
                "embedding_llm": len(edges_stage23),
            },
            "paradigm": paradigm,
            "concept_count": len(concepts),
        }

    # ========== 阶段1: parent_hint 精确匹配 ==========

    def _stage1_parent_hint_match(
        self,
        level_groups: Dict[str, List[Dict]],
        config: Dict,
    ) -> List[Dict[str, Any]]:
        """
        基于提取时记录的 parent_hint 进行精确匹配。
        匹配策略（按优先级）：
        1. parent_hint 与 immediate upper level 的 canonical name 精确匹配
        2. parent_hint 通过名称映射表查找 canonical ID，再匹配 immediate upper level
        3. parent_hint 在所有层级中搜索（处理 LLM 层级判断不准确的情况）
        """
        edges = []
        transitions = config["transitions"]
        existing_pairs = set()  # 避免重复边

        # 加载 "原始名称 → canonical ID" 映射表
        name_mapping = self._load_name_mapping()

        # 预先构建"所有概念"的映射（用于策略3）
        all_concepts_map = {}
        all_concepts_id_map = {}
        for level_concepts in level_groups.values():
            for c in level_concepts:
                all_concepts_map[c["name"].strip().lower()] = c
                all_concepts_id_map[c["id"]] = c
                for alias in c.get("aliases", []):
                    if alias:
                        all_concepts_map[alias.strip().lower()] = c

        for (upper_type, lower_type), relation_type in transitions.items():
            parents = level_groups.get(upper_type, [])
            children = level_groups.get(lower_type, [])
            if not parents or not children:
                continue

            # 建立 immediate upper level 的映射
            parent_map = {}
            parent_id_map = {}
            for p in parents:
                parent_map[p["name"].strip().lower()] = p
                parent_id_map[p["id"]] = p
                for alias in p.get("aliases", []):
                    if alias:
                        parent_map[alias.strip().lower()] = p

            for child in children:
                hint = child.get("parent_hint", "").strip()
                if not hint:
                    continue

                hint_lower = hint.lower()
                pair_key = (hint_lower, child["id"])
                if pair_key in existing_pairs:
                    continue

                matched_parent = None
                match_reason = ""

                # 策略1: 精确匹配 immediate upper level
                matched_parent = parent_map.get(hint_lower)
                if matched_parent:
                    match_reason = f"精确匹配: '{hint}' -> '{matched_parent['name']}'"

                # 策略2: 通过名称映射表查找 canonical ID（在 immediate upper level 中）
                if not matched_parent and name_mapping:
                    canonical_id = name_mapping.get(hint_lower)
                    if canonical_id and canonical_id in parent_id_map:
                        matched_parent = parent_id_map[canonical_id]
                        match_reason = f"映射表匹配: '{hint}' -> '{matched_parent['name']}'"

                # 策略3: 在所有层级中搜索（LLM 层级判断不准确时的 fallback）
                if not matched_parent:
                    # 先在所有概念中精确匹配
                    matched_parent = all_concepts_map.get(hint_lower)
                    if matched_parent:
                        match_reason = f"全局搜索: '{hint}' -> '{matched_parent['name']}'"
                    else:
                        # 通过映射表在所有概念中查找
                        canonical_id = name_mapping.get(hint_lower)
                        if canonical_id and canonical_id in all_concepts_id_map:
                            matched_parent = all_concepts_id_map[canonical_id]
                            match_reason = f"全局映射: '{hint}' -> '{matched_parent['name']}'"

                if matched_parent:
                    # 如果匹配到的 parent 类型和期望的 upper_type 不同，调整关系类型
                    actual_relation = relation_type
                    if matched_parent.get("type") != upper_type:
                        # 跨层级连接：根据实际类型调整关系
                        actual_relation = self._determine_cross_level_relation(
                            matched_parent.get("type"), child.get("type")
                        )

                    edges.append({
                        "parent_id": matched_parent["id"],
                        "parent_name": matched_parent["name"],
                        "child_id": child["id"],
                        "child_name": child["name"],
                        "relation_type": actual_relation,
                        "confidence": 1.0,
                        "reason": match_reason,
                        "stage": "parent_hint",
                    })
                    existing_pairs.add(pair_key)

        return edges

    def _determine_cross_level_relation(self, parent_type: str, child_type: str) -> str:
        """
        根据实际类型确定跨层级连接的关系类型。
        """
        # requirement -> anything = SOLUTION
        if parent_type in ["requirement", "sub_requirement"]:
            return "SOLUTION"
        # technology -> anything = DEPENDS_ON (技术依赖于下层需求)
        if parent_type in ["technology", "sub_technology"]:
            return "DEPENDS_ON"
        return "SOLUTION"

    def _load_name_mapping(self) -> Dict[str, str]:
        """
        加载 "原始名称 → canonical ID" 映射表。
        由 ConceptDeduper 在去重后生成。
        """
        mapping_path = KNOWLEDGE_BASE_DIR / f"{self.collection_name}_name_mapping.json"
        if not mapping_path.exists():
            return {}

        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[SemanticLinker] 加载名称映射表失败: {e}")
            return {}

    # ========== 阶段2+3: embedding 初筛 + LLM 确认 ==========

    def _stage23_embedding_then_llm(
        self,
        level_groups: Dict[str, List[Dict]],
        config: Dict,
        existing_pairs: set,
    ) -> List[Dict[str, Any]]:
        """
        对没有 parent_hint 匹配的概念对，进行 embedding 相似度初筛 + LLM 二次确认。
        """
        edges = []
        transitions = config["transitions"]

        for (upper_type, lower_type), relation_type in transitions.items():
            parents = level_groups.get(upper_type, [])
            children = level_groups.get(lower_type, [])
            if not parents or not children:
                continue

            relation_meaning = {
                "SOLUTION": "子概念是父概念的解决方案/实现手段",
                "DEPENDS_ON": "父概念的实现依赖于子概念所描述的需求/约束",
            }.get(relation_type, "上层概念与下层概念存在语义关联")

            # 阶段2: embedding 初筛
            candidate_pairs = []
            for parent in parents:
                for child in children:
                    pair_key = (parent["id"], child["id"])
                    if pair_key in existing_pairs:
                        continue

                    sim = self._compute_similarity(parent, child)
                    if sim >= self.embedding_threshold:
                        candidate_pairs.append((parent, child, sim))

            if not candidate_pairs:
                continue

            # 按相似度排序，优先处理相似度高的对
            candidate_pairs.sort(key=lambda x: x[2], reverse=True)

            # 阶段3: LLM 二次确认
            for parent, child, sim in candidate_pairs:
                pair_key = (parent["id"], child["id"])
                if pair_key in existing_pairs:
                    continue

                result = self._llm_judge(
                    parent, child, relation_type, relation_meaning
                )

                if result.get("has_relation") and result.get("confidence", 0) >= self.llm_threshold:
                    edges.append({
                        "parent_id": parent["id"],
                        "parent_name": parent["name"],
                        "child_id": child["id"],
                        "child_name": child["name"],
                        "relation_type": relation_type,
                        "confidence": result.get("confidence", 0.0),
                        "reason": result.get("reason", ""),
                        "stage": "embedding_llm",
                    })
                    existing_pairs.add(pair_key)

        return edges

    # ========== LLM 判断 ==========

    def _llm_judge(
        self,
        parent: Dict[str, Any],
        child: Dict[str, Any],
        relation_type: str,
        relation_meaning: str,
    ) -> Dict[str, Any]:
        """
        使用 LLM 判断两个概念之间是否存在语义连接。
        """
        if not self.llm.available:
            return {"has_relation": False, "confidence": 0.0, "reason": "LLM不可用"}

        prompt = _LINK_JUDGE_PROMPT.format(
            parent_name=parent["name"],
            parent_type=parent["type"],
            parent_description=parent.get("description", ""),
            child_name=child["name"],
            child_type=child["type"],
            child_description=child.get("description", ""),
            relation_type=relation_type,
            relation_meaning=relation_meaning,
        )

        try:
            result = self.llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )
            if isinstance(result, dict):
                return result
            return {"has_relation": False, "confidence": 0.0, "reason": "解析失败"}
        except Exception as e:
            print(f"[SemanticLinker] LLM 判断失败: {e}")
            return {"has_relation": False, "confidence": 0.0, "reason": str(e)}

    # ========== 相似度计算 ==========

    def _compute_similarity(self, parent: Dict, child: Dict) -> float:
        """
        计算两个概念的 embedding 相似度。

        策略：比较 parent 的 name+description 与 child 的 name+description+parent_hint。
        使用 cosine 相似度。
        """
        parent_emb = parent.get("embedding")
        child_emb = child.get("embedding")

        if parent_emb is None or child_emb is None:
            return 0.0

        try:
            parent_vec = np.array(parent_emb, dtype=np.float32)
            child_vec = np.array(child_emb, dtype=np.float32)

            # 归一化
            parent_norm = np.linalg.norm(parent_vec)
            child_norm = np.linalg.norm(child_vec)

            if parent_norm == 0 or child_norm == 0:
                return 0.0

            cosine_sim = np.dot(parent_vec, child_vec) / (parent_norm * child_norm)
            return float(cosine_sim)
        except Exception as e:
            print(f"[SemanticLinker] 相似度计算失败: {e}")
            return 0.0

    # ========== 数据加载与分组 ==========

    def _load_canonical_concepts(self) -> List[Dict[str, Any]]:
        """
        加载所有 canonical 概念。
        优先从 KùzuDB 读取，fallback 到 CSV。

        返回的概念包含:
        - id: canonical 概念 ID
        - name: 概念名称
        - type: 概念类型
        - description: 描述
        - aliases: 别名列表
        - embedding: embedding 向量（实时计算）
        - parent_hint: parent_hint
        - source_chunks: 来源 chunk ID 列表
        """
        # 1. 优先从 KùzuDB 读取
        db_concepts = self._load_from_kuzudb()
        if db_concepts:
            return db_concepts

        # 2. Fallback: 从 CSV 读取（兼容旧数据）
        csv_concepts = self._load_from_csv()

        merged = []
        for concept_id, csv_info in csv_concepts.items():
            merged.append({
                "id": concept_id,
                "name": csv_info.get("name", ""),
                "type": csv_info.get("concept_type", ""),
                "description": csv_info.get("description", ""),
                "aliases": csv_info.get("aliases", []),
                "embedding": csv_info.get("embedding", None),
                "parent_hint": csv_info.get("parent_hint", ""),
                "source_chunks": csv_info.get("source_chunks", []),
            })

        return merged

    def _load_from_kuzudb(self) -> List[Dict[str, Any]]:
        """
        从 KùzuDB 读取 CanonicalConcept 节点。
        embedding 需要实时计算（不在 KùzuDB 中存储）。
        """
        try:
            nodes = self.graph_store.get_canonical_concepts(limit=10000)
            if not nodes:
                return []

            # 为每个 canonical 概念计算 embedding
            result = []
            for node in nodes:
                name = node.get("name", "")
                if not name:
                    continue

                # 实时计算 embedding
                try:
                    emb = self._get_embedding(name)
                except Exception:
                    emb = None

                # 解析 source_chunks（JSON 字符串）
                source_chunks_raw = node.get("source_chunks", "[]")
                try:
                    source_chunks = json.loads(source_chunks_raw) if isinstance(source_chunks_raw, str) else source_chunks_raw
                except json.JSONDecodeError:
                    source_chunks = []

                result.append({
                    "id": node.get("id", ""),
                    "name": name,
                    "type": node.get("type", ""),
                    "description": node.get("description", ""),
                    "aliases": [],  # KùzuDB 中的 aliases 也是 JSON，需要解析
                    "embedding": emb,
                    "parent_hint": node.get("parent_hint", ""),
                    "source_chunks": source_chunks,
                })

            return result
        except Exception as e:
            print(f"[SemanticLinker] 从 KùzuDB 读取 canonical 概念失败: {e}")
            return []

    def _load_from_csv(self) -> Dict[str, Dict]:
        """
        从去重后的 CSV 文件读取概念完整信息。

        CSV 文件路径: knowledge_base/{subject}_concepts.csv
        """
        csv_path = KNOWLEDGE_BASE_DIR / f"{self.collection_name}_concepts.csv"
        if not csv_path.exists():
            return {}

        result = {}
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    concept_id = row.get("id", "").strip()
                    if not concept_id:
                        continue

                    # 解析 embedding（JSON 数组字符串）
                    embedding = None
                    emb_str = row.get("embedding", "")
                    if emb_str:
                        try:
                            embedding = json.loads(emb_str)
                        except json.JSONDecodeError:
                            pass

                    # 解析 aliases（分号分隔）
                    aliases = []
                    alias_str = row.get("aliases", "")
                    if alias_str:
                        aliases = [a.strip() for a in alias_str.split(";") if a.strip()]

                    # 解析 source_chunks（逗号分隔）
                    chunks = []
                    chunk_str = row.get("source_chunks", "")
                    if chunk_str:
                        chunks = [c.strip() for c in chunk_str.split(",") if c.strip()]

                    result[concept_id] = {
                        "name": row.get("name", ""),
                        "concept_type": row.get("concept_type", ""),
                        "description": row.get("description", ""),
                        "aliases": aliases,
                        "embedding": embedding,
                        "parent_hint": row.get("parent_hint", ""),
                        "source_chunks": chunks,
                    }
        except Exception as e:
            print(f"[SemanticLinker] 读取 CSV 失败: {e}")

        return result

    def _group_by_level(
        self,
        concepts: List[Dict],
        level_types: List[str],
    ) -> Dict[str, List[Dict]]:
        """
        按概念类型分组。
        """
        groups = {t: [] for t in level_types}
        for c in concepts:
            ct = c.get("type", "").lower()
            if ct in groups:
                groups[ct].append(c)
        return groups

    # ========== 数据库写入 ==========

    def _write_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        将语义连接边写入 KùzuDB。
        如果 canonical 概念节点不存在，则先创建。
        """
        conn = self.graph_store._ensure_db()
        written = 0
        esc = self.graph_store._escape_cypher_string

        for edge in edges:
            # 先确保两端节点存在（MERGE canonical 概念节点）
            for node_id, node_name in [(edge['parent_id'], edge.get('parent_name', '')),
                                        (edge['child_id'], edge.get('child_name', ''))]:
                safe_id = esc(node_id)
                safe_name = esc(node_name)
                merge_node_cypher = f"""
                    MERGE (c:Concept {{
                        concept_id: '{safe_id}'
                    }})
                    ON CREATE SET c.name = '{safe_name}'
                """
                try:
                    conn.execute(merge_node_cypher)
                except Exception as e:
                    print(f"[SemanticLinker] 创建节点失败 {node_id}: {e}")

            # 创建关系
            safe_parent_id = esc(edge['parent_id'])
            safe_child_id = esc(edge['child_id'])
            safe_relation = esc(edge['relation_type'])
            confidence = float(edge.get('confidence', 0.0))
            cypher = f"""
                MATCH (p:Concept {{concept_id: '{safe_parent_id}'}}),
                      (c:Concept {{concept_id: '{safe_child_id}'}})
                CREATE (p)-[:{safe_relation} {{confidence: {confidence}}}]->(c)
            """
            try:
                conn.execute(cypher)
                written += 1
            except Exception as e:
                print(f"[SemanticLinker] 写入边失败: {e}")

        print(f"[SemanticLinker] 写入 {written} 条语义连接边")
        return written


# ========== CLI 测试入口 ==========

def main():
    import sys

    subject = sys.argv[1] if len(sys.argv) > 1 else "ai_llm_v2"
    print(f"=== SemanticLinker: {subject} ===")

    linker = SemanticLinker(subject)
    result = linker.link_all(paradigm="engineering")

    print(f"\n结果:")
    print(f"  创建边数: {result['edges_created']}")
    print(f"  parent_hint 匹配: {result['by_stage']['parent_hint_match']}")
    print(f"  embedding+LLM: {result['by_stage']['embedding_llm']}")
    print(f"  概念总数: {result['concept_count']}")


if __name__ == "__main__":
    main()

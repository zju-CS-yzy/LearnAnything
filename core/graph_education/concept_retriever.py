"""
LA-040-P0: Concept Retriever（概念检索器）

将用户查询/出题需求映射到知识图谱中的 CanonicalConcept 节点
"""

import math
import re
from typing import Dict, List, Optional, Any

from core.graph_education.types import ConceptNode, UserKnowledgeState
from core.graph_store import GraphStore


class ConceptRetriever:
    """
    概念检索器：将用户查询/出题需求映射到 CanonicalConcept 节点

    支持三种检索策略：
    1. 名称精确/模糊匹配
    2. 别名匹配
    3. Embedding 语义检索（回退）
    """

    def __init__(
        self,
        graph_store: GraphStore,
        vector_store=None,
        cache: Optional[Dict] = None
    ):
        self.graph_store = graph_store
        self.vector_store = vector_store
        self.cache = cache or {}
        self._subject_id = graph_store.collection_name

    # ───────────────────────────────────────────────
    # 核心接口
    # ───────────────────────────────────────────────

    def resolve(
        self,
        concept_names: List[str],
        subject_id: Optional[str] = None
    ) -> List[ConceptNode]:
        """
        将概念名称列表解析为 CanonicalConcept 节点

        策略：名称精确匹配 → 模糊匹配 → 别名匹配 → Embedding 语义检索

        Args:
            concept_names: 概念名称列表（如 ["注意力机制", "Transformer"]）
            subject_id: 学科 ID（可选，默认使用 GraphStore 的 collection_name）

        Returns:
            List[ConceptNode]: 匹配的概念节点列表（去重）

        Raises:
            ValueError: 当所有概念都无法解析时
        """
        if not concept_names:
            return []

        resolved = []
        not_found = []

        for name in concept_names:
            name = name.strip()
            if not name:
                continue

            # 策略 1: 精确匹配
            node = self._match_exact(name)
            if node:
                resolved.append(node)
                continue

            # 策略 2: 模糊匹配（包含关系）
            nodes = self._match_fuzzy(name)
            if nodes:
                resolved.append(nodes[0])  # 取最匹配的
                continue

            # 策略 3: 别名匹配
            node = self._match_alias(name)
            if node:
                resolved.append(node)
                continue

            not_found.append(name)

        # 回退：对未找到的概念尝试 Embedding 语义检索
        if not_found and self.vector_store:
            for name in not_found:
                node = self._search_by_embedding(name)
                if node:
                    resolved.append(node)

        # 去重（按 canonical_id）
        seen = set()
        unique = []
        for n in resolved:
            if n.canonical_id not in seen:
                seen.add(n.canonical_id)
                unique.append(n)

        # 兜底策略：如果所有匹配都失败，返回图谱中 PageRank 最高的前 5 个概念
        # 这样即使主题不匹配，P0 流程仍然可以工作（基于图谱全局概念出题）
        if not unique and concept_names:
            print(f"[ConceptRetriever] 主题 '{concept_names}' 未匹配到任何概念，使用图谱 Top-5 兜底")
            all_concepts = self._get_all_concepts()
            all_concepts.sort(key=lambda x: x.pagerank_score, reverse=True)
            unique = all_concepts[:5]

        return unique

    def expand(
        self,
        seed_concepts: List[ConceptNode],
        hop: int = 1,
        edge_types: Optional[List[str]] = None,
        max_nodes: int = 20
    ) -> List[ConceptNode]:
        """
        从种子概念沿图扩展，获取相关概念

        Args:
            seed_concepts: 种子概念列表
            hop: 扩展深度（1-hop 或 2-hop）
            edge_types: 限制的边类型（如 ["SOLUTION", "DEPENDS_ON"]）
            max_nodes: 最大返回节点数（包含种子）

        Returns:
            List[ConceptNode]: 扩展后的概念节点列表（包含种子）
        """
        if not seed_concepts:
            raise ValueError("LA-0403001: 种子概念为空，无法构建子图")

        if hop < 1:
            return list(seed_concepts)

        # 收集所有节点 ID（避免重复查询）
        all_ids = set()
        for sc in seed_concepts:
            all_ids.add(sc.canonical_id)

        current_frontier = [sc.canonical_id for sc in seed_concepts]

        for h in range(hop):
            if not current_frontier:
                break

            # 查询当前 frontier 的邻居
            frontier_str = ", ".join([f"'{cid}'" for cid in current_frontier])

            # 构建 Cypher 查询，边类型过滤在 MATCH 模式中指定
            if edge_types and len(edge_types) > 0:
                # KùzuDB 支持在 MATCH 中指定关系类型：-[r:SOLUTION|DEPENDS_ON]-
                rel_types = "|".join(edge_types)
                cypher = f"""
                    MATCH (c:CanonicalConcept)-[r:{rel_types}]-(n:CanonicalConcept)
                    WHERE c.canonical_id IN [{frontier_str}]
                    RETURN DISTINCT n.canonical_id, n.name, n.concept_type,
                           n.description, n.parent_hint, n.aliases
                    LIMIT {max_nodes * 2}
                """
            else:
                cypher = f"""
                    MATCH (c:CanonicalConcept)-[r]-(n:CanonicalConcept)
                    WHERE c.canonical_id IN [{frontier_str}]
                    RETURN DISTINCT n.canonical_id, n.name, n.concept_type,
                           n.description, n.parent_hint, n.aliases
                    LIMIT {max_nodes * 2}
                """

            conn = self.graph_store._ensure_db()
            result = self.graph_store._execute(conn, cypher)

            new_frontier = []
            while result.has_next():
                row = result.get_next()
                cid = row[0]
                if cid not in all_ids and len(all_ids) < max_nodes:
                    all_ids.add(cid)
                    new_frontier.append(cid)

            current_frontier = new_frontier
            if len(all_ids) >= max_nodes:
                break

        # 批量加载所有收集到的节点
        return self._load_nodes_by_ids(list(all_ids))

    def select_weak_concepts(
        self,
        user_id: str,
        subject_id: str,
        n: int = 5
    ) -> List[ConceptNode]:
        """
        选择用户掌握度最低的 n 个概念（用于靶向出题）

        策略：
        1. 有历史数据 → 选择 mastery_level 最低的
        2. 无历史数据 → 选择 PageRank 最低的（边缘概念通常更难）

        Args:
            user_id: 用户 ID
            subject_id: 学科 ID
            n: 返回概念数量

        Returns:
            List[ConceptNode]: 薄弱概念列表
        """
        # 先检查用户是否有历史数据
        has_history = self._check_user_history(user_id, subject_id)

        if has_history:
            # 从用户状态表查询 mastery_level 最低的概念
            return self._select_weak_from_history(user_id, subject_id, n)
        else:
            # 无历史数据，从全图选 PageRank 最低的
            return self._select_weak_from_graph(n)

    def select_by_coverage(
        self,
        subject_id: str,
        existing_questions: Optional[List] = None,
        n: int = 5
    ) -> List[ConceptNode]:
        """
        选择覆盖度最低的 n 个概念（用于全面检测）

        策略：选择历史上被考察次数最少的概念

        Args:
            subject_id: 学科 ID
            existing_questions: 已有题目列表（用于计算已覆盖概念）
            n: 返回概念数量

        Returns:
            List[ConceptNode]: 未充分覆盖的概念列表
        """
        # 获取所有概念
        all_concepts = self._get_all_concepts()

        # 统计已覆盖概念
        covered = set()
        if existing_questions:
            for q in existing_questions:
                # 假设 question 有 primary_concepts 属性
                pcs = getattr(q, 'primary_concepts', []) or getattr(q, 'knowledge_trace', {}).get('primary_concepts', [])
                covered.update(pcs)

        # 过滤未覆盖的，按 PageRank 排序（优先核心概念）
        uncovered = [c for c in all_concepts if c.canonical_id not in covered]
        uncovered.sort(key=lambda x: x.pagerank_score, reverse=True)

        return uncovered[:n]

    # ───────────────────────────────────────────────
    # 辅助接口
    # ───────────────────────────────────────────────

    def get_concept_stats(self, canonical_id: str) -> Dict[str, Any]:
        """
        获取概念统计信息

        Returns:
            Dict: {
                'in_degree': int,
                'out_degree': int,
                'pagerank_score': float,
                'neighbor_count': int
            }
        """
        conn = self.graph_store._ensure_db()

        # 查询度数
        in_cypher = f"""
            MATCH (c:CanonicalConcept {{canonical_id: '{canonical_id}'}})<-[:SOLUTION|:DEPENDS_ON|:HAS_DETAIL]-(n)
            RETURN count(n) as in_degree
        """
        out_cypher = f"""
            MATCH (c:CanonicalConcept {{canonical_id: '{canonical_id}'}})-[:SOLUTION|:DEPENDS_ON|:HAS_DETAIL]->(n)
            RETURN count(n) as out_degree
        """

        try:
            in_result = self.graph_store._execute(conn, in_cypher)
            in_degree = in_result.get_next()[0] if in_result.has_next() else 0
        except:
            in_degree = 0

        try:
            out_result = self.graph_store._execute(conn, out_cypher)
            out_degree = out_result.get_next()[0] if out_result.has_next() else 0
        except:
            out_degree = 0

        return {
            'in_degree': in_degree,
            'out_degree': out_degree,
            'pagerank_score': 0.0,  # 需要从缓存读取
            'neighbor_count': in_degree + out_degree
        }

    def search_by_embedding(self, query: str, top_k: int = 5) -> List[ConceptNode]:
        """
        Embedding 语义检索

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            List[ConceptNode]: 语义相似的概念
        """
        if not self.vector_store:
            return []

        # 使用 vector_store 查询
        results = self.vector_store.query(query, n_results=top_k)

        nodes = []
        for doc in results:
            # 尝试从 metadata 中获取 canonical_id
            metadata = doc.get('metadata', {})
            canonical_id = metadata.get('canonical_id')
            if canonical_id:
                node = self._load_node_by_id(canonical_id)
                if node:
                    node.similarity_score = doc.get('score', 0.0)
                    nodes.append(node)

        return nodes

    # ───────────────────────────────────────────────
    # 内部方法
    # ───────────────────────────────────────────────

    def _match_exact(self, name: str) -> Optional[ConceptNode]:
        """精确匹配名称"""
        conn = self.graph_store._ensure_db()
        safe_name = name.replace("'", "\\'")

        cypher = f"""
            MATCH (c:CanonicalConcept {{name: '{safe_name}'}})
            RETURN c.canonical_id, c.name, c.concept_type, c.description,
                   c.parent_hint, c.aliases, c.source_chunks
            LIMIT 1
        """

        try:
            result = self.graph_store._execute(conn, cypher)
            if result.has_next():
                row = result.get_next()
                return self._row_to_node(row)
        except Exception as e:
            # 可能是旧 schema，回退到基本查询
            pass

        return None

    def _match_fuzzy(self, name: str) -> List[ConceptNode]:
        """
        模糊匹配：双向包含关系。

        匹配规则：概念名包含查询词，或查询词包含概念名。
        例如：查询 "RAG 技术" 会匹配概念名 "RAG"；查询 "RAG" 也会匹配概念名 "RAG 技术"。
        """
        conn = self.graph_store._ensure_db()
        safe_name = name.replace("'", "\\'")

        cypher = f"""
            MATCH (c:CanonicalConcept)
            WHERE c.name CONTAINS '{safe_name}' OR '{safe_name}' CONTAINS c.name
            RETURN c.canonical_id, c.name, c.concept_type, c.description,
                   c.parent_hint, c.aliases, c.source_chunks
            LIMIT 10
        """

        try:
            result = self.graph_store._execute(conn, cypher)
            nodes = []
            while result.has_next():
                row = result.get_next()
                nodes.append(self._row_to_node(row))
            return nodes
        except Exception as e:
            return []

    def _match_alias(self, name: str) -> Optional[ConceptNode]:
        """别名匹配：aliases 字段包含"""
        conn = self.graph_store._ensure_db()
        safe_name = name.replace("'", "\\'")

        cypher = f"""
            MATCH (c:CanonicalConcept)
            WHERE c.aliases CONTAINS '{safe_name}'
            RETURN c.canonical_id, c.name, c.concept_type, c.description,
                   c.parent_hint, c.aliases, c.source_chunks
            LIMIT 1
        """

        try:
            result = self.graph_store._execute(conn, cypher)
            if result.has_next():
                row = result.get_next()
                return self._row_to_node(row)
        except Exception as e:
            return None

        return None

    def _search_by_embedding(self, name: str) -> Optional[ConceptNode]:
        """Embedding 回退搜索"""
        nodes = self.search_by_embedding(name, top_k=3)
        if nodes and nodes[0].similarity_score and nodes[0].similarity_score > 0.6:
            return nodes[0]
        return None

    def _load_node_by_id(self, canonical_id: str) -> Optional[ConceptNode]:
        """通过 ID 加载单个节点"""
        nodes = self._load_nodes_by_ids([canonical_id])
        return nodes[0] if nodes else None

    def _load_nodes_by_ids(self, ids: List[str]) -> List[ConceptNode]:
        """批量加载节点"""
        if not ids:
            return []

        conn = self.graph_store._ensure_db()
        id_str = ", ".join([f"'{cid}'" for cid in ids])

        cypher = f"""
            MATCH (c:CanonicalConcept)
            WHERE c.canonical_id IN [{id_str}]
            RETURN c.canonical_id, c.name, c.concept_type, c.description,
                   c.parent_hint, c.aliases, c.source_chunks
        """

        nodes = []
        try:
            result = self.graph_store._execute(conn, cypher)
            while result.has_next():
                row = result.get_next()
                nodes.append(self._row_to_node(row))
        except Exception as e:
            # 兼容旧 schema
            try:
                cypher = f"""
                    MATCH (c:CanonicalConcept)
                    WHERE c.canonical_id IN [{id_str}]
                    RETURN c.canonical_id, c.name, c.concept_type, c.description,
                           c.parent_hint
                """
                result = self.graph_store._execute(conn, cypher)
                while result.has_next():
                    row = result.get_next()
                    nodes.append(self._row_to_node(row))
            except:
                pass

        return nodes

    def _row_to_node(self, row) -> ConceptNode:
        """将查询结果行转换为 ConceptNode"""
        # row 可能为不同长度，需要安全处理
        length = len(row)

        canonical_id = row[0] or ""
        name = row[1] or ""
        concept_type = row[2] or "concept"
        description = row[3] or ""
        parent_hint = row[4] if length > 4 else ""

        aliases = []
        if length > 5 and row[5]:
            try:
                import json
                aliases_val = row[5]
                if isinstance(aliases_val, str) and aliases_val.strip():
                    aliases = json.loads(aliases_val)
            except:
                aliases = []

        source_chunks = ""
        if length > 6 and row[6]:
            source_chunks = row[6]

        return ConceptNode(
            canonical_id=canonical_id,
            name=name,
            concept_type=concept_type,
            description=description,
            aliases=aliases,
            parent_hint=parent_hint,
            source_chunks=source_chunks
        )

    def _check_user_history(self, user_id: str, subject_id: str) -> bool:
        """检查用户是否有答题历史"""
        # 简化实现：检查 KùzuDB 中是否有 UserKnowledgeState 节点
        # P0 阶段使用 SQLite 实现，这里返回 False 作为默认值
        return False

    def _select_weak_from_history(
        self, user_id: str, subject_id: str, n: int
    ) -> List[ConceptNode]:
        """从历史记录中选择薄弱概念"""
        # P0 阶段：从 KùzuDB 查询 UserKnowledgeState
        # 简化实现：返回全图概念
        return self._select_weak_from_graph(n)

    def _select_weak_from_graph(self, n: int) -> List[ConceptNode]:
        """从全图选择 PageRank 最低的 n 个概念"""
        all_concepts = self._get_all_concepts()

        # 按 PageRank 排序（升序，边缘概念在前）
        all_concepts.sort(key=lambda x: x.pagerank_score)

        return all_concepts[:n]

    def _get_all_concepts(self) -> List[ConceptNode]:
        """获取所有 CanonicalConcept"""
        conn = self.graph_store._ensure_db()

        cypher = """
            MATCH (c:CanonicalConcept)
            RETURN c.canonical_id, c.name, c.concept_type, c.description,
                   c.parent_hint, c.aliases, c.source_chunks
            LIMIT 1000
        """

        nodes = []
        try:
            result = self.graph_store._execute(conn, cypher)
            while result.has_next():
                row = result.get_next()
                nodes.append(self._row_to_node(row))
        except Exception as e:
            # 兼容旧 schema
            try:
                cypher = """
                    MATCH (c:CanonicalConcept)
                    RETURN c.canonical_id, c.name, c.concept_type, c.description, c.parent_hint
                    LIMIT 1000
                """
                result = self.graph_store._execute(conn, cypher)
                while result.has_next():
                    row = result.get_next()
                    nodes.append(self._row_to_node(row))
            except:
                pass

        return nodes

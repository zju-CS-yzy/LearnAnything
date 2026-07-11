"""
语义聚合器 (SemanticAggregator)
LA-035 Phase 2.3: 基于 MarkdownChunker v2.0 树形结构，将 HeadingChunk 下的 ParagraphChunk 概念聚合为主题概念 + 层级关系。

核心流程:
    1. 构建 chunk 树形索引（heading -> paragraphs）
    2. 从 GraphStore 获取 DERIVED_FROM 映射（extracted -> canonical）
    3. 建立 chunk_id -> [canonical_id] 映射
    4. 对每个 HeadingChunk:
       a. 收集所有子 ParagraphChunk 的 canonical concepts
       b. 从 heading_path 提取候选主题名称
       c. 在 canonical concepts 中匹配主题概念（精确/子串/缩写）
       d. 建立 HAS_DETAIL 关系（主题 -> 细节）
    5. 写入 GraphStore

使用方式:
    from core.semantic_aggregator import SemanticAggregator
    aggregator = SemanticAggregator("ai_llm_v2")
    result = aggregator.aggregate(chunks)
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.graph_store import GraphStore


class SemanticAggregator:
    """
    语义聚合器。
    
    基于 MarkdownChunker v2.0 的树形分块结构，建立概念间的层级关系。
    """

    # 匹配策略配置
    THEME_MATCH_STRATEGIES = ["exact", "substring", "abbreviation"]

    def __init__(self, collection_name: str, graph_store: Optional[GraphStore] = None):
        """
        Args:
            collection_name: 学科集合名
            graph_store: 可选的 GraphStore 实例
        """
        self.collection_name = collection_name
        self.graph_store = graph_store or GraphStore(collection_name)

    def aggregate(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        执行语义聚合。
        
        Args:
            chunks: MarkdownChunker 输出的 chunk 列表（含 heading + paragraph）
        
        Returns:
            {
                "status": "success",
                "heading_count": int,
                "theme_concepts": List[str],
                "has_detail_edges": int,
                "details": List[Dict],
            }
        """
        print(f"[SemanticAggregator] 开始语义聚合: {self.collection_name}")

        # Step 1: 构建 chunk 树形索引
        heading_ids, para_to_heading = self._build_chunk_tree(chunks)
        print(f"[SemanticAggregator] 识别到 {len(heading_ids)} 个 HeadingChunk")

        # Step 2: 获取 DERIVED_FROM 映射（extracted -> canonical）
        derived_map = self._get_derived_from_map()
        print(f"[SemanticAggregator] DERIVED_FROM 映射: {len(derived_map)} 条")

        # Step 3: 建立 chunk_id -> [canonical_name] 映射
        chunk_to_canonicals = self._build_chunk_to_canonicals(derived_map)
        print(f"[SemanticAggregator] 涉及 {len(chunk_to_canonicals)} 个 chunk")

        # Step 4: 对每个 HeadingChunk 建立 HAS_DETAIL 关系
        all_relations = []
        theme_concepts = []
        detail_stats = []

        for heading_id in heading_ids:
            heading = next((c for c in chunks if c["id"] == heading_id), None)
            if not heading:
                continue

            # 收集该 HeadingChunk 下所有 paragraph 的 canonical concepts
            child_concepts = self._collect_child_concepts(
                heading_id, chunks, para_to_heading, chunk_to_canonicals
            )
            if not child_concepts:
                continue

            # 提取候选主题名称
            heading_path = heading.get("metadata", {}).get("heading_path", "")
            candidate_themes = self._extract_theme_candidates(heading_path)

            # 匹配主题概念
            theme_ids = self._match_theme_concepts(
                candidate_themes, child_concepts
            )

            if not theme_ids:
                # 未匹配到主题，尝试使用 heading 本身提取的概念作为主题
                theme_ids = self._get_heading_self_concepts(
                    heading_id, chunk_to_canonicals
                )

            if theme_ids:
                theme_concepts.extend(theme_ids)
                # 建立 HAS_DETAIL 关系
                relations = self._create_has_detail_relations(
                    theme_ids, child_concepts
                )
                all_relations.extend(relations)
                detail_stats.append({
                    "heading": heading_path[:50],
                    "themes": len(theme_ids),
                    "details": len(child_concepts),
                    "relations": len(relations),
                })

        # Step 5: 写入 GraphStore
        if all_relations:
            created = self.graph_store.add_has_detail_relations(all_relations)
        else:
            created = 0

        print(f"[SemanticAggregator] 聚合完成: {len(theme_concepts)} 个主题, {created} 条 HAS_DETAIL 关系")

        return {
            "status": "success",
            "heading_count": len(heading_ids),
            "theme_concepts": list(set(theme_ids for t in theme_concepts for theme_ids in [t])),
            "has_detail_edges": created,
            "details": detail_stats,
        }

    # ========== Step 1: 构建 chunk 树形索引 ==========

    def _build_chunk_tree(
        self, chunks: List[Dict[str, Any]]
    ) -> Tuple[List[str], Dict[str, str]]:
        """
        构建 chunk 树形索引。
        
        Returns:
            (heading_ids, para_to_heading)
            heading_ids: HeadingChunk ID 列表
            para_to_heading: {paragraph_id: heading_id}
        """
        heading_ids = []
        para_to_heading = {}

        # 先收集所有 heading chunks
        headings = {}
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            if meta.get("chunk_type") == "heading":
                heading_ids.append(chunk["id"])
                headings[chunk["id"]] = chunk

        # 建立 paragraph -> heading 映射
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            if meta.get("chunk_type") == "paragraph":
                parent_id = meta.get("parent_id")
                if parent_id and parent_id in headings:
                    para_to_heading[chunk["id"]] = parent_id

        return heading_ids, para_to_heading

    # ========== Step 2: 获取 DERIVED_FROM 映射 ==========

    def _get_derived_from_map(self) -> Dict[str, str]:
        """
        从 GraphStore 获取 DERIVED_FROM 映射。
        
        Returns:
            {extracted_id: canonical_id}
        """
        conn = self.graph_store._ensure_db()
        derived_map = {}

        try:
            result = self.graph_store._execute(conn, """
                MATCH (e:ExtractedConcept)-[r:DERIVED_FROM]->(c:CanonicalConcept)
                RETURN e.extracted_id, c.canonical_id
            """)
            while result.has_next():
                row = result.get_next()
                derived_map[row[0]] = row[1]
        except Exception as e:
            print(f"[SemanticAggregator] 获取 DERIVED_FROM 失败: {e}")

        return derived_map

    # ========== Step 3: 建立 chunk -> canonical 映射 ==========

    def _build_chunk_to_canonicals(
        self, derived_map: Dict[str, str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        建立 chunk_id -> [canonical_concept] 映射。
        
        通过: chunk -(HAS_CONCEPT)-> ExtractedConcept -(DERIVED_FROM)-> CanonicalConcept
        
        Returns:
            {chunk_id: [{"id": canonical_id, "name": name}, ...]}
        """
        conn = self.graph_store._ensure_db()
        chunk_to_canonicals: Dict[str, List[Dict[str, Any]]] = {}

        try:
            result = self.graph_store._execute(conn, """
                MATCH (ch:Chunk)-[:HAS_CONCEPT]->(e:ExtractedConcept)-[:DERIVED_FROM]->(c:CanonicalConcept)
                RETURN ch.chunk_id, c.canonical_id, c.name
            """)
            while result.has_next():
                row = result.get_next()
                chunk_id = row[0]
                canonical_id = row[1]
                name = row[2]

                if chunk_id not in chunk_to_canonicals:
                    chunk_to_canonicals[chunk_id] = []
                # 去重（同一 chunk 可能通过多个 extracted 指向同一 canonical）
                existing = [c["id"] for c in chunk_to_canonicals[chunk_id]]
                if canonical_id not in existing:
                    chunk_to_canonicals[chunk_id].append({
                        "id": canonical_id,
                        "name": name,
                    })
        except Exception as e:
            print(f"[SemanticAggregator] 构建 chunk->canonical 映射失败: {e}")

        return chunk_to_canonicals

    # ========== Step 4a: 收集子概念 ==========

    def _collect_child_concepts(
        self,
        heading_id: str,
        chunks: List[Dict[str, Any]],
        para_to_heading: Dict[str, str],
        chunk_to_canonicals: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """
        收集 HeadingChunk 下所有 paragraph 的 canonical concepts（含递归子 heading 的 paragraphs）。
        
        策略: 收集所有直接或间接属于该 heading（及子 headings）的 paragraph 的概念。
        """
        # 找到该 heading 下的所有 paragraph（包括子 heading 下的）
        all_para_ids = self._get_all_paragraphs_under_heading(
            heading_id, chunks, para_to_heading
        )

        # 收集所有概念
        concepts = []
        seen_ids = set()
        for para_id in all_para_ids:
            for concept in chunk_to_canonicals.get(para_id, []):
                if concept["id"] not in seen_ids:
                    seen_ids.add(concept["id"])
                    concepts.append(concept)

        return concepts

    def _get_all_paragraphs_under_heading(
        self,
        heading_id: str,
        chunks: List[Dict[str, Any]],
        para_to_heading: Dict[str, str],
    ) -> List[str]:
        """
        递归获取 heading 下的所有 paragraph IDs（包括子 headings 下的）。
        """
        # 找到直接属于该 heading 的 paragraphs
        direct_paras = [
            pid for pid, hid in para_to_heading.items() if hid == heading_id
        ]

        # 找到子 headings
        heading = next((c for c in chunks if c["id"] == heading_id), None)
        if not heading:
            return direct_paras

        child_heading_ids = heading.get("metadata", {}).get("child_ids", [])
        
        # 递归收集子 heading 的 paragraphs
        all_paras = list(direct_paras)
        for child_hid in child_heading_ids:
            all_paras.extend(
                self._get_all_paragraphs_under_heading(child_hid, chunks, para_to_heading)
            )

        return all_paras

    # ========== Step 4b: 提取候选主题 ==========

    def _extract_theme_candidates(self, heading_path: str) -> List[str]:
        """
        从 heading_path 提取候选主题名称。
        
        策略:
        1. heading_path 最后一个 ">" 后的文本 = 当前标题
        2. 清理: 去掉序号前缀（如 "5.4 "）、标点符号
        3. 提取括号内的缩写（如 "(RRF)" -> "RRF"）
        
        Returns:
            候选主题名称列表（按优先级排序）
        """
        if not heading_path:
            return []

        # 获取最后一个标题
        parts = [p.strip() for p in heading_path.split(">")]
        current_heading = parts[-1] if parts else heading_path

        candidates = []

        # 原始标题（清理前后空格）
        candidates.append(current_heading)

        # 去掉常见前缀: 数字编号、章节号等
        cleaned = re.sub(r'^[\d\.\s、]+', '', current_heading)
        cleaned = re.sub(r'^第[一二三四五六七八九十\d]+[章节节]\s*', '', cleaned)
        cleaned = cleaned.strip()
        if cleaned and cleaned != current_heading:
            candidates.append(cleaned)

        # 提取括号内的缩写
        abbrev_match = re.search(r'\(([A-Z\-]+)\)', current_heading)
        if abbrev_match:
            candidates.append(abbrev_match.group(1))

        # 去掉括号及内容
        no_paren = re.sub(r'\s*\([^)]+\)', '', current_heading).strip()
        if no_paren and no_paren not in candidates:
            candidates.append(no_paren)

        # 去掉标点
        no_punct = re.sub(r'[^\w\u4e00-\u9fff]', '', current_heading)
        if no_punct and no_punct not in candidates:
            candidates.append(no_punct)

        return candidates

    # ========== Step 4c: 匹配主题概念 ==========

    def _match_theme_concepts(
        self,
        candidate_themes: List[str],
        concepts: List[Dict[str, Any]],
    ) -> List[str]:
        """
        在概念列表中匹配候选主题。
        
        匹配策略（按优先级）:
        1. 精确匹配（忽略大小写和空格）
        2. 子串匹配（候选包含概念名 或 概念名包含候选）
        3. 缩写匹配
        
        Returns:
            匹配到的主题概念 canonical_id 列表
        """
        theme_ids = []

        for candidate in candidate_themes:
            candidate_norm = self._normalize_text(candidate)
            if not candidate_norm:
                continue

            for concept in concepts:
                concept_name = concept.get("name", "")
                concept_norm = self._normalize_text(concept_name)

                # 精确匹配
                if candidate_norm == concept_norm:
                    theme_ids.append(concept["id"])
                    continue

                # 子串匹配（候选包含概念名）
                if concept_norm and concept_norm in candidate_norm:
                    theme_ids.append(concept["id"])
                    continue

                # 子串匹配（概念名包含候选）
                if candidate_norm in concept_norm:
                    theme_ids.append(concept["id"])
                    continue

        return list(set(theme_ids))  # 去重

    def _normalize_text(self, text: str) -> str:
        """标准化文本用于匹配（小写、去空格、去标点）。"""
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'\s+', '', text)
        text = re.sub(r'[^\w\u4e00-\u9fff]', '', text)
        return text

    # ========== Step 4d: 获取 heading 自身的概念 ==========

    def _get_heading_self_concepts(
        self,
        heading_id: str,
        chunk_to_canonicals: Dict[str, List[Dict[str, Any]]],
    ) -> List[str]:
        """
        获取 HeadingChunk 自身提取的概念（如果 heading 文本也被提取了概念）。
        
        当前 pipeline 中，graph_builder 可能只对 paragraph chunks 提取概念。
        如果 heading chunks 也被提取了概念，可以用作备选主题。
        """
        concepts = chunk_to_canonicals.get(heading_id, [])
        return [c["id"] for c in concepts]

    # ========== Step 4e: 创建 HAS_DETAIL 关系 ==========

    def _create_has_detail_relations(
        self,
        theme_ids: List[str],
        child_concepts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        创建 HAS_DETAIL 关系。
        
        规则:
        - 每个主题概念 -> 每个非主题概念（子细节概念）
        - 不创建自环
        """
        relations = []
        theme_id_set = set(theme_ids)

        for theme_id in theme_ids:
            for child in child_concepts:
                child_id = child["id"]
                if child_id in theme_id_set:
                    continue  # 跳过主题概念自身

                relations.append({
                    "from": theme_id,
                    "to": child_id,
                    "confidence": 0.85,
                })

        return relations


# ========== 便捷函数 ==========

def aggregate_semantic_layers(
    collection_name: str,
    chunks: List[Dict[str, Any]],
    graph_store: Optional[GraphStore] = None,
) -> Dict[str, Any]:
    """
    一键执行语义聚合。
    
    Args:
        collection_name: 学科集合名
        chunks: MarkdownChunker 输出的 chunk 列表
        graph_store: 可选的 GraphStore 实例
    
    Returns:
        聚合结果统计
    """
    aggregator = SemanticAggregator(collection_name, graph_store)
    return aggregator.aggregate(chunks)

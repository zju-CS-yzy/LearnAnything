"""
Phase 1: 知识库图结构层构建器

功能：
1. 从 SQLite 向量库读取 chunk 数据
2. 在 KùzuDB 中创建图 Schema
3. 构建结构层关系（BELONGS_TO, HAS_PARENT, ADJACENT_TO）

使用方式:
    from core.graph_builder import GraphBuilder
    builder = GraphBuilder("ai_llm_v2")
    builder.build_all()  # 一键构建完整结构层
"""

from pathlib import Path
from typing import Dict, List, Any

from config.settings import VECTOR_DB_DIR, GRAPH_DB_DIR
from core.vector_store import VectorStore
from core.graph_store import GraphStore


class GraphBuilder:
    """
    知识库图结构层构建器（Phase 1）。

    负责将 SQLite 向量库中的 chunk 数据迁移到 KùzuDB 图数据库，
    并建立结构层关系（文档层级、页码相邻、parent-child引用）。
    """

    def __init__(self, collection_name: str, paradigm: str = "theory"):
        """
        Args:
            collection_name: 学科集合名（如 "ai_llm_v2"）
            paradigm: 分解范式，可选 "theory" / "engineering" / "hierarchical"
        """
        self.collection_name = collection_name
        self.paradigm = paradigm
        self.vector_store = VectorStore(collection_name)
        self.graph_store = GraphStore(collection_name)

    def build_all(self, force_rebuild: bool = False) -> Dict[str, Any]:
        """
        一键构建完整的 Phase 1 图结构。

        Args:
            force_rebuild: 是否强制重建（删除已有图数据库）

        Returns:
            构建统计信息
        """
        print(f"[GraphBuilder] Starting Phase 1 build for {self.collection_name}")

        # 1. 初始化图数据库 Schema
        self.graph_store.init_schema(force=force_rebuild)

        # 2. 从向量库读取所有 chunks（parent + child）
        print("[GraphBuilder] Reading chunks from vector store...")
        all_chunks = self.vector_store.list_all(limit=100000)

        # 分离 parent 和 child
        parent_chunks = [c for c in all_chunks if c.get("metadata", {}).get("type") == "parent"]
        child_chunks = [c for c in all_chunks if c.get("metadata", {}).get("type") == "child"]

        print(f"[GraphBuilder] Found {len(parent_chunks)} parent chunks, {len(child_chunks)} child chunks")

        # 3. 添加所有 chunk 节点到图数据库
        self.graph_store.add_chunk_nodes(all_chunks)

        # 4. 构建结构层关系
        belongs_count = self.graph_store.build_belongs_to_relations()
        adjacent_count = self.graph_store.build_adjacent_relations()

        # 5. 统计
        stats = self.graph_store.get_graph_stats()

        result = {
            "collection": self.collection_name,
            "chunks_total": len(all_chunks),
            "parent_chunks": len(parent_chunks),
            "child_chunks": len(child_chunks),
            "belongs_to_edges": belongs_count,
            "adjacent_to_edges": adjacent_count,
            "graph_stats": stats,
            "status": "success",
        }

        print(f"[GraphBuilder] Phase 1 build completed: {result}")
        return result

    def increment_update(self, new_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        增量更新：向已有图谱中添加新导入的 chunk。

        Args:
            new_chunks: 新导入的 chunk 列表

        Returns:
            更新统计信息
        """
        print(f"[GraphBuilder] Incremental update: {len(new_chunks)} new chunks")

        # 确保 Schema 已初始化
        self.graph_store.init_schema()

        # 添加新节点
        added = self.graph_store.add_chunk_nodes(new_chunks)

        # 重建相关关系（仅涉及新增 chunk 的部分）
        # 注意：BELONGS_TO 和 ADJACENT_TO 需要全局重建
        # 简化处理：直接重建所有关系
        belongs_count = self.graph_store.build_belongs_to_relations()
        adjacent_count = self.graph_store.build_adjacent_relations()

        return {
            "new_chunks": len(new_chunks),
            "added_nodes": added,
            "belongs_to_edges": belongs_count,
            "adjacent_to_edges": adjacent_count,
            "status": "success",
        }

    def rebuild_relations_only(self) -> Dict[str, Any]:
        """
        仅重建关系（不重新创建节点），用于关系算法更新后重算。
        """
        print("[GraphBuilder] Rebuilding relations only...")

        belongs_count = self.graph_store.build_belongs_to_relations()
        adjacent_count = self.graph_store.build_adjacent_relations()

        return {
            "belongs_to_edges": belongs_count,
            "adjacent_to_edges": adjacent_count,
            "status": "success",
        }

    # ========== Phase 2: 语义层构建 ==========

    def extract_all_concepts(self) -> Dict[str, Any]:
        """
        对知识库中所有 chunk 进行语义提取。

        流程：
        1. 从 SQLite 向量库读取所有 chunk
        2. 对每个 chunk 调用 SemanticExtractor 提取概念
        3. 将概念写入 KùzuDB
        4. 记录质量评估分数
        """
        from core.semantic_extractor import SemanticExtractor
        from core.semantic_quality_evaluator import SemanticQualityEvaluator

        extractor = SemanticExtractor(paradigm=self.paradigm)
        evaluator = SemanticQualityEvaluator()

        # 获取所有 chunk
        all_chunks = self.vector_store.list_all(limit=10000)
        child_chunks = [c for c in all_chunks if c.get("metadata", {}).get("type", "child") != "parent"]

        if not child_chunks:
            return {"status": "empty", "message": "没有 chunk 可供提取"}

        print(f"[GraphBuilder] 开始提取 {len(child_chunks)} 个 chunk 的概念 (paradigm={self.paradigm})...")

        extracted_count = 0
        failed_count = 0
        quality_scores = []

        for chunk in child_chunks:
            chunk_id = chunk["id"]
            chunk_text = chunk.get("text", "")

            if not chunk_text.strip():
                continue

            try:
                # LA-035: 获取 chunk 的多媒体上下文
                chunk_meta = chunk.get("metadata", {})
                media_context = []
                if chunk_meta.get("media_refs"):
                    media_context = chunk_meta["media_refs"]
                
                # 提取概念（传入多媒体上下文）
                concepts = extractor.extract_concepts(chunk_text, media_context=media_context)

                # LA-035: 为图片相关 chunk 的概念注入 parent_hint
                chunk_type = chunk_meta.get("chunk_type", "") or chunk_meta.get("type", "")
                heading_path = chunk_meta.get("heading_path", "")
                if chunk_type in ("image", "image_pseudo") and heading_path:
                    for c in concepts:
                        if not c.get("parent_hint"):
                            c["parent_hint"] = heading_path

                # 写入 KùzuDB
                for c in concepts:
                    c["id"] = extractor.generate_concept_id(c["name"], chunk_id)
                    # LA-035: 将 media_refs 附加到概念
                    if media_context:
                        c["media_refs"] = media_context

                added = self.graph_store.add_concepts(chunk_id, concepts)

                if added > 0:
                    extracted_count += 1
                    # 质量评估（可选，只评估部分 chunk 以节省 API 调用）
                    if extracted_count <= 10:  # 前10个 chunk 评估质量
                        quality_result = evaluator.evaluate(chunk_text)
                        quality_scores.append(quality_result["overall_score"])

            except Exception as e:
                failed_count += 1
                if failed_count <= 5:
                    print(f"[GraphBuilder] 提取失败 {chunk_id}: {e}")

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        return {
            "status": "success",
            "chunks_processed": len(child_chunks),
            "chunks_extracted": extracted_count,
            "chunks_failed": failed_count,
            "avg_quality_score": round(avg_quality, 3),
            "quality_scores": quality_scores,
        }

    def dedupe_concepts(self) -> Dict[str, Any]:
        """
        对全局概念空间进行去重。

        返回：
            去重后的概念表统计信息
        """
        from core.concept_deduper import ConceptDeduper

        # 复用同一个 GraphStore 实例，避免 KùzuDB 锁冲突
        deduper = ConceptDeduper(self.collection_name, graph_store=self.graph_store)
        stats = deduper.get_deduped_stats()

        # 导出表格
        csv_path = deduper.export_table()

        return {
            "status": "success",
            **stats,
            "csv_path": csv_path,
        }

    # ========== Phase 2.5: 全局语义连接 ==========

    def link_concepts(self, paradigm: str = "engineering") -> Dict[str, Any]:
        """
        执行全局语义连接推断。

        流程：
        1. 调用 SemanticLinker 读取去重后的概念
        2. 基于 parent_hint 和 embedding + LLM 建立概念间连接
        3. 写入 KùzuDB
        """
        from core.semantic_linker import SemanticLinker

        linker = SemanticLinker(self.collection_name, graph_store=self.graph_store)
        result = linker.link_all(paradigm=paradigm)

        return {
            "status": "success",
            **result,
        }


def main():
    """CLI 入口，用于命令行构建图谱。"""
    import sys

    collection = sys.argv[1] if len(sys.argv) > 1 else "ai_llm_v2"
    force = "--force" in sys.argv

    builder = GraphBuilder(collection)
    result = builder.build_all(force_rebuild=force)
    print("\n=== Build Result ===")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()

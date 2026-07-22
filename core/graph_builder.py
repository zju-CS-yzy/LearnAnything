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
        2. 按 heading_path 分组，同一 heading 的 chunk 批量提取
        3. 将概念写入 KùzuDB
        4. 记录质量评估分数
        """
        from core.semantic_extractor import SemanticExtractor
        from core.semantic_quality_evaluator import SemanticQualityEvaluator

        extractor = SemanticExtractor(paradigm=self.paradigm)
        evaluator = SemanticQualityEvaluator()

        # 获取所有 chunk
        all_chunks = self.vector_store.list_all(limit=10000)
        
        # LA-035-P11: 调试打印 - 查看所有 chunk 的类型分布
        chunk_type_counts = {}
        for c in all_chunks:
            ct = c.get("metadata", {}).get("chunk_type", "") or c.get("metadata", {}).get("type", "unknown")
            chunk_type_counts[ct] = chunk_type_counts.get(ct, 0) + 1
        print(f"[GraphBuilder] 向量存储中所有 chunk 类型分布: {chunk_type_counts}")
        
        # 检查是否有图片相关的 chunk — 放宽识别条件
        # LA-052 FIX: 排除已带 VLM 描述的 image_pseudo chunks（避免重复调用 VLM）
        image_chunks = []
        for c in all_chunks:
            chunk_type = c.get("metadata", {}).get("chunk_type", "")
            # 跳过已处理的 image_pseudo chunks（已有 VLM 描述）
            if chunk_type == "image_pseudo":
                continue
            if chunk_type in ("image", "text_image") or c.get("metadata", {}).get("image_refs", []):
                image_chunks.append(c)
        
        print(f"[GraphBuilder] 找到 {len(image_chunks)} 个需要 VLM 描述的图片 chunk (排除了 image_pseudo)")
        for ic in image_chunks[:3]:
            ic_meta = ic.get("metadata", {})
            print(f"  - {ic['id']}: type={ic_meta.get('chunk_type')}, text_len={len(ic.get('text', ''))}, has_media_refs={bool(ic_meta.get('media_refs'))}, image_refs_count={len(ic_meta.get('image_refs', []))}")
        
        # LA-035-P11: 对图片 chunk 调用 VLM 生成描述，使其可提取概念
        if image_chunks:
            print(f"[GraphBuilder] 为 {len(image_chunks)} 个图片 chunk 生成 VLM 描述...")
            from core.vlm_client import VLMClient
            vlm = VLMClient()
            
            if vlm.available:
                for chunk in image_chunks:
                    chunk_meta = chunk.get("metadata", {})
                    img_refs = chunk_meta.get("image_refs", []) or chunk_meta.get("media_refs", [])
                    
                    if not img_refs:
                        print(f"[GraphBuilder] [WARN] 图片 chunk 无图片引用: {chunk['id']}")
                        continue
                    
                    # 构建完整路径（取第一个图片）
                    from config.settings import KNOWLEDGE_BASE_DIR
                    img_path = img_refs[0].get("path", "")
                    if not img_path:
                        print(f"[GraphBuilder] [WARN] 图片 chunk 无 path: {chunk['id']}")
                        continue
                    
                    full_path = KNOWLEDGE_BASE_DIR / img_path
                    
                    if not full_path.exists():
                        print(f"[GraphBuilder] [WARN] 图片文件不存在: {full_path}")
                        continue
                    
                    try:
                        # 调用 VLM 生成描述
                        description = vlm.analyze_image(str(full_path), task="describe")
                        
                        if description and description.strip():
                            # 将 VLM 描述附加到 chunk text 中
                            chunk["text"] = f"[图片内容]\n{description}\n\n[原始占位] {chunk.get('text', '')}"
                            chunk["metadata"]["vlm_description"] = description
                            print(f"[GraphBuilder] [OK] 图片 chunk VLM 描述生成成功: {chunk['id']}, desc_len={len(description)}")
                        else:
                            print(f"[GraphBuilder] [WARN] 图片 chunk VLM 描述为空: {chunk['id']}")
                    
                    except Exception as e:
                        print(f"[GraphBuilder] [ERR] 图片 chunk VLM 描述生成失败 {chunk['id']}: {e}")
            else:
                print(f"[GraphBuilder] [WARN] VLM 不可用，跳过图片 chunk 描述生成")
        
        child_chunks = [c for c in all_chunks if c.get("metadata", {}).get("type", "child") != "parent"]

        if not child_chunks:
            return {"status": "empty", "message": "没有 chunk 可供提取"}

        print(f"[GraphBuilder] 开始提取 {len(child_chunks)} 个 chunk 的概念 (paradigm={self.paradigm})...")
        print(f"[GraphBuilder] 使用小批量提取：同一 heading 内的 chunk 合并提取")

        # LA-035-P11: 按 heading_path 分组 chunk
        heading_groups = {}
        skipped_empty_text = 0
        skipped_empty_text_image = 0
        for chunk in child_chunks:
            chunk_meta = chunk.get("metadata", {})
            heading_path = chunk_meta.get("heading_path", "")
            if heading_path not in heading_groups:
                heading_groups[heading_path] = []
            heading_groups[heading_path].append(chunk)

        print(f"[GraphBuilder] 共 {len(heading_groups)} 个 heading 组")

        extracted_count = 0
        failed_count = 0
        quality_scores = []

        # 按 heading 组批量提取
        for heading_path, chunks in heading_groups.items():
            # LA-035-P12: 分离 heading chunk 和可提取 chunk
            heading_chunks = []
            extractable_chunks = []
            
            for chunk in chunks:
                chunk_type = chunk.get("metadata", {}).get("chunk_type", "") or chunk.get("metadata", {}).get("type", "")
                if chunk_type == "heading":
                    heading_chunks.append(chunk)
                else:
                    extractable_chunks.append(chunk)
            
            # 提取 heading context（作为语义层级声明注入）
            heading_context = ""
            for hc in heading_chunks:
                h_text = hc.get("text", "")
                if h_text.strip():
                    heading_context += h_text.strip() + "\n"
            heading_context = heading_context.strip()[:300]  # 截断到300字符，避免占用过多token
            
            # 准备批量提取的输入（只包含非 heading 的 chunk）
            batch_chunks = []
            for chunk in extractable_chunks:
                chunk_id = chunk["id"]
                chunk_text = chunk.get("text", "")
                chunk_meta = chunk.get("metadata", {})
                chunk_type = chunk_meta.get("chunk_type", "") or chunk_meta.get("type", "")

                # LA-035-P11: 调试 - 记录被过滤的图片 chunk
                if not chunk_text.strip():
                    skipped_empty_text += 1
                    if chunk_type in ("image", "image_pseudo", "text_image"):
                        skipped_empty_text_image += 1
                        print(f"[GraphBuilder] [WARN] 图片 chunk 因 text 为空被过滤: {chunk_id}, type={chunk_type}, image_path={chunk_meta.get('image_path', 'N/A')}")
                    continue

                # LA-035-P11: 多媒体上下文 — 统一从多种来源提取
                media_context = self._normalize_media_refs(chunk_meta)
                
                # 调试打印图片 chunk 的 media_context
                if chunk_type in ("image", "image_pseudo") and media_context:
                    print(f"[GraphBuilder] [OK] 图片 chunk 进入提取流程: {chunk_id}, media_refs_count={len(media_context)}")

                batch_chunks.append({
                    "id": chunk_id,
                    "text": chunk_text,
                    "media_context": media_context,
                })

            if not batch_chunks:
                continue

            try:
                # 批量提取（小批量：同一 heading 的 chunk 一起提取）
                # LA-035-P12: heading 作为上下文注入，heading 本身不提取概念
                batch_results = extractor.extract_concepts_batch_v2(
                    batch_chunks,
                    max_tokens_per_batch=3000,
                    heading_context=heading_context,
                )

                # 处理每个 chunk 的结果（只处理可提取的 chunk）
                for chunk in extractable_chunks:
                    chunk_id = chunk["id"]
                    chunk_meta = chunk.get("metadata", {})
                    chunk_type = chunk_meta.get("chunk_type", "") or chunk_meta.get("type", "")
                    heading_path = chunk_meta.get("heading_path", "")
                    
                    # 如果这个 chunk 因为 text 为空被跳过了，不处理
                    chunk_text = chunk.get("text", "")
                    if not chunk_text.strip():
                        continue
                    
                    media_context = self._normalize_media_refs(chunk_meta)

                    concepts = batch_results.get(chunk_id, [])
                    
                    # 调试打印图片 chunk 提取结果
                    if chunk_type in ("image", "image_pseudo", "text_image"):
                        print(f"[GraphBuilder] 图片 chunk 提取结果: {chunk_id}, concepts_count={len(concepts)}, media_refs_count={len(media_context)}")
                        for c in concepts:
                            print(f"  - 概念: {c.get('name')}, media_refs_added={bool(media_context)}")

                    # 为图片相关 chunk 的概念注入 parent_hint
                    if chunk_type in ("image", "image_pseudo", "text_image") and heading_path:
                        for c in concepts:
                            if not c.get("parent_hint"):
                                c["parent_hint"] = heading_path

                    # 写入 KùzuDB
                    for c in concepts:
                        c["id"] = extractor.generate_concept_id(c["name"], chunk_id)
                        if media_context:
                            c["media_refs"] = media_context

                    added = self.graph_store.add_concepts(chunk_id, concepts)

                    if added > 0:
                        extracted_count += 1
                        if extracted_count <= 10:
                            quality_result = evaluator.evaluate(chunk.get("text", ""))
                            quality_scores.append(quality_result["overall_score"])

            except Exception as e:
                failed_count += len(batch_chunks)
                if failed_count <= 5:
                    print(f"[GraphBuilder] heading 提取失败 [{heading_path[:50]}]: {e}")
        
        print(f"[GraphBuilder] 调试总结: skipped_empty_text={skipped_empty_text}, skipped_empty_text_image={skipped_empty_text_image}")

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        return {
            "status": "success",
            "chunks_processed": len(child_chunks),
            "chunks_extracted": extracted_count,
            "chunks_failed": failed_count,
            "avg_quality_score": round(avg_quality, 3),
            "quality_scores": quality_scores,
            "heading_groups": len(heading_groups),
        }

    def _normalize_media_refs(self, chunk_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        统一从 chunk 元数据中提取 media_refs。

        支持多种来源（按优先级）：
        1. media_refs（已标准化格式）
        2. image_refs（MarkdownChunker 输出，需转换）
        3. image_path / thumbnail_path（DocumentProcessor 图片 chunk）

        返回统一的 media_refs 列表。
        """
        # 1. 已标准化的 media_refs
        media_refs = chunk_meta.get("media_refs", []) or []
        if media_refs:
            return media_refs

        # 2. image_refs（MarkdownChunker 格式）
        image_refs = chunk_meta.get("image_refs", []) or []
        if image_refs:
            normalized = []
            for ref in image_refs:
                normalized.append({
                    "type": ref.get("type", "image"),
                    "path": ref.get("path", ""),
                    "caption": ref.get("alt", ""),
                })
            return normalized

        # 3. image_path / thumbnail_path（DocumentProcessor 图片 chunk）
        image_path = chunk_meta.get("image_path", "")
        thumbnail_path = chunk_meta.get("thumbnail_path", "")
        if image_path:
            return [{
                "type": "image",
                "path": image_path,
                "thumbnail_path": thumbnail_path,
                "caption": chunk_meta.get("text", "")[:100] or "",
                "width": chunk_meta.get("width", 0) or 0,
                "height": chunk_meta.get("height", 0) or 0,
            }]

        return []

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

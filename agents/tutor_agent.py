#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TutorAgent: 概念讲解 Agent
检索知识库 -> 上下文压缩 -> LLM 润色生成 -> 返回自然语言回答
"""

import re
from typing import Dict, Any, List, Optional

from core.embedding import EmbeddingManager
from core.hybrid_retriever import HybridRetriever
from core.reranker import RerankerFactory
from core.query_rewriter import QueryRewriter
from core.query_cache import QueryCache
from core.llm_client import LLMClient
from agents.base_agent import BaseAgent


class TutorAgent(BaseAgent):
    """概念讲解 Agent — 检索 + LLM 润色"""

    @property
    def agent_name(self) -> str:
        return "TutorAgent"

    def __init__(self, collection_name: str = "learnanything_v1", top_k: int = 5, message_bus=None):
        self.collection_name = collection_name
        self.top_k = top_k
        self._retriever = None
        self._reranker = None
        self._cache = QueryCache()
        self._rewriter = QueryRewriter()
        self._embedding = EmbeddingManager()
        self._llm = LLMClient()
        # P0-INT-6: 消息总线
        self._message_bus = message_bus
        # P0-INT-6: 用户薄弱点（从消息总线接收）
        self._user_weak_areas: List[str] = []

    def _get_retriever(self):
        if self._retriever is None:
            self._retriever = HybridRetriever(self.collection_name)
        return self._retriever

    def _get_reranker(self):
        if self._reranker is None:
            self._reranker = RerankerFactory.create()
        return self._reranker

    def _generate_answer(self, query: str, context_chunks: List[Dict[str, Any]], context_text_override: str = None, media: List[Dict[str, Any]] = None, history_text: str = None) -> str:
        """调用 LLM 生成润色后的自然语言回答（阶段 1：支持对话历史注入）。

        Args:
            query: 用户问题
            context_chunks: 上下文 chunk 列表
            context_text_override: 可选，直接使用提供的上下文文本（P0 图谱上下文）
            media: 可选，关联的媒体资源列表（LA-IMG）
            history_text: 可选，对话历史文本（阶段 1 新增）
        """
        if not self._llm.available:
            # LLM 不可用时返回原始上下文拼接
            return "\n\n---\n\n".join(c.get("text", "")[:500] for c in context_chunks)

        # 构建上下文
        if context_text_override:
            # P0: 使用图谱上下文
            context = context_text_override[:4000]  # 限制长度
            source_note = "（来自知识图谱）"
        else:
            # 传统检索：最多取前 5 个 chunk
            context_texts = []
            for i, chunk in enumerate(context_chunks[:5], 1):
                text = chunk.get("text", "").strip()
                if text:
                    context_texts.append(f"[资料{i}]\n{text[:600]}")
            context = "\n\n".join(context_texts)
            source_note = ""

        if not context:
            return "抱歉，未检索到与该问题相关的资料。"

        # LA-IMG: 构建媒体引用提示
        media_hint = ""
        if media:
            media_hint = "\n\n## 相关图片/公式资源\n"
            media_hint += "以下是与该问题相关的图片或公式，请在回答中适当位置引用它们。"
            media_hint += "引用格式：使用 markdown 图片语法，如 ![描述](/api/media/路径)。\n\n"
            for i, m in enumerate(media[:5], 1):  # 最多引用 5 张
                media_hint += f"[{i}] {m['caption']}:\n"
                media_hint += f"![{m['caption']}](/api/media/{m['path']})\n\n"

        # 阶段 1: 对话历史提示
        history_hint = ""
        if history_text:
            # 统计历史文本信息
            history_lines = history_text.strip().split('\n')
            history_turns = sum(1 for line in history_lines if line.startswith('用户:') or line.startswith('TutorAgent:'))
            history_tokens = len(history_text)
            print(f"[TutorAgent] 阶段1: 注入对话历史 {history_turns} 轮, {history_tokens} 字符")
            history_hint = f"\n\n{history_text}\n\n"
        
        # 记录上下文组装日志
        print(f"[TutorAgent] 上下文组装:")
        print(f"  - 资料来源: {'图谱(P0)' if context_text_override else '检索'}")
        print(f"  - 参考资料长度: {len(context)} 字符")
        print(f"  - 对话历史: {'已注入' if history_hint else '无'}")
        print(f"  - 媒体资源: {len(media) if media else 0} 个")
        print(f"  - 薄弱领域: {len(self._user_weak_areas)} 个")

        system_prompt = (
            "你是一位知识渊博的AI助教。请根据提供的参考资料，为用户的问题生成一个"
            "清晰、连贯、有结构的回答。要求：\n"
            "1. 直接回答用户问题，不要绕弯子\n"
            "2. 引用资料中的关键信息来支撑回答\n"
            "3. 使用适当的段落、列表和标题来组织内容\n"
            "4. 遇到专业术语时简要解释\n"
            "5. 如果提供了图片/公式资源，请在讲解到相关内容时，用 markdown 图片语法引用"
            "（格式：![描述](/api/media/路径)），让用户可以直观看到图示\n"
            "6. 如果资料不足以完全回答问题，诚实说明\n"
            "7. 如果提供了对话历史，请注意保持与上下文的连贯性，回答应与之前的对话相关联"
        )

        user_prompt = f"{history_hint}用户问题：{query}{source_note}\n\n参考资料：\n{context}{media_hint}\n\n请生成回答："
        
        # 记录最终 prompt 长度
        total_prompt_len = len(system_prompt) + len(user_prompt)
        print(f"[TutorAgent] Prompt 总长度: {total_prompt_len} 字符 (system={len(system_prompt)}, user={len(user_prompt)})")

        messages = [{"role": "user", "content": user_prompt}]

        try:
            answer = self._llm.chat(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=1500,
            )
            return answer
        except Exception as e:
            print(f"[TutorAgent] LLM 生成失败: {e}")
            # 降级：返回原始上下文
            return "\n\n---\n\n".join(c.get("text", "")[:500] for c in context_chunks)

    def handle(self, query: str, context: Optional[Any] = None, filters: Optional[Dict[str, Any]] = None, graph_context=None, **kwargs) -> Dict[str, Any]:
        """
        概念讲解主入口。
        阶段 1 增强: 支持对话上下文注入（含跨学科记忆分层）。
        """
        print(f"\n[TutorAgent] ====== handle 调用 ======")
        print(f"[TutorAgent] 查询: {query[:60]}...")
        
        # 阶段 1 增强: 记录对话上下文信息
        if context is not None and hasattr(context, 'get_log_summary'):
            print(f"[TutorAgent] 接收上下文: {context.get_log_summary()}")
        elif context is not None:
            print(f"[TutorAgent] 接收上下文: turn={getattr(context, 'turn_number', 'N/A')}, subject={getattr(context, 'subject_id', 'N/A')}")
        else:
            print(f"[TutorAgent] 无对话上下文（独立查询）")

        # P0-INT-1: 如果提供了图谱上下文，直接使用图谱上下文生成回答
        if graph_context is not None:
            print(f"[TutorAgent] P0-INT-1: 使用图谱上下文生成回答")
            return self._handle_with_graph_context(query, graph_context, context=context)

        # 否则使用传统检索方式
        return self._handle_with_retrieval(query, filters, context=context)

    def _handle_with_graph_context(self, query: str, graph_context, context=None) -> Dict[str, Any]:
        """使用 P0 图谱上下文生成回答（支持图片/公式嵌入 + 对话上下文 + 详细日志）"""
        print(f"\n{'='*60}")
        print(f"[TutorAgent] 🔗 函数链: _handle_with_graph_context() ENTER")
        print(f"[TutorAgent] 📥 输入数据链:")
        print(f"[TutorAgent]    - query: '{query[:80]}...'")
        print(f"[TutorAgent]    - has_context: {context is not None}")
        if context:
            print(f"[TutorAgent]    - session_id: {getattr(context, 'session_id', None)}")
            print(f"[TutorAgent]    - turn_number: {getattr(context, 'turn_number', None)}")
            print(f"[TutorAgent]    - current_topic: {getattr(context, 'current_topic', None)}")
            print(f"[TutorAgent]    - history_len: {len(getattr(context, 'history', []))}")
        print(f"{'='*60}")
        
        context_text = graph_context.text if hasattr(graph_context, 'text') else str(graph_context)
        concept_names = []
        if hasattr(graph_context, 'subgraph') and graph_context.subgraph:
            concept_names = [n.name for n in graph_context.subgraph.nodes]
        print(f"[TutorAgent] 图谱概念: {concept_names[:5]}")

        # P0-INT-6: 薄弱领域提示
        if self._user_weak_areas:
            print(f"[TutorAgent] P0-INT-6: 优先覆盖薄弱领域: {self._user_weak_areas}")
            weak_hint = f"用户薄弱环节: {', '.join(self._user_weak_areas)}。请重点讲解这些概念。\n\n"
            context_text = weak_hint + context_text

        # LA-IMG: 媒体资源
        media = self._collect_related_media(graph_context)
        if media:
            print(f"[TutorAgent] LA-IMG: 找到 {len(media)} 个关联媒体资源")

        # LA-047: 收集引用来源（heading_path + page_number + source）
        sources = self._collect_sources(graph_context)
        if sources:
            print(f"[TutorAgent] LA-047: 找到 {len(sources)} 个引用来源")

        # 构建 chunks
        context_chunks = []
        if hasattr(graph_context, 'subgraph') and graph_context.subgraph:
            for node in graph_context.subgraph.nodes:
                context_chunks.append({
                    "id": getattr(node, 'id', ''),
                    "text": getattr(node, 'description', '') or getattr(node, 'name', ''),
                    "source": "knowledge_graph",
                    "concept": getattr(node, 'name', ''),
                })

        # 阶段 1 增强: 注入对话历史
        history_text = ""
        if context is not None and hasattr(context, 'to_prompt_context'):
            history_text = context.to_prompt_context(max_turns=5)
            if history_text:
                print(f"[TutorAgent] 对话历史注入: {len(history_text)} 字符")
            else:
                print(f"[TutorAgent] 对话历史为空（新会话）")

        # 生成回答
        print(f"[TutorAgent] 调用 LLM 生成回答...")
        answer = self._generate_answer(query, context_chunks, context_text_override=context_text, media=media, history_text=history_text)
        print(f"[TutorAgent] 回答生成完成: {len(answer)} 字符")
        
        print(f"\n{'='*60}")
        print(f"[TutorAgent] 🔗 函数链: _handle_with_graph_context() EXIT")
        print(f"[TutorAgent] 📤 输出数据链:")
        print(f"[TutorAgent]    - answer_len: {len(answer)}")
        print(f"[TutorAgent]    - answer_preview: '{answer[:100]}...'")
        print(f"[TutorAgent]    - concepts_count: {len(concept_names)}")
        print(f"[TutorAgent]    - sources_count: {len(sources)}")
        print(f"[TutorAgent]    - media_count: {len(media)}")
        print(f"{'='*60}\n")

        return {
            "text": answer,
            "metadata": {
                "source": "p0_graph_context",
                "concepts": concept_names,
                "token_count": getattr(graph_context, 'token_count', 0),
                "media": media,
                "has_context": bool(history_text),
                "sources": sources,  # LA-047: 引用来源
            },
            "chunks": context_chunks,
        }

    def _collect_related_media(self, graph_context) -> List[Dict[str, Any]]:
        """LA-IMG: 从图谱上下文中收集关联的图片/公式资源

        FIX-LA049:
        1. 正确解析 source_chunks（支持 JSON 列表字符串、逗号分隔字符串、Python 列表）
        2. 使用安全转义避免 Cypher 语法错误
        3. 返回相对路径（学科名 + 文件名），避免 Windows 绝对路径问题
        """
        import json
        import ast
        from pathlib import Path

        media = []
        if not hasattr(graph_context, 'subgraph') or not graph_context.subgraph:
            return media

        # FIX-LA049: 正确解析 source_chunks（支持多种格式）
        chunk_ids = set()
        for node in graph_context.subgraph.nodes:
            raw = getattr(node, 'source_chunks', None)
            if not raw:
                continue

            # 尝试多种解析方式
            ids = []
            if isinstance(raw, list):
                ids = raw
            elif isinstance(raw, str):
                raw = raw.strip()
                # 尝试 JSON 解析
                if raw.startswith('[') and raw.endswith(']'):
                    try:
                        ids = json.loads(raw)
                    except json.JSONDecodeError:
                        try:
                            ids = ast.literal_eval(raw)
                        except (ValueError, SyntaxError):
                            ids = [s.strip().strip("'\"") for s in raw[1:-1].split(',')]
                else:
                    # 逗号分隔字符串
                    ids = [s.strip() for s in raw.split(',') if s.strip()]
            elif hasattr(raw, '__iter__'):
                ids = list(raw)

            for cid in ids:
                if isinstance(cid, str) and cid:
                    chunk_ids.add(cid.strip())

        if not chunk_ids:
            return media

        # 通过 GraphStore 查询 chunk 详情
        try:
            from core.graph_store import GraphStore
            store = GraphStore(self.collection_name)
            store.init_schema()
            conn = store._ensure_db()

            # FIX-LA049: 使用参数化方式构建 Cypher（避免引号注入）
            # KùzuDB 不支持参数化查询，使用安全转义
            safe_ids = []
            for cid in chunk_ids:
                # 转义单引号（Cypher 字符串中 ' 需要变成 ''）
                safe_cid = str(cid).replace("'", "\\'")
                safe_ids.append(f"'{safe_cid}'")

            id_str = ", ".join(safe_ids)
            # FIX-LA049: KùzuDB Cypher 列表字面量必须用方括号 []
            cypher = f"""
                MATCH (c:Chunk)
                WHERE c.chunk_id IN [{id_str}]
                  AND c.chunk_type IN ['image', 'image_pseudo', 'formula_pseudo']
                RETURN c.chunk_id, c.chunk_type, c.thumbnail_path, c.image_path, c.heading_path, c.media_refs
            """
            result = conn.execute(cypher)
            while result.has_next():
                row = result.get_next()
                thumbnail = row[2] or row[3]  # 优先使用缩略图
                if not thumbnail:
                    continue

                # FIX-LA049: 将绝对路径转换为相对路径
                # 期望格式: {subject}_v1_images/{filename} 或 {subject}_v1_thumbnails/{filename}
                path_str = str(thumbnail).replace('\\\\', '/').replace('\\', '/')

                # 如果是绝对路径，提取最后两部分（学科文件夹 + 文件名）
                if ':' in path_str or path_str.startswith('/'):
                    # Windows 绝对路径如 D:/.../rag_v1_images/xxx.png
                    parts = path_str.split('/')
                    # 找到包含 _v1_images 或 _v1_thumbnails 的目录名
                    for i, part in enumerate(parts):
                        if '_v1_images' in part or '_v1_thumbnails' in part:
                            # 取目录名 + 文件名
                            if i + 1 < len(parts):
                                path_str = f"{part}/{parts[i + 1]}"
                                break
                    else:
                        # 如果没找到，只保留文件名
                        path_str = parts[-1]
                elif not any(marker in path_str for marker in ['_v1_images/', '_v1_thumbnails/']):
                    # 只有文件名，尝试从 collection_name 推断学科
                    subject = self.collection_name.replace('_v1', '')
                    path_str = f"{subject}_v1_images/{path_str}"

                media.append({
                    "chunk_id": row[0],
                    "type": row[1],
                    "path": path_str,
                    "caption": row[4] or "相关图片",
                })
        except Exception as e:
            print(f"[TutorAgent] LA-IMG: 收集媒体资源失败: {e}")
            import traceback
            traceback.print_exc()

        return media

    # ==================== LA-047: 引用来源收集 ====================

    def _collect_sources(self, graph_context) -> List[Dict[str, Any]]:
        """LA-047: 从图谱上下文中收集引用来源（heading_path + page_number + source 文件名）

        遍历 subgraph 中所有节点的 source_chunks，查询 GraphStore 获取 chunk 元数据，
        去重后格式化为前端可渲染的结构。
        """
        import json
        import ast

        if not hasattr(graph_context, 'subgraph') or not graph_context.subgraph:
            return []

        # 收集所有 source_chunks 中的 chunk_id
        chunk_ids = set()
        for node in graph_context.subgraph.nodes:
            raw = getattr(node, 'source_chunks', None)
            if not raw:
                continue

            ids = []
            if isinstance(raw, list):
                ids = raw
            elif isinstance(raw, str):
                raw = raw.strip()
                if raw.startswith('[') and raw.endswith(']'):
                    try:
                        ids = json.loads(raw)
                    except json.JSONDecodeError:
                        try:
                            ids = ast.literal_eval(raw)
                        except (ValueError, SyntaxError):
                            ids = [s.strip().strip("'\"") for s in raw[1:-1].split(',')]
                else:
                    ids = [s.strip() for s in raw.split(',') if s.strip()]
            elif hasattr(raw, '__iter__'):
                ids = list(raw)

            for cid in ids:
                if isinstance(cid, str) and cid:
                    chunk_ids.add(cid.strip())

        if not chunk_ids:
            return []

        # 查询 GraphStore 获取 chunk 元数据
        try:
            from core.graph_store import GraphStore
            store = GraphStore(self.collection_name)
            store.init_schema()
            conn = store._ensure_db()

            safe_ids = []
            for cid in chunk_ids:
                safe_cid = str(cid).replace("'", "\\'")
                safe_ids.append(f"'{safe_cid}'")

            id_str = ", ".join(safe_ids)
            cypher = f"""
                MATCH (c:Chunk)
                WHERE c.chunk_id IN [{id_str}]
                RETURN c.chunk_id, c.heading_path, c.page_number, c.source
            """
            result = conn.execute(cypher)

            sources = []
            seen = set()
            while result.has_next():
                row = result.get_next()
                chunk_id = row[0] or ""
                heading_path = row[1] or ""
                page_number = row[2] if row[2] is not None else ""
                source_file = row[3] or ""

                # 去重：基于 (heading_path, page_number, source_file)
                key = (heading_path, str(page_number), source_file)
                if key in seen:
                    continue
                seen.add(key)

                # 跳过完全空的来源
                if not heading_path and not page_number and not source_file:
                    continue

                sources.append({
                    "chunk_id": chunk_id,
                    "heading_path": heading_path,
                    "page_number": str(page_number) if page_number not in (None, "", 0) else "",
                    "source": source_file,
                })

            return sources
        except Exception as e:
            print(f"[TutorAgent] LA-047: 收集引用来源失败: {e}")
            return []

    def _handle_with_retrieval(self, query: str, filters: Optional[Dict[str, Any]] = None, context=None) -> Dict[str, Any]:
        """使用传统 HybridRetriever 检索生成回答（阶段 1：支持对话上下文）"""
        # 查询改写
        queries = self._rewriter.rewrite(query, n_variants=3)

        # 缓存检查
        query_embedding = self._embedding.embed_single(queries[0])
        cached = self._cache.get(queries[0], query_embedding)
        if cached is not None:
            cached_data = cached.get('result', {})
            # 新缓存结构: {'chunks': [...], 'answer': '...'}
            if isinstance(cached_data, dict) and 'answer' in cached_data:
                return {
                    "text": cached_data['answer'],
                    "metadata": {"cache_hit": True, "hit_type": cached.get("hit_type", "unknown")},
                    "chunks": cached_data.get('chunks', [])
                }
            # 兼容旧缓存结构（纯 chunks 列表）
            elif isinstance(cached_data, list):
                chunks = cached_data
                # 阶段 1: 注入对话历史
                history_text = ""
                if context is not None and hasattr(context, 'to_prompt_context'):
                    history_text = context.to_prompt_context(max_turns=5)
                answer = self._generate_answer(query, chunks, history_text=history_text)
                return {
                    "text": answer,
                    "metadata": {"cache_hit": True, "hit_type": cached.get("hit_type", "unknown")},
                    "chunks": chunks
                }

        # 检索
        all_results = []
        retriever = self._get_retriever()
        for q in queries:
            results = retriever.query(q, n_results=50, where=None)
            all_results.extend(results)

        # 去重
        seen = set()
        unique_results = []
        for r in all_results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique_results.append(r)

        # 重排序
        reranker = self._get_reranker()
        reranked = reranker.rerank(query, unique_results[:30], top_n=30)

        # MMR 多样性
        final_results = self._apply_mmr(query, reranked, n_results=self.top_k)

        # 阶段 1: 注入对话历史
        history_text = ""
        if context is not None and hasattr(context, 'to_prompt_context'):
            history_text = context.to_prompt_context(max_turns=5)

        # 调用 LLM 生成润色回答
        answer = self._generate_answer(query, final_results, history_text=history_text)

        # 写入缓存（新结构：包含 chunks 和 answer）
        cache_data = {
            'chunks': final_results,
            'answer': answer,
        }
        self._cache.set(queries[0], query_embedding, cache_data)

        return {"text": answer, "metadata": {"chunks": len(final_results), "has_context": bool(history_text)}, "chunks": final_results}

    def _apply_mmr(self, query: str, candidates: List[Dict[str, Any]], n_results: int = 5, lambda_param: float = 0.7) -> List[Dict[str, Any]]:
        import numpy as np
        if len(candidates) <= n_results:
            return candidates

        candidate_texts = [c.get("text", "") for c in candidates]
        candidate_embeddings = np.array(self._embedding.embed(candidate_texts))
        query_embedding = np.array(self._embedding.embed_single(query))
        relevance_scores = np.dot(candidate_embeddings, query_embedding)
        doc_similarities = np.dot(candidate_embeddings, candidate_embeddings.T)

        selected_indices = []
        remaining = list(range(len(candidates)))

        for _ in range(n_results):
            if not remaining:
                break
            best_mmr = -float('inf')
            best_idx = None
            for idx in remaining:
                relevance = relevance_scores[idx]
                redundancy = max(doc_similarities[idx][s] for s in selected_indices) if selected_indices else 0.0
                mmr_score = lambda_param * relevance - (1 - lambda_param) * redundancy
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = idx
            selected_indices.append(best_idx)
            remaining.remove(best_idx)

        return [candidates[i] for i in selected_indices]

    def _compress_context(self, chunks: List[Dict[str, Any]], max_tokens: int = 4000) -> List[str]:
        cleaned = []
        total_tokens = 0
        seen_lines = {}

        for chunk in chunks:
            text = chunk.get("text", "")
            if not text or len(text) < 20:
                continue

            # 过滤 PDF 占位符
            if "本文档为 PDF 嵌入文件" in text and "需单独下载处理" in text:
                continue

            # 去除 Markdown 标记
            text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'`(.+?)`', r'\1', text)
            text = re.sub(r'```\w*\n?', '', text)
            text = text.replace('```', '')
            text = re.sub(r'^\s*>\s?', '', text, flags=re.MULTILINE)
            text = re.sub(r'^---+\s*$', '', text, flags=re.MULTILINE)
            text = re.sub(r'\n{3,}', '\n\n', text)

            # 去除重复页眉
            filtered_lines = []
            for line in text.split('\n'):
                stripped = line.strip()
                if len(stripped) < 3:
                    filtered_lines.append(line)
                    continue
                seen_lines[stripped] = seen_lines.get(stripped, 0) + 1
                if seen_lines[stripped] <= 3:
                    filtered_lines.append(line)
            text = '\n'.join(filtered_lines)

            # 截断到最大长度
            max_chunk_len = 800
            if len(text) > max_chunk_len:
                text = text[:max_chunk_len] + '...'

            estimated_tokens = len(text) * 0.7
            if total_tokens + estimated_tokens > max_tokens:
                break

            cleaned.append(text.strip())
            total_tokens += estimated_tokens

        return cleaned

    # ==================== P0-INT-6: 消息总线回调 ====================

    def on_weak_area_detected(self, msg):
        """
        订阅 weak_area 主题的回调：接收薄弱点检测，调整讲解策略。

        Args:
            msg: Message 对象（event="weak_area_detected"）
        """
        payload = msg.payload
        concept = payload.get("concept", "")
        streak_wrong = payload.get("streak_wrong", 0)
        if concept and streak_wrong >= 2:
            if concept not in self._user_weak_areas:
                self._user_weak_areas.append(concept)
            print(f"[TutorAgent] P0-INT-6: 记录薄弱点 concept={concept} streak_wrong={streak_wrong}，下次讲解将优先覆盖")

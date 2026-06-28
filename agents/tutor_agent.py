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

    def __init__(self, collection_name: str = "learnanything_v1", top_k: int = 5):
        self.collection_name = collection_name
        self.top_k = top_k
        self._retriever = None
        self._reranker = None
        self._cache = QueryCache()
        self._rewriter = QueryRewriter()
        self._embedding = EmbeddingManager()
        self._llm = LLMClient()

    def _get_retriever(self):
        if self._retriever is None:
            self._retriever = HybridRetriever(self.collection_name)
        return self._retriever

    def _get_reranker(self):
        if self._reranker is None:
            self._reranker = RerankerFactory.create()
        return self._reranker

    def _generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """调用 LLM 生成润色后的自然语言回答。"""
        if not self._llm.available:
            # LLM 不可用时返回原始上下文拼接
            return "\n\n---\n\n".join(c.get("text", "")[:500] for c in context_chunks)

        # 构建上下文（最多取前 5 个 chunk）
        context_texts = []
        for i, chunk in enumerate(context_chunks[:5], 1):
            text = chunk.get("text", "").strip()
            if text:
                context_texts.append(f"[资料{i}]\n{text[:600]}")

        context = "\n\n".join(context_texts)
        if not context:
            return "抱歉，未检索到与该问题相关的资料。"

        system_prompt = (
            "你是一位知识渊博的AI助教。请根据提供的参考资料，为用户的问题生成一个"
            "清晰、连贯、有结构的回答。要求：\n"
            "1. 直接回答用户问题，不要绕弯子\n"
            "2. 引用资料中的关键信息来支撑回答\n"
            "3. 使用适当的段落、列表和标题来组织内容\n"
            "4. 遇到专业术语时简要解释\n"
            "5. 如果资料不足以完全回答问题，诚实说明"
        )

        user_prompt = f"用户问题：{query}\n\n参考资料：\n{context}\n\n请生成回答："

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

    def handle(self, query: str, filters: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
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
                answer = self._generate_answer(query, chunks)
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

        # 调用 LLM 生成润色回答
        answer = self._generate_answer(query, final_results)

        # 写入缓存（新结构：包含 chunks 和 answer）
        cache_data = {
            'chunks': final_results,
            'answer': answer,
        }
        self._cache.set(queries[0], query_embedding, cache_data)

        return {"text": answer, "metadata": {"chunks": len(final_results)}, "chunks": final_results}

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

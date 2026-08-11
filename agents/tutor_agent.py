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
from core.llm_client import FallbackLLMClient as LLMClient  # LLM-ROBUST: 自动故障转移
from agents.base_agent import BaseAgent


class TutorAgent(BaseAgent):
    """概念讲解 Agent — 检索 + LLM 润色"""

    @property
    def agent_name(self) -> str:
        return "TutorAgent"

    def __init__(self, collection_name: str = "learnanything_v1", top_k: int = 5, message_bus=None,
                 user_theta: Optional[float] = None, graph_store=None, vector_store=None,
                 user_id: Optional[str] = None):
        self.collection_name = collection_name
        self.top_k = top_k
        # LA-IMG: 复用 Coordinator 注入的权限感知 GraphStore，避免私有学科回退到 Share。
        self._graph_store = graph_store
        self._vector_store = vector_store
        self.user_id = user_id
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
        # LA-044-#2: 用户能力水平（IRT theta），用于个性化讲解深度
        self.user_theta = user_theta

    def _get_retriever(self):
        if self._retriever is None:
            # LA-051-RET-FIX: Coordinator 注入的权限感知 VectorStore 包装进
            # HybridRetriever（保留 BM25 混合检索）；未注入时回退默认 Share 库。
            self._retriever = HybridRetriever(self.collection_name, vector_store=self._vector_store)
        return self._retriever

    def _cache_scope(self) -> str:
        """CACHE-P1-1: 查询缓存按 用户+学科 隔离，防止跨用户/跨学科答案泄漏。"""
        return f"{self.user_id or 'default'}:{self.collection_name}"

    def _get_reranker(self):
        if self._reranker is None:
            self._reranker = RerankerFactory.create()
        return self._reranker

    def _generate_answer(self, query: str, context_chunks: List[Dict[str, Any]], context_text_override: str = None, media: List[Dict[str, Any]] = None, history_text: str = None, user_theta: Optional[float] = None) -> str:
        """调用 LLM 生成润色后的自然语言回答（阶段 1：支持对话历史注入 + LA-044-#2：支持 theta 个性化）。

        Args:
            query: 用户问题
            context_chunks: 上下文 chunk 列表
            context_text_override: 可选，直接使用提供的上下文文本（P0 图谱上下文）
            media: 可选，关联的媒体资源列表（LA-IMG）
            history_text: 可选，对话历史文本（阶段 1 新增）
            user_theta: 可选，用户 IRT 能力值 0.0~1.0（LA-044-#2 新增）
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
            media_hint = "\n\n## 相关图片/公式资源（重要：请在回答中引用）\n"
            media_hint += "以下是与该问题相关的图片资源。请根据图片的**内容类型**和**适用场景**，"
            media_hint += "在回答的对应位置直接插入 markdown 图片语法 ![描述](路径)。\n"
            media_hint += "【强制规则】\n"
            media_hint += "- 流程图、架构图、示意图、工作流程图：在描述流程/架构时**必须**引用，文字描述后紧跟图片\n"
            media_hint += "- 公式图片：在讲解公式时**必须**引用\n"
            media_hint += "- 截图/示例图：在举例说明时引用\n"
            media_hint += "- 图片不能只在末尾列出，要在正文中适当位置嵌入\n"
            media_hint += "- 引用格式必须严格为 ![描述](/api/media/路径)\n\n"
            
            for i, m in enumerate(media[:5], 1):  # 最多引用 5 张
                # LA-IMG-ENHANCE: 根据文件名和标题推断内容类型
                content_type = _infer_image_content_type(m.get('caption', ''), m.get('filename', ''))
                usage_hint = _get_image_usage_hint(content_type)
                
                media_hint += f"[图片{i}] {m['caption']}\n"
                media_hint += f"  内容类型: {content_type}\n"
                media_hint += f"  适用场景: {usage_hint}\n"
                media_hint += f"  引用方式: ![{m['caption']}]({m['url'] or '/api/media/' + m['path']})\n\n"
            
            print(f"[TutorAgent] LA-IMG: 媒体提示已生成 ({len(media_hint)} 字符, {len(media)} 张图片)")
        else:
            print(f"[TutorAgent] LA-IMG: 无媒体资源")

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

        # LA-044-#2: 根据 user_theta 生成个性化讲解深度指示
        effective_theta = user_theta if user_theta is not None else self.user_theta
        personalization_hint = ""
        if effective_theta is not None:
            if effective_theta <= 0.3:
                personalization_hint = (
                    "\n\n【个性化讲解指示】该用户当前处于初学者水平。"
                    "请按照以下方式讲解：\n"
                    "1. 先解释'是什么'，再解释'为什么'，最后讲'怎么用'\n"
                    "2. 每个专业术语都必须用通俗类比来解释（如把'向量'类比为'带方向的箭头'）\n"
                    "3. 避免任何跳步，将推导/计算过程拆解到最细的步骤\n"
                    "4. 多用具体例子帮助理解，少用抽象描述\n"
                    "5. 回答长度可以适当增加，确保用户完全理解"
                )
            elif effective_theta <= 0.7:
                personalization_hint = (
                    "\n\n【个性化讲解指示】该用户当前处于中级水平。"
                    "请按照以下方式讲解：\n"
                    "1. 平衡直觉理解和形式化描述，既讲原理也讲推导\n"
                    "2. 关键步骤需要展开解释，非关键步骤可以适当跳步\n"
                    "3. 专业术语可以默认用户已了解基础含义，重点讲深层联系\n"
                    "4. 适当引入与其他知识点的关联，帮助构建知识网络\n"
                    "5. 回答长度适中，重点突出核心逻辑链"
                )
            else:
                personalization_hint = (
                    "\n\n【个性化讲解指示】该用户当前处于高级水平。"
                    "请按照以下方式讲解：\n"
                    "1. 直接聚焦核心原理和深层机制，默认基础知识已掌握\n"
                    "2. 允许大量跳步，只讲解最关键的创新点和难点\n"
                    "3. 深入技术细节（如公式推导、算法复杂度、边界条件）\n"
                    "4. 可以讨论前沿进展、变体方法和未解决问题\n"
                    "5. 回答简洁精炼，避免冗余解释，优先形式化表达"
                )
            print(f"[TutorAgent] LA-044-#2: 个性化指示已注入 (theta={effective_theta:.2f}, 级别={'初学者' if effective_theta <= 0.3 else '中级' if effective_theta <= 0.7 else '高级'})")
        else:
            print(f"[TutorAgent] LA-044-#2: 无 theta 值，使用默认讲解风格")

        system_prompt = (
            "你是一位知识渊博的AI助教。请根据提供的参考资料，为用户的问题生成一个"
            "清晰、连贯、有结构的回答。要求：\n"
            "1. 直接回答用户问题，不要绕弯子\n"
            "2. 引用资料中的关键信息来支撑回答\n"
            "3. 使用适当的段落、列表和标题来组织内容\n"
            "4. 遇到专业术语时简要解释\n"
            "5. 【图片引用规则 - 强制】如果提供了图片资源，你必须在回答中引用。具体要求：\n"
            "   a) 流程图、架构图、工作原理图：在描述流程/架构/原理时，文字描述后**必须**紧跟图片引用\n"
            "   b) 公式图片：在讲解公式时**必须**引用\n"
            "   c) 对比图、示意图：在对比/说明时**必须**引用\n"
            "   d) 引用格式严格为: ![图片描述](/api/media/路径)\n"
            "   e) 图片必须在正文段落中嵌入，不能只在末尾罗列\n"
            "   f) 先文字描述，再嵌入图片，让读者看到图对应什么内容\n"
            "   g) 【错误示例】只在最后写'如下图所示'但不嵌入图片 → 这是不允许的\n"
            "   h) 【正确示例】'该系统的工作流程如下：首先...然后... ![工作流程图](/api/media/xxx.png) 接着...'\n"
            "6. 如果资料不足以完全回答问题，诚实说明\n"
            "7. 如果提供了对话历史，请注意保持与上下文的连贯性"
            f"{personalization_hint}"
        )

        user_prompt = f"{history_hint}用户问题：{query}{source_note}\n\n## 相关图片资源（回答时必须引用）\n{media_hint}\n\n参考资料：\n{context}\n\n请生成回答："
        
        # 记录最终 prompt 长度
        total_prompt_len = len(system_prompt) + len(user_prompt)
        print(f"[TutorAgent] Prompt 总长度: {total_prompt_len} 字符 (system={len(system_prompt)}, user={len(user_prompt)})")

        messages = [{"role": "user", "content": user_prompt}]

        try:
            answer = self._llm.chat(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=4000,
            )
        except Exception as e:
            print(f"[TutorAgent] LLM 生成失败: {e}")
            return "\n\n---\n\n".join(c.get("text", "")[:500] for c in context_chunks)

        # LA-IMG-FIX: LLM 输出后处理 — 修正图片路径
        if media:
            original_answer = answer
            answer = self._fix_image_paths(answer, media)
            if answer != original_answer:
                print(f"[TutorAgent] LA-IMG-FIX: 图片路径已修正")

        return answer

    def handle(self, query: str, context: Optional[Any] = None, filters: Optional[Dict[str, Any]] = None, graph_context=None, user_theta: Optional[float] = None, **kwargs) -> Dict[str, Any]:
        """
        概念讲解主入口。
        阶段 1 增强: 支持对话上下文注入（含跨学科记忆分层）。
        LA-044-#2: 支持动态传入 user_theta 覆盖默认值。
        """
        # LA-044-#2: 动态更新 theta（如果本次请求传入了新值）
        if user_theta is not None:
            self.user_theta = user_theta
            print(f"[TutorAgent] LA-044-#2: 动态更新 user_theta={user_theta:.2f}")

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
                    # LA-UI-001 M4-FIX: ConceptNode 主键是 canonical_id（无 id 字段），
                    # 修复图谱命令派生链路的节点 id 断裂
                    "id": getattr(node, 'id', '') or getattr(node, 'canonical_id', ''),
                    "text": getattr(node, 'description', '') or getattr(node, 'name', ''),
                    "source": "knowledge_graph",
                    "concept": getattr(node, 'name', ''),
                })

        # 阶段 1 增强: 注入对话历史（使用基类统一方法）
        history_text = self.get_history_text(context, max_turns=5)
        if history_text:
            print(f"[TutorAgent] 对话历史注入: {len(history_text)} 字符")
        else:
            print(f"[TutorAgent] 对话历史为空（新会话）")

        # 生成回答
        print(f"[TutorAgent] 调用 LLM 生成回答...")
        answer = self._generate_answer(query, context_chunks, context_text_override=context_text, media=media, history_text=history_text, user_theta=self.user_theta)
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

        LA-MEDIA-UNIFY: 使用 core/media_resolver 统一解析路径，
        返回标准化的媒体对象（含可直接访问的 url 字段）。
        """
        import json
        import ast

        media = []
        seen_media_urls = set()
        if not hasattr(graph_context, 'subgraph') or not graph_context.subgraph:
            return media

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

        print(f"[TutorAgent] LA-IMG: 收集到 {len(chunk_ids)} 个 source_chunks")
        if not chunk_ids:
            return media

        # 通过 GraphStore 查询 chunk 详情
        try:
            from core.media_resolver import resolve_media_path, resolve_media_list

            store = self._graph_store
            if store is None:
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
                  AND c.chunk_type IN ['image', 'image_pseudo', 'formula_pseudo']
                RETURN c.chunk_id, c.chunk_type, c.thumbnail_path, c.image_path, c.heading_path, c.media_refs, c.source
            """
            result = conn.execute(cypher)
            while result.has_next():
                row = result.get_next()
                chunk_id = row[0]
                chunk_type = row[1]
                heading = row[4] or "相关图片"

                # 收集所有可能的路径来源
                raw_media_refs = []
                if row[5]:  # media_refs
                    try:
                        media_refs_data = json.loads(row[5])
                        if isinstance(media_refs_data, list):
                            raw_media_refs.extend(media_refs_data)
                    except Exception:
                        pass

                # 也加入 thumbnail_path 和 image_path 作为备选
                if row[2]:
                    raw_media_refs.append({"path": row[2]})
                if row[3]:
                    raw_media_refs.append({"path": row[3]})

                if not raw_media_refs:
                    continue

                # LA-MEDIA-UNIFY: 使用统一解析器解析路径
                subject = self.collection_name.replace('_v1', '')
                resolved_list = resolve_media_list(raw_media_refs, subject=subject, user_id=self.user_id)

                for resolved in resolved_list:
                    if not resolved.get("resolved"):
                        print(f"[TutorAgent] LA-IMG: 跳过未解析的媒体: {resolved}")
                        continue
                    if resolved["url"] in seen_media_urls:
                        continue
                    seen_media_urls.add(resolved["url"])

                    media.append({
                        "chunk_id": chunk_id,
                        "type": chunk_type,
                        "path": resolved["relative_path"],  # 相对路径，前端兼容性
                        "url": resolved["url"],  # LA-MEDIA-UNIFY: 统一 URL
                        "caption": heading,
                        "filename": resolved["filename"],
                        "original_name": resolved.get("original_name", ""),
                        "subject": resolved["subject"],
                    })
                    print(f"[TutorAgent] LA-IMG: 解析成功: {resolved['url']}")

        except Exception as e:
            print(f"[TutorAgent] LA-IMG: 收集媒体资源失败: {e}")
            import traceback
            traceback.print_exc()

        print(f"[TutorAgent] LA-IMG: 共收集 {len(media)} 个媒体资源")
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
            store = self._graph_store
            if store is None:
                from core.graph_store import GraphStore
                store = GraphStore(self.collection_name)
            store.init_schema()
            conn = store._ensure_db()

            safe_ids = []
            for cid in chunk_ids:
                safe_cid = str(cid).replace("'", "\\'")
                safe_ids.append(f"'{safe_cid}'")

            id_str = ", ".join(safe_ids)
            # LLM-ROBUST-FIX: 使用 UNWIND 替代 IN，避免 KùzuDB 语法兼容性问题
            cypher = f"""
                UNWIND [{id_str}] AS target_id
                MATCH (c:Chunk)
                WHERE c.chunk_id = target_id
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
                
                # LA-047-FIX: 当 heading_path 为空时，尝试从 chunk_id 推断章节信息
                display_heading = heading_path
                if not display_heading and chunk_id:
                    # 从 chunk_id 推断：md_文件名_h2_15_xxx → "第15节"
                    import re
                    # 尝试匹配 h{level}_{num} 模式
                    m = re.search(r'_h(\d+)_(\d+)', chunk_id)
                    if m:
                        level, num = m.group(1), m.group(2)
                        display_heading = f"第{num}节 (H{level})"
                    else:
                        # 尝试匹配 p_{num} 模式
                        m = re.search(r'_p_(\d+)', chunk_id)
                        if m:
                            display_heading = f"第{m.group(1)}段"
                
                # LA-047-FIX: 当 source_file 为空时，从 chunk_id 推断文件名
                display_source = source_file
                if not display_source and chunk_id:
                    import re
                    m = re.search(r'md_([^_]+(?:_[^_]+)*)_', chunk_id)
                    if m:
                        display_source = m.group(1) + ".pdf"

                sources.append({
                    "chunk_id": chunk_id,
                    "heading_path": display_heading,
                    "page_number": str(page_number) if page_number not in (None, "", 0) else "",
                    "source": display_source,
                })

            return sources
        except Exception as e:
            print(f"[TutorAgent] LA-047: 收集引用来源失败: {e}")
            return []

    def _handle_with_retrieval(self, query: str, filters: Optional[Dict[str, Any]] = None, context=None) -> Dict[str, Any]:
        """使用传统 HybridRetriever 检索生成回答（阶段 1：支持对话上下文 + LA-IMG: 支持媒体收集）"""
        # 查询改写
        queries = self._rewriter.rewrite(query, n_variants=3)

        # 缓存检查
        query_embedding = self._embedding.embed_single(queries[0])
        cached = self._cache.get(queries[0], query_embedding, scope=self._cache_scope())
        if cached is not None:
            cached_data = cached.get('result', {})
            # 新缓存结构: {'chunks': [...], 'answer': '...'}
            if isinstance(cached_data, dict) and 'answer' in cached_data:
                cached_chunks = cached_data.get('chunks', [])
                cached_media = self._collect_media_from_chunks(cached_chunks)
                cached_answer = cached_data['answer']
                if cached_media:
                    cached_answer = self._fix_image_paths(cached_answer, cached_media)
                return {
                    "text": cached_answer,
                    "metadata": {
                        "cache_hit": True,
                        "hit_type": cached.get("hit_type", "unknown"),
                        "media": cached_media,
                    },
                    "chunks": cached_chunks,
                }
            # 兼容旧缓存结构（纯 chunks 列表）
            elif isinstance(cached_data, list):
                chunks = cached_data
                # 阶段 1: 注入对话历史
                history_text = ""
                if context is not None and hasattr(context, 'to_prompt_context'):
                    history_text = context.to_prompt_context(max_turns=5)
                answer = self._generate_answer(query, chunks, history_text=history_text, user_theta=self.user_theta)
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

        # LA-IMG-FIX: 从检索结果中收集媒体资源（传统检索路径也支持图片引用）
        media = self._collect_media_from_chunks(final_results)
        if media:
            print(f"[TutorAgent] LA-IMG: 传统检索路径收集到 {len(media)} 个媒体资源")

        # 阶段 1: 注入对话历史
        history_text = ""
        if context is not None and hasattr(context, 'to_prompt_context'):
            history_text = context.to_prompt_context(max_turns=5)

        # 调用 LLM 生成润色回答
        answer = self._generate_answer(query, final_results, history_text=history_text, media=media, user_theta=self.user_theta)

        # 写入缓存（新结构：包含 chunks 和 answer）
        cache_data = {
            'chunks': final_results,
            'answer': answer,
        }
        self._cache.set(queries[0], query_embedding, cache_data, scope=self._cache_scope())

        # LA-047: 从检索结果收集引用来源
        sources = []
        for r in final_results:
            meta = r.get("metadata", {})
            src = meta.get("source", "")
            heading = meta.get("heading_path", "")
            page = meta.get("page_number", "")
            if src:
                sources.append({
                    "source": src,
                    "heading_path": heading,
                    "page_number": page,
                })
        # 去重
        seen = set()
        unique_sources = []
        for s in sources:
            key = s["source"]
            if key not in seen:
                seen.add(key)
                unique_sources.append(s)
        
        return {
            "text": answer,
            "metadata": {"chunks": len(final_results), "has_context": bool(history_text), "media": media},
            "sources": unique_sources,  # LA-047: 引用来源
            "chunks": final_results,
        }

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

    def _collect_media_from_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """LA-IMG-FIX: 从检索结果中收集媒体资源（传统检索路径使用）
        
        遍历检索到的 chunks，提取 image_pseudo / image / formula_pseudo 类型的 chunk
        中的媒体引用信息。
        """
        import json
        from core.media_resolver import resolve_media_list

        media = []
        seen_paths = set()
        
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            chunk_type = meta.get("chunk_type", "")
            
            # 只处理包含图片的 chunk 类型
            if chunk_type not in ("image_pseudo", "image", "formula_pseudo"):
                continue
            
            # 提取 media_refs
            media_refs = meta.get("media_refs", [])
            if isinstance(media_refs, str):
                try:
                    media_refs = json.loads(media_refs)
                except Exception:
                    media_refs = []
            
            if not media_refs:
                continue
            
            # 使用统一解析器解析路径
            subject = self.collection_name.replace('_v1', '')
            resolved_list = resolve_media_list(media_refs, subject=subject, user_id=self.user_id)
            
            for resolved in resolved_list:
                if not resolved.get("resolved"):
                    continue
                # 去重
                key = resolved.get("url", "")
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                
                media.append({
                    "chunk_id": chunk.get("id", ""),
                    "type": chunk_type,
                    "path": resolved["relative_path"],
                    "url": resolved["url"],
                    "caption": meta.get("image_title", meta.get("heading_path", "相关图片")),
                    "filename": resolved["filename"],
                    "original_name": resolved.get("original_name", ""),
                    "subject": resolved["subject"],
                })
        
        return media

    def _fix_image_paths(self, answer: str, media: List[Dict[str, Any]]) -> str:
        """LA-IMG-FIX: LLM 输出后处理 — 修正不完整的图片路径

        LLM 经常只输出文件名（如 ![图](xxx.png)）而不是完整 URL。
        此函数扫描 answer 中的 markdown 图片链接，自动补全为可访问的路径。
        """
        import re

        # 构建 filename -> 完整 url 的映射
        filename_to_url = {}
        for m in media:
            # 从 url 中提取文件名
            url = m.get("url", "")
            filename = m.get("filename", "")
            if filename and url:
                filename_to_url[filename] = url
            # 也支持从 path 中提取
            path = m.get("path", "")
            if path:
                path_filename = path.split("/")[-1]
                if path_filename and path_filename not in filename_to_url:
                    filename_to_url[path_filename] = url or f"/api/media/{path}"

        canonical_media = [m for m in media if m.get("url")]
        canonical_urls = {m.get("url", "").split("?", 1)[0] for m in canonical_media}

        if not filename_to_url:
            return answer

        # 正则匹配 markdown 图片: ![alt](url)
        def replace_image(match):
            alt = match.group(1)
            url = match.group(2).strip()

            # 如果已经是完整 URL，不处理
            if url.startswith("http://") or url.startswith("https://"):
                return match.group(0)
            if "/api/media/Share/" in url or "/api/media/Users/" in url:
                if url.split("?", 1)[0] in canonical_urls:
                    return match.group(0)

            # 提取文件名（处理 /api/media/filename.png 或纯 filename.png）
            raw_filename = url.split("/")[-1]

            # 在映射中查找匹配
            if raw_filename in filename_to_url:
                full_url = filename_to_url[raw_filename]
                print(f"[TutorAgent] LA-IMG-FIX: 替换 '{url}' -> '{full_url}'")
                return f"![{alt}]({full_url})"

            # 尝试模糊匹配（去除扩展名）
            for known_filename, full_url in filename_to_url.items():
                # 去掉扩展名比较
                known_stem = known_filename.rsplit(".", 1)[0] if "." in known_filename else known_filename
                raw_stem = raw_filename.rsplit(".", 1)[0] if "." in raw_filename else raw_filename
                if known_stem == raw_stem:
                    print(f"[TutorAgent] LA-IMG-FIX: 模糊替换 '{url}' -> '{full_url}'")
                    return f"![{alt}]({full_url})"

            # 没找到匹配，保持原样
            # LLM 可能把中文文件名改写成英文别名（例如 rag_typical_flow.png）。
            # 只有在后端明确提供了媒体资源时才回写，避免把真正的幻觉 URL 指向任意文件。
            if len(canonical_media) == 1:
                full_url = canonical_media[0]["url"]
                print(f"[TutorAgent] LA-IMG-FIX: 未知图片引用 '{url}' 回写到唯一关联媒体 '{full_url}'")
                return f"![{alt}]({full_url})"

            # 多张图片时按 alt/caption/文件名做保守匹配。
            alt_text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", alt).lower()
            best = None
            best_score = 0
            for candidate in canonical_media:
                searchable = " ".join(str(candidate.get(k, "")) for k in ("caption", "filename", "original_name")).lower()
                tokens = [t for t in re.split(r"\s+", re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", searchable)) if t]
                score = sum(1 for token in tokens if len(token) >= 2 and token in alt_text)
                if score > best_score:
                    best_score, best = score, candidate
            if best is not None:
                full_url = best["url"]
                print(f"[TutorAgent] LA-IMG-FIX: 按描述匹配 '{url}' -> '{full_url}'")
                return f"![{alt}]({full_url})"

            # 没找到匹配，保持原样
            return match.group(0)

        # 替换 markdown 图片链接
        fixed = re.sub(r"!\[(.*?)\]\((.*?)\)", replace_image, answer)
        return fixed

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


# ==================== LA-IMG-ENHANCE: 图片内容类型推断辅助函数 ====================

def _infer_image_content_type(caption: str, filename: str) -> str:
    """根据图片标题和文件名推断内容类型，用于生成更精确的媒体提示。"""
    text = (caption + " " + filename).lower()
    
    if any(k in text for k in ["流程", "workflow", "process", "步骤", "step", "sequence"]):
        return "流程图"
    if any(k in text for k in ["架构", "architecture", "结构", "structure", "framework", "框架"]):
        return "架构图"
    if any(k in text for k in ["原理", "principle", "mechanism", "how it works", "工作原理"]):
        return "原理示意图"
    if any(k in text for k in ["对比", "compare", "comparison", "vs", "versus", "差异"]):
        return "对比图"
    if any(k in text for k in ["公式", "formula", "equation", "math", "latex"]):
        return "公式"
    if any(k in text for k in ["截图", "screen", "screenshot", "界面", "ui", "界面"]):
        return "截图/界面"
    if any(k in text for k in ["示例", "example", "demo", "sample", "实例"]):
        return "示例图"
    if any(k in text for k in ["数据", "chart", "graph", "统计", "趋势", "分布"]):
        return "数据图表"
    return "示意图"


def _get_image_usage_hint(content_type: str) -> str:
    """根据内容类型返回使用提示，告诉 LLM 什么时候该引用这张图。"""
    hints = {
        "流程图": "描述工作流程、处理步骤、算法流程时**必须**引用",
        "架构图": "描述系统架构、模块组成、层次结构时**必须**引用",
        "原理示意图": "解释工作原理、核心机制、关键概念时**必须**引用",
        "对比图": "进行对比分析、优劣比较、方案选型时**必须**引用",
        "公式": "讲解数学公式、算法表达式时**必须**引用",
        "截图/界面": "展示界面操作、配置步骤时引用",
        "示例图": "举例说明、展示具体案例时引用",
        "数据图表": "展示数据趋势、统计结果、实验数据时引用",
        "示意图": "辅助说明抽象概念或复杂结构时引用",
    }
    return hints.get(content_type, "在讲解相关内容时引用")

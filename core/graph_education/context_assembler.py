"""
LA-040-P0: Context Assembler（上下文组装器）

将图谱子图组装为 LLM 可理解的结构化上下文（Graph-to-Text）
"""

import re
import json
from typing import Dict, List, Optional, Any

from core.graph_education.types import (
    ConceptNode, Subgraph, GraphContext, ContextBudget, UserKnowledgeState, QuestionPattern
)


class ContextAssembler:
    """
    上下文组装器：将图谱子图组装为 LLM 可理解的结构化上下文
    
    核心功能：
    1. 出题上下文组装：将子图组装为出题用的概念描述
    2. 讲解上下文组装：将子图 + 用户状态组装为讲解用的知识网络
    3. 预算控制：token 预算内裁剪、描述截断、节点淘汰
    """
    
    # 中文 token 估算系数（经验值：1 中文字 ≈ 1.5 tokens）
    TOKEN_RATIO = 1.5
    
    def __init__(self, tokenizer: Optional[Any] = None, graph_store=None):
        """
        Args:
            tokenizer: 可选的分词器（如 tiktoken），用于精确估算 token。
                       未提供时使用字符数估算。
            graph_store: 可选的 GraphStore 实例，用于查询 Chunk 节点的完整来源信息。
        """
        self.tokenizer = tokenizer
        self.graph_store = graph_store
    
    # ───────────────────────────────────────────────
    # 核心接口
    # ───────────────────────────────────────────────
    
    def assemble(
        self,
        subgraph: Subgraph,
        budget: ContextBudget,
        include_prerequisites: bool = False,
        include_media: bool = True,
        target_concept: Optional[ConceptNode] = None
    ) -> GraphContext:
        """
        组装出题上下文
        
        Args:
            subgraph: 构建好的子图
            budget: token 预算
            include_prerequisites: 是否包含前置知识链
            include_media: 是否包含媒体引用描述
            target_concept: 目标概念（用于标记重点）
            
        Returns:
            GraphContext: 组装后的上下文
        """
        # 1. 裁剪到预算
        trimmed = self.trim_to_budget(subgraph, budget)
        
        # 1.1 处理空子图
        if not trimmed.nodes:
            return GraphContext(
                text="（暂无关联概念）",
                token_count=0,
                subgraph=trimmed,
                sections={}
            )
        
        # 2. 组装各段
        sections = {}
        
        # 目标知识点
        if target_concept:
            sections["target"] = self._format_target_concept(target_concept)
        else:
            sections["target"] = self._format_target_concept(trimmed.nodes[0])
        
        # 概念列表
        sections["concepts"] = self._format_concept_list(trimmed.nodes)
        
        # 依赖链（如果要求）
        if include_prerequisites and len(trimmed.edges) > 0:
            sections["prerequisites"] = self._format_prerequisites(trimmed)
        
        # 来源文档
        sections["sources"] = self._format_sources(trimmed.nodes)
        
        # 3. 合并为完整文本
        full_text = self._merge_sections(sections)
        
        # 4. 估算 token
        token_count = self.estimate_tokens(full_text)
        
        return GraphContext(
            text=full_text,
            token_count=token_count,
            subgraph=trimmed,
            sections=sections
        )
    
    def assemble_explanation(
        self,
        subgraph: Subgraph,
        user_states: Dict[str, UserKnowledgeState],
        target_concept: Optional[ConceptNode] = None,
        depth: str = "L2",
        user_answer: Optional[str] = None
    ) -> GraphContext:
        """
        组装讲解上下文
        
        Args:
            subgraph: 讲解子图
            user_states: 用户在各概念上的知识状态
            target_concept: 目标概念（出错的概念）
            depth: 讲解深度（L1/L2/L3/L4）
            user_answer: 用户答案（用于分析错误选项）
            
        Returns:
            GraphContext: 组装后的讲解上下文
        """
        # 根据深度确定预算
        depth_budget = {
            "L1": ContextBudget(max_tokens=1500, max_nodes=5),
            "L2": ContextBudget(max_tokens=2500, max_nodes=12),
            "L3": ContextBudget(max_tokens=3500, max_nodes=20),
            "L4": ContextBudget(max_tokens=5000, max_nodes=30),
        }.get(depth, ContextBudget(max_tokens=2500, max_nodes=12))
        
        # 裁剪到预算
        trimmed = self.trim_to_budget(subgraph, depth_budget)
        
        sections = {}
        
        # 核心错因定位
        if target_concept:
            sections["定位"] = self._format_explanation_target(target_concept, user_states)
        
        # 知识网络
        sections["知识网络"] = self._format_knowledge_network(trimmed, user_states)
        
        # 原文依据
        sections["原文依据"] = self._format_sources(trimmed.nodes)
        
        # 用户答案分析（如果提供）
        if user_answer:
            sections["答案分析"] = self._format_answer_analysis(user_answer, target_concept)
        
        # 推荐学习路径
        sections["推荐"] = self._format_recommendations(trimmed, user_states)
        
        full_text = self._merge_sections(sections)
        token_count = self.estimate_tokens(full_text)
        
        return GraphContext(
            text=full_text,
            token_count=token_count,
            subgraph=trimmed,
            sections=sections
        )
    
    # ───────────────────────────────────────────────
    # 预算控制
    # ───────────────────────────────────────────────
    
    def trim_to_budget(
        self,
        subgraph: Subgraph,
        budget: ContextBudget
    ) -> Subgraph:
        """
        将子图裁剪到 token 预算内
        
        策略：
        1. 保留中心/种子节点
        2. 截断描述文本到 max_description_length
        3. 如果仍超预算，按 PageRank 删除低重要性节点
        """
        # 快速路径：节点数已在限制内
        if len(subgraph.nodes) <= budget.max_nodes:
            # 仍需截断描述
            trimmed_nodes = self._trim_descriptions(subgraph.nodes, budget.max_description_length)
            return Subgraph(
                nodes=trimmed_nodes,
                edges=subgraph.edges,
                seed_concepts=subgraph.seed_concepts,
                build_mode=subgraph.build_mode
            )
        
        # 策略：保留种子节点 + 最高 PageRank 的节点
        seed_ids = set(subgraph.seed_concepts)
        
        # 按重要性排序：种子优先，然后 PageRank
        sorted_nodes = sorted(
            subgraph.nodes,
            key=lambda n: (n.canonical_id in seed_ids, n.pagerank_score),
            reverse=True
        )
        
        kept = sorted_nodes[:budget.max_nodes]
        kept_ids = {n.canonical_id for n in kept}
        
        # 截断描述
        kept = self._trim_descriptions(kept, budget.max_description_length)
        
        # 过滤边（只保留两端都在 kept 中的边）
        kept_edges = [
            e for e in subgraph.edges
            if e.source_id in kept_ids and e.target_id in kept_ids
        ]
        
        return Subgraph(
            nodes=kept,
            edges=kept_edges,
            seed_concepts=subgraph.seed_concepts,
            build_mode=subgraph.build_mode
        )
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算文本 token 数
        
        简单实现：按字符数 × 1.5 估算
        更精确的方式可使用 tiktoken
        """
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except:
                pass
        
        # 混合文本：中文字符 × 1.5 + 英文单词 × 1.2
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        
        return int(chinese_chars * self.TOKEN_RATIO + other_chars * 0.5)
    
    # ───────────────────────────────────────────────
    # 格式化方法
    # ───────────────────────────────────────────────
    
    def _format_target_concept(self, concept: ConceptNode) -> str:
        """格式化目标概念"""
        lines = [f"## 目标知识点"]
        lines.append(f"- **概念**: {concept.name}")
        lines.append(f"- **类型**: {concept.concept_type}")
        if concept.description:
            # 描述截断到 150 字（保证可读性）
            desc = concept.description[:150]
            if len(concept.description) > 150:
                desc += "..."
            lines.append(f"- **描述**: {desc}")
        if concept.aliases:
            lines.append(f"- **别名**: {', '.join(concept.aliases[:3])}")
        return "\n".join(lines)
    
    def _format_concept_list(self, nodes: List[ConceptNode]) -> str:
        """格式化概念列表"""
        lines = ["## 关联概念"]
        for i, node in enumerate(nodes, 1):
            desc = node.description[:80] if node.description else ""
            if len(node.description) > 80:
                desc += "..."
            lines.append(f"{i}. **{node.name}** ({node.concept_type}) - {desc}")
        return "\n".join(lines)
    
    def _format_prerequisites(self, subgraph: Subgraph) -> str:
        """格式化前置知识链"""
        # 查找 DEPENDS_ON 链
        chains = []
        for edge in subgraph.edges:
            if edge.edge_type == "DEPENDS_ON" or edge.edge_type == "RELATED":
                source = subgraph.node_map.get(edge.source_id)
                target = subgraph.node_map.get(edge.target_id)
                if source and target:
                    chains.append(f"- {source.name} ← {target.name}")
        
        if not chains:
            return "## 前置知识\n（无明确依赖链）"
        
        return "## 前置知识\n" + "\n".join(chains)
    
    def _format_sources(self, nodes: List[ConceptNode]) -> str:
        """
        格式化来源文档
        
        如果提供了 graph_store，会查询 Chunk 节点获取完整的文档信息：
        - 文件名（从 metadata.source 解析）
        - 章节路径（heading_path）
        - 页码（page_number）
        """
        chunk_ids = set()
        for node in nodes:
            if node.source_chunks:
                for chunk_id in str(node.source_chunks).split(","):
                    chunk_id = chunk_id.strip()
                    if chunk_id:
                        chunk_ids.add(chunk_id)
        
        if not chunk_ids:
            return "## 来源文档\n（无明确来源）"
        
        # 如果有 graph_store，查询 Chunk 节点获取完整元数据
        if self.graph_store:
            chunk_info = self._query_chunk_info(chunk_ids)
            if chunk_info:
                return self._format_sources_enriched(chunk_info)
        
        # 回退：简单显示 chunk_id
        lines = ["## 来源文档"]
        for s in list(chunk_ids)[:5]:
            lines.append(f"- {s}")
        return "\n".join(lines)
    
    def _query_chunk_info(self, chunk_ids: set) -> List[Dict]:
        """查询 Chunk 节点的元数据（文件名、章节、页码）"""
        if not chunk_ids or not self.graph_store:
            return []
        
        conn = self.graph_store._ensure_db()
        id_str = ", ".join([f"'{cid}'" for cid in chunk_ids])
        
        # 注意：KùzuDB 中 Chunk 节点的 id 字段是 chunk_id，文件名是 source 字段
        cypher = f"""
            MATCH (c:Chunk)
            WHERE c.chunk_id IN [{id_str}]
            RETURN c.chunk_id, c.heading_path, c.page_number, c.source
        """
        
        results = []
        try:
            result = self.graph_store._execute(conn, cypher)
            while result.has_next():
                row = result.get_next()
                results.append({
                    "chunk_id": row[0] or "",
                    "heading_path": row[1] or "",
                    "page_number": row[2] if row[2] is not None else "",
                    "metadata": json.dumps({"source": row[3] or ""})  # 模拟 metadata 格式
                })
        except Exception:
            pass
        
        return results
    
    def _format_sources_enriched(self, chunk_info: List[Dict]) -> str:
        """格式化 enriched 来源信息（含文件名、章节、页码）"""
        if not chunk_info:
            return "## 来源文档\n（无明确来源）"
        
        # 按文件分组
        by_file = {}
        for info in chunk_info:
            filename = "未知文件"
            try:
                metadata = json.loads(info["metadata"]) if info["metadata"] else {}
                filename = metadata.get("source", "未知文件")
            except (json.JSONDecodeError, TypeError):
                pass
            
            if filename not in by_file:
                by_file[filename] = []
            by_file[filename].append(info)
        
        lines = ["## 来源文档"]
        for filename, chunks in by_file.items():
            lines.append(f"- **文件**: {filename}")
            for info in chunks:
                parts = []
                if info["heading_path"]:
                    parts.append(f"章节: {info['heading_path']}")
                if info["page_number"] not in (None, "", 0):
                    parts.append(f"页码: {info['page_number']}")
                if info["chunk_id"]:
                    parts.append(f"段落: {info['chunk_id']}")
                if parts:
                    lines.append(f"  - {'; '.join(parts)}")
        return "\n".join(lines)
    
    def _format_explanation_target(
        self,
        target: ConceptNode,
        user_states: Dict[str, UserKnowledgeState]
    ) -> str:
        """格式化讲解目标定位"""
        lines = ["## 核心错因定位"]
        lines.append(f"- **目标概念**: {target.name}")
        
        state = user_states.get(target.canonical_id)
        if state:
            lines.append(f"- **掌握度**: {state.mastery_level:.0%}")
            lines.append(f"- **测试次数**: {state.test_count}")
            lines.append(f"- **连续正确**: {state.streak}")
        
        if target.description:
            lines.append(f"- **核心定义**: {target.description[:100]}")
        
        return "\n".join(lines)
    
    def _format_knowledge_network(
        self,
        subgraph: Subgraph,
        user_states: Dict[str, UserKnowledgeState]
    ) -> str:
        """格式化知识网络（含用户状态）"""
        lines = ["## 知识网络"]
        
        # 节点状态
        lines.append("### 概念状态")
        for node in subgraph.nodes:
            state = user_states.get(node.canonical_id)
            mastery = f"{state.mastery_level:.0%}" if state else "未测试"
            lines.append(f"- {node.name}: {mastery}")
        
        # 连接关系
        if subgraph.edges:
            lines.append("### 概念关联")
            for edge in subgraph.edges:
                source = subgraph.node_map.get(edge.source_id)
                target = subgraph.node_map.get(edge.target_id)
                if source and target:
                    rel = "→" if edge.edge_type == "SOLUTION" else "←"
                    lines.append(f"- {source.name} {rel} {target.name}")
        
        return "\n".join(lines)
    
    def _format_answer_analysis(self, user_answer: str, target: Optional[ConceptNode]) -> str:
        """格式化答案分析"""
        lines = ["## 答案分析"]
        lines.append(f"- **用户答案**: {user_answer}")
        if target:
            lines.append(f"- **涉及概念**: {target.name}")
        return "\n".join(lines)
    
    def _format_recommendations(
        self,
        subgraph: Subgraph,
        user_states: Dict[str, UserKnowledgeState]
    ) -> str:
        """格式化推荐学习路径"""
        # 找出掌握度最低的 3 个概念
        weak = []
        for node in subgraph.nodes:
            state = user_states.get(node.canonical_id)
            if state and state.mastery_level < 0.5:
                weak.append((node.name, state.mastery_level))
        
        weak.sort(key=lambda x: x[1])
        
        lines = ["## 推荐学习"]
        if weak:
            lines.append("### 优先补强")
            for name, level in weak[:3]:
                lines.append(f"- {name}（掌握度: {level:.0%}）")
        else:
            lines.append("- 当前概念掌握度良好，建议继续拓展")
        
        return "\n".join(lines)
    
    def _merge_sections(self, sections: Dict[str, str]) -> str:
        """合并各段为完整文本"""
        parts = []
        for key, content in sections.items():
            if content and content.strip():
                parts.append(content)
                parts.append("")  # 空行分隔
        return "\n".join(parts).strip()
    
    def _trim_descriptions(
        self,
        nodes: List[ConceptNode],
        max_length: int
    ) -> List[ConceptNode]:
        """截断所有节点的描述"""
        result = []
        for node in nodes:
            # 创建副本，避免修改原始节点
            trimmed = ConceptNode(
                canonical_id=node.canonical_id,
                name=node.name,
                concept_type=node.concept_type,
                description=node.description[:max_length] if node.description else "",
                aliases=node.aliases,
                parent_hint=node.parent_hint,
                pagerank_score=node.pagerank_score,
                in_degree=node.in_degree,
                out_degree=node.out_degree,
                source_chunks=node.source_chunks,
            )
            if len(node.description) > max_length:
                trimmed.description += "..."
            result.append(trimmed)
        return result

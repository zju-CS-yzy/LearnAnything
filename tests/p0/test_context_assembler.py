"""
LA-040-P0: Context Assembler 单元测试

测试文件: tests/p0/test_context_assembler.py
覆盖 TC-CA-001 ~ TC-CA-006 及错误码测试
"""

import pytest

from core.graph_education.context_assembler import ContextAssembler
from core.graph_education.types import (
    ConceptNode, Subgraph, ContextBudget, GraphContext, UserKnowledgeState
)


class TestAssembleQuestion:
    """测试出题上下文组装"""
    
    def test_assemble_within_budget(self, sample_subgraph):
        """TC-CA-001: 预算内组装"""
        assembler = ContextAssembler()
        budget = ContextBudget(max_tokens=1500, max_nodes=10)
        
        result = assembler.assemble(
            subgraph=sample_subgraph,
            budget=budget,
            target_concept=sample_subgraph.nodes[0]
        )
        
        assert isinstance(result, GraphContext)
        assert result.token_count <= 1500
        assert "目标知识点" in result.text
        assert "关联概念" in result.text
        assert "来源文档" in result.text
    
    def test_assemble_sections(self, sample_subgraph):
        """组装结果包含多个段落"""
        assembler = ContextAssembler()
        budget = ContextBudget(max_tokens=1500, max_nodes=10)
        
        result = assembler.assemble(sample_subgraph, budget)
        
        assert "sections" in result.__dict__
        assert len(result.sections) >= 3
    
    def test_assemble_with_prerequisites(self, sample_subgraph):
        """TC-CA-003: 包含依赖链"""
        assembler = ContextAssembler()
        budget = ContextBudget(max_tokens=2000, max_nodes=10)
        
        result = assembler.assemble(
            subgraph=sample_subgraph,
            budget=budget,
            include_prerequisites=True
        )
        
        assert "前置知识" in result.text or "前置知识" in str(result.sections)
    
    def test_assemble_trim_descriptions(self, large_subgraph):
        """描述被截断"""
        assembler = ContextAssembler()
        budget = ContextBudget(max_tokens=1000, max_nodes=5, max_description_length=50)
        
        result = assembler.assemble(large_subgraph, budget)
        
        # 检查节点描述是否被截断
        for node in result.subgraph.nodes:
            assert len(node.description) <= 55  # 50 + "..."


class TestAssembleExplanation:
    """测试讲解上下文组装"""
    
    def test_assemble_explanation_l2(self, sample_subgraph):
        """TC-CA-004: L2 链讲解"""
        assembler = ContextAssembler()
        
        # 创建用户状态
        user_states = {}
        for node in sample_subgraph.nodes:
            user_states[node.canonical_id] = UserKnowledgeState(
                canonical_id=node.canonical_id,
                canonical_name=node.name,
                mastery_level=0.3,
                test_count=2,
                streak=-1
            )
        
        result = assembler.assemble_explanation(
            subgraph=sample_subgraph,
            user_states=user_states,
            target_concept=sample_subgraph.nodes[0],
            depth="L2"
        )
        
        assert isinstance(result, GraphContext)
        assert "核心错因定位" in result.text
        assert "知识网络" in result.text
        # 讲解上下文中使用 "来源文档" 而非 "原文依据"
        assert "来源文档" in result.text
    
    def test_assemble_explanation_l3(self, sample_subgraph):
        """TC-CA-005: L3 面讲解"""
        assembler = ContextAssembler()
        
        user_states = {}
        for node in sample_subgraph.nodes:
            user_states[node.canonical_id] = UserKnowledgeState(
                canonical_id=node.canonical_id,
                canonical_name=node.name,
                mastery_level=0.2,
                test_count=5,
                streak=-3
            )
        
        result = assembler.assemble_explanation(
            subgraph=sample_subgraph,
            user_states=user_states,
            target_concept=sample_subgraph.nodes[0],
            depth="L3"
        )
        
        # L3 应该有推荐学习
        assert "推荐学习" in result.text
        assert "优先补强" in result.text
    
    def test_assemble_explanation_with_answer(self, sample_subgraph):
        """包含答案分析"""
        assembler = ContextAssembler()
        user_states = {}
        
        result = assembler.assemble_explanation(
            subgraph=sample_subgraph,
            user_states=user_states,
            target_concept=sample_subgraph.nodes[0],
            depth="L2",
            user_answer="C"
        )
        
        assert "答案分析" in result.text
        assert "C" in result.text


class TestTrimToBudget:
    """测试预算裁剪"""
    
    def test_trim_respects_max_nodes(self, large_subgraph):
        """TC-CA-002: 超预算裁剪到节点上限"""
        assembler = ContextAssembler()
        budget = ContextBudget(max_tokens=1500, max_nodes=3)
        
        trimmed = assembler.trim_to_budget(large_subgraph, budget)
        
        assert len(trimmed.nodes) <= 3
    
    def test_trim_keeps_seed_nodes(self, large_subgraph):
        """裁剪保留种子节点"""
        assembler = ContextAssembler()
        budget = ContextBudget(max_tokens=1500, max_nodes=3)
        
        trimmed = assembler.trim_to_budget(large_subgraph, budget)
        
        # 种子节点应该被保留
        seed_ids = set(large_subgraph.seed_concepts)
        kept_ids = {n.canonical_id for n in trimmed.nodes}
        # 至少保留一个种子节点
        assert any(sid in kept_ids for sid in seed_ids)
    
    def test_trim_no_edges_lost(self, large_subgraph):
        """裁剪后边不丢失"""
        assembler = ContextAssembler()
        budget = ContextBudget(max_tokens=1500, max_nodes=5)
        
        trimmed = assembler.trim_to_budget(large_subgraph, budget)
        
        # 边的两端都在保留节点中
        kept_ids = {n.canonical_id for n in trimmed.nodes}
        for edge in trimmed.edges:
            assert edge.source_id in kept_ids
            assert edge.target_id in kept_ids


class TestEstimateTokens:
    """测试 token 估算"""
    
    def test_estimate_chinese(self):
        """中文估算"""
        assembler = ContextAssembler()
        text = "注意力机制"
        
        result = assembler.estimate_tokens(text)
        # 4 个中文字 × 1.5 ≈ 6
        assert result >= 4
    
    def test_estimate_mixed(self):
        """混合文本估算"""
        assembler = ContextAssembler()
        text = "Attention 注意力机制"
        
        result = assembler.estimate_tokens(text)
        assert result > 0
    
    def test_estimate_empty(self):
        """空文本估算"""
        assembler = ContextAssembler()
        assert assembler.estimate_tokens("") == 0


class TestFormatSections:
    """测试各段格式化"""
    
    def test_format_target_concept(self, attention_concept):
        """目标概念格式化"""
        assembler = ContextAssembler()
        result = assembler._format_target_concept(attention_concept)
        
        assert "目标知识点" in result
        assert "注意力机制" in result
        assert "概念" in result
    
    def test_format_concept_list(self, sample_concept_nodes):
        """概念列表格式化"""
        assembler = ContextAssembler()
        result = assembler._format_concept_list(sample_concept_nodes[:3])
        
        assert "关联概念" in result
        for node in sample_concept_nodes[:3]:
            assert node.name in result
    
    def test_format_sources(self, sample_concept_nodes):
        """来源文档格式化"""
        # 给第一个节点添加来源
        nodes = list(sample_concept_nodes[:2])
        nodes[0].source_chunks = "chunk_001"
        
        assembler = ContextAssembler()
        result = assembler._format_sources(nodes)
        
        assert "来源文档" in result
        assert "chunk_001" in result
    
    def test_format_sources_empty(self):
        """无来源文档"""
        assembler = ContextAssembler()
        result = assembler._format_sources([])
        
        assert "无明确来源" in result


class TestMergeSections:
    """测试段落合并"""
    
    def test_merge_multiple_sections(self):
        """合并多段"""
        assembler = ContextAssembler()
        sections = {
            "A": "内容A",
            "B": "内容B",
            "C": "内容C"
        }
        
        result = assembler._merge_sections(sections)
        
        assert "内容A" in result
        assert "内容B" in result
        assert "内容C" in result
    
    def test_merge_skips_empty(self):
        """跳过空段落"""
        assembler = ContextAssembler()
        sections = {
            "A": "内容A",
            "B": "",
            "C": "内容C"
        }
        
        result = assembler._merge_sections(sections)
        
        assert "内容A" in result
        assert "内容B" not in result
        assert "内容C" in result


class TestEdgeCases:
    """测试边界情况"""
    
    def test_empty_subgraph(self):
        """空子图"""
        assembler = ContextAssembler()
        empty = Subgraph(nodes=[], edges=[])
        budget = ContextBudget(max_tokens=1000, max_nodes=5)
        
        # 没有节点的子图应该返回空内容
        result = assembler.assemble(empty, budget)
        
        assert isinstance(result, GraphContext)
    
    def test_single_node_subgraph(self, attention_concept):
        """单节点子图"""
        assembler = ContextAssembler()
        single = Subgraph(nodes=[attention_concept], edges=[])
        budget = ContextBudget(max_tokens=1000, max_nodes=5)
        
        result = assembler.assemble(single, budget)
        
        assert "注意力机制" in result.text
    
    def test_very_long_description(self, attention_concept):
        """超长描述截断"""
        assembler = ContextAssembler()
        attention_concept.description = "这是一个非常长的描述" * 50
        single = Subgraph(nodes=[attention_concept], edges=[])
        budget = ContextBudget(max_tokens=500, max_nodes=5, max_description_length=30)
        
        result = assembler.assemble(single, budget)
        
        # 描述应该被截断
        assert "..." in result.text or len(result.text) < 500


class TestExplanationsWithStates:
    """测试含用户状态的讲解"""
    
    def test_weak_concept_recommendation(self, sample_subgraph):
        """薄弱概念推荐"""
        assembler = ContextAssembler()
        
        # 创建一个薄弱状态
        user_states = {
            sample_subgraph.nodes[0].canonical_id: UserKnowledgeState(
                canonical_id=sample_subgraph.nodes[0].canonical_id,
                canonical_name=sample_subgraph.nodes[0].name,
                mastery_level=0.2,  # 薄弱
                test_count=3
            )
        }
        
        result = assembler.assemble_explanation(
            sample_subgraph,
            user_states,
            depth="L2"
        )
        
        assert "优先补强" in result.text or "薄弱" in result.text

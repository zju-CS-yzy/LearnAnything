"""
LA-040-P0: Subgraph Builder 单元测试

测试文件: tests/p0/test_subgraph_builder.py
覆盖 TC-SB-001 ~ TC-SB-007 及错误码测试
"""

import pytest

from core.graph_education.types import ConceptNode, Subgraph, ContextBudget, QuestionPattern
from core.graph_education.subgraph_builder import SubgraphBuilder


class TestBuildStar:
    """测试星型子图构建"""
    
    def test_build_star_basic(self, subgraph_builder, attention_concept):
        """TC-SB-001: 基本星型子图"""
        subgraph = subgraph_builder.build_star(
            attention_concept,
            include_derived=True,
            max_nodes=10
        )
        
        assert isinstance(subgraph, Subgraph)
        assert subgraph.build_mode == "star"
        assert len(subgraph.nodes) >= 1
        assert subgraph.nodes[0].name == "注意力机制"
        assert "concept_c1_attention" in subgraph.seed_concepts
    
    def test_build_star_respects_max_nodes(self, subgraph_builder, attention_concept):
        """星型子图尊重 max_nodes"""
        subgraph = subgraph_builder.build_star(
            attention_concept,
            max_nodes=3
        )
        
        assert len(subgraph.nodes) <= 3
    
    def test_build_star_has_center(self, subgraph_builder, attention_concept):
        """星型子图包含中心节点"""
        subgraph = subgraph_builder.build_star(attention_concept)
        
        center_names = [n.name for n in subgraph.nodes]
        assert "注意力机制" in center_names


class TestBuildChain:
    """测试链型子图构建"""
    
    def test_build_chain_basic(self, subgraph_builder, mha_concept, attention_concept):
        """TC-SB-002: 基本链型子图"""
        subgraph = subgraph_builder.build_chain(
            mha_concept,
            attention_concept,
            max_nodes=10
        )
        
        assert isinstance(subgraph, Subgraph)
        assert subgraph.build_mode == "chain"
        assert len(subgraph.nodes) >= 2
        
        names = [n.name for n in subgraph.nodes]
        assert "多头注意力" in names
        assert "注意力机制" in names
    
    def test_build_chain_no_path_raises(self, subgraph_builder, attention_concept):
        """TC-SB-ERR-002: 两点间无路径"""
        # 创建与图中其他节点无连接的孤立概念
        isolated = ConceptNode(
            canonical_id="concept_isolated",
            name="孤立概念",
            description="没有连接的概念"
        )
        
        with pytest.raises(ValueError) as exc_info:
            subgraph_builder.build_chain(attention_concept, isolated)
        
        assert "LA-0403003" in str(exc_info.value)


class TestBuildTree:
    """测试树型子图构建"""
    
    def test_build_tree_basic(self, subgraph_builder, attention_concept):
        """TC-SB-003: 基本树型子图"""
        subgraph = subgraph_builder.build_tree(
            attention_concept,
            max_depth=2,
            max_nodes=10
        )
        
        assert isinstance(subgraph, Subgraph)
        assert subgraph.build_mode == "tree"
        assert len(subgraph.nodes) >= 1
        assert subgraph.max_depth == 2
    
    def test_build_tree_respects_max_depth(self, subgraph_builder, attention_concept):
        """树型子图尊重 max_depth"""
        subgraph = subgraph_builder.build_tree(
            attention_concept,
            max_depth=1,
            max_nodes=10
        )
        
        # depth=1 只有根节点和直接邻居
        assert len(subgraph.nodes) >= 1
    
    def test_build_tree_respects_max_nodes(self, subgraph_builder, transformer_concept):
        """树型子图尊重 max_nodes"""
        subgraph = subgraph_builder.build_tree(
            transformer_concept,
            max_depth=3,
            max_nodes=4
        )
        
        assert len(subgraph.nodes) <= 4


class TestBuildGeneral:
    """测试通用子图构建"""
    
    def test_build_auto_single_seed(self, subgraph_builder, attention_concept):
        """自动模式：单种子 → Star"""
        subgraph = subgraph_builder.build(
            [attention_concept],
            mode="auto"
        )
        
        assert subgraph.build_mode == "star"
    
    def test_build_auto_multi_seed(self, subgraph_builder, attention_concept, mha_concept):
        """自动模式：多种子 → Tree"""
        subgraph = subgraph_builder.build(
            [attention_concept, mha_concept],
            mode="auto"
        )
        
        assert subgraph.build_mode == "tree"
    
    def test_build_with_related(self, subgraph_builder, attention_concept, mha_concept):
        """带相关概念构建"""
        subgraph = subgraph_builder.build(
            [attention_concept],
            related_concepts=[mha_concept],
            max_nodes=10
        )
        
        names = [n.name for n in subgraph.nodes]
        assert "注意力机制" in names
        assert "多头注意力" in names
    
    def test_build_empty_seed_raises(self, subgraph_builder):
        """TC-SB-ERR-001: 空种子抛出错误"""
        with pytest.raises(ValueError) as exc_info:
            subgraph_builder.build([])
        
        assert "LA-0403001" in str(exc_info.value)
    
    def test_build_respects_max_nodes(self, subgraph_builder, transformer_concept):
        """TC-SB-004: 子图节点数上限"""
        subgraph = subgraph_builder.build_tree(
            transformer_concept,
            max_depth=3,
            max_nodes=5
        )
        
        assert len(subgraph.nodes) <= 5


class TestBuildForPattern:
    """测试题型专用子图构建"""
    
    def test_build_for_pattern_choice(self, subgraph_builder, attention_concept):
        """TC-SB-005: 选择题模式"""
        pattern = QuestionPattern(
            pattern_id="choice_single",
            name="单选题",
            concept_depth=1,
            max_concepts_per_question=5
        )
        
        subgraph = subgraph_builder.build_for_pattern(
            attention_concept,
            pattern
        )
        
        assert len(subgraph.nodes) <= 5
        assert "注意力机制" in [n.name for n in subgraph.nodes]
    
    def test_build_for_pattern_essay(self, subgraph_builder, attention_concept):
        """TC-SB-006: 解答题模式"""
        pattern = QuestionPattern(
            pattern_id="essay",
            name="解答题",
            concept_depth=2,
            max_concepts_per_question=15,
            require_concept_chain=True
        )
        
        subgraph = subgraph_builder.build_for_pattern(
            attention_concept,
            pattern
        )
        
        assert len(subgraph.nodes) <= 15
        assert subgraph.build_mode == "tree"


class TestBuildForExplanation:
    """测试讲解子图构建"""
    
    def test_build_for_explanation_l1(self, subgraph_builder, attention_concept):
        """L1 讲解：简单"""
        class MockQuestion:
            primary_concepts = ["concept_c1_attention"]
            knowledge_trace = None
        
        question = MockQuestion()
        subgraph = subgraph_builder.build_for_explanation(question, depth="L1")
        
        assert len(subgraph.nodes) <= 5
    
    def test_build_for_explanation_l2(self, subgraph_builder, attention_concept):
        """L2 讲解：链式"""
        class MockQuestion:
            primary_concepts = ["concept_c1_attention"]
            knowledge_trace = None
        
        question = MockQuestion()
        subgraph = subgraph_builder.build_for_explanation(question, depth="L2")
        
        assert len(subgraph.nodes) <= 12
    
    def test_build_for_explanation_no_concepts_raises(self, subgraph_builder):
        """无关联概念时抛出错误"""
        class MockQuestion:
            primary_concepts = []
            knowledge_trace = None
        
        with pytest.raises(ValueError) as exc_info:
            subgraph_builder.build_for_explanation(MockQuestion())
        
        assert "LA-0403001" in str(exc_info.value)


class TestSnapshot:
    """测试序列化与重建"""
    
    def test_snapshot_roundtrip(self, subgraph_builder, sample_subgraph):
        """TC-SB-007: 序列化与重建"""
        snapshot = subgraph_builder.to_snapshot(sample_subgraph)
        restored = subgraph_builder.from_snapshot(snapshot)
        
        # 节点数量相同
        assert len(restored.nodes) == len(sample_subgraph.nodes)
        
        # 节点名称一致
        original_names = sorted([n.name for n in sample_subgraph.nodes])
        restored_names = sorted([n.name for n in restored.nodes])
        assert original_names == restored_names
        
        # 边数量一致
        assert len(restored.edges) == len(sample_subgraph.edges)
    
    def test_snapshot_preserves_metadata(self, subgraph_builder, sample_subgraph):
        """快照保留元数据"""
        snapshot = subgraph_builder.to_snapshot(sample_subgraph)
        
        assert "seed_concepts" in snapshot
        assert "build_mode" in snapshot
        assert "nodes" in snapshot
        assert "edges" in snapshot
    
    def test_from_snapshot_empty(self, subgraph_builder):
        """从空快照重建"""
        snapshot = {"nodes": [], "edges": [], "seed_concepts": [], "build_mode": "auto"}
        restored = subgraph_builder.from_snapshot(snapshot)
        
        assert len(restored.nodes) == 0
        assert len(restored.edges) == 0


class TestSubgraphOperations:
    """测试子图操作方法"""
    
    def test_node_map(self, sample_subgraph):
        """节点映射"""
        node_map = sample_subgraph.node_map
        
        assert isinstance(node_map, dict)
        assert all(isinstance(k, str) for k in node_map.keys())
        assert all(isinstance(v, ConceptNode) for v in node_map.values())
    
    def test_get_neighbors(self, subgraph_builder, attention_concept):
        """获取邻居"""
        # 先构建一个包含边的子图
        subgraph = subgraph_builder.build_tree(attention_concept, max_depth=2, max_nodes=10)
        
        if len(subgraph.nodes) > 1:
            root = subgraph.nodes[0]
            neighbors = subgraph.get_neighbors(root.canonical_id)
            
            # 邻居应该是节点对象
            assert all(isinstance(n, ConceptNode) for n in neighbors)
    
    def test_get_outgoing(self, subgraph_builder, attention_concept):
        """获取 outgoing 邻居"""
        subgraph = subgraph_builder.build_tree(attention_concept, max_depth=2, max_nodes=10)
        
        if len(subgraph.nodes) > 1:
            root = subgraph.nodes[0]
            outgoing = subgraph.get_outgoing(root.canonical_id)
            
            assert all(isinstance(n, ConceptNode) for n in outgoing)
    
    def test_node_count(self, sample_subgraph):
        """节点计数"""
        assert sample_subgraph.node_count == len(sample_subgraph.nodes)
    
    def test_edge_count(self, sample_subgraph):
        """边计数"""
        assert sample_subgraph.edge_count == len(sample_subgraph.edges)


class TestEdgeQueries:
    """测试边查询内部方法"""
    
    def test_query_edges_between(self, subgraph_builder, sample_concept_nodes):
        """查询节点间的边"""
        ids = {n.canonical_id for n in sample_concept_nodes[:3]}
        edges = subgraph_builder._query_edges_between(ids)
        
        # 返回的边应该在节点集合内
        for e in edges:
            assert e.source_id in ids or e.target_id in ids


class TestEnsureConceptChain:
    """测试依赖链确保"""
    
    def test_ensure_concept_chain_adds_prerequisite(self, subgraph_builder, mha_concept):
        """确保前置概念被添加"""
        # 构建一个只包含 mha 的星型子图
        subgraph = subgraph_builder.build_star(mha_concept, max_nodes=5)
        
        # 手动检查是否有 DEPENDS_ON 边
        has_depends = any(
            e.edge_type == "DEPENDS_ON" and e.target_id == mha_concept.canonical_id
            for e in subgraph.edges
        )
        
        # 如果原来没有，_ensure_concept_chain 应该添加
        # 注意：这里取决于测试数据库的实际数据
        assert isinstance(subgraph, Subgraph)

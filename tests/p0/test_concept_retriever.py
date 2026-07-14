"""
LA-040-P0: Concept Retriever 单元测试

测试文件: tests/p0/test_concept_retriever.py
覆盖 TC-CR-001 ~ TC-CR-008 及错误码测试
"""

import pytest

from core.graph_education.concept_retriever import ConceptRetriever
from core.graph_education.types import ConceptNode


class TestResolve:
    """测试概念解析功能"""
    
    def test_resolve_exact_match(self, concept_retriever):
        """TC-CR-001: 名称精确匹配"""
        result = concept_retriever.resolve(["注意力机制"])
        
        assert len(result) == 1
        assert result[0].name == "注意力机制"
        assert result[0].canonical_id == "concept_c1_attention"
    
    def test_resolve_alias_match(self, concept_retriever):
        """TC-CR-002: 别名匹配（Self-Attention）"""
        # 注意：测试数据中的别名是 ["Attention Mechanism", "Attention"]
        # 所以 "Attention" 应该匹配到 "注意力机制"
        result = concept_retriever.resolve(["Attention"])
        
        assert len(result) == 1
        assert result[0].name == "注意力机制"
    
    def test_resolve_multi_concepts(self, concept_retriever):
        """解析多个概念"""
        result = concept_retriever.resolve(["注意力机制", "多头注意力"])
        
        assert len(result) == 2
        names = [n.name for n in result]
        assert "注意力机制" in names
        assert "多头注意力" in names
    
    def test_resolve_empty_list(self, concept_retriever):
        """空列表返回空结果"""
        result = concept_retriever.resolve([])
        assert result == []
    
    def test_resolve_deduplicate(self, concept_retriever):
        """重复概念去重"""
        result = concept_retriever.resolve(["注意力机制", "注意力机制"])
        
        assert len(result) == 1
        assert result[0].name == "注意力机制"
    
    def test_resolve_not_found_raises(self, concept_retriever):
        """TC-CR-ERR-002: 概念名称解析失败"""
        with pytest.raises(ValueError) as exc_info:
            concept_retriever.resolve(["完全不存在的概念名称"])
        
        assert "LA-0402001" in str(exc_info.value)
        assert "未找到匹配概念" in str(exc_info.value)
    
    def test_resolve_partial_not_found(self, concept_retriever):
        """部分概念不存在时返回已找到的部分"""
        result = concept_retriever.resolve(["注意力机制", "完全不存在的概念"])
        
        # 至少返回已找到的概念
        assert len(result) >= 1
        assert result[0].name == "注意力机制"
    
    def test_resolve_all_not_found_raises(self, concept_retriever):
        """所有概念都不存在时抛出错误"""
        with pytest.raises(ValueError) as exc_info:
            concept_retriever.resolve(["完全不存在的概念1", "完全不存在的概念2"])
        
        assert "LA-0402001" in str(exc_info.value)
    
    def test_resolve_strips_whitespace(self, concept_retriever):
        """去除前后空白"""
        result = concept_retriever.resolve(["  注意力机制  "])
        
        assert len(result) == 1
        assert result[0].name == "注意力机制"


class TestExpand:
    """测试概念扩展功能"""
    
    def test_expand_one_hop(self, concept_retriever, attention_concept):
        """TC-CR-004: 1-hop 扩展"""
        result = concept_retriever.expand(
            [attention_concept],
            hop=1,
            max_nodes=20
        )
        
        names = [n.name for n in result]
        assert "注意力机制" in names
        # 应该有邻居（如多头注意力、缩放点积注意力）
        assert len(result) >= 1
    
    def test_expand_two_hop(self, concept_retriever, attention_concept):
        """2-hop 扩展"""
        result = concept_retriever.expand(
            [attention_concept],
            hop=2,
            max_nodes=20
        )
        
        names = [n.name for n in result]
        assert "注意力机制" in names
        # 2-hop 应该包含更多节点
        assert len(result) >= 1
    
    def test_expand_respects_max_nodes(self, concept_retriever, attention_concept):
        """TC-CR-005: 限制 max_nodes"""
        result = concept_retriever.expand(
            [attention_concept],
            hop=2,
            max_nodes=3
        )
        
        assert len(result) <= 3
    
    def test_expand_empty_seed_raises(self, concept_retriever):
        """空种子抛出错误"""
        with pytest.raises(ValueError) as exc_info:
            concept_retriever.expand([], hop=1)
        
        assert "LA-0403001" in str(exc_info.value)
    
    def test_expand_filter_by_edge_type(self, concept_retriever, attention_concept):
        """按边类型过滤"""
        result = concept_retriever.expand(
            [attention_concept],
            hop=1,
            edge_types=["DEPENDS_ON"],
            max_nodes=20
        )
        
        # 只包含 DEPENDS_ON 类型的边
        assert len(result) >= 1
    
    def test_expand_multiple_seeds(self, concept_retriever, attention_concept, mha_concept):
        """多种子扩展"""
        result = concept_retriever.expand(
            [attention_concept, mha_concept],
            hop=1,
            max_nodes=20
        )
        
        names = [n.name for n in result]
        assert "注意力机制" in names
        assert "多头注意力" in names


class TestSelectWeakConcepts:
    """测试薄弱概念选择"""
    
    def test_select_weak_no_history(self, concept_retriever):
        """TC-CR-006/007: 无历史数据时选择 PageRank 最低的概念"""
        result = concept_retriever.select_weak_concepts(
            user_id="test_user",
            subject_id="test_transformer",
            n=3
        )
        
        assert len(result) <= 3
        assert len(result) > 0
        # 返回的都是 ConceptNode
        assert all(isinstance(n, ConceptNode) for n in result)
    
    def test_select_weak_respects_n(self, concept_retriever):
        """n 参数限制返回数量"""
        result = concept_retriever.select_weak_concepts(
            user_id="test_user",
            subject_id="test_transformer",
            n=2
        )
        
        assert len(result) <= 2


class TestSelectByCoverage:
    """测试覆盖度选择"""
    
    def test_select_by_coverage_basic(self, concept_retriever):
        """基本覆盖度选择"""
        result = concept_retriever.select_by_coverage(
            subject_id="test_transformer",
            existing_questions=None,
            n=3
        )
        
        assert len(result) <= 3
        assert len(result) > 0

    def test_select_by_coverage_with_existing(self, concept_retriever):
        """有已有题目时排除已覆盖"""
        # 模拟已有题目
        class MockQuestion:
            def __init__(self, concepts):
                self.primary_concepts = concepts
        
        existing = [MockQuestion(["concept_c1_attention"])]
        
        result = concept_retriever.select_by_coverage(
            subject_id="test_transformer",
            existing_questions=existing,
            n=5
        )
        
        # 不应该包含已覆盖的概念
        ids = [n.canonical_id for n in result]
        assert "concept_c1_attention" not in ids


class TestGetConceptStats:
    """测试概念统计信息"""
    
    def test_get_concept_stats(self, concept_retriever):
        """TC-CR-008: 获取概念统计"""
        stats = concept_retriever.get_concept_stats("concept_c1_attention")
        
        assert isinstance(stats, dict)
        assert "in_degree" in stats
        assert "out_degree" in stats
        assert "neighbor_count" in stats
        assert stats["in_degree"] >= 0
        assert stats["out_degree"] >= 0
    
    def test_get_concept_stats_nonexistent(self, concept_retriever):
        """不存在的概念返回零值"""
        stats = concept_retriever.get_concept_stats("nonexistent")
        
        assert stats["in_degree"] == 0
        assert stats["out_degree"] == 0


class TestSearchByEmbedding:
    """测试 Embedding 语义检索"""
    
    def test_search_without_vector_store(self, concept_retriever):
        """无 vector_store 时返回空"""
        result = concept_retriever.search_by_embedding("query", top_k=5)
        assert result == []


class TestInternalMethods:
    """测试内部方法"""
    
    def test_match_exact_found(self, concept_retriever):
        """精确匹配成功"""
        node = concept_retriever._match_exact("多头注意力")
        assert node is not None
        assert node.name == "多头注意力"
    
    def test_match_exact_not_found(self, concept_retriever):
        """精确匹配失败"""
        node = concept_retriever._match_exact("不存在的概念")
        assert node is None
    
    def test_match_fuzzy(self, concept_retriever):
        """模糊匹配"""
        nodes = concept_retriever._match_fuzzy("注意力")
        assert len(nodes) > 0
        assert all("注意力" in n.name for n in nodes)
    
    def test_load_nodes_by_ids(self, concept_retriever):
        """批量加载节点"""
        nodes = concept_retriever._load_nodes_by_ids([
            "concept_c1_attention",
            "concept_c2_mha"
        ])
        
        assert len(nodes) == 2
        names = [n.name for n in nodes]
        assert "注意力机制" in names
        assert "多头注意力" in names
    
    def test_load_nodes_by_ids_empty(self, concept_retriever):
        """空 ID 列表"""
        nodes = concept_retriever._load_nodes_by_ids([])
        assert nodes == []
    
    def test_row_to_node(self, concept_retriever):
        """行数据转换"""
        row = ("id_1", "名称", "类型", "描述", "hint", '["别名1"]')
        node = concept_retriever._row_to_node(row)
        
        assert node.canonical_id == "id_1"
        assert node.name == "名称"
        assert node.aliases == ["别名1"]

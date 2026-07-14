"""
LA-040-P0: Group Manager 单元测试

测试文件: tests/p0/test_group_manager.py
"""

import pytest

from core.graph_education.group_manager import GroupManager
from core.graph_education.types import (
    QuestionGroup, GroupStatus, Question, UserKnowledgeState
)


class MockCache:
    """内存缓存"""
    def __init__(self):
        self._data = {}
    def get(self, key, default=None):
        return self._data.get(key, default)
    def set(self, key, value, ttl=None):
        self._data[key] = value
    def delete(self, key):
        self._data.pop(key, None)
    def clear(self):
        self._data.clear()


@pytest.fixture
def mock_cache():
    return MockCache()


@pytest.fixture
def group_manager(test_graph_store, mock_cache):
    from core.graph_education import (
        ConceptRetriever, SubgraphBuilder, ContextAssembler, IRTEstimator
    )
    
    retriever = ConceptRetriever(graph_store=test_graph_store)
    builder = SubgraphBuilder(graph_store=test_graph_store)
    assembler = ContextAssembler()
    irt = IRTEstimator(calibration_stage=1)
    
    return GroupManager(
        retriever=retriever,
        builder=builder,
        assembler=assembler,
        irt=irt,
        cache=mock_cache
    )


class TestCreateGroup:
    """测试生成题目组"""
    
    def test_create_group_basic(self, group_manager):
        """基本题目组生成"""
        group = group_manager.create_group(
            user_id="user_001",
            subject_id="test_transformer",
            template_id="quick_practice"
        )
        
        assert isinstance(group, QuestionGroup)
        assert group.status == GroupStatus.GENERATED
        assert group.user_id == "user_001"
        assert len(group.questions) == 5  # quick_practice 模板有 5 题
        assert all(q.irt_params.b is not None for q in group.questions)
    
    def test_create_group_with_target_concepts(self, group_manager):
        """指定目标概念"""
        group = group_manager.create_group(
            user_id="user_001",
            subject_id="test_transformer",
            target_concepts=["注意力机制"]
        )
        
        assert len(group.questions) > 0
        # 至少有一题关联到目标概念
        assert any(
            "concept_c1_attention" in q.knowledge_trace.primary_concepts
            for q in group.questions
        )
    
    def test_create_group_invalid_template(self, group_manager):
        """无效模板"""
        with pytest.raises(ValueError) as exc_info:
            group_manager.create_group(
                user_id="user_001",
                subject_id="test_transformer",
                template_id="nonexistent"
            )
        assert "LA-0406001" in str(exc_info.value)


class TestStartGroup:
    """测试开始答题"""
    
    def test_start_group_success(self, group_manager):
        """正常开始"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        
        updated = group_manager.start_group(group.group_id)
        assert updated.status == GroupStatus.IN_PROGRESS
    
    def test_start_group_already_started(self, group_manager):
        """重复开始"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        group_manager.start_group(group.group_id)
        
        with pytest.raises(ValueError) as exc_info:
            group_manager.start_group(group.group_id)
        
        assert "LA-0406002" in str(exc_info.value)


class TestSubmitGroup:
    """测试提交整组"""
    
    def test_submit_group_success(self, group_manager):
        """正常提交"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        group_manager.start_group(group.group_id)
        
        answers = [
            {"question_id": q.question_id, "user_answer": "B", "time_spent": 120}
            for q in group.questions
        ]
        
        result = group_manager.submit_group(group.group_id, answers)
        
        assert result["status"] == "grading"
        assert "score" in result
        assert result["total"] == len(group.questions)
    
    def test_submit_group_answer_mismatch(self, group_manager):
        """答案数量不匹配"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        group_manager.start_group(group.group_id)
        
        answers = [
            {"question_id": group.questions[0].question_id, "user_answer": "B", "time_spent": 120}
        ]
        
        with pytest.raises(ValueError) as exc_info:
            group_manager.submit_group(group.group_id, answers)
        
        assert "LA-0406003" in str(exc_info.value)
    
    def test_submit_group_already_submitted(self, group_manager):
        """重复提交"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        group_manager.start_group(group.group_id)
        
        answers = [
            {"question_id": q.question_id, "user_answer": "B", "time_spent": 120}
            for q in group.questions
        ]
        
        group_manager.submit_group(group.group_id, answers)
        
        with pytest.raises(ValueError) as exc_info:
            group_manager.submit_group(group.group_id, answers)
        
        assert "LA-0406002" in str(exc_info.value)
    
    def test_submit_updates_state(self, group_manager):
        """提交后更新用户状态"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        group_manager.start_group(group.group_id)
        
        answers = [
            {"question_id": q.question_id, "user_answer": "B", "time_spent": 120}
            for q in group.questions
        ]
        
        group_manager.submit_group(group.group_id, answers)
        
        # 检查能力画像已生成
        profile = group_manager._load_profile("user_001", "test_transformer")
        assert profile is not None
        assert "overall_score" in profile


class TestGetResult:
    """测试获取结果"""
    
    def test_get_result_not_graded(self, group_manager):
        """未评分时返回等待"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        
        result = group_manager.get_group_result(group.group_id)
        
        assert result["status"] == "generated"
    
    def test_get_result_graded(self, group_manager):
        """评分后返回完整结果"""
        group = group_manager.create_group(
            user_id="user_001", subject_id="test_transformer"
        )
        group_manager.start_group(group.group_id)
        
        answers = [
            {"question_id": q.question_id, "user_answer": "B", "time_spent": 120}
            for q in group.questions
        ]
        
        group_manager.submit_group(group.group_id, answers)
        
        result = group_manager.get_group_result(group.group_id)
        
        assert result["status"] == "graded"
        assert "score" in result
        assert "weak_concepts" in result


class TestKnowledgeState:
    """测试知识状态管理"""
    
    def test_load_or_create_state(self, group_manager):
        """加载或创建状态"""
        state = group_manager._load_or_create_state(
            "user_001", "test_transformer", "concept_c1"
        )
        
        assert state.user_id == "user_001"
        assert state.canonical_id == "concept_c1"
        assert state.mastery_level == 0.0
    
    def test_save_and_load_state(self, group_manager):
        """保存和加载状态"""
        state = group_manager._load_or_create_state(
            "user_001", "test_transformer", "concept_c1"
        )
        state.mastery_level = 0.8
        group_manager._save_user_state(state)
        
        loaded = group_manager._load_user_state(
            "user_001", "test_transformer", "concept_c1"
        )
        
        assert loaded.mastery_level == 0.8


class TestProfile:
    """测试能力画像"""
    
    def test_generate_profile_empty(self, group_manager):
        """无历史数据时生成画像"""
        profile = group_manager._generate_profile("user_001", "test_transformer")
        
        assert profile["total_concepts"] == 0
        assert profile["overall_score"] == 0.0
    
    def test_generate_profile_with_states(self, group_manager):
        """有状态数据时生成画像"""
        # 创建几个状态
        for i in range(3):
            state = UserKnowledgeState(
                state_id=f"user_001#test_transformer#concept_{i}",
                user_id="user_001",
                subject_id="test_transformer",
                canonical_id=f"concept_{i}",
                canonical_name=f"概念{i}",
                mastery_level=0.3 + i * 0.3,
            )
            group_manager._save_user_state(state)
        
        profile = group_manager._generate_profile("user_001", "test_transformer")
        
        assert profile["total_concepts"] == 3
        assert profile["overall_score"] > 0
        assert len(profile["weak_concepts"]) > 0
        assert "mastery_distribution" in profile

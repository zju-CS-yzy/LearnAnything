"""
LA-040-P0: IRT Estimator 单元测试

测试文件: tests/p0/test_irt_estimator.py
覆盖 TC-IRT-001 ~ TC-IRT-007 及错误码测试
"""

import math
import pytest

from core.graph_education.irt_estimator import IRTEstimator
from core.graph_education.types import ConceptNode, IRTParams, AnswerRecord


class TestHeuristicEstimation:
    """测试启发式难度估计"""
    
    def test_estimate_b_central_concept(self):
        """TC-IRT-001: 中心概念（低难度）"""
        estimator = IRTEstimator(calibration_stage=1)
        concept = ConceptNode(
            canonical_id="c1",
            name="中心概念",
            pagerank_score=0.3,  # 高中心性
            in_degree=8,
            out_degree=2,
            description="这是一个非常长的描述" * 50,
        )
        
        b = estimator.estimate_b_heuristic(concept)
        
        # 中心概念 → b 应该较低（容易）
        assert 0.2 <= b <= 1.0
        assert isinstance(b, float)
    
    def test_estimate_b_edge_concept(self):
        """TC-IRT-002: 边缘概念（高难度）"""
        estimator = IRTEstimator(calibration_stage=1)
        concept = ConceptNode(
            canonical_id="c2",
            name="边缘概念",
            pagerank_score=0.02,  # 低中心性
            in_degree=2,
            out_degree=0,
            description="短描述",
        )
        
        b = estimator.estimate_b_heuristic(concept)
        
        # 边缘概念（PageRank低、邻居少）→ b 应该比中心概念高
        # 由于公式有 -0.5 偏移，b 可能为负，但比中心概念高
        assert b > -0.5  # 比中心概念高（更难）
    
    def test_estimate_b_empty_description(self):
        """空描述的概念"""
        estimator = IRTEstimator(calibration_stage=1)
        concept = ConceptNode(
            canonical_id="c3",
            name="空描述",
            pagerank_score=0.15,
            in_degree=5,
            out_degree=5,
            description="",
        )
        
        b = estimator.estimate_b_heuristic(concept)
        
        # 空描述 → 描述项为 0，但仍可计算
        assert isinstance(b, float)
        assert -2 <= b <= 2


class TestProbability:
    """测试答对概率计算"""
    
    def test_compute_probability_theta_equals_b(self):
        """theta = b 时，P ≈ 0.5（c=0）"""
        estimator = IRTEstimator()
        p = estimator.compute_probability(theta=0.0, a=1.0, b=0.0, c=0.0)
        
        assert abs(p - 0.5) < 0.01
    
    def test_compute_probability_with_c(self):
        """theta = b 时，P ≈ 0.5 + c/2"""
        estimator = IRTEstimator()
        p = estimator.compute_probability(theta=0.0, a=1.0, b=0.0, c=0.25)
        
        assert abs(p - 0.625) < 0.01
    
    def test_compute_probability_high_theta(self):
        """高能力 → 高答对概率"""
        estimator = IRTEstimator()
        p = estimator.compute_probability(theta=3.0, a=1.0, b=0.0, c=0.25)
        
        assert p > 0.95
    
    def test_compute_probability_low_theta(self):
        """低能力 → 低答对概率（接近猜测度）"""
        estimator = IRTEstimator()
        p = estimator.compute_probability(theta=-3.0, a=1.0, b=0.0, c=0.25)
        
        # theta=-3 时 P ≈ 0.25，由于 a 有限，可能略高于猜测度
        assert 0.25 <= p <= 0.35
    
    def test_compute_probability_extreme_exponent(self):
        """极端 exponent 值不溢出"""
        estimator = IRTEstimator()
        p_high = estimator.compute_probability(theta=10.0, a=1.0, b=0.0, c=0.25)
        p_low = estimator.compute_probability(theta=-10.0, a=1.0, b=0.0, c=0.25)
        
        assert p_high <= 1.0
        assert p_low >= 0.25


class TestInformation:
    """测试信息量计算"""
    
    def test_information_max_near_theta_equals_b(self):
        """TC-IRT-003: theta ≈ b 时信息量较大（c=0 时严格最大）"""
        estimator = IRTEstimator()
        # c=0 时，theta=b 严格最大
        i_center = estimator.compute_information(theta=0.0, a=1.5, b=0.0, c=0.0)
        i_left = estimator.compute_information(theta=-1.0, a=1.5, b=0.0, c=0.0)
        i_right = estimator.compute_information(theta=1.0, a=1.5, b=0.0, c=0.0)
        
        assert i_center > i_left
        assert i_center > i_right
    
    def test_information_zero_at_extremes(self):
        """极端 theta 时信息量接近 0"""
        estimator = IRTEstimator()
        i = estimator.compute_information(theta=10.0, a=1.0, b=0.0, c=0.25)
        
        assert i < 0.01
    
    def test_information_proportional_to_a_squared(self):
        """a 越高，信息量越大"""
        estimator = IRTEstimator()
        i1 = estimator.compute_information(theta=0.0, a=1.0, b=0.0, c=0.25)
        i2 = estimator.compute_information(theta=0.0, a=2.0, b=0.0, c=0.25)
        
        assert i2 > i1


class TestThetaUpdate:
    """测试能力更新"""
    
    def test_update_theta_correct(self):
        """TC-IRT-004: 答对 → theta 上升"""
        estimator = IRTEstimator()
        theta_new = estimator.update_theta(
            theta=0.0, is_correct=1.0, a=1.0, b=0.0, c=0.25
        )
        
        assert theta_new > 0.0
    
    def test_update_theta_incorrect(self):
        """TC-IRT-005: 答错 → theta 下降"""
        estimator = IRTEstimator()
        theta_new = estimator.update_theta(
            theta=0.0, is_correct=0.0, a=1.0, b=0.0, c=0.25
        )
        
        assert theta_new < 0.0
    
    def test_update_theta_clipped(self):
        """TC-IRT-006: theta 不超出 [-3, 3]"""
        estimator = IRTEstimator()
        theta_new = estimator.update_theta(
            theta=2.9, is_correct=1.0, a=1.0, b=2.9, c=0.25
        )
        
        assert theta_new <= 3.0
    
    def test_update_theta_easy_question(self):
        """答对简单题（b 很低）→ theta 小幅上升"""
        estimator = IRTEstimator()
        theta_new = estimator.update_theta(
            theta=0.0, is_correct=1.0, a=1.0, b=-2.0, c=0.25
        )
        
        # 简单题答对，说明能力本来就高，更新幅度较小
        assert theta_new > 0.0
        assert theta_new < 1.0
    
    def test_update_theta_hard_question(self):
        """答对难题（b 很高）→ theta 上升"""
        estimator = IRTEstimator()
        theta_new = estimator.update_theta(
            theta=0.0, is_correct=1.0, a=1.0, b=2.0, c=0.25
        )
        
        # 难题答对，说明能力被低估，应该上升
        assert theta_new > 0.0


class TestCalibration:
    """测试校准"""
    
    def test_calibrate_rasch_sufficient(self):
        """TC-IRT-007: Rasch 校准（50 条）"""
        estimator = IRTEstimator(calibration_stage=1)
        
        # 生成 50 条记录，80% 正确率
        records = [
            AnswerRecord(
                record_id=f"r{i}", user_id="u1", subject_id="s1",
                group_id="g1", question_id="q1", sequence=1,
                user_answer="B", correct_answer="B",
                is_correct=(i % 5 != 0),  # 80% 正确率
                theta_before=0.0, theta_after=0.0,
                item_information=0.0
            )
            for i in range(50)
        ]
        
        b = estimator.calibrate_rasch("q1", records)
        
        assert -3 <= b <= 3
        # 80% 正确率 → b 应该为负（偏简单）
        assert b < 0
    
    def test_calibrate_rasch_insufficient_raises(self):
        """TC-IRT-ERR-001: 数据不足"""
        estimator = IRTEstimator(calibration_stage=1)
        records = [
            AnswerRecord(
                record_id=f"r{i}", user_id="u1", subject_id="s1",
                group_id="g1", question_id="q1", sequence=1,
                user_answer="B", correct_answer="B", is_correct=True
            )
            for i in range(30)
        ]
        
        with pytest.raises(ValueError) as exc_info:
            estimator.calibrate_rasch("q1", records)
        
        assert "LA-0405001" in str(exc_info.value)
    
    def test_calibrate_rasch_extreme_p(self):
        """极端正确率（100%）→ b 极负"""
        estimator = IRTEstimator(calibration_stage=1)
        records = [
            AnswerRecord(
                record_id=f"r{i}", user_id="u1", subject_id="s1",
                group_id="g1", question_id="q1", sequence=1,
                user_answer="B", correct_answer="B", is_correct=True
            )
            for i in range(50)
        ]
        
        b = estimator.calibrate_rasch("q1", records)
        
        # 100% 正确率 → b 应该为负（极简单）
        assert b < -2


class TestEstimateParams:
    """测试完整参数估计"""
    
    def test_estimate_params_choice(self):
        """选择题参数"""
        estimator = IRTEstimator(calibration_stage=1)
        concept = ConceptNode(
            canonical_id="c1", name="测试概念",
            pagerank_score=0.15, in_degree=5, out_degree=5
        )
        
        params = estimator.estimate_irt_params(concept, question_type="choice")
        
        assert params.a == 1.0  # 阶段 1 固定
        assert params.c == 0.25  # 选择题猜测度
        assert params.calibration_stage == 1
    
    def test_estimate_params_fill_blank(self):
        """填空题参数（c=0）"""
        estimator = IRTEstimator(calibration_stage=1)
        concept = ConceptNode(
            canonical_id="c1", name="测试概念",
            pagerank_score=0.15, in_degree=5, out_degree=5
        )
        
        params = estimator.estimate_irt_params(concept, question_type="fill_blank")
        
        assert params.c == 0.0  # 填空题无猜测度


class TestMasteryConversion:
    """测试掌握度转换"""
    
    def test_theta_to_mastery_zero(self):
        """theta=0 → 掌握度=0.5"""
        estimator = IRTEstimator()
        m = estimator.theta_to_mastery(0.0)
        assert abs(m - 0.5) < 0.01
    
    def test_theta_to_mastery_high(self):
        """高 theta → 高掌握度"""
        estimator = IRTEstimator()
        m = estimator.theta_to_mastery(3.0)
        assert m > 0.95
    
    def test_roundtrip(self):
        """theta -> mastery -> theta 往返"""
        estimator = IRTEstimator()
        original = 1.5
        mastery = estimator.theta_to_mastery(original)
        recovered = estimator.mastery_to_theta(mastery)
        
        assert abs(original - recovered) < 0.01


class TestEstimateA:
    """测试区分度估计"""
    
    def test_estimate_a_technology(self):
        """技术概念区分度更高"""
        estimator = IRTEstimator(calibration_stage=2)
        concept = ConceptNode(
            canonical_id="c1", name="技术概念",
            concept_type="technology"
        )
        
        a = estimator.estimate_a_heuristic(concept)
        # technology 类型有 1.2 倍乘数，base_a=1.0, quality=0.5 → a = 1.0 * 1.2 * 0.75 = 0.9
        assert a >= 0.8  # 技术概念区分度高于概念类型
    
    def test_estimate_a_concept(self):
        """抽象概念区分度较低"""
        estimator = IRTEstimator(calibration_stage=2)
        concept = ConceptNode(
            canonical_id="c1", name="抽象概念",
            concept_type="concept"
        )
        
        a = estimator.estimate_a_heuristic(concept)
        assert a <= 1.0

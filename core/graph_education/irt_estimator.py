"""
LA-040-P0: IRT Estimator（IRT 估计器）

分阶段实现：
- 阶段 1（Rasch）：固定 a=1.0, c=0.25，启发式 b → 积累数据后校准 b
- 阶段 2（2PL）：校准 a 和 b
- 阶段 3（3PL）：校准 a, b, c（长期运营）
"""

import math
from typing import List, Optional, Tuple, Dict

from core.graph_education.types import IRTParams, ConceptNode, AnswerRecord


class IRTEstimator:
    """
    IRT 参数估计器：分阶段从启发式到数据驱动
    
    使用说明：
    1. 阶段 1（冷启动）：使用启发式 b，固定 a=1.0, c=0.25
    2. 阶段 2（数据积累 ≥100 条）：校准 a 和 b
    3. 阶段 3（数据积累 ≥200 条）：校准 a, b, c
    """
    
    # 能力更新学习率
    LEARNING_RATE = 0.3
    
    # 能力值边界（logit 尺度）
    THETA_MIN = -3.0
    THETA_MAX = 3.0
    
    def __init__(self, calibration_stage: int = 1):
        """
        Args:
            calibration_stage: 1=Rasch, 2=2PL, 3=3PL
        """
        self.calibration_stage = calibration_stage
    
    # ───────────────────────────────────────────────
    # 阶段 1: 启发式难度估计
    # ───────────────────────────────────────────────
    
    def estimate_b_heuristic(self, concept: ConceptNode) -> float:
        """
        阶段 1: 启发式难度估计
        
        公式:
            b = 0.3 * (1 - centrality) 
                + 0.3 * min(neighbors/10, 1)
                + 0.2 * min(description_len/500, 1)
                + 0.2 * historical_difficulty
        
        解释：
        - 中心性越低（边缘概念）→ b 越高（越难）
        - 邻居越多（关联复杂）→ b 越高
        - 描述越长（内容复杂）→ b 越高
        - 历史难度（若有数据）→ b 加权
        
        Args:
            concept: 概念节点
            
        Returns:
            float: 难度参数 b（范围大致 -1.5 ~ 2.0）
        """
        # 1. 图中心性（PageRank 越高 = 越基础 = 越容易 = b 越低）
        centrality_term = 0.3 * (1 - concept.pagerank_score)
        
        # 2. 邻居数量（关联越多 = 越复杂 = 越难）
        neighbor_count = concept.in_degree + concept.out_degree
        neighbor_term = 0.3 * min(neighbor_count / 10, 1.0)
        
        # 3. 描述复杂度（描述越长 = 内容越复杂）
        desc_len = len(concept.description) if concept.description else 0
        desc_term = 0.2 * min(desc_len / 500, 1.0)
        
        # 4. 历史难度（P0 阶段无历史数据，默认 0.5）
        historical_term = 0.2 * 0.5
        
        b = centrality_term + neighbor_term + desc_term + historical_term
        
        # 缩放到合理范围（-1.0 ~ 2.0）
        return round(b - 0.5, 2)  # 减去偏移，使中心概念 b≈0
    
    def estimate_a_heuristic(self, concept: ConceptNode, distractor_quality: float = 0.5) -> float:
        """
        阶段 2: 基于干扰项质量估计区分度
        
        a 越高 = 题目区分能力越强
        
        Args:
            concept: 概念节点
            distractor_quality: 干扰项质量（0-1，越高越好）
            
        Returns:
            float: 区分度参数 a
        """
        # 基础区分度
        base_a = 1.0
        
        # 概念类型调整：
        # - 技术概念（technology）通常有更明确的边界 → 区分度更高
        # - 抽象概念（concept）边界模糊 → 区分度较低
        type_multiplier = {
            "technology": 1.2,
            "sub_technology": 1.1,
            "requirement": 1.0,
            "sub_requirement": 0.9,
            "concept": 0.9,
        }.get(concept.concept_type, 1.0)
        
        # 干扰项质量调整
        a = base_a * type_multiplier * (0.5 + 0.5 * distractor_quality)
        
        return round(min(a, 3.0), 2)
    
    # ───────────────────────────────────────────────
    # 阶段 2/3: 数据驱动的校准
    # ───────────────────────────────────────────────
    
    def calibrate_rasch(self, question_id: str, records: List[AnswerRecord]) -> float:
        """
        阶段 1 校准: 固定 a=1.0, c=0.25，仅估计 b
        
        使用简化版最大似然估计（MLE）：
        b = log(正确率 / 错误率) 的加权平均
        
        Args:
            question_id: 题目 ID
            records: 该题目的答题记录（≥50 条）
            
        Returns:
            float: 校准后的 b 参数
            
        Raises:
            ValueError: 数据不足（<50 条）
        """
        if len(records) < 50:
            raise ValueError(
                f"LA-0405001: Rasch 校准需要至少 50 条记录，"
                f"当前只有 {len(records)} 条"
            )
        
        # 简化 MLE：根据答题正确率反推 b
        correct_count = sum(1 for r in records if r.is_correct)
        total = len(records)
        
        # 避免极端值
        p = max(0.01, min(0.99, correct_count / total))
        
        # 反推 b：假设平均能力 θ=0
        # P(θ=0) = 1/(1+exp(b)) → b = -log(P/(1-P))
        # 注意：正确率高 → b 为负（题简单）
        b = -math.log(p / (1 - p))
        
        return round(b, 2)
    
    def calibrate_2pl(self, question_id: str, records: List[AnswerRecord]) -> Tuple[float, float]:
        """
        阶段 2 校准: 估计 a 和 b
        
        使用矩估计法（简化版）：
        - a = 1.7 / (P_75% - P_25%)
        - b = θ 中位数
        
        Args:
            question_id: 题目 ID
            records: 该题目的答题记录（≥100 条）
            
        Returns:
            Tuple[float, float]: (a, b)
        """
        if len(records) < 100:
            raise ValueError(
                f"LA-0405001: 2PL 校准需要至少 100 条记录，"
                f"当前只有 {len(records)} 条"
            )
        
        # 收集答题前的能力估计 θ
        thetas = [r.theta_before for r in records if r.theta_before is not None]
        
        if not thetas:
            # 无能力数据，回退到 Rasch
            b = self.calibrate_rasch(question_id, records)
            return 1.0, b
        
        # 按 θ 排序，计算正确率
        sorted_records = sorted(records, key=lambda r: r.theta_before or 0)
        n = len(sorted_records)
        
        # 分位数计算
        q25 = n // 4
        q75 = 3 * n // 4
        
        p25 = sum(1 for r in sorted_records[:q25] if r.is_correct) / max(q25, 1)
        p75 = sum(1 for r in sorted_records[q75:] if r.is_correct) / max(n - q75, 1)
        
        # 避免极端值
        p25 = max(0.01, min(0.99, p25))
        p75 = max(0.01, min(0.99, p75))
        
        # 估计 a 和 b
        theta_25 = sorted_records[q25].theta_before if q25 < n else 0
        theta_75 = sorted_records[q75].theta_before if q75 < n else 0
        
        # a = (logit(p75) - logit(p25)) / (θ75 - θ25)
        logit_diff = math.log(p75 / (1 - p75)) - math.log(p25 / (1 - p25))
        theta_diff = theta_75 - theta_25
        
        if abs(theta_diff) > 0.1:
            a = logit_diff / theta_diff
        else:
            a = 1.0
        
        a = max(0.3, min(a, 3.0))  # 约束在合理范围
        
        # b = θ_median - logit(p_median)/a
        median_idx = n // 2
        p_median = sum(1 for r in sorted_records[:median_idx+1] if r.is_correct) / (median_idx + 1)
        p_median = max(0.01, min(0.99, p_median))
        theta_median = sorted_records[median_idx].theta_before if median_idx < n else 0
        b = theta_median - math.log(p_median / (1 - p_median)) / a
        
        return round(a, 2), round(b, 2)
    
    # ───────────────────────────────────────────────
    # 核心 IRT 计算
    # ───────────────────────────────────────────────
    
    def compute_probability(self, theta: float, a: float, b: float, c: float) -> float:
        """
        计算答对概率 P(θ)
        
        3PL 模型: P(θ) = c + (1-c) / (1 + exp(-a(θ - b)))
        
        Args:
            theta: 考生能力（logit 尺度）
            a: 区分度
            b: 难度
            c: 猜测度
            
        Returns:
            float: 答对概率（0-1）
        """
        # 避免数值溢出
        exponent = -a * (theta - b)
        if exponent > 700:
            return c + (1 - c) * 0.0  # exp(700) 溢出，分母→∞，分数→0
        if exponent < -700:
            return c + (1 - c) * 1.0  # exp(-700)→0，分母→1，分数→1
        
        return c + (1 - c) / (1 + math.exp(exponent))
    
    def compute_information(self, theta: float, a: float, b: float, c: float) -> float:
        """
        计算题目信息量 I(θ)
        
        I(θ) = a² × P(θ) × (1-P(θ)) / (1-c)²
        
        信息量越大 = 该题对当前能力水平的考生测量越精准
        
        Args:
            theta: 考生能力
            a: 区分度
            b: 难度
            c: 猜测度
            
        Returns:
            float: 信息量（非负）
        """
        p = self.compute_probability(theta, a, b, c)
        
        # 避免除以 0
        if c >= 1.0:
            return 0.0
        
        info = (a ** 2) * p * (1 - p) / ((1 - c) ** 2)
        return round(info, 4)
    
    def update_theta(self, theta: float, is_correct: bool, 
                     a: float, b: float, c: float,
                     learning_rate: Optional[float] = None) -> float:
        """
        更新能力估计（简化 Elo 式更新）
        
        θ_new = θ_old + lr × (is_correct - P(θ_old))
        
        Args:
            theta: 当前能力估计
            is_correct: 是否答对（1.0 或 0.0）
            a: 题目区分度
            b: 题目难度
            c: 猜测度
            learning_rate: 学习率（默认 0.3）
            
        Returns:
            float: 更新后的能力估计
        """
        lr = learning_rate or self.LEARNING_RATE
        
        p = self.compute_probability(theta, a, b, c)
        
        # 更新
        theta_new = theta + lr * (is_correct - p)
        
        # 裁剪到合理范围
        return round(max(self.THETA_MIN, min(self.THETA_MAX, theta_new)), 2)
    
    def estimate_irt_params(self, concept: ConceptNode, question_type: str = "choice") -> IRTParams:
        """
        为概念估计 IRT 参数（P0 入口）
        
        Args:
            concept: 概念节点
            question_type: 题型（choice/fill_blank/essay）
            
        Returns:
            IRTParams: 完整的 IRT 参数
        """
        # 启发式 b
        b = self.estimate_b_heuristic(concept)
        
        # 启发式 a（阶段 1 固定为 1.0）
        a = 1.0 if self.calibration_stage == 1 else self.estimate_a_heuristic(concept)
        
        # c：选择题固定 0.25，填空/问答题 0.0
        c = 0.25 if question_type == "choice" else 0.0
        
        return IRTParams(
            a=a,
            b=b,
            c=c,
            calibration_stage=self.calibration_stage,
            calibration_samples=0
        )
    
    # ───────────────────────────────────────────────
    # 辅助方法
    # ───────────────────────────────────────────────
    
    def sigmoid(self, x: float) -> float:
        """Sigmoid 函数，将 θ 映射到 0-1"""
        if x > 700:
            return 1.0
        if x < -700:
            return 0.0
        return 1 / (1 + math.exp(-x))
    
    def theta_to_mastery(self, theta: float) -> float:
        """将能力值 θ 映射到掌握度 0-1"""
        return self.sigmoid(theta)
    
    def mastery_to_theta(self, mastery: float) -> float:
        """将掌握度映射到能力值 θ"""
        # 避免 log(0)
        mastery = max(0.01, min(0.99, mastery))
        return math.log(mastery / (1 - mastery))

"""
LA-040-P0: Group Manager（题目组管理器）

按组选题的生命周期管理：
生成 → 答题 → 提交 → 评分 → 画像更新
"""

import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from core.graph_education.types import (
    QuestionGroup, GroupStatus, Question, AnswerRecord, UserKnowledgeState,
    ExamTemplate, BUILTIN_TEMPLATES, QuestionPattern, ContextBudget
)
from core.graph_education.concept_retriever import ConceptRetriever
from core.graph_education.subgraph_builder import SubgraphBuilder
from core.graph_education.context_assembler import ContextAssembler
from core.graph_education.irt_estimator import IRTEstimator


class GroupManager:
    """
    题目组管理器：按组选题的生命周期管理
    
    状态机：
        GENERATED → IN_PROGRESS → SUBMITTED → GRADED
    
    核心功能：
    1. 生成题目组（基于模板 + 目标概念）
    2. 管理答题过程（前端缓存，不触发实时计算）
    3. 提交整组（触发后台批量处理）
    4. 批量评分 + IRT 更新 + 知识传播 + 画像生成
    """
    
    def __init__(
        self,
        retriever: ConceptRetriever,
        builder: SubgraphBuilder,
        assembler: ContextAssembler,
        irt: IRTEstimator,
        db=None,  # SQLite 数据库连接
        cache=None
    ):
        self.retriever = retriever
        self.builder = builder
        self.assembler = assembler
        self.irt = irt
        self.db = db
        self.cache = cache
    
    # ───────────────────────────────────────────────
    # 1. 生成题目组
    # ───────────────────────────────────────────────
    
    def create_group(
        self,
        user_id: str,
        subject_id: str,
        template_id: str = "quick_practice",
        target_concepts: Optional[List[str]] = None,
        count: Optional[int] = None
    ) -> QuestionGroup:
        """
        生成新题目组
        
        流程：
        1. 加载模板
        2. 概念检索（解析目标概念 / 自动选择薄弱概念）
        3. 子图构建
        4. 按模板生成每道题
        5. 估计 IRT 参数
        6. 组装溯源信息
        
        Args:
            user_id: 用户 ID
            subject_id: 学科 ID
            template_id: 试卷模板 ID（默认 quick_practice）
            target_concepts: 目标概念名称列表（可选）
            count: 覆盖模板数量（可选）
            
        Returns:
            QuestionGroup: 生成的题目组
        """
        # 加载模板
        template = BUILTIN_TEMPLATES.get(template_id)
        if not template:
            raise ValueError(f"LA-0406001: 模板不存在: {template_id}")
        
        # 概念检索
        if target_concepts:
            seed_concepts = self.retriever.resolve(target_concepts, subject_id)
        else:
            # 自动选择薄弱概念
            seed_concepts = self.retriever.select_weak_concepts(
                user_id=user_id, subject_id=subject_id, n=3
            )
        
        # 扩展相关概念
        related = self.retriever.expand(seed_concepts, hop=1, max_nodes=20)
        
        # 创建题目组
        group = QuestionGroup(
            group_id=f"qg_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            subject_id=subject_id,
            template_id=template_id,
            status=GroupStatus.GENERATED,
            target_concepts=[c.canonical_id for c in seed_concepts],
        )
        
        # 按模板生成题目
        for pattern in template.question_patterns:
            for i in range(pattern.count):
                # 选择目标概念（考虑覆盖度，避免重复）
                target = self._select_target_concept(seed_concepts, group.questions, pattern)
                if not target:
                    break
                
                # 构建题型专用子图
                question_subgraph = self.builder.build_for_pattern(target, pattern)
                
                # 组装上下文
                context = self.assembler.assemble(
                    subgraph=question_subgraph,
                    budget=pattern.context_budget,
                    include_prerequisites=pattern.require_concept_chain,
                    target_concept=target
                )
                
                # 估计 IRT 参数
                irt_params = self.irt.estimate_irt_params(
                    target, question_type=pattern.pattern_id.split("_")[0]
                )
                
                # 构建知识追踪
                knowledge_trace = self._build_knowledge_trace(
                    question_subgraph, target
                )
                
                # 创建题目（P0 阶段不调用 LLM，使用占位文本）
                question = Question(
                    question_id=f"q_{uuid.uuid4().hex[:12]}",
                    group_id=group.group_id,
                    sequence=len(group.questions) + 1,
                    question_type=pattern.pattern_id,
                    question_text=f"关于 {target.name} 的题目（待 LLM 生成）",
                    options={"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
                    correct_answer="B",
                    explanation=f"{target.name} 的正确理解是...",
                    knowledge_trace=knowledge_trace,
                    irt_params=irt_params,
                )
                
                group.questions.append(question)
        
        # 存储题目组
        self._save_group(group)
        
        return group
    
    def start_group(self, group_id: str) -> QuestionGroup:
        """
        用户开始答题，状态变为 IN_PROGRESS
        
        Args:
            group_id: 题目组 ID
            
        Returns:
            QuestionGroup: 更新后的题目组
        """
        group = self._load_group(group_id)
        if group.status != GroupStatus.GENERATED:
            raise ValueError(
                f"LA-0406002: 题目组状态冲突，当前状态: {group.status.value}"
            )
        
        group.status = GroupStatus.IN_PROGRESS
        self._save_group(group)
        
        return group
    
    # ───────────────────────────────────────────────
    # 2. 提交与评分
    # ───────────────────────────────────────────────
    
    def submit_group(
        self,
        group_id: str,
        answers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        提交整组答案，触发后台处理
        
        流程：
        1. 验证题目组状态
        2. 即时评分（前端已完成，这里只做验证）
        3. 创建答题记录
        4. 批量 IRT 更新
        5. 批量知识传播
        6. 生成能力画像
        
        Args:
            group_id: 题目组 ID
            answers: 答案列表 [{"question_id": "...", "user_answer": "...", "time_spent": 120}, ...]
            
        Returns:
            Dict: 评分结果（即时返回，后台异步完成画像更新）
        """
        group = self._load_group(group_id)
        if group.status in (GroupStatus.SUBMITTED, GroupStatus.GRADED):
            raise ValueError("LA-0406002: 题目组已提交，不可重复提交")
        
        if len(answers) != len(group.questions):
            raise ValueError(
                f"LA-0406003: 答案数量不匹配，"
                f"期望 {len(group.questions)}，实际 {len(answers)}"
            )
        
        group.status = GroupStatus.SUBMITTED
        group.submitted_at = datetime.now()
        
        # 创建答题记录
        records = []
        correct_count = 0
        
        for ans in answers:
            question = self._find_question(group, ans["question_id"])
            is_correct = (ans["user_answer"] == question.correct_answer)
            if is_correct:
                correct_count += 1
            
            record = AnswerRecord(
                record_id=f"ar_{uuid.uuid4().hex[:12]}",
                user_id=group.user_id,
                subject_id=group.subject_id,
                group_id=group_id,
                question_id=ans["question_id"],
                sequence=question.sequence,
                user_answer=ans["user_answer"],
                correct_answer=question.correct_answer,
                is_correct=is_correct,
                time_spent=ans.get("time_spent", 0),
                answered_at=datetime.now(),
                primary_concepts=question.knowledge_trace.primary_concepts,
                theta_before=0.0,  # 从缓存读取用户当前 θ
            )
            records.append(record)
        
        # 批量处理
        self._process_group_submission(group, records)
        
        # 返回即时结果
        score = correct_count / len(group.questions) if group.questions else 0
        
        return {
            "group_id": group_id,
            "score": round(score, 2),
            "correct_count": correct_count,
            "total": len(group.questions),
            "status": "grading",
            "message": "评分中，请稍后查看能力画像"
        }
    
    def get_group_result(self, group_id: str) -> Dict[str, Any]:
        """
        获取题目组的完整结果
        
        Args:
            group_id: 题目组 ID
            
        Returns:
            Dict: 完整评分结果和能力画像
        """
        group = self._load_group(group_id)
        
        if group.status != GroupStatus.GRADED:
            return {
                "group_id": group_id,
                "status": group.status.value,
                "message": "评分尚未完成"
            }
        
        # 加载能力画像
        profile = self._load_profile(group.user_id, group.subject_id)
        
        return {
            "group_id": group_id,
            "status": "graded",
            "score": profile.get("overall_score", 0),
            "weak_concepts": profile.get("weak_concepts", []),
            "recommended_next": profile.get("recommended_next", []),
            "mastery_distribution": profile.get("mastery_distribution", {}),
        }
    
    # ───────────────────────────────────────────────
    # 3. 后台批量处理
    # ───────────────────────────────────────────────
    
    def _process_group_submission(
        self,
        group: QuestionGroup,
        records: List[AnswerRecord]
    ) -> None:
        """
        后台批量处理整组提交
        
        流程：
        1. 保存答题记录
        2. 批量 IRT 更新（能力估计）
        3. 批量知识传播（沿图）
        4. 检查 IRT 校准条件
        5. 生成能力画像
        """
        # 1. 保存记录
        self._save_records(records)
        
        # 2. 批量更新用户知识状态（IRT 更新）
        updated_states = []
        for record in records:
            states = self._update_knowledge_state(record)
            updated_states.extend(states)
        
        # 3. 批量图传播
        for record in records:
            self._propagate_knowledge(record)
        
        # 4. 检查 IRT 校准条件
        for record in records:
            self._check_calibration(record.question_id)
        
        # 5. 生成能力画像
        profile = self._generate_profile(group.user_id, group.subject_id)
        self._save_profile(group.user_id, group.subject_id, profile)
        
        # 更新组状态
        group.status = GroupStatus.GRADED
        group.graded_at = datetime.now()
        self._save_group(group)
    
    def _update_knowledge_state(
        self,
        record: AnswerRecord
    ) -> List[UserKnowledgeState]:
        """
        更新用户知识状态（IRT 更新）
        
        对每个关联概念：
        1. 获取当前状态
        2. IRT 能力更新
        3. 更新统计信息
        """
        updated = []
        
        for concept_id in record.primary_concepts:
            state = self._load_user_state(
                record.user_id, record.subject_id, concept_id
            )
            
            if state is None:
                state = UserKnowledgeState(
                    state_id=f"{record.user_id}#{record.subject_id}#{concept_id}",
                    user_id=record.user_id,
                    subject_id=record.subject_id,
                    canonical_id=concept_id,
                )
            
            # IRT 能力更新（简化版：假设所有题 a=1.0, c=0.25）
            # P0 阶段使用固定 b=0（未校准），后续可从题目加载
            p = self.irt.compute_probability(
                state.theta, a=1.0, b=0.0, c=0.25
            )
            
            is_correct_float = 1.0 if record.is_correct else 0.0
            state.theta = state.theta + 0.3 * (is_correct_float - p)
            state.theta = max(-3.0, min(3.0, state.theta))
            
            # 更新统计
            state.test_count += 1
            if record.is_correct:
                state.correct_count += 1
                state.streak = state.streak + 1 if state.streak >= 0 else 1
            else:
                state.streak = state.streak - 1 if state.streak <= 0 else -1
            
            # 掌握度映射
            state.mastery_level = self.irt.theta_to_mastery(state.theta)
            state.confidence = min(1.0, state.test_count / 10)
            state.last_tested = datetime.now()
            state.source_of_latest_update = record.group_id
            
            self._save_user_state(state)
            updated.append(state)
        
        return updated
    
    def _propagate_knowledge(self, record: AnswerRecord) -> None:
        """
        沿图传播知识更新
        
        - 答对：前置知识掌握度 +0.05
        - 答错：应用概念置信度 × 0.9
        """
        if record.is_correct:
            # 沿 DEPENDS_ON 反向传播（前置知识 +0.05）
            for concept_id in record.primary_concepts:
                prerequisites = self._get_predecessors(concept_id, "DEPENDS_ON")
                for prereq_id in prerequisites:
                    state = self._load_or_create_state(
                        record.user_id, record.subject_id, prereq_id
                    )
                    state.mastery_level = min(1.0, state.mastery_level + 0.05)
                    self._save_user_state(state)
        else:
            # 沿 SOLUTION 正向传播（应用概念置信度 × 0.9）
            for concept_id in record.primary_concepts:
                applications = self._get_successors(concept_id, "SOLUTION")
                for app_id in applications:
                    state = self._load_or_create_state(
                        record.user_id, record.subject_id, app_id
                    )
                    state.confidence *= 0.9
                    self._save_user_state(state)
    
    def _check_calibration(self, question_id: str) -> None:
        """检查题目是否达到 IRT 校准条件"""
        records = self._load_records_for_question(question_id)
        
        if len(records) >= 50:
            # 异步触发校准
            # P0 阶段简化：直接记录待校准队列
            pass
    
    def _generate_profile(
        self,
        user_id: str,
        subject_id: str
    ) -> Dict[str, Any]:
        """
        生成能力画像
        
        Returns:
            Dict: {
                "overall_score": float,
                "total_concepts": int,
                "mastered_concepts": int,
                "weak_concepts": List[Dict],
                "mastery_distribution": Dict[str, int],
                "recommended_next": List[str],
            }
        """
        states = self._load_all_user_states(user_id, subject_id)
        
        total = len(states)
        mastered = sum(1 for s in states if s.mastery_level >= 0.7)
        
        # 薄弱概念（掌握度 < 0.5）
        weak = [
            {
                "concept_id": s.canonical_id,
                "concept_name": s.canonical_name,
                "mastery": round(s.mastery_level, 2),
                "test_count": s.test_count,
            }
            for s in states
            if s.mastery_level < 0.5
        ]
        weak.sort(key=lambda x: x["mastery"])
        
        # 掌握度分布
        distribution = {
            "excellent": sum(1 for s in states if s.mastery_level >= 0.8),
            "good": sum(1 for s in states if 0.6 <= s.mastery_level < 0.8),
            "fair": sum(1 for s in states if 0.4 <= s.mastery_level < 0.6),
            "weak": sum(1 for s in states if s.mastery_level < 0.4),
        }
        
        # 推荐下一组
        recommended = [w["concept_id"] for w in weak[:3]]
        
        # 总体得分
        overall = sum(s.mastery_level for s in states) / max(total, 1)
        
        return {
            "overall_score": round(overall, 2),
            "total_concepts": total,
            "mastered_concepts": mastered,
            "weak_concepts": weak[:5],
            "mastery_distribution": distribution,
            "recommended_next": recommended,
        }
    
    # ───────────────────────────────────────────────
    # 4. 辅助方法
    # ───────────────────────────────────────────────
    
    def _select_target_concept(
        self,
        seed_concepts: List[Any],
        existing_questions: List[Question],
        pattern: QuestionPattern
    ) -> Optional[Any]:
        """选择目标概念（考虑覆盖度，避免重复）"""
        used = set()
        for q in existing_questions:
            used.update(q.knowledge_trace.primary_concepts)
        
        # 优先选择未使用的概念
        for concept in seed_concepts:
            if concept.canonical_id not in used:
                return concept
        
        # 都用过则轮询
        if seed_concepts:
            idx = len(existing_questions) % len(seed_concepts)
            return seed_concepts[idx]
        
        return None
    
    def _build_knowledge_trace(self, subgraph: Any, target: Any) -> Any:
        """构建知识追踪信息"""
        from core.graph_education.types import KnowledgeTrace
        
        primary = [target.canonical_id]
        secondary = [
            n.canonical_id for n in subgraph.nodes
            if n.canonical_id != target.canonical_id
        ]
        
        return KnowledgeTrace(
            primary_concepts=primary,
            secondary_concepts=secondary[:5],
            difficulty_score=0.5,
            difficulty_label="中等"
        )
    
    # ───────────────────────────────────────────────
    # 5. 存储层（P0 简化实现，后续接入 SQLite/KùzuDB）
    # ───────────────────────────────────────────────
    
    def _save_group(self, group: QuestionGroup) -> None:
        """保存题目组"""
        if self.cache:
            self.cache.set(f"group:{group.group_id}", group)
    
    def _load_group(self, group_id: str) -> QuestionGroup:
        """加载题目组"""
        if self.cache:
            group = self.cache.get(f"group:{group_id}")
            if group:
                return group
        raise ValueError(f"LA-0406001: 题目组不存在: {group_id}")
    
    def _save_records(self, records: List[AnswerRecord]) -> None:
        """保存答题记录"""
        if self.cache:
            for r in records:
                self.cache.set(f"record:{r.record_id}", r)
    
    def _save_user_state(self, state: UserKnowledgeState) -> None:
        """保存用户知识状态"""
        if self.cache:
            self.cache.set(f"state:{state.state_id}", state)
    
    def _load_user_state(
        self, user_id: str, subject_id: str, concept_id: str
    ) -> Optional[UserKnowledgeState]:
        """加载用户知识状态"""
        state_id = f"{user_id}#{subject_id}#{concept_id}"
        if self.cache:
            return self.cache.get(f"state:{state_id}")
        return None
    
    def _load_or_create_state(
        self, user_id: str, subject_id: str, concept_id: str
    ) -> UserKnowledgeState:
        """加载或创建用户知识状态"""
        state = self._load_user_state(user_id, subject_id, concept_id)
        if state:
            return state
        
        return UserKnowledgeState(
            state_id=f"{user_id}#{subject_id}#{concept_id}",
            user_id=user_id,
            subject_id=subject_id,
            canonical_id=concept_id,
        )
    
    def _load_all_user_states(
        self, user_id: str, subject_id: str
    ) -> List[UserKnowledgeState]:
        """加载用户所有知识状态"""
        states = []
        if self.cache:
            # 简化：遍历缓存中的所有状态
            prefix = f"state:{user_id}#{subject_id}#"
            for key in list(self.cache._data.keys()):
                if key.startswith(prefix):
                    state = self.cache.get(key)
                    if state:
                        states.append(state)
        return states
    
    def _load_records_for_question(self, question_id: str) -> List[AnswerRecord]:
        """加载题目的所有答题记录"""
        records = []
        if self.cache:
            for key in list(self.cache._data.keys()):
                if key.startswith("record:"):
                    r = self.cache.get(key)
                    if r and r.question_id == question_id:
                        records.append(r)
        return records
    
    def _save_profile(
        self, user_id: str, subject_id: str, profile: Dict
    ) -> None:
        """保存能力画像"""
        if self.cache:
            self.cache.set(f"profile:{user_id}#{subject_id}", profile)
    
    def _load_profile(self, user_id: str, subject_id: str) -> Dict:
        """加载能力画像"""
        if self.cache:
            return self.cache.get(f"profile:{user_id}#{subject_id}", {})
        return {}
    
    def _get_predecessors(self, concept_id: str, edge_type: str) -> List[str]:
        """获取概念的前置概念（从 KùzuDB 查询）"""
        # P0 简化：直接返回空列表，后续接入图查询
        return []
    
    def _get_successors(self, concept_id: str, edge_type: str) -> List[str]:
        """获取概念的后继概念（从 KùzuDB 查询）"""
        # P0 简化：直接返回空列表，后续接入图查询
        return []
    
    def _find_question(self, group: QuestionGroup, question_id: str) -> Question:
        """在题目组中查找题目"""
        for q in group.questions:
            if q.question_id == question_id:
                return q
        raise ValueError(f"LA-0406003: 题目不存在: {question_id}")

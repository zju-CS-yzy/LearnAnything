#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoachAgent: 能力评测 Agent
调用 QuizAgent 出题 + 自动评分 + 生成报告

评分策略:
  - 客观题(单选/多选/判断/填空): 规则评分 — 精确匹配或关键词匹配
  - 主观题(简答/计算/编程/论述): LLM-as-judge — 多维度评分 + 反馈
"""

import re
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from agents.quiz_agent import QuizAgent
from agents.base_agent import BaseAgent
from core.subject_analyzer import SubjectAnalyzer
from core.llm_client import LLMClient
from core.graph_education import IRTEstimator, IRTParams, UserKnowledgeState, AnswerRecord, UserStateStore


# 每题默认满分（5题=100分）
DEFAULT_QUESTION_SCORE = 20


class CoachAgent(BaseAgent):
    """能力评测 Agent（支持动态学科配置 + 自动评分）"""

    @property
    def agent_name(self) -> str:
        return "CoachAgent"

    def __init__(self, collection_name: str = "learnanything_v1", subject: str = "generic", top_k: int = 5, message_bus=None):
        self.collection_name = collection_name
        self.subject = subject
        self.top_k = top_k
        self._quiz_agent = None
        self._llm_client = None
        self._irt_estimator = None
        self._state_store = None
        # P0-INT-6: 消息总线
        self._message_bus = message_bus
        # P0-INT-6: 待评测题目队列（从 QuizAgent 接收）
        self._pending_quizzes: List[Dict[str, Any]] = []

    def _get_subject_config(self) -> Dict[str, Any]:
        """加载动态学科配置"""
        config = SubjectAnalyzer.load_config(self.subject)
        if config is not None:
            return config
        return SubjectAnalyzer.get_generic_config()

    def _get_quiz_agent(self) -> QuizAgent:
        if self._quiz_agent is None:
            self._quiz_agent = QuizAgent(self.collection_name, subject=self.subject, top_k=self.top_k)
        return self._quiz_agent

    def _get_irt_estimator(self) -> IRTEstimator:
        """P0-INT-3: 延迟初始化 IRTEstimator"""
        if self._irt_estimator is None:
            print(f"[CoachAgent] P0-INT-3: 延迟初始化 IRTEstimator")
            self._irt_estimator = IRTEstimator(calibration_stage=1)
        return self._irt_estimator

    def _get_state_store(self) -> UserStateStore:
        """P0-INT-4: 延迟初始化 UserStateStore"""
        if self._state_store is None:
            print(f"[CoachAgent] P0-INT-4: 延迟初始化 UserStateStore")
            self._state_store = UserStateStore()
        return self._state_store

    def _save_user_states(self, user_id: str, subject_id: str, details: List[Dict], theta: float) -> None:
        """P0-INT-4: 保存用户知识状态到 SQLite"""
        try:
            store = self._get_state_store()
            now = datetime.now()
            for detail in details:
                topic = detail.get("topic", detail.get("question", "")[:20])
                if not topic:
                    continue
                canonical_id = topic  # 使用 topic 作为概念 ID（简化）
                state_id = f"{user_id}#{subject_id}#{canonical_id}"
                
                # 尝试加载已有状态
                existing = store.load(user_id, subject_id, canonical_id)
                if existing:
                    # 更新已有状态
                    existing.test_count += 1
                    if detail.get("is_correct"):
                        existing.correct_count += 1
                        existing.streak += 1
                    else:
                        existing.streak = 0
                    existing.theta = theta
                    existing.mastery_level = self._sigmoid(theta)
                    existing.confidence = min(1.0, existing.test_count / 10)
                    existing.last_tested = now
                    existing.updated_at = now
                    existing.source_of_latest_update = "coach_evaluate"
                    store.save(existing)
                else:
                    # 创建新状态
                    new_state = UserKnowledgeState(
                        state_id=state_id,
                        user_id=user_id,
                        subject_id=subject_id,
                        canonical_id=canonical_id,
                        canonical_name=topic,
                        mastery_level=self._sigmoid(theta),
                        confidence=0.1,
                        theta=theta,
                        test_count=1,
                        correct_count=1 if detail.get("is_correct") else 0,
                        streak=1 if detail.get("is_correct") else 0,
                        last_tested=now,
                        first_tested=now,
                        updated_at=now,
                        source_of_latest_update="coach_evaluate",
                    )
                    store.save(new_state)
            print(f"[CoachAgent] P0-INT-4: 已保存 {len(details)} 个用户知识状态")
        except Exception as e:
            print(f"[CoachAgent] P0-INT-4: 保存用户状态失败: {e}")

    def _sigmoid(self, x: float) -> float:
        """sigmoid 函数，将 theta 映射到 0-1"""
        import math
        return 1 / (1 + math.exp(-x))

    def _get_llm_client(self) -> Optional[LLMClient]:
        """延迟加载 LLM 客户端"""
        if self._llm_client is None:
            try:
                self._llm_client = LLMClient()
            except Exception as e:
                print(f"[CoachAgent] LLM client init failed: {e}")
                self._llm_client = None
        return self._llm_client

    def handle(self, query: str, n_questions: int = 5, filters: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """生成评测题目（原逻辑保留）"""
        topic = self._extract_topic(query)

        config = self._get_subject_config()
        subject_name = config.get("name", "当前学科")
        question_types = list(config.get("question_types", {}).keys())

        quiz_agent = self._get_quiz_agent()
        quiz_result = quiz_agent.handle(topic + " 评测题", n_questions=n_questions, filters=filters)

        instructions = f"""【能力评测】

本次评测包含 {n_questions} 道题目，涵盖「{topic}」相关知识。
学科领域：{subject_name}
涉及题型：{', '.join(question_types) if question_types else '单选题、简答题'}

答题说明：
1. 请按题目要求作答
2. 完成后提交答案，系统将自动评分
3. 答题时间建议不超过 {n_questions * 3} 分钟

请回答以下题目："""

        return {
            "text": instructions + "\n\n" + quiz_result.get("text", ""),
            "questions": quiz_result.get("questions", []),
            "topic": topic,
            "subject_config": {
                "subject": config.get("subject", "generic"),
                "name": subject_name,
                "question_types": question_types,
            },
        }

    def evaluate(self, questions: List[Dict[str, Any]], user_answers: List[str]) -> Dict[str, Any]:
        """
        自动评分入口。

        Args:
            questions: QuizAgent 生成的题目列表，每个题目包含 id, type, question, answer, explanation
            user_answers: 用户答案列表，顺序与 questions 对应

        Returns:
            评分报告，包含每题得分、总分、反馈、薄弱点分析
        """
        if not questions:
            return {"error": "没有题目可评分"}
        if len(user_answers) < len(questions):
            # 补齐未答题目
            user_answers = list(user_answers) + [""] * (len(questions) - len(user_answers))

        details = []
        total_score = 0
        max_score = 0
        correct_count = 0

        for q, ua in zip(questions, user_answers):
            qid = q.get("id", 0)
            qtype = q.get("type", "short_answer")
            correct = q.get("answer", "")
            score_per_q = DEFAULT_QUESTION_SCORE
            max_score += score_per_q

            # 按题型路由评分方法
            if qtype in ("single_choice", "multiple_choice", "true_false"):
                result = self._score_objective(q, ua, score_per_q)
            elif qtype == "fill_blank":
                result = self._score_fill_blank(q, ua, score_per_q)
            elif qtype in ("short_answer", "essay"):
                result = self._score_subjective_llm(q, ua, score_per_q)
            elif qtype == "calculation":
                result = self._score_calculation(q, ua, score_per_q)
            elif qtype == "coding":
                result = self._score_coding(q, ua, score_per_q)
            else:
                result = self._score_subjective_llm(q, ua, score_per_q)

            detail = {
                "id": qid,
                "type": qtype,
                "question": q.get("question", ""),
                "user_answer": ua,
                "correct_answer": correct,
                "score": result["score"],
                "max_score": score_per_q,
                "is_correct": result["is_correct"],
                "feedback": result["feedback"],
                "explanation": q.get("explanation", ""),
            }
            details.append(detail)
            total_score += result["score"]
            if result["is_correct"]:
                correct_count += 1

        # 生成总体报告
        percentage = round(total_score / max_score * 100, 1) if max_score > 0 else 0
        summary = self._generate_summary(details, percentage)

        report = {
            "total_score": total_score,
            "max_score": max_score,
            "percentage": percentage,
            "correct_count": correct_count,
            "total_questions": len(questions),
            "details": details,
            "summary": summary["text"],
            "weak_areas": summary["weak_areas"],
            "strong_areas": summary["strong_areas"],
            "level": summary["level"],
        }

        # 组装可读文本
        text_lines = [
            f"【评测结果】总分: {total_score}/{max_score} ({percentage}%)",
            f"等级: {summary['level']}",
            f"正确率: {correct_count}/{len(questions)}",
            "",
            "=" * 50,
            "",
        ]
        for d in details:
            status = "✅" if d["is_correct"] else "❌"
            text_lines.append(f"{status} 第{d['id']}题 ({d['type']}) — {d['score']}/{d['max_score']}分")
            text_lines.append(f"   你的答案: {d['user_answer']}")
            text_lines.append(f"   参考答案: {d['correct_answer']}")
            text_lines.append(f"   反馈: {d['feedback']}")
            text_lines.append("")

        text_lines.extend([
            "=" * 50,
            "",
            "📊 能力分析",
            summary["text"],
            "",
        ])
        if summary["weak_areas"]:
            text_lines.append(f"⚠️ 薄弱点: {', '.join(summary['weak_areas'])}")
        if summary["strong_areas"]:
            text_lines.append(f"💪 优势点: {', '.join(summary['strong_areas'])}")

        # P0-INT-3: IRT 能力估计
        try:
            irt = self._get_irt_estimator()
            print(f"[CoachAgent] P0-INT-3: 开始 IRT 能力估计")

            answer_records = []
            for detail in details:
                record = AnswerRecord(
                    question_id=str(detail["id"]),
                    user_answer=detail["user_answer"],
                    correct_answer=detail["correct_answer"],
                    is_correct=detail["is_correct"],
                    primary_concepts=[detail.get("topic", detail.get("question", "")[:20])],
                )
                answer_records.append(record)

            theta = 0.0
            for record in answer_records:
                theta = irt.update_theta(theta, record.is_correct, a=1.0, b=0.0, c=0.25)

            concept_difficulties = {}
            for detail in details:
                topic = detail.get("topic", detail.get("question", "")[:20])
                if topic:
                    concept_difficulties[topic] = irt.estimate_b_heuristic(
                        type('ConceptNode', (), {
                            'pagerank_score': 0.5,
                            'in_degree': 2, 'out_degree': 2,
                            'description': detail.get("question", ""),
                            'concept_type': 'concept'
                        })()
                    )

            print(f"[CoachAgent] IRT 能力估计: theta={theta:.2f}")

            report["irt"] = {
                "theta": round(theta, 2),
                "level": self._theta_to_level(theta),
                "concept_difficulties": concept_difficulties,
            }
            
            # P0-INT-4: 保存用户知识状态到 SQLite
            self._save_user_states("anonymous", self.subject, details, theta)
            
            # P0-INT-6: 发布 ability_updated 事件（通知 QuizAgent 调整难度）
            if self._message_bus:
                for detail in details:
                    topic = detail.get("topic", detail.get("question", "")[:20])
                    if topic:
                        self._message_bus.publish(
                            topic="user_state",
                            sender="CoachAgent",
                            event="ability_updated",
                            payload={
                                "theta": round(theta, 2),
                                "concept": topic,
                                "is_correct": detail.get("is_correct", False),
                                "score": detail.get("score", 0),
                            }
                        )
                
                # 检测薄弱点并发布 weak_area_detected
                weak_concepts = []
                for detail in details:
                    topic = detail.get("topic", detail.get("question", "")[:20])
                    if topic and not detail.get("is_correct", False):
                        weak_concepts.append(topic)
                
                # 统计每个概念的连续错误次数（简化：本次错误即发布）
                for concept in set(weak_concepts):
                    self._message_bus.publish(
                        topic="weak_area",
                        sender="CoachAgent",
                        event="weak_area_detected",
                        payload={
                            "concept": concept,
                            "streak_wrong": 1,
                            "theta": round(theta, 2),
                        }
                    )
        except Exception as e:
            print(f"[CoachAgent] IRT 估计失败: {e}")
            report["irt"] = {"error": str(e)}

        report["text"] = "\n".join(text_lines)
        return report

    def _theta_to_level(self, theta: float) -> str:
        """P0-INT-3: 将 IRT theta 转换为等级"""
        if theta < -1.5:
            return "入门"
        elif theta < -0.5:
            return "初级"
        elif theta < 0.5:
            return "中级"
        elif theta < 1.5:
            return "高级"
        return "专家"

    # ========== 评分子方法 ==========

    def _score_objective(self, question: Dict, user_answer: str, max_score: int) -> Dict[str, Any]:
        """客观题评分 — 精确匹配（支持多种格式输入）"""
        # 标准化正确答案：提取字母
        correct_raw = str(question.get("answer", "")).strip()
        # 如果正确答案是 "A. xxx" 格式，提取 "A"
        correct = re.sub(r'^[A-Fa-f][\.．、]\s*', '', correct_raw).strip().upper()
        if not correct or correct not in "ABCDEF":
            correct = correct_raw[0].upper() if correct_raw else ""

        # 标准化用户答案：提取字母
        user_raw = str(user_answer).strip()
        # 如果用户答案是 "B. xxx" 格式，提取 "B"
        user = re.sub(r'^[A-Fa-f][\.．、]\s*', '', user_raw).strip().upper()
        if not user or user not in "ABCDEF":
            user = user_raw[0].upper() if user_raw else ""

        is_correct = user == correct and user != ""
        score = max_score if is_correct else 0

        if is_correct:
            feedback = "回答正确！"
        elif user == "":
            feedback = "未作答。"
        else:
            feedback = f"回答错误。你选择了 {user}，正确答案是 {correct}。"

        return {"score": score, "is_correct": is_correct, "feedback": feedback}

    def _score_fill_blank(self, question: Dict, user_answer: str, max_score: int) -> Dict[str, Any]:
        """填空题评分 — 关键词匹配（支持同义词）"""
        correct = str(question.get("answer", "")).strip()
        user = str(user_answer).strip()

        if not user:
            return {"score": 0, "is_correct": False, "feedback": "未作答。"}

        # 简单关键词匹配：提取正确答案中的关键词（长度>=2的词）
        keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}', correct)
        matched = sum(1 for kw in keywords if kw.lower() in user.lower())
        ratio = matched / max(len(keywords), 1)

        if ratio >= 0.8:
            score = max_score
            is_correct = True
            feedback = "回答正确，关键词覆盖完整。"
        elif ratio >= 0.5:
            score = int(max_score * 0.5)
            is_correct = False
            feedback = f"部分正确，覆盖了 {matched}/{len(keywords)} 个关键词。"
        else:
            score = 0
            is_correct = False
            feedback = f"回答错误。正确答案是: {correct}"

        return {"score": score, "is_correct": is_correct, "feedback": feedback}

    def _score_subjective_llm(self, question: Dict, user_answer: str, max_score: int) -> Dict[str, Any]:
        """主观题评分 — LLM-as-judge（简答/论述）"""
        client = self._get_llm_client()
        if not client or not client.available:
            # LLM 不可用时回退到关键词匹配
            return self._score_fill_blank(question, user_answer, max_score)

        q_text = question.get("question", "")
        correct = question.get("answer", "")
        explanation = question.get("explanation", "")

        prompt = f"""你是一位严格的学科评分专家。请对以下答案进行评分。

题目：{q_text}
参考答案：{correct}
补充说明：{explanation}

考生答案：{user_answer}

评分要求（满分 {max_score} 分）：
1. 准确性（0-{max_score}）：内容是否正确，核心要点是否覆盖
2. 只给整数分数，不可给小数
3. 如果答案完全错误或未作答，给 0 分

请以 JSON 格式输出：
{{
  "score": <整数 0-{max_score}>,
  "is_correct": <true/false, score>={max_score}*0.8 为 true>,
  "feedback": "<一句话评价>"
}}"""

        try:
            result = client.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            score = int(result.get("score", 0))
            score = max(0, min(score, max_score))
            is_correct = bool(result.get("is_correct", score >= max_score * 0.8))
            feedback = result.get("feedback", "已评分")
            return {"score": score, "is_correct": is_correct, "feedback": feedback}
        except Exception as e:
            print(f"[CoachAgent] LLM scoring failed: {e}, fallback to keyword match")
            return self._score_fill_blank(question, user_answer, max_score)

    def _score_calculation(self, question: Dict, user_answer: str, max_score: int) -> Dict[str, Any]:
        """计算/推导题评分 — LLM 判断公式等价"""
        client = self._get_llm_client()
        if not client or not client.available:
            return self._score_fill_blank(question, user_answer, max_score)

        q_text = question.get("question", "")
        correct = question.get("answer", "")

        prompt = f"""你是一位数学/物理评分专家。请判断以下计算答案是否正确或等价。

题目：{q_text}
参考答案（可接受的等价形式）：{correct}

考生答案：{user_answer}

评分要求（满分 {max_score} 分）：
1. 如果结果数值正确（允许等价形式如分数/小数），给满分
2. 如果步骤正确但结果错误，给一半分
3. 如果完全错误或未作答，给 0 分

请以 JSON 格式输出：
{{
  "score": <整数 0-{max_score}>,
  "is_correct": <true/false>,
  "feedback": "<评价说明>"
}}"""

        try:
            result = client.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            score = int(result.get("score", 0))
            score = max(0, min(score, max_score))
            is_correct = bool(result.get("is_correct", False))
            feedback = result.get("feedback", "已评分")
            return {"score": score, "is_correct": is_correct, "feedback": feedback}
        except Exception as e:
            print(f"[CoachAgent] LLM scoring failed: {e}, fallback to keyword match")
            return self._score_fill_blank(question, user_answer, max_score)

    def _score_coding(self, question: Dict, user_answer: str, max_score: int) -> Dict[str, Any]:
        """编程题评分 — LLM 判断代码逻辑"""
        client = self._get_llm_client()
        if not client or not client.available:
            return self._score_fill_blank(question, user_answer, max_score)

        q_text = question.get("question", "")
        correct = question.get("answer", "")

        prompt = f"""你是一位编程评分专家。请对以下代码答案进行评分。

题目：{q_text}
参考答案思路：{correct}

考生代码：
```
{user_answer}
```

评分要求（满分 {max_score} 分）：
1. 如果代码逻辑正确、能解决问题，给满分
2. 如果逻辑基本正确但有语法小错误，扣少量分
3. 如果逻辑错误或未作答，给 0 分

请以 JSON 格式输出：
{{
  "score": <整数 0-{max_score}>,
  "is_correct": <true/false>,
  "feedback": "<评价说明>"
}}"""

        try:
            result = client.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=400,
            )
            score = int(result.get("score", 0))
            score = max(0, min(score, max_score))
            is_correct = bool(result.get("is_correct", False))
            feedback = result.get("feedback", "已评分")
            return {"score": score, "is_correct": is_correct, "feedback": feedback}
        except Exception as e:
            print(f"[CoachAgent] LLM scoring failed: {e}, fallback to keyword match")
            return self._score_fill_blank(question, user_answer, max_score)

    def _generate_summary(self, details: List[Dict[str, Any]], percentage: float) -> Dict[str, Any]:
        """生成能力分析总结"""
        # 按题型统计正确率
        type_stats = {}
        for d in details:
            t = d["type"]
            if t not in type_stats:
                type_stats[t] = {"total": 0, "correct": 0, "scores": 0, "max": 0}
            type_stats[t]["total"] += 1
            type_stats[t]["max"] += d["max_score"]
            type_stats[t]["scores"] += d["score"]
            if d["is_correct"]:
                type_stats[t]["correct"] += 1

        weak_areas = []
        strong_areas = []

        for t, stat in type_stats.items():
            rate = stat["scores"] / max(stat["max"], 1)
            if rate < 0.5:
                weak_areas.append(t)
            elif rate >= 0.8:
                strong_areas.append(t)

        # 等级划分
        if percentage >= 90:
            level = "优秀"
        elif percentage >= 75:
            level = "良好"
        elif percentage >= 60:
            level = "合格"
        else:
            level = "需加强"

        # 生成文本总结
        lines = [f"本次评测共 {len(details)} 题，你获得了 {percentage}% 的分数，等级为「{level}」。"]

        if weak_areas:
            lines.append(f"在以下题型上表现较弱: {', '.join(weak_areas)}，建议针对性练习。")
        if strong_areas:
            lines.append(f"在以下题型上表现优秀: {', '.join(strong_areas)}，继续保持。")

        if not weak_areas and not strong_areas:
            lines.append("各题型表现均衡，建议继续巩固提升。")

        return {
            "text": " ".join(lines),
            "weak_areas": weak_areas,
            "strong_areas": strong_areas,
            "level": level,
        }

    def _extract_topic(self, query: str) -> str:
        keywords = [
            "评测", "评估", "评分", "打分", "测水平", "测能力",
            "我水平", "我能力", "测一下我", "评估我", "评价我",
            "evaluate", "assess", "score", "rate me", "my level",
            "我懂多少", "我学得怎么样", "我掌握", "一下", "我的",
        ]
        topic = query
        for kw in keywords:
            topic = topic.replace(kw, "")
        return " ".join(topic.split()).strip() or "通用知识"

    # ==================== P0-INT-6: 消息总线回调 ====================

    def on_quiz_generated(self, msg):
        """
        订阅 quiz 主题的回调：接收出题事件，加入待评测队列。

        Args:
            msg: Message 对象（event="quiz_generated"）
        """
        payload = msg.payload
        quiz_info = {
            "topic": payload.get("topic", ""),
            "question_count": payload.get("question_count", 0),
            "question_ids": payload.get("question_ids", []),
            "concepts": payload.get("concepts", []),
            "user_theta": payload.get("user_theta", 0.0),
        }
        self._pending_quizzes.append(quiz_info)
        print(f"[CoachAgent] P0-INT-6: 收到出题事件，加入待评测队列: {quiz_info['topic']} ({quiz_info['question_count']} 题)")


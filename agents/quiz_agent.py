#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QuizAgent: 出题 Agent
基于检索内容生成面试题/练习题

修复历史:
- 2026-06-28: 重写为 LLM 驱动生成，解决题目质量差问题(LA-018)
"""

import random
import re
from typing import Dict, Any, List, Optional

from core.vector_store import VectorStore
from core.embedding import EmbeddingManager
from core.query_rewriter import QueryRewriter
from core.subject_analyzer import SubjectAnalyzer
from core.llm_client import LLMClient
from core.graph_education import GraphContext
from agents.base_agent import BaseAgent


# 出题系统 Prompt — 多题型支持（P1: 多题型扩展）
# 每个题型独立模板，handle() 根据 question_types 参数选择混合生成

QUIZ_PROMPT_TEMPLATES = {
    "single_choice": """单选题：从 4 个选项中选择唯一正确答案。
出题要求：
1. 题干必须完整、清晰、有意义
2. 4 个选项，每个选项必须是完整短语/句子，不能是碎片文本
3. 3 个干扰项与主题相关、有迷惑性但明确错误
4. 只有 1 个正确答案
5. 解析解释为什么正确、为什么其他错误

JSON 格式：
{{
  "type": "single_choice",
  "question": "题干文本",
  "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
  "answer": "A",
  "explanation": "解析"
}}
""",

    "multiple_choice": """多选题：从 4-5 个选项中选择所有正确答案（至少 2 个正确）。
出题要求：
1. 题干必须完整、清晰、有意义
2. 4-5 个选项，每个选项完整有意义
3. 干扰项与主题相关但错误，有迷惑性
4. 正确答案 ≥ 2 个
5. 解析逐一说明每个选项对错

JSON 格式：
{{
  "type": "multiple_choice",
  "question": "题干文本",
  "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
  "answer": ["A", "C"],
  "explanation": "解析（逐一说明每个选项）"
}}
""",

    "true_false": """判断题：判断陈述是否正确。
出题要求：
1. 题干是一个明确的事实陈述
2. 选项固定为 ["正确", "错误"]
3. 解析解释为什么对或错，可补充相关知识

JSON 格式：
{{
  "type": "true_false",
  "question": "陈述文本",
  "options": ["正确", "错误"],
  "answer": "正确",
  "explanation": "解析"
}}
""",

    "fill_blank": """填空题：填写空白处的正确答案。
出题要求：
1. 题干包含一个或多个空白（用 ____ 标记）
2. 答案为填空内容，多空用列表
3. 解析说明答案来源和理由

JSON 格式：
{{
  "type": "fill_blank",
  "question": "含有____的题干文本",
  "options": [],
  "answer": "填空答案",
  "explanation": "解析"
}}
""",

    "short_answer": """简答题：简述概念或原理。
出题要求：
1. 题干是一个开放性问题，需要展开论述
2. 无选项（options 为空数组）
3. 答案为参考答案要点（非唯一标准答案）
4. 解析给出评分要点

JSON 格式：
{{
  "type": "short_answer",
  "question": "简答题干文本",
  "options": [],
  "answer": "参考答案要点",
  "explanation": "评分要点：1. xxx；2. xxx"
}}
""",
}

# 统一输出格式说明（混合生成时附加）
QUIZ_OUTPUT_FORMAT = """
## 输出格式要求

你必须以 JSON 格式输出，不要包含任何 markdown 代码块标记或额外解释：

{{
  "questions": [
    {{...题型 1...}},
    {{...题型 2...}},
    ...
  ]
}}

注意：
- 所有内容必须是中文（技术术语可保留英文）
- 确保 JSON 格式完全正确，可以被 Python json.loads 解析
- 不同题型的 type 字段必须严格匹配：single_choice / multiple_choice / true_false / fill_blank / short_answer
"""

# 旧单选题 Prompt 保留（兼容）
QUIZ_GENERATION_PROMPT = """你是一个专业的教育出题专家。请基于以下「检索到的知识片段」，生成 {n_questions} 道高质量的单选题。

## 出题要求

1. **题干**: 必须是一个完整、清晰、有意义的问题，不能是从原文中直接摘录的陈述句
2. **选项**: 每个选项必须是完整、有意义的短语或句子，绝对不能是知识片段中的碎片文本（如"1.3"、"与深度学"、"第一章"等）
3. **干扰项**: 3个干扰项必须与题目主题相关，有一定迷惑性，但明确错误
4. **答案**: 只有一个正确答案
5. **解析**: 解释为什么正确答案是正确的，其他选项为什么错误
6. **来源**: 每道题应基于不同的知识片段，避免重复考察同一知识点

## 检索到的知识片段

{chunks_text}

## 输出格式

你必须以 JSON 格式输出，不要包含任何 markdown 代码块标记或额外解释：

{{
  "questions": [
    {{
      "id": 1,
      "type": "single_choice",
      "question": "完整的题干文本",
      "options": ["A. 完整选项1", "B. 完整选项2", "C. 完整选项3", "D. 完整选项4"],
      "answer": "A",
      "explanation": "解析说明"
    }}
  ]
}}

注意：
- options 数组中每个元素必须包含 "A. "、"B. " 等前缀
- 所有内容必须是中文（技术术语可保留英文）
- 确保 JSON 格式完全正确，可以被 Python json.loads 解析
"""
# 规则生成备用 Prompt（当 LLM 不可用时，改进的规则方法）
RULE_BASED_QUESTION_TEMPLATES = [
    "以下关于 {concept} 的描述，正确的是？",
    "{concept} 的核心特点不包括以下哪一项？",
    "在 {context} 中，{concept} 的主要作用是什么？",
    "关于 {concept}，下列说法错误的是？",
    "{concept} 与以下哪个概念的关系最为密切？",
]


class QuizAgent(BaseAgent):
    """出题 Agent（支持动态学科配置）"""

    @property
    def agent_name(self) -> str:
        return "QuizAgent"

    def __init__(self, collection_name: str = "learnanything_v1", subject: str = "generic", top_k: int = 5, message_bus=None):
        self.collection_name = collection_name
        self.subject = subject
        self.top_k = top_k
        self._vector_store = None
        self._embedding = EmbeddingManager()
        self._rewriter = QueryRewriter()
        self._llm = LLMClient()
        # P0-INT-6: 消息总线
        self._message_bus = message_bus
        # P0-INT-6: 用户能力状态（从消息总线接收）
        self._user_theta = 0.0
        self._user_weak_areas: List[str] = []
        # P0-INT-6: 订阅用户状态更新和薄弱领域通知（QuizAgent 自适应出题难度）
        if self._message_bus is not None:
            self._subscribe_to_message_bus()

    def _subscribe_to_message_bus(self):
        """订阅消息总线：接收用户能力更新和薄弱领域通知"""
        # 订阅 user_state 消息（CoachAgent 评分后发布）
        self._message_bus.subscribe(
            topic="user_state",
            agent_name="QuizAgent",
            handler=self.on_ability_updated,
        )
        # 订阅 weak_area 消息（薄弱领域通知）
        self._message_bus.subscribe(
            topic="weak_area",
            agent_name="QuizAgent",
            handler=self.on_weak_area_detected,
        )
        print(f"[QuizAgent] 已订阅消息总线: user_state, weak_area")

    def on_ability_updated(self, message):
        """处理 user_state 消息：更新用户 theta 值（公共方法名，供 Coordinator._setup_message_bus 引用）"""
        payload = message.payload
        theta = payload.get("theta")
        if theta is not None:
            self._user_theta = theta
            print(f"[QuizAgent] 收到用户能力更新: theta={self._user_theta:.2f}")

    def _get_subject_config(self) -> Dict[str, Any]:
        """加载动态学科配置，优先使用已分析的学科配置，回退到通用配置"""
        config = SubjectAnalyzer.load_config(self.subject)
        if config is not None:
            return config
        return SubjectAnalyzer.get_generic_config()

    def _get_vector_store(self):
        if self._vector_store is None:
            self._vector_store = VectorStore(self.collection_name)
        return self._vector_store

    def handle(self, query: str, n_questions: int = 5, filters: Optional[Dict[str, Any]] = None, graph_context: Optional[GraphContext] = None, **kwargs) -> Dict[str, Any]:
        # P1-FIX: 从 kwargs 读取 question_types（前端传入或默认配置）
        question_types = kwargs.get("question_types")

        # P0-INT-2: 如果提供了 graph_context，使用 P0 图谱上下文出题
        if graph_context is not None and graph_context.text:
            print(f"[QuizAgent] P0-INT-2: 使用 P0 图谱上下文出题，token={graph_context.token_count}")
            return self._generate_questions_with_context(query, n_questions, graph_context, question_types=question_types)

        # 回退：旧方式直接检索 chunks
        print(f"[QuizAgent] 回退到旧方式出题（无图谱上下文）")
        return self._generate_questions_old(query, n_questions, filters, question_types=question_types)

    def _extract_topic(self, query: str) -> str:
        """从用户查询中提取核心主题"""
        keywords = [
            "出题", "题目", "面试题", "练习题", "测试题", "考题", "试题",
            "考我", "测试我", "考一下", "测一下", "做道题", "来道题",
            "quiz", "question", "exam", "test me", "give me a question",
            "出一道", "来一道", "来几题", "出几题", "给我出题",
            "关于", "的", "一下", "几道", "几题",
        ]
        topic = query
        for kw in keywords:
            topic = topic.replace(kw, "")
        return " ".join(topic.split()).strip() or query

    # ==================== P0-INT-2: 使用图谱上下文出题（多题型支持）====================

    def _generate_questions_with_context(self, query: str, n_questions: int, graph_context: GraphContext, question_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """P0-INT-2: 使用 ContextAssembler 组装的上下文生成题目（支持多题型）"""
        topic = self._extract_topic(query)
        config = self._get_subject_config()
        # P1-FIX: 如果没有指定题型，使用配置中启用的题型
        if question_types is None:
            question_types = [k for k, v in config.get("question_types", {}).items() if v.get("enabled", False)]
        if not question_types:
            question_types = ["single_choice", "short_answer"]  # 默认回退

        # 使用 graph_context.text 作为上下文
        context_text = graph_context.text

        # 从 subgraph 提取概念名列表
        concept_names = []
        if graph_context.subgraph:
            concept_names = [n.name for n in graph_context.subgraph.nodes]
            print(f"[QuizAgent] 图谱上下文概念: {concept_names}")

        # P0-INT-6: 自适应出题 — 根据用户能力状态和薄弱领域调整
        user_theta = self._user_theta
        weak_areas = self._user_weak_areas
        if weak_areas:
            print(f"[QuizAgent] P0-INT-6: 自适应出题 — theta={user_theta:.2f}, 薄弱领域={weak_areas}")
            # 优先从薄弱领域相关概念中抽取上下文
            filtered_context = self._filter_context_by_weak_areas(context_text, weak_areas, concept_names)
            if filtered_context:
                context_text = filtered_context
                print(f"[QuizAgent] P0-INT-6: 使用薄弱领域相关上下文出题")

        # 优先使用 LLM 生成题目（多题型）
        questions = self._generate_questions_llm_from_context(
            context_text, n_questions, topic, question_types, user_theta, weak_areas
        )

        if not questions:
            questions = self._generate_questions_fallback_from_context(context_text, n_questions, topic, question_types)

        # 为题目增加 knowledge_trace
        for q in questions:
            q["knowledge_trace"] = {
                "primary_concepts": concept_names[:3] if concept_names else [topic],
                "secondary_concepts": concept_names[3:6] if len(concept_names) > 3 else [],
                "concept_chain": concept_names,
                "difficulty_score": 0.5,
                "difficulty_label": "中等",
            }

        text_parts = [f"以下是 {len(questions)} 道关于「{topic}」的题目（基于知识图谱）：\n"]
        for q in questions:
            type_label = {
                "single_choice": "【单选】",
                "multiple_choice": "【多选】",
                "true_false": "【判断】",
                "fill_blank": "【填空】",
                "short_answer": "【简答】",
            }.get(q.get("type", "single_choice"), "【题】")
            text_parts.append(f"\n【{q['id']}】{type_label}{q['question']}")
            if q.get('options'):
                for opt in q['options']:
                    text_parts.append(f"  {opt}")
            text_parts.append(f"\n答案：{q['answer']}")
            text_parts.append(f"解析：{q['explanation']}")

        # P0-INT-6: 发布 quiz_generated 事件
        if self._message_bus:
            self._message_bus.publish(
                topic="quiz",
                sender="QuizAgent",
                event="quiz_generated",
                payload={
                    "topic": topic,
                    "question_count": len(questions),
                    "question_ids": [q.get("id") for q in questions],
                    "concepts": concept_names[:3] if concept_names else [topic],
                    "user_theta": self._user_theta,
                }
            )

        return {
            "text": "\n".join(text_parts),
            "questions": questions,
            "graph_context_token_count": graph_context.token_count,
            "concept_names": concept_names,
            "topic": topic,
            "subject_config": {
                "subject": config.get("subject", "generic"),
                "name": config.get("name", "通用"),
                "question_types_used": question_types,
            },
            "generation_method": "p0_context" if questions else "fallback",
        }

    def _filter_context_by_weak_areas(self, context_text: str, weak_areas: List[str], concept_names: List[str]) -> str:
        """P0-INT-6: 从上下文中过滤与薄弱领域相关的部分"""
        if not weak_areas or not context_text:
            return context_text

        sentences = re.split(r'[。！？\n]+', context_text)
        matched = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # 检查是否包含薄弱领域关键词
            for area in weak_areas:
                if area.lower() in s.lower() or any(area.lower() in c.lower() for c in concept_names):
                    matched.append(s)
                    break

        if matched:
            # 保留匹配部分 + 原始上下文的一部分（避免过度过滤）
            return "\n".join(matched[:20]) + "\n" + context_text[:2000]
        return context_text

    def _generate_questions_llm_from_context(self, context_text: str, n_questions: int, topic: str, question_types: List[str], user_theta: float = 0.0, weak_areas: List[str] = None) -> List[Dict[str, Any]]:
        """使用 graph_context.text 替代 chunks 作为 LLM prompt 上下文，支持多题型混合生成"""
        if not self._llm.available or not context_text:
            return []

        # 限制 context 长度
        if len(context_text) > 6000:
            context_text = context_text[:6000] + "..."

        # P0-INT-6: 根据用户 theta 调整难度
        difficulty_hint = self._theta_to_difficulty_hint(user_theta)

        # P0-INT-6: 根据薄弱领域调整侧重
        weak_areas_hint = ""
        if weak_areas:
            weak_areas_hint = f"\n\n用户薄弱环节: {', '.join(weak_areas)}。请优先针对这些薄弱环节出题。"

        # P1-FIX: 构建混合题型 prompt
        prompt = self._build_mixed_prompt(
            n_questions=n_questions,
            context_text=context_text,
            topic=topic,
            question_types=question_types,
        ) + difficulty_hint + weak_areas_hint

        try:
            result = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2000,
            )
            questions = result.get("questions", [])
            if not questions:
                return []

            cleaned_questions = []
            for i, q in enumerate(questions):
                cleaned = self._validate_and_clean_question(q, i + 1)
                if cleaned:
                    cleaned_questions.append(cleaned)
            return cleaned_questions[:n_questions]
        except Exception as e:
            print(f"[QuizAgent] 图谱上下文 LLM 生成题目失败: {e}")
            return []

    def _theta_to_difficulty_hint(self, theta: float) -> str:
        """P0-INT-6: 将 IRT theta 转换为出题难度提示"""
        if theta < -1.0:
            return "\n\n用户当前能力水平：初级。请出基础概念题，避免复杂推理。"
        elif theta < 0.0:
            return "\n\n用户当前能力水平：入门。请出基础到中等难度题目，侧重概念理解。"
        elif theta < 1.0:
            return "\n\n用户当前能力水平：中级。请出中等难度题目，可适当包含应用和分析。"
        else:
            return "\n\n用户当前能力水平：高级。请出高难度题目，侧重深入理解、综合应用和辨析。"


    # ==================== P1: 多题型混合生成 Prompt 构建 ====================

    def _build_mixed_prompt(self, n_questions: int, context_text: str, topic: str, question_types: List[str]) -> str:
        """构建多题型混合生成的 LLM prompt

        根据 question_types 列表，动态组合各题型模板，生成一次 LLM 调用。
        自动分配每类题型数量（尽量均匀分布）。
        """
        # 过滤有效题型
        valid_types = [t for t in question_types if t in QUIZ_PROMPT_TEMPLATES]
        if not valid_types:
            valid_types = ["single_choice"]  # 回退到单选题

        # 计算每类题型数量（尽量均匀，优先单选题）
        type_counts = {}
        if len(valid_types) == 1:
            type_counts[valid_types[0]] = n_questions
        else:
            # 单选题优先多分配（如果有）
            base = n_questions // len(valid_types)
            remainder = n_questions % len(valid_types)
            for i, t in enumerate(valid_types):
                type_counts[t] = base + (1 if i < remainder else 0)

        # 构建 prompt 头部
        parts = [
            f"你是一个专业的教育出题专家。请基于以下「知识片段」，生成 {n_questions} 道关于「{topic}」的高质量题目。",
            "",
            "## 题型分布",
        ]
        for t, count in type_counts.items():
            label = {
                "single_choice": "单选题",
                "multiple_choice": "多选题",
                "true_false": "判断题",
                "fill_blank": "填空题",
                "short_answer": "简答题",
            }.get(t, t)
            parts.append(f"- {label}: {count} 道")
        parts.extend([
            "",
            "## 各题型详细要求",
            "",
        ])

        # 拼接各题型模板
        for t in valid_types:
            parts.append(f"--- {t} ---")
            parts.append(QUIZ_PROMPT_TEMPLATES[t])
            parts.append("")

        # 添加知识片段
        parts.extend([
            "## 知识片段",
            "",
            context_text,
            "",
        ])

        # 添加统一输出格式
        parts.append(QUIZ_OUTPUT_FORMAT)

        return "\n".join(parts)

    # ==================== P1: 多题型回退生成 ====================

    def _generate_questions_fallback_from_context(self, context_text: str, n_questions: int, topic: str, question_types: List[str] = None) -> List[Dict[str, Any]]:
        """LLM 不可用时，从 context 文本中提取关键句生成题目（支持多题型回退）"""
        if question_types is None:
            question_types = ["single_choice", "short_answer"]

        questions = []
        sentences = re.split(r'[。！？\n]+', context_text)
        key_sentences = [s.strip() for s in sentences if 30 <= len(s.strip()) <= 200]

        # 回退生成只支持单选题和简答题（其他题型规则生成太复杂）
        fallback_type_cycle = [t for t in question_types if t in ("single_choice", "short_answer")]
        if not fallback_type_cycle:
            fallback_type_cycle = ["single_choice"]

        for i, sentence in enumerate(key_sentences[:n_questions]):
            qtype = fallback_type_cycle[i % len(fallback_type_cycle)]
            if qtype == "single_choice":
                q = self._build_fallback_single_choice(sentence, topic, i + 1)
            else:  # short_answer
                q = self._build_fallback_short_answer(sentence, topic, i + 1)
            if q:
                questions.append(q)

        return questions

    def _build_fallback_single_choice(self, sentence: str, topic: str, qid: int) -> Dict[str, Any]:
        """回退生成单选题"""
        options_pool = [sentence[:80]]
        return {
            "id": qid,
            "type": "single_choice",
            "question": f"关于「{topic}」，以下描述正确的是？",
            "options": [f"{['A','B','C','D'][j]}. {opt}" for j, opt in enumerate(options_pool + ["其他选项"] * 3)],
            "answer": "A",
            "explanation": sentence[:200],
            "source": "graph_context",
        }

    def _build_fallback_short_answer(self, sentence: str, topic: str, qid: int) -> Dict[str, Any]:
        """回退生成简答题"""
        return {
            "id": qid,
            "type": "short_answer",
            "question": f"请结合知识片段，简述「{topic}」中的相关概念。",
            "options": [],
            "answer": sentence[:200],
            "explanation": "（基于知识片段生成）",
            "source": "graph_context",
        }

    # ==================== 旧方式出题（回退）====================

    def _generate_questions_old(self, query: str, n_questions: int = 5, filters: Optional[Dict[str, Any]] = None, question_types: List[str] = None) -> Dict[str, Any]:
        """P0-INT-2: 原 handle 逻辑提取为独立方法（回退路径，支持多题型）"""
        topic = self._extract_topic(query)

        config = self._get_subject_config()
        if question_types is None:
            question_types = [k for k, v in config.get("question_types", {}).items() if v.get("enabled", False)]
        if not question_types:
            question_types = ["single_choice", "short_answer"]

        store = self._get_vector_store()
        retrieved = store.query(topic, n_results=max(n_questions * 4, 24))

        questions = self._generate_questions_llm(retrieved, n_questions, topic, question_types=question_types)

        if not questions:
            questions = self._generate_questions_fallback(retrieved, n_questions, question_types=question_types)

        text_parts = [f"以下是 {len(questions)} 道关于「{topic}」的题目：\n"]
        for q in questions:
            type_label = {
                "single_choice": "【单选】",
                "multiple_choice": "【多选】",
                "true_false": "【判断】",
                "fill_blank": "【填空】",
                "short_answer": "【简答】",
            }.get(q.get("type", "single_choice"), "【题】")
            text_parts.append(f"\n【{q['id']}】{type_label}{q['question']}")
            if q.get('options'):
                for opt in q['options']:
                    text_parts.append(f"  {opt}")
            text_parts.append(f"\n答案：{q['answer']}")
            text_parts.append(f"解析：{q['explanation']}")

        # P0-INT-6: 发布 quiz_generated 事件（旧方式也发布）
        if self._message_bus:
            self._message_bus.publish(
                topic="quiz",
                sender="QuizAgent",
                event="quiz_generated",
                payload={
                    "topic": topic,
                    "question_count": len(questions),
                    "question_ids": [q.get("id") for q in questions],
                    "concepts": [topic],
                    "user_theta": self._user_theta,
                    "generation_method": "llm" if self._llm.available else "fallback",
                }
            )

        return {
            "text": "\n".join(text_parts),
            "questions": questions,
            "retrieved_chunks": retrieved,
            "topic": topic,
            "subject_config": {
                "subject": config.get("subject", "generic"),
                "name": config.get("name", "通用"),
                "question_types_used": question_types,
            },
            "generation_method": "llm" if self._llm.available else "fallback",
        }

    # ==================== LLM 驱动生成（首选）====================

    def _generate_questions_llm(self, chunks: List[Dict[str, Any]], n_questions: int, topic: str, question_types: List[str] = None) -> List[Dict[str, Any]]:
        """使用 LLM 基于检索内容生成高质量题目（支持多题型）"""
        if not self._llm.available:
            return []

        if question_types is None:
            question_types = ["single_choice", "short_answer"]

        # 过滤有效 chunk
        valid_chunks = [c for c in chunks if c.get("text") and len(c.get("text", "")) >= 50]
        if not valid_chunks:
            return []

        # 构造知识片段文本
        chunks_text_parts = []
        total_len = 0
        max_total_len = 6000

        for i, chunk in enumerate(valid_chunks[:10]):
            text = chunk.get("text", "").strip()
            if len(text) > 800:
                text = text[:800] + "..."
            source = chunk.get("metadata", {}).get("source", "未知来源")
            header = chunk.get("metadata", {}).get("header_path", "")
            chunk_desc = f"【片段 {i+1}】来源: {source}"
            if header:
                chunk_desc += f" | 标题: {header}"
            chunk_desc += f"\n{text}\n"

            if total_len + len(chunk_desc) > max_total_len:
                break
            chunks_text_parts.append(chunk_desc)
            total_len += len(chunk_desc)

        if not chunks_text_parts:
            return []

        chunks_text = "\n".join(chunks_text_parts)

        # P1-FIX: 使用混合题型 prompt
        prompt = self._build_mixed_prompt(
            n_questions=n_questions,
            context_text=chunks_text,
            topic=topic,
            question_types=question_types,
        )

        try:
            result = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2000,
            )

            questions = result.get("questions", [])
            if not questions:
                return []

            cleaned_questions = []
            for i, q in enumerate(questions):
                cleaned = self._validate_and_clean_question(q, i + 1)
                if cleaned:
                    cleaned_questions.append(cleaned)

            return cleaned_questions[:n_questions]

        except Exception as e:
            print(f"[QuizAgent] LLM 生成题目失败: {e}")
            return []

    def _validate_and_clean_question(self, q: Dict[str, Any], qid: int) -> Optional[Dict[str, Any]]:
        """验证 LLM 返回的题目格式，清理无效内容（支持多题型）"""
        question_text = q.get("question", "").strip()
        qtype = q.get("type", "single_choice")
        options = q.get("options", [])
        answer = q.get("answer", "")
        explanation = q.get("explanation", "").strip()

        # 基本验证：题干必须非空
        if not question_text or len(question_text) < 10:
            return None

        # 按题型分别验证
        if qtype == "single_choice":
            return self._validate_single_choice(qid, question_text, options, answer, explanation, q)
        elif qtype == "multiple_choice":
            return self._validate_multiple_choice(qid, question_text, options, answer, explanation, q)
        elif qtype == "true_false":
            return self._validate_true_false(qid, question_text, options, answer, explanation, q)
        elif qtype == "fill_blank":
            return self._validate_fill_blank(qid, question_text, answer, explanation, q)
        elif qtype == "short_answer":
            return self._validate_short_answer(qid, question_text, answer, explanation, q)
        else:
            # 未知题型回退为单选题验证
            return self._validate_single_choice(qid, question_text, options, answer, explanation, q)

    def _validate_single_choice(self, qid: int, question_text: str, options: List[str], answer: str, explanation: str, q: Dict) -> Optional[Dict[str, Any]]:
        """验证单选题"""
        if len(options) < 2:
            return None

        cleaned_options = []
        option_labels = ["A", "B", "C", "D", "E", "F"]
        for i, opt in enumerate(options[:4]):
            opt_text = str(opt).strip()
            opt_text = re.sub(r'^[A-Fa-f][\.．、]\s*', '', opt_text)
            if len(opt_text) < 2 or re.match(r'^[\d\s\.\-%]+$', opt_text):
                return None
            cleaned_options.append(f"{option_labels[i]}. {opt_text}")

        if len(cleaned_options) < 4:
            return None

        answer_str = str(answer).strip().upper()
        if answer_str not in option_labels[:len(cleaned_options)]:
            for i, opt in enumerate(cleaned_options):
                if answer_str in opt or opt.startswith(f"{answer_str}."):
                    answer_str = option_labels[i]
                    break
            else:
                answer_str = "A"

        return {
            "id": qid,
            "type": "single_choice",
            "question": question_text,
            "options": cleaned_options,
            "answer": answer_str,
            "explanation": explanation or "暂无解析",
            "source": q.get("source", ""),
        }

    def _validate_multiple_choice(self, qid: int, question_text: str, options: List[str], answer: str, explanation: str, q: Dict) -> Optional[Dict[str, Any]]:
        """验证多选题"""
        if len(options) < 4:
            return None

        cleaned_options = []
        option_labels = ["A", "B", "C", "D", "E"]
        for i, opt in enumerate(options[:5]):
            opt_text = str(opt).strip()
            opt_text = re.sub(r'^[A-Fa-f][\.．、]\s*', '', opt_text)
            if len(opt_text) < 2:
                return None
            cleaned_options.append(f"{option_labels[i]}. {opt_text}")

        if len(cleaned_options) < 4:
            return None

        # 验证答案：支持 "A,B" 或 ["A", "B"] 格式
        answer_list = []
        if isinstance(answer, str):
            answer_list = [a.strip().upper() for a in answer.split(",") if a.strip()]
        elif isinstance(answer, list):
            answer_list = [str(a).strip().upper() for a in answer if a]

        valid_labels = option_labels[:len(cleaned_options)]
        answer_list = [a for a in answer_list if a in valid_labels]

        if not answer_list or len(answer_list) < 2:
            return None

        return {
            "id": qid,
            "type": "multiple_choice",
            "question": question_text,
            "options": cleaned_options,
            "answer": answer_list,
            "explanation": explanation or "暂无解析",
            "source": q.get("source", ""),
        }

    def _validate_true_false(self, qid: int, question_text: str, options: List[str], answer: str, explanation: str, q: Dict) -> Optional[Dict[str, Any]]:
        """验证判断题"""
        cleaned_options = ["正确", "错误"]
        answer_str = str(answer).strip()
        if answer_str not in ("正确", "错误", "对", "错", "True", "False", "是", "否"):
            answer_str = "正确"
        if answer_str in ("对", "True", "是"):
            answer_str = "正确"
        elif answer_str in ("错", "False", "否"):
            answer_str = "错误"

        return {
            "id": qid,
            "type": "true_false",
            "question": question_text,
            "options": cleaned_options,
            "answer": answer_str,
            "explanation": explanation or "暂无解析",
            "source": q.get("source", ""),
        }

    def _validate_fill_blank(self, qid: int, question_text: str, answer: str, explanation: str, q: Dict) -> Optional[Dict[str, Any]]:
        """验证填空题"""
        answer_clean = answer
        if isinstance(answer, list):
            answer_clean = [str(a).strip() for a in answer if a]
        else:
            answer_clean = str(answer).strip()

        if not answer_clean:
            return None

        return {
            "id": qid,
            "type": "fill_blank",
            "question": question_text,
            "options": [],
            "answer": answer_clean,
            "explanation": explanation or "暂无解析",
            "source": q.get("source", ""),
        }

    def _validate_short_answer(self, qid: int, question_text: str, answer: str, explanation: str, q: Dict) -> Optional[Dict[str, Any]]:
        """验证简答题"""
        answer_clean = str(answer).strip() if answer else ""
        if not answer_clean:
            answer_clean = "（开放性问题，无标准答案）"

        return {
            "id": qid,
            "type": "short_answer",
            "question": question_text,
            "options": [],
            "answer": answer_clean,
            "explanation": explanation or "暂无解析",
            "source": q.get("source", ""),
        }

    # ==================== 规则回退生成（LLM 不可用时）====================

    def _generate_questions_fallback(self, chunks: List[Dict[str, Any]], n_questions: int, question_types: List[str] = None) -> List[Dict[str, Any]]:
        """LLM 不可用时，使用改进的规则方法生成题目（支持多题型回退）"""
        if question_types is None:
            question_types = ["single_choice"]

        questions = []
        used_sources = set()

        # 回退只支持单选题和简答题
        fallback_cycle = [t for t in question_types if t in ("single_choice", "short_answer")]
        if not fallback_cycle:
            fallback_cycle = ["single_choice"]

        for i, chunk in enumerate(chunks):
            if len(questions) >= n_questions:
                break

            text = chunk.get("text", "")
            if not text or len(text) < 100:
                continue

            source = chunk.get("metadata", {}).get("source", "")
            if source in used_sources:
                continue
            used_sources.add(source)

            qtype = fallback_cycle[i % len(fallback_cycle)]
            if qtype == "single_choice":
                question = self._build_question_fallback(text, chunk, i + 1)
            else:
                question = self._build_generic_question(None, i + 1)
                question["type"] = "short_answer"
                header = chunk.get("metadata", {}).get("header_path", "")
                concept = header or "该知识点"
                question["question"] = f"请简述「{concept}」的核心概念。"
                question["answer"] = text[:200]
            if question:
                questions.append(question)

        # 补充通用题目
        while len(questions) < n_questions:
            questions.append(self._build_generic_question(questions[-1] if questions else None, len(questions) + 1))

        return questions[:n_questions]

    def _build_question_fallback(self, text: str, chunk: Dict[str, Any], qid: int) -> Optional[Dict[str, Any]]:
        """改进的规则方法：从 chunk 中提取完整概念生成题目"""
        # 提取标题/章节名作为概念
        header = chunk.get("metadata", {}).get("header_path", "")
        source = chunk.get("metadata", {}).get("source", "")
        concept = header or source or "该知识点"

        # 提取关键句子（定义句、特征句）
        sentences = re.split(r'[。！？\n]+', text)
        key_sentences = []
        for s in sentences:
            s = s.strip()
            if 30 <= len(s) <= 200:
                # 优先选择包含定义特征的句子
                if any(w in s for w in ["是", "指", "定义为", "用于", "通过", "基于", "实现", "包括"]):
                    key_sentences.append(s)

        if not key_sentences:
            return None

        # 从关键句子中提取关键概念作为选项素材
        # 提取技术术语（英文大驼峰、中文技术词）
        tech_terms = re.findall(r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*', text)
        tech_terms = list(set(t.strip() for t in tech_terms if len(t.strip()) > 2))[:8]

        chinese_terms = re.findall(r'[\u4e00-\u9fff]{2,8}(?:[\u4e00-\u9fff\s]*[\u4e00-\u9fff]{2,8})?', text)
        chinese_terms = list(set(t.strip() for t in chinese_terms if len(t.strip()) >= 4))[:8]

        # 构建选项池
        option_pool = []
        for term in tech_terms + chinese_terms:
            if len(term) >= 3 and term not in option_pool:
                option_pool.append(term)

        if len(option_pool) < 4:
            # 选项不足时生成通用选项
            option_pool = [
                concept,
                f"{concept}的优化方法",
                f"{concept}的替代方案",
                f"与{concept}无关的技术",
            ]

        # 构造题干
        template = random.choice(RULE_BASED_QUESTION_TEMPLATES)
        question_text = template.format(concept=concept, context=source)

        # 构造选项（确保是完整概念）
        correct = option_pool[0]
        distractors = option_pool[1:4] if len(option_pool) >= 4 else [
            f"其他{concept}变体",
            f"不相关的技术",
            f"{concept}的早期版本",
        ]
        options = [correct] + distractors[:3]

        random.seed(qid)
        random.shuffle(options)
        correct_idx = options.index(correct)

        return {
            "id": qid,
            "type": "single_choice",
            "question": question_text,
            "options": [f"{['A','B','C','D'][i]}. {opt}" for i, opt in enumerate(options)],
            "answer": ["A","B","C","D"][correct_idx],
            "explanation": key_sentences[0][:200],
            "source": source,
        }

    def _build_generic_question(self, last_question: Optional[Dict[str, Any]], qid: int) -> Dict[str, Any]:
        """通用模板题目（题目不足时补充）"""
        topics = ["RAG", "Agent", "Embedding", "Transformer", "LLM", "Prompt Engineering", "微调", "分布式训练"]
        random.seed(qid)
        topic = random.choice(topics)
        return {
            "id": qid,
            "type": "short_answer",
            "question": f"请结合你的理解，阐述 {topic} 在实际项目中的应用。",
            "options": [],
            "answer": "（开放性问题）",
            "explanation": "（开放性问题，无标准答案）",
            "source": "",
        }

    # ==================== P0-INT-6: 消息总线回调 ====================

    def on_ability_updated(self, msg):
        """
        订阅 user_state 主题的回调：接收 IRT 能力更新，调整出题难度。

        Args:
            msg: Message 对象（event="ability_updated"）
        """
        payload = msg.payload
        theta = payload.get("theta", 0.0)
        concept = payload.get("concept", "")
        self._user_theta = theta
        print(f"[QuizAgent] P0-INT-6: 收到能力更新 theta={theta:.2f} concept={concept}，将调整出题难度")

    def on_weak_area_detected(self, msg):
        """
        订阅 weak_area 主题的回调：记录薄弱点，优先出题。

        Args:
            msg: Message 对象（event="weak_area_detected"）
        """
        payload = msg.payload
        concept = payload.get("concept", "")
        streak_wrong = payload.get("streak_wrong", 0)
        if concept and streak_wrong >= 2:
            if concept not in self._user_weak_areas:
                self._user_weak_areas.append(concept)
            print(f"[QuizAgent] P0-INT-6: 记录薄弱点 concept={concept} streak_wrong={streak_wrong}")

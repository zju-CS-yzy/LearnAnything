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
from agents.base_agent import BaseAgent


# 出题系统 Prompt — 基于检索到的知识片段生成高质量题目
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

    def __init__(self, collection_name: str = "learnanything_v1", subject: str = "generic", top_k: int = 5):
        self.collection_name = collection_name
        self.subject = subject
        self.top_k = top_k
        self._vector_store = None
        self._embedding = EmbeddingManager()
        self._rewriter = QueryRewriter()
        self._llm = LLMClient()

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

    def handle(self, query: str, n_questions: int = 5, filters: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        # 从用户查询中提取核心主题
        topic = self._extract_topic(query)

        # 加载动态学科配置
        config = self._get_subject_config()
        enabled_types = [k for k, v in config.get("question_types", {}).items() if v.get("enabled", False)]

        # 检索相关知识
        store = self._get_vector_store()
        retrieved = store.query(topic, n_results=max(n_questions * 4, 24))

        # 优先使用 LLM 生成高质量题目
        questions = self._generate_questions_llm(retrieved, n_questions, topic)

        # LLM 失败时回退到规则方法
        if not questions:
            questions = self._generate_questions_fallback(retrieved, n_questions)

        # 组装文本
        text_parts = [f"以下是 {len(questions)} 道关于「{topic}」的题目：\n"]
        for q in questions:
            text_parts.append(f"\n【{q['id']}】{q['question']}")
            if q.get('options'):
                for opt in q['options']:
                    text_parts.append(f"  {opt}")
            text_parts.append(f"\n答案：{q['answer']}")
            text_parts.append(f"解析：{q['explanation']}")

        return {
            "text": "\n".join(text_parts),
            "questions": questions,
            "retrieved_chunks": retrieved,
            "topic": topic,
            "subject_config": {
                "subject": config.get("subject", "generic"),
                "name": config.get("name", "通用"),
                "question_types_used": enabled_types,
            },
            "generation_method": "llm" if self._llm.available else "fallback",
        }

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

    # ==================== LLM 驱动生成（首选）====================

    def _generate_questions_llm(self, chunks: List[Dict[str, Any]], n_questions: int, topic: str) -> List[Dict[str, Any]]:
        """使用 LLM 基于检索内容生成高质量题目"""
        if not self._llm.available:
            return []

        # 过滤有效 chunk
        valid_chunks = [c for c in chunks if c.get("text") and len(c.get("text", "")) >= 50]
        if not valid_chunks:
            return []

        # 构造知识片段文本（取前 8 个最相关的片段，限制总长度避免超出上下文）
        chunks_text_parts = []
        total_len = 0
        max_total_len = 6000  # 控制 prompt 总长度

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

        # 构建 prompt
        prompt = QUIZ_GENERATION_PROMPT.format(
            n_questions=min(n_questions, len(valid_chunks)),
            chunks_text=chunks_text,
        )

        try:
            # 调用 LLM 生成 JSON 格式题目
            result = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,  # 稍低温度保证确定性
                max_tokens=2000,
            )

            questions = result.get("questions", [])
            if not questions:
                return []

            # 验证并清理返回的题目
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
        """验证 LLM 返回的题目格式，清理无效内容"""
        question_text = q.get("question", "").strip()
        options = q.get("options", [])
        answer = q.get("answer", "").strip().upper()
        explanation = q.get("explanation", "").strip()

        # 基本验证
        if not question_text or len(question_text) < 10:
            return None
        if len(options) < 2:
            return None

        # 清理选项：确保每个选项以 A./B./C./D. 开头
        cleaned_options = []
        option_labels = ["A", "B", "C", "D", "E", "F"]
        for i, opt in enumerate(options[:4]):  # 最多4个选项
            opt_text = str(opt).strip()
            # 去除已有的前缀（如 "A. xxx" -> "xxx"）
            opt_text = re.sub(r'^[A-Fa-f][\.．、]\s*', '', opt_text)
            # 过滤掉明显是碎片的选项（纯数字、纯标点、过短）
            if len(opt_text) < 2 or re.match(r'^[\d\s\.\-%]+$', opt_text):
                return None  # 只要有一个选项是碎片，整道题丢弃
            cleaned_options.append(f"{option_labels[i]}. {opt_text}")

        if len(cleaned_options) < 4:
            return None

        # 验证答案是否在有效范围内
        if answer not in option_labels[:len(cleaned_options)]:
            # 尝试从选项文本中推断
            for i, opt in enumerate(cleaned_options):
                if answer in opt or opt.startswith(f"{answer}."):
                    answer = option_labels[i]
                    break
            else:
                answer = "A"  # 默认第一个

        return {
            "id": qid,
            "type": "single_choice",
            "question": question_text,
            "options": cleaned_options,
            "answer": answer,
            "explanation": explanation or "暂无解析",
            "source": q.get("source", ""),
        }

    # ==================== 规则回退生成（LLM 不可用时）====================

    def _generate_questions_fallback(self, chunks: List[Dict[str, Any]], n_questions: int) -> List[Dict[str, Any]]:
        """LLM 不可用时，使用改进的规则方法生成题目"""
        questions = []
        used_sources = set()

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

            question = self._build_question_fallback(text, chunk, i + 1)
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

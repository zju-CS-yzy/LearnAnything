"""
评测模块
基于 LLM-as-a-judge 和规则的多维度评测
"""

import json
import re
from typing import List, Dict, Any

EVALUATION_DIMENSIONS = {
    "accuracy": {"name": "准确性", "description": "内容是否正确，与检索知识一致", "weight": 0.25},
    "completeness": {"name": "完整性", "description": "是否覆盖核心要点", "weight": 0.20},
    "clarity": {"name": "清晰度", "description": "表达是否清晰，逻辑结构合理", "weight": 0.15},
    "practicality": {"name": "实用性", "description": "是否包含可操作步骤或示例", "weight": 0.15},
    "citation": {"name": "引用准确性", "description": "是否准确引用来源", "weight": 0.10},
    "hallucination": {"name": "幻觉程度", "description": "是否包含编造内容（越低越好）", "weight": 0.15},
}


class Evaluator:
    """智能评测器"""

    def __init__(self):
        self._llm = None
        self._llm_available = None

    def _check_llm(self) -> bool:
        if self._llm_available is not None:
            return self._llm_available
        try:
            from core.llm_client import LLMClient
            self._llm = LLMClient()
            self._llm_available = True
        except Exception:
            self._llm_available = False
        return self._llm_available

    def evaluate(self, question: str, answer: str, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if self._check_llm():
            try:
                return self._llm_evaluate(question, answer, retrieved_chunks)
            except Exception as e:
                print(f"[Evaluator] LLM evaluate failed: {e}, fallback to rules")
        return self._rule_evaluate(question, answer, retrieved_chunks)

    def _llm_evaluate(self, question: str, answer: str, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        sources = "\n\n".join([c.get("text", "")[:500] for c in retrieved_chunks[:5]])
        dimensions_desc = "\n".join([f"- {k}: {v['name']}（权重 {v['weight'] * 100}%）" for k, v in EVALUATION_DIMENSIONS.items()])

        prompt = f"""你是一位严格的质量评测专家。基于以下信息，对回答进行多维度评测（每个维度 0-10 分）。

评测维度：
{dimensions_desc}

【用户问题】
{question}

【知识片段】
{sources}

【回答】
{answer}

输出严格 JSON：
{{"dimensions": {{"accuracy": {{"score": 0-10, "comment": "..."}}, ...}}, "summary": "...", "strengths": ["..."], "weaknesses": ["..."], "suggestions": ["..."]}}"""

        response = self._llm.chat([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=1500)
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            result = json.loads(json_match.group()) if json_match else json.loads(response.strip())
        except Exception:
            raise ValueError(f"Parse failed: {response[:200]}")

        dimensions = result.get("dimensions", {})
        overall = sum(float(dim.get("score", 0)) * EVALUATION_DIMENSIONS.get(k, {}).get("weight", 0) * 10 for k, dim in dimensions.items())

        return {
            'overall_score': round(overall, 1),
            'dimensions': dimensions,
            'summary': result.get('summary', ''),
            'strengths': result.get('strengths', []),
            'weaknesses': result.get('weaknesses', []),
            'suggestions': result.get('suggestions', []),
            'method': 'llm_judge',
        }

    def _rule_evaluate(self, question: str, answer: str, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        dimensions = {k: {'score': 6.0, 'comment': '基于规则的粗略评估'} for k in EVALUATION_DIMENSIONS}

        source_text = " ".join([c.get("text", "") for c in retrieved_chunks])
        answer_words = set(answer.lower().split())
        source_words = set(source_text.lower().split())
        if answer_words and source_words:
            overlap = len(answer_words & source_words) / len(answer_words)
            dimensions['accuracy']['score'] = min(6 + overlap * 4, 10)
            dimensions['accuracy']['comment'] = f'关键词重叠率: {overlap:.1%}'

        answer_len = len(answer)
        if answer_len > 500:
            dimensions['completeness']['score'] = 7.0
        elif answer_len > 100:
            dimensions['completeness']['score'] = 5.0
        else:
            dimensions['completeness']['score'] = 3.0

        has_structure = bool(re.search(r'[\d一二三四五六七八九十]、|[\(\（][\d一二三四五六七八九十][\)\）]', answer))
        dimensions['clarity']['score'] = 8.0 if has_structure else 6.0

        has_code = '```' in answer or 'import' in answer or 'def ' in answer
        has_example = '例如' in answer or '示例' in answer
        dimensions['practicality']['score'] = 8.0 if (has_code or has_example) else 5.0

        has_citation = '【来源】' in answer or '来源' in answer
        dimensions['citation']['score'] = 7.0 if has_citation else 4.0

        try:
            from core.hallucination_detector import detect_hallucination
            hall_result = detect_hallucination(answer, retrieved_chunks)
            hall_score = hall_result.get('hallucination_score', 0)
            dimensions['hallucination']['score'] = max(0, 10 - hall_score * 10)
            dimensions['hallucination']['comment'] = f'幻觉检测: {hall_score:.2f}'
        except Exception:
            dimensions['hallucination']['score'] = 5.0

        overall = sum(float(dim['score']) * EVALUATION_DIMENSIONS[k]['weight'] * 10 for k, dim in dimensions.items())

        strengths, weaknesses, suggestions = [], [], []
        for k, dim in dimensions.items():
            score = dim['score']
            if score >= 8:
                strengths.append(f"{EVALUATION_DIMENSIONS[k]['name']}优秀")
            elif score < 5:
                weaknesses.append(f"{EVALUATION_DIMENSIONS[k]['name']}需改进")
                suggestions.append(f"提升{EVALUATION_DIMENSIONS[k]['name']}")

        if not strengths: strengths.append('回答基本满足要求')
        if not weaknesses: weaknesses.append('无明显不足')
        if not suggestions: suggestions.append('可进一步优化回答结构')

        return {
            'overall_score': round(overall, 1),
            'dimensions': dimensions,
            'summary': f'规则评测: {round(overall, 1)}/100',
            'strengths': strengths,
            'weaknesses': weaknesses,
            'suggestions': suggestions,
            'method': 'rule_fallback',
        }

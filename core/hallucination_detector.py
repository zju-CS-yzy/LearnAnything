"""
幻觉检测模块
对比生成回答与检索文档，检测事实性幻觉
"""

import re
from typing import List, Dict, Any, Optional

import numpy as np

from core.embedding import EmbeddingManager

SIMILARITY_THRESHOLD = 0.55


class HallucinationDetector:
    """幻觉检测器"""

    def __init__(self, use_llm_judge: bool = False):
        self.use_llm_judge = use_llm_judge
        self._embedding = EmbeddingManager()

    def detect(self, generated_text: str, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not generated_text or not retrieved_chunks:
            return {'hallucination_score': 0.0, 'is_safe': True, 'issues': [], 'coverage_score': 0.0, 'method': 'rule'}

        source_texts = [c.get("text", "") for c in retrieved_chunks]
        combined_source = "\n".join(source_texts)
        claims = self._extract_claims(generated_text)

        issues = []
        supported = 0

        if claims and source_texts:
            try:
                claim_embeddings = np.array(self._embedding.embed(claims))
                source_embeddings = np.array(self._embedding.embed(source_texts))
                similarities = np.dot(claim_embeddings, source_embeddings.T)
            except Exception:
                similarities = None
        else:
            similarities = None

        for i, claim in enumerate(claims):
            issue = self._check_claim(claim, combined_source, similarities[i] if similarities is not None else None)
            if issue:
                issues.append(issue)
            else:
                supported += 1

        total = len(claims)
        unsupported_ratio = (total - supported) / total if total > 0 else 0.0
        hallucination_score = min(unsupported_ratio, 1.0)
        is_safe = hallucination_score < 0.3
        coverage_score = supported / total if total > 0 else 1.0

        return {
            'hallucination_score': round(hallucination_score, 3),
            'is_safe': is_safe,
            'issues': issues,
            'coverage_score': round(coverage_score, 3),
            'method': 'rule',
            'total_claims': total,
            'supported_claims': supported,
        }

    def _extract_claims(self, text: str) -> List[str]:
        sentences = re.split(r'[。！？\n]+', text)
        claims = []
        for s in sentences:
            s = s.strip()
            if len(s) < 10 or s.endswith('?') or s.endswith('？'):
                continue
            if any(s.startswith(w) for w in ['请', '建议', '注意', '简单来说', '简而言之', '总之']):
                continue
            has_number = bool(re.search(r'\d+', s))
            has_term = bool(re.search(r'[A-Za-z]{3,}', s))
            has_chinese = bool(re.search(r'[\u4e00-\u9fff]{2,}', s))
            if has_number or has_term or has_chinese:
                claims.append(s)
        return claims

    def _check_claim(self, claim: str, source: str, similarity: Optional[np.ndarray]) -> Optional[Dict[str, Any]]:
        if similarity is not None:
            max_sim = float(np.max(similarity))
            if max_sim < SIMILARITY_THRESHOLD:
                return {'type': 'unsupported', 'text': claim[:100], 'confidence': round(1.0 - max_sim, 3),
                        'reason': f'声明与原文相似度最高 {max_sim:.3f}，低于阈值 {SIMILARITY_THRESHOLD}'}
            return None

        key_terms = list(set(re.findall(r'[A-Za-z]{3,}|\d+\.?\d*%?', claim) + re.findall(r'[\u4e00-\u9fff]{2,4}', claim)))
        if len(key_terms) < 2:
            return None

        found = sum(1 for t in key_terms if t.lower() in source.lower())
        coverage = found / len(key_terms) if key_terms else 1.0
        if coverage < 0.5:
            return {'type': 'hallucination', 'text': claim[:100], 'confidence': round(1.0 - coverage, 3),
                    'reason': f'声明中 {len(key_terms) - found}/{len(key_terms)} 个关键词未在原文中出现'}
        return None


def detect_hallucination(generated_text: str, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    detector = HallucinationDetector()
    return detector.detect(generated_text, retrieved_chunks)

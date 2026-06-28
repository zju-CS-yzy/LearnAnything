"""
Reranker 模块
CrossEncoder 重排序，支持轻量模型和 CPU 推理
"""

import numpy as np
import sys
from typing import List, Dict, Any, Tuple

from core.embedding import EmbeddingManager


class Reranker:
    """Reranker 基类"""

    def rerank(self, query: str, docs: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError


class CosineReranker(Reranker):
    """Cosine 相似度回退 Reranker"""

    def __init__(self):
        self.embedding = EmbeddingManager()

    def rerank(self, query: str, docs: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        # 空文档列表保护：直接返回空结果
        if not docs:
            return []
        query_emb = np.array(self.embedding.embed_single(query))
        texts = [d.get("text", "") for d in docs]
        doc_embs = np.array(self.embedding.embed(texts))
        scores = np.dot(doc_embs, query_emb)
        ranked_indices = np.argsort(scores)[::-1].tolist()

        results = []
        for idx in ranked_indices[:top_n]:
            doc = dict(docs[idx])
            doc["rerank_score"] = round(float(scores[idx]), 4)
            doc["reranker"] = "CosineReranker"
            results.append(doc)
        return results


class CrossEncoderReranker(Reranker):
    """CrossEncoder Reranker（优先，需要 sentence-transformers）"""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.available = False
        self.model = None
        self.model_name = model_name
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name, device="cpu")
            self.available = True
        except Exception as e:
            print(f"[Reranker] CrossEncoder load failed: {e}")

    def rerank(self, query: str, docs: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        if not self.available or self.model is None:
            raise RuntimeError("CrossEncoder not available")

        texts = [d.get("text", "") for d in docs]
        pairs = [[query, t] for t in texts]
        scores = self.model.predict(pairs)

        ranked_indices = np.argsort(scores)[::-1].tolist()
        results = []
        for idx in ranked_indices[:top_n]:
            doc = dict(docs[idx])
            doc["rerank_score"] = round(float(scores[idx]), 4)
            doc["reranker"] = "CrossEncoderReranker"
            results.append(doc)
        return results


class RerankerFactory:
    """Reranker 工厂，优先 CrossEncoder，失败回退 Cosine"""

    @staticmethod
    def create() -> Reranker:
        # PyInstaller 打包环境下禁用 CrossEncoder，避免 transformers/torch 依赖崩溃
        if getattr(sys, 'frozen', False):
            print("[Reranker] PyInstaller mode: using CosineReranker")
            return CosineReranker()

        try:
            ce = CrossEncoderReranker()
            if ce.available:
                return ce
        except Exception:
            pass
        return CosineReranker()

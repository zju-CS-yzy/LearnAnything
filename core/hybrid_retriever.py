"""
混合检索模块
BM25 + 向量检索 + RRF 融合
"""

import gc
import json
import pickle
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import numpy as np

from config.settings import CACHE_DIR
from core.embedding import EmbeddingManager
from core.vector_store import VectorStore


def jieba_tokenize(text) -> List[str]:
    """jieba 分词，带空值保护（兼容 ChromaDB 可能返回的 None）"""
    import jieba
    if not text or not isinstance(text, str):
        return []
    tokens = []
    for t in jieba.cut(text.strip()):
        t = t.strip().lower()
        if t and (len(t) > 1 or t.isalnum()):
            tokens.append(t)
    return tokens


def rrf_fuse(rankings: List[List[str]], k: int = 60) -> List[Tuple[str, float]]:
    scores = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            if doc_id not in scores:
                scores[doc_id] = 0.0
            scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


class HybridRetriever:
    """
    BM25 + 向量混合检索器。

    使用方式:
        retriever = HybridRetriever("chemistry_v1")
        results = retriever.query("化学键", n_results=5)
    """

    def __init__(self, collection_name: str, top_k_bm25: int = 100, top_k_vector: int = 100, use_cache: bool = True):
        self.collection_name = collection_name
        self.top_k_bm25 = top_k_bm25
        self.top_k_vector = top_k_vector
        self.use_cache = use_cache
        self.bm25 = None
        self.doc_ids = []
        self.doc_texts = []
        self.doc_metadatas = []
        self._loaded = False
        self._vector_store = VectorStore(collection_name)
        self._embedding = EmbeddingManager()

    def _build_bm25_index(self):
        from rank_bm25 import BM25Okapi
        cache_file = CACHE_DIR / f"bm25_{self.collection_name}.pkl"
        ids_cache = CACHE_DIR / f"bm25_{self.collection_name}_ids.json"

        if self.use_cache and cache_file.exists() and ids_cache.exists():
            with open(cache_file, 'rb') as f:
                self.bm25 = pickle.load(f)
            with open(ids_cache, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.doc_ids = data['ids']
                self.doc_texts = data['texts']
                self.doc_metadatas = data['metadatas']
            return

        print(f"[HybridRetriever] Building BM25 index for {self.collection_name}...")
        count = self._vector_store.count()

        # 空集合保护：无文档时跳过 BM25 索引构建
        if count == 0:
            print(f"[HybridRetriever] WARNING: Collection '{self.collection_name}' is empty, BM25 disabled")
            self.bm25 = None
            self.doc_ids = []
            self.doc_texts = []
            self.doc_metadatas = []
            return

        batch_size = 200
        all_ids, all_docs, all_metas = [], [], []

        for offset in range(0, count, batch_size):
            result = self._vector_store.get(
                limit=batch_size,
                offset=offset,
                include=["documents", "metadatas"],
            )
            all_ids.extend(result['ids'])
            all_docs.extend(result['documents'])
            all_metas.extend(result['metadatas'])

        self.doc_ids = all_ids
        self.doc_texts = all_docs
        self.doc_metadatas = all_metas

        # 过滤无效文档（None、空字符串、非字符串）
        valid_pairs = [(doc_id, doc, meta) for doc_id, doc, meta in zip(all_ids, all_docs, all_metas) if doc and isinstance(doc, str) and doc.strip()]
        if not valid_pairs:
            print(f"[HybridRetriever] WARNING: No valid documents for BM25 in '{self.collection_name}'")
            self.bm25 = None
            return
        self.doc_ids = [p[0] for p in valid_pairs]
        self.doc_texts = [p[1] for p in valid_pairs]
        self.doc_metadatas = [p[2] for p in valid_pairs]

        tokenized_corpus = [jieba_tokenize(d) for d in self.doc_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

        if self.use_cache:
            with open(cache_file, 'wb') as f:
                pickle.dump(self.bm25, f)
            with open(ids_cache, 'w', encoding='utf-8') as f:
                json.dump({
                    'ids': all_ids, 'texts': all_docs, 'metadatas': all_metas,
                    'created_at': datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)

    def _ensure_ready(self):
        if not self._loaded:
            self._build_bm25_index()
            self._loaded = True

    def query(self, query_text: str, n_results: int = 5, where: Optional[Dict] = None, return_scores: bool = False) -> List[Dict[str, Any]]:
        self._ensure_ready()
        start_time = time.time()

        # BM25（空集合时 bm25 为 None，跳过）
        if self.bm25 is not None:
            query_tokens = jieba_tokenize(query_text)
            bm25_scores = self.bm25.get_scores(query_tokens)
            bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: -bm25_scores[i])[:self.top_k_bm25]
            bm25_ranking = [self.doc_ids[i] for i in bm25_indices]
        else:
            bm25_scores = []
            bm25_indices = []
            bm25_ranking = []

        # Vector 检索（使用 SQLite 实现的 VectorStore.query）
        vector_results = self._vector_store.query(query_text, n_results=self.top_k_vector, where=where)
        vector_ranking = [r["id"] for r in vector_results]
        vector_docs = [r["text"] for r in vector_results]
        vector_metas = [r["metadata"] for r in vector_results]
        vector_dists = [r["distance"] for r in vector_results]

        # RRF 融合（BM25 为空时只取向量结果）
        rankings = [r for r in [bm25_ranking, vector_ranking] if r]
        fused = rrf_fuse(rankings, k=60)

        # Assemble
        id_to_text = dict(zip(self.doc_ids, self.doc_texts))
        id_to_meta = dict(zip(self.doc_ids, self.doc_metadatas))
        vector_id_to_data = {vid: (doc, meta, dist) for vid, doc, meta, dist in zip(vector_ranking, vector_docs, vector_metas, vector_dists)}

        results = []
        for doc_id, rrf_score in fused[:n_results]:
            text = id_to_text.get(doc_id, "")
            metadata = id_to_meta.get(doc_id, {})
            vector_distance = None
            vector_data = vector_id_to_data.get(doc_id)
            if vector_data:
                vector_doc, vector_meta, vector_dist = vector_data
                if vector_doc:
                    text = vector_doc
                if vector_meta:
                    metadata = vector_meta
                vector_distance = vector_dist

            bm25_rank = bm25_ranking.index(doc_id) + 1 if doc_id in bm25_ranking else None
            vector_rank = vector_ranking.index(doc_id) + 1 if doc_id in vector_ranking else None

            item = {
                "id": doc_id,
                "text": text,
                "metadata": metadata,
                "rrf_score": round(rrf_score, 4),
                "bm25_rank": bm25_rank,
                "vector_rank": vector_rank,
            }
            if return_scores:
                if bm25_rank is not None:
                    item["bm25_score"] = round(float(bm25_scores[bm25_indices[bm25_rank - 1]]), 4)
                if vector_distance is not None:
                    item["vector_distance"] = round(vector_distance, 4)
            results.append(item)

        if return_scores:
            print(f"[HybridRetriever] {len(results)} results in {(time.time()-start_time)*1000:.1f}ms")
        return results

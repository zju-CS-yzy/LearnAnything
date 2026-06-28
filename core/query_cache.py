"""
查询缓存模块
SQLite 本地缓存，支持精确匹配和语义相似匹配
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

import numpy as np

from config.settings import CACHE_DIR, CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES
from core.embedding import EmbeddingManager


class QueryCache:
    """
    查询缓存器。

    使用方式:
        cache = QueryCache()
        result = cache.get(query_text, query_embedding)
        if result is None:
            result = retriever.query(...)
            cache.set(query_text, query_embedding, result)
    """

    def __init__(self, db_path: Path = CACHE_DIR / "query_cache.db",
                 ttl: int = CACHE_TTL_SECONDS, max_entries: int = CACHE_MAX_ENTRIES):
        self.db_path = db_path
        self.ttl = ttl
        self.max_entries = max_entries
        self._embedding = EmbeddingManager()
        self._ensure_db()

    def _ensure_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                query_hash TEXT PRIMARY KEY,
                query_text TEXT NOT NULL,
                embedding_blob BLOB,
                result_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                accessed_at REAL NOT NULL,
                access_count INTEGER DEFAULT 1,
                hit_type TEXT DEFAULT 'exact'
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accessed_at ON query_cache(accessed_at)")
        conn.commit()
        conn.close()

    def _normalize(self, query: str) -> str:
        return ' '.join(query.lower().split())

    def _hash(self, query: str) -> str:
        return hashlib.md5(self._normalize(query).encode()).hexdigest()

    def _cosine(self, a: List[float], b: List[float]) -> float:
        a_arr = np.array(a)
        b_arr = np.array(b)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))

    def _cleanup(self, conn: sqlite3.Connection):
        cutoff = time.time() - self.ttl
        cursor = conn.cursor()
        cursor.execute("DELETE FROM query_cache WHERE created_at < ?", (cutoff,))
        conn.commit()

    def _lru_evict(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM query_cache")
        count = cursor.fetchone()[0]
        if count > self.max_entries:
            to_delete = count - self.max_entries
            cursor.execute(
                "DELETE FROM query_cache WHERE query_hash IN (SELECT query_hash FROM query_cache ORDER BY accessed_at ASC LIMIT ?)",
                (to_delete,)
            )
            conn.commit()

    def get(self, query_text: str, query_embedding: Optional[List[float]] = None,
            similarity_threshold: float = 0.95) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            self._cleanup(conn)
            cursor = conn.cursor()
            query_hash = self._hash(query_text)

            # 精确匹配
            cursor.execute(
                "SELECT result_json, access_count, query_text FROM query_cache WHERE query_hash = ?",
                (query_hash,)
            )
            row = cursor.fetchone()
            if row:
                result_json, access_count, cached_text = row
                cursor.execute(
                    "UPDATE query_cache SET accessed_at = ?, access_count = ?, hit_type = 'exact' WHERE query_hash = ?",
                    (time.time(), access_count + 1, query_hash)
                )
                conn.commit()
                return {'result': json.loads(result_json), 'hit_type': 'exact', 'cached_query': cached_text}

            # 语义相似匹配
            if query_embedding is not None:
                cursor.execute("SELECT query_hash, query_text, embedding_blob, result_json FROM query_cache")
                for row in cursor.fetchall():
                    cached_hash, cached_text, embedding_blob, result_json = row
                    if embedding_blob:
                        cached_embedding = json.loads(embedding_blob)
                        similarity = self._cosine(query_embedding, cached_embedding)
                        if similarity >= similarity_threshold:
                            cursor.execute(
                                "UPDATE query_cache SET accessed_at = ?, access_count = access_count + 1, hit_type = 'semantic' WHERE query_hash = ?",
                                (time.time(), cached_hash)
                            )
                            conn.commit()
                            return {'result': json.loads(result_json), 'hit_type': 'semantic', 'cached_query': cached_text, 'similarity': round(similarity, 4)}

            return None
        finally:
            conn.close()

    def set(self, query_text: str, query_embedding: Optional[List[float]], result: Any) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            self._lru_evict(conn)
            cursor = conn.cursor()
            query_hash = self._hash(query_text)
            embedding_blob = json.dumps(query_embedding) if query_embedding else None
            now = time.time()
            cursor.execute(
                """INSERT OR REPLACE INTO query_cache
                   (query_hash, query_text, embedding_blob, result_json, created_at, accessed_at, access_count, hit_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_hash, query_text, embedding_blob, json.dumps(result), now, now, 1, 'exact')
            )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(access_count), AVG(access_count) FROM query_cache")
            total, total_hits, avg_hits = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM query_cache WHERE hit_type = 'exact'")
            exact_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM query_cache WHERE hit_type = 'semantic'")
            semantic_count = cursor.fetchone()[0]
            return {
                'total_entries': total or 0,
                'total_hits': total_hits or 0,
                'avg_hits_per_entry': round(avg_hits or 0, 2),
                'exact_hits': exact_count or 0,
                'semantic_hits': semantic_count or 0,
                'ttl_hours': self.ttl / 3600,
            }
        finally:
            conn.close()

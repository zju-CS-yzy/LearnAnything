"""
向量数据库抽象层（SQLite + numpy 实现，完全替代 ChromaDB 的 Rust 扩展）

线程安全：所有数据库操作在 sqlite3 连接内执行，天然线程安全。
无需 ChromaDB 的 Rust 原生扩展，从根本上规避 PyInstaller 打包后的多线程崩溃。

使用方式:
    store = VectorStore("chemistry_v1")
    store.add_documents([{"id": "1", "text": "...", "metadata": {}}])
    results = store.query("化学键", n_results=5)
"""

import hashlib
import json
import sqlite3
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any

from config.settings import VECTOR_DB_DIR, DEFAULT_EMBEDDING_DIM
from core.embedding import EmbeddingManager


class VectorStore:
    """向量数据库封装（SQLite + numpy 实现）。"""

    def __init__(self, collection_name: str, embedding_dim: int = DEFAULT_EMBEDDING_DIM):
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self._embedding = EmbeddingManager()
        self._db_path = VECTOR_DB_DIR / f"{collection_name}.db"
        self._conn = sqlite3.connect(str(self._db_path))
        self._ensure_table()

    # ========== 内部表管理 ==========

    def _ensure_table(self):
        """创建必要的数据表和索引。"""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                metadata TEXT,
                embedding TEXT
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_id ON documents(id)")
        self._conn.commit()

    # ========== 底层操作 ==========

    def get(self, limit=None, offset=None, include=None, where=None) -> Dict[str, Any]:
        """获取集合中的文档列表（兼容 ChromaDB 返回格式）。"""
        sql = "SELECT id, text, metadata FROM documents"
        params = []
        conditions = []

        if where:
            for key, condition in where.items():
                if isinstance(condition, dict) and "$eq" in condition:
                    conditions.append("json_extract(metadata, ?) = ?")
                    params.append(f"$.{key}")
                    params.append(condition["$eq"])
                elif isinstance(condition, dict) and "$ne" in condition:
                    conditions.append("json_extract(metadata, ?) != ?")
                    params.append(f"$.{key}")
                    params.append(condition["$ne"])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        if limit is not None:
            sql += f" LIMIT {limit}"
        if offset is not None:
            sql += f" OFFSET {offset}"

        cursor = self._conn.execute(sql, params)
        ids, docs, metas = [], [], []

        for row in cursor:
            ids.append(row[0])
            docs.append(row[1])
            metas.append(json.loads(row[2]) if row[2] else {})

        return {"ids": ids, "documents": docs, "metadatas": metas}

    def count(self) -> int:
        """返回集合文档数。"""
        cursor = self._conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    def delete(self, ids: List[str]) -> None:
        """按 ID 删除文档。"""
        for doc_id in ids:
            self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self._conn.commit()

    def list_all(self, limit: int = 50, offset: int = 0, where: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """列出所有文档片段（用于知识库可视化）。

        Args:
            limit: 返回数量上限
            offset: 偏移量
            where: 过滤条件（支持 metadata 字段的 $eq / $ne 过滤）
        """
        sql = "SELECT id, text, metadata FROM documents"
        params = []
        conditions = []

        if where:
            for key, condition in where.items():
                if isinstance(condition, dict) and "$eq" in condition:
                    conditions.append("json_extract(metadata, ?) = ?")
                    params.append(f"$.{key}")
                    params.append(condition["$eq"])
                elif isinstance(condition, dict) and "$ne" in condition:
                    conditions.append("json_extract(metadata, ?) != ?")
                    params.append(f"$.{key}")
                    params.append(condition["$ne"])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self._conn.execute(sql, params)
        results = []
        for row in cursor:
            meta = json.loads(row[2]) if row[2] else {}
            results.append({
                "id": row[0],
                "text": row[1],
                "metadata": meta,
            })
        return results

    def count(self, where: Optional[Dict] = None) -> int:
        """返回集合文档数，支持过滤条件。"""
        sql = "SELECT COUNT(*) FROM documents"
        params = []
        conditions = []

        if where:
            for key, condition in where.items():
                if isinstance(condition, dict) and "$eq" in condition:
                    conditions.append("json_extract(metadata, ?) = ?")
                    params.append(f"$.{key}")
                    params.append(condition["$eq"])
                elif isinstance(condition, dict) and "$ne" in condition:
                    conditions.append("json_extract(metadata, ?) != ?")
                    params.append(f"$.{key}")
                    params.append(condition["$ne"])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        cursor = self._conn.execute(sql, params)
        return cursor.fetchone()[0]

    def count_all(self) -> int:
        """返回集合文档总数（无过滤）。"""
        cursor = self._conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    # ========== 高级封装 ==========

    def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        """批量添加文档到知识库。"""
        if not documents:
            return

        texts = [d["text"] for d in documents]
        embeddings = self._embedding.embed(texts)

        for doc, emb in zip(documents, embeddings):
            doc_id = doc.get("id", self._generate_id(doc["text"]))
            meta = json.dumps(doc.get("metadata", {}), ensure_ascii=False)
            # 兼容 ndarray（HashEmbedding 返回 numpy array）
            if hasattr(emb, 'tolist'):
                emb = emb.tolist()
            emb_json = json.dumps(emb, ensure_ascii=False)
            self._conn.execute(
                "INSERT OR REPLACE INTO documents (id, text, metadata, embedding) VALUES (?, ?, ?, ?)",
                (doc_id, doc["text"], meta, emb_json)
            )
        self._conn.commit()

    def query(self, query_text: str, n_results: int = 10, where: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """向量检索：计算 query embedding 与所有文档的 cosine similarity，返回 Top-K。"""
        query_emb = np.array(self._embedding.embed_single(query_text), dtype=np.float32)
        cursor = self._conn.execute("SELECT id, text, metadata, embedding FROM documents")
        results = []

        for row in cursor:
            doc_id, text, meta_str, emb_str = row
            if not text or not emb_str:
                continue

            meta = json.loads(meta_str) if meta_str else {}
            if where and not self._matches_where(meta, where):
                continue

            emb = np.array(json.loads(emb_str), dtype=np.float32)
            norm_q = np.linalg.norm(query_emb)
            norm_d = np.linalg.norm(emb)
            if norm_q == 0 or norm_d == 0:
                continue

            sim = float(np.dot(query_emb, emb) / (norm_q * norm_d))
            results.append({
                "id": doc_id,
                "text": text,
                "metadata": meta,
                "distance": 1.0 - sim,
            })

        results.sort(key=lambda x: x["distance"])
        return results[:n_results]

    def _matches_where(self, metadata: Dict, where: Dict) -> bool:
        """简单的 where 过滤（支持 $eq / $ne 运算符）。"""
        for key, condition in where.items():
            if isinstance(condition, dict):
                if "$eq" in condition:
                    if metadata.get(key) != condition["$eq"]:
                        return False
                if "$ne" in condition:
                    if metadata.get(key) == condition["$ne"]:
                        return False
            else:
                if metadata.get(key) != condition:
                    return False
        return True

    # ========== 工具方法 ==========

    def _generate_id(self, text: str) -> str:
        """基于文本前200字符生成唯一 ID。"""
        return hashlib.md5(text[:200].encode()).hexdigest()[:16]

    def get_by_parent_id(self, parent_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 parent_id 查找对应的 Parent chunk。
        
        用于 Parent-Child 双层检索：命中 Child chunk 后，取出 Parent chunk 的完整上下文。
        
        Args:
            parent_id: Child chunk metadata 中的 parent_id
        
        Returns:
            Parent chunk 字典，或 None（未找到）
        """
        cursor = self._conn.execute(
            "SELECT id, text, metadata FROM documents WHERE id = ?",
            (parent_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "text": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
            }
        return None

    def query_with_parent_context(self, query_text: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """
        Parent-Child 双层检索：先搜索 Child chunk，再补充 Parent chunk 上下文。
        
        返回结果中每个 item 包含：
        - child: 命中的子 chunk
        - parent: 对应的父 chunk（完整页内容）
        - combined_text: 合并后的文本（父 + 子），可直接送入 LLM
        """
        child_results = self.query(query_text, n_results=n_results)
        
        enriched_results = []
        seen_parents = set()
        
        for child in child_results:
            parent_id = child.get("metadata", {}).get("parent_id")
            parent = None
            
            if parent_id and parent_id not in seen_parents:
                parent = self.get_by_parent_id(parent_id)
                if parent:
                    seen_parents.add(parent_id)
            
            combined_text = child["text"]
            if parent:
                combined_text = f"【引用来源: {parent['metadata'].get('document_name', '未知文档')} 第{parent['metadata'].get('page_number', '?')}页】\n\n{parent['text']}\n\n---\n\n【相关段落】\n{child['text']}"
            
            enriched_results.append({
                "child": child,
                "parent": parent,
                "combined_text": combined_text,
                "distance": child["distance"],
            })
        
        return enriched_results

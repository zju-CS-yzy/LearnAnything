#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学科管理模块 — v3 (LA-050-Phase3)

负责学科的 CRUD、自动识别、知识库隔离、学科文件夹管理。

LA-050-Phase3 改造说明:
- 新增 SubjectManager 类，支持自定义 db_path 和 kb_root（用户隔离）
- 原有模块级函数保留为向后兼容的包装（委托给默认全局实例）
- 现有代码无需修改即可继续工作

目录结构:
    <user_data_dir>/
        subjects.db              # 学科元数据
    <kb_root>/<subject_id>/
        raw/                     # 原始资料
        meta.json                # 学科元数据汇总
        visual/                  # 可视化数据（预留）
"""

import json
import sqlite3
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import KNOWLEDGE_BASE_DIR

# 用户数据目录（支持 PyInstaller 持久化）
from config.settings import DATA_ROOT
_user_data_dir = DATA_ROOT
_user_data_dir.mkdir(parents=True, exist_ok=True)

# 知识库根目录
KB_ROOT = KNOWLEDGE_BASE_DIR
KB_ROOT.mkdir(parents=True, exist_ok=True)


# LA-051: 学科可见性枚举
VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"
VISIBILITY_GROUP = "group"


# ==================== SubjectManager 类 (LA-050-Phase3) ====================

class SubjectManager:
    """学科管理器（支持用户级路径参数化）。"""

    def __init__(self, db_path: Optional[str] = None, kb_root: Optional[str] = None):
        """
        Args:
            db_path: 学科元数据数据库路径（默认 ~/.learnanything/subjects.db）
            kb_root: 知识库根目录（默认 KNOWLEDGE_BASE_DIR）
        """
        self.db_path = Path(db_path) if db_path else _user_data_dir / "subjects.db"
        self.kb_root = Path(kb_root) if kb_root else KB_ROOT
        self.kb_root.mkdir(parents=True, exist_ok=True)

    def _get_conn(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        self._ensure_table(conn)
        return conn

    @staticmethod
    def _ensure_table(conn: sqlite3.Connection):
        # 基础 subjects 表（LA-050）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                keywords TEXT,
                created_at TEXT,
                document_count INTEGER DEFAULT 0,
                raw_files_count INTEGER DEFAULT 0
            )
        ''')
        # LA-051: 向后兼容添加 owner_id / visibility / updated_at
        for col, dtype in [
            ("document_count", "INTEGER DEFAULT 0"),
            ("raw_files_count", "INTEGER DEFAULT 0"),
            ("owner_id", "TEXT"),
            ("visibility", "TEXT DEFAULT 'public'"),
            ("updated_at", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE subjects ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError:
                pass  # 已存在
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subject_documents (
                id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                source_name TEXT,
                source_path TEXT,
                chunk_count INTEGER DEFAULT 0,
                imported_at TEXT
            )
        ''')
        try:
            conn.execute('ALTER TABLE subject_documents ADD COLUMN source_path TEXT')
        except sqlite3.OperationalError:
            pass
        conn.commit()

    # ---------- 学科文件夹管理 ----------

    def get_subject_dir(self, subject_id: str) -> Path:
        return self.kb_root / subject_id

    def ensure_subject_dir(self, subject_id: str) -> Path:
        subj_dir = self.get_subject_dir(subject_id)
        (subj_dir / "raw").mkdir(parents=True, exist_ok=True)
        (subj_dir / "visual").mkdir(parents=True, exist_ok=True)
        return subj_dir

    def save_raw_file(self, subject_id: str, filename: str, content: bytes) -> Path:
        raw_dir = self.ensure_subject_dir(subject_id) / "raw"
        target = raw_dir / filename
        counter = 1
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        while target.exists():
            target = raw_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        target.write_bytes(content)
        return target

    def list_raw_files(self, subject_id: str) -> List[Dict[str, Any]]:
        raw_dir = self.get_subject_dir(subject_id) / "raw"
        if not raw_dir.exists():
            return []
        files = []
        for f in raw_dir.iterdir():
            if f.is_file():
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        return sorted(files, key=lambda x: x["modified"], reverse=True)

    def delete_raw_file(self, subject_id: str, filename: str) -> bool:
        target = self.get_subject_dir(subject_id) / "raw" / filename
        if target.exists():
            target.unlink()
            return True
        return False

    def get_subject_meta(self, subject_id: str) -> Dict[str, Any]:
        subj = self.get_subject(subject_id)
        if not subj:
            return {}
        raw_files = self.list_raw_files(subject_id)
        subj_dir = self.get_subject_dir(subject_id)
        return {
            **subj,
            "raw_files": raw_files,
            "raw_files_count": len(raw_files),
            "dir_exists": subj_dir.exists(),
            "dir_path": str(subj_dir),
        }

    # ---------- 学科 CRUD ----------

    def create_subject(self, id: str, name: str, description: str = "", keywords: List[str] = None,
                       owner_id: str = "system", visibility: str = VISIBILITY_PUBLIC) -> Dict[str, Any]:
        """
        创建学科（LA-051: 新增 owner_id 和 visibility）
        
        Args:
            id: 学科唯一标识
            name: 显示名称
            description: 描述
            keywords: 关键词列表
            owner_id: 所有者用户ID（默认 "system"）
            visibility: 可见性（public/private/group）
        """
        conn = self._get_conn()
        try:
            clean_id = "".join(c for c in id if c.isalnum() or c in "_-").lower()
            if not clean_id:
                clean_id = f"sub_{uuid.uuid4().hex[:8]}"
            now = datetime.now().isoformat()
            conn.execute(
                """INSERT OR REPLACE INTO subjects
                   (id, name, description, keywords, created_at, updated_at, owner_id, visibility)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (clean_id, name, description, json.dumps(keywords or [], ensure_ascii=False),
                 now, now, owner_id, visibility),
            )
            conn.commit()
            self.ensure_subject_dir(clean_id)
            return self.get_subject(clean_id)
        finally:
            conn.close()

    def get_subject(self, subject_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
            if row:
                return self._row_to_dict(row)
            return None
        finally:
            conn.close()

    def list_subjects(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM subjects ORDER BY created_at DESC").fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def delete_subject(self, subject_id: str) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM subject_documents WHERE subject_id = ?", (subject_id,))
            deleted_docs = cursor.rowcount
            print(f"[SubjectDelete] 删除 {deleted_docs} 条 subject_documents 记录")
            conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
            conn.commit()

            # 删除学科文件夹
            subj_dir = self.get_subject_dir(subject_id)
            if subj_dir.exists():
                shutil.rmtree(subj_dir)
                print(f"[SubjectDelete] 删除学科文件夹: {subj_dir}")

            # 删除向量数据库
            from config.settings import VECTOR_DB_DIR
            vec_db = VECTOR_DB_DIR / f"{subject_id}_v1.db"
            if vec_db.exists():
                vec_db.unlink()
                print(f"[SubjectDelete] 删除向量数据库: {vec_db}")
            for suffix in ["-wal", "-shm", "-journal"]:
                extra = vec_db.parent / f"{vec_db.name}{suffix}"
                if extra.exists():
                    extra.unlink()
                    print(f"[SubjectDelete] 删除向量数据库附属文件: {extra}")

            # 删除图数据库
            try:
                from core.graph_store import GraphStore
                store = GraphStore(f"{subject_id}_v1")
                store.delete_all()
                print(f"[SubjectDelete] GraphStore.delete_all() succeeded for {subject_id}")
            except Exception as e:
                print(f"[SubjectDelete] GraphStore.delete_all() failed (fallback): {e}")
                graph_db_dir = KNOWLEDGE_BASE_DIR / "graph_db"
                graph_db_file = graph_db_dir / f"{subject_id}_v1_graph"
                if graph_db_file.exists():
                    graph_db_file.unlink()
                    print(f"[SubjectDelete] 手动删除图数据库: {graph_db_file}")
                wal_dir = graph_db_dir / f"{subject_id}_v1_graph.wal"
                if wal_dir.exists():
                    shutil.rmtree(wal_dir)

            # 删除图片和缩略图目录
            img_dir = KNOWLEDGE_BASE_DIR / f"{subject_id}_v1_images"
            if img_dir.exists():
                shutil.rmtree(img_dir)
            thumb_dir = KNOWLEDGE_BASE_DIR / f"{subject_id}_v1_thumbnails"
            if thumb_dir.exists():
                shutil.rmtree(thumb_dir)

            return True
        except Exception as e:
            print(f"[SubjectDelete] Error: {e}")
            return False
        finally:
            conn.close()

    def update_document_count(self, subject_id: str, count: int):
        conn = self._get_conn()
        try:
            conn.execute("UPDATE subjects SET document_count = ? WHERE id = ?", (count, subject_id))
            conn.commit()
        finally:
            conn.close()

    def update_raw_files_count(self, subject_id: str):
        count = len(self.list_raw_files(subject_id))
        conn = self._get_conn()
        try:
            conn.execute("UPDATE subjects SET raw_files_count = ? WHERE id = ?", (count, subject_id))
            conn.commit()
        finally:
            conn.close()

    def record_import(self, subject_id: str, source_name: str, source_path: str = "", chunk_count: int = 0):
        conn = self._get_conn()
        try:
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"
            conn.execute(
                "INSERT INTO subject_documents (id, subject_id, source_name, source_path, chunk_count, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, subject_id, source_name, source_path, chunk_count, datetime.now().isoformat()),
            )
            total_chunks = conn.execute("SELECT SUM(chunk_count) FROM subject_documents WHERE subject_id = ?", (subject_id,)).fetchone()[0] or 0
            total_files = conn.execute("SELECT COUNT(*) FROM subject_documents WHERE subject_id = ?", (subject_id,)).fetchone()[0] or 0
            # LA-051: 防御性更新，兼容旧表结构
            try:
                conn.execute("UPDATE subjects SET document_count = ?, raw_files_count = ? WHERE id = ?", (total_chunks, total_files, subject_id))
            except sqlite3.OperationalError as e:
                print(f"[SubjectManager] 更新计数失败(兼容旧表): {e}")
            conn.commit()
        finally:
            conn.close()

    # ---------- 自动识别 ----------

    def detect_subject(self, query: str) -> Optional[str]:
        try:
            import jieba
        except ImportError:
            words = query.lower().split()
            return self._match_keywords(words)
        words = list(jieba.cut(query.lower()))
        return self._match_keywords(words)

    def _match_keywords(self, words: List[str]) -> Optional[str]:
        subjects = self.list_subjects()
        if not subjects:
            return None
        best_match = None
        best_score = 0
        for sub in subjects:
            keywords = sub.get("keywords", [])
            if not keywords:
                continue
            score = 0
            for kw in keywords:
                kw_lower = kw.lower()
                for w in words:
                    if kw_lower in w or w in kw_lower:
                        score += 1
            if score > best_score:
                best_score = score
                best_match = sub["id"]
        return best_match if best_score >= 1 else None

    # ---------- 启动初始化 ----------

    def ensure_default_subjects(self):
        print(f"[SubjectManager] DB path: {self.db_path}")
        print(f"[SubjectManager] KB root: {self.kb_root}")
        subjects = self.list_subjects()
        print(f"[SubjectManager] Loaded {len(subjects)} subjects: {[s['id'] for s in subjects]}")
        if not subjects:
            self.create_subject(
                id="generic",
                name="通用",
                description="默认通用知识库",
                keywords=["通用", "知识", "学习"],
            )
            print("[SubjectManager] Created default 'generic' subject")

    # ---------- 工具函数 ----------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        if d.get("keywords"):
            try:
                d["keywords"] = json.loads(d["keywords"])
            except:
                d["keywords"] = []
        # LA-051: 新字段默认值（处理数据库 NULL）
        if d.get("owner_id") is None:
            d["owner_id"] = "system"
        if d.get("visibility") is None:
            d["visibility"] = VISIBILITY_PUBLIC
        if d.get("updated_at") is None:
            d["updated_at"] = d.get("created_at", "")
        return d


# ==================== 全局默认实例（向后兼容）====================

_default_subject_manager = SubjectManager()

# 保留原有模块级函数，委托给默认实例

SUBJECT_DB_PATH = _user_data_dir / "subjects.db"


def _get_conn():
    return _default_subject_manager._get_conn()


def _ensure_table(conn: sqlite3.Connection):
    return SubjectManager._ensure_table(conn)


def get_subject_dir(subject_id: str) -> Path:
    return _default_subject_manager.get_subject_dir(subject_id)


def ensure_subject_dir(subject_id: str) -> Path:
    return _default_subject_manager.ensure_subject_dir(subject_id)


def save_raw_file(subject_id: str, filename: str, content: bytes) -> Path:
    return _default_subject_manager.save_raw_file(subject_id, filename, content)


def list_raw_files(subject_id: str) -> List[Dict[str, Any]]:
    return _default_subject_manager.list_raw_files(subject_id)


def delete_raw_file(subject_id: str, filename: str) -> bool:
    return _default_subject_manager.delete_raw_file(subject_id, filename)


def get_subject_meta(subject_id: str) -> Dict[str, Any]:
    return _default_subject_manager.get_subject_meta(subject_id)


def create_subject(id: str, name: str, description: str = "", keywords: List[str] = None) -> Dict[str, Any]:
    return _default_subject_manager.create_subject(id, name, description, keywords)


def get_subject(subject_id: str) -> Optional[Dict[str, Any]]:
    return _default_subject_manager.get_subject(subject_id)


def list_subjects() -> List[Dict[str, Any]]:
    return _default_subject_manager.list_subjects()


def delete_subject(subject_id: str) -> bool:
    return _default_subject_manager.delete_subject(subject_id)


def update_document_count(subject_id: str, count: int):
    return _default_subject_manager.update_document_count(subject_id, count)


def update_raw_files_count(subject_id: str):
    return _default_subject_manager.update_raw_files_count(subject_id)


def record_import(subject_id: str, source_name: str, source_path: str = "", chunk_count: int = 0):
    return _default_subject_manager.record_import(subject_id, source_name, source_path, chunk_count)


def detect_subject(query: str) -> Optional[str]:
    return _default_subject_manager.detect_subject(query)


def ensure_default_subjects():
    return _default_subject_manager.ensure_default_subjects()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return SubjectManager._row_to_dict(row)

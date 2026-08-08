#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学科管理模块 — v4 (LA-051-DIR)

目录结构（统一 LA-051-STRUCT）：
    data/knowledge_base/
        Share/<subject_id>/        ← 公有学科
            raw/
            media/images/
            media/thumbnails/
            vector.db
            graph/
        Users/<user_id>/<subject_id>/  ← 私有学科
            raw/
            media/images/
            media/thumbnails/
            vector.db
            graph/
    data/
        subjects.db                 ← 全局学科注册表
        users/<user_id>/subjects.db ← 用户私有学科注册表

所有目录创建均通过 config.settings 辅助函数，确保路径一致性。
"""

import json
import sqlite3
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# LA-051-DIR: 统一路径入口
from config.settings import (
    DATA_ROOT,
    get_share_subject_dir,
    get_user_subject_dir,
    get_subject_vector_db_path,
    get_subject_graph_db_path,
    get_subject_images_dir,
    get_subject_thumbnails_dir,
)

# LA-051: 学科可见性枚举
VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"
VISIBILITY_GROUP = "group"

# LA-051-DIR-FIX: GraphStore 用于学科删除时清理图数据库
from core.graph_store import GraphStore


# ==================== SubjectManager 类 (LA-051-DIR) ====================

class SubjectManager:
    """学科管理器（统一路径，支持用户隔离）。"""

    def __init__(self, db_path: Optional[str] = None, kb_root: Optional[str] = None):
        """
        Args:
            db_path: 学科元数据数据库路径（默认 data/subjects.db）
            kb_root: 已废弃参数（LA-051-DIR: 路径由 settings.py 统一管理，忽略此参数）
        """
        self.db_path = Path(db_path) if db_path else DATA_ROOT / "subjects.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ---------- 学科路径（统一通过 settings.py） ----------

    @staticmethod
    def get_subject_dir(subject_id: str, owner_id: str = "system",
                         visibility: str = VISIBILITY_PUBLIC) -> Path:
        """
        获取学科目录。
        LA-051-DIR: 根据 owner_id 和 visibility 选择正确路径。
        """
        # 用户私有学科 → Users/<user>/<subject>/
        if visibility == VISIBILITY_PRIVATE and owner_id and owner_id != "system":
            return get_user_subject_dir(owner_id, subject_id)
        # 公有/组内学科 → Share/<subject>/
        return get_share_subject_dir(subject_id)

    @staticmethod
    def ensure_subject_dir(subject_id: str, owner_id: str = "system",
                             visibility: str = VISIBILITY_PUBLIC) -> Path:
        """
        确保学科目录存在（创建完整结构）。
        LA-051-DIR: 通过 settings.py 辅助函数自动创建 raw/media/。
        """
        return SubjectManager.get_subject_dir(subject_id, owner_id, visibility)

    # ---------- 内部数据库 ----------

    def _get_conn(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        self._ensure_table(conn)
        return conn

    @staticmethod
    def _ensure_table(conn: sqlite3.Connection):
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                keywords TEXT,
                created_at TEXT,
                document_count INTEGER DEFAULT 0,
                raw_files_count INTEGER DEFAULT 0,
                owner_id TEXT,
                visibility TEXT DEFAULT 'public',
                updated_at TEXT
            )
        ''')
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
        conn.commit()

    # ---------- 原始文件管理 ----------

    def save_raw_file(self, subject_id: str, filename: str, content: bytes,
                      owner_id: str = "system", visibility: str = VISIBILITY_PUBLIC) -> Path:
        """保存原始文件到学科 raw/ 目录。"""
        raw_dir = self.get_subject_dir(subject_id, owner_id, visibility) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        target = raw_dir / filename
        counter = 1
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        while target.exists():
            target = raw_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        target.write_bytes(content)
        return target

    def list_raw_files(self, subject_id: str, owner_id: str = "system",
                       visibility: str = VISIBILITY_PUBLIC) -> List[Dict[str, Any]]:
        """列出学科 raw/ 目录下的文件。"""
        raw_dir = self.get_subject_dir(subject_id, owner_id, visibility) / "raw"
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

    def delete_raw_file(self, subject_id: str, filename: str,
                        owner_id: str = "system", visibility: str = VISIBILITY_PUBLIC) -> bool:
        """删除学科 raw/ 目录下的文件。"""
        target = self.get_subject_dir(subject_id, owner_id, visibility) / "raw" / filename
        if target.exists():
            target.unlink()
            return True
        return False

    def get_subject_meta(self, subject_id: str) -> Dict[str, Any]:
        """获取学科完整元数据。"""
        subj = self.get_subject(subject_id)
        if not subj:
            return {}
        raw_files = self.list_raw_files(
            subject_id,
            owner_id=subj.get("owner_id", "system"),
            visibility=subj.get("visibility", VISIBILITY_PUBLIC),
        )
        subj_dir = self.get_subject_dir(
            subject_id,
            owner_id=subj.get("owner_id", "system"),
            visibility=subj.get("visibility", VISIBILITY_PUBLIC),
        )
        return {
            **subj,
            "raw_files": raw_files,
            "raw_files_count": len(raw_files),
            "dir_exists": subj_dir.exists(),
            "dir_path": str(subj_dir),
        }

    # ---------- 学科 CRUD ----------

    def create_subject(self, id: str, name: str, description: str = "",
                       keywords: List[str] = None,
                       owner_id: str = "system",
                       visibility: str = VISIBILITY_PUBLIC) -> Dict[str, Any]:
        """
        创建学科（LA-051-DIR: 使用统一路径入口）。

        Args:
            id: 学科唯一标识
            name: 显示名称
            description: 描述
            keywords: 关键词列表
            owner_id: 所有者用户ID
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
            # LA-051-DIR: 创建学科目录（通过 settings.py，自动创建完整结构）
            self.ensure_subject_dir(clean_id, owner_id, visibility)
            return self.get_subject(clean_id)
        finally:
            conn.close()

    def get_subject(self, subject_id: str) -> Optional[Dict[str, Any]]:
        """获取学科信息。"""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
            if row:
                return self._row_to_dict(row)
            return None
        finally:
            conn.close()

    def list_subjects(self) -> List[Dict[str, Any]]:
        """列出所有学科。"""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM subjects ORDER BY created_at DESC").fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def delete_subject(self, subject_id: str, owner_id: str = None, visibility: str = None) -> bool:
        """
        删除学科及其所有数据。
        LA-051-DIR: 支持传入 owner_id/visibility。
        
        删除顺序（关键！避免文件句柄冲突）：
        1. 先关闭并删除 GraphStore（释放 KùzuDB 文件句柄）
        2. 删除 VectorStore 数据库文件
        3. 删除数据库记录
        4. 最后删除学科目录
        """
        # 确定路径参数
        if owner_id is None or visibility is None:
            subj = self.get_subject(subject_id)
            if subj:
                owner_id = subj.get("owner_id", "system")
                visibility = subj.get("visibility", VISIBILITY_PUBLIC)
            else:
                owner_id = owner_id or "system"
                visibility = visibility or VISIBILITY_PUBLIC

        # 1. 先关闭并删除 GraphStore（释放文件句柄）
        # LA-051-DIR-FIX: 需要删除所有可能的图数据库路径，因为不同版本代码可能使用不同路径
        from config.settings import GRAPH_DB_DIR

        # 清除缓存中的 GraphStore 实例（防止下次创建同名学科时返回旧的）
        # 惰性导入避免循环依赖：core → app
        try:
            import app.backend_api as api_module
            cache_key = f"{subject_id}_v1"
            if hasattr(api_module, '_graph_store_cache') and cache_key in api_module._graph_store_cache:
                del api_module._graph_store_cache[cache_key]
                print(f"[SubjectDelete] 清除 GraphStore 缓存: {cache_key}")
        except Exception as e:
            print(f"[SubjectDelete] 清除 GraphStore 缓存失败（非阻塞）: {e}")

        # 路径1: 新学科内聚路径（LA-051-DIR）
        try:
            graph_db_path_new = get_subject_graph_db_path(
                subject_id, owner_id if visibility == VISIBILITY_PRIVATE else None
            )
            if graph_db_path_new.exists():
                store = GraphStore(subject_id, db_path=str(graph_db_path_new))
                store.delete_all()
                print(f"[SubjectDelete] GraphStore(新路径) 已删除: {graph_db_path_new}")
        except Exception as e:
            print(f"[SubjectDelete] GraphStore(新路径) 删除失败（非阻塞）: {e}")

        # 路径2: 旧默认路径（GRAPH_DB_DIR / {subject}_v1_graph）
        # 这是 _graph_store_cache 中 GraphStore(key) 无 db_path 时使用的路径
        try:
            graph_db_path_old = GRAPH_DB_DIR / f"{subject_id}_v1_graph"
            if graph_db_path_old.exists():
                store = GraphStore(subject_id, db_path=str(graph_db_path_old))
                store.delete_all()
                print(f"[SubjectDelete] GraphStore(旧路径) 已删除: {graph_db_path_old}")
        except Exception as e:
            print(f"[SubjectDelete] GraphStore(旧路径) 删除失败（非阻塞）: {e}")

        # 2. 删除 VectorStore 数据库文件
        try:
            vec_db = get_subject_vector_db_path(
                subject_id, owner_id if visibility == VISIBILITY_PRIVATE else None
            )
            if vec_db.exists():
                vec_db.unlink()
                print(f"[SubjectDelete] 删除向量数据库: {vec_db}")
            for suffix in ["-wal", "-shm", "-journal"]:
                extra = vec_db.parent / f"{vec_db.name}{suffix}"
                if extra.exists():
                    extra.unlink()
        except Exception as e:
            print(f"[SubjectDelete] 向量数据库删除失败（非阻塞）: {e}")

        # 3. 删除数据库记录
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM subject_documents WHERE subject_id = ?", (subject_id,))
            print(f"[SubjectDelete] 删除 {cursor.rowcount} 条 subject_documents 记录")
            conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
            conn.commit()
        except Exception as e:
            print(f"[SubjectDelete] 数据库记录删除失败: {e}")
        finally:
            conn.close()

        # 4. 最后删除学科目录（此时所有文件句柄已释放）
        try:
            subj_dir = self.get_subject_dir(subject_id, owner_id, visibility)
            if subj_dir.exists():
                # Windows: 使用 onerror 处理只读文件
                import stat
                def _onerror(func, path, exc_info):
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                shutil.rmtree(subj_dir, onerror=_onerror)
                print(f"[SubjectDelete] 删除学科目录: {subj_dir}")
        except Exception as e:
            print(f"[SubjectDelete] 学科目录删除失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        return True

    def update_document_count(self, subject_id: str, count: int):
        conn = self._get_conn()
        try:
            conn.execute("UPDATE subjects SET document_count = ? WHERE id = ?", (count, subject_id))
            conn.commit()
        finally:
            conn.close()

    def update_raw_files_count(self, subject_id: str):
        subj = self.get_subject(subject_id)
        count = len(self.list_raw_files(
            subject_id,
            owner_id=subj.get("owner_id", "system") if subj else "system",
            visibility=subj.get("visibility", VISIBILITY_PUBLIC) if subj else VISIBILITY_PUBLIC,
        ))
        conn = self._get_conn()
        try:
            conn.execute("UPDATE subjects SET raw_files_count = ? WHERE id = ?", (count, subject_id))
            conn.commit()
        finally:
            conn.close()

    def record_import(self, subject_id: str, source_name: str,
                      source_path: str = "", chunk_count: int = 0):
        conn = self._get_conn()
        try:
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"
            conn.execute(
                "INSERT INTO subject_documents (id, subject_id, source_name, source_path, chunk_count, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, subject_id, source_name, source_path, chunk_count, datetime.now().isoformat()),
            )
            total_chunks = conn.execute(
                "SELECT SUM(chunk_count) FROM subject_documents WHERE subject_id = ?", (subject_id,)
            ).fetchone()[0] or 0
            total_files = conn.execute(
                "SELECT COUNT(*) FROM subject_documents WHERE subject_id = ?", (subject_id,)
            ).fetchone()[0] or 0
            conn.execute(
                "UPDATE subjects SET document_count = ?, raw_files_count = ? WHERE id = ?",
                (total_chunks, total_files, subject_id),
            )
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

    # ---------- 工具函数 ----------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        if d.get("keywords"):
            try:
                d["keywords"] = json.loads(d["keywords"])
            except:
                d["keywords"] = []
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
# 注意：这些函数不传递 owner_id/visibility，仅用于全局学科（向后兼容）

SUBJECT_DB_PATH = DATA_ROOT / "subjects.db"


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


def create_subject(id: str, name: str, description: str = "",
                   keywords: List[str] = None, owner_id: str = "system",
                   visibility: str = VISIBILITY_PUBLIC) -> Dict[str, Any]:
    return _default_subject_manager.create_subject(id, name, description, keywords, owner_id, visibility)


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


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return SubjectManager._row_to_dict(row)

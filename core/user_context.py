#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UserContext - 用户上下文

LA-051-DIR: 统一路径入口，所有学科相关路径均通过 config.settings 辅助函数。

目录结构：
    data/knowledge_base/
        Share/<subject>/          ← 公有学科
        Users/<user_id>/<subject>/ ← 用户私有学科
    data/users/<user_id>/
        user_states.db
        subjects.db
"""
import sqlite3
from pathlib import Path
from typing import Optional, Any

# LA-051-DIR: 统一路径入口
from config.settings import (
    USERS_KB_DIR,
    get_user_subject_dir,
    get_subject_vector_db_path,
    get_subject_graph_db_path,
    get_subject_images_dir,
    get_subject_thumbnails_dir,
)
from core.user_manager import get_user_manager


class UserContext:
    """
    用户上下文：封装当前用户的所有数据访问

    核心设计：
    1. 用户数据物理隔离（各目录独立）
    2. 所有路径统一通过 settings.py 辅助函数（确保一致性）
    3. 延迟初始化（按需创建数据库连接）
    """

    def __init__(self, user_id: str, user_manager: Optional[Any] = None):
        self.user_id = user_id
        self._user_mgr = user_manager or get_user_manager()
        self._data_dir = self._user_mgr.get_user_data_dir(user_id)

        # 延迟初始化
        self._dialog_mgr = None
        self._state_store = None
        self._subject_mgr = None
        self._permission_mgr = None
        self._vector_stores = {}
        self._graph_stores = {}

    # ── 属性访问 ──

    @property
    def user_info(self) -> Optional[dict]:
        """获取用户信息"""
        return self._user_mgr.get_user(self.user_id)

    @property
    def display_name(self) -> str:
        """获取用户显示昵称"""
        info = self.user_info
        if info:
            return info.get("display_name") or info.get("username") or self.user_id
        return self.user_id

    @property
    def data_dir(self) -> Path:
        """获取用户数据根目录"""
        return self._data_dir

    # ── 用户状态数据库 ──

    def _get_states_conn(self) -> sqlite3.Connection:
        """获取用户状态数据库连接"""
        db_path = self._user_mgr.get_user_states_db(self.user_id)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── 对话管理器 ──

    @property
    def dialog_manager(self):
        """获取用户隔离的对话管理器"""
        if self._dialog_mgr is None:
            from core.dialog_context import DialogContextManager
            db_path = self._user_mgr.get_user_states_db(self.user_id)
            self._dialog_mgr = DialogContextManager(db_path=str(db_path))
        return self._dialog_mgr

    # ── 用户状态存储 ──

    @property
    def state_store(self):
        """获取用户隔离的状态存储"""
        if self._state_store is None:
            from core.graph_education.user_state_store import UserStateStore
            db_path = self._user_mgr.get_user_states_db(self.user_id)
            self._state_store = UserStateStore(db_path=str(db_path))
        return self._state_store

    # ── 知识库根目录 ──

    @property
    def kb_root(self) -> Path:
        """获取用户知识库根目录（LA-051-DIR: knowledge_base/Users/<user_id>/）"""
        # LA-051-DIR: 用户私有学科统一放在 knowledge_base/Users/<user_id>/
        d = USERS_KB_DIR / self.user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_subject_kb_dir(self, subject: str) -> Path:
        """获取指定学科的知识库目录（LA-051-DIR: 使用 settings 辅助函数）"""
        return get_user_subject_dir(self.user_id, subject)

    # ── 向量存储 ──

    def get_user_vector_store(self, subject: str):
        """
        LA-051-DIR: 获取用户隔离的 VectorStore。
        路径: knowledge_base/Users/<user_id>/<subject>/vector.db
        """
        from core.vector_store import VectorStore
        db_path = get_subject_vector_db_path(subject, self.user_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return VectorStore(subject, db_path=str(db_path))

    def get_user_graph_store(self, subject: str):
        """
        LA-051-DIR: 获取用户隔离的 GraphStore。
        路径: knowledge_base/Users/<user_id>/<subject>/graph/
        """
        from core.graph_store import GraphStore
        db_path = get_subject_graph_db_path(subject, self.user_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return GraphStore(subject, db_path=str(db_path))

    def get_user_quiz_bank_path(self, subject: str) -> Path:
        """LA-051-DIR: 获取用户隔离的 quiz bank 路径"""
        kb = self.kb_root / subject
        kb.mkdir(parents=True, exist_ok=True)
        return kb / f"{subject}_quiz_bank.db"

    def get_user_images_dir(self, subject: str) -> Path:
        """LA-051-DIR: 获取用户隔离的图片目录（新结构）"""
        return get_subject_images_dir(subject, self.user_id)

    def get_user_thumbnails_dir(self, subject: str) -> Path:
        """LA-051-DIR: 获取用户隔离的缩略图目录（新结构）"""
        return get_subject_thumbnails_dir(subject, self.user_id)

    # ── 图存储（向后兼容）──

    def get_vector_store(self, subject: str, prefer_private: bool = True):
        """获取向量存储（向后兼容：优先私有 → fallback 共享）"""
        cache_key = f"{subject}_{prefer_private}"
        if cache_key in self._vector_stores:
            return self._vector_stores[cache_key]

        from core.vector_store import VectorStore

        if prefer_private:
            # 优先查用户私有
            user_vdb = get_subject_vector_db_path(subject, self.user_id)
            if user_vdb.exists():
                store = VectorStore(subject, db_path=str(user_vdb))
                self._vector_stores[cache_key] = store
                return store

        # Fallback 到共享
        share_vdb = get_subject_vector_db_path(subject, None)
        if share_vdb.exists():
            store = VectorStore(subject, db_path=str(share_vdb))
        else:
            store = VectorStore(subject)
        self._vector_stores[cache_key] = store
        return store

    def get_or_create_private_vector_store(self, subject: str):
        """获取或创建用户私有向量存储"""
        from core.vector_store import VectorStore
        user_vdb = get_subject_vector_db_path(subject, self.user_id)
        user_vdb.parent.mkdir(parents=True, exist_ok=True)
        store = VectorStore(subject, db_path=str(user_vdb))
        cache_key = f"{subject}_True"
        self._vector_stores[cache_key] = store
        return store

    def get_graph_store(self, subject: str, prefer_private: bool = True):
        """获取图存储（向后兼容）"""
        cache_key = f"graph_{subject}_{prefer_private}"
        if cache_key in self._graph_stores:
            return self._graph_stores[cache_key]

        from core.graph_store import GraphStore

        if prefer_private:
            user_gdb = get_subject_graph_db_path(subject, self.user_id)
            if user_gdb.exists():
                store = GraphStore(subject, db_path=str(user_gdb))
                self._graph_stores[cache_key] = store
                return store

        share_gdb = get_subject_graph_db_path(subject, None)
        if share_gdb.exists():
            store = GraphStore(subject, db_path=str(share_gdb))
        else:
            store = GraphStore(subject)
        self._graph_stores[cache_key] = store
        return store

    def get_or_create_private_graph_store(self, subject: str):
        """获取或创建用户私有图存储"""
        from core.graph_store import GraphStore
        user_gdb = get_subject_graph_db_path(subject, self.user_id)
        user_gdb.parent.mkdir(parents=True, exist_ok=True)
        store = GraphStore(subject, db_path=str(user_gdb))
        cache_key = f"graph_{subject}_True"
        self._graph_stores[cache_key] = store
        return store

    # ── 学科管理 ──

    @property
    def subject_manager(self):
        """获取用户隔离的学科管理器"""
        if self._subject_mgr is None:
            from core.subject_manager import SubjectManager
            db_path = self._user_mgr.get_user_subjects_db(self.user_id)
            # LA-051-DIR: SubjectManager 不再接收 kb_root（路径由 settings 统一管理）
            self._subject_mgr = SubjectManager(db_path=str(db_path))
        return self._subject_mgr

    # ── 权限管理 ──

    @property
    def permission_manager(self):
        """获取权限管理器（LA-051）"""
        if self._permission_mgr is None:
            from core.permission_manager import PermissionManager
            self._permission_mgr = PermissionManager()
        return self._permission_mgr

    # ── 学科列表（向后兼容）──

    def list_accessible_subjects(self) -> list:
        """列出用户可访问的所有学科"""
        subjects = []

        # 用户私有学科
        user_subjects_db = self._user_mgr.get_user_subjects_db(self.user_id)
        if user_subjects_db.exists():
            conn = sqlite3.connect(str(user_subjects_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, description, is_private FROM subjects")
            for row in cursor.fetchall():
                subjects.append({
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "type": "private",
                    "is_private": bool(row["is_private"]),
                })
            conn.close()

        # 共享学科
        from config.settings import SHARE_KB_DIR
        if SHARE_KB_DIR.exists():
            for item in SHARE_KB_DIR.iterdir():
                if item.is_dir():
                    subjects.append({
                        "id": item.name,
                        "name": item.name,
                        "description": "",
                        "type": "shared",
                        "is_private": False,
                    })

        return subjects

    def create_private_subject(self, subject_id: str, name: str, description: str = "") -> bool:
        """创建用户私有学科"""
        db_path = self._user_mgr.get_user_subjects_db(self.user_id)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            from datetime import datetime
            now = datetime.now().isoformat()
            conn.execute("""
                INSERT INTO subjects (id, name, description, is_private, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (subject_id, name, description, 1, now))
            conn.commit()
            # LA-051-DIR: 通过 settings 创建目录
            get_user_subject_dir(self.user_id, subject_id)
            print(f"[UserContext] 创建私有学科: {subject_id} (user={self.user_id})")
            return True
        except sqlite3.IntegrityError:
            print(f"[UserContext] 私有学科已存在: {subject_id}")
            return False
        finally:
            conn.close()

    # ── 缓存目录 ──

    def get_cache_dir(self) -> Path:
        """获取用户缓存目录"""
        return self._user_mgr.get_user_cache_dir(self.user_id)

    # ── 统计信息 ──

    def get_stats(self) -> dict:
        """获取用户统计信息"""
        stats = {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "data_dir": str(self.data_dir),
        }
        try:
            conn = self._get_states_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM evaluation_history WHERE user_id = ?", (self.user_id,))
            stats["evaluations"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM wrong_answers WHERE user_id = ?", (self.user_id,))
            stats["wrong_answers"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM dialog_sessions")
            stats["dialog_sessions"] = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            print(f"[UserContext] 统计信息获取失败: {e}")
            stats["evaluations"] = 0
            stats["wrong_answers"] = 0
            stats["dialog_sessions"] = 0
        return stats

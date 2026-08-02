#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UserContext - 用户上下文

LA-050: 多用户隔离架构基础设施
封装当前用户的所有数据访问，实现共享/私有学科的自动 fallback

使用方式:
    ctx = UserContext("alice")
    # 获取该用户隔离的对话管理器
    dialog_mgr = ctx.dialog_manager
    # 获取该用户的向量存储（自动 fallback 共享）
    store = ctx.get_vector_store("rag")
"""
import sqlite3
from pathlib import Path
from typing import Optional, Any

from config.settings import (
    KNOWLEDGE_BASE_DIR, PROJECT_ROOT,
    get_subject_vector_db_path, get_subject_graph_db_path,
    get_subject_images_dir, get_subject_thumbnails_dir,
)
from core.user_manager import get_user_manager


class UserContext:
    """
    用户上下文：封装当前用户的所有数据访问

    核心设计：
    1. 用户数据物理隔离（各目录独立）
    2. 共享学科自动 fallback（用户私有不存在时读共享）
    3. 延迟初始化（按需创建数据库连接）
    """

    def __init__(self, user_id: str, user_manager: Optional[Any] = None):
        """
        初始化用户上下文

        Args:
            user_id: 用户唯一标识
            user_manager: 可选的 UserManager 实例（用于测试注入，默认使用全局单例）
        """
        self.user_id = user_id
        self._user_mgr = user_manager or get_user_manager()
        self._data_dir = self._user_mgr.get_user_data_dir(user_id)

        # 延迟初始化（首次访问时创建）
        self._dialog_mgr = None
        self._state_store = None
        self._subject_mgr = None
        self._permission_mgr = None
        self._vector_stores = {}  # 缓存 vector_store 实例
        self._graph_stores = {}   # 缓存 graph_store 实例

    # ── 属性访问 ──

    @property
    def user_info(self) -> Optional[dict]:
        """获取用户信息"""
        return self._user_mgr.get_user(self.user_id)

    @property
    def display_name(self) -> str:
        """获取用户显示昵称（用于 Agent 称呼）"""
        info = self.user_info
        if info:
            return info.get("display_name") or info.get("username") or self.user_id
        return self.user_id

    @property
    def data_dir(self) -> Path:
        """获取用户数据根目录"""
        return self._data_dir

    # ── 用户状态数据库（user_states.db） ──

    def _get_states_conn(self) -> sqlite3.Connection:
        """获取用户状态数据库连接"""
        db_path = self._user_mgr.get_user_states_db(self.user_id)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── 对话管理器（DialogContextManager） ──

    @property
    def dialog_manager(self):
        """
        获取用户隔离的对话管理器

        延迟初始化：首次访问时创建 DialogContextManager 实例
        """
        if self._dialog_mgr is None:
            # 动态导入，避免循环依赖
            from core.dialog_context import DialogContextManager
            db_path = self._user_mgr.get_user_states_db(self.user_id)
            self._dialog_mgr = DialogContextManager(db_path=str(db_path))
        return self._dialog_mgr

    # ── 用户状态存储（UserStateStore） ──

    @property
    def state_store(self):
        """
        获取用户隔离的状态存储

        延迟初始化：首次访问时创建 UserStateStore 实例
        """
        if self._state_store is None:
            from core.graph_education.user_state_store import UserStateStore
            db_path = self._user_mgr.get_user_states_db(self.user_id)
            self._state_store = UserStateStore(db_path=str(db_path))
        return self._state_store

    # ── 知识库根目录 ──

    @property
    def kb_root(self) -> Path:
        """获取用户知识库根目录（LA-050-Phase5）"""
        return self._user_mgr.get_user_kb_dir(self.user_id)

    def get_subject_kb_dir(self, subject: str) -> Path:
        """获取指定学科的知识库目录（LA-050-Phase5）"""
        subj_dir = self.kb_root / subject
        subj_dir.mkdir(parents=True, exist_ok=True)
        return subj_dir

    # ── 向量存储（VectorStore） ──

    def get_user_vector_store(self, subject: str):
        """
        LA-050-Phase5: 获取用户隔离的 VectorStore（总是指向用户目录，不 fallback 共享）
        """
        from core.vector_store import VectorStore
        user_vdb = self._user_mgr.get_user_vector_db_dir(self.user_id) / f"{subject}_v1.db"
        user_vdb.parent.mkdir(parents=True, exist_ok=True)
        return VectorStore(subject, db_path=str(user_vdb))

    def get_user_graph_store(self, subject: str):
        """
        LA-050-Phase5: 获取用户隔离的 GraphStore（总是指向用户目录，不 fallback 共享）
        """
        from core.graph_store import GraphStore
        user_gdb = self._user_mgr.get_user_graph_db_dir(self.user_id) / f"{subject}_v1"
        user_gdb.parent.mkdir(parents=True, exist_ok=True)
        return GraphStore(subject, db_path=str(user_gdb))

    def get_user_quiz_bank_path(self, subject: str) -> Path:
        """
        LA-050-Phase5: 获取用户隔离的 quiz bank 路径
        """
        kb = self.kb_root / subject
        kb.mkdir(parents=True, exist_ok=True)
        return kb / f"{subject}_quiz_bank.db"

    def get_user_images_dir(self, subject: str) -> Path:
        """
        LA-051-STRUCT: 获取用户隔离的图片目录（新结构）
        """
        return get_subject_images_dir(subject, self.user_id)

    def get_user_thumbnails_dir(self, subject: str) -> Path:
        """
        LA-051-STRUCT: 获取用户隔离的缩略图目录（新结构）
        """
        return get_subject_thumbnails_dir(subject, self.user_id)

    # ── 原有方法保持不变（向后兼容）──

    def get_vector_store(self, subject: str, prefer_private: bool = True):
        """
        获取向量存储

        逻辑：
        1. 优先查找用户私有向量数据库
        2. 不存在则 fallback 到共享向量数据库

        Args:
            subject: 学科标识
            prefer_private: 是否优先使用私有存储

        Returns:
            VectorStore 实例
        """
        cache_key = f"{subject}_{prefer_private}"
        if cache_key in self._vector_stores:
            return self._vector_stores[cache_key]

        from core.vector_store import VectorStore

        if prefer_private:
            # 1. 检查用户私有
            user_vdb = self._user_mgr.get_user_vector_db_dir(self.user_id) / f"{subject}_v1.db"
            if user_vdb.exists():
                store = VectorStore(subject, db_path=str(user_vdb))
                self._vector_stores[cache_key] = store
                return store

        # 2. Fallback 到共享
        store = VectorStore(subject)
        self._vector_stores[cache_key] = store
        return store

    def get_or_create_private_vector_store(self, subject: str):
        """
        获取或创建用户私有向量存储

        用于用户向私有学科导入内容时
        """
        from core.vector_store import VectorStore

        user_vdb_dir = self._user_mgr.get_user_vector_db_dir(self.user_id)
        user_vdb_dir.mkdir(parents=True, exist_ok=True)

        user_vdb = user_vdb_dir / f"{subject}_v1.db"
        store = VectorStore(subject, db_path=str(user_vdb))

        cache_key = f"{subject}_True"
        self._vector_stores[cache_key] = store
        return store

    # ── 图存储（GraphStore） ──

    def get_graph_store(self, subject: str, prefer_private: bool = True):
        """
        获取图存储

        逻辑与向量存储相同：优先私有 → fallback 共享
        """
        cache_key = f"graph_{subject}_{prefer_private}"
        if cache_key in self._graph_stores:
            return self._graph_stores[cache_key]

        from core.graph_store import GraphStore

        if prefer_private:
            # 1. 检查用户私有
            user_gdb = self._user_mgr.get_user_graph_db_dir(self.user_id) / f"{subject}_v1"
            if user_gdb.exists():
                store = GraphStore(subject, db_path=str(user_gdb))
                self._graph_stores[cache_key] = store
                return store

        # 2. Fallback 到共享
        store = GraphStore(subject)
        self._graph_stores[cache_key] = store
        return store

    def get_or_create_private_graph_store(self, subject: str):
        """获取或创建用户私有图存储"""
        from core.graph_store import GraphStore

        user_gdb_dir = self._user_mgr.get_user_graph_db_dir(self.user_id)
        user_gdb_dir.mkdir(parents=True, exist_ok=True)

        user_gdb = user_gdb_dir / f"{subject}_v1"
        store = GraphStore(subject, db_path=str(user_gdb))

        cache_key = f"graph_{subject}_True"
        self._graph_stores[cache_key] = store
        return store

    # ── 学科管理（SubjectManager） ──

    @property
    def subject_manager(self):
        """
        获取用户隔离的学科管理器

        LA-050-Phase3: 使用用户级 subjects.db 和知识库目录
        """
        if self._subject_mgr is None:
            from core.subject_manager import SubjectManager
            db_path = self._user_mgr.get_user_subjects_db(self.user_id)
            kb_root = self._user_mgr.get_user_kb_dir(self.user_id)
            self._subject_mgr = SubjectManager(
                db_path=str(db_path),
                kb_root=str(kb_root),
            )
        return self._subject_mgr

    # ── 权限管理（PermissionManager） ──

    @property
    def permission_manager(self):
        """
        获取权限管理器（LA-051）
        
        延迟初始化：首次访问时创建 PermissionManager 实例
        """
        if self._permission_mgr is None:
            from core.permission_manager import PermissionManager
            self._permission_mgr = PermissionManager()
        return self._permission_mgr

    # ── 学科管理（向后兼容：也支持共享学科 fallback） ──

    def list_accessible_subjects(self) -> list:
        """
        列出用户可访问的所有学科

        包括：
        1. 用户私有学科（subjects.db）
        2. 共享学科（全局 knowledge_base 目录）
        """
        subjects = []

        # 1. 用户私有学科
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

        # 2. 共享学科（扫描全局 knowledge_base 目录）
        shared_subjects = self._scan_shared_subjects()
        subjects.extend(shared_subjects)

        return subjects

    def _scan_shared_subjects(self) -> list:
        """扫描共享学科"""
        subjects = []

        # 扫描 knowledge_base 下的学科目录
        if KNOWLEDGE_BASE_DIR.exists():
            for item in KNOWLEDGE_BASE_DIR.iterdir():
                if item.is_dir() and item.name not in ("vector_db", "graph_db", "cache"):
                    subjects.append({
                        "id": item.name,
                        "name": item.name,
                        "description": "",
                        "type": "shared",
                        "is_private": False,
                    })

        return subjects

    def create_private_subject(self, subject_id: str, name: str, description: str = "") -> bool:
        """
        创建用户私有学科

        Args:
            subject_id: 学科唯一标识（如 "alice_notes"）
            name: 显示名称
            description: 描述
        """
        # 1. 写入用户私有学科表
        user_subjects_db = self._user_mgr.get_user_subjects_db(self.user_id)
        conn = sqlite3.connect(str(user_subjects_db))
        conn.row_factory = sqlite3.Row

        try:
            from datetime import datetime
            now = datetime.now().isoformat()
            conn.execute("""
                INSERT INTO subjects (id, name, description, is_private, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (subject_id, name, description, 1, now))
            conn.commit()

            # 2. 创建学科目录
            kb_dir = self._user_mgr.get_user_kb_dir(self.user_id)
            (kb_dir / subject_id).mkdir(parents=True, exist_ok=True)

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

        # 评测次数
        try:
            conn = self._get_states_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM evaluation_history WHERE user_id = ?", (self.user_id,))
            stats["evaluations"] = cursor.fetchone()[0]

            # 错题数
            cursor.execute("SELECT COUNT(*) FROM wrong_answers WHERE user_id = ?", (self.user_id,))
            stats["wrong_answers"] = cursor.fetchone()[0]

            # 对话数
            cursor.execute("SELECT COUNT(*) FROM dialog_sessions")
            stats["dialog_sessions"] = cursor.fetchone()[0]

            conn.close()
        except Exception as e:
            print(f"[UserContext] 统计信息获取失败: {e}")
            stats["evaluations"] = 0
            stats["wrong_answers"] = 0
            stats["dialog_sessions"] = 0

        return stats

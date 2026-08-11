#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UserManager - 用户管理器

LA-050: 多用户隔离架构基础设施
负责用户CRUD、会话管理、数据目录初始化

存储结构:
    ~/.learnanything/
        users.db              # 全局用户注册表
        users/
            <user_id>/        # 用户隔离数据目录
                user_states.db
                subjects.db
                knowledge_base/
"""
import json
import shutil
import sqlite3
import uuid
import bcrypt
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


# ========== 默认路径（LA-051-STRUCT: 使用 settings.DATA_ROOT）==========

from config.settings import DATA_ROOT, USERS_DB_PATH, USERS_DIR

_USER_DATA_DIR = DATA_ROOT
_USERS_DB_PATH = USERS_DB_PATH
_USERS_DIR = USERS_DIR

SYSTEM_ROLES = {"admin", "user"}


class UserManager:
    """
    用户管理器：负责用户注册、查询、切换、数据目录管理
    """

    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or _USER_DATA_DIR
        self.users_db = self.base_dir / "users.db"
        self.users_dir = self.base_dir / "users"
        self._ensure_base_dir()
        self._ensure_users_table()
        self._ensure_auth_tokens_table()
        # LA-052-A: 自动创建 default 用户（本地用户，无需密码）
        self._ensure_default_user()

    # ── 内部工具 ──

    def _ensure_base_dir(self):
        """确保基础目录存在"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_users_table(self):
        """初始化全局用户注册表（LA-052: 增加 password_hash 字段）"""
        conn = sqlite3.connect(str(self.users_db))
        # LA-052: 创建 users 表（如果已存在则跳过）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT,
                avatar TEXT,
                created_at TEXT,
                last_active_at TEXT,
                preferences TEXT
            )
        ''')
        # LA-052: 为已有表添加 password_hash 字段（向后兼容）
        try:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        except sqlite3.OperationalError:
            pass  # 字段已存在
        try:
            conn.execute("ALTER TABLE users ADD COLUMN system_role TEXT NOT NULL DEFAULT 'user'")
        except sqlite3.OperationalError:
            pass  # 字段已存在
        conn.execute(
            "UPDATE users SET system_role = 'user' "
            "WHERE system_role IS NULL OR system_role NOT IN ('admin', 'user')"
        )
        conn.commit()
        conn.close()

    def _ensure_auth_tokens_table(self):
        """LA-052: 初始化认证 token 表"""
        conn = sqlite3.connect(str(self.users_db))
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT,
                expires_at TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def _ensure_default_user(self):
        """
        LA-052-A: 确保 default 用户存在

        default 是本地主人用户，无需密码，数据隔离在独立目录。
        首次启动时自动创建。
        """
        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = 'default'")
        if not cursor.fetchone():
            now = self._now()
            cursor.execute('''
                INSERT INTO users (user_id, username, display_name, created_at, last_active_at, preferences)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', ('default', 'default', '本地用户', now, now, '{}'))
            conn.commit()
            print("[UserManager] LA-052-A: 自动创建 default 用户")
            # 初始化 default 用户数据目录
            self._init_user_dir('default')
        conn.close()

    def _init_user_dir(self, user_id: str) -> Path:
        """
        初始化用户数据目录结构

        创建:
            users/<user_id>/
                user_states.db      # 对话、评测、错题本
                subjects.db         # 用户私有学科
                knowledge_base/
                    vector_db/      # 私有向量数据库
                    graph_db/       # 私有图数据库
                    cache/          # 私有缓存
        """
        user_dir = self.users_dir / user_id
        kb_dir = user_dir / "knowledge_base"

        # 创建目录
        user_dir.mkdir(parents=True, exist_ok=True)
        # LA-051-DIR-FIX: 不再创建旧式 vector_db/graph_db 目录，学科使用内聚路径
        (kb_dir / "cache").mkdir(parents=True, exist_ok=True)

        # 初始化 user_states.db（创建空表结构，与当前结构一致）
        self._init_user_states_db(user_dir / "user_states.db")

        # 初始化 subjects.db（用户私有学科）
        self._init_user_subjects_db(user_dir / "subjects.db")

        return user_dir

    def _init_user_states_db(self, db_path: Path):
        """初始化用户状态数据库（与当前 user_states.db 结构一致）"""
        conn = sqlite3.connect(str(db_path))

        # 对话会话表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS dialog_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                subject_id TEXT,
                status TEXT DEFAULT 'active',
                current_topic TEXT,
                user_theta REAL DEFAULT 0.0,
                weak_areas TEXT,
                turn_count INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                context_summary TEXT
            )
        ''')

        # 对话消息表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS dialog_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                turn_number INTEGER,
                role TEXT,
                agent_name TEXT,
                content TEXT,
                intent TEXT,
                metadata TEXT,
                created_at TEXT
            )
        ''')

        # 对话话题表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS dialog_topics (
                topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                topic_name TEXT,
                first_turn INTEGER,
                last_turn INTEGER,
                mention_count INTEGER DEFAULT 0,
                canonical_concept_ids TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # 用户画像表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                profession TEXT,
                tech_stack TEXT,
                experience_level TEXT,
                learning_style TEXT,
                weak_areas_global TEXT,
                prefer_code_examples INTEGER DEFAULT 0,
                prefer_diagrams INTEGER DEFAULT 0,
                prefer_concise INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # 评测历史表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS evaluation_history (
                history_id TEXT PRIMARY KEY,
                user_id TEXT,
                subject_id TEXT,
                eval_session_id TEXT,
                topic TEXT,
                theta REAL,
                total_score INTEGER,
                max_score INTEGER,
                correct_count INTEGER,
                total_questions INTEGER,
                accuracy REAL,
                weak_areas TEXT,
                strong_areas TEXT,
                evaluated_at TEXT
            )
        ''')

        # 错题本表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wrong_answers (
                wrong_id TEXT PRIMARY KEY,
                user_id TEXT,
                subject_id TEXT,
                question_id TEXT,
                question_text TEXT,
                question_type TEXT,
                options TEXT,
                user_answer TEXT,
                correct_answer TEXT,
                explanation TEXT,
                concept_id TEXT,
                concept_name TEXT,
                bloom_level TEXT,
                is_mastered INTEGER DEFAULT 0,
                is_in_review INTEGER DEFAULT 0,
                wrong_count INTEGER DEFAULT 1,
                first_wrong_at TEXT,
                last_wrong_at TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def _init_user_subjects_db(self, db_path: Path):
        """初始化用户私有学科数据库"""
        conn = sqlite3.connect(str(db_path))

        # 学科表（ENG-P1-NEW: 与 core.subject_manager._ensure_table 保持一致，
        # 避免旧 schema 缺列导致 create_subject 报 OperationalError）
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
        conn.close()

    def _now(self) -> str:
        """当前时间ISO格式"""
        return datetime.now().isoformat()

    # ── 用户CRUD ──

    def create_user(self, username: str, password: str = None, display_name: str = None,
                    avatar: str = None, preferences: dict = None) -> dict:
        """
        创建新用户（LA-052: 增加密码参数）

        Args:
            username: 用户名（唯一标识，如"alice"）
            password: 密码（明文，内部哈希存储）
            display_name: 显示昵称（Agent称呼用）
            avatar: 头像路径或URL
            preferences: 偏好设置字典

        Returns:
            用户信息字典

        Raises:
            ValueError: 用户名已存在或密码不合规
        """
        # LA-052-A: 密码校验（default 用户无需密码，其他用户必须设置密码）
        if not password or len(password) < 6:
            raise ValueError("密码至少 6 位")

        # 检查用户名是否已存在
        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            raise ValueError(f"用户名 '{username}' 已存在")

        # 生成 user_id
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        now = self._now()
        prefs_json = json.dumps(preferences, ensure_ascii=False) if preferences else "{}"

        # LA-052: 密码哈希
        password_hash = ""
        if password:
            salt = bcrypt.gensalt(rounds=12)
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

        # 写入注册表
        cursor.execute('''
            INSERT INTO users (user_id, username, display_name, avatar, created_at, last_active_at, preferences, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, display_name or username, avatar, now, now, prefs_json, password_hash))
        conn.commit()
        conn.close()

        # 初始化用户数据目录
        self._init_user_dir(user_id)

        print(f"[UserManager] 创建用户: {username} (id={user_id})")

        return {
            "user_id": user_id,
            "username": username,
            "display_name": display_name or username,
            "avatar": avatar,
            "created_at": now,
            "system_role": "user",
        }

    def get_user(self, user_id: str) -> Optional[dict]:
        """获取用户信息"""
        conn = sqlite3.connect(str(self.users_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "avatar": row["avatar"],
            "created_at": row["created_at"],
            "last_active_at": row["last_active_at"],
            "preferences": json.loads(row["preferences"] or "{}"),
            "system_role": row["system_role"],
        }

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """通过用户名获取用户信息"""
        conn = sqlite3.connect(str(self.users_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "avatar": row["avatar"],
            "created_at": row["created_at"],
            "last_active_at": row["last_active_at"],
            "preferences": json.loads(row["preferences"] or "{}"),
            "system_role": row["system_role"],
        }

    # ── 系统级角色 ──

    def get_system_role(self, user_id: str) -> Optional[str]:
        """Return the application-wide role for a user."""
        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute("SELECT system_role FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def is_system_admin(self, user_id: str) -> bool:
        """Check whether the user is an application administrator."""
        return self.get_system_role(user_id) == "admin"

    def count_system_admins(self) -> int:
        """Return the number of application administrators."""
        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE system_role = 'admin'")
        count = int(cursor.fetchone()[0])
        conn.close()
        return count

    def set_system_role(self, user_id: str, role: str) -> bool:
        """Set an application-wide role while protecting the last admin."""
        normalized = role.strip().lower()
        if normalized not in SYSTEM_ROLES:
            raise ValueError(f"Unsupported system role: {role}")

        conn = sqlite3.connect(str(self.users_db), timeout=10)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT system_role, password_hash FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"User does not exist: {user_id}")

            current_role, password_hash = row
            if normalized == "admin" and not password_hash:
                raise ValueError("A password-authenticated account is required for administrators")
            if current_role == "admin" and normalized != "admin":
                admin_count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM users WHERE system_role = 'admin'"
                    ).fetchone()[0]
                )
                if admin_count <= 1:
                    raise ValueError("Cannot demote the last system administrator")

            cursor = conn.execute(
                "UPDATE users SET system_role = ? WHERE user_id = ?",
                (normalized, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def verify_user_password(self, user_id: str, password: str) -> bool:
        """Verify a password against a specific user without exposing its hash."""
        if not password:
            return False
        conn = sqlite3.connect(str(self.users_db))
        row = conn.execute(
            "SELECT password_hash FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
        return bool(
            row
            and row[0]
            and bcrypt.checkpw(password.encode("utf-8"), row[0].encode("utf-8"))
        )

    def claim_first_system_admin(self, user_id: str, password: str) -> bool:
        """Atomically let a password-authenticated user claim the first admin role."""
        conn = sqlite3.connect(str(self.users_db), timeout=10)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"User does not exist: {user_id}")
            if not row[0]:
                raise ValueError("A password-authenticated account is required for administrators")

            admin_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM users WHERE system_role = 'admin'"
                ).fetchone()[0]
            )
            if admin_count:
                raise ValueError("A system administrator already exists")
            if not password or not bcrypt.checkpw(
                password.encode("utf-8"), row[0].encode("utf-8")
            ):
                raise ValueError("Current password is incorrect")

            cursor = conn.execute(
                "UPDATE users SET system_role = 'admin' WHERE user_id = ?",
                (user_id,),
            )
            conn.commit()
            return cursor.rowcount == 1
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── LA-052: 密码认证 ──

    def verify_password(self, username: str, password: str) -> Optional[dict]:
        """
        验证用户名密码

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            用户信息字典（成功）或 None（失败）
        """
        conn = sqlite3.connect(str(self.users_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, username, display_name, password_hash, system_role FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        stored_hash = row["password_hash"] or ""
        # LA-052: 向后兼容：无密码的 legacy 用户不允许密码登录
        if not stored_hash:
            return None

        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            return {
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "system_role": row["system_role"],
            }
        return None

    def set_password(self, user_id: str, password: str) -> bool:
        """
        为用户设置/重置密码

        Args:
            user_id: 用户 ID
            password: 新密码（明文，内部哈希存储）

        Returns:
            是否成功
        """
        if len(password) < 6:
            raise ValueError("密码至少 6 位")

        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (password_hash, user_id)
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def generate_token(self, user_id: str) -> str:
        """
        生成认证 token

        Args:
            user_id: 用户 ID

        Returns:
            随机 token 字符串
        """
        token = secrets.token_urlsafe(32)
        now = self._now()
        expires = (datetime.now() + timedelta(days=30)).isoformat()

        conn = sqlite3.connect(str(self.users_db))
        conn.execute(
            "INSERT INTO auth_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now, expires)
        )
        conn.commit()
        conn.close()
        return token

    def verify_token(self, token: str) -> Optional[str]:
        """
        验证 token 有效性

        Args:
            token: 认证 token

        Returns:
            user_id（有效）或 None（无效/过期）
        """
        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, expires_at FROM auth_tokens WHERE token = ?",
            (token,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        user_id, expires_at = row
        # 检查是否过期
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                self.revoke_token(token)
                return None
        except (ValueError, TypeError):
            return None

        return user_id

    def revoke_token(self, token: str) -> bool:
        """
        注销 token（登出）

        Args:
            token: 认证 token

        Returns:
            是否成功删除
        """
        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def list_users(self) -> List[dict]:
        """列出所有用户"""
        conn = sqlite3.connect(str(self.users_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "user_id": r["user_id"],
                "username": r["username"],
                "display_name": r["display_name"],
                "avatar": r["avatar"],
                "created_at": r["created_at"],
                "last_active_at": r["last_active_at"],
                "system_role": r["system_role"],
            }
            for r in rows
        ]

    def update_user(self, user_id: str, **kwargs) -> bool:
        """
        更新用户信息

        可更新字段: display_name, avatar, preferences
        """
        allowed = {"display_name", "avatar", "preferences"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()

        if "preferences" in updates and isinstance(updates["preferences"], dict):
            updates["preferences"] = json.dumps(updates["preferences"], ensure_ascii=False)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]

        cursor.execute(f"UPDATE users SET {set_clauses} WHERE user_id = ?", values)
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return updated

    def delete_user(self, user_id: str) -> bool:
        """
        删除用户及其所有数据

        警告：此操作不可恢复！
        """
        if self.is_system_admin(user_id) and self.count_system_admins() <= 1:
            raise ValueError("Cannot delete the last system administrator")

        # 1. 删除用户目录
        user_dir = self.users_dir / user_id
        if user_dir.exists():
            shutil.rmtree(user_dir)

        # 2. 从注册表删除
        conn = sqlite3.connect(str(self.users_db))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if deleted:
            print(f"[UserManager] 已删除用户: {user_id}")

        return deleted

    # ── 数据目录访问 ──

    def get_user_data_dir(self, user_id: str) -> Path:
        """获取用户数据目录"""
        return self.users_dir / user_id

    def get_user_states_db(self, user_id: str) -> Path:
        """获取用户状态数据库路径"""
        return self.get_user_data_dir(user_id) / "user_states.db"

    def get_user_subjects_db(self, user_id: str) -> Path:
        """获取用户私有学科数据库路径"""
        return self.get_user_data_dir(user_id) / "subjects.db"

    def get_user_kb_dir(self, user_id: str) -> Path:
        """获取用户知识库根目录"""
        return self.get_user_data_dir(user_id) / "knowledge_base"

    def get_user_vector_db_dir(self, user_id: str) -> Path:
        """获取用户向量数据库目录"""
        return self.get_user_kb_dir(user_id) / "vector_db"

    def get_user_graph_db_dir(self, user_id: str) -> Path:
        """获取用户图数据库目录"""
        return self.get_user_kb_dir(user_id) / "graph_db"

    def get_user_cache_dir(self, user_id: str) -> Path:
        """获取用户缓存目录"""
        return self.get_user_kb_dir(user_id) / "cache"

    def user_exists(self, user_id: str) -> bool:
        """检查用户是否存在"""
        return self.get_user(user_id) is not None

    # ── 向后兼容 ──

    def ensure_anonymous_user(self) -> dict:
        """
        确保匿名用户存在（向后兼容）

        如果 anonymous 用户不存在，自动创建
        如果旧版 user_states.db 存在，自动迁移
        """
        user = self.get_user_by_username("anonymous")
        if user:
            return user

        # 创建 anonymous 用户
        try:
            user = self.create_user(
                username="anonymous",
                display_name="访客",
                preferences={},
            )
        except ValueError:
            # 可能已经存在（并发情况）
            user = self.get_user_by_username("anonymous")

        # 尝试迁移旧数据
        self._migrate_anonymous_data()

        return user

    def _migrate_anonymous_data(self):
        """迁移旧版 anonymous 用户数据"""
        from config.settings import KNOWLEDGE_BASE_DIR

        old_db = KNOWLEDGE_BASE_DIR / "user_states.db"
        if not old_db.exists():
            return

        anon_dir = self.get_user_data_dir("anonymous")
        new_db = anon_dir / "user_states.db"

        if new_db.exists() and new_db.stat().st_size > 0:
            # 已经迁移过，跳过
            return

        try:
            import shutil
            shutil.copy2(old_db, new_db)
            print(f"[UserManager] 已迁移 anonymous 用户数据: {old_db} -> {new_db}")
        except Exception as e:
            print(f"[UserManager] 迁移 anonymous 数据失败: {e}")


# ========== 全局实例 ==========

_user_manager: Optional[UserManager] = None


def get_user_manager() -> UserManager:
    """获取全局 UserManager 实例（懒加载）"""
    global _user_manager
    if _user_manager is None:
        _user_manager = UserManager()
    return _user_manager

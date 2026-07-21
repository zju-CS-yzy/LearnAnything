#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DialogContextManager - 对话上下文管理器（阶段 1 增强版）

新增:
1. 跨学科记忆分层（全局画像 + 学科隔离）
2. 详细日志打印（便于控制台观察）
3. user_profiles 表（跨学科共享的用户画像）
"""

import sqlite3
import json
import uuid
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class UserProfile:
    """用户全局画像 - 跨学科共享"""
    user_id: str
    created_at: str = ""          # ISO 8601
    updated_at: str = ""
    profession: str = ""          # 职业
    tech_stack: str = ""          # JSON 数组字符串 ["C++", "Python"]
    experience_level: str = ""    # 初级/中级/高级
    learning_style: str = ""      # 学习风格
    weak_areas_global: str = ""   # JSON 数组字符串 ["线性代数"]
    prefer_code_examples: int = 1 # 0/1
    prefer_diagrams: int = 1
    prefer_concise: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "profession": self.profession,
            "tech_stack": self._safe_json_loads(self.tech_stack, []),
            "experience_level": self.experience_level,
            "weak_areas_global": self._safe_json_loads(self.weak_areas_global, []),
        }

    @staticmethod
    def _safe_json_loads(s: str, default):
        try:
            return json.loads(s or "null") or default
        except:
            return default


@dataclass
class DialogContext:
    """传递给 Agent 的对话上下文对象（增强版：跨学科记忆分层）"""
    session_id: str
    user_id: str
    turn_number: int
    history: List[Dict[str, Any]] = field(default_factory=list)
    current_topic: Optional[str] = None
    user_theta: float = 0.0
    weak_areas: List[str] = field(default_factory=list)        # 学科内薄弱点（隔离）
    subject_id: Optional[str] = None

    # 跨学科共享
    user_profile: Optional[UserProfile] = None
    weak_areas_global: List[str] = field(default_factory=list)

    def to_prompt_context(self, max_turns: int = 5, max_chars: int = 800) -> str:
        """
        转换为 LLM prompt 中的分层上下文文本（含日志描述）。

        LA-044-#1: 当历史文本超过 max_chars 时，使用 LLM 摘要替代完整历史。

        Args:
            max_turns: 保留的最近轮次数（未超限时）
            max_chars: 历史文本字符数阈值，超过则触发摘要
        """
        lines = []

        # 1. 全局用户画像（跨学科共享）
        if self.user_profile and self.user_profile.profession:
            lines.append("【用户画像】(跨学科共享)")
            if self.user_profile.profession:
                lines.append(f"职业: {self.user_profile.profession}")
            tech_stack = self.user_profile._safe_json_loads(self.user_profile.tech_stack, [])
            if tech_stack:
                lines.append(f"技术栈: {', '.join(tech_stack)}")
            if self.user_profile.experience_level:
                lines.append(f"经验水平: {self.user_profile.experience_level}")
            if self.weak_areas_global:
                lines.append(f"通用薄弱领域: {', '.join(self.weak_areas_global)}")
            lines.append("")

        # 2. 学科上下文（学科隔离）
        if self.subject_id or self.current_topic:
            lines.append(f"【当前学科】(学科隔离)")
            if self.subject_id:
                lines.append(f"学科: {self.subject_id}")
            if self.current_topic:
                lines.append(f"当前话题: {self.current_topic}")
            if self.weak_areas:
                lines.append(f"本学科薄弱点: {', '.join(self.weak_areas)}")
            lines.append("")

        # 3. 对话历史（LA-044-#1: 摘要机制）
        if self.history:
            # 先计算完整历史的字符数
            history_lines = []
            for msg in self.history[-max_turns:]:
                role_label = "用户" if msg.get("role") == "user" else msg.get("agent_name", "系统")
                content = msg.get("content", "")[:200]
                history_lines.append(f"{role_label}: {content}")

            full_history = "\n".join(history_lines)

            # LA-044-#1: 检查是否超过阈值
            if len(full_history) > max_chars:
                # 使用 LLM 摘要
                summary = self.to_summary()
                if summary:
                    lines.append("【对话摘要】(历史较长，已摘要)")
                    lines.append(summary)
                    lines.append("")
                else:
                    # 摘要失败，回退到最近 2 轮
                    lines.append("【对话历史】(最近2轮)")
                    for msg in self.history[-2:]:
                        role_label = "用户" if msg.get("role") == "user" else msg.get("agent_name", "系统")
                        content = msg.get("content", "")[:150]
                        lines.append(f"{role_label}: {content}")
                    lines.append("")
            else:
                # 未超限，使用完整历史
                lines.append("【对话历史】(学科隔离)")
                lines.extend(history_lines)
                lines.append("")

        return "\n".join(lines)

    def to_summary(self) -> Optional[str]:
        """
        LA-044-#1: 使用 LLM 生成对话历史摘要。

        当对话历史过长时，调用 LLM 生成精简摘要，保留关键信息：
        - 讨论过的话题
        - 用户的疑问和 Agent 的核心回答
        - 用户的薄弱点暴露

        Returns:
            摘要文本 或 None（LLM 调用失败时）
        """
        # 检查缓存（同一轮次不重复生成）
        cache_key = f"{self.session_id}_{self.turn_number}"
        if hasattr(self, '_summary_cache') and self._summary_cache.get('key') == cache_key:
            return self._summary_cache.get('text')

        if not self.history:
            return None

        try:
            from core.llm_client import LLMClient

            # 构建 LLM 输入：完整历史
            history_text = "\n".join([
                f"{'用户' if m.get('role') == 'user' else m.get('agent_name', '系统')}: {m.get('content', '')[:300]}"
                for m in self.history
            ])

            prompt = f"""请对以下对话历史进行摘要，保留关键信息（讨论话题、用户疑问、核心回答、暴露的薄弱点）。
摘要控制在 200 字以内，使用中文。

对话历史：
{history_text}

摘要："""

            print(f"[DialogContext] LA-044-#1: 调用 LLM 生成对话摘要 (history_len={len(self.history)})")

            llm = LLMClient()
            summary = llm.complete(prompt, temperature=0.3, max_tokens=300)

            if summary:
                summary = summary.strip()
                # 缓存结果
                self._summary_cache = {'key': cache_key, 'text': summary}
                print(f"[DialogContext] LA-044-#1: 摘要生成成功 ({len(summary)} 字)")
                return summary

        except Exception as e:
            print(f"[DialogContext] LA-044-#1: LLM 摘要生成失败: {e}")

        return None

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        LA-044-#1: 简易 token 估算（中文 ≈ 1 字/1 token，英文 ≈ 0.75 token/词）。

        这是快速估算，不精确但足够用于阈值判断。
        """
        if not text:
            return 0
        # 中文字符计数
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        # 英文单词估算
        import re
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        # 其他字符（标点、数字等）
        other_chars = len(text) - chinese_chars - sum(len(m.group()) for m in re.finditer(r'[a-zA-Z]+', text))

        estimated = chinese_chars + int(english_words * 0.75) + int(other_chars * 0.5)
        return max(1, estimated)

    def get_log_summary(self) -> str:
        """返回日志摘要，便于控制台观察"""
        profile_info = ""
        if self.user_profile:
            profile_info = f", 画像=有(profession={self.user_profile.profession})"
        return (
            f"[DialogContext] session={self.session_id[:8]}..., "
            f"user={self.user_id}, subject={self.subject_id}, "
            f"turn={self.turn_number}, history={len(self.history)}轮, "
            f"topic={self.current_topic or 'None'}, "
            f"weak_areas={len(self.weak_areas)}, weak_global={len(self.weak_areas_global)}"
            f"{profile_info}"
        )


class DialogContextManager:
    """对话上下文管理器（阶段 1 增强版）"""

    DB_PATH = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\user_states.db")
    SESSION_TIMEOUT_MINUTES = 30
    MAX_HISTORY_TURNS = 20

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else self.DB_PATH
        self._init_tables()
        print(f"[DialogContextManager] 初始化完成, db={self.db_path}")

    # ---------- 表初始化 ----------

    def _init_tables(self):
        """初始化对话相关表（含新增 user_profiles）"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            # 会话表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dialog_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    subject_id TEXT,
                    status TEXT DEFAULT 'active',
                    current_topic TEXT,
                    user_theta REAL DEFAULT 0.0,
                    weak_areas TEXT,
                    turn_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    context_summary TEXT
                )
            """)
            # 消息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dialog_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    agent_name TEXT,
                    content TEXT NOT NULL,
                    intent TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            # 新增：用户画像表（跨学科共享）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    profession TEXT,
                    tech_stack TEXT,
                    experience_level TEXT,
                    learning_style TEXT,
                    weak_areas_global TEXT,
                    prefer_code_examples INTEGER DEFAULT 1,
                    prefer_diagrams INTEGER DEFAULT 1,
                    prefer_concise INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            # 索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON dialog_sessions(user_id, updated_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_status ON dialog_sessions(status, updated_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session ON dialog_messages(session_id, turn_number)
            """)
            # LA-044-B: 话题追踪表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dialog_topics (
                    topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    topic_name TEXT NOT NULL,
                    first_turn INTEGER DEFAULT 1,
                    last_turn INTEGER DEFAULT 1,
                    mention_count INTEGER DEFAULT 1,
                    canonical_concept_ids TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, topic_name)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_topics_session ON dialog_topics(session_id, mention_count DESC)
            """)
            conn.commit()
            print("[DialogContextManager] 表初始化完成: dialog_sessions, dialog_messages, user_profiles, dialog_topics")
        finally:
            conn.close()

    # ---------- 用户画像（跨学科共享）----------

    def get_or_create_profile(self, user_id: str) -> UserProfile:
        """获取或创建用户全局画像"""
        profile = self._load_profile(user_id)
        if profile:
            print(f"[DialogContextManager] 加载用户画像: user={user_id}, profession={profile.profession}")
            return profile
        # 创建默认画像
        now = datetime.now().isoformat()
        profile = UserProfile(user_id=user_id, created_at=now, updated_at=now)
        self._save_profile(profile)
        print(f"[DialogContextManager] 创建新用户画像: user={user_id}")
        return profile

    def _load_profile(self, user_id: str) -> Optional[UserProfile]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            data = dict(zip(columns, row))
            return UserProfile(**data)
        finally:
            conn.close()

    def _save_profile(self, profile: UserProfile):
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_profiles
                (user_id, profession, tech_stack, experience_level, learning_style,
                 weak_areas_global, prefer_code_examples, prefer_diagrams, prefer_concise,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile.user_id, profile.profession, profile.tech_stack,
                profile.experience_level, profile.learning_style,
                profile.weak_areas_global, profile.prefer_code_examples,
                profile.prefer_diagrams, profile.prefer_concise,
                profile.created_at, datetime.now().isoformat()
            ))
            conn.commit()
        finally:
            conn.close()

    def update_profile(self, user_id: str, **updates) -> bool:
        """更新用户画像字段（如果不存在则创建）"""
        # 先检查是否存在
        existing = self._load_profile(user_id)
        if not existing:
            # 创建默认画像
            now = datetime.now().isoformat()
            default = UserProfile(user_id=user_id, created_at=now, updated_at=now)
            self._save_profile(default)
            print(f"[DialogContextManager] 用户画像不存在，已创建默认: user={user_id}")

        allowed = {"profession", "tech_stack", "experience_level", "learning_style",
                   "weak_areas_global", "prefer_code_examples", "prefer_diagrams", "prefer_concise"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return False

        # 序列化列表字段
        for key in ["tech_stack", "weak_areas_global"]:
            if key in fields and isinstance(fields[key], list):
                fields[key] = json.dumps(fields[key], ensure_ascii=False)

        fields["updated_at"] = datetime.now().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
            values = list(fields.values()) + [user_id]
            cursor.execute(f"UPDATE user_profiles SET {set_clause} WHERE user_id = ?", values)
            conn.commit()
            print(f"[DialogContextManager] 更新用户画像: user={user_id}, fields={list(updates.keys())}")
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ---------- 会话生命周期（含跨学科切换检测）----------

    def get_or_create_session(self, user_id: str, subject_id: str = None,
                              session_id: str = None) -> Tuple[str, Dict]:
        """
        获取或创建会话（增强版：跨学科隔离）。

        关键行为:
        - 同学科 → 恢复活跃会话
        - 跨学科 → 暂停旧会话，创建新会话
        - 显式 session_id → 恢复该会话（忽略学科）
        """
        print(f"[DialogContextManager] get_or_create_session: user={user_id}, subject={subject_id}, session_id={session_id}")

        # 1. 如果提供了 session_id，尝试恢复
        if session_id:
            session = self._load_session(session_id)
            if session and not self._is_expired(session):
                print(f"[DialogContextManager] 显式恢复会话: session_id={session_id[:8]}..., subject={session.get('subject_id')}")
                return session_id, session
            print(f"[DialogContextManager] 显式 session_id 已过期或不存在，将创建新会话")

        # 2. 关闭该用户的过期会话
        closed_count = self._close_expired_sessions(user_id)
        if closed_count > 0:
            print(f"[DialogContextManager] 关闭了 {closed_count} 个过期会话")

        # 3. 查找用户最近的活跃会话
        active_session = self._find_active_session(user_id)

        if active_session:
            active_subject = active_session.get("subject_id", "")
            # 跨学科切换检测
            if active_subject and subject_id and active_subject != subject_id:
                print(f"[DialogContextManager] >>> 跨学科切换检测 <<<: {active_subject} -> {subject_id}")
                print(f"[DialogContextManager] 暂停旧会话: session={active_session['session_id'][:8]}..., subject={active_subject}")
                self._suspend_session(active_session["session_id"])
                # 创建新会话（新学科）
                new_session = self._create_session(user_id, subject_id)
                print(f"[DialogContextManager] 创建新学科会话: session={new_session['session_id'][:8]}..., subject={subject_id}")
                return new_session["session_id"], new_session
            else:
                # 同学科或无前学科 → 恢复
                print(f"[DialogContextManager] 恢复同学科会话: session={active_session['session_id'][:8]}..., subject={active_subject}")
                return active_session["session_id"], active_session

        # 4. 无活跃会话 → 创建新会话
        new_session = self._create_session(user_id, subject_id)
        print(f"[DialogContextManager] 创建新会话: session={new_session['session_id'][:8]}..., subject={subject_id}")
        return new_session["session_id"], new_session

    def _create_session(self, user_id: str, subject_id: str = None) -> Dict:
        now = datetime.now().isoformat()
        session_id = str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "subject_id": subject_id or "",
            "status": "active",
            "current_topic": None,
            "user_theta": 0.0,
            "weak_areas": "[]",
            "turn_count": 0,
            "created_at": now,
            "updated_at": now,
            "context_summary": None,
        }
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dialog_sessions
                (session_id, user_id, subject_id, status, current_topic, user_theta,
                 weak_areas, turn_count, created_at, updated_at, context_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(session.values()))
            conn.commit()
        finally:
            conn.close()
        return session

    def _load_session(self, session_id: str) -> Optional[Dict]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dialog_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        finally:
            conn.close()

    def _find_active_session(self, user_id: str, subject_id: str = None) -> Optional[Dict]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            if subject_id:
                cursor.execute("""
                    SELECT * FROM dialog_sessions
                    WHERE user_id = ? AND subject_id = ? AND status = 'active'
                    ORDER BY updated_at DESC LIMIT 1
                """, (user_id, subject_id))
            else:
                cursor.execute("""
                    SELECT * FROM dialog_sessions
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY updated_at DESC LIMIT 1
                """, (user_id,))
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        finally:
            conn.close()

    def _suspend_session(self, session_id: str):
        """暂停会话（跨学科切换时使用，非过期）"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE dialog_sessions SET status = 'suspended', updated_at = ? WHERE session_id = ?
            """, (datetime.now().isoformat(), session_id))
            conn.commit()
            print(f"[DialogContextManager] 会话已暂停: session_id={session_id[:8]}...")
        finally:
            conn.close()

    def _is_expired(self, session: Dict) -> bool:
        try:
            updated_at = datetime.fromisoformat(session.get("updated_at", ""))
            elapsed = (datetime.now() - updated_at).total_seconds()
            return elapsed > self.SESSION_TIMEOUT_MINUTES * 60
        except (ValueError, TypeError):
            return True

    def _close_expired_sessions(self, user_id: str) -> int:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT session_id, updated_at FROM dialog_sessions
                WHERE user_id = ? AND status = 'active'
            """, (user_id,))
            rows = cursor.fetchall()
            closed = 0
            for row in rows:
                session_id, updated_at = row
                try:
                    dt = datetime.fromisoformat(updated_at)
                    elapsed = (datetime.now() - dt).total_seconds()
                    if elapsed > self.SESSION_TIMEOUT_MINUTES * 60:
                        cursor.execute("""
                            UPDATE dialog_sessions SET status = 'expired' WHERE session_id = ?
                        """, (session_id,))
                        closed += 1
                except (ValueError, TypeError):
                    pass
            conn.commit()
            return closed
        finally:
            conn.close()

    def _suspend_user_subject_sessions(self, user_id: str, subject_id: str = None):
        """
        LA-044-FIX: 暂停用户指定学科的所有活跃会话。
        
        新建会话时调用，确保旧会话不会被复用。
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            if subject_id:
                # 暂停同学科的活跃会话
                cursor.execute("""
                    UPDATE dialog_sessions 
                    SET status = 'suspended', updated_at = ? 
                    WHERE user_id = ? AND subject_id = ? AND status = 'active'
                """, (now, user_id, subject_id))
            else:
                # 暂停所有活跃会话
                cursor.execute("""
                    UPDATE dialog_sessions 
                    SET status = 'suspended', updated_at = ? 
                    WHERE user_id = ? AND status = 'active'
                """, (now, user_id))
            
            suspended_count = cursor.rowcount
            conn.commit()
            
            if suspended_count > 0:
                print(f"[DialogContextManager] 暂停了 {suspended_count} 个旧会话 (user={user_id}, subject={subject_id})")
        finally:
            conn.close()

    # ---------- 消息持久化（增强日志）----------

    def save_message(self, session_id: str, turn_number: int, role: str,
                     content: str, agent_name: str = None, intent: str = None,
                     metadata: Dict = None) -> bool:
        print(f"[DialogContextManager] 保存消息: session={session_id[:8]}..., turn={turn_number}, role={role}, intent={intent}, content_len={len(content)}")
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO dialog_messages
                (session_id, turn_number, role, agent_name, content, intent, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, turn_number, role, agent_name, content, intent,
                  json.dumps(metadata or {}, ensure_ascii=False), now))
            conn.commit()
            print(f"[DialogContextManager] 消息已保存: message_id={cursor.lastrowid}")
            return True
        except Exception as e:
            print(f"[DialogContextManager] 保存消息失败: {e}")
            return False
        finally:
            conn.close()

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM dialog_messages
                WHERE session_id = ?
                ORDER BY turn_number DESC, message_id DESC
                LIMIT ?
            """, (session_id, limit))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            messages = []
            for row in rows:
                msg = dict(zip(columns, row))
                if msg.get("metadata"):
                    try:
                        msg["metadata"] = json.loads(msg["metadata"])
                    except json.JSONDecodeError:
                        msg["metadata"] = {}
                messages.append(msg)
            messages.reverse()
            print(f"[DialogContextManager] 查询历史: session={session_id[:8]}..., 返回 {len(messages)} 条消息")
            return messages
        finally:
            conn.close()

    # ---------- 上下文构建（增强版：跨学科记忆分层）----------

    def build_context(self, session_id: str) -> Optional[DialogContext]:
        """
        构建完整的对话上下文，包含：
        - 学科隔离部分（当前会话历史、当前话题、学科薄弱点）
        - 全局共享部分（用户画像、通用薄弱点）
        """
        print(f"[DialogContextManager] 构建上下文: session={session_id[:8]}...")

        session = self._load_session(session_id)
        if not session:
            print(f"[DialogContextManager] 会话不存在: {session_id}")
            return None

        user_id = session.get("user_id", "")
        subject_id = session.get("subject_id", "")

        # 1. 学科隔离记忆：当前会话历史
        history = self.get_history(session_id, limit=self.MAX_HISTORY_TURNS)
        turn_count = session.get("turn_count", 0)

        # 2. 学科隔离记忆：学科薄弱点
        weak_areas = []
        try:
            weak_areas = json.loads(session.get("weak_areas", "[]") or "[]")
        except json.JSONDecodeError:
            weak_areas = []

        # 3. 全局共享记忆：用户画像
        profile = self.get_or_create_profile(user_id)

        # 4. 全局共享记忆：通用薄弱点
        weak_areas_global = profile._safe_json_loads(profile.weak_areas_global, [])

        context = DialogContext(
            session_id=session_id,
            user_id=user_id,
            turn_number=turn_count,
            history=history,
            current_topic=session.get("current_topic"),
            user_theta=session.get("user_theta", 0.0),
            weak_areas=weak_areas,
            subject_id=subject_id,
            user_profile=profile,
            weak_areas_global=weak_areas_global,
        )

        print(f"[DialogContextManager] {context.get_log_summary()}")
        return context

    def update_session(self, session_id: str, **updates) -> bool:
        if not updates:
            return True

        allowed_fields = {"current_topic", "user_theta", "weak_areas", "turn_count", "status", "context_summary"}
        fields = {k: v for k, v in updates.items() if k in allowed_fields}
        if not fields:
            return False

        if "weak_areas" in fields and isinstance(fields["weak_areas"], list):
            fields["weak_areas"] = json.dumps(fields["weak_areas"], ensure_ascii=False)

        fields["updated_at"] = datetime.now().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
            values = list(fields.values()) + [session_id]
            cursor.execute(f"UPDATE dialog_sessions SET {set_clause} WHERE session_id = ?", values)
            conn.commit()
            print(f"[DialogContextManager] 更新会话: session={session_id[:8]}..., fields={list(updates.keys())}")
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[DialogContextManager] 更新会话失败: {e}")
            return False
        finally:
            conn.close()

    # ---------- 指代解析（增强日志）----------

    def resolve_references(self, query: str, context: DialogContext) -> str:
        resolved = query

        if context.current_topic:
            pronouns = ["它", "他", "她", "这个方法", "这个概念", "这个技术"]
            replaced = []
            for p in pronouns:
                if p in resolved:
                    resolved = resolved.replace(p, context.current_topic)
                    replaced.append(p)
            if replaced:
                print(f"[DialogContextManager] 指代替换: {replaced} -> '{context.current_topic}'")

            ellipsis_patterns = re.compile(r'^(和|与|跟|同|以及|还有|另外|那么|然后)\s+')
            if ellipsis_patterns.match(resolved.strip()):
                resolved = f"{context.current_topic} {resolved}"
                print(f"[DialogContextManager] 省略主语补全: '{query}' -> '{resolved}'")

        if resolved == query:
            print(f"[DialogContextManager] 无需指代解析: '{query[:50]}...'")

        return resolved

    # ---------- LA-044-B: 话题提取与追踪 ----------

    def extract_topic(self, answer_text: str, concept_names: List[str] = None, query: str = None) -> Optional[str]:
        """
        从回答文本中提取话题关键词。

        策略（按优先级）：
        1. 从回答中提取第一个 Markdown heading（如 ### RAG架构）
        2. 从 concept_names 中取出现频率最高的概念
        3. 从 query 中提取核心名词（去掉疑问词）
        4. 回退：取回答前 20 个字符

        Args:
            answer_text: Agent 回答文本
            concept_names: 图谱中的概念名称列表
            query: 用户查询

        Returns:
            话题关键词 或 None
        """
        print(f"\n[DialogContextManager] ====== extract_topic ======")
        print(f"[DialogContextManager] 输入: answer_len={len(answer_text)}, concepts={concept_names[:3] if concept_names else None}, query='{query[:30] if query else ''}...'")

        # 策略1: Markdown heading
        if answer_text:
            heading_match = re.search(r'^#{2,4}\s+(.+)$', answer_text, re.MULTILINE)
            if heading_match:
                topic = heading_match.group(1).strip()
                print(f"[DialogContextManager] 话题提取(heading): '{topic}'")
                return topic

        # 策略2: concept_names 中取第一个（最相关的）
        if concept_names and len(concept_names) > 0:
            topic = concept_names[0]
            print(f"[DialogContextManager] 话题提取(concept): '{topic}'")
            return topic

        # 策略3: query 去掉疑问词
        if query:
            cleaned = re.sub(r'^(什么是|什么叫|什么是|怎么|如何|为什么|请解释|介绍一下)\s*', '', query)
            cleaned = re.sub(r'[？?\s]+$', '', cleaned)
            if cleaned and len(cleaned) > 1:
                print(f"[DialogContextManager] 话题提取(query): '{cleaned}'")
                return cleaned

        # 策略4: 回退
        if answer_text:
            fallback = answer_text[:20].strip()
            print(f"[DialogContextManager] 话题提取(fallback): '{fallback}'")
            return fallback

        print(f"[DialogContextManager] 话题提取: 失败，无可用文本")
        return None

    def detect_topic_switch(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        检测用户是否意图切换话题。

        Returns:
            (is_switch, new_topic) - is_switch=True 表示检测到切换意图
        """
        print(f"\n[DialogContextManager] ====== detect_topic_switch ======")
        print(f"[DialogContextManager] 输入查询: '{query}'")

        switch_keywords = {
            "换个话题": True, "换个": True, "另外": True, "再讲一下": True,
            "再说说": True, "还有": True, "转到": True, "切换到": True,
            "讲讲": True, "说下": True, "聊一下": True,
        }

        for kw in switch_keywords:
            if kw in query:
                # 提取新话题：假设关键词后面的内容是话题
                idx = query.find(kw) + len(kw)
                new_topic = query[idx:].strip("，,、\s")
                # 去掉常见前缀词
                new_topic = re.sub(r'^[讲讲说下聊一下关于]*', '', new_topic)
                print(f"[DialogContextManager] 检测到话题切换: kw='{kw}', new_topic='{new_topic}'")
                return True, new_topic or None

        print(f"[DialogContextManager] 无话题切换意图")
        return False, None

    def track_topic(self, session_id: str, topic_name: str, turn_number: int):
        """
        追踪话题：更新或创建 dialog_topics 记录。

        Args:
            session_id: 会话 ID
            topic_name: 话题名称
            turn_number: 当前轮次
        """
        print(f"\n[DialogContextManager] ====== track_topic ======")
        print(f"[DialogContextManager] 输入: session={session_id[:8]}..., topic='{topic_name}', turn={turn_number}")

        if not topic_name or not topic_name.strip():
            print(f"[DialogContextManager] 话题为空，跳过追踪")
            return

        topic_name = topic_name.strip()[:100]  # 截断过长话题
        now = datetime.now().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            # 尝试更新已有话题
            cursor.execute("""
                UPDATE dialog_topics
                SET last_turn = ?, mention_count = mention_count + 1, updated_at = ?
                WHERE session_id = ? AND topic_name = ?
            """, (turn_number, now, session_id, topic_name))

            if cursor.rowcount == 0:
                # 创建新话题
                cursor.execute("""
                    INSERT INTO dialog_topics (session_id, topic_name, first_turn, last_turn, mention_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (session_id, topic_name, turn_number, turn_number, 1, now, now))
                print(f"[DialogContextManager] 新建话题追踪: '{topic_name}'")
            else:
                print(f"[DialogContextManager] 更新话题追踪: '{topic_name}', mention_count+1")

            conn.commit()
        finally:
            conn.close()

    def get_topic_chain(self, session_id: str) -> List[str]:
        """
        获取会话的话题链（按 mention_count 降序）。

        Returns:
            话题名称列表
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT topic_name FROM dialog_topics
                WHERE session_id = ?
                ORDER BY mention_count DESC, last_turn DESC
            """, (session_id,))
            rows = cursor.fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def update_session_topic(self, session_id: str, new_topic: str, turn_number: int):
        """
        更新会话的 current_topic 并追踪话题。

        Args:
            session_id: 会话 ID
            new_topic: 新话题
            turn_number: 当前轮次
        """
        print(f"\n[DialogContextManager] ====== update_session_topic ======")
        print(f"[DialogContextManager] 输入: session={session_id[:8]}..., new_topic='{new_topic}', turn={turn_number}")

        # 更新 session 的 current_topic
        self.update_session(session_id, current_topic=new_topic)

        # 追踪话题
        self.track_topic(session_id, new_topic, turn_number)

        # 打印话题链
        topic_chain = self.get_topic_chain(session_id)
        print(f"[DialogContextManager] 当前话题链: {topic_chain[:5]}")

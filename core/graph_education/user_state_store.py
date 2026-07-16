#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UserKnowledgeState SQLite 持久化存储

P0-INT-4: 实现 UserKnowledgeState 的 SQLite 持久化，
         支持用户答题历史的跨会话保存和 IRT 校准。

数据库路径: knowledge_base/user_states.db
表结构: user_knowledge_states
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from core.graph_education.types import UserKnowledgeState


class UserStateStore:
    """用户知识状态持久化存储"""

    DB_PATH = Path(r"D:\MyCS\AI\Project\LearnAnything\knowledge_base\user_states.db")

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else self.DB_PATH
        self._init_db()

    def _init_db(self):
        """初始化数据库和表"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_knowledge_states (
                    state_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    canonical_name TEXT,
                    mastery_level REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.5,
                    theta REAL DEFAULT 0.0,
                    theta_se REAL DEFAULT 1.0,
                    test_count INTEGER DEFAULT 0,
                    correct_count INTEGER DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    last_tested TEXT,
                    first_tested TEXT,
                    updated_at TEXT NOT NULL,
                    source_of_latest_update TEXT,
                    UNIQUE(user_id, subject_id, canonical_id)
                )
            """)
            # 索引加速查询
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_subject 
                ON user_knowledge_states(user_id, subject_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_canonical 
                ON user_knowledge_states(user_id, canonical_id)
            """)
            conn.commit()
        finally:
            conn.close()

    def save(self, state: UserKnowledgeState) -> bool:
        """保存用户知识状态，存在则更新"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_knowledge_states (
                    state_id, user_id, subject_id, canonical_id, canonical_name,
                    mastery_level, confidence, theta, theta_se,
                    test_count, correct_count, streak,
                    last_tested, first_tested, updated_at, source_of_latest_update
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_id) DO UPDATE SET
                    mastery_level=excluded.mastery_level,
                    confidence=excluded.confidence,
                    theta=excluded.theta,
                    theta_se=excluded.theta_se,
                    test_count=excluded.test_count,
                    correct_count=excluded.correct_count,
                    streak=excluded.streak,
                    last_tested=excluded.last_tested,
                    updated_at=excluded.updated_at,
                    source_of_latest_update=excluded.source_of_latest_update
            """, (
                state.state_id, state.user_id, state.subject_id,
                state.canonical_id, state.canonical_name,
                state.mastery_level, state.confidence, state.theta, state.theta_se,
                state.test_count, state.correct_count, state.streak,
                self._dt_to_str(state.last_tested),
                self._dt_to_str(state.first_tested),
                self._dt_to_str(state.updated_at),
                state.source_of_latest_update,
            ))
            conn.commit()
            print(f"[UserStateStore] 保存状态: {state.state_id}, theta={state.theta:.2f}")
            return True
        except Exception as e:
            print(f"[UserStateStore] 保存失败: {e}")
            return False
        finally:
            conn.close()

    def load(self, user_id: str, subject_id: str, canonical_id: str) -> Optional[UserKnowledgeState]:
        """加载用户知识状态"""
        state_id = f"{user_id}#{subject_id}#{canonical_id}"
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM user_knowledge_states
                WHERE state_id = ?
            """, (state_id,))
            row = cursor.fetchone()
            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            data = dict(zip(columns, row))

            return UserKnowledgeState(
                state_id=data["state_id"],
                user_id=data["user_id"],
                subject_id=data["subject_id"],
                canonical_id=data["canonical_id"],
                canonical_name=data["canonical_name"] or "",
                mastery_level=data["mastery_level"],
                confidence=data["confidence"],
                theta=data["theta"],
                theta_se=data["theta_se"],
                test_count=data["test_count"],
                correct_count=data["correct_count"],
                streak=data["streak"],
                last_tested=self._str_to_dt(data["last_tested"]),
                first_tested=self._str_to_dt(data["first_tested"]),
                updated_at=self._str_to_dt(data["updated_at"]) or datetime.now(),
                source_of_latest_update=data["source_of_latest_update"] or "",
            )
        except Exception as e:
            print(f"[UserStateStore] 加载失败: {e}")
            return None
        finally:
            conn.close()

    def load_by_user(self, user_id: str, subject_id: Optional[str] = None) -> List[UserKnowledgeState]:
        """加载用户的所有知识状态（可选按学科过滤）"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            if subject_id:
                cursor.execute("""
                    SELECT * FROM user_knowledge_states
                    WHERE user_id = ? AND subject_id = ?
                """, (user_id, subject_id))
            else:
                cursor.execute("""
                    SELECT * FROM user_knowledge_states
                    WHERE user_id = ?
                """, (user_id,))

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            states = []
            for row in rows:
                data = dict(zip(columns, row))
                states.append(UserKnowledgeState(
                    state_id=data["state_id"],
                    user_id=data["user_id"],
                    subject_id=data["subject_id"],
                    canonical_id=data["canonical_id"],
                    canonical_name=data["canonical_name"] or "",
                    mastery_level=data["mastery_level"],
                    confidence=data["confidence"],
                    theta=data["theta"],
                    theta_se=data["theta_se"],
                    test_count=data["test_count"],
                    correct_count=data["correct_count"],
                    streak=data["streak"],
                    last_tested=self._str_to_dt(data["last_tested"]),
                    first_tested=self._str_to_dt(data["first_tested"]),
                    updated_at=self._str_to_dt(data["updated_at"]) or datetime.now(),
                    source_of_latest_update=data["source_of_latest_update"] or "",
                ))
            return states
        except Exception as e:
            print(f"[UserStateStore] 批量加载失败: {e}")
            return []
        finally:
            conn.close()

    def delete(self, user_id: str, subject_id: str, canonical_id: str) -> bool:
        """删除用户知识状态"""
        state_id = f"{user_id}#{subject_id}#{canonical_id}"
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM user_knowledge_states WHERE state_id = ?
            """, (state_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
        """datetime 转 ISO 字符串"""
        if dt is None:
            return None
        return dt.isoformat()

    @staticmethod
    def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
        """ISO 字符串转 datetime"""
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    def get_stats(self, user_id: str, subject_id: Optional[str] = None) -> Dict[str, Any]:
        """获取用户统计信息"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            if subject_id:
                cursor.execute("""
                    SELECT COUNT(*) as total_concepts,
                           AVG(mastery_level) as avg_mastery,
                           AVG(theta) as avg_theta,
                           SUM(test_count) as total_tests,
                           SUM(correct_count) as total_correct
                    FROM user_knowledge_states
                    WHERE user_id = ? AND subject_id = ?
                """, (user_id, subject_id))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as total_concepts,
                           AVG(mastery_level) as avg_mastery,
                           AVG(theta) as avg_theta,
                           SUM(test_count) as total_tests,
                           SUM(correct_count) as total_correct
                    FROM user_knowledge_states
                    WHERE user_id = ?
                """, (user_id,))
            row = cursor.fetchone()
            return {
                "total_concepts": row[0] or 0,
                "avg_mastery": round(row[1] or 0, 2),
                "avg_theta": round(row[2] or 0, 2),
                "total_tests": row[3] or 0,
                "total_correct": row[4] or 0,
                "accuracy": round((row[4] or 0) / max(row[3] or 1, 1) * 100, 1),
            }
        finally:
            conn.close()

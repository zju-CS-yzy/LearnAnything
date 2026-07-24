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
        """初始化数据库和表（含 LA-044-#3 新增 user_subject_profiles 表）"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            # 原有表：概念级别的知识状态
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
            # LA-044-#3 新增：用户-学科级别全局画像表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_subject_profiles (
                    profile_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    global_theta REAL DEFAULT 0.0,
                    weak_areas TEXT DEFAULT '[]',
                    total_questions INTEGER DEFAULT 0,
                    total_correct INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, subject_id)
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_subject_profile 
                ON user_subject_profiles(user_id, subject_id)
            """)
            conn.commit()
            print(f"[UserStateStore] 数据库初始化完成: {self.db_path}")
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

    # ==================== LA-044-#3: 用户全局画像管理 ====================

    def save_profile(self, user_id: str, subject_id: str, global_theta: float,
                     weak_areas: List[str], total_questions: int = 0, total_correct: int = 0) -> bool:
        """保存用户-学科级别全局画像

        Args:
            user_id: 用户ID
            subject_id: 学科ID
            global_theta: 全局能力值
            weak_areas: 薄弱点列表
            total_questions: 总答题数
            total_correct: 总答对数

        Returns:
            是否保存成功
        """
        profile_id = f"{user_id}#{subject_id}"
        now = datetime.now().isoformat()
        weak_areas_json = json.dumps(weak_areas, ensure_ascii=False)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_subject_profiles (
                    profile_id, user_id, subject_id, global_theta, weak_areas,
                    total_questions, total_correct, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    global_theta=excluded.global_theta,
                    weak_areas=excluded.weak_areas,
                    total_questions=excluded.total_questions,
                    total_correct=excluded.total_correct,
                    updated_at=excluded.updated_at
            """, (profile_id, user_id, subject_id, global_theta, weak_areas_json,
                  total_questions, total_correct, now, now))
            conn.commit()
            print(f"[UserStateStore] LA-044-#3: 保存画像成功"
                  f" | user={user_id}, subject={subject_id}"
                  f" | theta={global_theta:.2f}, weak_areas={weak_areas}"
                  f" | questions={total_questions}, correct={total_correct}")
            return True
        except Exception as e:
            print(f"[UserStateStore] LA-044-#3: 保存画像失败 | user={user_id}, subject={subject_id} | error={e}")
            return False
        finally:
            conn.close()

    def load_profile(self, user_id: str, subject_id: str) -> Optional[Dict[str, Any]]:
        """加载用户-学科级别全局画像

        Args:
            user_id: 用户ID
            subject_id: 学科ID

        Returns:
            画像字典，含 theta/weak_areas/total_questions/total_correct 等字段
        """
        profile_id = f"{user_id}#{subject_id}"
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM user_subject_profiles WHERE profile_id = ?
            """, (profile_id,))
            row = cursor.fetchone()
            if not row:
                print(f"[UserStateStore] LA-044-#3: 画像不存在 | user={user_id}, subject={subject_id}")
                return None

            columns = [desc[0] for desc in cursor.description]
            data = dict(zip(columns, row))

            # 解析 weak_areas JSON
            weak_areas = []
            if data.get("weak_areas"):
                try:
                    weak_areas = json.loads(data["weak_areas"])
                except json.JSONDecodeError:
                    weak_areas = []

            profile = {
                "user_id": data["user_id"],
                "subject_id": data["subject_id"],
                "global_theta": data["global_theta"],
                "weak_areas": weak_areas,
                "total_questions": data["total_questions"],
                "total_correct": data["total_correct"],
                "accuracy": round(data["total_correct"] / max(data["total_questions"], 1) * 100, 1),
                "updated_at": data["updated_at"],
            }
            print(f"[UserStateStore] LA-044-#3: 加载画像成功"
                  f" | user={user_id}, subject={subject_id}"
                  f" | theta={profile['global_theta']:.2f}, weak_areas={profile['weak_areas']}"
                  f" | questions={profile['total_questions']}, correct={profile['total_correct']}")
            return profile
        except Exception as e:
            print(f"[UserStateStore] LA-044-#3: 加载画像失败 | user={user_id}, subject={subject_id} | error={e}")
            return None
        finally:
            conn.close()

    def get_weak_areas(self, user_id: str, subject_id: str) -> List[str]:
        """获取用户的薄弱点列表

        Args:
            user_id: 用户ID
            subject_id: 学科ID

        Returns:
            薄弱点名称列表
        """
        profile = self.load_profile(user_id, subject_id)
        if profile:
            return profile.get("weak_areas", [])
        return []

    def update_from_dialog(self, user_id: str, subject_id: str, theta: Optional[float] = None,
                           weak_areas: Optional[List[str]] = None) -> bool:
        """LA-044-#3: 从对话上下文更新用户画像（自动保存入口）

        在 /api/ask 响应后调用，将对话中检测到的 theta 和薄弱点写回持久化存储。

        Args:
            user_id: 用户ID
            subject_id: 学科ID
            theta: 可选，对话中检测到的能力值
            weak_areas: 可选，对话中检测到的薄弱点

        Returns:
            是否更新成功
        """
        print(f"\n[UserStateStore] LA-044-#3: ====== update_from_dialog ======")
        print(f"[UserStateStore] 输入: user={user_id}, subject={subject_id}, theta={theta}, weak_areas={weak_areas}")

        # 加载现有画像
        existing = self.load_profile(user_id, subject_id)

        if existing:
            # 合并更新：theta 优先使用新值，weak_areas 合并去重
            merged_theta = theta if theta is not None else existing["global_theta"]
            existing_weak = set(existing.get("weak_areas", []))
            if weak_areas:
                existing_weak.update(weak_areas)
            merged_weak = list(existing_weak)
            print(f"[UserStateStore] LA-044-#3: 合并更新"
                  f" | 旧theta={existing['global_theta']:.2f} -> 新theta={merged_theta:.2f}"
                  f" | 旧weak={existing.get('weak_areas', [])} -> 新weak={merged_weak}")
            return self.save_profile(user_id, subject_id, merged_theta, merged_weak,
                                     existing["total_questions"], existing["total_correct"])
        else:
            # 新建画像
            merged_theta = theta if theta is not None else 0.0
            merged_weak = weak_areas if weak_areas else []
            print(f"[UserStateStore] LA-044-#3: 新建画像"
                  f" | theta={merged_theta:.2f}, weak_areas={merged_weak}")
            return self.save_profile(user_id, subject_id, merged_theta, merged_weak)

    def get_full_user_state(self, user_id: str, subject_id: str) -> Dict[str, Any]:
        """LA-044-#3: 获取用户完整状态（全局画像 + 概念级别知识状态列表）

        Args:
            user_id: 用户ID
            subject_id: 学科ID

        Returns:
            完整用户状态字典
        """
        print(f"[UserStateStore] LA-044-#3: 获取完整用户状态 | user={user_id}, subject={subject_id}")

        profile = self.load_profile(user_id, subject_id)
        concept_states = self.load_by_user(user_id, subject_id)
        stats = self.get_stats(user_id, subject_id)

        result = {
            "user_id": user_id,
            "subject_id": subject_id,
            "profile": profile or {
                "global_theta": 0.0,
                "weak_areas": [],
                "total_questions": 0,
                "total_correct": 0,
                "accuracy": 0.0,
            },
            "concept_states": [
                {
                    "canonical_id": s.canonical_id,
                    "canonical_name": s.canonical_name,
                    "mastery_level": s.mastery_level,
                    "theta": s.theta,
                    "test_count": s.test_count,
                    "correct_count": s.correct_count,
                    "streak": s.streak,
                }
                for s in concept_states
            ],
            "stats": stats,
        }
        print(f"[UserStateStore] LA-044-#3: 完整状态返回"
              f" | concepts={len(concept_states)}"
              f" | profile_theta={result['profile']['global_theta']:.2f}"
              f" | weak_areas={result['profile']['weak_areas']}")
        return result

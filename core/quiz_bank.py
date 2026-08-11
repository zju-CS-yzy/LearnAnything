#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题库管理模块
负责题目的保存、查询、随机抽取、统计
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import KNOWLEDGE_BASE_DIR

# 题库数据库路径：使用用户数据目录（PyInstaller 打包后数据持久化）
# 用户数据目录：~/.learnanything/ 或 AppData/Local/LearnAnything/
_user_data_dir = Path.home() / ".learnanything"
_user_data_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = _user_data_dir / "quiz_bank.db"

# 同时保留知识库目录的引用（用于数据迁移）
LEGACY_DB_PATH = KNOWLEDGE_BASE_DIR / "quiz_bank.db"


def _get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    return conn


def _ensure_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS question_bank (
            id TEXT PRIMARY KEY,
            subject TEXT NOT NULL DEFAULT 'generic',
            topic TEXT,
            type TEXT NOT NULL,
            question TEXT NOT NULL,
            options TEXT,
            answer TEXT,
            explanation TEXT,
            difficulty INTEGER DEFAULT 2,
            bloom_level TEXT,
            source TEXT,
            source_entry_id TEXT,
            tags TEXT,
            is_approved INTEGER DEFAULT 0,
            created_at TEXT,
            used_count INTEGER DEFAULT 0,
            correct_rate REAL DEFAULT 0
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_qb_subject ON question_bank(subject)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_qb_topic ON question_bank(topic)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_qb_source_entry ON question_bank(source_entry_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_qb_approved ON question_bank(is_approved)')
    
    # LA-040-P2: 兼容旧表 — 如果表已存在但没有 bloom_level 列，则添加
    cursor = conn.execute("PRAGMA table_info(question_bank)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'bloom_level' not in columns:
        conn.execute('ALTER TABLE question_bank ADD COLUMN bloom_level TEXT')
        print("[QuizBank] 已升级表结构: 添加 bloom_level 列")
    
    conn.execute('CREATE INDEX IF NOT EXISTS idx_qb_bloom ON question_bank(bloom_level)')
    conn.commit()
    # 迁移：从旧数据库复制数据（如果旧数据库存在且新数据库为空）
    _migrate_legacy_data(conn)


def _migrate_legacy_data(conn: sqlite3.Connection):
    """从旧数据库位置迁移数据到新用户数据目录"""
    if not LEGACY_DB_PATH.exists():
        return
    try:
        # 检查新数据库是否已有数据
        cursor = conn.execute('SELECT COUNT(*) FROM question_bank')
        count = cursor.fetchone()[0]
        if count > 0:
            return  # 新数据库已有数据，不迁移
        
        # 连接旧数据库并复制数据
        legacy_conn = sqlite3.connect(str(LEGACY_DB_PATH))
        legacy_conn.row_factory = sqlite3.Row
        legacy_cursor = legacy_conn.execute('SELECT * FROM question_bank')
        rows = legacy_cursor.fetchall()
        
        for row in rows:
            conn.execute('''
                INSERT OR IGNORE INTO question_bank
                (id, subject, topic, type, question, options, answer, explanation,
                 difficulty, source, source_entry_id, tags, is_approved, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                row['id'], row['subject'], row['topic'], row['type'], row['question'],
                row['options'], row['answer'], row['explanation'], row['difficulty'],
                row['source'], row['source_entry_id'], row['tags'], row['is_approved'],
                row['created_at'],
            ))
        conn.commit()
        legacy_conn.close()
    except Exception as e:
        print(f"[QuizBank] Legacy migration skipped: {e}")


def save_question(
    question: Dict[str, Any],
    subject: str = "generic",
    topic: str = None,
    is_approved: bool = False,
    source_entry_id: str = None,
    bloom_level: str = None,
) -> str:
    """保存一道题目到题库"""
    conn = _get_conn()
    try:
        qid = question.get("id", f"qb-{uuid.uuid4().hex[:8]}")
        if isinstance(qid, int):
            qid = f"qb-{qid}"

        options = question.get("options", [])
        if isinstance(options, list):
            options = json.dumps(options, ensure_ascii=False)

        tags = question.get("tags", [])
        if isinstance(tags, list):
            tags = json.dumps(tags, ensure_ascii=False)

        conn.execute(
            """
            INSERT OR REPLACE INTO question_bank
            (id, subject, topic, type, question, options, answer, explanation,
             difficulty, bloom_level, source, source_entry_id, tags, is_approved, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                qid,
                subject,
                topic or "",
                question.get("type", "single_choice"),
                question.get("question", ""),
                options,
                question.get("answer", ""),
                question.get("explanation", ""),
                question.get("difficulty", 2),
                bloom_level or question.get("bloom_level", ""),
                question.get("source", ""),
                source_entry_id or "",
                tags,
                1 if is_approved else 0,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return qid
    finally:
        conn.close()


def update_bloom_level(qid: str, bloom_level: str) -> bool:
    """更新题目的 Bloom 认知层次"""
    valid_levels = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
    if bloom_level not in valid_levels:
        return False

    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE question_bank SET bloom_level = ? WHERE id = ?",
            (bloom_level, qid),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def batch_update_bloom(subject: str = None, questions: List[Dict] = None) -> Dict[str, Any]:
    """批量更新题目的 Bloom 认知层次

    Args:
        subject: 学科筛选（可选）
        questions: [{'id': 'qb-xxx', 'bloom_level': 'analyze'}, ...]

    Returns:
        {'updated': N, 'skipped': M}
    """
    if not questions:
        return {"updated": 0, "skipped": 0}

    conn = _get_conn()
    valid_levels = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
    updated = 0
    skipped = 0

    try:
        for q in questions:
            qid = q.get("id")
            level = q.get("bloom_level", "").lower()
            if not qid or level not in valid_levels:
                skipped += 1
                continue

            cur = conn.execute(
                "UPDATE question_bank SET bloom_level = ? WHERE id = ?",
                (level, qid),
            )
            if cur.rowcount > 0:
                updated += 1
            else:
                skipped += 1

        conn.commit()
        return {"updated": updated, "skipped": skipped}
    finally:
        conn.close()


def get_bloom_stats(subject: str = None) -> Dict[str, Any]:
    """获取题库的 Bloom 认知层次统计"""
    conn = _get_conn()
    try:
        conditions = ["1=1"]
        params = []
        if subject:
            conditions.append("subject = ?")
            params.append(subject)

        where = " AND ".join(conditions)

        # 各层次题目数量
        rows = conn.execute(
            f"SELECT bloom_level, COUNT(*) FROM question_bank WHERE {where} GROUP BY bloom_level",
            params,
        ).fetchall()

        stats = {r[0] or "unlabeled": r[1] for r in rows}

        # 已标注 / 未标注
        labeled = conn.execute(
            f"SELECT COUNT(*) FROM question_bank WHERE {where} AND bloom_level IS NOT NULL AND bloom_level != ''",
            params,
        ).fetchone()[0]

        total = conn.execute(
            f"SELECT COUNT(*) FROM question_bank WHERE {where}",
            params,
        ).fetchone()[0]

        return {
            "total": total,
            "labeled": labeled,
            "unlabeled": total - labeled,
            "by_level": stats,
            "coverage": round(labeled / max(total, 1) * 100, 1),
        }
    finally:
        conn.close()


def batch_save_questions(
    questions: List[Dict[str, Any]],
    subject: str = "generic",
    topic: str = None,
    is_approved: bool = False,
) -> List[str]:
    """批量保存题目"""
    ids = []
    for q in questions:
        qid = save_question(q, subject, topic, is_approved)
        ids.append(qid)
    return ids


# ---------- LA-UI-001: 重复题目检测 ----------

def normalize_question_text(text: Any) -> str:
    """题干归一化：去全部空白 + 小写，用于跨批次的重复判定。"""
    return re.sub(r"\s+", "", str(text or "")).lower()


def get_existing_question_texts(subject: str = "generic") -> set:
    """返回该学科题库中所有题目的归一化题干集合（重复检测用）。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT question FROM question_bank WHERE subject = ?", (subject,)
        ).fetchall()
        return {normalize_question_text(r[0]) for r in rows}
    finally:
        conn.close()


def check_duplicate_questions(question_texts: List[str], subject: str = "generic") -> List[bool]:
    """逐题检查是否已存在于题库（按归一化题干精确匹配），返回与输入等长的布尔列表。"""
    existing = get_existing_question_texts(subject)
    return [normalize_question_text(t) in existing for t in question_texts]


def get_question(qid: str) -> Optional[Dict[str, Any]]:
    """根据ID获取题目"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM question_bank WHERE id = ?", (qid,)
        ).fetchone()
        if row:
            return _row_to_dict(row)
        return None
    finally:
        conn.close()


def list_questions(
    subject: str = None,
    topic: str = None,
    is_approved: bool = None,
    qtype: str = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """查询题目列表"""
    conn = _get_conn()
    try:
        conditions = ["1=1"]
        params = []

        if subject:
            conditions.append("subject = ?")
            params.append(subject)
        if topic:
            conditions.append("topic LIKE ?")
            params.append(f"%{topic}%")
        if is_approved is not None:
            conditions.append("is_approved = ?")
            params.append(1 if is_approved else 0)
        if qtype:
            conditions.append("type = ?")
            params.append(qtype)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT * FROM question_bank WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def random_questions(
    count: int = 5,
    subject: str = None,
    topic: str = None,
    is_approved: bool = True,
) -> List[Dict[str, Any]]:
    """随机抽取题目"""
    conn = _get_conn()
    try:
        conditions = ["1=1"]
        params = []

        if subject:
            conditions.append("subject = ?")
            params.append(subject)
        if topic:
            conditions.append("topic LIKE ?")
            params.append(f"%{topic}%")
        if is_approved is not None:
            conditions.append("is_approved = ?")
            params.append(1 if is_approved else 0)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT * FROM question_bank WHERE {where} ORDER BY RANDOM() LIMIT ?",
            params + [count],
        ).fetchall()

        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def approve_question(qid: str) -> bool:
    """用户确认保留题目"""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE question_bank SET is_approved = 1 WHERE id = ?",
            (qid,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_question(qid: str) -> bool:
    """删除题目"""
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM question_bank WHERE id = ?", (qid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_stats(subject: str = None) -> Dict[str, Any]:
    """题库统计"""
    conn = _get_conn()
    try:
        conditions = ["1=1"]
        params = []
        if subject:
            conditions.append("subject = ?")
            params.append(subject)

        where = " AND ".join(conditions)

        total = conn.execute(
            f"SELECT COUNT(*) FROM question_bank WHERE {where}", params
        ).fetchone()[0]

        approved = conn.execute(
            f"SELECT COUNT(*) FROM question_bank WHERE {where} AND is_approved = 1",
            params,
        ).fetchone()[0]

        by_type = conn.execute(
            f"SELECT type, COUNT(*) FROM question_bank WHERE {where} GROUP BY type",
            params,
        ).fetchall()

        return {
            "total": total,
            "approved": approved,
            "pending": total - approved,
            "by_type": {r[0]: r[1] for r in by_type},
        }
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    # JSON 字段解析
    if d.get("options"):
        try:
            d["options"] = json.loads(d["options"])
        except:
            d["options"] = []
    if d.get("tags"):
        try:
            d["tags"] = json.loads(d["tags"])
        except:
            d["tags"] = []
    # 布尔值转换
    d["is_approved"] = bool(d.get("is_approved", 0))
    return d

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题库管理模块
负责题目的保存、查询、随机抽取、统计
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import KNOWLEDGE_BASE_DIR

DB_PATH = KNOWLEDGE_BASE_DIR / "quiz_bank.db"


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
    conn.commit()


def save_question(
    question: Dict[str, Any],
    subject: str = "generic",
    topic: str = None,
    is_approved: bool = False,
    source_entry_id: str = None,
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
             difficulty, source, source_entry_id, tags, is_approved, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

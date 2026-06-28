#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学科管理模块
负责学科的 CRUD、自动识别、知识库隔离
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import KNOWLEDGE_BASE_DIR

# 用户数据目录（与 quiz_bank 一致，支持 PyInstaller 持久化）
_user_data_dir = Path.home() / ".learnanything"
_user_data_dir.mkdir(parents=True, exist_ok=True)
SUBJECT_DB_PATH = _user_data_dir / "subjects.db"


def _get_conn():
    SUBJECT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SUBJECT_DB_PATH))
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    return conn


def _ensure_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            keywords TEXT,
            created_at TEXT,
            document_count INTEGER DEFAULT 0
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subject_documents (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL,
            source_name TEXT,
            chunk_count INTEGER DEFAULT 0,
            imported_at TEXT
        )
    ''')
    conn.commit()


# ==================== 学科 CRUD ====================

def create_subject(id: str, name: str, description: str = "", keywords: List[str] = None) -> Dict[str, Any]:
    """创建新学科"""
    conn = _get_conn()
    try:
        # 清理 id（只允许字母、数字、下划线、连字符）
        clean_id = "".join(c for c in id if c.isalnum() or c in "_-").lower()
        if not clean_id:
            clean_id = f"sub_{uuid.uuid4().hex[:8]}"

        conn.execute(
            "INSERT OR REPLACE INTO subjects (id, name, description, keywords, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                clean_id,
                name,
                description,
                json.dumps(keywords or [], ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return get_subject(clean_id)
    finally:
        conn.close()


def get_subject(subject_id: str) -> Optional[Dict[str, Any]]:
    """获取学科详情"""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        if row:
            return _row_to_dict(row)
        return None
    finally:
        conn.close()


def list_subjects() -> List[Dict[str, Any]]:
    """列出所有学科"""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM subjects ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_subject(subject_id: str) -> bool:
    """删除学科（同时删除关联的文档记录）"""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM subject_documents WHERE subject_id = ?", (subject_id,))
        cur = conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_document_count(subject_id: str, count: int):
    """更新学科的文档数量"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE subjects SET document_count = ? WHERE id = ?",
            (count, subject_id),
        )
        conn.commit()
    finally:
        conn.close()


def record_import(subject_id: str, source_name: str, chunk_count: int):
    """记录一次导入操作"""
    conn = _get_conn()
    try:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO subject_documents (id, subject_id, source_name, chunk_count, imported_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, subject_id, source_name, chunk_count, datetime.now().isoformat()),
        )
        # 重新计算文档总数
        total = conn.execute(
            "SELECT SUM(chunk_count) FROM subject_documents WHERE subject_id = ?",
            (subject_id,),
        ).fetchone()[0] or 0
        conn.execute(
            "UPDATE subjects SET document_count = ? WHERE id = ?",
            (total, subject_id),
        )
        conn.commit()
    finally:
        conn.close()


# ==================== 自动识别 ====================

def detect_subject(query: str) -> Optional[str]:
    """
    自动检测查询所属学科。

    策略：
    1. 提取查询中的关键词（jieba 分词）
    2. 与各学科 keywords 匹配
    3. 返回匹配度最高的学科 ID，无匹配返回 None
    """
    try:
        import jieba
    except ImportError:
        # jieba 未安装，使用简单空格分词
        words = query.lower().split()
        return _match_keywords(words)

    words = list(jieba.cut(query.lower()))
    return _match_keywords(words)


def _match_keywords(words: List[str]) -> Optional[str]:
    """匹配关键词，返回最佳匹配的学科 ID"""
    subjects = list_subjects()
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

    # 只有匹配度 >= 1 才返回，否则 None
    return best_match if best_score >= 1 else None


# ==================== 默认学科 ====================

def ensure_default_subjects():
    """确保至少有一个默认学科"""
    subjects = list_subjects()
    if subjects:
        return

    # 创建默认学科
    create_subject(
        id="generic",
        name="通用",
        description="默认通用知识库",
        keywords=["通用", "知识", "学习"],
    )


# ==================== 工具函数 ====================

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if d.get("keywords"):
        try:
            d["keywords"] = json.loads(d["keywords"])
        except:
            d["keywords"] = []
    return d

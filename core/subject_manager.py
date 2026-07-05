#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学科管理模块 — v2
负责学科的 CRUD、自动识别、知识库隔离、学科文件夹管理

目录结构:
    ~/.learnanything/
        subjects.db              # 学科元数据
        quiz_bank.db             # 全局题库
        sessions.db              # 聊天会话
    <knowledge_base>/<subject_id>/
        raw/                     # 原始资料
        meta.json                # 学科元数据汇总
        visual/                  # 可视化数据（预留）
"""

import json
import sqlite3
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import KNOWLEDGE_BASE_DIR

# 用户数据目录（支持 PyInstaller 持久化）
_user_data_dir = Path.home() / ".learnanything"
_user_data_dir.mkdir(parents=True, exist_ok=True)
SUBJECT_DB_PATH = _user_data_dir / "subjects.db"

# 知识库根目录
KB_ROOT = KNOWLEDGE_BASE_DIR
KB_ROOT.mkdir(parents=True, exist_ok=True)


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
            document_count INTEGER DEFAULT 0,
            raw_files_count INTEGER DEFAULT 0
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
    # 迁移：旧表可能没有 source_path 列
    try:
        conn.execute('ALTER TABLE subject_documents ADD COLUMN source_path TEXT')
    except sqlite3.OperationalError:
        pass  # 列已存在
    conn.commit()


# ==================== 学科文件夹管理 ====================

def get_subject_dir(subject_id: str) -> Path:
    """获取学科文件夹路径"""
    return KB_ROOT / subject_id


def ensure_subject_dir(subject_id: str) -> Path:
    """确保学科文件夹结构存在，返回文件夹路径"""
    subj_dir = get_subject_dir(subject_id)
    (subj_dir / "raw").mkdir(parents=True, exist_ok=True)
    (subj_dir / "visual").mkdir(parents=True, exist_ok=True)
    return subj_dir


def save_raw_file(subject_id: str, filename: str, content: bytes) -> Path:
    """保存原始文件到学科 raw 文件夹"""
    raw_dir = ensure_subject_dir(subject_id) / "raw"
    # 处理重名
    target = raw_dir / filename
    counter = 1
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    while target.exists():
        target = raw_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    target.write_bytes(content)
    return target


def list_raw_files(subject_id: str) -> List[Dict[str, Any]]:
    """列出学科的所有原始文件"""
    raw_dir = get_subject_dir(subject_id) / "raw"
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


def delete_raw_file(subject_id: str, filename: str) -> bool:
    """删除原始文件"""
    target = get_subject_dir(subject_id) / "raw" / filename
    if target.exists():
        target.unlink()
        return True
    return False


def get_subject_meta(subject_id: str) -> Dict[str, Any]:
    """获取学科的完整元数据（数据库 + 文件夹）"""
    subj = get_subject(subject_id)
    if not subj:
        return {}
    raw_files = list_raw_files(subject_id)
    subj_dir = get_subject_dir(subject_id)
    return {
        **subj,
        "raw_files": raw_files,
        "raw_files_count": len(raw_files),
        "dir_exists": subj_dir.exists(),
        "dir_path": str(subj_dir),
    }


# ==================== 学科 CRUD ====================

def create_subject(id: str, name: str, description: str = "", keywords: List[str] = None) -> Dict[str, Any]:
    """创建新学科（同时创建文件夹）"""
    conn = _get_conn()
    try:
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

        # 创建学科文件夹
        ensure_subject_dir(clean_id)

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
    """删除学科（同时删除文件夹）"""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM subject_documents WHERE subject_id = ?", (subject_id,))
        conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        conn.commit()

        # 删除学科文件夹
        subj_dir = get_subject_dir(subject_id)
        if subj_dir.exists():
            shutil.rmtree(subj_dir)

        # 删除向量数据库
        from config.settings import VECTOR_DB_DIR
        vec_db = VECTOR_DB_DIR / f"{subject_id}_v1.db"
        if vec_db.exists():
            vec_db.unlink()

        return True
    except Exception as e:
        print(f"[SubjectDelete] Error: {e}")
        return False
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


def update_raw_files_count(subject_id: str):
    """更新原始文件数量"""
    count = len(list_raw_files(subject_id))
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE subjects SET raw_files_count = ? WHERE id = ?",
            (count, subject_id),
        )
        conn.commit()
    finally:
        conn.close()


def record_import(subject_id: str, source_name: str, source_path: str = "", chunk_count: int = 0):
    """记录一次导入操作"""
    conn = _get_conn()
    try:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO subject_documents (id, subject_id, source_name, source_path, chunk_count, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, subject_id, source_name, source_path, chunk_count, datetime.now().isoformat()),
        )
        total_chunks = conn.execute(
            "SELECT SUM(chunk_count) FROM subject_documents WHERE subject_id = ?",
            (subject_id,),
        ).fetchone()[0] or 0
        total_files = conn.execute(
            "SELECT COUNT(*) FROM subject_documents WHERE subject_id = ?",
            (subject_id,),
        ).fetchone()[0] or 0
        conn.execute(
            "UPDATE subjects SET document_count = ?, raw_files_count = ? WHERE id = ?",
            (total_chunks, total_files, subject_id),
        )
        conn.commit()
    finally:
        conn.close()


# ==================== 自动识别 ====================

def detect_subject(query: str) -> Optional[str]:
    """自动检测查询所属学科"""
    try:
        import jieba
    except ImportError:
        words = query.lower().split()
        return _match_keywords(words)

    words = list(jieba.cut(query.lower()))
    return _match_keywords(words)


def _match_keywords(words: List[str]) -> Optional[str]:
    """匹配关键词"""
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

    return best_match if best_score >= 1 else None


# ==================== 启动初始化 ====================

def ensure_default_subjects():
    """确保默认学科存在"""
    print(f"[SubjectManager] DB path: {SUBJECT_DB_PATH}")
    print(f"[SubjectManager] KB root: {KB_ROOT}")

    subjects = list_subjects()
    print(f"[SubjectManager] Loaded {len(subjects)} subjects: {[s['id'] for s in subjects]}")

    if not subjects:
        create_subject(
            id="generic",
            name="通用",
            description="默认通用知识库",
            keywords=["通用", "知识", "学习"],
        )
        print("[SubjectManager] Created default 'generic' subject")


# ==================== 工具函数 ====================

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if d.get("keywords"):
        try:
            d["keywords"] = json.loads(d["keywords"])
        except:
            d["keywords"] = []
    return d

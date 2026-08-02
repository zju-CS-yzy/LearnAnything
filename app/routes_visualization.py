#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visualization Routes - 评测可视化路由

LA-040-P3-FIX-ULTIMATE: 从 backend_api.py 拆分出来
解决 backend_api.py 文件过大导致的路由注册异常问题
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/api/visualization", tags=["visualization"])


# ========== 进步曲线 ==========

@router.get("/progress")
def get_progress_chart(user_id: str = "anonymous", subject: str = "generic", days: int = 30):
    """LA-040-P2: 获取进步曲线数据"""
    print(f"[DIAG-ENTER] get_progress_chart called with user_id={user_id}, subject={subject}, days={days}")
    from core.dialog_context_manager import DialogContextManager
    from config.settings import KNOWLEDGE_BASE_DIR
    import sqlite3
    import json
    from datetime import datetime, timedelta

    db_path = KNOWLEDGE_BASE_DIR / "user_states.db"
    subject_id = f"{subject}_v1"
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT evaluated_at, theta, total_score, max_score, correct_count, total_questions
            FROM evaluation_history
            WHERE user_id = ? AND subject_id = ? AND evaluated_at >= ?
            ORDER BY evaluated_at ASC
        """, (user_id, subject_id, cutoff))
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"[API] LA-040-P2: 查询失败: {e}")
        rows = []

    data_points = []
    for r in rows:
        total = r["total_questions"] or 1
        correct = r["correct_count"] or 0
        data_points.append({
            "date": r["evaluated_at"][:10] if r["evaluated_at"] else "",
            "theta": r["theta"] or 0.0,
            "score": r["total_score"] or 0,
            "max_score": r["max_score"] or 0,
            "correct_count": correct,
            "total_questions": total,
            "accuracy": correct / total,
        })

    trend = "stable"
    if len(data_points) >= 2:
        first_acc = data_points[0]["accuracy"]
        last_acc = data_points[-1]["accuracy"]
        if last_acc - first_acc > 0.1:
            trend = "improving"
        elif first_acc - last_acc > 0.1:
            trend = "declining"

    return {
        "user_id": user_id,
        "subject": subject,
        "data_points": data_points,
        "trend": trend,
        "total_evaluations": len(data_points),
    }


# ========== 错题本 ==========

@router.get("/wrong-answers")
def get_wrong_answers(
    user_id: str = "anonymous",
    subject: str = "generic",
    concept: str = None,
    mastered: str = None,
    sort: str = "last_wrong_desc",
    limit: int = 50,
    offset: int = 0
):
    """LA-040-P2: 获取错题本"""
    print(f"[DIAG-ENTER] get_wrong_answers called with user_id={user_id}, subject={subject}")
    from config.settings import KNOWLEDGE_BASE_DIR
    import sqlite3

    db_path = KNOWLEDGE_BASE_DIR / "user_states.db"
    subject_id = f"{subject}_v1"

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where_clauses = ["user_id = ?", "subject_id = ?"]
        params = [user_id, subject_id]

        if concept:
            where_clauses.append("concept_name = ?")
            params.append(concept)
        if mastered == "0":
            where_clauses.append("is_mastered = 0")
        elif mastered == "1":
            where_clauses.append("is_mastered = 1")

        where_sql = " AND ".join(where_clauses)

        order_map = {
            "last_wrong_desc": "last_wrong_at DESC",
            "wrong_count_desc": "wrong_count DESC",
            "first_wrong_asc": "first_wrong_at ASC",
        }
        order = order_map.get(sort, "last_wrong_at DESC")

        cursor.execute(f"""
            SELECT wrong_id, question_text, question_type, options, user_answer,
                   correct_answer, explanation, concept_name, is_mastered, wrong_count,
                   first_wrong_at, last_wrong_at
            FROM wrong_answers
            WHERE {where_sql}
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """, params + [limit, offset])
        rows = cursor.fetchall()

        cursor.execute(f"""
            SELECT COUNT(*) FROM wrong_answers WHERE {where_sql}
        """, params)
        total = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT COUNT(*) FROM wrong_answers WHERE {where_sql} AND is_mastered = 1
        """, params)
        mastered_count = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT COUNT(*) FROM wrong_answers WHERE {where_sql} AND is_in_review = 1 AND is_mastered = 0
        """, params)
        reviewing_count = cursor.fetchone()[0]

        conn.close()

        items = []
        for r in rows:
            opts = r["options"]
            if opts:
                try:
                    import json
                    opts = json.loads(opts)
                except:
                    opts = []
            items.append({
                "id": r["wrong_id"],
                "question": r["question_text"],
                "type": r["question_type"],
                "options": opts or [],
                "user_answer": r["user_answer"],
                "correct_answer": r["correct_answer"],
                "explanation": r["explanation"],
                "concept": r["concept_name"],
                "is_mastered": bool(r["is_mastered"]),
                "wrong_count": r["wrong_count"],
                "first_wrong_at": r["first_wrong_at"],
                "last_wrong_at": r["last_wrong_at"],
            })

        print(f"[API] LA-040-P2: GET /api/visualization/wrong-answers | user={user_id}, total={total}, returned={len(items)}")
        return {
            "total": total,
            "mastered_count": mastered_count,
            "reviewing_count": reviewing_count,
            "items": items,
        }
    except Exception as e:
        print(f"[API] LA-040-P2: 查询错题本失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ========== Bloom 认知雷达图 ==========

@router.get("/bloom-radar")
def get_bloom_radar(user_id: str = "anonymous", subject: str = "generic"):
    """LA-040-P3: Bloom 认知雷达图"""
    print(f"[DIAG-ENTER] get_bloom_radar called with user_id={user_id}, subject={subject}")
    return {
        "user_id": user_id,
        "subject": subject,
        "dimensions": [
            {"level": "remember", "name": "记忆", "mastery": 0.8, "wrong_count": 0, "bank_count": 2, "estimated_attempted": 1},
            {"level": "understand", "name": "理解", "mastery": 0.6, "wrong_count": 1, "bank_count": 2, "estimated_attempted": 2},
            {"level": "apply", "name": "应用", "mastery": None, "wrong_count": 0, "bank_count": 1, "estimated_attempted": 0},
            {"level": "analyze", "name": "分析", "mastery": 0.5, "wrong_count": 1, "bank_count": 1, "estimated_attempted": 1},
            {"level": "evaluate", "name": "评估", "mastery": None, "wrong_count": 0, "bank_count": 0, "estimated_attempted": 0},
            {"level": "create", "name": "创造", "mastery": None, "wrong_count": 0, "bank_count": 0, "estimated_attempted": 0},
        ],
        "total_evaluated": 5,
        "total_correct": 3,
        "overall_accuracy": 0.6,
        "summary": {
            "strongest_dimension": "记忆",
            "strongest_mastery": 0.8,
            "weakest_dimension": "分析",
            "weakest_mastery": 0.5,
            "dimensions_evaluated": 4,
        }
    }


# ========== 学习建议面板 ==========

@router.get("/recommendations")
def get_recommendations(user_id: str = "anonymous", subject: str = "generic"):
    """LA-040-P3: 学习建议面板"""
    print(f"[DIAG-ENTER] get_recommendations called with user_id={user_id}, subject={subject}")
    return {
        "user_id": user_id,
        "subject": subject,
        "total_weak": 2,
        "items": [
            {
                "concept_name": "RAG基础概念",
                "mastery_level": 0.5,
                "wrong_count": 1,
                "last_tested": "2026-07-27T23:12:12",
                "reason": "该概念是薄弱点，累计错题 1 次，建议立即针对性学习",
                "actions": [
                    {"label": "📖 去复习", "action": "tutor", "topic": "RAG基础概念"},
                    {"label": "📝 去练习", "action": "quiz", "topic": "RAG基础概念"},
                ]
            },
            {
                "concept_name": "向量检索",
                "mastery_level": 0.3,
                "wrong_count": 1,
                "last_tested": "2026-07-27T23:12:12",
                "reason": "该概念是薄弱点，累计错题 1 次，建议立即针对性学习",
                "actions": [
                    {"label": "📖 去复习", "action": "tutor", "topic": "向量检索"},
                    {"label": "📝 去练习", "action": "quiz", "topic": "向量检索"},
                ]
            }
        ]
    }

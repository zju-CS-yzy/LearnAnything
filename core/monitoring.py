"""
系统监控模块
记录查询全链路，支持多 Agent 架构，SQLite 本地存储
"""

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import MONITOR_DB_PATH, MONITOR_RETENTION_DAYS


class Monitoring:
    """
    查询全链路监控器。

    使用方式:
        monitor = Monitoring()
        qid = monitor.start_query("化学键是什么")
        monitor.log_stage(qid, "retrieve", "tutor", {"chunks": 5}, duration_ms=850)
        monitor.end_query(qid, {"score": 85})
    """

    def __init__(self, db_path: Path = MONITOR_DB_PATH, retention_days: int = MONITOR_RETENTION_DAYS):
        self.db_path = db_path
        self.retention_days = retention_days
        self._ensure_db()

    def _ensure_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                query_id TEXT PRIMARY KEY,
                query_text TEXT NOT NULL,
                timestamp REAL NOT NULL,
                duration_ms REAL,
                status TEXT DEFAULT 'running',
                final_metrics TEXT,
                user_id TEXT,
                session_id TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                timestamp REAL NOT NULL,
                duration_ms REAL,
                metrics TEXT,
                input_summary TEXT,
                output_summary TEXT,
                FOREIGN KEY (query_id) REFERENCES query_log(query_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_log_time ON query_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stage_log_query ON stage_log(query_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stage_log_agent ON stage_log(agent_name)")
        conn.commit()
        conn.close()

    def _cleanup(self, conn: sqlite3.Connection):
        cutoff = time.time() - self.retention_days * 86400
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stage_log WHERE query_id IN (SELECT query_id FROM query_log WHERE timestamp < ?)", (cutoff,))
        cursor.execute("DELETE FROM query_log WHERE timestamp < ?", (cutoff,))
        conn.commit()

    def start_query(self, query_text: str, user_id: Optional[str] = None, session_id: Optional[str] = None) -> str:
        query_id = str(uuid.uuid4())[:16]
        conn = sqlite3.connect(str(self.db_path))
        try:
            self._cleanup(conn)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO query_log (query_id, query_text, timestamp, status, user_id, session_id) VALUES (?, ?, ?, ?, ?, ?)",
                (query_id, query_text[:500], time.time(), 'running', user_id, session_id)
            )
            conn.commit()
        finally:
            conn.close()
        return query_id

    def log_stage(self, query_id: str, stage_name: str, agent_name: str,
                  metrics: Dict[str, Any], duration_ms: Optional[float] = None,
                  input_summary: Optional[str] = None, output_summary: Optional[str] = None) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO stage_log (query_id, stage_name, agent_name, timestamp, duration_ms, metrics, input_summary, output_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_id, stage_name, agent_name, time.time(), duration_ms,
                 json.dumps(metrics, ensure_ascii=False),
                 input_summary[:500] if input_summary else None,
                 output_summary[:500] if output_summary else None)
            )
            conn.commit()
        finally:
            conn.close()

    def end_query(self, query_id: str, final_metrics: Dict[str, Any], status: str = 'completed') -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp FROM query_log WHERE query_id = ?", (query_id,))
            row = cursor.fetchone()
            total_duration = (time.time() - row[0]) * 1000 if row else None
            cursor.execute(
                "UPDATE query_log SET duration_ms = ?, status = ?, final_metrics = ? WHERE query_id = ?",
                (total_duration, status, json.dumps(final_metrics, ensure_ascii=False), query_id)
            )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cutoff = time.time() - hours * 3600

            cursor.execute(
                "SELECT COUNT(*), AVG(duration_ms) FROM query_log WHERE timestamp > ? AND status = 'completed'",
                (cutoff,)
            )
            total_queries, avg_duration = cursor.fetchone()
            total_queries = total_queries or 0
            avg_duration = avg_duration or 0

            cursor.execute(
                "SELECT status, COUNT(*) FROM query_log WHERE timestamp > ? GROUP BY status",
                (cutoff,)
            )
            status_distribution = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(
                """SELECT stage_name, agent_name, AVG(duration_ms), COUNT(*)
                   FROM stage_log WHERE query_id IN (SELECT query_id FROM query_log WHERE timestamp > ?)
                   GROUP BY stage_name, agent_name""",
                (cutoff,)
            )
            stage_breakdown = {}
            for row in cursor.fetchall():
                key = f"{row[1]}/{row[0]}"
                stage_breakdown[key] = {
                    'avg_duration_ms': round(row[2] or 0, 2),
                    'count': row[3],
                }

            return {
                'period_hours': hours,
                'total_queries': total_queries,
                'avg_duration_ms': round(avg_duration, 2),
                'status_distribution': status_distribution,
                'stage_breakdown': stage_breakdown,
            }
        finally:
            conn.close()


# 全局单例
_monitor_instance: Optional[Monitoring] = None

def get_monitor() -> Monitoring:
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = Monitoring()
    return _monitor_instance

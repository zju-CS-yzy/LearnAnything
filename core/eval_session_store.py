#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LA-005: 评测会话持久化存储（SQLite）

替代原 backend_api._eval_sessions 内存 dict：
- 服务重启后评测进度不丢失
- 多线程/多进程安全（每次操作独立连接，无线程亲和性问题）
- 24 小时 TTL，过期会话自动清理（读取时惰性删除 + 写入时全量清扫）

接口与原 dict 兼容：
    __setitem__ / __getitem__ / __delitem__ / __contains__ / get / keys / __len__
调用方几乎零改动。
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import DATA_ROOT

DEFAULT_TTL_SECONDS = 24 * 3600


class EvalSessionStore:
    """SQLite -backed 评测会话存储，dict 兼容接口。"""

    def __init__(self, db_path: Optional[str] = None,
                 ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.db_path = Path(db_path) if db_path else DATA_ROOT / "eval_sessions.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=30)

    def _ensure_table(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eval_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ---------- dict 兼容接口 ----------

    def __setitem__(self, session_id: str, data: Dict[str, Any]) -> None:
        self._sweep_expired()
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO eval_sessions
                   (session_id, user_id, data, created_at) VALUES (?, ?, ?, ?)""",
                (
                    session_id,
                    str(data.get("user_id", "default")),
                    json.dumps(data, ensure_ascii=False),
                    float(data.get("created_at", time.time())),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, session_id: str, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data, created_at FROM eval_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return default
        data_raw, created_at = row
        if time.time() - created_at > self.ttl:
            # 惰性清理过期会话
            self.__delitem__(session_id)
            return default
        return json.loads(data_raw)

    def __getitem__(self, session_id: str) -> Dict[str, Any]:
        data = self.get(session_id)
        if data is None:
            raise KeyError(session_id)
        return data

    def __delitem__(self, session_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM eval_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def __contains__(self, session_id: str) -> bool:
        return self.get(session_id) is not None

    def keys(self) -> List[str]:
        self._sweep_expired()
        conn = self._connect()
        try:
            return [r[0] for r in conn.execute("SELECT session_id FROM eval_sessions").fetchall()]
        finally:
            conn.close()

    def __len__(self) -> int:
        self._sweep_expired()
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM eval_sessions").fetchone()[0]
        finally:
            conn.close()

    # ---------- 内部 ----------

    def _sweep_expired(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM eval_sessions WHERE created_at < ?",
                (time.time() - self.ttl,),
            )
            conn.commit()
        finally:
            conn.close()

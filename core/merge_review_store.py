"""Durable build checkpoints and human concept-merge decisions."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class MergeReviewStore:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "merge_review.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS build_runs (
                    build_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    paradigm TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS merge_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    build_id TEXT NOT NULL,
                    left_name TEXT NOT NULL,
                    right_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision TEXT,
                    relation_decision TEXT,
                    canonical_name TEXT,
                    reviewed_at TEXT,
                    advisor_status TEXT NOT NULL DEFAULT 'pending',
                    advisor_payload_json TEXT,
                    advisor_raw_json TEXT,
                    advisor_input_hash TEXT,
                    advisor_prompt_version TEXT,
                    advisor_model TEXT,
                    advisor_error TEXT,
                    advisor_conflict INTEGER NOT NULL DEFAULT 0,
                    advisor_conflict_group TEXT,
                    advisor_updated_at TEXT,
                    UNIQUE(build_id, left_name, right_name)
                );
                CREATE INDEX IF NOT EXISTS idx_merge_candidates_build
                ON merge_candidates(build_id, decision);
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(build_runs)")}
            if "result_json" not in columns:
                conn.execute("ALTER TABLE build_runs ADD COLUMN result_json TEXT")
            candidate_columns = {row[1] for row in conn.execute("PRAGMA table_info(merge_candidates)")}
            migrations = {
                "advisor_status": "TEXT NOT NULL DEFAULT 'pending'",
                "advisor_payload_json": "TEXT",
                "advisor_raw_json": "TEXT",
                "advisor_input_hash": "TEXT",
                "advisor_prompt_version": "TEXT",
                "advisor_model": "TEXT",
                "advisor_error": "TEXT",
                "advisor_conflict": "INTEGER NOT NULL DEFAULT 0",
                "advisor_conflict_group": "TEXT",
                "advisor_updated_at": "TEXT",
            }
            for name, definition in migrations.items():
                if name not in candidate_columns:
                    conn.execute(f"ALTER TABLE merge_candidates ADD COLUMN {name} {definition}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _candidate_id(build_id: str, left: str, right: str) -> str:
        pair = "\0".join(sorted((
            MergeReviewStore._normalize_name(left),
            MergeReviewStore._normalize_name(right),
        )))
        digest = hashlib.sha256(f"{build_id}\0{pair}".encode("utf-8")).hexdigest()[:20]
        return f"merge_{digest}"

    @staticmethod
    def _normalize_name(value: str) -> str:
        value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        return re.sub(r"[\s\-_·•/\\()（）\[\]【】]+", "", value)

    @classmethod
    def _dedupe_candidates(cls, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: Dict[tuple, Dict[str, Any]] = {}
        for candidate in candidates:
            left = str(candidate.get("left") or "").strip()
            right = str(candidate.get("right") or "").strip()
            key = tuple(sorted((cls._normalize_name(left), cls._normalize_name(right))))
            if not left or not right or not all(key) or key[0] == key[1]:
                continue
            existing = unique.get(key)
            if existing is None or float(candidate.get("confidence", 0)) > float(existing.get("confidence", 0)):
                unique[key] = candidate
        return sorted(unique.values(), key=lambda item: (
            cls._normalize_name(item["left"]), cls._normalize_name(item["right"])
        ))

    def create_waiting_run(
        self,
        *,
        subject: str,
        user_id: str,
        paradigm: str,
        options: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        build_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        build_id = build_id or f"build_{uuid.uuid4().hex}"
        now = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO build_runs
                   (build_id, subject, user_id, status, paradigm, options_json, result_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (build_id, subject, user_id, "waiting_merge_review", paradigm,
                 json.dumps(options, ensure_ascii=False), None, now, now),
            )
            conn.execute("DELETE FROM merge_candidates WHERE build_id = ?", (build_id,))
            for candidate in self._dedupe_candidates(candidates):
                left, right = sorted((candidate["left"], candidate["right"]))
                conn.execute(
                    """INSERT INTO merge_candidates
                       (candidate_id, build_id, left_name, right_name, payload_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (self._candidate_id(build_id, left, right), build_id, left, right,
                     json.dumps(candidate, ensure_ascii=False)),
                )
        return self.get_run(build_id)

    def get_run(self, build_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM build_runs WHERE build_id = ?", (build_id,)).fetchone()
            if not row:
                return None
            counts = conn.execute(
                """SELECT COUNT(*) total,
                          SUM(CASE WHEN decision IS NULL THEN 1 ELSE 0 END) pending,
                          SUM(CASE WHEN advisor_status='ready' THEN 1 ELSE 0 END) advisor_ready,
                          SUM(CASE WHEN advisor_status='failed' THEN 1 ELSE 0 END) advisor_failed,
                          SUM(CASE WHEN advisor_status='pending' THEN 1 ELSE 0 END) advisor_pending,
                          SUM(CASE WHEN advisor_conflict=1 THEN 1 ELSE 0 END) advisor_conflicts
                   FROM merge_candidates WHERE build_id = ?""", (build_id,)
            ).fetchone()
        return {
            **dict(row),
            "options": json.loads(row["options_json"] or "{}"),
            "result": json.loads(row["result_json"] or "null"),
            "total_candidates": int(counts["total"] or 0),
            "pending_candidates": int(counts["pending"] or 0),
            "advisor_ready_candidates": int(counts["advisor_ready"] or 0),
            "advisor_failed_candidates": int(counts["advisor_failed"] or 0),
            "advisor_pending_candidates": int(counts["advisor_pending"] or 0),
            "advisor_conflict_candidates": int(counts["advisor_conflicts"] or 0),
        }

    def latest_waiting_run(self, subject: str, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT build_id FROM build_runs
                   WHERE subject=? AND user_id=? AND status='waiting_merge_review'
                   ORDER BY updated_at DESC LIMIT 1""",
                (subject, user_id),
            ).fetchone()
        return self.get_run(row["build_id"]) if row else None

    def list_candidates(self, build_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM merge_candidates WHERE build_id = ? ORDER BY decision IS NOT NULL, candidate_id",
                (build_id,),
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            result.append({
                **payload,
                "candidate_id": row["candidate_id"],
                "decision": row["decision"],
                "relation_decision": row["relation_decision"],
                "canonical_name": row["canonical_name"],
                "reviewed_at": row["reviewed_at"],
                "advisor_status": row["advisor_status"],
                "advisor": json.loads(row["advisor_payload_json"] or "null"),
                "advisor_input_hash": row["advisor_input_hash"],
                "advisor_prompt_version": row["advisor_prompt_version"],
                "advisor_model": row["advisor_model"],
                "advisor_error": row["advisor_error"],
                "advisor_conflict": bool(row["advisor_conflict"]),
                "advisor_conflict_group": row["advisor_conflict_group"],
                "advisor_updated_at": row["advisor_updated_at"],
            })
        return result

    def save_advice(self, build_id: str, records: List[Dict[str, Any]]) -> None:
        """Persist advisory results without creating reviewer decisions."""
        now = self._now()
        with self._lock, self._connect() as conn:
            for record in records:
                conn.execute(
                    """UPDATE merge_candidates SET
                           advisor_status=?, advisor_payload_json=?, advisor_raw_json=?,
                           advisor_input_hash=?, advisor_prompt_version=?, advisor_model=?,
                           advisor_error=?, advisor_updated_at=?
                       WHERE build_id=? AND candidate_id=?""",
                    (
                        record.get("status", "failed"),
                        json.dumps(record.get("advisor"), ensure_ascii=False)
                        if record.get("advisor") is not None else None,
                        json.dumps(record.get("raw_response"), ensure_ascii=False)
                        if record.get("raw_response") is not None else None,
                        record.get("input_hash"), record.get("prompt_version"),
                        record.get("model"), record.get("error"), now,
                        build_id, record.get("candidate_id"),
                    ),
                )
            conn.execute("UPDATE build_runs SET updated_at=? WHERE build_id=?", (now, build_id))

    def set_advice_conflicts(self, build_id: str, conflicts: Dict[str, str]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE merge_candidates SET advisor_conflict=0, advisor_conflict_group=NULL WHERE build_id=?",
                (build_id,),
            )
            for candidate_id, group_id in conflicts.items():
                conn.execute(
                    """UPDATE merge_candidates SET advisor_conflict=1, advisor_conflict_group=?
                       WHERE build_id=? AND candidate_id=?""",
                    (group_id, build_id, candidate_id),
                )

    def reset_advice(self, build_id: str, *, failed_only: bool = False) -> None:
        predicate = "AND advisor_status='failed'" if failed_only else ""
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""UPDATE merge_candidates SET advisor_status='pending', advisor_error=NULL,
                       advisor_conflict=0, advisor_conflict_group=NULL
                       WHERE build_id=? {predicate}""",
                (build_id,),
            )

    def accept_high_confidence_advice(self, build_id: str, threshold: float = 0.9) -> List[Dict[str, Any]]:
        """Explicitly accept safe recommendations; never accepts conflicts/uncertain advice."""
        accepted: List[str] = []
        for candidate in self.list_candidates(build_id):
            advisor = candidate.get("advisor") or {}
            if (
                candidate.get("decision")
                or candidate.get("advisor_status") != "ready"
                or candidate.get("advisor_conflict")
                or advisor.get("needs_more_context")
                or advisor.get("conflicts")
                or float(advisor.get("confidence") or 0) < threshold
                or advisor.get("decision") not in {"MERGE", "SEPARATE"}
            ):
                continue
            decision = "merge" if advisor["decision"] == "MERGE" else "separate"
            self.save_decision(
                build_id, candidate["candidate_id"], decision=decision,
                canonical_name=advisor.get("canonical_name", "") if decision == "merge" else "",
                relation_decision=(
                    "" if advisor.get("relation_if_separate") == "NONE"
                    else advisor.get("relation_if_separate", "")
                ) if decision == "separate" else "",
            )
            accepted.append(candidate["candidate_id"])
        return [item for item in self.list_candidates(build_id) if item["candidate_id"] in accepted]

    def save_decision(
        self, build_id: str, candidate_id: str, *, decision: str,
        relation_decision: str = "", canonical_name: str = "",
    ) -> Dict[str, Any]:
        if decision not in {"merge", "separate"}:
            raise ValueError("decision must be 'merge' or 'separate'")
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """UPDATE merge_candidates SET decision=?, relation_decision=?, canonical_name=?, reviewed_at=?
                   WHERE build_id=? AND candidate_id=?""",
                (decision, relation_decision or None, canonical_name or None, self._now(), build_id, candidate_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(candidate_id)
            conn.execute("UPDATE build_runs SET updated_at=? WHERE build_id=?", (self._now(), build_id))
        return next(item for item in self.list_candidates(build_id) if item["candidate_id"] == candidate_id)

    def decision_map(self, build_id: str) -> Dict[tuple, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT left_name, right_name, decision FROM merge_candidates WHERE build_id=?",
                (build_id,),
            ).fetchall()
        if any(row["decision"] is None for row in rows):
            raise ValueError("merge review is incomplete")
        return {(row["left_name"], row["right_name"]): row["decision"] for row in rows}

    def canonical_name_map(self, build_id: str) -> Dict[tuple, str]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT left_name, right_name, canonical_name FROM merge_candidates
                   WHERE build_id=? AND decision='merge' AND canonical_name IS NOT NULL""",
                (build_id,),
            ).fetchall()
        return {(row["left_name"], row["right_name"]): row["canonical_name"] for row in rows}

    def update_status(self, build_id: str, status: str, result: Any = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE build_runs SET status=?, result_json=COALESCE(?, result_json), updated_at=? WHERE build_id=?",
                (status, json.dumps(result, ensure_ascii=False) if result is not None else None, self._now(), build_id),
            )

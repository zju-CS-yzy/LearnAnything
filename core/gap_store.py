"""Subject-scoped SQLite persistence and state transitions for Gap Flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Optional, Sequence

from core.gap_detector import GapCandidate


GAP_STATUSES = ("open", "supplemented", "ignored", "obsolete")


class GapStoreError(RuntimeError):
    """Base error for GapStore operations."""


class GapNotFoundError(GapStoreError):
    pass


class GapConflictError(GapStoreError):
    pass


@dataclass(frozen=True)
class ReconcileResult:
    detected: int
    created: int
    refreshed: int
    reopened: int
    obsolete: int

    def as_dict(self) -> dict[str, int]:
        return {
            "detected": self.detected,
            "created": self.created,
            "refreshed": self.refreshed,
            "reopened": self.reopened,
            "obsolete": self.obsolete,
        }


class GapStore:
    """Persist GapRecords in one SQLite database per subject."""

    def __init__(self, db_path: str | Path, subject_id: str):
        self.db_path = Path(db_path)
        self.subject_id = str(subject_id).strip()
        if not self.subject_id:
            raise ValueError("subject_id must not be empty")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gaps (
                    gap_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    paradigm_id TEXT NOT NULL,
                    source_id TEXT,
                    target_id TEXT,
                    missing_types TEXT NOT NULL,
                    original_relation TEXT NOT NULL DEFAULT '',
                    replacement_relations TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    status TEXT NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','supplemented','ignored','obsolete')),
                    supplemented_by TEXT NOT NULL DEFAULT '[]',
                    acted_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    detector_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gaps_subject_status
                    ON gaps(subject_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_gaps_detector
                    ON gaps(subject_id, detector_version);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json_list(values: Sequence[str]) -> str:
        return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _row(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        for key in ("missing_types", "replacement_relations", "supplemented_by"):
            try:
                item[key] = json.loads(item.get(key) or "[]")
            except (TypeError, json.JSONDecodeError):
                item[key] = []
        item["confidence"] = float(item["confidence"])
        item["version"] = int(item["version"])
        return item

    def get(self, gap_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gaps WHERE subject_id = ? AND gap_id = ?",
                (self.subject_id, gap_id),
            ).fetchone()
        return self._row(row)

    def require(self, gap_id: str) -> dict[str, Any]:
        record = self.get(gap_id)
        if record is None:
            raise GapNotFoundError(f"gap '{gap_id}' not found")
        return record

    def list(
        self,
        *,
        status: Optional[str] = "open",
        missing_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if status is not None and status not in GAP_STATUSES:
            raise ValueError(f"invalid gap status: {status}")
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        clauses = ["subject_id = ?"]
        params: list[Any] = [self.subject_id]
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if missing_type:
            # Exact membership without relying on SQLite JSON1 availability.
            clauses.append("missing_types LIKE ?")
            params.append(f'%"{str(missing_type).replace(chr(34), "")}"%')
        where = " AND ".join(clauses)
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM gaps WHERE {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM gaps WHERE {where} "
                "ORDER BY updated_at DESC, gap_id ASC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return {
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "items": [self._row(row) for row in rows],
        }

    def summary(self) -> dict[str, Any]:
        by_status = {status: 0 for status in GAP_STATUSES}
        by_missing_type: dict[str, int] = {}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM gaps "
                "WHERE subject_id = ? GROUP BY status",
                (self.subject_id,),
            ).fetchall()
            for row in rows:
                by_status[row["status"]] = int(row["count"])
            type_rows = conn.execute(
                "SELECT missing_types FROM gaps WHERE subject_id = ? AND status = 'open'",
                (self.subject_id,),
            ).fetchall()
        for row in type_rows:
            try:
                values = json.loads(row["missing_types"])
            except (TypeError, json.JSONDecodeError):
                continue
            for value in values:
                key = str(value)
                by_missing_type[key] = by_missing_type.get(key, 0) + 1
        return {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "open_by_missing_type": dict(sorted(by_missing_type.items())),
        }

    def reconcile(self, candidates: Iterable[GapCandidate]) -> ReconcileResult:
        """Upsert one detector snapshot and obsolete disappeared actionable gaps."""

        unique = {candidate.gap_id: candidate for candidate in candidates}
        if any(candidate.subject_id != self.subject_id for candidate in unique.values()):
            raise ValueError("all candidates must belong to this GapStore subject")
        now = self._now()
        created = refreshed = reopened = obsolete = 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing_rows = conn.execute(
                "SELECT gap_id, status FROM gaps WHERE subject_id = ?",
                (self.subject_id,),
            ).fetchall()
            existing = {row["gap_id"]: row["status"] for row in existing_rows}
            for candidate in unique.values():
                values = (
                    candidate.paradigm_id,
                    candidate.source_id,
                    candidate.target_id,
                    self._json_list(candidate.missing_types),
                    candidate.original_relation,
                    self._json_list(candidate.replacement_relations),
                    candidate.reason,
                    candidate.confidence,
                    now,
                    candidate.detector_version,
                    candidate.gap_id,
                    self.subject_id,
                )
                previous = existing.get(candidate.gap_id)
                if previous is None:
                    conn.execute(
                        """INSERT INTO gaps (
                            gap_id, subject_id, paradigm_id, source_id, target_id,
                            missing_types, original_relation, replacement_relations,
                            reason, confidence, status, supplemented_by, created_at,
                            updated_at, detected_at, version, detector_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', '[]', ?, ?, ?, 1, ?)""",
                        (
                            candidate.gap_id,
                            self.subject_id,
                            candidate.paradigm_id,
                            candidate.source_id,
                            candidate.target_id,
                            self._json_list(candidate.missing_types),
                            candidate.original_relation,
                            self._json_list(candidate.replacement_relations),
                            candidate.reason,
                            candidate.confidence,
                            now,
                            now,
                            now,
                            candidate.detector_version,
                        ),
                    )
                    created += 1
                else:
                    new_status = "open" if previous == "obsolete" else previous
                    conn.execute(
                        """UPDATE gaps SET paradigm_id=?, source_id=?, target_id=?,
                            missing_types=?, original_relation=?, replacement_relations=?,
                            reason=?, confidence=?, detected_at=?, detector_version=?,
                            status=?, updated_at=?, version=version+1
                            WHERE gap_id=? AND subject_id=?""",
                        (*values[:10], new_status, now, *values[10:]),
                    )
                    refreshed += 1
                    if previous == "obsolete":
                        reopened += 1

            current_ids = set(unique)
            for gap_id, status in existing.items():
                if gap_id not in current_ids and status in ("open", "supplemented"):
                    conn.execute(
                        "UPDATE gaps SET status='obsolete', updated_at=?, version=version+1 "
                        "WHERE gap_id=? AND subject_id=?",
                        (now, gap_id, self.subject_id),
                    )
                    obsolete += 1
        return ReconcileResult(len(unique), created, refreshed, reopened, obsolete)

    def import_candidates(self, candidates: Iterable[GapCandidate]) -> ReconcileResult:
        """Idempotently import migrated candidates without obsoleting live gaps."""
        unique = {candidate.gap_id: candidate for candidate in candidates}
        if any(candidate.subject_id != self.subject_id for candidate in unique.values()):
            raise ValueError("all candidates must belong to this GapStore subject")
        now = self._now()
        created = refreshed = reopened = 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for candidate in unique.values():
                row = conn.execute(
                    "SELECT status FROM gaps WHERE subject_id=? AND gap_id=?",
                    (self.subject_id, candidate.gap_id),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """INSERT INTO gaps (
                            gap_id, subject_id, paradigm_id, source_id, target_id,
                            missing_types, original_relation, replacement_relations,
                            reason, confidence, status, supplemented_by, created_at,
                            updated_at, detected_at, version, detector_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', '[]', ?, ?, ?, 1, ?)""",
                        (
                            candidate.gap_id, self.subject_id, candidate.paradigm_id,
                            candidate.source_id, candidate.target_id,
                            self._json_list(candidate.missing_types),
                            candidate.original_relation,
                            self._json_list(candidate.replacement_relations),
                            candidate.reason, candidate.confidence,
                            now, now, now, candidate.detector_version,
                        ),
                    )
                    created += 1
                    continue
                previous = row["status"]
                new_status = "open" if previous == "obsolete" else previous
                conn.execute(
                    """UPDATE gaps SET paradigm_id=?, source_id=?, target_id=?,
                        missing_types=?, original_relation=?, replacement_relations=?,
                        reason=?, confidence=?, detected_at=?, detector_version=?,
                        status=?, updated_at=?, version=version+1
                        WHERE gap_id=? AND subject_id=?""",
                    (
                        candidate.paradigm_id, candidate.source_id, candidate.target_id,
                        self._json_list(candidate.missing_types),
                        candidate.original_relation,
                        self._json_list(candidate.replacement_relations),
                        candidate.reason, candidate.confidence, now,
                        candidate.detector_version, new_status, now,
                        candidate.gap_id, self.subject_id,
                    ),
                )
                refreshed += 1
                reopened += int(previous == "obsolete")
        return ReconcileResult(len(unique), created, refreshed, reopened, 0)

    def ignore(self, gap_id: str, *, acted_by: str, expected_version: int) -> dict[str, Any]:
        return self._transition(
            gap_id, from_status="open", to_status="ignored",
            acted_by=acted_by, expected_version=expected_version,
        )

    def reopen(self, gap_id: str, *, acted_by: str, expected_version: int) -> dict[str, Any]:
        return self._transition(
            gap_id, from_status="ignored", to_status="open",
            acted_by=acted_by, expected_version=expected_version,
        )

    def mark_supplemented(
        self,
        gap_id: str,
        *,
        supplemented_by: Sequence[str],
        acted_by: str,
        expected_version: int,
    ) -> dict[str, Any]:
        record = self.require(gap_id)
        if record["status"] == "supplemented":
            return record
        return self._transition(
            gap_id,
            from_status="open",
            to_status="supplemented",
            acted_by=acted_by,
            expected_version=expected_version,
            supplemented_by=supplemented_by,
        )

    def _transition(
        self,
        gap_id: str,
        *,
        from_status: str,
        to_status: str,
        acted_by: str,
        expected_version: int,
        supplemented_by: Optional[Sequence[str]] = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE gaps SET status=?, supplemented_by=COALESCE(?, supplemented_by),
                    acted_by=?, updated_at=?, version=version+1
                    WHERE subject_id=? AND gap_id=? AND status=? AND version=?""",
                (
                    to_status,
                    self._json_list(supplemented_by) if supplemented_by is not None else None,
                    acted_by,
                    now,
                    self.subject_id,
                    gap_id,
                    from_status,
                    int(expected_version),
                ),
            )
            if cursor.rowcount != 1:
                current = conn.execute(
                    "SELECT status, version FROM gaps WHERE subject_id=? AND gap_id=?",
                    (self.subject_id, gap_id),
                ).fetchone()
                if current is None:
                    raise GapNotFoundError(f"gap '{gap_id}' not found")
                raise GapConflictError(
                    f"gap state/version conflict: expected {from_status}@{expected_version}, "
                    f"current {current['status']}@{current['version']}"
                )
        return self.require(gap_id)


__all__ = [
    "GAP_STATUSES",
    "GapConflictError",
    "GapNotFoundError",
    "GapStore",
    "GapStoreError",
    "ReconcileResult",
]

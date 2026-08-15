"""Persistence for auditable, non-binding LLM Gap completion proposals."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional
import uuid

from core.gap_store import GapConflictError, GapNotFoundError


PROPOSAL_STATUSES = (
    "generating",
    "ready",
    "needs_external_evidence",
    "applying",
    "accepted",
    "rejected",
    "superseded",
    "failed",
    "stale",
)


class GapProposalStore:
    """Store proposal attempts beside their subject-scoped ``gaps`` table."""

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
                CREATE TABLE IF NOT EXISTS gap_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    gap_id TEXT NOT NULL,
                    gap_version INTEGER NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN (
                            'generating','ready','needs_external_evidence',
                            'applying','accepted','rejected','superseded','failed','stale'
                        )),
                    proposal_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    duplicate_candidates_json TEXT NOT NULL DEFAULT '[]',
                    source_recommendations_json TEXT NOT NULL DEFAULT '[]',
                    input_hash TEXT NOT NULL DEFAULT '',
                    prompt_version TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT '',
                    raw_response_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT NOT NULL,
                    reviewed_by TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    FOREIGN KEY(gap_id) REFERENCES gaps(gap_id)
                );
                CREATE INDEX IF NOT EXISTS idx_gap_proposals_gap
                    ON gap_proposals(subject_id, gap_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_gap_proposals_status
                    ON gap_proposals(subject_id, status, updated_at DESC);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _row(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        for column, fallback in (
            ("proposal_json", {}),
            ("evidence_json", []),
            ("duplicate_candidates_json", []),
            ("source_recommendations_json", []),
            ("raw_response_json", {}),
        ):
            try:
                item[column.removesuffix("_json")] = json.loads(item.pop(column) or "null")
            except (TypeError, json.JSONDecodeError):
                item[column.removesuffix("_json")] = fallback
        item["gap_version"] = int(item["gap_version"])
        return item

    def create(
        self,
        *,
        gap_id: str,
        gap_version: int,
        created_by: str,
        source_recommendations: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        now = self._now()
        proposal_id = "gap_proposal_" + uuid.uuid4().hex
        with self._connect() as conn:
            gap = conn.execute(
                "SELECT status, version FROM gaps WHERE subject_id=? AND gap_id=?",
                (self.subject_id, gap_id),
            ).fetchone()
            if gap is None:
                raise GapNotFoundError(f"gap '{gap_id}' not found")
            if gap["status"] != "open" or int(gap["version"]) != int(gap_version):
                raise GapConflictError(
                    f"gap state/version conflict: current {gap['status']}@{gap['version']}"
                )
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """UPDATE gap_proposals SET status='superseded', updated_at=?
                   WHERE subject_id=? AND gap_id=?
                     AND status IN ('generating','ready','needs_external_evidence','failed')""",
                (now, self.subject_id, gap_id),
            )
            conn.execute(
                """INSERT INTO gap_proposals (
                    proposal_id, subject_id, gap_id, gap_version, status,
                    source_recommendations_json, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'generating', ?, ?, ?, ?)""",
                (
                    proposal_id, self.subject_id, gap_id, int(gap_version),
                    self._dump(source_recommendations or []), created_by, now, now,
                ),
            )
        return self.require(proposal_id)

    def get(self, proposal_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gap_proposals WHERE subject_id=? AND proposal_id=?",
                (self.subject_id, proposal_id),
            ).fetchone()
        return self._row(row)

    def require(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get(proposal_id)
        if proposal is None:
            raise GapNotFoundError(f"gap proposal '{proposal_id}' not found")
        return proposal

    def latest(self, gap_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM gap_proposals
                   WHERE subject_id=? AND gap_id=?
                   ORDER BY created_at DESC, proposal_id DESC LIMIT 1""",
                (self.subject_id, gap_id),
            ).fetchone()
        return self._row(row)

    def list_for_gap(
        self, gap_id: str, *, limit: int = 30, offset: int = 0
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        with self._connect() as conn:
            total = int(conn.execute(
                "SELECT COUNT(*) FROM gap_proposals WHERE subject_id=? AND gap_id=?",
                (self.subject_id, gap_id),
            ).fetchone()[0])
            rows = conn.execute(
                """SELECT * FROM gap_proposals
                   WHERE subject_id=? AND gap_id=?
                   ORDER BY created_at DESC, proposal_id DESC LIMIT ? OFFSET ?""",
                (self.subject_id, gap_id, safe_limit, safe_offset),
            ).fetchall()
        return {"total": total, "items": [self._row(row) for row in rows]}

    def update_source_status(
        self,
        proposal_id: str,
        *,
        chunk_id: str,
        status: str,
        acted_by: str,
    ) -> dict[str, Any]:
        if status not in {"imported", "deactivated"}:
            raise ValueError(f"invalid external evidence status: {status}")
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT source_recommendations_json FROM gap_proposals
                   WHERE subject_id=? AND proposal_id=?""",
                (self.subject_id, proposal_id),
            ).fetchone()
            if row is None:
                raise GapNotFoundError(f"gap proposal '{proposal_id}' not found")
            try:
                sources = json.loads(row[0] or "[]")
            except (TypeError, json.JSONDecodeError):
                sources = []
            matched = False
            for item in sources:
                if not isinstance(item, dict):
                    continue
                chunk_ids = list(item.get("chunk_ids") or [])
                if item.get("chunk_id"):
                    chunk_ids.append(item["chunk_id"])
                if chunk_id not in chunk_ids:
                    continue
                item["status"] = status
                item["status_changed_by"] = acted_by
                item["status_changed_at"] = now
                matched = True
            if not matched:
                raise ValueError("external evidence chunk is not part of this proposal")
            conn.execute(
                """UPDATE gap_proposals SET source_recommendations_json=?, updated_at=?
                   WHERE subject_id=? AND proposal_id=?""",
                (self._dump(sources), now, self.subject_id, proposal_id),
            )
        return self.require(proposal_id)

    def update_source_record(
        self,
        proposal_id: str,
        *,
        result_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT source_recommendations_json FROM gap_proposals
                   WHERE subject_id=? AND proposal_id=?""",
                (self.subject_id, proposal_id),
            ).fetchone()
            if row is None:
                raise GapNotFoundError(f"gap proposal '{proposal_id}' not found")
            try:
                sources = json.loads(row[0] or "[]")
            except (TypeError, json.JSONDecodeError):
                sources = []
            matched = False
            for item in sources:
                if isinstance(item, dict) and str(item.get("result_id") or "") == result_id:
                    item.update(updates)
                    matched = True
            if not matched:
                raise ValueError("external search result is not part of this proposal")
            conn.execute(
                """UPDATE gap_proposals SET source_recommendations_json=?, updated_at=?
                   WHERE subject_id=? AND proposal_id=?""",
                (self._dump(sources), now, self.subject_id, proposal_id),
            )
        return self.require(proposal_id)

    def save_result(
        self,
        proposal_id: str,
        *,
        status: str,
        proposal: dict[str, Any],
        evidence: list[dict[str, Any]],
        duplicate_candidates: list[dict[str, Any]],
        source_recommendations: list[dict[str, Any]],
        input_hash: str,
        prompt_version: str,
        model: str,
        provider: str,
        raw_response: Any,
    ) -> dict[str, Any]:
        if status not in {"ready", "needs_external_evidence"}:
            raise ValueError(f"invalid proposal result status: {status}")
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE gap_proposals SET status=?, proposal_json=?, evidence_json=?,
                    duplicate_candidates_json=?, source_recommendations_json=?,
                    input_hash=?, prompt_version=?, model=?, provider=?, raw_response_json=?,
                    error=NULL, updated_at=?
                   WHERE subject_id=? AND proposal_id=? AND status='generating'""",
                (
                    status, self._dump(proposal), self._dump(evidence),
                    self._dump(duplicate_candidates), self._dump(source_recommendations),
                    input_hash, prompt_version, model, provider,
                    self._dump(raw_response), now, self.subject_id, proposal_id,
                ),
            )
            if cursor.rowcount != 1:
                current = self.require(proposal_id)
                if current["status"] == "superseded":
                    return current
                raise GapConflictError(
                    f"proposal state conflict: current {current['status']}"
                )
        return self.require(proposal_id)

    def save_source_recommendations(
        self,
        proposal_id: str,
        recommendations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Attach provider results without changing the proposal decision.

        Search candidates remain non-binding audit data on the proposal.  Only a
        later, explicit import can turn selected abstracts into knowledge Chunks.
        Previously imported records remain attached so another search cannot make
        successfully materialised evidence appear to have disappeared.
        """
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT source_recommendations_json FROM gap_proposals
                   WHERE subject_id=? AND proposal_id=?
                     AND status='needs_external_evidence'""",
                (self.subject_id, proposal_id),
            ).fetchone()
            if row is None:
                current = self.require(proposal_id)
                raise GapConflictError(
                    "external search requires a needs_external_evidence proposal, "
                    f"current {current['status']}"
                )
            try:
                existing = json.loads(row[0] or "[]")
            except (TypeError, json.JSONDecodeError):
                existing = []
            imported = [
                item for item in existing
                if isinstance(item, dict) and item.get("status") in {"imported", "deactivated"}
            ]
            imported_ids = {
                str(item.get("result_id")) for item in imported if item.get("result_id")
            }
            merged = imported + [
                item for item in recommendations
                if not item.get("result_id") or str(item.get("result_id")) not in imported_ids
            ]
            cursor = conn.execute(
                """UPDATE gap_proposals SET source_recommendations_json=?, updated_at=?
                   WHERE subject_id=? AND proposal_id=?
                     AND status='needs_external_evidence'""",
                (
                    self._dump(merged), now,
                    self.subject_id, proposal_id,
                ),
            )
            if cursor.rowcount != 1:
                current = self.require(proposal_id)
                raise GapConflictError(
                    "external search requires a needs_external_evidence proposal, "
                    f"current {current['status']}"
                )
        return self.require(proposal_id)

    def mark_failed(self, proposal_id: str, error: str) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """UPDATE gap_proposals SET status='failed', error=?, updated_at=?
                   WHERE subject_id=? AND proposal_id=? AND status='generating'""",
                (str(error)[:2000], now, self.subject_id, proposal_id),
            )
        return self.require(proposal_id)

    def mark_stale(self, proposal_id: str) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """UPDATE gap_proposals SET status='stale', updated_at=?
                   WHERE subject_id=? AND proposal_id=?
                     AND status IN ('generating','ready','needs_external_evidence')""",
                (now, self.subject_id, proposal_id),
            )
        return self.require(proposal_id)

    def review(self, proposal_id: str, *, decision: str, reviewed_by: str) -> dict[str, Any]:
        target = {"accept": "accepted", "reject": "rejected"}.get(decision)
        if target is None:
            raise ValueError(f"invalid proposal review decision: {decision}")
        allowed = ("ready",) if target == "accepted" else (
            "ready", "needs_external_evidence", "failed"
        )
        now = self._now()
        placeholders = ",".join("?" for _ in allowed)
        with self._connect() as conn:
            cursor = conn.execute(
                f"""UPDATE gap_proposals SET status=?, reviewed_by=?, reviewed_at=?, updated_at=?
                    WHERE subject_id=? AND proposal_id=? AND status IN ({placeholders})""",
                (
                    target, reviewed_by, now, now, self.subject_id, proposal_id,
                    *allowed,
                ),
            )
            if cursor.rowcount != 1:
                current = self.require(proposal_id)
                if current["status"] == target:
                    return current
                raise GapConflictError(
                    f"proposal state conflict: cannot {decision} {current['status']} proposal"
                )
        return self.require(proposal_id)

    def claim_for_accept(self, proposal_id: str, *, reviewed_by: str) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE gap_proposals SET status='applying', reviewed_by=?, updated_at=?
                   WHERE subject_id=? AND proposal_id=? AND status='ready'""",
                (reviewed_by, now, self.subject_id, proposal_id),
            )
            if cursor.rowcount != 1:
                current = self.require(proposal_id)
                if current["status"] in {"applying", "accepted"}:
                    return current
                raise GapConflictError(
                    f"proposal state conflict: cannot accept {current['status']} proposal"
                )
        return self.require(proposal_id)

    def finish_accept(self, proposal_id: str, *, reviewed_by: str) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE gap_proposals SET status='accepted', reviewed_by=?,
                    reviewed_at=?, updated_at=?, error=NULL
                   WHERE subject_id=? AND proposal_id=? AND status='applying'""",
                (reviewed_by, now, now, self.subject_id, proposal_id),
            )
            if cursor.rowcount != 1:
                current = self.require(proposal_id)
                if current["status"] == "accepted":
                    return current
                raise GapConflictError(
                    f"proposal state conflict: cannot finish {current['status']} proposal"
                )
        return self.require(proposal_id)

    def release_accept(self, proposal_id: str, error: str) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """UPDATE gap_proposals SET status='ready', error=?, updated_at=?
                   WHERE subject_id=? AND proposal_id=? AND status='applying'""",
                (str(error)[:2000], now, self.subject_id, proposal_id),
            )
        return self.require(proposal_id)


__all__ = ["GapProposalStore", "PROPOSAL_STATUSES"]

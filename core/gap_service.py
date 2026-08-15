"""Application service coordinating GapStore and GraphStore safely."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from core.gap_store import GapConflictError, GapStore


class GapSupplementError(RuntimeError):
    pass


class GapSupplementService:
    def __init__(self, gap_store: GapStore, graph_store: Any):
        self.gap_store = gap_store
        self.graph_store = graph_store

    @staticmethod
    def _concept_id(gap_id: str, index: int, name: str, concept_type: str) -> str:
        raw = f"{gap_id}|{index}|{name.strip()}|{concept_type.strip()}"
        return "concept_gap_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def supplement(
        self,
        *,
        gap_id: str,
        concepts: Sequence[Mapping[str, Any]],
        acted_by: str,
        expected_version: int,
    ) -> dict[str, Any]:
        gap = self.gap_store.require(gap_id)
        if gap["status"] == "supplemented":
            return gap
        if gap["status"] != "open" or gap["version"] != int(expected_version):
            raise GapConflictError(
                f"gap state/version conflict: current {gap['status']}@{gap['version']}"
            )
        missing_types = gap["missing_types"]
        if len(concepts) != len(missing_types):
            raise ValueError(
                f"supplement requires {len(missing_types)} concepts in missing_types order"
            )

        resolved_ids: list[str] = []
        created_concepts: list[str] = []
        created_edges: list[tuple[str, str, str]] = []
        original_removed = False
        try:
            for index, (spec, expected_type) in enumerate(zip(concepts, missing_types)):
                canonical_id = str(spec.get("canonical_id") or "").strip()
                if canonical_id:
                    concept = self.graph_store.get_canonical_concept(canonical_id)
                    if concept is None:
                        raise ValueError(f"canonical concept '{canonical_id}' not found")
                    if concept.get("concept_type") != expected_type:
                        raise ValueError(
                            f"concept '{canonical_id}' type must be '{expected_type}'"
                        )
                else:
                    name = str(spec.get("name") or "").strip()
                    concept_type = str(spec.get("concept_type") or "").strip()
                    description = str(spec.get("description") or "").strip()
                    if not name or not description or concept_type != expected_type:
                        raise ValueError(
                            f"new concept at index {index} requires name, description, "
                            f"and concept_type '{expected_type}'"
                        )
                    canonical_id = self._concept_id(gap_id, index, name, concept_type)
                    concept, created = self.graph_store.ensure_gap_concept(
                        canonical_id=canonical_id,
                        name=name,
                        concept_type=concept_type,
                        description=description,
                        evidence=str(spec.get("evidence") or "").strip(),
                        aliases=list(spec.get("aliases") or []),
                        source_chunks=list(spec.get("source_chunks") or []),
                    )
                    if created:
                        created_concepts.append(canonical_id)
                resolved_ids.append(canonical_id)

            path = (
                ([gap["source_id"]] if gap["source_id"] else [])
                + resolved_ids
                + ([gap["target_id"]] if gap["target_id"] else [])
            )
            relations = gap["replacement_relations"]
            if len(relations) != len(path) - 1:
                raise GapSupplementError("replacement relation count does not match gap path")
            for source_id, target_id, relation in zip(path, path[1:], relations):
                if self.graph_store.ensure_canonical_edge(
                    source_id, target_id, relation, confidence=1.0
                ):
                    created_edges.append((source_id, target_id, relation))

            if gap["source_id"] and gap["target_id"] and gap["original_relation"]:
                original_removed = self.graph_store.remove_canonical_edge(
                    gap["source_id"], gap["target_id"], gap["original_relation"]
                )

            return self.gap_store.mark_supplemented(
                gap_id,
                supplemented_by=resolved_ids,
                acted_by=acted_by,
                expected_version=expected_version,
            )
        except Exception:
            # Compensate only writes made by this call. Existing graph data is preserved.
            for source_id, target_id, relation in reversed(created_edges):
                try:
                    self.graph_store.remove_canonical_edge(source_id, target_id, relation)
                except Exception:
                    pass
            if original_removed:
                try:
                    self.graph_store.ensure_canonical_edge(
                        gap["source_id"], gap["target_id"], gap["original_relation"],
                        confidence=float(gap.get("confidence", 1.0)),
                    )
                except Exception:
                    pass
            for canonical_id in reversed(created_concepts):
                try:
                    self.graph_store.delete_gap_concept_if_orphan(canonical_id)
                except Exception:
                    pass
            raise


__all__ = ["GapSupplementError", "GapSupplementService"]

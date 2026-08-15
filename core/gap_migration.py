"""Safe migration of LA-046 virtual concepts into Gap Flow records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.gap_detector import GapCandidate, GapDetector


@dataclass(frozen=True)
class LegacyGapMigrationReport:
    found: int
    migratable: int
    naturally_filled: int
    skipped: int
    records_created: int
    records_refreshed: int
    deleted: int
    dry_run: bool
    skipped_nodes: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["skipped_nodes"] = list(self.skipped_nodes)
        return result


class LegacyGapMigrator:
    """Convert only unambiguous one-layer legacy placeholders."""

    def __init__(self, graph_store: Any, gap_store: Any):
        self.graph_store = graph_store
        self.gap_store = gap_store

    @staticmethod
    def _has_natural_path(
        source_id: str,
        target_id: str,
        missing_type: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> bool:
        typed_ids = {
            node["id"] for node in nodes
            if node.get("type") == missing_type
        }
        from_source = {
            edge["target"] for edge in edges if edge["source"] == source_id
        }
        to_target = {
            edge["source"] for edge in edges if edge["target"] == target_id
        }
        return bool(typed_ids & from_source & to_target)

    @staticmethod
    def _original_relation(
        source_type: str,
        target_type: str,
        config: Mapping[str, Any],
    ) -> str:
        relation_map = config.get("relation_map", {})
        choices = [
            relation for relation, targets in relation_map.get(source_type, {}).items()
            if target_type in targets
        ]
        return sorted(choices)[0] if choices else ""

    def migrate(
        self,
        *,
        subject_id: str,
        paradigm_id: str,
        paradigm_config: Mapping[str, Any],
        detector_version: str,
        dry_run: bool = True,
    ) -> LegacyGapMigrationReport:
        legacy = self.graph_store.inspect_legacy_virtual_concepts()
        real_nodes = self.graph_store.get_canonical_concepts(limit=None)
        real_edges = self.graph_store.get_concept_links(limit=None)
        node_types = {node["id"]: node.get("type", "") for node in real_nodes}
        candidates: list[GapCandidate] = []
        deletable: list[str] = []
        naturally_filled = 0
        skipped: list[dict[str, str]] = []

        for node in legacy:
            incoming = node.get("incoming", [])
            outgoing = node.get("outgoing", [])
            if len(incoming) != 1 or len(outgoing) != 1:
                skipped.append({
                    "canonical_id": node["id"],
                    "reason": "expected exactly one real incoming and outgoing edge",
                })
                continue
            source_id = incoming[0]["source"]
            target_id = outgoing[0]["target"]
            missing_type = str(node.get("type") or "").strip()
            if not missing_type or source_id == target_id:
                skipped.append({
                    "canonical_id": node["id"],
                    "reason": "missing concept type or invalid endpoints",
                })
                continue
            deletable.append(node["id"])
            if self._has_natural_path(
                source_id, target_id, missing_type, real_nodes, real_edges
            ):
                naturally_filled += 1
                continue
            source_type = node_types.get(source_id, "")
            target_type = node_types.get(target_id, "")
            replacement = (incoming[0]["type"], outgoing[0]["type"])
            gap_id = GapDetector.stable_gap_id(
                subject_id=subject_id,
                paradigm_id=paradigm_id,
                source_id=source_id,
                target_id=target_id,
                missing_types=(missing_type,),
                detector_version=detector_version,
            )
            candidates.append(GapCandidate(
                gap_id=gap_id,
                subject_id=subject_id,
                paradigm_id=paradigm_id,
                source_id=source_id,
                target_id=target_id,
                missing_types=(missing_type,),
                original_relation=self._original_relation(
                    source_type, target_type, paradigm_config
                ),
                replacement_relations=replacement,
                reason=f"migrated from legacy virtual concept {node['id']}",
                confidence=min(
                    float(incoming[0].get("confidence") or 0.5),
                    float(outgoing[0].get("confidence") or 0.5),
                ),
                detector_version=detector_version,
            ))

        created = refreshed = deleted = 0
        if not dry_run:
            imported = self.gap_store.import_candidates(candidates)
            created = imported.created
            refreshed = imported.refreshed
            # Records are durable before graph cleanup. A retry is idempotent.
            deleted = self.graph_store.delete_legacy_virtual_concepts(deletable)

        return LegacyGapMigrationReport(
            found=len(legacy), migratable=len(candidates),
            naturally_filled=naturally_filled, skipped=len(skipped),
            records_created=created, records_refreshed=refreshed,
            deleted=deleted, dry_run=dry_run,
            skipped_nodes=tuple(skipped),
        )


__all__ = ["LegacyGapMigrationReport", "LegacyGapMigrator"]

"""Deterministic structural-gap detection for knowledge graphs.

This module deliberately has no database, HTTP, or LLM dependencies.  It is
the M0 boundary of Gap Flow: callers provide real graph nodes/edges and a
paradigm configuration, and receive stable candidates plus diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


DEFAULT_DETECTOR_VERSION = "gap-detector-v1"


@dataclass(frozen=True)
class GapCandidate:
    """A persistable structural gap candidate produced by :class:`GapDetector`."""

    gap_id: str
    subject_id: str
    paradigm_id: str
    source_id: Optional[str]
    target_id: Optional[str]
    missing_types: Tuple[str, ...]
    original_relation: str
    replacement_relations: Tuple[str, ...]
    reason: str
    confidence: float
    detector_version: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for the future GapStore/API."""

        return {
            "gap_id": self.gap_id,
            "subject_id": self.subject_id,
            "paradigm_id": self.paradigm_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "missing_types": list(self.missing_types),
            "original_relation": self.original_relation,
            "replacement_relations": list(self.replacement_relations),
            "reason": self.reason,
            "confidence": self.confidence,
            "detector_version": self.detector_version,
        }


@dataclass(frozen=True)
class GapDiagnostic:
    """A non-actionable detection observation, such as an illegal direction."""

    code: str
    message: str
    source_id: Optional[str] = None
    target_id: Optional[str] = None


@dataclass(frozen=True)
class GapDetectionResult:
    """Candidates and non-fatal diagnostics from one deterministic scan."""

    candidates: Tuple[GapCandidate, ...] = field(default_factory=tuple)
    diagnostics: Tuple[GapDiagnostic, ...] = field(default_factory=tuple)


class GapDetector:
    """Detect structural gaps using a frozen paradigm configuration.

    Node inputs may be either ``{canonical_id: concept_type}`` or an iterable
    of dictionaries/objects containing ``canonical_id`` (or ``id``) and
    ``concept_type`` (or ``type``).  Edge inputs may be dictionaries or objects
    with ``source_id``/``target_id`` or the legacy
    ``parent_id``/``child_id`` names.
    """

    def __init__(self, detector_version: str = DEFAULT_DETECTOR_VERSION):
        version = str(detector_version).strip()
        if not version:
            raise ValueError("detector_version must not be empty")
        self.detector_version = version

    def detect(
        self,
        *,
        subject_id: str,
        paradigm_id: str,
        nodes: Mapping[str, str] | Iterable[Any],
        edges: Iterable[Any],
        paradigm_config: Mapping[str, Any],
        detect_root_gaps: bool = True,
    ) -> GapDetectionResult:
        """Detect gaps without mutating the supplied graph.

        For non-cyclic paradigms, root gaps are detected only when legal root
        types are explicit (``root_types``) or inferable from empty entries in
        ``parent_rules``.  Cyclic paradigms do not infer roots because any type
        may legitimately start a displayed subgraph.
        """

        subject = self._required_text(subject_id, "subject_id")
        paradigm = self._required_text(paradigm_id, "paradigm_id")
        if not isinstance(paradigm_config, Mapping):
            raise TypeError("paradigm_config must be a mapping")

        node_types = self._normalise_nodes(nodes)
        normalised_edges = self._normalise_edges(edges)
        config = self._validate_config(paradigm_config)
        candidates: dict[str, GapCandidate] = {}
        diagnostics: list[GapDiagnostic] = []

        for source_id, target_id, relation in normalised_edges:
            source_type = node_types.get(source_id)
            target_type = node_types.get(target_id)
            if source_type is None or target_type is None:
                missing = source_id if source_type is None else target_id
                diagnostics.append(
                    GapDiagnostic(
                        code="unknown_endpoint",
                        message=f"edge endpoint '{missing}' is not present in nodes",
                        source_id=source_id,
                        target_id=target_id,
                    )
                )
                continue
            if source_id == target_id:
                diagnostics.append(
                    GapDiagnostic(
                        code="self_loop",
                        message="self-loop edges cannot produce a structural gap",
                        source_id=source_id,
                        target_id=target_id,
                    )
                )
                continue

            if config["cyclic"]:
                outcome = self._detect_cyclic_edge(source_type, target_type, config)
            else:
                outcome = self._detect_linear_edge(source_type, target_type, config)

            if outcome["diagnostic"]:
                diagnostics.append(
                    GapDiagnostic(
                        code=outcome["diagnostic"],
                        message=outcome["message"],
                        source_id=source_id,
                        target_id=target_id,
                    )
                )
                continue

            missing_types = outcome["missing_types"]
            if not missing_types:
                continue
            path_types = (source_type, *missing_types, target_type)
            replacement_relations = self._relations_for_path(path_types, config)
            if replacement_relations is None:
                diagnostics.append(
                    GapDiagnostic(
                        code="missing_replacement_relation",
                        message=f"paradigm has no relation mapping for path {path_types}",
                        source_id=source_id,
                        target_id=target_id,
                    )
                )
                continue

            candidate = self._candidate(
                subject_id=subject,
                paradigm_id=paradigm,
                source_id=source_id,
                target_id=target_id,
                missing_types=missing_types,
                original_relation=relation,
                replacement_relations=replacement_relations,
                reason=outcome["message"],
            )
            candidates[candidate.gap_id] = candidate

        if detect_root_gaps and not config["cyclic"]:
            self._detect_root_gaps(
                subject,
                paradigm,
                node_types,
                normalised_edges,
                config,
                candidates,
                diagnostics,
            )

        return GapDetectionResult(
            candidates=tuple(sorted(candidates.values(), key=lambda item: item.gap_id)),
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def stable_gap_id(
        *,
        subject_id: str,
        paradigm_id: str,
        source_id: Optional[str],
        target_id: Optional[str],
        missing_types: Sequence[str],
        detector_version: str = DEFAULT_DETECTOR_VERSION,
    ) -> str:
        """Build the stable ID specified by the Gap Flow design baseline."""

        payload = {
            "subject_id": str(subject_id).strip(),
            "paradigm_id": str(paradigm_id).strip(),
            "source_id": str(source_id).strip() if source_id is not None else "",
            "target_id": str(target_id).strip() if target_id is not None else "",
            "missing_types": [str(value).strip() for value in missing_types],
            "detector_version": str(detector_version).strip(),
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return "gap_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _candidate(
        self,
        *,
        subject_id: str,
        paradigm_id: str,
        source_id: Optional[str],
        target_id: Optional[str],
        missing_types: Sequence[str],
        original_relation: str,
        replacement_relations: Sequence[str],
        reason: str,
    ) -> GapCandidate:
        missing = tuple(missing_types)
        return GapCandidate(
            gap_id=self.stable_gap_id(
                subject_id=subject_id,
                paradigm_id=paradigm_id,
                source_id=source_id,
                target_id=target_id,
                missing_types=missing,
                detector_version=self.detector_version,
            ),
            subject_id=subject_id,
            paradigm_id=paradigm_id,
            source_id=source_id,
            target_id=target_id,
            missing_types=missing,
            original_relation=original_relation,
            replacement_relations=tuple(replacement_relations),
            reason=reason,
            confidence=1.0,
            detector_version=self.detector_version,
        )

    def _detect_root_gaps(
        self,
        subject_id: str,
        paradigm_id: str,
        node_types: Mapping[str, str],
        edges: Sequence[Tuple[str, str, str]],
        config: Mapping[str, Any],
        candidates: dict[str, GapCandidate],
        diagnostics: list[GapDiagnostic],
    ) -> None:
        root_types = config["root_types"]
        chain = config["ideal_chain"]
        if not root_types:
            diagnostics.append(
                GapDiagnostic(
                    code="root_detection_unconfigured",
                    message="root gap detection skipped because no legal root type is configured",
                )
            )
            return

        incoming = {target_id for _, target_id, _ in edges}
        root_indices = [chain.index(value) for value in root_types if value in chain]
        if not root_indices:
            return
        first_root_index = min(root_indices)

        for node_id, node_type in node_types.items():
            if node_id in incoming or node_type in root_types:
                continue
            if node_type not in chain:
                diagnostics.append(
                    GapDiagnostic(
                        code="type_not_in_chain",
                        message=f"root node type '{node_type}' is absent from ideal_chain",
                        target_id=node_id,
                    )
                )
                continue
            node_index = chain.index(node_type)
            if node_index <= first_root_index:
                continue
            missing_types = tuple(chain[first_root_index:node_index])
            path_types = (*missing_types, node_type)
            relations = self._relations_for_path(path_types, config)
            if relations is None:
                diagnostics.append(
                    GapDiagnostic(
                        code="missing_replacement_relation",
                        message=f"paradigm has no relation mapping for root path {path_types}",
                        target_id=node_id,
                    )
                )
                continue
            candidate = self._candidate(
                subject_id=subject_id,
                paradigm_id=paradigm_id,
                source_id=None,
                target_id=node_id,
                missing_types=missing_types,
                original_relation="",
                replacement_relations=relations,
                reason=f"root node of type '{node_type}' skips {missing_types}",
            )
            candidates[candidate.gap_id] = candidate

    @staticmethod
    def _detect_cyclic_edge(
        source_type: str, target_type: str, config: Mapping[str, Any]
    ) -> dict[str, Any]:
        pattern = config["cycle_pattern"]
        if source_type not in pattern or target_type not in pattern:
            return {
                "missing_types": (),
                "diagnostic": "type_not_in_cycle",
                "message": f"types '{source_type}' and '{target_type}' must be in cycle_pattern",
            }
        source_index = pattern.index(source_type)
        expected = pattern[(source_index + 1) % len(pattern)]
        if target_type == expected:
            return {"missing_types": (), "diagnostic": "", "message": "adjacent cycle types"}
        if target_type == source_type:
            return {
                "missing_types": (expected,),
                "diagnostic": "",
                "message": f"same-type cycle edge skips alternating type '{expected}'",
            }
        return {
            "missing_types": (),
            "diagnostic": "illegal_cycle_direction",
            "message": f"'{source_type}' cannot be followed by '{target_type}' in cycle_pattern",
        }

    @staticmethod
    def _detect_linear_edge(
        source_type: str, target_type: str, config: Mapping[str, Any]
    ) -> dict[str, Any]:
        chain = config["ideal_chain"]
        if source_type not in chain or target_type not in chain:
            return {
                "missing_types": (),
                "diagnostic": "type_not_in_chain",
                "message": f"types '{source_type}' and '{target_type}' must be in ideal_chain",
            }
        source_index = chain.index(source_type)
        target_index = chain.index(target_type)
        if target_index <= source_index:
            return {
                "missing_types": (),
                "diagnostic": "illegal_direction",
                "message": f"edge direction {source_type} -> {target_type} contradicts ideal_chain",
            }
        missing = tuple(chain[source_index + 1 : target_index])
        return {
            "missing_types": missing,
            "diagnostic": "",
            "message": (
                f"edge {source_type} -> {target_type} skips {missing}"
                if missing
                else "adjacent chain types"
            ),
        }

    @staticmethod
    def _relations_for_path(
        path_types: Sequence[str], config: Mapping[str, Any]
    ) -> Optional[Tuple[str, ...]]:
        relation_map = config["relation_map"]
        relations: list[str] = []
        for source_type, target_type in zip(path_types, path_types[1:]):
            matches = [
                relation
                for relation, targets in relation_map.get(source_type, {}).items()
                if target_type in targets
            ]
            if not matches:
                return None
            relations.append(sorted(matches)[0])
        return tuple(relations)

    @classmethod
    def _validate_config(cls, config: Mapping[str, Any]) -> dict[str, Any]:
        cyclic = bool(config.get("cyclic", False))
        ideal_chain = cls._text_sequence(config.get("ideal_chain", ()), "ideal_chain")
        cycle_pattern = cls._text_sequence(config.get("cycle_pattern", ()), "cycle_pattern")
        if cyclic and len(cycle_pattern) < 2:
            raise ValueError("cyclic paradigms require at least two cycle_pattern types")
        if not cyclic and len(ideal_chain) < 2:
            raise ValueError("non-cyclic paradigms require at least two ideal_chain types")
        if not cyclic and len(set(ideal_chain)) != len(ideal_chain):
            raise ValueError("non-cyclic ideal_chain must not contain duplicate types")

        relation_map = config.get("relation_map", {})
        if not isinstance(relation_map, Mapping):
            raise TypeError("relation_map must be a mapping")

        if "root_types" in config:
            root_types = cls._text_sequence(config.get("root_types", ()), "root_types")
        elif not cyclic:
            parent_rules = config.get("parent_rules", {})
            root_types = tuple(
                str(concept_type).strip()
                for concept_type, parents in parent_rules.items()
                if isinstance(parents, Sequence)
                and not isinstance(parents, (str, bytes))
                and len(parents) == 0
            ) if isinstance(parent_rules, Mapping) else ()
        else:
            root_types = ()

        return {
            "cyclic": cyclic,
            "ideal_chain": ideal_chain,
            "cycle_pattern": cycle_pattern,
            "relation_map": relation_map,
            "root_types": root_types,
        }

    @classmethod
    def _normalise_nodes(
        cls, nodes: Mapping[str, str] | Iterable[Any]
    ) -> dict[str, str]:
        if isinstance(nodes, Mapping):
            pairs = nodes.items()
        else:
            pairs = (
                (
                    cls._value(node, "canonical_id", "id"),
                    cls._value(node, "concept_type", "type"),
                )
                for node in nodes
            )
        result: dict[str, str] = {}
        for node_id, concept_type in pairs:
            normal_id = cls._required_text(node_id, "node canonical_id")
            normal_type = cls._required_text(concept_type, f"concept_type for '{normal_id}'")
            if normal_id in result and result[normal_id] != normal_type:
                raise ValueError(f"node '{normal_id}' has conflicting concept types")
            result[normal_id] = normal_type
        return result

    @classmethod
    def _normalise_edges(cls, edges: Iterable[Any]) -> Tuple[Tuple[str, str, str], ...]:
        result = []
        for edge in edges:
            source_id = cls._required_text(
                cls._value(edge, "source_id", "parent_id", "source"), "edge source_id"
            )
            target_id = cls._required_text(
                cls._value(edge, "target_id", "child_id", "target"), "edge target_id"
            )
            relation = cls._value(
                edge, "original_relation", "relation_type", "relation", "type"
            )
            result.append((source_id, target_id, str(relation or "").strip()))
        return tuple(result)

    @staticmethod
    def _value(value: Any, *names: str) -> Any:
        for name in names:
            if isinstance(value, Mapping) and name in value:
                return value[name]
            if hasattr(value, name):
                return getattr(value, name)
        return None

    @staticmethod
    def _required_text(value: Any, label: str) -> str:
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError(f"{label} must not be empty")
        return text

    @classmethod
    def _text_sequence(cls, value: Any, label: str) -> Tuple[str, ...]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise TypeError(f"{label} must be a sequence")
        return tuple(cls._required_text(item, label) for item in value)


__all__ = [
    "DEFAULT_DETECTOR_VERSION",
    "GapCandidate",
    "GapDetectionResult",
    "GapDetector",
    "GapDiagnostic",
]

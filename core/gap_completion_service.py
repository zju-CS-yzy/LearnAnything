"""Context assembly, duplicate screening and reviewed application for Gap M4A."""

from __future__ import annotations

from difflib import SequenceMatcher
import json
import re
from typing import Any, Callable, Optional, Sequence

from core.gap_completion_advisor import GapCompletionAdvisor
from core.gap_proposal_store import GapProposalStore
from core.gap_service import GapSupplementService
from core.gap_store import GapConflictError, GapStore


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return [part.strip() for part in str(value).split(",") if part.strip()]


def _key(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


class GapCompletionContextBuilder:
    """Assemble a bounded, evidence-whitelisted context from one subject."""

    def __init__(
        self,
        graph_store: Any,
        *,
        source_loader: Optional[Callable[[list[str]], list[dict[str, Any]]]] = None,
        search_loader: Optional[Callable[[str, int], list[dict[str, Any]]]] = None,
    ):
        self.graph_store = graph_store
        self.source_loader = source_loader
        self.search_loader = search_loader

    def build(
        self,
        gap: dict[str, Any],
        paradigm_config: dict[str, Any],
        extra_source_ids: Optional[Sequence[str]] = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        nodes = self.graph_store.get_canonical_concepts(limit=None)
        edges = self.graph_store.get_concept_links(limit=None)
        by_id = {str(item.get("id")): item for item in nodes if item.get("id")}
        endpoint_ids = [
            str(item) for item in (gap.get("source_id"), gap.get("target_id")) if item
        ]
        neighbor_ids: list[str] = []
        neighbor_edges: list[dict[str, Any]] = []
        for edge in edges:
            source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
            if source in endpoint_ids or target in endpoint_ids:
                neighbor_edges.append({
                    "source": source,
                    "target": target,
                    "relation": str(edge.get("type") or ""),
                })
                other = target if source in endpoint_ids else source
                if other and other not in endpoint_ids and other not in neighbor_ids:
                    neighbor_ids.append(other)
            if len(neighbor_edges) >= 16:
                break

        profile_ids = endpoint_ids + neighbor_ids[:8]
        source_ids: list[str] = list(dict.fromkeys(
            str(item).strip() for item in (extra_source_ids or []) if str(item).strip()
        ))[:10]
        for concept_id in profile_ids:
            for chunk_id in _json_list((by_id.get(concept_id) or {}).get("source_chunks")):
                text = str(chunk_id).strip()
                if text and text not in source_ids and not text.startswith("__virtual"):
                    source_ids.append(text)
                if len(source_ids) >= 16:
                    break

        chunks: list[dict[str, Any]] = []
        if self.source_loader and source_ids:
            chunks.extend(self.source_loader(source_ids[:16]) or [])

        endpoint_names = [str((by_id.get(item) or {}).get("name") or "") for item in endpoint_ids]
        type_labels = paradigm_config.get("types") or {}
        query = " ".join(
            [name for name in endpoint_names if name]
            + [str(type_labels.get(item) or item) for item in gap.get("missing_types") or []]
        ).strip()
        if self.search_loader and query:
            try:
                chunks.extend(self.search_loader(query, 6) or [])
            except Exception as exc:
                print(f"[GapCompletion] local semantic retrieval degraded: {exc}")

        compact_chunks: list[dict[str, Any]] = []
        seen_chunks: set[str] = set()
        for item in chunks:
            chunk_id = str(item.get("id") or item.get("chunk_id") or "").strip()
            if not chunk_id or chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)
            compact_chunks.append({
                "chunk_id": chunk_id,
                "text": str(item.get("text") or "")[:1800],
                "metadata": item.get("metadata") or {},
            })
            if len(compact_chunks) >= 14:
                break

        def profile(concept_id: Optional[str]) -> Optional[dict[str, Any]]:
            if not concept_id:
                return None
            item = by_id.get(str(concept_id)) or {}
            return {
                "canonical_id": str(concept_id),
                "name": str(item.get("name") or ""),
                "concept_type": str(item.get("type") or item.get("concept_type") or ""),
                "description": str(item.get("description") or "")[:2000],
                "aliases": _json_list(item.get("aliases"))[:12],
                "source_chunk_ids": _json_list(item.get("source_chunks"))[:12],
            }

        context = {
            "subject_id": gap.get("subject_id"),
            "paradigm_id": gap.get("paradigm_id"),
            "paradigm": {
                "name": paradigm_config.get("name"),
                "description": paradigm_config.get("description"),
                "types": paradigm_config.get("types") or {},
                "ideal_chain": paradigm_config.get("ideal_chain") or [],
                "cycle_pattern": paradigm_config.get("cycle_pattern") or [],
                "relation_map": paradigm_config.get("relation_map") or {},
                "prompt_addon": str(paradigm_config.get("prompt_addon") or "")[:5000],
            },
            "gap": {
                "gap_id": gap.get("gap_id"),
                "reason": gap.get("reason"),
                "confidence": gap.get("confidence"),
                "original_relation": gap.get("original_relation"),
                "replacement_relations": gap.get("replacement_relations") or [],
            },
            "missing_types": gap.get("missing_types") or [],
            "source_concept": profile(gap.get("source_id")),
            "target_concept": profile(gap.get("target_id")),
            "neighbor_concepts": [profile(item) for item in neighbor_ids[:8]],
            "neighbor_edges": neighbor_edges,
            "chunks": compact_chunks,
        }
        return context, nodes


class GapCompletionService:
    def __init__(
        self,
        *,
        gap_store: GapStore,
        proposal_store: GapProposalStore,
        graph_store: Any,
        advisor: GapCompletionAdvisor,
        context_builder: GapCompletionContextBuilder,
    ):
        self.gap_store = gap_store
        self.proposal_store = proposal_store
        self.graph_store = graph_store
        self.advisor = advisor
        self.context_builder = context_builder

    @staticmethod
    def _screen_duplicates(
        proposal: dict[str, Any], all_nodes: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        duplicate_candidates: list[dict[str, Any]] = []
        for concept in proposal.get("concepts") or []:
            expected_type = concept.get("concept_type")
            proposed_terms = {_key(concept.get("name"))}
            proposed_terms.update(_key(item) for item in concept.get("aliases") or [])
            proposed_terms.discard("")
            fuzzy: list[tuple[float, dict[str, Any]]] = []
            exact: Optional[dict[str, Any]] = None
            for node in all_nodes:
                node_type = node.get("type") or node.get("concept_type")
                if node_type != expected_type or node.get("is_virtual"):
                    continue
                node_terms = {_key(node.get("name"))}
                node_terms.update(_key(item) for item in _json_list(node.get("aliases")))
                node_terms.discard("")
                if proposed_terms & node_terms:
                    exact = node
                    break
                score = max(
                    (SequenceMatcher(None, left, right).ratio()
                     for left in proposed_terms for right in node_terms),
                    default=0.0,
                )
                if score >= 0.78:
                    fuzzy.append((score, node))
            if exact:
                concept["canonical_id"] = exact.get("id") or exact.get("canonical_id")
                concept["existing_match"] = {
                    "canonical_id": concept["canonical_id"],
                    "name": exact.get("name"),
                    "confidence": 1.0,
                    "reason": "名称或别名与同类型既有概念精确匹配，将修复关系而不创建重复节点。",
                }
                continue
            for score, node in sorted(fuzzy, key=lambda item: item[0], reverse=True)[:3]:
                duplicate_candidates.append({
                    "slot_index": concept.get("slot_index"),
                    "canonical_id": node.get("id") or node.get("canonical_id"),
                    "name": node.get("name"),
                    "concept_type": expected_type,
                    "similarity": round(score, 4),
                    "reason": "名称相近但没有充分证据自动复用，请在审核时留意。",
                })
        return duplicate_candidates

    def generate(self, proposal_id: str, paradigm_config: dict[str, Any]) -> dict[str, Any]:
        proposal_record = self.proposal_store.require(proposal_id)
        gap = self.gap_store.require(proposal_record["gap_id"])
        if gap["status"] != "open" or gap["version"] != proposal_record["gap_version"]:
            return self.proposal_store.mark_stale(proposal_id)
        imported_sources = [
            item for item in proposal_record.get("source_recommendations") or []
            if isinstance(item, dict) and item.get("status") == "imported"
        ]
        imported_chunk_ids: list[str] = []
        for item in imported_sources:
            imported_chunk_ids.extend(item.get("chunk_ids") or [])
            if item.get("chunk_id"):
                imported_chunk_ids.append(item["chunk_id"])
        context, all_nodes = self.context_builder.build(
            gap,
            paradigm_config,
            extra_source_ids=list(dict.fromkeys(imported_chunk_ids)),
        )
        result = self.advisor.advise(context)
        duplicate_candidates = self._screen_duplicates(result["proposal"], all_nodes)
        return self.proposal_store.save_result(
            proposal_id,
            status=result["status"],
            proposal=result["proposal"],
            evidence=result["evidence"],
            duplicate_candidates=duplicate_candidates,
            source_recommendations=imported_sources + result["source_recommendations"],
            input_hash=result["input_hash"],
            prompt_version=result["prompt_version"],
            model=result["model"],
            provider=result["provider"],
            raw_response=result["raw_response"],
        )

    def accept(
        self,
        proposal_id: str,
        *,
        acted_by: str,
        expected_gap_version: int,
        edits: Optional[Sequence[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        record = self.proposal_store.require(proposal_id)
        if record["status"] == "accepted":
            return {"proposal": record, "gap": self.gap_store.require(record["gap_id"])}
        if record["status"] == "applying":
            current_gap = self.gap_store.require(record["gap_id"])
            if current_gap["status"] == "supplemented":
                reviewed = self.proposal_store.finish_accept(
                    proposal_id, reviewed_by=acted_by
                )
                return {"proposal": reviewed, "gap": current_gap}
            raise GapConflictError("proposal is currently being applied")
        if record["status"] != "ready":
            raise GapConflictError(f"only ready proposal can be accepted, current {record['status']}")
        gap = self.gap_store.require(record["gap_id"])
        if (
            gap["status"] != "open"
            or gap["version"] != int(expected_gap_version)
            or record["gap_version"] != int(expected_gap_version)
        ):
            self.proposal_store.mark_stale(proposal_id)
            raise GapConflictError(
                f"gap state/version conflict: current {gap['status']}@{gap['version']}"
            )

        concepts = [dict(item) for item in record["proposal"].get("concepts") or []]
        if len(concepts) != len(gap["missing_types"]):
            raise ValueError("proposal concept count does not match gap")
        if edits is not None:
            if len(edits) != len(concepts):
                raise ValueError("edited concept count does not match proposal")
            for index, edit in enumerate(edits):
                if concepts[index].get("canonical_id"):
                    continue
                if str(edit.get("concept_type") or concepts[index]["concept_type"]) != concepts[index]["concept_type"]:
                    raise ValueError("concept type cannot be edited")
                for field, limit in (("name", 255), ("description", 4000)):
                    value = str(edit.get(field) or "").strip()
                    if not value:
                        raise ValueError(f"edited {field} must not be empty")
                    concepts[index][field] = value[:limit]
                concepts[index]["aliases"] = list(dict.fromkeys(
                    str(item).strip()[:255]
                    for item in (edit.get("aliases") or concepts[index].get("aliases") or [])
                    if str(item).strip()
                ))[:12]

        # Re-run exact duplicate screening after optional user edits so a renamed
        # proposal cannot create a second canonical node with an existing alias.
        self._screen_duplicates(
            {"concepts": concepts},
            self.graph_store.get_canonical_concepts(limit=None),
        )

        specs: list[dict[str, Any]] = []
        for concept in concepts:
            if concept.get("canonical_id"):
                specs.append({"canonical_id": concept["canonical_id"]})
                continue
            evidence = "\n".join(
                f"[{item['chunk_id']}] {item['quote']}"
                for item in concept.get("evidence") or []
            )
            specs.append({
                "name": concept["name"],
                "concept_type": concept["concept_type"],
                "description": concept["description"],
                "aliases": concept.get("aliases") or [],
                "source_chunks": concept.get("source_chunk_ids") or [],
                "evidence": evidence,
            })
        self.proposal_store.claim_for_accept(proposal_id, reviewed_by=acted_by)
        try:
            completed_gap = GapSupplementService(self.gap_store, self.graph_store).supplement(
                gap_id=gap["gap_id"],
                concepts=specs,
                acted_by=acted_by,
                expected_version=expected_gap_version,
            )
            reviewed = self.proposal_store.finish_accept(
                proposal_id, reviewed_by=acted_by
            )
        except Exception as exc:
            current_gap = self.gap_store.require(gap["gap_id"])
            if current_gap["status"] == "supplemented":
                try:
                    self.proposal_store.finish_accept(proposal_id, reviewed_by=acted_by)
                except Exception:
                    pass
            else:
                self.proposal_store.release_accept(proposal_id, str(exc))
            raise
        return {"proposal": reviewed, "gap": completed_gap}

    def reject(self, proposal_id: str, *, acted_by: str) -> dict[str, Any]:
        return self.proposal_store.review(
            proposal_id, decision="reject", reviewed_by=acted_by
        )


__all__ = [
    "GapCompletionContextBuilder",
    "GapCompletionService",
]

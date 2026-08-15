"""Global concept resolution: candidate retrieval, relation classification and merge."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from core.embedding import EmbeddingManager
from core.graph_store import GraphStore


class _UnionFind:
    def __init__(self, values: Iterable[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        # The root is deliberately deterministic; display-name selection happens later.
        winner, loser = sorted((left_root, right_root))
        self.parent[loser] = winner


class ConceptDeduper:
    """Resolve extracted names into canonical concepts without greedy-order effects."""

    # Backwards-compatible constructor setting. It is now the lower bound for an
    # embedding-only SAME_AS review candidate, not an unconditional merge threshold.
    SIMILARITY_THRESHOLD = 0.85
    CANDIDATE_SIMILARITY_THRESHOLD = 0.72
    AUTO_MERGE_SIMILARITY_THRESHOLD = 0.94

    _SAFE_SUFFIXES = ("技术", "术语", "概念")
    _STRUCTURAL_MARKERS = (
        "阶段", "流程", "步骤", "链", "系统", "平台", "模块", "组件", "模型",
        "方法", "算法", "应用", "案例", "问题", "挑战", "方案", "实现", "查询",
        "评估", "优化", "框架", "架构", "服务", "工具", "数据集", "指标",
    )

    def __init__(
        self,
        collection_name: str,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        graph_store=None,
        embedding_manager=None,
    ):
        self.collection_name = collection_name
        self.similarity_threshold = float(similarity_threshold)
        self.graph_store = graph_store or GraphStore(collection_name)
        self.embedding = embedding_manager or EmbeddingManager()
        self._embedding_cache: Dict[str, List[float]] = {}
        self.last_report: Dict[str, Any] = {}

    @staticmethod
    def _normalize_name(value: str) -> str:
        value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        return re.sub(r"[\s\-_·•/\\()（）\[\]【】]+", "", value)

    @staticmethod
    def _clean_aliases(value: Any, concept_name: str = "") -> List[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                value = parsed if isinstance(parsed, list) else [value]
            except Exception:
                value = [part.strip() for part in re.split(r"[;,；，]", value)]
        if not isinstance(value, list):
            return []
        concept_norm = ConceptDeduper._normalize_name(concept_name)
        result: List[str] = []
        seen = set()
        for item in value:
            alias = str(item or "").strip()
            norm = ConceptDeduper._normalize_name(alias)
            if not alias or not norm or norm == concept_norm or norm in seen:
                continue
            seen.add(norm)
            result.append(alias[:120])
        return result

    @staticmethod
    def _clean_alias_evidence(value: Any) -> List[Dict[str, str]]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                return []
        if not isinstance(value, list):
            return []
        result: List[Dict[str, str]] = []
        seen = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            alias = str(item.get("alias") or "").strip()[:120]
            evidence = str(item.get("evidence") or "").strip()[:240]
            if not alias or not evidence:
                continue
            key = (ConceptDeduper._normalize_name(alias), evidence)
            if key in seen:
                continue
            seen.add(key)
            result.append({"alias": alias, "evidence": evidence})
        return result

    def _get_embedding(self, text: str) -> List[float]:
        if not text:
            return [0.0] * 2048
        if text not in self._embedding_cache:
            self._embedding_cache[text] = self.embedding.embed([text])[0]
        return self._embedding_cache[text]

    @staticmethod
    def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
        a_vec = np.asarray(a, dtype=float)
        b_vec = np.asarray(b, dtype=float)
        if a_vec.size == 0 or b_vec.size == 0 or a_vec.size != b_vec.size:
            return 0.0
        denominator = np.linalg.norm(a_vec) * np.linalg.norm(b_vec)
        return float(np.dot(a_vec, b_vec) / denominator) if denominator else 0.0

    @staticmethod
    def _generate_canonical_id(name: str) -> str:
        digest = hashlib.md5((name or "unnamed").encode("utf-8")).hexdigest()[:10]
        return f"concept_canonical_{digest}"

    def collect_all_concepts(self) -> List[Dict[str, Any]]:
        nodes = self.graph_store.get_extracted_concepts(limit=10000)
        details = self.graph_store._load_concept_details()
        concepts = []
        for node in nodes:
            concept_id = node.get("id", "")
            detail = details.get(concept_id, {})
            aliases = self._clean_aliases(
                detail.get("aliases", node.get("aliases", [])), node.get("name", "")
            )
            alias_evidence = self._clean_alias_evidence(
                detail.get("alias_evidence", node.get("alias_evidence", []))
            )
            concepts.append({
                "id": concept_id,
                "name": str(node.get("name") or "").strip(),
                "concept_type": node.get("type", "definition"),
                "extract_role": node.get("extract_role", "DEFINES"),
                "source_chunk": node.get("source_chunk", ""),
                "description": detail.get("description", node.get("description", "")),
                "parent_hint": detail.get("parent_hint", node.get("parent_hint", "")),
                "aliases": aliases,
                "alias_evidence": alias_evidence,
                "media_refs": node.get("media_refs", []),
            })
        return [concept for concept in concepts if concept["name"]]

    def _infer_inline_aliases(self, name: str, descriptions: Iterable[str]) -> List[Dict[str, str]]:
        """Recover explicit X (Y) evidence from legacy extraction descriptions."""
        name_norm = self._normalize_name(name)
        results: List[Dict[str, str]] = []
        patterns = (
            re.compile(r"\b([A-Za-z][A-Za-z0-9.+_-]{1,30})\s*[（(]\s*([^()（）]{1,80})\s*[)）]"),
            re.compile(r"([\u4e00-\u9fff]{2,20})\s*[（(]\s*([A-Z][A-Z0-9.+_-]{1,20})\s*[)）]"),
        )
        seen = set()
        for description in descriptions:
            for pattern in patterns:
                for match in pattern.finditer(str(description or "")):
                    left, right = (part.strip(" ：:，,。.;；") for part in match.groups())
                    left_norm, right_norm = self._normalize_name(left), self._normalize_name(right)
                    if name_norm == left_norm:
                        alias = right
                    elif name_norm == right_norm:
                        alias = left
                    else:
                        continue
                    alias_norm = self._normalize_name(alias)
                    if not alias_norm or alias_norm == name_norm or alias_norm in seen:
                        continue
                    seen.add(alias_norm)
                    results.append({"alias": alias, "evidence": match.group(0)[:240]})
        return results

    def _build_profiles(self, concepts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for concept in concepts:
            grouped[self._normalize_name(concept["name"])].append(concept)

        profiles: Dict[str, Dict[str, Any]] = {}
        for normalized_name in sorted(grouped):
            originals = grouped[normalized_name]
            surface_counts = Counter(item["name"] for item in originals)
            name = sorted(
                surface_counts,
                key=lambda value: (-surface_counts[value], -len(value), value),
            )[0]
            aliases: List[str] = []
            evidence: List[Dict[str, str]] = []
            for concept in originals:
                aliases.extend(self._clean_aliases(concept.get("aliases"), name))
                evidence.extend(self._clean_alias_evidence(concept.get("alias_evidence")))
            inferred = self._infer_inline_aliases(name, (c.get("description", "") for c in originals))
            evidence.extend(inferred)
            aliases.extend(item["alias"] for item in evidence)
            aliases = self._clean_aliases(aliases, name)
            evidence = self._clean_alias_evidence(evidence)
            profiles[name] = {
                "name": name,
                "normalized_name": self._normalize_name(name),
                "aliases": aliases,
                "alias_norms": {self._normalize_name(alias) for alias in aliases},
                "alias_evidence": evidence,
                "originals": originals,
                "frequency": len(originals),
            }
        return profiles

    def _dedupe_candidate_pairs(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove A↔B/B↔A and normalized spelling duplicates before review."""
        unique: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for candidate in candidates:
            pair = tuple(sorted((
                self._normalize_name(candidate.get("left", "")),
                self._normalize_name(candidate.get("right", "")),
            )))
            if not all(pair) or pair[0] == pair[1]:
                continue
            existing = unique.get(pair)
            if existing is None:
                unique[pair] = candidate
                continue
            # Prefer the stronger/richer representative and merge audit signals.
            winner, other = sorted(
                (existing, candidate),
                key=lambda item: (
                    float(item.get("confidence", 0)),
                    len(item.get("evidence", [])),
                    item.get("left", ""),
                    item.get("right", ""),
                ),
                reverse=True,
            )
            winner = dict(winner)
            winner["signals"] = sorted(set(
                winner.get("signals", []) + other.get("signals", [])
            ))
            evidence = winner.get("evidence", []) + other.get("evidence", [])
            seen_evidence = set()
            unique_evidence = []
            for item in evidence:
                key = (item.get("alias", ""), item.get("evidence", ""))
                if key in seen_evidence:
                    continue
                seen_evidence.add(key)
                unique_evidence.append(item)
            winner["evidence"] = unique_evidence[:8]
            unique[pair] = winner
        return sorted(unique.values(), key=lambda item: (
            self._normalize_name(item["left"]),
            self._normalize_name(item["right"]),
        ))

    def _weak_base(self, normalized: str) -> str:
        for suffix in self._SAFE_SUFFIXES:
            suffix_norm = self._normalize_name(suffix)
            if normalized.endswith(suffix_norm) and len(normalized) > len(suffix_norm) + 1:
                return normalized[:-len(suffix_norm)]
        return normalized

    def _structural_marker(self, name: str) -> Optional[str]:
        norm = self._normalize_name(name)
        for marker in self._STRUCTURAL_MARKERS:
            if self._normalize_name(marker) in norm:
                return marker
        return None

    def _has_explicit_alias(self, left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        return (
            right["normalized_name"] in left["alias_norms"]
            or left["normalized_name"] in right["alias_norms"]
        )

    def _classify_candidate(
        self,
        left: Dict[str, Any],
        right: Dict[str, Any],
        similarity: float,
    ) -> Optional[Dict[str, Any]]:
        left_name, right_name = left["name"], right["name"]
        left_norm, right_norm = left["normalized_name"], right["normalized_name"]
        explicit_alias = self._has_explicit_alias(left, right)
        left_base = self._weak_base(left_norm)
        right_base = self._weak_base(right_norm)
        weak_equal = left_base == right_base
        left_marker = self._structural_marker(left_name)
        right_marker = self._structural_marker(right_name)
        containment = bool(left_norm and right_norm and (left_norm in right_norm or right_norm in left_norm))
        base_containment = bool(
            left_base and right_base and left_base != right_base
            and (left_base in right_base or right_base in left_base)
        )
        shorter_name = left_name if len(left_norm) <= len(right_norm) else right_name
        shorter_is_acronym = bool(re.fullmatch(r"[A-Z][A-Z0-9.+_-]{1,10}", shorter_name))

        signals: List[str] = []
        if explicit_alias:
            signals.append("explicit_alias_evidence")
        if weak_equal and left_norm != right_norm:
            signals.append("safe_generic_suffix")
        if similarity:
            signals.append(f"name_embedding:{similarity:.4f}")

        if left_norm == right_norm:
            relation, confidence, decision = "SAME_AS", 1.0, "auto_merge"
        elif explicit_alias:
            relation, confidence, decision = "SAME_AS", 0.99, "auto_merge"
        elif weak_equal and not left_marker and not right_marker and shorter_is_acronym:
            relation, confidence, decision = "SAME_AS", 0.96, "auto_merge"
        elif weak_equal and not left_marker and not right_marker:
            relation, confidence, decision = "SAME_AS", max(0.88, similarity), "review"
        elif (left_marker or right_marker) and (containment or similarity >= self.similarity_threshold):
            # A stage, chain, system or application of X is not X itself.
            if containment:
                relation = "NARROWER_THAN" if len(left_norm) != len(right_norm) else "RELATED_TO"
            else:
                relation = "RELATED_TO"
            confidence, decision = max(0.80, similarity), "keep_separate"
            signals.append(f"structural_modifier:{left_marker or right_marker}")
        elif containment or base_containment:
            relation, confidence, decision = "NARROWER_THAN", max(0.76, similarity), "keep_separate"
            signals.append("lexical_containment_after_safe_suffix")
        elif similarity >= self.AUTO_MERGE_SIMILARITY_THRESHOLD:
            relation, confidence, decision = "SAME_AS", similarity, "auto_merge"
        elif similarity >= self.similarity_threshold:
            relation, confidence, decision = "SAME_AS", similarity, "review"
        elif similarity >= self.CANDIDATE_SIMILARITY_THRESHOLD:
            relation, confidence, decision = "RELATED_TO", similarity, "keep_separate"
        else:
            return None

        subject, object_name = left_name, right_name
        if relation == "NARROWER_THAN":
            subject, object_name = (
                (left_name, right_name)
                if len(left_norm) > len(right_norm)
                else (right_name, left_name)
            )

        def review_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
            originals = profile.get("originals", [])
            type_counts = Counter(
                item.get("concept_type", "definition") for item in originals
            )
            descriptions = sorted({
                str(item.get("description") or "").strip()
                for item in originals if item.get("description")
            }, key=lambda value: (-len(value), value))
            source_chunks = sorted({
                str(item.get("source_chunk") or "").strip()
                for item in originals if item.get("source_chunk")
            })
            return {
                "name": profile["name"],
                "types": dict(sorted(type_counts.items())),
                "aliases": profile.get("aliases", [])[:8],
                "descriptions": descriptions[:3],
                "source_chunks": source_chunks[:8],
                "occurrences": len(originals),
            }

        return {
            "left": left_name,
            "right": right_name,
            "left_profile": review_profile(left),
            "right_profile": review_profile(right),
            "subject": subject,
            "object": object_name,
            "relation": relation,
            "confidence": round(float(confidence), 6),
            "decision": decision,
            "signals": signals,
            "evidence": sorted(
                left.get("alias_evidence", []) + right.get("alias_evidence", []),
                key=lambda item: (item.get("alias", ""), item.get("evidence", "")),
            )[:8],
        }

    def _retrieve_and_classify(self, profiles: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        names = list(profiles)
        embeddings: Dict[str, List[float]] = {}
        missing_names = [name for name in names if name not in self._embedding_cache]
        try:
            if missing_names:
                vectors = self.embedding.embed(missing_names)
                if len(vectors) != len(missing_names):
                    raise RuntimeError("embedding result length mismatch")
                self._embedding_cache.update(zip(missing_names, vectors))
        except Exception as exc:
            print(f"[ConceptDeduper] batched embedding failed, falling back per name: {exc}")

        for name in names:
            try:
                embeddings[name] = self._get_embedding(name)
            except Exception as exc:
                print(f"[ConceptDeduper] embedding failed for '{name}': {exc}")
                embeddings[name] = []

        candidates: List[Dict[str, Any]] = []
        for index, left_name in enumerate(names):
            for right_name in names[index + 1:]:
                left, right = profiles[left_name], profiles[right_name]
                explicit = self._has_explicit_alias(left, right)
                weak_equal = self._weak_base(left["normalized_name"]) == self._weak_base(right["normalized_name"])
                containment = (
                    left["normalized_name"] in right["normalized_name"]
                    or right["normalized_name"] in left["normalized_name"]
                )
                left_base = self._weak_base(left["normalized_name"])
                right_base = self._weak_base(right["normalized_name"])
                base_containment = (
                    left_base != right_base
                    and (left_base in right_base or right_base in left_base)
                )
                similarity = self._cosine_similarity(embeddings[left_name], embeddings[right_name])
                if not (
                    explicit or weak_equal or containment or base_containment
                    or similarity >= self.CANDIDATE_SIMILARITY_THRESHOLD
                ):
                    continue
                candidate = self._classify_candidate(left, right, similarity)
                if candidate:
                    candidates.append(candidate)
        return self._dedupe_candidate_pairs(candidates)

    def _canonical_name(self, names: List[str], profiles: Dict[str, Dict[str, Any]]) -> str:
        def score(name: str) -> Tuple[int, int, int, int, str]:
            norm = profiles[name]["normalized_name"]
            marker_penalty = -1 if self._structural_marker(name) else 0
            safe_suffix_penalty = -1 if self._weak_base(norm) != norm else 0
            acronym_penalty = -1 if re.fullmatch(r"[A-Za-z][A-Za-z0-9.+_-]{1,15}", name) else 0
            chinese_bonus = 1 if re.search(r"[\u4e00-\u9fff]", name) else 0
            return (
                marker_penalty,
                safe_suffix_penalty,
                chinese_bonus + acronym_penalty,
                profiles[name]["frequency"],
                -len(name),
            )

        # max() is deterministic because names are pre-sorted and the final fallback is lexical.
        return max(sorted(names), key=lambda name: (score(name), tuple(-ord(ch) for ch in name)))

    def _build_canonical_concepts(
        self,
        profiles: Dict[str, Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        merge_decisions: Optional[set[Tuple[str, str]]] = None,
        canonical_name_decisions: Optional[Dict[Tuple[str, str], str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, str], Dict[str, List[str]]]:
        union_find = _UnionFind(profiles)
        merge_decisions = merge_decisions or set()
        canonical_name_decisions = canonical_name_decisions or {}
        for candidate in candidates:
            pair = tuple(sorted((candidate["left"], candidate["right"])))
            if (
                candidate["relation"] == "SAME_AS"
                and (candidate["decision"] == "auto_merge" or pair in merge_decisions)
            ):
                union_find.union(candidate["left"], candidate["right"])

        groups_by_root: Dict[str, List[str]] = defaultdict(list)
        for name in profiles:
            groups_by_root[union_find.find(name)].append(name)

        canonical_groups: Dict[str, List[str]] = {}
        for names in groups_by_root.values():
            ordered_names = sorted(names, key=lambda value: (self._normalize_name(value), value))
            canonical_groups[self._canonical_name(ordered_names, profiles)] = ordered_names

        # A reviewer may choose either existing label as the display name.
        for names in list(canonical_groups.values()):
            chosen = next((
                canonical_name_decisions[pair]
                for pair in sorted(canonical_name_decisions)
                if canonical_name_decisions[pair] in names and set(pair).issubset(names)
            ), None)
            if not chosen:
                continue
            old_key = next(key for key, value in canonical_groups.items() if value is names)
            if old_key != chosen:
                del canonical_groups[old_key]
                canonical_groups[chosen] = names

        canonical_map: Dict[str, str] = {}
        derived_from_map: Dict[str, str] = {}
        canonical_concepts: List[Dict[str, Any]] = []
        for canonical_name in sorted(canonical_groups, key=lambda value: (self._normalize_name(value), value)):
            merged_names = canonical_groups[canonical_name]
            originals = [item for name in merged_names for item in profiles[name]["originals"]]
            canonical_id = self._generate_canonical_id(canonical_name)
            for name in merged_names:
                canonical_map[name] = canonical_name
            for original in originals:
                derived_from_map[original["id"]] = canonical_id

            type_counts = Counter(item.get("concept_type", "definition") for item in originals)
            dominant_type = sorted(type_counts, key=lambda value: (-type_counts[value], value))[0]
            descriptions = [str(item.get("description") or "") for item in originals if item.get("description")]
            description = sorted(descriptions, key=lambda value: (-len(value), value))[0] if descriptions else ""
            hints = Counter(str(item.get("parent_hint") or "").strip() for item in originals if item.get("parent_hint"))
            parent_hint = sorted(hints, key=lambda value: (-hints[value], value))[0] if hints else ""
            source_chunks = sorted({str(item.get("source_chunk") or "") for item in originals if item.get("source_chunk")})

            aliases: List[str] = list(merged_names)
            alias_evidence: List[Dict[str, str]] = []
            for name in merged_names:
                aliases.extend(profiles[name]["aliases"])
                alias_evidence.extend(profiles[name]["alias_evidence"])
            aliases = [canonical_name] + self._clean_aliases(aliases, canonical_name)
            alias_evidence = self._clean_alias_evidence(alias_evidence)

            media_refs: List[Dict[str, Any]] = []
            seen_refs = set()
            for original in originals:
                for ref in original.get("media_refs", []) or []:
                    key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
                    if key not in seen_refs:
                        seen_refs.add(key)
                        media_refs.append(ref)

            canonical_concepts.append({
                "id": canonical_id,
                "name": canonical_name,
                "aliases": aliases,
                "alias_count": len(aliases),
                "alias_evidence": alias_evidence,
                "concept_type": dominant_type,
                "type_votes": dict(sorted(type_counts.items())),
                "source_chunks": source_chunks,
                "source_chunk_count": len(source_chunks),
                "description": description,
                "parent_hint": parent_hint,
                "media_refs": media_refs,
                "embedding": self._get_embedding(canonical_name),
            })
        return canonical_concepts, derived_from_map, canonical_map, canonical_groups

    def dedupe_all(
        self,
        review_decisions: Optional[Dict[Tuple[str, str], str]] = None,
        canonical_name_decisions: Optional[Dict[Tuple[str, str], str]] = None,
        require_review_complete: bool = False,
    ) -> List[Dict[str, Any]]:
        print(f"[ConceptDeduper] resolving concepts: {self.collection_name}")
        concepts = self.collect_all_concepts()
        if not concepts:
            self.last_report = {"status": "empty", "candidates": [], "review_candidates": []}
            return []

        profiles = self._build_profiles(concepts)
        candidates = self._retrieve_and_classify(profiles)
        review_candidates = [item for item in candidates if item["decision"] == "review"]
        normalized_decisions = {
            tuple(sorted(pair)): action
            for pair, action in (review_decisions or {}).items()
        }
        unresolved = [
            item for item in review_candidates
            if tuple(sorted((item["left"], item["right"]))) not in normalized_decisions
        ]
        merge_decisions = {
            pair for pair, action in normalized_decisions.items() if action == "merge"
        }
        canonical, derived_map, canonical_map, groups = self._build_canonical_concepts(
            profiles,
            candidates,
            merge_decisions=merge_decisions,
            canonical_name_decisions=canonical_name_decisions,
        )
        should_persist = not (require_review_complete and unresolved)
        added = 0
        if should_persist:
            added = self.graph_store.add_canonical_concepts(canonical, derived_from_map=derived_map)
            self._save_name_mapping(canonical_map, groups, profiles)

        self.last_report = {
            "status": "success" if should_persist else "waiting_merge_review",
            "extracted_concepts": len(concepts),
            "unique_names": len(profiles),
            "canonical_concepts": len(canonical),
            "written_canonical_concepts": added,
            "candidate_count": len(candidates),
            "auto_merge_count": sum(item["decision"] == "auto_merge" for item in candidates),
            "review_candidate_count": len(review_candidates),
            "unresolved_review_count": len(unresolved),
            "persisted": should_persist,
            "kept_separate_count": sum(item["decision"] == "keep_separate" for item in candidates),
            "candidates": candidates,
            "review_candidates": review_candidates,
            "unresolved_review_candidates": unresolved,
        }
        print(
            f"[ConceptDeduper] {len(concepts)} extracted / {len(profiles)} names -> "
            f"{len(canonical)} canonical; {len(review_candidates)} require review"
        )
        return canonical

    def _save_name_mapping(
        self,
        canonical_map: Dict[str, str],
        canonical_groups: Dict[str, List[str]],
        profiles: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        name_to_id: Dict[str, str] = {}
        for canonical_name, merged_names in canonical_groups.items():
            canonical_id = self._generate_canonical_id(canonical_name)
            all_names = list(merged_names)
            if profiles:
                for name in merged_names:
                    all_names.extend(profiles[name].get("aliases", []))
            for name in all_names + [canonical_name]:
                normalized = str(name or "").strip().lower()
                if normalized:
                    name_to_id[normalized] = canonical_id
        path = self.graph_store.data_dir / "name_mapping.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dict(sorted(name_to_id.items())), handle, ensure_ascii=False, indent=2)

    def load_name_mapping(self) -> Dict[str, str]:
        path = self.graph_store.data_dir / "name_mapping.json"
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def export_table(self, output_path: str = None, concepts: Optional[List[Dict[str, Any]]] = None) -> str:
        if output_path is None:
            output_path = str(self.graph_store.data_dir / "concepts.csv")
        if concepts is None:
            concepts = self.dedupe_all()
        if not concepts:
            return output_path

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "id", "name", "aliases", "alias_count", "alias_evidence",
                "concept_type", "relation", "source_chunks", "source_chunk_count",
                "description", "parent_hint", "media_refs", "embedding",
            ])
            for concept in concepts:
                embedding = concept.get("embedding", [])
                if isinstance(embedding, np.ndarray):
                    embedding = embedding.tolist()
                writer.writerow([
                    concept["id"],
                    concept["name"],
                    ";".join(str(item) for item in concept.get("aliases", []) if item),
                    concept.get("alias_count", 0),
                    json.dumps(concept.get("alias_evidence", []), ensure_ascii=False),
                    concept.get("concept_type", ""),
                    concept.get("extract_role", ""),
                    ",".join(str(item) for item in concept.get("source_chunks", []) if item),
                    concept.get("source_chunk_count", 0),
                    concept.get("description", ""),
                    concept.get("parent_hint", ""),
                    json.dumps(concept.get("media_refs", []), ensure_ascii=False),
                    json.dumps(embedding) if embedding else "",
                ])
        return output_path

    def get_deduped_stats(self, concepts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if concepts is None:
            concepts = self.dedupe_all()
        if not concepts:
            return {"status": "empty", "concepts": [], **self.last_report}
        type_distribution = Counter(concept["concept_type"] for concept in concepts)
        return {
            "status": "success",
            "canonical_concepts": len(concepts),
            "type_distribution": dict(sorted(type_distribution.items())),
            "concepts": concepts[:20],
            "dedupe_report": self.last_report,
        }


def main() -> None:
    import sys

    collection = sys.argv[1] if len(sys.argv) > 1 else "ai_llm_v1"
    deduper = ConceptDeduper(collection)
    concepts = deduper.dedupe_all()
    deduper.export_table(concepts=concepts)


if __name__ == "__main__":
    main()

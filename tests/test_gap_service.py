import pytest

from core.gap_detector import GapCandidate
from core.gap_service import GapSupplementService
from core.gap_store import GapStore


class FakeGraphStore:
    def __init__(self, fail_relation=None):
        self.concepts = {
            "definition-1": {"canonical_id": "definition-1", "concept_type": "definition"},
            "application-1": {"canonical_id": "application-1", "concept_type": "application"},
        }
        self.edges = {("definition-1", "application-1", "APPLIES_TO")}
        self.fail_relation = fail_relation

    def get_canonical_concept(self, canonical_id):
        return self.concepts.get(canonical_id)

    def ensure_gap_concept(
        self, *, canonical_id, name, concept_type, description, evidence="",
        aliases=None, source_chunks=None,
    ):
        if canonical_id in self.concepts:
            return self.concepts[canonical_id], False
        concept = {
            "canonical_id": canonical_id, "concept_type": concept_type, "name": name,
            "aliases": aliases or [], "source_chunks": source_chunks or [],
        }
        self.concepts[canonical_id] = concept
        return concept, True

    def ensure_canonical_edge(self, source_id, target_id, relation, confidence=1.0):
        if relation == self.fail_relation:
            raise RuntimeError("cycle or graph failure")
        edge = (source_id, target_id, relation)
        created = edge not in self.edges
        self.edges.add(edge)
        return created

    def remove_canonical_edge(self, source_id, target_id, relation):
        edge = (source_id, target_id, relation)
        existed = edge in self.edges
        self.edges.discard(edge)
        return existed

    def delete_gap_concept_if_orphan(self, canonical_id):
        if any(canonical_id in edge[:2] for edge in self.edges):
            return False
        return self.concepts.pop(canonical_id, None) is not None


def make_store(tmp_path):
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    store.reconcile([
        GapCandidate(
            gap_id="gap_1", subject_id="subject-a", paradigm_id="theory",
            source_id="definition-1", target_id="application-1",
            missing_types=("law",), original_relation="APPLIES_TO",
            replacement_relations=("HAS_LAW", "APPLIES_TO"),
            reason="skip", confidence=1.0, detector_version="v1",
        )
    ])
    return store


def test_supplement_creates_real_chain_and_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    graph = FakeGraphStore()
    service = GapSupplementService(store, graph)
    request = [{
        "name": "A law", "concept_type": "law", "description": "Evidence-backed law"
    }]

    completed = service.supplement(
        gap_id="gap_1", concepts=request, acted_by="owner", expected_version=1
    )
    again = service.supplement(
        gap_id="gap_1", concepts=request, acted_by="owner", expected_version=1
    )

    assert completed["status"] == again["status"] == "supplemented"
    assert len(completed["supplemented_by"]) == 1
    concept_id = completed["supplemented_by"][0]
    assert ("definition-1", concept_id, "HAS_LAW") in graph.edges
    assert (concept_id, "application-1", "APPLIES_TO") in graph.edges
    assert ("definition-1", "application-1", "APPLIES_TO") not in graph.edges


def test_graph_failure_compensates_edges_concept_and_gap_state(tmp_path):
    store = make_store(tmp_path)
    graph = FakeGraphStore(fail_relation="APPLIES_TO")
    service = GapSupplementService(store, graph)

    with pytest.raises(RuntimeError):
        service.supplement(
            gap_id="gap_1",
            concepts=[{"name": "A law", "concept_type": "law", "description": "desc"}],
            acted_by="owner",
            expected_version=1,
        )

    assert store.require("gap_1")["status"] == "open"
    assert set(graph.concepts) == {"definition-1", "application-1"}
    assert graph.edges == {("definition-1", "application-1", "APPLIES_TO")}


def test_existing_concept_type_must_match_gap(tmp_path):
    store = make_store(tmp_path)
    graph = FakeGraphStore()
    service = GapSupplementService(store, graph)

    with pytest.raises(ValueError):
        service.supplement(
            gap_id="gap_1",
            concepts=[{"canonical_id": "application-1"}],
            acted_by="owner",
            expected_version=1,
        )

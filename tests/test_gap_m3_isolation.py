from pathlib import Path

from core.graph_store import GraphStore
from core.semantic_linker import SemanticLinker


def test_all_legacy_virtual_signatures_are_recognised():
    assert GraphStore.is_legacy_virtual_concept({"id": "__virtual_deadbeef_law_a_b"})
    assert GraphStore.is_legacy_virtual_concept({"id": "x", "is_virtual": "true"})
    assert GraphStore.is_legacy_virtual_concept({"id": "x", "description": "[VIRTUAL] old"})
    assert GraphStore.is_legacy_virtual_concept({"id": "x", "source_chunks": '["__virtual__"]'})
    assert not GraphStore.is_legacy_virtual_concept({"id": "real", "is_virtual": False})


def test_semantic_linker_m3_hook_never_materialises_virtual_nodes():
    linker = SemanticLinker.__new__(SemanticLinker)
    linker._get_concept_type = lambda node_id: {
        "d": "definition", "a": "application"
    }[node_id]
    edges = [{"parent_id": "d", "child_id": "a", "relation_type": "APPLIES_TO"}]
    returned, stats = linker._detect_gaps_without_virtual_nodes(
        edges, {"cyclic": False, "ideal_chain": ["definition", "law", "application"]}
    )
    assert returned == edges
    assert stats == {"gap_edges": 1, "virtual_nodes": 0}


def test_education_queries_and_packaging_include_gap_flow_m3_modules():
    root = Path(__file__).parents[1]
    retriever = (root / "core/graph_education/concept_retriever.py").read_text(encoding="utf-8")
    builder = (root / "core/graph_education/subgraph_builder.py").read_text(encoding="utf-8")
    spec = (root / "app.spec").read_text(encoding="utf-8")
    assert retriever.count("STARTS WITH '__virtual_'") >= 10
    assert builder.count("STARTS WITH '__virtual_'") >= 6
    for module in (
        "core.gap_detector", "core.gap_store", "core.gap_service",
        "core.gap_migration", "core.gap_proposal_store",
        "core.gap_completion_advisor", "core.gap_completion_service",
        "core.knowledge_search",
        "app.gap_api",
    ):
        assert module in spec

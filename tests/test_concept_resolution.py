import json
from pathlib import Path

from core.concept_deduper import ConceptDeduper
from core.semantic_extractor import SemanticExtractor
from core.graph_store import GraphStore
from core.graph_builder import GraphBuilder
from core.merge_review_store import MergeReviewStore


class FakeEmbeddingManager:
    def __init__(self, vectors=None):
        self.vectors = vectors or {}

    def embed(self, texts):
        return [self.vectors.get(text, [0.0, 0.0, 1.0]) for text in texts]


class FakeGraphStore:
    def __init__(self, tmp_path: Path, concepts):
        self.data_dir = tmp_path
        self._concepts = concepts
        self.add_calls = 0
        self.written = []
        self.derived = {}

    def get_extracted_concepts(self, limit=10000):
        return list(self._concepts)[:limit]

    def _load_concept_details(self):
        return {}

    def add_canonical_concepts(self, concepts, derived_from_map=None):
        self.add_calls += 1
        self.written = concepts
        self.derived = derived_from_map or {}
        return len(concepts)


class FakeLLM:
    available = True

    def __init__(self, result):
        self.result = result

    def chat_json(self, **kwargs):
        return self.result


def extracted(concept_id, name, *, aliases=None, alias_evidence=None, description=""):
    return {
        "id": concept_id,
        "name": name,
        "type": "technology",
        "extract_role": "IMPLEMENTS",
        "source_chunk": f"chunk-{concept_id}",
        "description": description,
        "parent_hint": "",
        "aliases": aliases or [],
        "alias_evidence": alias_evidence or [],
        "media_refs": [],
    }


def test_rag_aliases_merge_but_structural_variants_remain_distinct(tmp_path):
    concepts = [
        extracted(
            "1",
            "RAG",
            aliases=["检索增强生成"],
            alias_evidence=[{"alias": "检索增强生成", "evidence": "RAG（检索增强生成）"}],
        ),
        extracted("2", "RAG技术"),
        extracted("3", "检索增强生成"),
        extracted("4", "Graph RAG"),
        extracted("5", "RAG链"),
        extracted("6", "RAG应用"),
    ]
    vectors = {
        "RAG": [1.0, 0.0, 0.0],
        "RAG技术": [0.95, 0.1, 0.0],
        "检索增强生成": [0.2, 0.98, 0.0],
        "Graph RAG": [0.98, 0.1, 0.0],
        "RAG链": [0.97, 0.2, 0.0],
        "RAG应用": [0.96, 0.25, 0.0],
    }
    store = FakeGraphStore(tmp_path, concepts)
    deduper = ConceptDeduper("test", graph_store=store, embedding_manager=FakeEmbeddingManager(vectors))

    canonical = deduper.dedupe_all()

    assert store.add_calls == 1
    assert len(canonical) == 4
    merged = next(item for item in canonical if item["name"] == "检索增强生成")
    assert {"RAG", "RAG技术", "检索增强生成"}.issubset(set(merged["aliases"]))
    assert {item["name"] for item in canonical} >= {"Graph RAG", "RAG链", "RAG应用"}
    assert any(
        candidate["left"] == "RAG" and candidate["right"] == "RAG链"
        and candidate["relation"] == "NARROWER_THAN"
        and candidate["subject"] == "RAG链" and candidate["object"] == "RAG"
        and candidate["decision"] == "keep_separate"
        for candidate in deduper.last_report["candidates"]
    )


def test_legacy_parenthetical_evidence_recovers_alias(tmp_path):
    concepts = [
        extracted("1", "RAG", description="片段明确提及 RAG（检索增强生成），并解释其工作机制。"),
        extracted("2", "检索增强生成"),
    ]
    store = FakeGraphStore(tmp_path, concepts)
    deduper = ConceptDeduper("test", graph_store=store, embedding_manager=FakeEmbeddingManager())

    canonical = deduper.dedupe_all()

    assert len(canonical) == 1
    assert canonical[0]["name"] == "检索增强生成"
    assert canonical[0]["alias_evidence"] == [
        {"alias": "检索增强生成", "evidence": "RAG（检索增强生成）"}
    ]


def test_dedupe_is_deterministic_and_stats_export_do_not_rerun(tmp_path):
    base = [extracted("1", "RAG技术"), extracted("2", "RAG")]
    vectors = {"RAG": [1.0, 0.0, 0.0], "RAG技术": [0.99, 0.01, 0.0]}
    outputs = []
    for index, concepts in enumerate((base, list(reversed(base)))):
        store = FakeGraphStore(tmp_path / str(index), concepts)
        deduper = ConceptDeduper("test", graph_store=store, embedding_manager=FakeEmbeddingManager(vectors))
        canonical = deduper.dedupe_all()
        deduper.get_deduped_stats(concepts=canonical)
        csv_path = deduper.export_table(concepts=canonical)
        outputs.append([(item["id"], item["name"], item["aliases"]) for item in canonical])
        assert store.add_calls == 1
        assert Path(csv_path).exists()
    assert outputs[0] == outputs[1]


def test_embedding_only_medium_confidence_candidate_goes_to_review(tmp_path):
    concepts = [
        extracted("1", "Alpha", description=r"满足 $E=mc^2$ 的描述"),
        extracted("2", "Beta"),
    ]
    vectors = {"Alpha": [1.0, 0.0], "Beta": [0.88, 0.475]}
    store = FakeGraphStore(tmp_path, concepts)
    deduper = ConceptDeduper("test", graph_store=store, embedding_manager=FakeEmbeddingManager(vectors))

    canonical = deduper.dedupe_all()

    assert len(canonical) == 2
    assert deduper.last_report["review_candidate_count"] == 1
    candidate = deduper.last_report["review_candidates"][0]
    assert candidate["relation"] == "SAME_AS"
    assert candidate["left_profile"]["descriptions"] == [r"满足 $E=mc^2$ 的描述"]
    assert candidate["left_profile"]["source_chunks"] == ["chunk-1"]
    assert candidate["left_profile"]["types"] == {"technology": 1}


def test_semantic_extractor_keeps_only_evidenced_aliases():
    aliases, evidence = SemanticExtractor._normalize_alias_fields(
        {
            "aliases": ["RAG", "相关技术"],
            "alias_evidence": [{"alias": "RAG", "evidence": "检索增强生成（RAG）"}],
        },
        "检索增强生成",
    )
    assert aliases == ["RAG"]
    assert evidence == [{"alias": "RAG", "evidence": "检索增强生成（RAG）"}]


def test_single_semantic_extraction_returns_alias_evidence():
    extractor = SemanticExtractor(llm_client=FakeLLM([{
        "name": "检索增强生成",
        "concept_type": "technology",
        "relation": "IMPLEMENTS",
        "description": "结合外部检索与生成",
        "parent_hint": "",
        "aliases": ["RAG", "RAG系统"],
        "alias_evidence": [{"alias": "RAG", "evidence": "检索增强生成（RAG）"}],
    }]), paradigm="engineering")

    concepts = extractor.extract_concepts("检索增强生成（RAG）结合了检索与生成。")

    assert concepts[0]["aliases"] == ["RAG"]
    assert concepts[0]["alias_evidence"][0]["evidence"] == "检索增强生成（RAG）"


def test_batch_semantic_extraction_returns_alias_evidence():
    extractor = SemanticExtractor(llm_client=FakeLLM({
        "chunk-1": [{
            "name": "检索增强生成",
            "concept_type": "technology",
            "relation": "IMPLEMENTS",
            "description": "结合外部检索与生成",
            "parent_hint": "",
            "aliases": ["RAG"],
            "alias_evidence": [{"alias": "RAG", "evidence": "检索增强生成（RAG）"}],
        }],
    }), paradigm="engineering")

    result = extractor.extract_concepts_batch_v2([{"id": "chunk-1", "text": "检索增强生成（RAG）"}])

    assert result["chunk-1"][0]["aliases"] == ["RAG"]


def test_graph_store_persists_alias_evidence(tmp_path):
    db_path = tmp_path / "graph" / "graph"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = GraphStore("test_alias_schema", db_path=str(db_path))
    store.init_schema(force=True)
    store.add_chunk_nodes([{
        "id": "chunk-1",
        "text": "检索增强生成（RAG）",
        "metadata": {"type": "child", "source": "test.md"},
    }])
    store.add_concepts("chunk-1", [{
        "id": "concept-1",
        "name": "检索增强生成",
        "concept_type": "technology",
        "relation": "IMPLEMENTS",
        "description": "一种结合检索和生成的技术",
        "parent_hint": "",
        "aliases": ["RAG"],
        "alias_evidence": [{"alias": "RAG", "evidence": "检索增强生成（RAG）"}],
    }])

    concepts = store.get_extracted_concepts()
    store.close()

    assert concepts[0]["aliases"] == ["RAG"]
    assert concepts[0]["alias_evidence"] == [
        {"alias": "RAG", "evidence": "检索增强生成（RAG）"}
    ]


def test_graph_builder_runs_stateful_dedupe_once(monkeypatch, tmp_path):
    calls = {"dedupe": 0}
    canonical = [{"id": "c1", "name": "RAG", "concept_type": "technology"}]

    class CountingDeduper:
        def __init__(self, collection_name, graph_store=None):
            self.collection_name = collection_name

        def dedupe_all(self, review_decisions=None, require_review_complete=False, canonical_name_decisions=None):
            calls["dedupe"] += 1
            return canonical

        def get_deduped_stats(self, concepts=None):
            assert concepts is canonical
            return {"canonical_concepts": 1}

        def export_table(self, concepts=None):
            assert concepts is canonical
            return str(tmp_path / "concepts.csv")

    monkeypatch.setattr("core.concept_deduper.ConceptDeduper", CountingDeduper)
    builder = object.__new__(GraphBuilder)
    builder.collection_name = "test"
    builder.graph_store = object()

    result = builder.dedupe_concepts()

    assert calls["dedupe"] == 1
    assert result["canonical_concepts"] == 1


def test_merge_review_store_requires_every_decision(tmp_path):
    store = MergeReviewStore(tmp_path)
    run = store.create_waiting_run(
        subject="reality_mit", user_id="user-1", paradigm="theory", options={},
        candidates=[{
            "left": "RAG", "right": "检索增强生成", "relation": "SAME_AS",
            "confidence": 0.88, "signals": ["name_embedding:0.88"], "evidence": [],
        }],
    )
    candidates = store.list_candidates(run["build_id"])
    assert run["pending_candidates"] == 1
    try:
        store.decision_map(run["build_id"])
        assert False, "incomplete review must not resume"
    except ValueError:
        pass

    store.save_decision(run["build_id"], candidates[0]["candidate_id"], decision="merge")
    assert store.decision_map(run["build_id"]) == {("RAG", "检索增强生成"): "merge"}


def test_deduper_does_not_persist_before_review(tmp_path):
    concepts = [extracted("1", "Alpha"), extracted("2", "Beta")]
    vectors = {"Alpha": [1.0, 0.0], "Beta": [0.88, 0.475]}
    store = FakeGraphStore(tmp_path, concepts)
    deduper = ConceptDeduper("test", graph_store=store, embedding_manager=FakeEmbeddingManager(vectors))

    deduper.dedupe_all(require_review_complete=True)

    assert store.add_calls == 0
    assert deduper.last_report["status"] == "waiting_merge_review"


def test_semantic_extractor_requires_chinese_output_and_keeps_original_aliases():
    extractor = SemanticExtractor(llm_client=FakeLLM([]), paradigm="engineering")

    prompt = extractor._get_system_prompt()

    assert "name`、`description`、`parent_hint` 必须使用简体中文" in prompt
    assert "英文原名、标准缩写和英文全称保留在 `aliases`" in prompt
    assert "alias_evidence.evidence" in prompt


def test_profiles_collapse_case_and_unicode_name_variants(tmp_path):
    concepts = [
        extracted("1", "Minkowski Spacetime Diagram"),
        extracted("2", "Minkowski spacetime diagram"),
    ]
    deduper = ConceptDeduper(
        "test", graph_store=FakeGraphStore(tmp_path, concepts),
        embedding_manager=FakeEmbeddingManager(),
    )

    profiles = deduper._build_profiles(concepts)

    assert len(profiles) == 1
    assert len(next(iter(profiles.values()))["originals"]) == 2


def test_review_candidate_pairs_are_unordered_and_normalized(tmp_path):
    deduper = ConceptDeduper(
        "test", graph_store=FakeGraphStore(tmp_path, []),
        embedding_manager=FakeEmbeddingManager(),
    )
    candidates = [
        {"left": "Concept A", "right": "Concept B", "confidence": 0.81, "signals": ["one"], "evidence": []},
        {"left": "concept b", "right": "concept a", "confidence": 0.91, "signals": ["two"], "evidence": []},
    ]

    result = deduper._dedupe_candidate_pairs(candidates)

    assert len(result) == 1
    assert result[0]["confidence"] == 0.91
    assert result[0]["signals"] == ["one", "two"]


def test_merge_review_store_dedupes_reversed_candidate_pairs(tmp_path):
    store = MergeReviewStore(tmp_path)
    run = store.create_waiting_run(
        subject="rag", user_id="user-1", paradigm="engineering", options={},
        candidates=[
            {"left": "Concept A", "right": "Concept B", "confidence": 0.82},
            {"left": "concept b", "right": "concept a", "confidence": 0.93},
        ],
    )

    assert run["total_candidates"] == 1
    assert len(store.list_candidates(run["build_id"])) == 1
    assert store.list_candidates(run["build_id"])[0]["confidence"] == 0.93

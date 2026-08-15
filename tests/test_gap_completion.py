from core.gap_completion_advisor import GapCompletionAdvisor
from core.gap_completion_service import GapCompletionContextBuilder, GapCompletionService
from core.gap_detector import GapCandidate
from core.gap_proposal_store import GapProposalStore
from core.gap_store import GapConflictError, GapStore


class FakeLLM:
    model = "fake-model"
    base_url = "https://example.invalid"

    def __init__(self, response):
        self.response = response

    def chat_json(self, **kwargs):
        return self.response


class SequenceLLM(FakeLLM):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


class FakeGraph:
    def __init__(self):
        self.concepts = {
            "definition-1": {
                "id": "definition-1", "name": "场", "type": "definition",
                "description": "场的定义", "aliases": [], "source_chunks": ["chunk-d"],
            },
            "application-1": {
                "id": "application-1", "name": "场的应用", "type": "application",
                "description": "使用场计算", "aliases": [], "source_chunks": ["chunk-a"],
            },
        }
        self.edges = {("definition-1", "application-1", "APPLIES_TO")}

    def get_canonical_concepts(self, limit=100000):
        return list(self.concepts.values())

    def get_concept_links(self, limit=100000):
        return [
            {"source": source, "target": target, "type": relation}
            for source, target, relation in self.edges
        ]

    def get_canonical_concept(self, canonical_id):
        item = self.concepts.get(canonical_id)
        if not item:
            return None
        return {
            "canonical_id": canonical_id,
            "concept_type": item["type"],
            "name": item["name"],
        }

    def ensure_gap_concept(
        self, *, canonical_id, name, concept_type, description, evidence="",
        aliases=None, source_chunks=None,
    ):
        if canonical_id in self.concepts:
            return self.get_canonical_concept(canonical_id), False
        self.concepts[canonical_id] = {
            "id": canonical_id, "name": name, "type": concept_type,
            "description": description, "aliases": aliases or [],
            "source_chunks": source_chunks or [],
        }
        return self.get_canonical_concept(canonical_id), True

    def ensure_canonical_edge(self, source_id, target_id, relation, confidence=1.0):
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


def make_gap_store(tmp_path, missing_types=("law",)):
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    replacement = ("HAS_LAW", "APPLIES_TO")
    if len(missing_types) == 2:
        replacement = ("HAS_LAW", "APPLIES_TO", "EXTENDS")
    store.reconcile([
        GapCandidate(
            gap_id="gap-1", subject_id="subject-a", paradigm_id="theory",
            source_id="definition-1", target_id="application-1",
            missing_types=missing_types, original_relation="APPLIES_TO",
            replacement_relations=replacement,
            reason="skip", confidence=0.9, detector_version="v1",
        )
    ])
    return store


def base_context():
    return {
        "missing_types": ["law"],
        "chunks": [{
            "chunk_id": "chunk-d",
            "text": "场方程说明场如何随源变化。",
            "metadata": {"source": "lecture.pdf"},
        }],
    }


def valid_response(name="场方程"):
    return {
        "decision": "PROPOSE",
        "concepts": [{
            "slot_index": 0,
            "concept_type": "law",
            "name": name,
            "description": "描述场随源变化的规律。",
            "aliases": ["Field equation"],
            "confidence": 0.88,
            "source_chunk_ids": ["chunk-d"],
            "evidence": [{"chunk_id": "chunk-d", "quote": "场方程说明场如何随源变化。"}],
        }],
        "overall_confidence": 0.86,
        "explanation": "补全定义与应用之间的规律层。",
        "missing_information": [],
        "recommended_search_queries": [],
    }


def test_advisor_accepts_only_whitelisted_verbatim_evidence():
    ready = GapCompletionAdvisor(FakeLLM(valid_response())).advise(base_context())
    assert ready["status"] == "ready"
    assert ready["proposal"]["concepts"][0]["source_chunk_ids"] == ["chunk-d"]

    response = valid_response()
    response["concepts"][0]["evidence"][0]["quote"] = "原文中不存在的引文"
    blocked = GapCompletionAdvisor(FakeLLM(response)).advise(base_context())
    assert blocked["status"] == "needs_external_evidence"
    assert blocked["proposal"]["decision"] == "NEEDS_EXTERNAL_EVIDENCE"


def test_advisor_accepts_unicode_formula_quote_for_equivalent_latex_source():
    context = {
        "missing_types": ["law"],
        "chunks": [{
            "chunk_id": "formula-chunk",
            "text": (
                "These are related by converting using Lorentz transformation matrices: "
                "$$ F ^ {\\mu^ {\\prime} \\nu^ {\\prime}} = F ^ {\\alpha \\beta} "
                "\\Lambda_{\\alpha}^{\\mu^{\\prime}} \\Lambda_{\\beta}^{\\nu^{\\prime}}."
                "\\tag{11.28} $$"
            ),
            "metadata": {},
        }],
    }
    response = valid_response("电磁场张量变换规律")
    response["concepts"][0]["source_chunk_ids"] = ["formula-chunk"]
    response["concepts"][0]["evidence"] = [{
        "chunk_id": "formula-chunk",
        "quote": (
            "These are related by converting using Lorentz transformation matrices: "
            "F^{μ′ν′} = F^{αβ} Λ_α^{μ′} Λ_β^{ν′}."
        ),
    }]

    result = GapCompletionAdvisor(FakeLLM(response)).advise(context)

    assert result["status"] == "ready"
    assert result["evidence"][0]["chunk_id"] == "formula-chunk"


def test_advisor_still_rejects_a_different_formula():
    context = {
        "missing_types": ["law"],
        "chunks": [{"chunk_id": "formula-chunk", "text": "$E = mc^2$", "metadata": {}}],
    }
    response = valid_response("能量关系")
    response["concepts"][0]["source_chunk_ids"] = ["formula-chunk"]
    response["concepts"][0]["evidence"] = [{"chunk_id": "formula-chunk", "quote": "E = mv²"}]

    result = GapCompletionAdvisor(FakeLLM(response)).advise(context)

    assert result["status"] == "needs_external_evidence"


def test_advisor_repairs_a_spliced_quote_with_one_contiguous_llm_quote():
    first = (
        "The Lorentz transformation shows us that space and time are mixed together."
    )
    middle = "Several explanatory sentences occur between the two claims."
    last = "Different inertial observers measure different intervals of time."
    context = {
        "missing_types": ["law"],
        "chunks": [{
            "chunk_id": "lorentz-source",
            "text": f"{first} {middle} {last}",
            "metadata": {},
        }],
    }
    draft = valid_response("洛伦兹变换的时空混合规律")
    draft["concepts"][0]["source_chunk_ids"] = ["lorentz-source"]
    draft["concepts"][0]["evidence"] = [{
        "chunk_id": "lorentz-source",
        "quote": f"{first} {last}",
    }]
    repaired = {
        "concepts": [{
            "slot_index": 0,
            "name": "不得采用的名称修改",
            "evidence": [{"chunk_id": "lorentz-source", "quote": first}],
        }],
    }
    llm = SequenceLLM([draft, repaired])

    result = GapCompletionAdvisor(llm).advise(context)

    assert result["status"] == "ready"
    assert len(llm.calls) == 2
    assert result["proposal"]["concepts"][0]["name"] == "洛伦兹变换的时空混合规律"
    assert result["evidence"][0]["quote"] == first
    assert result["raw_response"]["_evidence_repair"]["accepted"] is True


def test_advisor_keeps_proposal_blocked_when_repaired_quote_is_not_verbatim():
    context = base_context()
    draft = valid_response()
    draft["concepts"][0]["evidence"] = [{
        "chunk_id": "chunk-d", "quote": "并不存在的拼接引文",
    }]
    invalid_repair = {
        "concepts": [{
            "slot_index": 0,
            "evidence": [{"chunk_id": "chunk-d", "quote": "仍然不存在的引文"}],
        }],
    }
    llm = SequenceLLM([draft, invalid_repair])

    result = GapCompletionAdvisor(llm).advise(context)

    assert result["status"] == "needs_external_evidence"
    assert len(llm.calls) == 2
    assert result["raw_response"]["_evidence_repair"]["accepted"] is False


def test_evidence_repair_does_not_replace_an_already_valid_slot():
    context = {
        "missing_types": ["law", "application"],
        "chunks": [
            {"chunk_id": "law-c", "text": "A valid law quote.", "metadata": {}},
            {"chunk_id": "app-c", "text": "A valid application quote.", "metadata": {}},
        ],
    }
    draft = {
        "decision": "PROPOSE",
        "concepts": [
            {
                "concept_type": "law", "name": "规律", "description": "规律描述",
                "source_chunk_ids": ["law-c"],
                "evidence": [{"chunk_id": "law-c", "quote": "A valid law quote."}],
            },
            {
                "concept_type": "application", "name": "应用", "description": "应用描述",
                "source_chunk_ids": ["app-c"],
                "evidence": [{"chunk_id": "app-c", "quote": "A fabricated quote."}],
            },
        ],
        "overall_confidence": 0.8,
    }
    repair = {
        "concepts": [
            {
                "slot_index": 0,
                "evidence": [{"chunk_id": "law-c", "quote": "Not in the source."}],
            },
            {
                "slot_index": 1,
                "evidence": [{"chunk_id": "app-c", "quote": "A valid application quote."}],
            },
        ],
    }

    result = GapCompletionAdvisor(SequenceLLM([draft, repair])).advise(context)

    assert result["status"] == "ready"
    assert result["proposal"]["concepts"][0]["evidence"][0]["quote"] == "A valid law quote."
    assert result["proposal"]["concepts"][1]["evidence"][0]["quote"] == "A valid application quote."


def test_advisor_separates_evidence_from_description_and_builds_fallback_query():
    context = {
        **base_context(),
        "source_concept": {"name": "检索增强生成", "aliases": ["RAG"]},
        "target_concept": {"name": "生成器模块", "aliases": ["Generator"]},
        "paradigm": {"types": {"law": "规律"}},
    }
    response = valid_response()
    response["concepts"][0]["description"] = (
        "描述场随源变化的规律。 Evidence: [chunk-d] 场方程说明场如何随源变化。"
    )
    response["concepts"][0]["evidence"] = []
    response["recommended_search_queries"] = []

    result = GapCompletionAdvisor(FakeLLM(response)).advise(context)

    assert result["proposal"]["concepts"][0]["description"] == "描述场随源变化的规律。"
    assert result["status"] == "needs_external_evidence"
    assert result["proposal"]["recommended_search_queries"]
    assert "RAG" in result["proposal"]["recommended_search_queries"][0]


def test_advisor_preserves_multi_layer_slot_order():
    context = {
        "missing_types": ["law", "application"],
        "chunks": [
            {"chunk_id": "law-c", "text": "该规律说明定义之间的约束。", "metadata": {}},
            {"chunk_id": "app-c", "text": "该方法用于具体测量。", "metadata": {}},
        ],
    }
    response = {
        "decision": "PROPOSE",
        "concepts": [
            {
                "concept_type": "law", "name": "约束规律", "description": "规律描述",
                "confidence": .8, "source_chunk_ids": ["law-c"],
                "evidence": [{"chunk_id": "law-c", "quote": "该规律说明定义之间的约束。"}],
            },
            {
                "concept_type": "application", "name": "测量应用", "description": "应用描述",
                "confidence": .75, "source_chunk_ids": ["app-c"],
                "evidence": [{"chunk_id": "app-c", "quote": "该方法用于具体测量。"}],
            },
        ],
        "overall_confidence": .77,
    }
    result = GapCompletionAdvisor(FakeLLM(response)).advise(context)

    assert result["status"] == "ready"
    assert [item["concept_type"] for item in result["proposal"]["concepts"]] == [
        "law", "application",
    ]


def test_proposal_store_supersedes_previous_attempt_and_checks_gap_version(tmp_path):
    gap_store = make_gap_store(tmp_path)
    proposals = GapProposalStore(gap_store.db_path, "subject-a")
    first = proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")
    second = proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")

    assert proposals.require(first["proposal_id"])["status"] == "superseded"
    assert second["status"] == "generating"
    gap_store.ignore("gap-1", acted_by="owner", expected_version=1)
    try:
        proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")
        assert False, "stale proposal creation must fail"
    except GapConflictError:
        pass


def test_imported_external_chunk_is_forced_into_regenerated_context(tmp_path):
    gap_store = make_gap_store(tmp_path)
    proposals = GapProposalStore(gap_store.db_path, "subject-a")
    graph = FakeGraph()
    chunks = {
        "external-proof": {
            "id": "external-proof",
            "text": "外部摘要逐字说明场方程连接定义与应用。",
            "metadata": {"source_kind": "external_academic"},
        },
    }
    response = valid_response()
    response["concepts"][0]["source_chunk_ids"] = ["external-proof"]
    response["concepts"][0]["evidence"] = [{
        "chunk_id": "external-proof",
        "quote": "外部摘要逐字说明场方程连接定义与应用。",
    }]
    service = GapCompletionService(
        gap_store=gap_store,
        proposal_store=proposals,
        graph_store=graph,
        advisor=GapCompletionAdvisor(FakeLLM(response)),
        context_builder=GapCompletionContextBuilder(
            graph,
            source_loader=lambda ids: [chunks[item] for item in ids if item in chunks],
        ),
    )
    created = proposals.create(
        gap_id="gap-1",
        gap_version=1,
        created_by="owner",
        source_recommendations=[{
            "status": "imported",
            "chunk_id": "external-proof",
            "title": "Reviewed paper",
        }],
    )

    generated = service.generate(created["proposal_id"], {"types": {"law": "规律"}})

    assert generated["status"] == "ready"
    assert generated["evidence"][0]["chunk_id"] == "external-proof"
    assert generated["source_recommendations"][0]["status"] == "imported"


def test_new_external_search_keeps_already_imported_evidence(tmp_path):
    gap_store = make_gap_store(tmp_path)
    proposals = GapProposalStore(gap_store.db_path, "subject-a")
    created = proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")
    proposals.save_result(
        created["proposal_id"], status="needs_external_evidence",
        proposal={}, evidence=[], duplicate_candidates=[],
        source_recommendations=[{
            "status": "imported", "result_id": "imported-1",
            "chunk_id": "external-proof", "title": "Imported paper",
            "abstract": "Already stored evidence.", "evidence_ready": True,
        }],
        input_hash="h", prompt_version="v", model="m", provider="p",
        raw_response={},
    )

    updated = proposals.save_source_recommendations(
        created["proposal_id"],
        [{"result_id": "new-1", "title": "New candidate", "abstract": "Candidate"}],
    )

    assert [item["result_id"] for item in updated["source_recommendations"]] == [
        "imported-1", "new-1",
    ]


def test_proposal_history_and_external_evidence_deactivation_are_auditable(tmp_path):
    gap_store = make_gap_store(tmp_path)
    proposals = GapProposalStore(gap_store.db_path, "subject-a")
    first = proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")
    proposals.save_result(
        first["proposal_id"], status="needs_external_evidence",
        proposal={}, evidence=[], duplicate_candidates=[],
        source_recommendations=[{
            "status": "imported", "result_id": "paper-1",
            "chunk_id": "external-proof", "chunk_ids": ["external-proof", "external-proof-2"],
        }],
        input_hash="h", prompt_version="v", model="m", provider="p", raw_response={},
    )

    updated = proposals.update_source_status(
        first["proposal_id"], chunk_id="external-proof", status="deactivated", acted_by="owner",
    )
    second = proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")
    history = proposals.list_for_gap("gap-1")

    assert updated["source_recommendations"][0]["status"] == "deactivated"
    assert updated["source_recommendations"][0]["status_changed_by"] == "owner"
    assert history["total"] == 2
    assert history["items"][0]["proposal_id"] == second["proposal_id"]
    assert history["items"][1]["source_recommendations"][0]["status"] == "deactivated"


def test_generation_and_reviewed_acceptance_preserve_source_chunks(tmp_path):
    gap_store = make_gap_store(tmp_path)
    proposals = GapProposalStore(gap_store.db_path, "subject-a")
    graph = FakeGraph()
    chunks = {
        "chunk-d": {"id": "chunk-d", "text": "场方程说明场如何随源变化。", "metadata": {}},
        "chunk-a": {"id": "chunk-a", "text": "场被用于计算。", "metadata": {}},
    }
    context_builder = GapCompletionContextBuilder(
        graph,
        source_loader=lambda ids: [chunks[item] for item in ids if item in chunks],
    )
    service = GapCompletionService(
        gap_store=gap_store,
        proposal_store=proposals,
        graph_store=graph,
        advisor=GapCompletionAdvisor(FakeLLM(valid_response())),
        context_builder=context_builder,
    )
    proposal = proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")
    generated = service.generate(proposal["proposal_id"], {
        "name": "理论归纳", "types": {"law": "规律"},
        "ideal_chain": ["definition", "law", "application"],
        "relation_map": {},
    })
    accepted = service.accept(
        proposal["proposal_id"], acted_by="owner", expected_gap_version=1
    )

    assert generated["status"] == "ready"
    assert accepted["gap"]["status"] == "supplemented"
    created_id = accepted["gap"]["supplemented_by"][0]
    assert graph.concepts[created_id]["source_chunks"] == ["chunk-d"]
    assert proposals.require(proposal["proposal_id"])["status"] == "accepted"


def test_exact_alias_match_reuses_existing_concept(tmp_path):
    gap_store = make_gap_store(tmp_path)
    proposals = GapProposalStore(gap_store.db_path, "subject-a")
    graph = FakeGraph()
    graph.concepts["law-existing"] = {
        "id": "law-existing", "name": "场规律", "type": "law",
        "description": "既有描述", "aliases": ["Field equation"],
        "source_chunks": ["chunk-d"],
    }
    context_builder = GapCompletionContextBuilder(
        graph,
        source_loader=lambda ids: [{
            "id": "chunk-d", "text": "场方程说明场如何随源变化。", "metadata": {},
        }],
    )
    service = GapCompletionService(
        gap_store=gap_store, proposal_store=proposals, graph_store=graph,
        advisor=GapCompletionAdvisor(FakeLLM(valid_response())),
        context_builder=context_builder,
    )
    created = proposals.create(gap_id="gap-1", gap_version=1, created_by="owner")
    ready = service.generate(created["proposal_id"], {"types": {"law": "规律"}})
    concept = ready["proposal"]["concepts"][0]

    assert concept["canonical_id"] == "law-existing"
    assert concept["existing_match"]["confidence"] == 1.0

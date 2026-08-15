from core.concept_merge_advisor import ConceptMergeAdvisor, detect_advice_conflicts
from core.merge_review_store import MergeReviewStore


class FakeLLM:
    model = "fake-merge-model"

    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class SequencedFakeLLM(FakeLLM):
    def __init__(self, responses):
        super().__init__(responses[0])
        self.responses = list(responses)

    def chat_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def candidate(candidate_id="merge_1", left="RAG", right="检索增强生成"):
    return {
        "candidate_id": candidate_id,
        "left": left,
        "right": right,
        "left_profile": {
            "name": left, "types": {"technology": 1}, "aliases": [],
            "descriptions": ["结合检索结果生成答案"], "source_chunks": ["chunk_left"],
            "occurrences": 1,
        },
        "right_profile": {
            "name": right, "types": {"technology": 1}, "aliases": ["RAG"],
            "descriptions": ["先检索外部知识，再由模型生成答案"], "source_chunks": ["chunk_right"],
            "occurrences": 1,
        },
        "relation": "SAME_AS",
        "confidence": 0.86,
        "signals": ["name_embedding:0.86"],
        "evidence": [],
    }


def test_advisor_returns_auditable_non_binding_recommendation():
    item = candidate()
    llm = FakeLLM({"results": [{
        "candidate_id": item["candidate_id"],
        "decision": "MERGE",
        "confidence": 0.96,
        "canonical_name": "检索增强生成",
        "relation_if_separate": "NONE",
        "reason": "两者定义一致，RAG 是标准缩写。",
        "supporting_chunk_ids": ["chunk_left", "unknown"],
        "conflicts": [],
        "needs_more_context": False,
    }]})
    source_docs = {
        "chunk_left": {"id": "chunk_left", "text": "left context", "metadata": {"page": 1}},
        "chunk_right": {"id": "chunk_right", "text": "right context", "metadata": {"page": 2}},
    }
    advisor = ConceptMergeAdvisor(
        llm_client=llm,
        source_loader=lambda ids: [source_docs[item] for item in ids if item in source_docs],
    )

    result = advisor.advise([item], "engineering")[0]

    assert result["status"] == "ready"
    assert result["advisor"]["decision"] == "MERGE"
    assert result["advisor"]["canonical_name"] == "检索增强生成"
    assert result["advisor"]["supporting_chunk_ids"] == ["chunk_left"]
    assert len(result["input_hash"]) == 64
    assert result["prompt_version"] == "concept-merge-advisor-v1"
    assert "left context" in llm.calls[0]["messages"][0]["content"]


def test_invalid_merge_name_is_downgraded_to_uncertain():
    item = candidate()
    llm = FakeLLM({"results": [{
        "candidate_id": item["candidate_id"], "decision": "MERGE", "confidence": 0.99,
        "canonical_name": "new invented name", "reason": "same",
    }]})

    result = ConceptMergeAdvisor(llm_client=llm).advise([item], "engineering")[0]

    assert result["advisor"]["decision"] == "UNCERTAIN"
    assert result["advisor"]["confidence"] <= 0.49
    assert result["advisor"]["conflicts"]


def test_disagreeing_independent_verification_blocks_merge():
    item = candidate()
    initial = {"results": [{
        "candidate_id": item["candidate_id"], "decision": "MERGE", "confidence": 0.97,
        "canonical_name": "检索增强生成", "reason": "定义一致",
        "supporting_chunk_ids": ["chunk_left"],
    }]}
    verification = {"results": [{
        "candidate_id": item["candidate_id"], "decision": "SEPARATE", "confidence": 0.82,
        "reason": "范围不同",
    }]}

    result = ConceptMergeAdvisor(
        llm_client=SequencedFakeLLM([initial, verification]),
    ).advise([item], "engineering")[0]

    assert result["advisor"]["decision"] == "UNCERTAIN"
    assert result["advisor"]["needs_more_context"] is True
    assert "两次独立判断不一致" in result["advisor"]["conflicts"][-1]


def test_transitive_merge_conflict_is_detected():
    items = [
        {**candidate("ab", "A", "B"), "advisor": {"decision": "MERGE"}},
        {**candidate("bc", "B", "C"), "advisor": {"decision": "MERGE"}},
        {**candidate("ac", "A", "C"), "advisor": {"decision": "SEPARATE"}},
    ]

    conflicts = detect_advice_conflicts(items)

    assert set(conflicts) == {"ab", "bc", "ac"}
    assert len(set(conflicts.values())) == 1


def test_store_keeps_advice_separate_and_accepts_only_safe_high_confidence(tmp_path):
    store = MergeReviewStore(tmp_path)
    run = store.create_waiting_run(
        subject="rag", user_id="user-1", paradigm="engineering", options={},
        candidates=[candidate()],
    )
    item = store.list_candidates(run["build_id"])[0]
    store.save_advice(run["build_id"], [{
        "candidate_id": item["candidate_id"], "status": "ready",
        "advisor": {
            "decision": "MERGE", "confidence": 0.97,
            "canonical_name": "检索增强生成", "relation_if_separate": "NONE",
            "reason": "定义一致", "supporting_chunk_ids": [], "conflicts": [],
            "needs_more_context": False,
        },
        "input_hash": "hash", "prompt_version": "v1", "model": "fake",
        "raw_response": {"decision": "MERGE"},
    }])

    advised = store.list_candidates(run["build_id"])[0]
    assert advised["decision"] is None
    assert advised["advisor"]["decision"] == "MERGE"

    accepted = store.accept_high_confidence_advice(run["build_id"], threshold=0.9)
    assert len(accepted) == 1
    assert store.list_candidates(run["build_id"])[0]["decision"] == "merge"

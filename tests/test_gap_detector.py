import re

import pytest
import yaml

from config.settings import PROJECT_ROOT
from core.gap_detector import GapDetector


@pytest.fixture(scope="module")
def paradigms():
    path = PROJECT_ROOT / "config" / "paradigms.yaml"
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["paradigms"]


def detect(detector, paradigm_id, config, nodes, edges, **kwargs):
    return detector.detect(
        subject_id="subject-a",
        paradigm_id=paradigm_id,
        paradigm_config=config,
        nodes=nodes,
        edges=edges,
        **kwargs,
    )


def test_theory_adjacent_connection_has_no_gap(paradigms):
    result = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"definition-1": "definition", "law-1": "law"},
        [{"parent_id": "definition-1", "child_id": "law-1", "relation_type": "HAS_LAW"}],
    )

    assert result.candidates == ()
    assert result.diagnostics == ()


def test_theory_single_level_skip(paradigms):
    result = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"definition-1": "definition", "application-1": "application"},
        [{"source_id": "definition-1", "target_id": "application-1", "relation": "APPLIES_TO"}],
    )

    assert len(result.candidates) == 1
    gap = result.candidates[0]
    assert gap.missing_types == ("law",)
    assert gap.replacement_relations == ("HAS_LAW", "APPLIES_TO")
    assert gap.original_relation == "APPLIES_TO"
    assert gap.confidence == 1.0


def test_theory_multi_level_skip_preserves_chain_order(paradigms):
    result = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"definition-1": "definition", "extension-1": "extension"},
        [{"source_id": "definition-1", "target_id": "extension-1", "relation": "EXTENDS"}],
    )

    gap = result.candidates[0]
    assert gap.missing_types == ("law", "application")
    assert gap.replacement_relations == ("HAS_LAW", "APPLIES_TO", "EXTENDS")


@pytest.mark.parametrize(
    ("concept_type", "missing_type", "relations"),
    [
        ("requirement", "technology", ("IMPLEMENTS", "DEPEND_ON")),
        ("technology", "requirement", ("DEPEND_ON", "IMPLEMENTS")),
    ],
)
def test_engineering_same_type_connection_is_alternating_gap(
    paradigms, concept_type, missing_type, relations
):
    result = detect(
        GapDetector(),
        "engineering",
        paradigms["engineering"],
        {"a": concept_type, "b": concept_type},
        [{"source_id": "a", "target_id": "b", "relation_type": "DEPEND_ON"}],
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].missing_types == (missing_type,)
    assert result.candidates[0].replacement_relations == relations


def test_engineering_adjacent_alternating_types_have_no_gap(paradigms):
    result = detect(
        GapDetector(),
        "engineering",
        paradigms["engineering"],
        {"r": "requirement", "t": "technology"},
        [{"source_id": "r", "target_id": "t", "relation_type": "IMPLEMENTS"}],
    )

    assert result.candidates == ()


def test_repeated_and_duplicate_detection_has_one_stable_id(paradigms):
    detector = GapDetector()
    nodes = {"d": "definition", "a": "application"}
    edge = {"source_id": "d", "target_id": "a", "relation": "APPLIES_TO"}

    first = detect(detector, "theory", paradigms["theory"], nodes, [edge, edge])
    second = detect(detector, "theory", paradigms["theory"], nodes, [edge])

    assert len(first.candidates) == 1
    assert first.candidates[0].gap_id == second.candidates[0].gap_id
    assert re.fullmatch(r"gap_[0-9a-f]{64}", first.candidates[0].gap_id)


def test_detector_version_is_part_of_stable_id(paradigms):
    nodes = {"d": "definition", "a": "application"}
    edges = [{"source_id": "d", "target_id": "a"}]

    first = detect(GapDetector("v1"), "theory", paradigms["theory"], nodes, edges)
    second = detect(GapDetector("v2"), "theory", paradigms["theory"], nodes, edges)

    assert first.candidates[0].gap_id != second.candidates[0].gap_id


def test_illegal_direction_is_diagnostic_not_candidate(paradigms):
    result = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"law-1": "law", "definition-1": "definition"},
        [{"source_id": "law-1", "target_id": "definition-1"}],
        detect_root_gaps=False,
    )

    assert result.candidates == ()
    assert [item.code for item in result.diagnostics] == ["illegal_direction"]


def test_unknown_endpoint_and_self_loop_are_diagnostics(paradigms):
    result = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"definition-1": "definition"},
        [
            {"source_id": "definition-1", "target_id": "missing"},
            {"source_id": "definition-1", "target_id": "definition-1"},
        ],
        detect_root_gaps=False,
    )

    assert result.candidates == ()
    assert [item.code for item in result.diagnostics] == ["unknown_endpoint", "self_loop"]


def test_legal_root_is_not_gap_but_non_root_without_parent_is(paradigms):
    legal = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"d": "definition"},
        [],
    )
    missing_parent = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"a": "application"},
        [],
    )

    assert legal.candidates == ()
    assert missing_parent.candidates[0].source_id is None
    assert missing_parent.candidates[0].target_id == "a"
    assert missing_parent.candidates[0].missing_types == ("definition", "law")


@pytest.mark.parametrize(
    "bad_config",
    [
        {"cyclic": False, "ideal_chain": ["only"]},
        {"cyclic": False, "ideal_chain": ["a", "a"]},
        {"cyclic": True, "cycle_pattern": ["only"]},
    ],
)
def test_invalid_paradigm_configuration_is_rejected(bad_config):
    with pytest.raises(ValueError):
        detect(GapDetector(), "custom", bad_config, {}, [])


def test_candidate_is_json_friendly(paradigms):
    result = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"d": "definition", "a": "application"},
        [{"source_id": "d", "target_id": "a"}],
    )

    assert result.candidates[0].as_dict()["missing_types"] == ["law"]


def test_graph_store_edge_shape_preserves_original_relation(paradigms):
    result = detect(
        GapDetector(),
        "theory",
        paradigms["theory"],
        {"d": "definition", "a": "application"},
        [{"source": "d", "target": "a", "type": "APPLIES_TO"}],
    )

    assert result.candidates[0].original_relation == "APPLIES_TO"

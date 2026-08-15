"""Characterization tests for the pre-GapRecord virtual-node implementation.

These tests intentionally freeze migration-relevant behavior.  They are not an
endorsement of writing virtual concepts to KuzuDB; M3 will migrate them.
"""

import re

from core.semantic_linker import SemanticLinker


def test_legacy_virtual_node_ids_are_random_and_recognisable():
    linker = SemanticLinker.__new__(SemanticLinker)

    first = linker._create_virtual_node_id("concept_canonical_parent", "concept_canonical_child", "law")
    second = linker._create_virtual_node_id("concept_canonical_parent", "concept_canonical_child", "law")

    assert first != second
    assert re.fullmatch(r"__virtual_[0-9a-f]{8}_law_parent_child", first)


def test_legacy_gap_calculation_supports_only_one_linear_virtual_layer():
    linker = SemanticLinker.__new__(SemanticLinker)
    config = {"cyclic": False, "ideal_chain": ["definition", "law", "application", "extension"]}

    assert linker._calculate_gap("definition", "extension", config) == 2
    assert linker._infer_missing_type("definition", "extension", config) is None

from dataclasses import replace

import pytest

from core.gap_detector import GapCandidate
from core.gap_store import GapConflictError, GapStore


def candidate(gap_id="gap_1", *, missing_types=("law",), detector_version="v1"):
    return GapCandidate(
        gap_id=gap_id,
        subject_id="subject-a",
        paradigm_id="theory",
        source_id="definition-1",
        target_id="application-1",
        missing_types=missing_types,
        original_relation="APPLIES_TO",
        replacement_relations=("HAS_LAW", "APPLIES_TO"),
        reason="skipped law",
        confidence=1.0,
        detector_version=detector_version,
    )


def test_reconcile_upserts_lists_summarises_and_obsoletes(tmp_path):
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")

    first = store.reconcile([candidate(), candidate()])
    assert first.as_dict() == {
        "detected": 1, "created": 1, "refreshed": 0, "reopened": 0, "obsolete": 0
    }
    assert store.list()["total"] == 1
    assert store.summary()["by_status"]["open"] == 1
    assert store.summary()["open_by_missing_type"] == {"law": 1}

    second = store.reconcile([])
    assert second.obsolete == 1
    assert store.require("gap_1")["status"] == "obsolete"

    third = store.reconcile([candidate(detector_version="v2")])
    assert third.reopened == 1
    record = store.require("gap_1")
    assert record["status"] == "open"
    assert record["detector_version"] == "v2"


def test_ignored_gap_stays_ignored_across_reconcile(tmp_path):
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    store.reconcile([candidate()])
    ignored = store.ignore("gap_1", acted_by="owner", expected_version=1)

    store.reconcile([])
    assert store.require("gap_1")["status"] == "ignored"
    store.reconcile([candidate()])
    assert store.require("gap_1")["status"] == "ignored"

    reopened = store.reopen(
        "gap_1", acted_by="owner", expected_version=ignored["version"] + 1
    )
    assert reopened["status"] == "open"


def test_optimistic_version_rejects_concurrent_transition(tmp_path):
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    store.reconcile([candidate()])
    store.ignore("gap_1", acted_by="owner", expected_version=1)

    with pytest.raises(GapConflictError):
        store.ignore("gap_1", acted_by="maintainer", expected_version=1)


def test_candidate_subject_cannot_cross_store_boundary(tmp_path):
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    with pytest.raises(ValueError):
        store.reconcile([replace(candidate(), subject_id="other")])


def test_import_candidates_does_not_obsolete_or_reopen_ignored_records(tmp_path):
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    store.reconcile([candidate("existing"), candidate("ignored")])
    store.ignore("ignored", acted_by="owner", expected_version=1)

    imported = store.import_candidates([candidate("migrated")])
    assert imported.created == 1
    assert store.require("existing")["status"] == "open"
    assert store.require("ignored")["status"] == "ignored"

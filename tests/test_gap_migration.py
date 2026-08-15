from core.gap_migration import LegacyGapMigrator
from core.gap_store import GapStore


class FakeMigrationGraph:
    def __init__(self, *, natural=False, ambiguous=False):
        self.deleted = []
        self.nodes = [
            {"id": "definition-1", "type": "definition"},
            {"id": "application-1", "type": "application"},
        ]
        self.edges = []
        if natural:
            self.nodes.append({"id": "law-real", "type": "law"})
            self.edges.extend([
                {"source": "definition-1", "target": "law-real", "type": "HAS_LAW"},
                {"source": "law-real", "target": "application-1", "type": "APPLIES_TO"},
            ])
        incoming = [
            {"source": "definition-1", "target": "__virtual_old", "type": "HAS_LAW", "confidence": 0.8}
        ]
        if ambiguous:
            incoming.append(
                {"source": "definition-2", "target": "__virtual_old", "type": "HAS_LAW", "confidence": 0.8}
            )
        self.legacy = [{
            "id": "__virtual_old", "type": "law", "is_virtual": True,
            "incoming": incoming,
            "outgoing": [{
                "source": "__virtual_old", "target": "application-1",
                "type": "APPLIES_TO", "confidence": 0.7,
            }],
        }]

    def inspect_legacy_virtual_concepts(self):
        return self.legacy

    def get_canonical_concepts(self, limit=100000):
        return self.nodes

    def get_concept_links(self, limit=100000):
        return self.edges

    def delete_legacy_virtual_concepts(self, ids):
        self.deleted.extend(ids)
        return len(ids)


CONFIG = {
    "relation_map": {
        "definition": {"HAS_LAW": ["law"], "APPLIES_TO": ["application"]},
        "law": {"APPLIES_TO": ["application"]},
    }
}


def migrate(graph, store, *, dry_run):
    return LegacyGapMigrator(graph, store).migrate(
        subject_id="subject-a", paradigm_id="theory",
        paradigm_config=CONFIG, detector_version="migration-v1", dry_run=dry_run,
    )


def test_migration_dry_run_is_read_only_then_live_run_is_idempotent(tmp_path):
    graph = FakeMigrationGraph()
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")

    preview = migrate(graph, store, dry_run=True)
    assert preview.found == preview.migratable == 1
    assert preview.deleted == 0
    assert store.list(status=None)["total"] == 0

    applied = migrate(graph, store, dry_run=False)
    assert applied.records_created == applied.deleted == 1
    assert graph.deleted == ["__virtual_old"]
    record = store.list()["items"][0]
    assert record["source_id"] == "definition-1"
    assert record["target_id"] == "application-1"
    assert record["missing_types"] == ["law"]

    # Reopening the SQLite file simulates a desktop/backend restart.
    restarted = GapStore(tmp_path / "gap_flow.db", "subject-a")
    assert restarted.require(record["gap_id"])["status"] == "open"


def test_naturally_filled_legacy_node_is_cleaned_without_open_gap(tmp_path):
    graph = FakeMigrationGraph(natural=True)
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    report = migrate(graph, store, dry_run=False)
    assert report.naturally_filled == 1
    assert report.records_created == 0
    assert report.deleted == 1


def test_ambiguous_legacy_node_is_reported_and_preserved(tmp_path):
    graph = FakeMigrationGraph(ambiguous=True)
    store = GapStore(tmp_path / "gap_flow.db", "subject-a")
    report = migrate(graph, store, dry_run=False)
    assert report.skipped == 1
    assert report.deleted == 0
    assert graph.deleted == []

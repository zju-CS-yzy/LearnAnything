from core.gap_migration import LegacyGapMigrator
from core.gap_store import GapStore
from core.graph_store import GraphStore


def test_real_kuzu_migration_filters_pagerank_and_deletes_legacy_node(tmp_path):
    graph_path = tmp_path / "subject-a" / "graph" / "graph"
    graph = GraphStore("subject-a_v1", db_path=str(graph_path))
    graph.init_schema()
    conn = graph._ensure_db()
    for node_id, name, concept_type, is_virtual in (
        ("definition-1", "Definition", "definition", "false"),
        ("application-1", "Application", "application", "false"),
        ("__virtual_old", "Missing law", "law", "true"),
    ):
        graph._execute(conn, f"""
            CREATE (c:CanonicalConcept {{
                canonical_id: '{node_id}', name: '{name}', concept_type: '{concept_type}',
                description: '', parent_hint: '', aliases: '[]', source_chunks: '[]',
                type_votes: '{{}}', media_refs: '[]', is_virtual: {is_virtual}
            }})
        """)
    graph._execute(conn, """
        MATCH (a:CanonicalConcept {canonical_id: 'definition-1'}),
              (v:CanonicalConcept {canonical_id: '__virtual_old'})
        CREATE (a)-[:HAS_DETAIL {confidence: 0.8}]->(v)
    """)
    graph._execute(conn, """
        MATCH (v:CanonicalConcept {canonical_id: '__virtual_old'}),
              (b:CanonicalConcept {canonical_id: 'application-1'})
        CREATE (v)-[:HAS_DETAIL {confidence: 0.7}]->(b)
    """)

    assert {node["id"] for node in graph.get_canonical_concepts()} == {
        "definition-1", "application-1"
    }
    assert graph.get_concept_links() == []
    assert set(graph.compute_and_cache_centrality()) == {"definition-1", "application-1"}

    store = GapStore(tmp_path / "subject-a" / "gap_flow.db", "subject-a")
    report = LegacyGapMigrator(graph, store).migrate(
        subject_id="subject-a", paradigm_id="theory",
        paradigm_config={"relation_map": {}}, detector_version="migration-v1",
        dry_run=False,
    )
    assert report.records_created == report.deleted == 1
    assert graph.inspect_legacy_virtual_concepts() == []
    assert store.list()["total"] == 1
    graph.close()


def test_real_kuzu_limits_count_only_real_concepts(tmp_path):
    graph_path = tmp_path / "subject-limit" / "graph" / "graph"
    graph = GraphStore("subject-limit_v1", db_path=str(graph_path))
    graph.init_schema()
    conn = graph._ensure_db()
    for index, is_virtual in enumerate(("true", "true", "false", "false")):
        node_id = f"__virtual_{index}" if is_virtual == "true" else f"real-{index}"
        graph._execute(conn, f"""
            CREATE (c:CanonicalConcept {{
                canonical_id: '{node_id}', name: '{node_id}', concept_type: 'law',
                description: '', parent_hint: '', aliases: '[]', source_chunks: '[]',
                type_votes: '{{}}', media_refs: '[]', is_virtual: {is_virtual}
            }})
        """)
    result = graph.get_canonical_concepts(limit=1)
    assert len(result) == 1
    assert result[0]["id"].startswith("real-")
    graph.close()


def test_real_kuzu_none_limit_returns_complete_real_graph(tmp_path):
    graph_path = tmp_path / "subject-unbounded" / "graph" / "graph"
    graph = GraphStore("subject-unbounded_v1", db_path=str(graph_path))
    graph.init_schema()
    conn = graph._ensure_db()
    for index in range(3):
        graph._execute(conn, f"""
            CREATE (c:CanonicalConcept {{
                canonical_id: 'real-{index}', name: 'real-{index}', concept_type: 'law',
                description: '', parent_hint: '', aliases: '[]', source_chunks: '[]',
                type_votes: '{{}}', media_refs: '[]', is_virtual: false
            }})
        """)
    graph._execute(conn, """
        MATCH (a:CanonicalConcept {canonical_id: 'real-0'}),
              (b:CanonicalConcept {canonical_id: 'real-1'}),
              (c:CanonicalConcept {canonical_id: 'real-2'})
        CREATE (a)-[:HAS_LAW {confidence: 1.0}]->(b),
               (b)-[:HAS_LAW {confidence: 1.0}]->(c)
    """)

    assert len(graph.get_canonical_concepts(limit=None)) == 3
    assert len(graph.get_concept_links(limit=None)) == 2
    graph.close()

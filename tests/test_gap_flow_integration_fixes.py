import sqlite3

from core.markdown_chunker import MarkdownChunker
from core.mineru_client import MinerUClient
from core.graph_store import GraphStore
from core.graph_builder import GraphBuilder
from core.vector_store import VectorStore
from core.semantic_linker import SemanticLinker, _build_paradigm_config
from core.subject_manager import SubjectManager


def test_subject_manager_persists_paradigm_with_schema_migration(tmp_path):
    db_path = tmp_path / "subjects.db"
    manager = SubjectManager(db_path=str(db_path))
    manager.create_subject("physics", "Physics", owner_id="owner", visibility="private")

    assert manager.set_paradigm("physics", "theory") is True
    assert manager.get_subject("physics")["paradigm"] == "theory"

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(subjects)")}
    assert "paradigm" in columns


def test_numbered_questions_become_heading_tree_only_without_markdown_headings():
    markdown = """1 介绍一下 FFN 块 计算公式？

$$FFN(x)=xW_1W_2$$

2 介绍一下 GeLU 计算公式？

$$GeLU(x)=x\\Phi(x)$$
"""
    chunks = MarkdownChunker().chunk_markdown(
        markdown, {"source": "activation.pdf", "subject": "llm"}
    )
    headings = [c for c in chunks if c["metadata"]["chunk_type"] == "heading"]

    assert [c["metadata"]["heading_path"] for c in headings] == [
        "1 介绍一下 FFN 块 计算公式？",
        "2 介绍一下 GeLU 计算公式？",
    ]
    assert all(c["metadata"]["parent_id"] for c in chunks if c["metadata"]["chunk_type"] == "paragraph")


def test_unreferenced_formula_image_inherits_heading_anchor_metadata():
    chunks = [
        {
            "id": "heading-gelu",
            "text": "## GeLU\n$$GeLU(x) = x Phi(x)$$",
            "metadata": {
                "chunk_type": "heading",
                "heading_path": "2 GeLU",
                "heading_level": 2,
                "source": "activation.pdf",
                "page_number": 2,
            },
        },
        {
            "id": "heading-swish",
            "text": "## Swish\n$$Swish(x) = x sigmoid(x)$$",
            "metadata": {
                "chunk_type": "heading",
                "heading_path": "3 Swish",
                "heading_level": 2,
                "source": "activation.pdf",
                "page_number": 3,
            },
        },
    ]
    client = object.__new__(MinerUClient)
    anchor = client._match_image_anchor(
        text="GeLU(x)=x Phi(x)",
        is_formula=True,
        image_index=0,
        image_count=2,
        chunks=chunks,
    )

    assert anchor["id"] == "heading-gelu"
    assert anchor["metadata"]["heading_path"] == "2 GeLU"


def test_legacy_image_source_name_still_builds_document_membership(tmp_path):
    store = GraphStore("legacy-images", db_path=str(tmp_path / "graph" / "graph"))
    try:
        store.init_schema()
        store.add_chunk_nodes([
            {
                "id": "doc",
                "text": "[document]",
                "metadata": {
                    "chunk_type": "document",
                    "source": "legacy.pdf",
                    "heading_path": "",
                },
            },
            {
                "id": "image",
                "text": "[formula] x+y",
                "metadata": {
                    "chunk_type": "image_pseudo",
                    "source_name": "legacy.pdf",
                    "heading_path": "",
                },
            },
        ])
        assert store.build_belongs_to_relations() == 1
        result = store._execute(
            store._ensure_db(),
            "MATCH (a:Chunk)-[:BELONGS_TO]->(b:Chunk) RETURN a.chunk_id, b.chunk_id",
        )
        assert result.has_next()
        assert result.get_next() == ["doc", "image"]
    finally:
        store.close()


def test_force_rebuild_refreshes_saved_markdown_and_reanchors_images(tmp_path):
    subject_dir = tmp_path / "subject"
    md_dir = subject_dir / "md"
    md_dir.mkdir(parents=True)
    (md_dir / "activation.md").write_text(
        "1 介绍一下 FFN 计算公式？\n\n$$FFN(x)=xW$$\n\n"
        "2 介绍一下 GeLU 计算公式？\n\n$$GeLU(x)=xPhi(x)$$",
        encoding="utf-8",
    )

    vector = VectorStore("activation", db_path=str(subject_dir / "vector.db"))

    class FakeEmbedding:
        def embed(self, texts):
            return [[0.0] for _ in texts]

    vector._embedding = FakeEmbedding()
    vector.add_documents([
        {
            "id": "old-doc",
            "text": "old document",
            "metadata": {"chunk_type": "document", "source": "activation.pdf"},
        },
        {
            "id": "old-image",
            "text": "[formula] GeLU(x)=xPhi(x)",
            "metadata": {
                "chunk_type": "image_pseudo",
                "source_name": "activation.pdf",
                "is_formula_image": True,
                "media_refs": [{"type": "image", "path": "formula.png"}],
            },
        },
    ])

    class DataDirOnlyGraphStore:
        data_dir = subject_dir

    builder = object.__new__(GraphBuilder)
    builder.vector_store = vector
    builder.graph_store = DataDirOnlyGraphStore()
    try:
        assert builder._refresh_saved_markdown_structure() == {
            "documents": 1,
            "chunks": 6,
        }
        rows = vector.list_all(limit=100)
        headings = [r for r in rows if r["metadata"].get("chunk_type") == "heading"]
        image = next(r for r in rows if r["metadata"].get("chunk_type") == "image_pseudo")
        assert len(headings) == 2
        assert image["metadata"]["source"] == "activation.pdf"
        assert image["metadata"]["heading_path"] == "2 介绍一下 GeLU 计算公式？"
        assert image["metadata"]["media_refs"][0]["path"] == "formula.png"
    finally:
        vector.close()


def test_theory_parent_hint_uses_theory_relation_and_parent_rules():
    linker = object.__new__(SemanticLinker)
    linker._load_name_mapping = lambda: {}
    groups = {
        "definition": [{"id": "d", "name": "Base", "type": "definition", "aliases": [], "parent_hint": ""}],
        "law": [{"id": "l", "name": "Law", "type": "law", "aliases": [], "parent_hint": "Base"}],
        "application": [
            {"id": "a", "name": "Use", "type": "application", "aliases": [], "parent_hint": "Law"},
            {"id": "bad", "name": "Bad Use", "type": "application", "aliases": [], "parent_hint": "Use"},
        ],
        "extension": [],
    }

    edges = linker._stage1_parent_hint_match(
        groups, _build_paradigm_config("theory"), "theory"
    )
    triples = {(e["parent_id"], e["relation_type"], e["child_id"]) for e in edges}

    assert ("d", "HAS_LAW", "l") in triples
    assert ("l", "APPLIES_TO", "a") in triples
    assert all(edge[2] != "bad" for edge in triples)

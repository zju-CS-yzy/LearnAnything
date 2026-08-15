from core.markdown_chunker import MarkdownChunker
from core.graph_store import GraphStore
from core.types import ChunkMetadata, MediaRef
from pathlib import Path


def test_formula_media_contract_preserves_latex_and_display_mode():
    ref = MediaRef(type="formula", latex=r"E=mc^2", display="block", caption="质能关系")

    payload = ref.to_dict()
    assert payload["type"] == "formula"
    assert payload["latex"] == r"E=mc^2"
    assert payload["display"] == "block"
    assert payload["caption"] == "质能关系"

    metadata = ChunkMetadata(media_refs=[payload])
    assert metadata.media_refs[0].latex == r"E=mc^2"
    assert metadata.media_refs[0].display == "block"


def test_markdown_chunker_extracts_all_supported_formula_delimiters():
    chunker = object.__new__(MarkdownChunker)
    text = r"行内 $E=mc^2$ 与 \(p=mv\)，块级 $$a^2+b^2=c^2$$ 和 \[G_{\mu\nu}=8\pi T_{\mu\nu}\]"

    refs = chunker._extract_formulas(text)

    assert [(ref["latex"], ref["display"]) for ref in refs] == [
        (r"a^2+b^2=c^2", "block"),
        (r"G_{\mu\nu}=8\pi T_{\mu\nu}", "block"),
        (r"E=mc^2", "inline"),
        (r"p=mv", "inline"),
    ]
    assert chunker._count_formulas(text) == 4


def test_graph_store_sanitizer_preserves_formula_payload():
    store = object.__new__(GraphStore)
    refs = [{
        "type": "formula",
        "latex": r"G_{\mu\nu}=8\pi T_{\mu\nu}",
        "display": "block",
        "caption": "爱因斯坦场方程",
    }]

    assert store._sanitize_media_refs(refs) == refs


def test_graph_store_round_trip_preserves_formula_backslashes(tmp_path):
    db_path = tmp_path / "graph" / "graph"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = GraphStore("formula_round_trip", db_path=str(db_path))
    store.init_schema(force=True)
    formula = {
        "type": "formula",
        "latex": r"G_{\mu\nu}=8\pi T_{\mu\nu}",
        "display": "block",
        "caption": "爱因斯坦场方程",
    }
    store.add_chunk_nodes([{
        "id": "chunk-formula",
        "text": r"$$G_{\mu\nu}=8\pi T_{\mu\nu}$$",
        "metadata": {"chunk_type": "paragraph", "media_refs": [formula]},
    }])
    store.add_concepts("chunk-formula", [{
        "id": "extracted-formula",
        "name": "爱因斯坦场方程",
        "concept_type": "law",
        "relation": "HAS_LAW",
        "media_refs": [formula],
    }])

    extracted = store.get_extracted_concepts()
    store.add_canonical_concepts([{
        "id": "canonical-formula",
        "name": "爱因斯坦场方程",
        "concept_type": "law",
        "aliases": [],
        "source_chunks": ["chunk-formula"],
        "type_votes": {"law": 1},
        "media_refs": [formula],
    }], {"extracted-formula": "canonical-formula"})
    canonical = store.get_canonical_concepts()
    store.close()

    assert extracted[0]["media_refs"][0]["latex"] == formula["latex"]
    assert canonical[0]["media_refs"][0]["latex"] == formula["latex"]

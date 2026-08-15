import pytest
import requests

from core.embedding import ApiEmbeddingClient
from core.markdown_chunker import MarkdownChunker


def test_embedding_input_removes_pdf_control_characters():
    text = "before\x06Aside\x05after"

    prepared = ApiEmbeddingClient._prepare_input(text)

    assert prepared == "before Aside after"
    assert all(ord(char) >= 32 or char in "\n\r\t" for char in prepared)


def test_embedding_input_truncates_formula_heavy_text_with_headroom():
    text = " ".join(r"G_{\mu\nu}=8\pi T_{\mu\nu}" for _ in range(1000))

    prepared = ApiEmbeddingClient._prepare_input(text)
    estimated = sum(
        ApiEmbeddingClient._estimated_token_cost(match.group(0))
        for match in ApiEmbeddingClient._TOKEN_PARTS.finditer(prepared)
    )

    assert len(prepared) < len(text)
    assert estimated <= ApiEmbeddingClient.MAX_ESTIMATED_INPUT_TOKENS


def test_embedding_input_preserves_batch_cardinality():
    client = object.__new__(ApiEmbeddingClient)
    client.dimensions = 2
    client.model = "embedding-3"
    client._last_request_time = 0.0
    client._min_interval = 0.0
    calls = []

    def fake_request(batch):
        calls.append(list(batch))
        return [[float(index), 1.0] for index, _ in enumerate(batch)]

    client._request = fake_request
    result = client.encode(["normal", "bad\x06text", ""])

    assert len(result) == 3
    assert calls == [["normal", "bad text", " "]]


def test_embedding_batches_respect_total_token_budget_and_order():
    inputs = ["word " * 800 for _ in range(12)]
    prepared = [ApiEmbeddingClient._prepare_input(text) for text in inputs]

    batches = ApiEmbeddingClient._make_batches(prepared)

    assert [item for batch in batches for item in batch] == prepared
    assert len(batches) > 1
    assert all(len(batch) <= ApiEmbeddingClient.MAX_BATCH_ITEMS for batch in batches)
    assert all(
        sum(ApiEmbeddingClient._estimated_tokens(text) for text in batch)
        <= ApiEmbeddingClient.MAX_ESTIMATED_BATCH_TOKENS
        for batch in batches
    )


def test_markdown_chunker_removes_pdf_control_characters():
    chunks = MarkdownChunker().chunk_markdown(
        "# Title\n\nBefore\x06Aside\x05after",
        {"source": "control.pdf"},
    )

    assert chunks
    assert all("\x06" not in chunk["text"] and "\x05" not in chunk["text"] for chunk in chunks)


def _fake_client():
    client = object.__new__(ApiEmbeddingClient)
    client.dimensions = 2
    client.model = "embedding-3"
    client._last_request_time = 0.0
    client._min_interval = 0.0
    client.TRANSPORT_RECOVERY_COOLDOWN = 0.0
    return client


def test_transient_ssl_batch_is_deferred_and_retried_without_hash_fallback():
    client = _fake_client()
    calls = 0

    def flaky_request(batch):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.exceptions.SSLError("TLS EOF")
        return [[0.25, 0.75] for _ in batch]

    client._request = flaky_request

    assert client.encode(["A", "B"]) == [[0.25, 0.75], [0.25, 0.75]]
    assert calls == 2


def test_persistent_ssl_failure_aborts_instead_of_mixing_vector_spaces():
    client = _fake_client()
    client._request = lambda batch: (_ for _ in ()).throw(
        requests.exceptions.SSLError("TLS EOF")
    )

    with pytest.raises(RuntimeError, match="避免在同一向量库混用"):
        client.encode(["A", "B"])

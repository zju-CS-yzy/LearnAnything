from core.knowledge_search import (
    AcademicKnowledgeSearchProvider,
    AcademicSearchResult,
    CrossrefKnowledgeSearchProvider,
    OpenAlexKnowledgeSearchProvider,
    external_evidence_documents,
    assess_result_relevance,
)
import requests


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_crossref_normalizes_jats_abstract_and_metadata():
    session = FakeSession({"message": {"items": [{
        "DOI": "10.1000/TEST",
        "title": ["Retrieval augmented generation"],
        "abstract": "<jats:p>Uses <b>retrieval</b> evidence.</jats:p>",
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "published-online": {"date-parts": [[2024, 2, 1]]},
        "container-title": ["Journal of RAG"],
        "URL": "https://doi.org/10.1000/test",
        "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
    }]}})
    provider = CrossrefKnowledgeSearchProvider(session=session, mailto="test@example.com")

    result = provider.search("RAG", limit=3)[0].as_dict()

    assert result["doi"] == "10.1000/test"
    assert result["abstract"] == "Uses retrieval evidence."
    assert result["authors"] == ["Ada Lovelace"]
    assert result["year"] == 2024
    assert result["evidence_ready"] is True
    assert session.calls[0][1]["params"]["mailto"] == "test@example.com"


def test_openalex_reconstructs_abstract_and_skips_retracted_work():
    session = FakeSession({"results": [
        {
            "id": "https://openalex.org/W1",
            "display_name": "Useful paper",
            "abstract_inverted_index": {"retrieval": [1], "Grounded": [0]},
            "publication_year": 2023,
            "authorships": [{"author": {"display_name": "Lin Q"}}],
            "primary_location": {
                "landing_page_url": "https://example.org/paper",
                "source": {"display_name": "Proceedings"},
            },
            "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"},
            "ids": {"doi": "https://doi.org/10.1000/open"},
        },
        {"id": "W2", "display_name": "Retracted", "is_retracted": True},
    ]})

    results = OpenAlexKnowledgeSearchProvider("key", session=session).search("grounding")

    assert len(results) == 1
    assert results[0].abstract == "Grounded retrieval"
    assert results[0].doi == "10.1000/open"


def test_openalex_batches_doi_lookups_for_abstract_enrichment():
    session = FakeSession({"results": [{
        "id": "https://openalex.org/W3",
        "display_name": "DOI resolved paper",
        "doi": "https://doi.org/10.1000/resolved",
        "abstract_inverted_index": {"resolved": [1], "Evidence": [0]},
    }]})
    provider = OpenAlexKnowledgeSearchProvider("key", session=session)

    results = provider.lookup_dois(["10.1000/resolved", "https://doi.org/10.1000/resolved"])

    assert results["10.1000/resolved"].abstract == "Evidence resolved"
    params = session.calls[0][1]["params"]
    assert params["filter"] == "doi:https://doi.org/10.1000/resolved"
    assert params["per_page"] == 1


def test_openalex_retries_a_transient_tls_failure():
    class FlakySession(FakeSession):
        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if len(self.calls) == 1:
                raise requests.exceptions.SSLError("temporary TLS EOF")
            return FakeResponse({"results": []})

    session = FlakySession({})
    results = OpenAlexKnowledgeSearchProvider("key", session=session).search("relativity")

    assert results == []
    assert len(session.calls) == 2


def test_composite_search_deduplicates_same_doi_across_providers():
    shared = AcademicSearchResult(
        result_id="one", provider="a", external_id="1", query="q",
        title="Paper", abstract="Evidence", authors=(), year=2024,
        venue="", url="https://doi.org/10.1/x", doi="10.1/x",
    )

    class Provider:
        def __init__(self, name):
            self.name = name

        def search(self, query, limit=5):
            return [AcademicSearchResult(**{**shared.__dict__, "provider": self.name})]

    result = AcademicKnowledgeSearchProvider([Provider("a"), Provider("b")]).search_many(["q"])

    assert len(result["results"]) == 1


def test_composite_search_enriches_missing_crossref_abstract_by_doi():
    metadata = AcademicSearchResult(
        result_id="crossref-result", provider="crossref", external_id="10.1/x", query="q",
        title="Paper", abstract="", authors=(), year=2024,
        venue="Journal", url="https://doi.org/10.1/x", doi="10.1/x",
    )
    enriched = AcademicSearchResult(
        result_id="openalex-result", provider="openalex", external_id="W1", query="doi:10.1/x",
        title="Paper", abstract="Verified evidence", authors=(), year=2024,
        venue="Journal", url="https://doi.org/10.1/x", doi="10.1/x",
    )

    class MetadataProvider:
        name = "crossref"

        def search(self, query, limit=5):
            return [metadata]

    class DoiEnricher:
        name = "openalex"

        def search(self, query, limit=5):
            return []

        def lookup_dois(self, dois):
            assert list(dois) == ["10.1/x"]
            return {"10.1/x": enriched}

    result = AcademicKnowledgeSearchProvider([MetadataProvider(), DoiEnricher()]).search_many(["q"])

    assert result["results"][0]["abstract"] == "Verified evidence"
    assert result["results"][0]["evidence_ready"] is True
    assert result["results"][0]["abstract_provider"] == "openalex"
    assert result["results"][0]["providers"] == ["crossref", "openalex"]


def test_external_evidence_documents_preserve_traceability():
    source = AcademicSearchResult(
        result_id="academic_crossref_1", provider="crossref", external_id="10.1/x",
        query="RAG evidence", title="A paper", abstract="A grounded abstract.",
        authors=("Ada Lovelace",), year=2024, venue="Journal", url="https://doi.org/10.1/x",
        doi="10.1/x", license="CC-BY",
    ).as_dict()

    documents = external_evidence_documents(
        [source], subject_id="rag", imported_by="owner"
    )

    assert len(documents) == 1
    assert documents[0]["text"] == "A paper\n\nA grounded abstract."
    assert documents[0]["metadata"]["source_kind"] == "external_academic"
    assert documents[0]["metadata"]["result_id"] == "academic_crossref_1"
    assert documents[0]["metadata"]["imported_by"] == "owner"
    assert documents[0]["metadata"]["providers"] == ["crossref"]
    assert documents[0]["metadata"]["abstract_provider"] == "crossref"


def test_relevance_assessment_separates_gap_fit_from_abstract_availability():
    relevant = assess_result_relevance(
        {
            "title": "Lorentz transformation in Minkowski spacetime",
            "abstract": "We derive the transformation between inertial frames.",
        },
        ["Lorentz transformation Minkowski spacetime"],
    )
    unrelated = assess_result_relevance(
        {"title": "Plant genome assembly", "abstract": "A sequencing workflow."},
        ["Lorentz transformation Minkowski spacetime"],
    )
    assert relevant["relevance_level"] == "high"
    assert relevant["relevance_score"] > unrelated["relevance_score"]
    assert unrelated["relevance_level"] == "low"

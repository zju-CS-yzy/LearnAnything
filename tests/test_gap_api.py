from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import gap_api
from app.auth import get_effective_user_id
from core.gap_detector import GapCandidate
from core.gap_store import GapStore
from core.gap_proposal_store import GapProposalStore


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    subject = {"id": "subject-a", "owner_id": "owner", "visibility": "private"}
    gap_path = tmp_path / "owner" / "subject-a" / "gap_flow.db"
    store = GapStore(gap_path, "subject-a")
    proposal_store = GapProposalStore(gap_path, "subject-a")
    store.reconcile([
        GapCandidate(
            gap_id="gap_1", subject_id="subject-a", paradigm_id="theory",
            source_id="d", target_id="a", missing_types=("law",),
            original_relation="APPLIES_TO",
            replacement_relations=("HAS_LAW", "APPLIES_TO"),
            reason="skip", confidence=1.0, detector_version="v1",
        )
    ])

    monkeypatch.setattr(gap_api, "_find_subject", lambda subject_id, user_id=None: subject)
    monkeypatch.setattr(gap_api, "_stores", lambda subject_id, context: (store, object()))
    monkeypatch.setattr(gap_api, "_gap_store", lambda subject_id, context: store)
    monkeypatch.setattr(
        gap_api, "_proposal_store", lambda subject_id, context: proposal_store
    )

    app = FastAPI()
    app.include_router(gap_api.router)
    app.state.identity = "owner"
    app.state.proposal_store = proposal_store
    app.dependency_overrides[get_effective_user_id] = lambda: app.state.identity
    return app, TestClient(app), store


@pytest.mark.parametrize("identity", ["owner", "maintainer"])
def test_owner_and_maintainer_can_ignore(api_env, monkeypatch, identity):
    app, client, store = api_env
    app.state.identity = identity
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api.PermissionManager, "can_read", lambda *args: True)

    response = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/ignore", json={"version": 1}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@pytest.mark.parametrize("identity", ["reader", "contributor"])
def test_reader_and_contributor_cannot_mutate(api_env, monkeypatch, identity):
    app, client, _ = api_env
    app.state.identity = identity
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: False)
    monkeypatch.setattr(gap_api.PermissionManager, "can_read", lambda *args: True)

    response = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/ignore", json={"version": 1}
    )
    assert response.status_code == 403


def test_anonymous_private_access_is_denied(api_env, monkeypatch):
    app, client, _ = api_env
    app.state.identity = "anonymous"
    monkeypatch.setattr(gap_api.PermissionManager, "can_read", lambda *args: False)

    assert client.get("/api/knowledge-graph/subject-a/gaps").status_code == 403


def test_subject_lookup_prefers_current_users_same_named_private_subject(tmp_path, monkeypatch):
    users_dir = tmp_path / "users"
    current_db = users_dir / "current" / "subjects.db"
    other_db = users_dir / "other" / "subjects.db"
    monkeypatch.setattr(gap_api, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(gap_api, "USERS_DIR", users_dir)
    monkeypatch.setattr(gap_api.SubjectManager, "ensure_subject_dir", lambda *args, **kwargs: None)

    gap_api.SubjectManager(db_path=str(current_db)).create_subject(
        "rag", "RAG", owner_id="current", visibility="private"
    )
    gap_api.SubjectManager(db_path=str(other_db)).create_subject(
        "rag", "RAG", owner_id="other", visibility="private"
    )

    found = gap_api._find_subject("rag", "current")

    assert found["owner_id"] == "current"


def test_subject_lookup_skips_inaccessible_same_named_private_subject(tmp_path, monkeypatch):
    users_dir = tmp_path / "users"
    monkeypatch.setattr(gap_api, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(gap_api, "USERS_DIR", users_dir)
    monkeypatch.setattr(gap_api.SubjectManager, "ensure_subject_dir", lambda *args, **kwargs: None)
    for registry, owner in (("a", "owner-a"), ("b", "owner-b")):
        gap_api.SubjectManager(db_path=str(users_dir / registry / "subjects.db")).create_subject(
            "rag", "RAG", owner_id=owner, visibility="private"
        )
    monkeypatch.setattr(
        gap_api.PermissionManager,
        "can_read",
        lambda self, user_id, subject_id, owner_id, visibility: owner_id == "owner-b",
    )

    found = gap_api._find_subject("rag", "reviewer")

    assert found["owner_id"] == "owner-b"


def test_reader_can_list_and_summary(api_env, monkeypatch):
    app, client, _ = api_env
    app.state.identity = "reader"
    monkeypatch.setattr(gap_api.PermissionManager, "can_read", lambda *args: True)

    listed = client.get("/api/knowledge-graph/subject-a/gaps")
    summary = client.get("/api/knowledge-graph/subject-a/gaps/summary")
    assert listed.status_code == summary.status_code == 200
    assert listed.json()["total"] == 1
    assert summary.json()["by_status"]["open"] == 1


def test_all_status_query_includes_non_open_gaps(api_env, monkeypatch):
    app, client, _ = api_env
    app.state.identity = "owner"
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api.PermissionManager, "can_read", lambda *args: True)
    ignored = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/ignore", json={"version": 1}
    )
    assert ignored.status_code == 200

    default_list = client.get("/api/knowledge-graph/subject-a/gaps")
    all_list = client.get("/api/knowledge-graph/subject-a/gaps?status=all")

    assert default_list.json()["total"] == 0
    assert all_list.json()["total"] == 1
    assert all_list.json()["items"][0]["status"] == "ignored"


def test_anonymous_write_requires_authentication(api_env, monkeypatch):
    app, client, _ = api_env
    app.state.identity = "anonymous"
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: False)

    response = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/ignore", json={"version": 1}
    )
    assert response.status_code == 401


def test_stale_version_returns_conflict(api_env, monkeypatch):
    app, client, _ = api_env
    app.state.identity = "owner"
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)

    first = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/ignore", json={"version": 1}
    )
    stale = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/ignore", json={"version": 1}
    )
    assert first.status_code == 200
    assert stale.status_code == 409


def test_owner_can_start_and_read_non_binding_gap_proposal(api_env, monkeypatch):
    app, client, _ = api_env
    app.state.identity = "owner"
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api, "_run_gap_proposal_job", lambda **kwargs: None)

    created = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/proposals",
        json={"version": 1},
    )
    assert created.status_code == 202
    assert created.json()["status"] == "generating"

    latest = client.get(
        "/api/knowledge-graph/subject-a/gaps/gap_1/proposals/latest"
    )
    assert latest.status_code == 200
    assert latest.json()["proposal"]["proposal_id"] == created.json()["proposal_id"]

    history = client.get("/api/knowledge-graph/subject-a/gaps/gap_1/proposals")
    assert history.status_code == 200
    assert history.json()["total"] == 1


def test_reader_cannot_generate_gap_proposal(api_env, monkeypatch):
    app, client, _ = api_env
    app.state.identity = "reader"
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: False)

    response = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/proposals",
        json={"version": 1},
    )
    assert response.status_code == 403


def test_external_search_is_saved_but_does_not_modify_gap(api_env, monkeypatch):
    app, client, store = api_env
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api, "_run_gap_proposal_job", lambda **kwargs: None)
    created = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/proposals",
        json={"version": 1},
    ).json()
    app.state.proposal_store.save_result(
        created["proposal_id"],
        status="needs_external_evidence",
        proposal={"recommended_search_queries": ["grounded retrieval"]},
        evidence=[], duplicate_candidates=[], source_recommendations=[],
        input_hash="hash", prompt_version="v1", model="m", provider="p",
        raw_response={},
    )

    candidate = {
        "result_id": "academic_crossref_1", "provider": "crossref",
        "external_id": "10.1/x", "query": "grounded retrieval", "title": "Paper",
        "abstract": "Grounded evidence.", "authors": [], "year": 2024,
        "venue": "Journal", "url": "https://doi.org/10.1/x", "doi": "10.1/x",
        "open_access_url": "", "license": "", "evidence_ready": True,
        "source_type": "academic_abstract",
    }

    class Search:
        def search_many(self, queries, **kwargs):
            return {"queries": list(queries), "results": [candidate], "errors": []}

    monkeypatch.setattr(gap_api, "_knowledge_search_provider", lambda: Search())
    response = client.post(
        f"/api/knowledge-graph/subject-a/gaps/gap_1/proposals/{created['proposal_id']}/external-search",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["result_id"] == "academic_crossref_1"
    assert store.require("gap_1")["status"] == "open"
    saved = app.state.proposal_store.require(created["proposal_id"])
    assert saved["source_recommendations"][0]["title"] == "Paper"


def test_selected_external_abstract_becomes_chunk_then_regenerates(api_env, monkeypatch):
    app, client, _ = api_env
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api, "_run_gap_proposal_job", lambda **kwargs: None)
    created = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/proposals",
        json={"version": 1},
    ).json()
    candidate = {
        "result_id": "academic_crossref_1", "provider": "crossref",
        "external_id": "10.1/x", "query": "q", "title": "Paper",
        "abstract": "Grounded evidence.", "authors": ["Ada"], "year": 2024,
        "venue": "Journal", "url": "https://doi.org/10.1/x", "doi": "10.1/x",
        "open_access_url": "", "license": "CC-BY", "evidence_ready": True,
        "source_type": "academic_abstract",
    }
    app.state.proposal_store.save_result(
        created["proposal_id"],
        status="needs_external_evidence",
        proposal={"recommended_search_queries": ["q"]}, evidence=[],
        duplicate_candidates=[], source_recommendations=[candidate],
        input_hash="hash", prompt_version="v1", model="m", provider="p",
        raw_response={},
    )

    class Store:
        documents = []

        def add_documents(self, documents):
            self.documents.extend(documents)

    vector_store = Store()
    monkeypatch.setattr(gap_api, "_vector_store", lambda *args: vector_store)
    response = client.post(
        f"/api/knowledge-graph/subject-a/gaps/gap_1/proposals/{created['proposal_id']}/external-import",
        json={"version": 1, "result_ids": ["academic_crossref_1"]},
    )

    assert response.status_code == 202
    assert response.json()["proposal"]["status"] == "generating"
    imported = response.json()["proposal"]["source_recommendations"][0]
    assert imported["status"] == "imported"
    assert imported["abstract"] == "Grounded evidence."
    assert imported["chunk_id"] == vector_store.documents[0]["id"]
    assert vector_store.documents[0]["metadata"]["result_id"] == "academic_crossref_1"
    assert app.state.proposal_store.require(created["proposal_id"])["status"] == "superseded"


def test_manual_regeneration_keeps_imported_external_chunks(api_env, monkeypatch):
    app, client, _ = api_env
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api, "_run_gap_proposal_job", lambda **kwargs: None)
    initial = app.state.proposal_store.create(
        gap_id="gap_1",
        gap_version=1,
        created_by="owner",
        source_recommendations=[{
            "status": "imported",
            "result_id": "academic_openalex_1",
            "chunk_id": "external-proof",
            "title": "Reviewed source",
            "abstract": "Reviewed evidence.",
            "evidence_ready": True,
        }],
    )
    app.state.proposal_store.save_result(
        initial["proposal_id"],
        status="needs_external_evidence",
        proposal={}, evidence=[], duplicate_candidates=[],
        source_recommendations=initial["source_recommendations"],
        input_hash="h", prompt_version="v", model="m", provider="p",
        raw_response={},
    )

    response = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/proposals",
        json={"version": 1},
    )

    assert response.status_code == 202
    retained = response.json()["source_recommendations"]
    assert len(retained) == 1
    assert retained[0]["status"] == "imported"
    assert retained[0]["chunk_id"] == "external-proof"
    assert retained[0]["abstract"] == "Reviewed evidence."


def test_external_import_rejects_unsaved_result_id(api_env, monkeypatch):
    app, client, _ = api_env
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api, "_run_gap_proposal_job", lambda **kwargs: None)
    created = client.post(
        "/api/knowledge-graph/subject-a/gaps/gap_1/proposals",
        json={"version": 1},
    ).json()
    app.state.proposal_store.save_result(
        created["proposal_id"], status="needs_external_evidence",
        proposal={}, evidence=[], duplicate_candidates=[], source_recommendations=[],
        input_hash="h", prompt_version="v", model="m", provider="p", raw_response={},
    )

    response = client.post(
        f"/api/knowledge-graph/subject-a/gaps/gap_1/proposals/{created['proposal_id']}/external-import",
        json={"version": 1, "result_ids": ["forged"]},
    )

    assert response.status_code == 400


def test_imported_external_evidence_can_be_deactivated_and_regenerated(api_env, monkeypatch):
    app, client, _ = api_env
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api, "_run_gap_proposal_job", lambda **kwargs: None)
    created = app.state.proposal_store.create(
        gap_id="gap_1", gap_version=1, created_by="owner",
        source_recommendations=[{
            "status": "imported", "result_id": "paper-1", "title": "Paper",
            "chunk_id": "external-proof", "chunk_ids": ["external-proof", "external-proof-2"],
        }],
    )
    app.state.proposal_store.save_result(
        created["proposal_id"], status="needs_external_evidence", proposal={}, evidence=[],
        duplicate_candidates=[], source_recommendations=created["source_recommendations"],
        input_hash="h", prompt_version="v", model="m", provider="p", raw_response={},
    )

    class Store:
        deleted = []

        def delete(self, ids):
            self.deleted.extend(ids)

    vector = Store()
    monkeypatch.setattr(gap_api, "_vector_store", lambda *args: vector)
    response = client.post(
        f"/api/knowledge-graph/subject-a/gaps/gap_1/proposals/{created['proposal_id']}/external-deactivate",
        json={"version": 1, "chunk_id": "external-proof"},
    )

    assert response.status_code == 202
    assert vector.deleted == ["external-proof", "external-proof-2"]
    assert response.json()["proposal"]["source_recommendations"] == []
    old = app.state.proposal_store.require(created["proposal_id"])
    assert old["source_recommendations"][0]["status"] == "deactivated"


def test_open_access_fulltext_is_chunked_then_regenerates(api_env, monkeypatch):
    app, client, _ = api_env
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    monkeypatch.setattr(gap_api, "_run_gap_proposal_job", lambda **kwargs: None)
    created = app.state.proposal_store.create(gap_id="gap_1", gap_version=1, created_by="owner")
    candidate = {
        "result_id": "oa-1", "provider": "openalex", "title": "Open paper",
        "open_access_url": "https://example.org/paper.pdf", "status": "searched",
    }
    app.state.proposal_store.save_result(
        created["proposal_id"], status="needs_external_evidence", proposal={}, evidence=[],
        duplicate_candidates=[], source_recommendations=[candidate],
        input_hash="h", prompt_version="v", model="m", provider="p", raw_response={},
    )
    documents = [
        {"id": "full-1", "text": "Full text evidence one.", "metadata": {}},
        {"id": "full-2", "text": "Full text evidence two.", "metadata": {}},
    ]
    monkeypatch.setattr(gap_api, "_fulltext_documents", lambda *args, **kwargs: documents)

    class Store:
        added = []

        def add_documents(self, docs):
            self.added.extend(docs)

    vector = Store()
    monkeypatch.setattr(gap_api, "_vector_store", lambda *args: vector)
    response = client.post(
        f"/api/knowledge-graph/subject-a/gaps/gap_1/proposals/{created['proposal_id']}/external-fulltext",
        json={"version": 1, "result_id": "oa-1"},
    )

    assert response.status_code == 202
    assert response.json()["imported_chunks"] == ["full-1", "full-2"]
    regenerated_source = response.json()["proposal"]["source_recommendations"][0]
    assert regenerated_source["source_type"] == "academic_fulltext"
    assert regenerated_source["chunk_ids"] == ["full-1", "full-2"]


def test_legacy_migration_is_write_protected_and_dry_run_by_default(api_env, monkeypatch):
    app, client, _ = api_env

    class Graph:
        def init_schema(self):
            pass

    class Report:
        def as_dict(self):
            return {"found": 2, "deleted": 0, "dry_run": True}

    monkeypatch.setattr(gap_api, "_stores", lambda *args: (object(), Graph()))
    monkeypatch.setattr(gap_api, "_subject_paradigm", lambda *args: "theory")
    monkeypatch.setattr(gap_api, "_detector_version", lambda *args: "v1")
    monkeypatch.setattr(
        gap_api.get_paradigm_loader(), "get_paradigm", lambda *args: {}
    )
    monkeypatch.setattr(
        gap_api.LegacyGapMigrator, "migrate", lambda self, **kwargs: Report()
    )

    app.state.identity = "reader"
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: False)
    denied = client.post(
        "/api/knowledge-graph/subject-a/gaps/migrate-legacy", json={}
    )
    assert denied.status_code == 403

    app.state.identity = "owner"
    monkeypatch.setattr(gap_api.PermissionManager, "can_write", lambda *args: True)
    preview = client.post(
        "/api/knowledge-graph/subject-a/gaps/migrate-legacy", json={}
    )
    assert preview.status_code == 200
    assert preview.json()["dry_run"] is True

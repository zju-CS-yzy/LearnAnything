"""Permission-safe HTTP API for the Gap Flow M1 backend lifecycle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import ANONYMOUS_USER_IDS, get_effective_user_id
from config.settings import (
    DATA_ROOT,
    USERS_DIR,
    get_subject_gap_db_path,
    get_subject_vector_db_path,
)
from core.gap_completion_advisor import GapCompletionAdvisor
from core.gap_completion_service import GapCompletionContextBuilder, GapCompletionService
from core.gap_detector import DEFAULT_DETECTOR_VERSION, GapDetector
from core.gap_service import GapSupplementService
from core.gap_migration import LegacyGapMigrator
from core.gap_store import GapConflictError, GapNotFoundError, GapStore
from core.gap_proposal_store import GapProposalStore
from core.graph_store import GraphStore
from core.knowledge_search import (
    AcademicKnowledgeSearchProvider,
    download_open_access_document,
    external_evidence_documents,
    plain_text,
)
from core.paradigm_loader import get_paradigm_loader
from core.permission_manager import PermissionManager
from core.subject_manager import SubjectManager
from core.vector_store import VectorStore


router = APIRouter(prefix="/api/knowledge-graph/{subject}/gaps", tags=["gap-flow"])


class VersionRequest(BaseModel):
    version: int = Field(..., ge=1)


class ReconcileRequest(BaseModel):
    paradigm_id: Optional[str] = Field(default=None, min_length=1, max_length=50)
    detect_root_gaps: bool = True


class MigrationRequest(BaseModel):
    paradigm_id: Optional[str] = Field(default=None, min_length=1, max_length=50)
    dry_run: bool = True


class SupplementConceptRequest(BaseModel):
    canonical_id: Optional[str] = Field(default=None, min_length=1, max_length=255)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    concept_type: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    evidence: Optional[str] = Field(default=None, max_length=4000)


class SupplementRequest(BaseModel):
    version: int = Field(..., ge=1)
    concepts: list[SupplementConceptRequest] = Field(..., min_length=1, max_length=8)


class ProposalCreateRequest(BaseModel):
    version: int = Field(..., ge=1)


class ProposalEditConceptRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    concept_type: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=4000)
    aliases: list[str] = Field(default_factory=list, max_length=12)


class ProposalAcceptRequest(BaseModel):
    version: int = Field(..., ge=1)
    concepts: Optional[list[ProposalEditConceptRequest]] = Field(
        default=None, min_length=1, max_length=8
    )


class ExternalSearchRequest(BaseModel):
    # Advisor may emit up to eight suggestions; the endpoint de-duplicates and
    # executes only the first five so a valid proposal never fails validation.
    queries: list[str] = Field(default_factory=list, max_length=8)


class ExternalImportRequest(BaseModel):
    version: int = Field(..., ge=1)
    result_ids: list[str] = Field(..., min_length=1, max_length=10)


class ExternalEvidenceDeactivateRequest(BaseModel):
    version: int = Field(..., ge=1)
    chunk_id: str = Field(..., min_length=1, max_length=255)


class ExternalFullTextRequest(BaseModel):
    version: int = Field(..., ge=1)
    result_id: str = Field(..., min_length=1, max_length=255)


def _find_subject(subject_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Find public or private subject registration without creating directories."""
    # Subject IDs are only unique inside each registry.  The current user's
    # private registration must win over another user's same-named subject.
    # A set made this order nondeterministic and could resolve ``rag`` to a
    # different owner, producing a false 403 while the correct Gap DB existed.
    ordered_dbs: list[Path] = []
    if user_id and user_id not in ANONYMOUS_USER_IDS:
        ordered_dbs.append(USERS_DIR / user_id / "subjects.db")
    ordered_dbs.append(DATA_ROOT / "subjects.db")
    if USERS_DIR.exists():
        ordered_dbs.extend(
            path for path in sorted(USERS_DIR.glob("*/subjects.db"))
            if path.is_file() and path not in ordered_dbs
        )
    permissions = PermissionManager()
    first_found: Optional[dict[str, Any]] = None
    for db_path in ordered_dbs:
        if not db_path.is_file():
            continue
        found = SubjectManager(db_path=str(db_path)).get_subject(subject_id)
        if found:
            first_found = first_found or found
            if permissions.can_read(
                user_id,
                subject_id,
                found.get("owner_id") or "system",
                found.get("visibility") or "public",
            ):
                return found
    # Preserve 403 rather than changing an existing but inaccessible subject to 404.
    return first_found


def _subject_context(subject: str, user_id: str, *, write: bool = False) -> dict[str, Any]:
    registration = _find_subject(subject, user_id)
    if registration is None:
        raise HTTPException(status_code=404, detail="学科不存在")
    owner_id = registration.get("owner_id") or "system"
    visibility = registration.get("visibility") or "public"
    permissions = PermissionManager()
    if write:
        if user_id in ANONYMOUS_USER_IDS:
            raise HTTPException(status_code=401, detail="需要 Bearer Token 身份认证")
        if not permissions.can_write(user_id, subject, owner_id):
            raise HTTPException(status_code=403, detail="仅 owner 或 maintainer 可处理 Gap")
    elif not permissions.can_read(user_id, subject, owner_id, visibility):
        raise HTTPException(status_code=403, detail="无权访问该学科")
    data_user_id = owner_id if visibility == "private" and owner_id != "system" else None
    return {
        "registration": registration,
        "owner_id": owner_id,
        "visibility": visibility,
        "data_user_id": data_user_id,
    }


def _stores(subject: str, context: dict[str, Any]) -> tuple[GapStore, GraphStore]:
    data_user_id = context["data_user_id"]
    gap_path = get_subject_gap_db_path(subject, data_user_id)
    graph_path = gap_path.parent / "graph" / "graph"
    return (
        GapStore(gap_path, subject),
        GraphStore(f"{subject}_v1", db_path=str(graph_path)),
    )


def _gap_store(subject: str, context: dict[str, Any]) -> GapStore:
    return GapStore(
        get_subject_gap_db_path(subject, context["data_user_id"]), subject
    )


def _proposal_store(subject: str, context: dict[str, Any]) -> GapProposalStore:
    return GapProposalStore(
        get_subject_gap_db_path(subject, context["data_user_id"]), subject
    )


def _knowledge_search_provider() -> AcademicKnowledgeSearchProvider:
    return AcademicKnowledgeSearchProvider()


def _vector_store(subject: str, context: dict[str, Any]) -> VectorStore:
    return VectorStore(
        f"{subject}_v1",
        db_path=str(get_subject_vector_db_path(subject, context["data_user_id"])),
    )


def _run_gap_proposal_job(
    *,
    subject: str,
    data_user_id: Optional[str],
    proposal_id: str,
    paradigm_id: str,
) -> None:
    """Background entry point; all thread-affine stores are created inside it."""
    gap_path = get_subject_gap_db_path(subject, data_user_id)
    proposal_store = GapProposalStore(gap_path, subject)
    try:
        gap_store = GapStore(gap_path, subject)
        graph_store = GraphStore(
            f"{subject}_v1", db_path=str(gap_path.parent / "graph" / "graph")
        )
        graph_store.init_schema()
        vector_store = VectorStore(
            f"{subject}_v1",
            db_path=str(get_subject_vector_db_path(subject, data_user_id)),
        )
        paradigm_config = get_paradigm_loader().get_paradigm(paradigm_id)
        context_builder = GapCompletionContextBuilder(
            graph_store,
            source_loader=vector_store.get_by_ids,
            search_loader=lambda query, limit: vector_store.query(
                query, n_results=limit
            ),
        )
        service = GapCompletionService(
            gap_store=gap_store,
            proposal_store=proposal_store,
            graph_store=graph_store,
            advisor=GapCompletionAdvisor(),
            context_builder=context_builder,
        )
        service.generate(proposal_id, paradigm_config)
    except Exception as exc:
        print(f"[GapCompletion] proposal {proposal_id} failed: {exc}")
        try:
            proposal_store.mark_failed(proposal_id, str(exc))
        except Exception as store_exc:
            print(f"[GapCompletion] failed to persist proposal error: {store_exc}")


def _active_imported_sources(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in proposal.get("source_recommendations") or []
        if isinstance(item, dict)
        and item.get("status") == "imported"
        and (item.get("chunk_id") or item.get("chunk_ids"))
    ]


def _start_regenerated_proposal(
    *,
    subject: str,
    context: dict[str, Any],
    gap: dict[str, Any],
    proposal_store: GapProposalStore,
    created_by: str,
    background_tasks: BackgroundTasks,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    regenerated = proposal_store.create(
        gap_id=gap["gap_id"],
        gap_version=gap["version"],
        created_by=created_by,
        source_recommendations=sources,
    )
    paradigm_id = _subject_paradigm(
        subject, gap.get("paradigm_id"), context["registration"]
    )
    background_tasks.add_task(
        _run_gap_proposal_job,
        subject=subject,
        data_user_id=context["data_user_id"],
        proposal_id=regenerated["proposal_id"],
        paradigm_id=paradigm_id,
    )
    return regenerated


def _fulltext_documents(
    result: dict[str, Any], *, subject: str, user_id: str
) -> list[dict[str, Any]]:
    fetched = download_open_access_document(result.get("open_access_url") or "")
    content = fetched["content"]
    content_type = fetched["content_type"]
    result_id = str(result.get("result_id") or "")
    base = "external_fulltext_" + hashlib.sha256(result_id.encode("utf-8")).hexdigest()[:20]
    metadata = {
        "chunk_type": "external_academic_fulltext",
        "source_kind": "external_open_access_fulltext",
        "source": str(result.get("title") or "")[:500],
        "source_name": str(result.get("title") or "")[:500],
        "subject_id": subject,
        "result_id": result_id,
        "provider": str(result.get("provider") or ""),
        "url": fetched["url"],
        "doi": str(result.get("doi") or "")[:300],
        "license": str(result.get("license") or "")[:500],
        "imported_by": user_id,
    }
    texts: list[str] = []
    if content.startswith(b"%PDF") or content_type == "application/pdf":
        from core.document_processor import DocumentProcessor

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
                handle.write(content)
                temp_path = Path(handle.name)
            chunks = DocumentProcessor(pdf_engine="pymupdf").process_file(
                str(temp_path),
                subject=subject,
                source_name=str(result.get("title") or "external-open-access.pdf")[:180] + ".pdf",
                raw_path=fetched["url"],
                user_id=user_id,
            )
            texts = [
                str(item.get("text") or "").strip()
                for item in chunks
                if len(str(item.get("text") or "").strip()) >= 80
                and (item.get("metadata") or {}).get("chunk_type") not in {"image_pseudo", "formula_pseudo"}
            ]
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
    else:
        decoded = content.decode("utf-8", errors="replace")
        text = plain_text(decoded, 120000)
        texts = [text[index:index + 2200] for index in range(0, len(text), 2000)]
    texts = [text for text in texts if len(text) >= 80][:16]
    if not texts:
        raise ValueError("开放全文已获取，但没有提取到可用于核验的正文")
    return [
        {"id": f"{base}_{index:02d}", "text": text, "metadata": {**metadata, "fulltext_index": index}}
        for index, text in enumerate(texts)
    ]


def _subject_paradigm(
    subject: str,
    requested: Optional[str],
    registration: Optional[dict[str, Any]] = None,
) -> str:
    if requested:
        return requested
    if registration and registration.get("paradigm"):
        return str(registration["paradigm"])
    # Existing deployments keep this optional subject-level setting in config.
    config_path = Path(__file__).parent.parent / "config" / "subjects" / f"{subject}.json"
    if config_path.is_file():
        try:
            value = json.loads(config_path.read_text(encoding="utf-8")).get("paradigm")
            if value:
                return str(value)
        except (OSError, json.JSONDecodeError):
            pass
    return "engineering"


def detect_and_reconcile_gaps(
    *,
    subject: str,
    paradigm_id: str,
    gap_store: GapStore,
    graph_store: GraphStore,
    detect_root_gaps: bool = True,
) -> dict[str, Any]:
    """Run the deterministic detector for API and post-build callers."""
    graph_store.init_schema()
    config = get_paradigm_loader().get_paradigm(paradigm_id)
    nodes = graph_store.get_canonical_concepts(limit=None)
    edges = graph_store.get_concept_links(limit=None)
    detector = GapDetector(_detector_version(paradigm_id, config))
    detection = detector.detect(
        subject_id=subject,
        paradigm_id=paradigm_id,
        nodes=nodes,
        edges=edges,
        paradigm_config=config,
        detect_root_gaps=detect_root_gaps,
    )
    reconciled = gap_store.reconcile(detection.candidates)
    return {
        "subject_id": subject,
        "paradigm_id": paradigm_id,
        **reconciled.as_dict(),
        "diagnostics": [item.__dict__ for item in detection.diagnostics],
    }


def _detector_version(paradigm_id: str, config: dict[str, Any]) -> str:
    relevant = {
        "paradigm_id": paradigm_id,
        "ideal_chain": config.get("ideal_chain", []),
        "cycle_pattern": config.get("cycle_pattern", []),
        "cyclic": config.get("cyclic", False),
        "relation_map": config.get("relation_map", {}),
        "parent_rules": config.get("parent_rules", {}),
    }
    canonical = json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{DEFAULT_DETECTOR_VERSION}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _translate_store_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, GapNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, GapConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("")
def list_gaps(
    subject: str,
    status: Optional[str] = Query("open"),
    missing_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id)
    gap_store = _gap_store(subject, context)
    try:
        query_status = None if status in {None, "", "all"} else status
        result = gap_store.list(
            status=query_status, missing_type=missing_type, limit=limit, offset=offset
        )
        return {"subject_id": subject, **result}
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.get("/summary")
def gap_summary(subject: str, user_id: str = Depends(get_effective_user_id)):
    context = _subject_context(subject, user_id)
    gap_store = _gap_store(subject, context)
    return {"subject_id": subject, **gap_store.summary()}


@router.post("/reconcile")
def reconcile_gaps(
    subject: str,
    request: ReconcileRequest,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store, graph_store = _stores(subject, context)
    try:
        paradigm_id = _subject_paradigm(
            subject, request.paradigm_id, context["registration"]
        )
        return detect_and_reconcile_gaps(
            subject=subject,
            paradigm_id=paradigm_id,
            gap_store=gap_store,
            graph_store=graph_store,
            detect_root_gaps=request.detect_root_gaps,
        )
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post("/migrate-legacy")
def migrate_legacy_gaps(
    subject: str,
    request: MigrationRequest,
    user_id: str = Depends(get_effective_user_id),
):
    """Inventory or migrate historical Kuzu virtual concepts safely."""
    context = _subject_context(subject, user_id, write=True)
    gap_store, graph_store = _stores(subject, context)
    try:
        graph_store.init_schema()
        paradigm_id = _subject_paradigm(
            subject, request.paradigm_id, context["registration"]
        )
        config = get_paradigm_loader().get_paradigm(paradigm_id)
        version = _detector_version(paradigm_id, config)
        report = LegacyGapMigrator(graph_store, gap_store).migrate(
            subject_id=subject,
            paradigm_id=paradigm_id,
            paradigm_config=config,
            detector_version=version,
            dry_run=request.dry_run,
        )
        return {"subject_id": subject, "paradigm_id": paradigm_id, **report.as_dict()}
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post("/{gap_id}/ignore")
def ignore_gap(
    subject: str,
    gap_id: str,
    request: VersionRequest,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    try:
        return gap_store.ignore(gap_id, acted_by=user_id, expected_version=request.version)
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post("/{gap_id}/reopen")
def reopen_gap(
    subject: str,
    gap_id: str,
    request: VersionRequest,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    try:
        return gap_store.reopen(gap_id, acted_by=user_id, expected_version=request.version)
    except Exception as exc:
        raise _translate_store_error(exc) from exc


def _proposal_for_gap(
    proposal_store: GapProposalStore, gap_id: str, proposal_id: str
) -> dict[str, Any]:
    proposal = proposal_store.require(proposal_id)
    if proposal["gap_id"] != gap_id:
        raise GapNotFoundError(f"gap proposal '{proposal_id}' not found for gap '{gap_id}'")
    return proposal


@router.post(
    "/{gap_id}/proposals",
    status_code=status.HTTP_202_ACCEPTED,
)
def create_gap_proposal(
    subject: str,
    gap_id: str,
    request: ProposalCreateRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    proposal_store = _proposal_store(subject, context)
    try:
        gap = gap_store.require(gap_id)
        previous = proposal_store.latest(gap_id)
        imported_sources = []
        if previous and int(previous.get("gap_version") or 0) == int(request.version):
            imported_sources = [
                dict(item)
                for item in previous.get("source_recommendations") or []
                if isinstance(item, dict)
                and item.get("status") == "imported"
                and (item.get("chunk_id") or item.get("chunk_ids"))
            ]
        proposal = proposal_store.create(
            gap_id=gap_id,
            gap_version=request.version,
            created_by=user_id,
            source_recommendations=imported_sources,
        )
        paradigm_id = _subject_paradigm(
            subject, gap.get("paradigm_id"), context["registration"]
        )
        background_tasks.add_task(
            _run_gap_proposal_job,
            subject=subject,
            data_user_id=context["data_user_id"],
            proposal_id=proposal["proposal_id"],
            paradigm_id=paradigm_id,
        )
        return proposal
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.get("/{gap_id}/proposals/latest")
def get_latest_gap_proposal(
    subject: str,
    gap_id: str,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    proposal_store = _proposal_store(subject, context)
    try:
        proposal = proposal_store.latest(gap_id)
        if proposal is None:
            return {"proposal": None}
        gap = gap_store.require(gap_id)
        if (
            proposal["status"] in {"generating", "ready", "needs_external_evidence"}
            and (
                gap["status"] != "open"
                or gap["version"] != proposal["gap_version"]
            )
        ):
            proposal = proposal_store.mark_stale(proposal["proposal_id"])
        return {"proposal": proposal}
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.get("/{gap_id}/proposals")
def list_gap_proposals(
    subject: str,
    gap_id: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    proposal_store = _proposal_store(subject, context)
    try:
        gap_store.require(gap_id)
        return {"gap_id": gap_id, **proposal_store.list_for_gap(gap_id, limit=limit, offset=offset)}
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.get("/{gap_id}/proposals/{proposal_id}")
def get_gap_proposal(
    subject: str,
    gap_id: str,
    proposal_id: str,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    proposal_store = _proposal_store(subject, context)
    try:
        return _proposal_for_gap(proposal_store, gap_id, proposal_id)
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post("/{gap_id}/proposals/{proposal_id}/external-search")
def search_external_gap_evidence(
    subject: str,
    gap_id: str,
    proposal_id: str,
    request: ExternalSearchRequest,
    user_id: str = Depends(get_effective_user_id),
):
    """Search public academic metadata without granting the LLM web access."""
    context = _subject_context(subject, user_id, write=True)
    proposal_store = _proposal_store(subject, context)
    try:
        proposal = _proposal_for_gap(proposal_store, gap_id, proposal_id)
        if proposal["status"] != "needs_external_evidence":
            raise GapConflictError(
                "external search requires a needs_external_evidence proposal"
            )
        proposed_queries = proposal.get("proposal", {}).get(
            "recommended_search_queries", []
        )
        queries = request.queries or proposed_queries
        queries = list(dict.fromkeys(
            str(item).strip()[:300] for item in queries if str(item).strip()
        ))[:5]
        if not queries:
            raise ValueError("no academic search query is available")
        search = _knowledge_search_provider().search_many(
            queries, per_query=5, max_results=20
        )
        if not search["results"] and search["errors"]:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "academic search providers are temporarily unavailable",
                    "providers": search["errors"],
                },
            )
        updated = proposal_store.save_source_recommendations(
            proposal_id, search["results"]
        )
        return {
            "proposal": updated,
            "queries": search["queries"],
            "results": search["results"],
            "provider_errors": search["errors"],
        }
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post(
    "/{gap_id}/proposals/{proposal_id}/external-import",
    status_code=status.HTTP_202_ACCEPTED,
)
def import_external_gap_evidence(
    subject: str,
    gap_id: str,
    proposal_id: str,
    request: ExternalImportRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_effective_user_id),
):
    """Import reviewed abstracts as Chunks and start a fresh evidence-gated proposal."""
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    proposal_store = _proposal_store(subject, context)
    try:
        proposal = _proposal_for_gap(proposal_store, gap_id, proposal_id)
        if proposal["status"] != "needs_external_evidence":
            raise GapConflictError(
                "external import requires a needs_external_evidence proposal"
            )
        gap = gap_store.require(gap_id)
        if gap["status"] != "open" or gap["version"] != request.version:
            proposal_store.mark_stale(proposal_id)
            raise GapConflictError(
                f"gap state/version conflict: current {gap['status']}@{gap['version']}"
            )
        selected_ids = list(dict.fromkeys(
            str(item).strip() for item in request.result_ids if str(item).strip()
        ))
        candidates = {
            str(item.get("result_id")): item
            for item in proposal.get("source_recommendations") or []
            if isinstance(item, dict) and item.get("result_id")
        }
        unknown = [item for item in selected_ids if item not in candidates]
        if unknown:
            raise ValueError("selected result is not part of this proposal search")
        selected = [candidates[item] for item in selected_ids]
        documents = external_evidence_documents(
            selected, subject_id=subject, imported_by=user_id
        )
        if len(documents) != len(selected):
            raise ValueError(
                "every selected result must contain an evidence-ready abstract"
            )
        _vector_store(subject, context).add_documents(documents)
        regenerated = proposal_store.create(
            gap_id=gap_id,
            gap_version=request.version,
            created_by=user_id,
            source_recommendations=[
                {
                    **item,
                    "status": "imported",
                    "chunk_id": document["id"],
                }
                for item, document in zip(selected, documents)
            ],
        )
        paradigm_id = _subject_paradigm(
            subject, gap.get("paradigm_id"), context["registration"]
        )
        background_tasks.add_task(
            _run_gap_proposal_job,
            subject=subject,
            data_user_id=context["data_user_id"],
            proposal_id=regenerated["proposal_id"],
            paradigm_id=paradigm_id,
        )
        return {
            "proposal": regenerated,
            "imported_chunks": [item["id"] for item in documents],
            "imported_sources": [
                {"result_id": item["result_id"], "title": item["title"]}
                for item in selected
            ],
        }
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post(
    "/{gap_id}/proposals/{proposal_id}/external-deactivate",
    status_code=status.HTTP_202_ACCEPTED,
)
def deactivate_external_gap_evidence(
    subject: str,
    gap_id: str,
    proposal_id: str,
    request: ExternalEvidenceDeactivateRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_effective_user_id),
):
    """Remove reviewed external chunks from retrieval while preserving audit history."""
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    proposal_store = _proposal_store(subject, context)
    try:
        proposal = _proposal_for_gap(proposal_store, gap_id, proposal_id)
        gap = gap_store.require(gap_id)
        if gap["status"] != "open" or gap["version"] != request.version:
            raise GapConflictError(
                f"gap state/version conflict: current {gap['status']}@{gap['version']}"
            )
        source = next((
            item for item in proposal.get("source_recommendations") or []
            if isinstance(item, dict) and request.chunk_id in [
                *list(item.get("chunk_ids") or []),
                *([item.get("chunk_id")] if item.get("chunk_id") else []),
            ]
        ), None)
        if source is None or source.get("status") != "imported":
            raise ValueError("external evidence is not active on this proposal")
        chunk_ids = list(dict.fromkeys([
            *list(source.get("chunk_ids") or []),
            *([source.get("chunk_id")] if source.get("chunk_id") else []),
        ]))
        _vector_store(subject, context).delete(chunk_ids)
        updated = proposal_store.update_source_status(
            proposal_id,
            chunk_id=request.chunk_id,
            status="deactivated",
            acted_by=user_id,
        )
        regenerated = _start_regenerated_proposal(
            subject=subject,
            context=context,
            gap=gap,
            proposal_store=proposal_store,
            created_by=user_id,
            background_tasks=background_tasks,
            sources=_active_imported_sources(updated),
        )
        return {"proposal": regenerated, "deactivated_chunks": chunk_ids}
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post(
    "/{gap_id}/proposals/{proposal_id}/external-fulltext",
    status_code=status.HTTP_202_ACCEPTED,
)
def acquire_external_gap_fulltext(
    subject: str,
    gap_id: str,
    proposal_id: str,
    request: ExternalFullTextRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_effective_user_id),
):
    """Fetch a user-selected OA full text, chunk it, and regenerate the proposal."""
    context = _subject_context(subject, user_id, write=True)
    gap_store = _gap_store(subject, context)
    proposal_store = _proposal_store(subject, context)
    try:
        proposal = _proposal_for_gap(proposal_store, gap_id, proposal_id)
        if proposal["status"] != "needs_external_evidence":
            raise GapConflictError("full-text acquisition requires a needs_external_evidence proposal")
        gap = gap_store.require(gap_id)
        if gap["status"] != "open" or gap["version"] != request.version:
            raise GapConflictError(
                f"gap state/version conflict: current {gap['status']}@{gap['version']}"
            )
        candidate = next((
            item for item in proposal.get("source_recommendations") or []
            if isinstance(item, dict) and str(item.get("result_id") or "") == request.result_id
        ), None)
        if candidate is None:
            raise ValueError("selected result is not part of this proposal search")
        if not candidate.get("open_access_url"):
            raise ValueError("selected result has no reviewed open-access full-text URL")
        documents = _fulltext_documents(candidate, subject=subject, user_id=user_id)
        _vector_store(subject, context).add_documents(documents)
        updated = proposal_store.update_source_record(
            proposal_id,
            result_id=request.result_id,
            updates={
                "status": "imported",
                "source_type": "academic_fulltext",
                "chunk_id": documents[0]["id"],
                "chunk_ids": [item["id"] for item in documents],
                "fulltext_imported_by": user_id,
            },
        )
        regenerated = _start_regenerated_proposal(
            subject=subject,
            context=context,
            gap=gap,
            proposal_store=proposal_store,
            created_by=user_id,
            background_tasks=background_tasks,
            sources=_active_imported_sources(updated),
        )
        return {
            "proposal": regenerated,
            "imported_chunks": [item["id"] for item in documents],
            "source_type": "academic_fulltext",
        }
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post("/{gap_id}/proposals/{proposal_id}/accept")
def accept_gap_proposal(
    subject: str,
    gap_id: str,
    proposal_id: str,
    request: ProposalAcceptRequest,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store, graph_store = _stores(subject, context)
    proposal_store = _proposal_store(subject, context)
    try:
        _proposal_for_gap(proposal_store, gap_id, proposal_id)
        graph_store.init_schema()
        service = GapCompletionService(
            gap_store=gap_store,
            proposal_store=proposal_store,
            graph_store=graph_store,
            advisor=None,
            context_builder=None,
        )
        return service.accept(
            proposal_id,
            acted_by=user_id,
            expected_gap_version=request.version,
            edits=(
                [item.model_dump() for item in request.concepts]
                if request.concepts is not None else None
            ),
        )
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post("/{gap_id}/proposals/{proposal_id}/reject")
def reject_gap_proposal(
    subject: str,
    gap_id: str,
    proposal_id: str,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    proposal_store = _proposal_store(subject, context)
    try:
        _proposal_for_gap(proposal_store, gap_id, proposal_id)
        return proposal_store.review(
            proposal_id, decision="reject", reviewed_by=user_id
        )
    except Exception as exc:
        raise _translate_store_error(exc) from exc


@router.post("/{gap_id}/supplement")
def supplement_gap(
    subject: str,
    gap_id: str,
    request: SupplementRequest,
    user_id: str = Depends(get_effective_user_id),
):
    context = _subject_context(subject, user_id, write=True)
    gap_store, graph_store = _stores(subject, context)
    try:
        graph_store.init_schema()
        service = GapSupplementService(gap_store, graph_store)
        return service.supplement(
            gap_id=gap_id,
            concepts=[item.model_dump() for item in request.concepts],
            acted_by=user_id,
            expected_version=request.version,
        )
    except Exception as exc:
        raise _translate_store_error(exc) from exc


__all__ = ["router"]

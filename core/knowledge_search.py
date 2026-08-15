"""Provider-isolated academic search and traceable external evidence import.

Search results are only recommendations.  A result becomes admissible Gap evidence
after a user selects it and its abstract is materialised as a subject-scoped Chunk.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import hashlib
import ipaddress
import os
import re
import socket
import time
from typing import Any, Iterable, Optional, Protocol
from urllib.parse import urljoin, urlparse

import requests


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_TERM_RE = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}", re.I)


def _plain_text(value: Any, limit: int = 6000) -> str:
    text = unescape(_TAG_RE.sub(" ", str(value or "")))
    return _SPACE_RE.sub(" ", text).strip()[:limit]


def plain_text(value: Any, limit: int = 6000) -> str:
    """Public sanitizer used by the reviewed full-text acquisition workflow."""
    return _plain_text(value, limit)


def _first_text(value: Any, limit: int) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return _plain_text(value, limit)


def _public_url(value: Any) -> str:
    url = str(value or "").strip()[:2000]
    return url if urlparse(url).scheme.casefold() in {"http", "https"} else ""


def _stable_id(provider: str, external_id: str, title: str) -> str:
    raw = f"{provider}|{external_id or title.casefold()}"
    return f"academic_{provider}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def _normalize_doi(value: Any) -> str:
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value or "").strip(), flags=re.I)
    doi = doi.strip().lower()
    if not doi or "|" in doi or any(char.isspace() for char in doi):
        return ""
    return doi


def _terms(value: Any) -> set[str]:
    """Return transparent multilingual terms for deterministic relevance."""
    text = _plain_text(value, 12000).casefold()
    terms: set[str] = set()
    for token in _TERM_RE.findall(text):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            terms.update(token[index:index + 2] for index in range(len(token) - 1))
        else:
            terms.add(token)
    return terms


def assess_result_relevance(
    item: dict[str, Any], queries: Iterable[str]
) -> dict[str, Any]:
    """Score whether a result addresses the reviewed Gap search intent.

    This deliberately stays deterministic and inspectable: title matches carry
    more weight than abstract-only matches, while a usable abstract remains a
    separate evidence-quality gate.
    """
    query_terms = set().union(*(_terms(query) for query in queries))
    if not query_terms:
        return {"relevance_score": 0.0, "relevance_level": "unknown", "relevance_reason": "缺少可比较的检索词"}
    title_hits = query_terms & _terms(item.get("title"))
    abstract_hits = query_terms & _terms(item.get("abstract"))
    title_ratio = len(title_hits) / max(1, min(len(query_terms), 10))
    abstract_ratio = len(abstract_hits) / max(1, min(len(query_terms), 14))
    score = min(1.0, title_ratio * 0.72 + abstract_ratio * 0.28)
    level = "high" if score >= 0.42 else "medium" if score >= 0.18 else "low"
    matched = sorted(title_hits | abstract_hits, key=lambda term: (-len(term), term))[:5]
    reason = (
        f"命中检索语义：{'、'.join(matched)}" if matched
        else "题名和摘要未命中当前 Gap 的核心检索语义"
    )
    return {
        "relevance_score": round(score, 4),
        "relevance_level": level,
        "relevance_reason": reason,
    }


def _validate_public_https_url(value: Any) -> str:
    url = _public_url(value)
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("仅允许获取 HTTPS 开放获取全文地址")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("全文地址无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("全文地址不能指向本地或私有网络")
    return url


def _get_with_transient_retry(
    client: requests.Session,
    url: str,
    *,
    attempts: int = 3,
    **kwargs: Any,
) -> requests.Response:
    """Retry transport interruptions and temporary upstream failures only."""
    last_error: Optional[BaseException] = None
    for attempt in range(max(1, attempts)):
        try:
            response = client.get(url, **kwargs)
            if getattr(response, "status_code", 200) not in {429, 502, 503, 504}:
                return response
            response.close()
            last_error = requests.HTTPError(f"temporary upstream status {response.status_code}")
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(0.35 * (2 ** attempt))
    if last_error:
        raise last_error
    raise requests.ConnectionError("academic search request failed")


def download_open_access_document(
    url: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: float = 30.0,
    max_bytes: int = 25 * 1024 * 1024,
) -> dict[str, Any]:
    """Download a user-approved OA document with redirect and size guards."""
    client = session or requests.Session()
    current = _validate_public_https_url(url)
    for _ in range(4):
        response = _get_with_transient_retry(
            client,
            current,
            headers={"User-Agent": "LearnAnything/1.0 (reviewed open-access acquisition)"},
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("全文地址返回了无目标重定向")
            current = _validate_public_https_url(urljoin(current, location))
            continue
        response.raise_for_status()
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
        declared = int(response.headers.get("Content-Length") or 0)
        if declared > max_bytes:
            response.close()
            raise ValueError("开放全文超过 25 MB 获取上限")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                response.close()
                raise ValueError("开放全文超过 25 MB 获取上限")
            chunks.append(chunk)
        response.close()
        return {
            "url": current,
            "content_type": content_type,
            "content": b"".join(chunks),
        }
    raise ValueError("开放全文重定向次数过多")


@dataclass(frozen=True)
class AcademicSearchResult:
    result_id: str
    provider: str
    external_id: str
    query: str
    title: str
    abstract: str
    authors: tuple[str, ...]
    year: Optional[int]
    venue: str
    url: str
    doi: str = ""
    open_access_url: str = ""
    license: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "provider": self.provider,
            "external_id": self.external_id,
            "query": self.query,
            "title": self.title,
            "abstract": self.abstract,
            "authors": list(self.authors),
            "year": self.year,
            "venue": self.venue,
            "url": self.url,
            "doi": self.doi,
            "open_access_url": self.open_access_url,
            "license": self.license,
            "evidence_ready": bool(self.abstract),
            "abstract_provider": self.provider if self.abstract else "",
            "providers": [self.provider],
            "source_type": "academic_abstract",
        }


class KnowledgeSearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 5) -> list[AcademicSearchResult]: ...


class CrossrefKnowledgeSearchProvider:
    """No-key academic metadata search using Crossref's public REST API."""

    name = "crossref"
    endpoint = "https://api.crossref.org/works"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 20.0,
        mailto: Optional[str] = None,
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.mailto = (mailto if mailto is not None else os.getenv("CROSSREF_MAILTO", "")).strip()

    def search(self, query: str, limit: int = 5) -> list[AcademicSearchResult]:
        query = _plain_text(query, 300)
        if not query:
            return []
        params: dict[str, Any] = {
            "query.bibliographic": query,
            "rows": max(1, min(int(limit), 10)),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        response = _get_with_transient_retry(
            self.session,
            self.endpoint,
            params=params,
            headers={"User-Agent": "LearnAnything/1.0 (academic evidence search)"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        items = ((response.json() or {}).get("message") or {}).get("items") or []
        results: list[AcademicSearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _first_text(item.get("title"), 500)
            if not title:
                continue
            doi = _normalize_doi(item.get("DOI"))
            external_id = doi or str(item.get("URL") or "").strip() or title
            authors = tuple(
                name for author in item.get("author") or []
                if (name := _plain_text(
                    " ".join(filter(None, [author.get("given"), author.get("family")])), 200
                ))
            )
            date_parts = (
                ((item.get("published-print") or item.get("published-online") or item.get("issued") or {})
                 .get("date-parts") or [[]])[0]
            )
            try:
                year = int(date_parts[0]) if date_parts else None
            except (TypeError, ValueError):
                year = None
            licenses = item.get("license") or []
            license_url = _public_url(licenses[0].get("URL")) if licenses and isinstance(licenses[0], dict) else ""
            url = _public_url(item.get("URL")) or _doi_url(doi)
            results.append(AcademicSearchResult(
                result_id=_stable_id(self.name, external_id, title),
                provider=self.name,
                external_id=external_id,
                query=query,
                title=title,
                abstract=_plain_text(item.get("abstract")),
                authors=authors[:20],
                year=year,
                venue=_first_text(item.get("container-title"), 300),
                url=url,
                doi=doi,
                license=license_url,
            ))
        return results


class OpenAlexKnowledgeSearchProvider:
    """Optional OpenAlex search; enabled only when an API key is configured."""

    name = "openalex"
    endpoint = "https://api.openalex.org/works"

    def __init__(
        self,
        api_key: str,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 20.0,
    ):
        self.api_key = str(api_key or "").strip()
        self.session = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def _abstract(index: Any) -> str:
        if not isinstance(index, dict):
            return ""
        positions: list[tuple[int, str]] = []
        for word, raw_positions in index.items():
            for position in raw_positions or []:
                try:
                    positions.append((int(position), str(word)))
                except (TypeError, ValueError):
                    continue
        return _plain_text(" ".join(word for _, word in sorted(positions)))

    def _from_item(self, item: dict[str, Any], query: str) -> Optional[AcademicSearchResult]:
        if item.get("is_retracted"):
            return None
        title = _plain_text(item.get("display_name") or item.get("title"), 500)
        if not title:
            return None
        ids = item.get("ids") or {}
        doi = _normalize_doi(ids.get("doi") or item.get("doi"))
        external_id = str(item.get("id") or doi or title)
        primary = item.get("primary_location") or {}
        source = primary.get("source") or {}
        best_oa = item.get("best_oa_location") or {}
        try:
            year = int(item["publication_year"]) if item.get("publication_year") else None
        except (TypeError, ValueError):
            year = None
        return AcademicSearchResult(
            result_id=_stable_id(self.name, external_id, title),
            provider=self.name,
            external_id=external_id,
            query=query,
            title=title,
            abstract=self._abstract(item.get("abstract_inverted_index")),
            authors=tuple(
                _plain_text((entry.get("author") or {}).get("display_name"), 200)
                for entry in item.get("authorships") or []
                if _plain_text((entry.get("author") or {}).get("display_name"), 200)
            )[:20],
            year=year,
            venue=_plain_text(source.get("display_name"), 300),
            url=_public_url(primary.get("landing_page_url")) or _doi_url(doi) or _public_url(item.get("id")),
            doi=doi,
            open_access_url=_public_url(best_oa.get("pdf_url")) or _public_url(best_oa.get("landing_page_url")),
            license=str(best_oa.get("license") or ""),
        )

    def search(self, query: str, limit: int = 5) -> list[AcademicSearchResult]:
        if not self.api_key:
            return []
        query = _plain_text(query, 300)
        if not query:
            return []
        response = _get_with_transient_retry(
            self.session,
            self.endpoint,
            params={
                "search": query,
                "per_page": max(1, min(int(limit), 10)),
                "api_key": self.api_key,
            },
            headers={"User-Agent": "LearnAnything/1.0 (academic evidence search)"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results: list[AcademicSearchResult] = []
        for item in (response.json() or {}).get("results") or []:
            if not isinstance(item, dict):
                continue
            result = self._from_item(item, query)
            if result:
                results.append(result)
        return results

    def lookup_dois(self, dois: Iterable[str]) -> dict[str, AcademicSearchResult]:
        """Batch-resolve DOI metadata so Crossref-only records can gain abstracts."""
        normalized = list(dict.fromkeys(
            doi for value in dois if (doi := _normalize_doi(value))
        ))[:100]
        if not self.api_key or not normalized:
            return {}
        response = _get_with_transient_retry(
            self.session,
            self.endpoint,
            params={
                "filter": "doi:" + "|".join(_doi_url(doi) for doi in normalized),
                "per_page": len(normalized),
                "api_key": self.api_key,
            },
            headers={"User-Agent": "LearnAnything/1.0 (academic evidence search)"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        resolved: dict[str, AcademicSearchResult] = {}
        for item in (response.json() or {}).get("results") or []:
            if not isinstance(item, dict):
                continue
            result = self._from_item(item, f"doi:{_normalize_doi(item.get('doi'))}")
            if result and result.doi:
                resolved[result.doi] = result
        return resolved


def _result_key(item: dict[str, Any]) -> str:
    doi = _normalize_doi(item.get("doi"))
    if doi:
        return f"doi:{doi}"
    return str(item.get("url") or item.get("title") or "").strip().casefold()


def _merge_result(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate metadata while preferring a verifiable abstract."""
    providers = list(dict.fromkeys([
        *(base.get("providers") or [base.get("provider")]),
        *(incoming.get("providers") or [incoming.get("provider")]),
    ]))
    providers = [provider for provider in providers if provider]
    base["providers"] = providers

    if incoming.get("abstract") and not base.get("abstract"):
        base["abstract"] = incoming["abstract"]
        base["abstract_provider"] = incoming.get("abstract_provider") or incoming.get("provider") or ""
    for field in (
        "authors", "year", "venue", "url", "doi", "open_access_url", "license",
    ):
        if not base.get(field) and incoming.get(field):
            base[field] = incoming[field]
    base["evidence_ready"] = bool(base.get("abstract"))
    return base


class AcademicKnowledgeSearchProvider:
    """Search configured providers and return a normalized, de-duplicated result set."""

    def __init__(self, providers: Optional[Iterable[KnowledgeSearchProvider]] = None):
        if providers is None:
            configured: list[KnowledgeSearchProvider] = [CrossrefKnowledgeSearchProvider()]
            openalex_key = os.getenv("OPENALEX_API_KEY", "").strip()
            if openalex_key:
                configured.insert(0, OpenAlexKnowledgeSearchProvider(openalex_key))
            providers = configured
        self.providers = list(providers)

    def search_many(
        self,
        queries: Iterable[str],
        *,
        per_query: int = 5,
        max_results: int = 20,
    ) -> dict[str, Any]:
        normalized_queries = list(dict.fromkeys(
            _plain_text(query, 300) for query in queries if _plain_text(query, 300)
        ))[:5]
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        result_indexes: dict[str, int] = {}
        for query in normalized_queries:
            for provider in self.providers:
                try:
                    found = provider.search(query, limit=per_query)
                except Exception as exc:
                    errors.append({
                        "provider": getattr(provider, "name", type(provider).__name__),
                        "query": query,
                        "error": str(exc)[:500],
                    })
                    continue
                for result in found:
                    item = result.as_dict()
                    key = _result_key(item)
                    if not key:
                        continue
                    if key in result_indexes:
                        _merge_result(results[result_indexes[key]], item)
                    else:
                        result_indexes[key] = len(results)
                        results.append(item)

        missing_dois = list(dict.fromkeys(
            _normalize_doi(item.get("doi"))
            for item in results
            if not item.get("abstract") and _normalize_doi(item.get("doi"))
        ))[:100]
        if missing_dois:
            for provider in self.providers:
                lookup = getattr(provider, "lookup_dois", None)
                if not callable(lookup):
                    continue
                try:
                    enriched = lookup(missing_dois)
                except Exception as exc:
                    errors.append({
                        "provider": getattr(provider, "name", type(provider).__name__),
                        "query": "doi-enrichment",
                        "error": str(exc)[:500],
                    })
                    continue
                for item in results:
                    doi = _normalize_doi(item.get("doi"))
                    candidate = enriched.get(doi) if doi else None
                    if candidate:
                        _merge_result(item, candidate.as_dict())

        # Preserve provider relevance order within each group, but put usable
        # evidence before metadata-only records so the result cap is meaningful.
        for item in results:
            item.update(assess_result_relevance(item, normalized_queries))
        level_order = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
        results.sort(key=lambda item: (
            not bool(item.get("evidence_ready")),
            level_order.get(item.get("relevance_level"), 3),
            -float(item.get("relevance_score") or 0),
        ))
        return {
            "queries": normalized_queries,
            "results": results[:max_results],
            "errors": errors,
        }


def external_evidence_documents(
    results: Iterable[dict[str, Any]],
    *,
    subject_id: str,
    imported_by: str,
) -> list[dict[str, Any]]:
    """Convert reviewed abstract records into deterministic, auditable Chunks."""
    documents: list[dict[str, Any]] = []
    for item in results:
        abstract = _plain_text(item.get("abstract"))
        title = _plain_text(item.get("title"), 500)
        result_id = str(item.get("result_id") or "").strip()
        if not result_id or not title or not abstract:
            continue
        chunk_id = f"external_{hashlib.sha256(result_id.encode('utf-8')).hexdigest()[:24]}"
        documents.append({
            "id": chunk_id,
            "text": f"{title}\n\n{abstract}",
            "metadata": {
                "chunk_type": "external_academic_abstract",
                "source_kind": "external_academic",
                "source": title,
                "source_name": title,
                "subject_id": subject_id,
                "provider": str(item.get("provider") or ""),
                "providers": list(item.get("providers") or [])[:10],
                "abstract_provider": str(item.get("abstract_provider") or "")[:100],
                "external_id": str(item.get("external_id") or ""),
                "result_id": result_id,
                "authors": list(item.get("authors") or [])[:20],
                "year": item.get("year"),
                "venue": str(item.get("venue") or "")[:300],
                "url": str(item.get("url") or "")[:2000],
                "doi": str(item.get("doi") or "")[:300],
                "open_access_url": str(item.get("open_access_url") or "")[:2000],
                "license": str(item.get("license") or "")[:500],
                "query": str(item.get("query") or "")[:300],
                "imported_by": imported_by,
            },
        })
    return documents


__all__ = [
    "AcademicKnowledgeSearchProvider",
    "AcademicSearchResult",
    "CrossrefKnowledgeSearchProvider",
    "KnowledgeSearchProvider",
    "OpenAlexKnowledgeSearchProvider",
    "assess_result_relevance",
    "download_open_access_document",
    "external_evidence_documents",
    "plain_text",
]

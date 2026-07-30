"""Tier 2 source-content acquisition for FDA guidance documents."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.settings import get_settings
from src.common.storage import LocalArtifactStore, get_artifact_store
from src.db.models import GuidanceRegistry, SourceArtifact
from src.ingestion.fda_catalog import source_artifact_from_write_result


@dataclass(frozen=True)
class FetchedContent:
    """Bytes and response metadata fetched from an FDA source URL."""

    url: str
    data: bytes
    content_type: str


@dataclass(frozen=True)
class ResolvedContentSource:
    """Resolved Tier 2 source URL and source kind."""

    url: str
    artifact_kind: str
    preloaded_content: FetchedContent | None = None


@dataclass(frozen=True)
class AcquiredGuidanceContent:
    """Result of preserving raw source content for a guidance document."""

    document_slug: str
    source_url: str
    artifact: SourceArtifact
    raw_object_key: str
    version_hash: str
    content_type: str
    size_bytes: int


ContentFetcher = Callable[[str], Awaitable[FetchedContent]]


async def fetch_content(url: str) -> FetchedContent:
    """Fetch source bytes from an FDA URL."""
    import httpx

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return FetchedContent(
            url=str(response.url),
            data=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
        )


async def resolve_guidance_source(
    guidance: GuidanceRegistry,
    *,
    fetcher: ContentFetcher = fetch_content,
    base_url: str | None = None,
) -> ResolvedContentSource:
    """Resolve a guidance row to a PDF URL or landing-page HTML fallback."""
    if guidance.pdf_url:
        return ResolvedContentSource(url=guidance.pdf_url, artifact_kind="raw_pdf")

    if not guidance.landing_url:
        raise ValueError(f"Guidance row {guidance.slug!r} has no PDF URL or landing URL")

    landing_page = await fetcher(guidance.landing_url)
    pdf_url = extract_pdf_url(landing_page.data.decode("utf-8", errors="replace"), base_url=base_url)
    if pdf_url:
        return ResolvedContentSource(url=pdf_url, artifact_kind="raw_pdf")

    return ResolvedContentSource(
        url=landing_page.url,
        artifact_kind="raw_html",
        preloaded_content=landing_page,
    )


async def acquire_guidance_content(
    session: AsyncSession,
    guidance: GuidanceRegistry,
    *,
    fetcher: ContentFetcher = fetch_content,
    store: LocalArtifactStore | None = None,
) -> AcquiredGuidanceContent:
    """Download and preserve raw PDF or HTML for a guidance registry row."""
    settings = get_settings()
    source = await resolve_guidance_source(guidance, fetcher=fetcher, base_url=settings.fda_base_url)
    content = source.preloaded_content or await fetcher(source.url)
    version_hash = hashlib.sha256(content.data).hexdigest()
    existing_artifact = await latest_source_artifact(
        session,
        document_slug=guidance.slug,
        version_hash=version_hash,
    )
    if existing_artifact is not None:
        return AcquiredGuidanceContent(
            document_slug=guidance.slug,
            source_url=existing_artifact.source_url or content.url,
            artifact=existing_artifact,
            raw_object_key=existing_artifact.object_key,
            version_hash=version_hash,
            content_type=existing_artifact.content_type,
            size_bytes=existing_artifact.size_bytes,
        )

    extension = _extension_for_content(content.content_type, source.artifact_kind, content.url)
    object_key = PurePosixPath("raw", guidance.slug, f"{version_hash}.{extension}").as_posix()
    artifact_store = store or get_artifact_store()
    write_result = artifact_store.put_bytes(
        object_key,
        content.data,
        content_type=_normalize_content_type(content.content_type),
    )
    artifact = source_artifact_from_write_result(
        write_result,
        artifact_kind=source.artifact_kind,
        source_url=content.url,
        document_slug=guidance.slug,
        version_hash=version_hash,
    )
    session.add(artifact)

    return AcquiredGuidanceContent(
        document_slug=guidance.slug,
        source_url=content.url,
        artifact=artifact,
        raw_object_key=object_key,
        version_hash=version_hash,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
    )


async def latest_source_artifact(
    session: AsyncSession,
    *,
    document_slug: str,
    version_hash: str,
) -> SourceArtifact | None:
    """Return an existing raw-source artifact for a document/version hash."""
    result = await session.execute(
        select(SourceArtifact).where(
            SourceArtifact.document_slug == document_slug,
            SourceArtifact.version_hash == version_hash,
            SourceArtifact.artifact_kind.in_(["raw_pdf", "raw_html"]),
        )
    )
    return result.scalars().first()


def extract_pdf_url(html: str, *, base_url: str | None = None) -> str | None:
    """Extract the first FDA PDF/download link from landing-page HTML."""
    settings = get_settings()
    resolved_base_url = base_url or settings.fda_base_url
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        href_text = str(href)
        anchor_text = anchor.get_text(" ", strip=True).lower()
        if _looks_like_pdf_link(href_text, anchor_text):
            return urljoin(resolved_base_url, href_text)
    return None


def _looks_like_pdf_link(href: str, anchor_text: str) -> bool:
    parsed_path = urlparse(href).path.lower()
    return parsed_path.endswith(".pdf") or parsed_path.endswith("/download") or "pdf" in anchor_text


def _extension_for_content(content_type: str, artifact_kind: str, url: str) -> str:
    normalized = _normalize_content_type(content_type).split(";", maxsplit=1)[0].strip().lower()
    if normalized == "application/pdf" or artifact_kind == "raw_pdf":
        return "pdf"
    if normalized in {"text/html", "application/xhtml+xml"} or artifact_kind == "raw_html":
        return "html"
    path_suffix = PurePosixPath(urlparse(url).path).suffix.lstrip(".").lower()
    return path_suffix or "bin"


def _normalize_content_type(content_type: str | None) -> str:
    return content_type or "application/octet-stream"
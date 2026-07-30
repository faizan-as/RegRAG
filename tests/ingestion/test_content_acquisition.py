"""Tests for Tier 2 source-content acquisition."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.common.storage import LocalArtifactStore
from src.db.models import GuidanceRegistry
from src.db.models import SourceArtifact
from src.ingestion.content_acquisition import (
    FetchedContent,
    acquire_guidance_content,
    extract_pdf_url,
    resolve_guidance_source,
)


def test_extract_pdf_url_from_landing_page_html() -> None:
    """Landing-page fallback finds FDA media download links."""
    html = '<html><body><a href="/media/120958/download">PDF (137 KB)</a></body></html>'

    assert extract_pdf_url(html, base_url="https://www.fda.gov") == (
        "https://www.fda.gov/media/120958/download"
    )


async def test_resolve_guidance_source_prefers_registry_pdf_url() -> None:
    """Rows with catalog PDF URLs do not require landing-page fetches."""
    guidance = _guidance(pdf_url="https://www.fda.gov/media/example/download")

    async def failing_fetcher(url: str) -> FetchedContent:
        raise AssertionError(f"Unexpected fetch: {url}")

    source = await resolve_guidance_source(guidance, fetcher=failing_fetcher)

    assert source.url == "https://www.fda.gov/media/example/download"
    assert source.artifact_kind == "raw_pdf"


async def test_resolve_guidance_source_falls_back_to_landing_pdf() -> None:
    """Rows without PDF URLs resolve PDF links from landing-page HTML."""
    guidance = _guidance(pdf_url=None)

    async def fetcher(url: str) -> FetchedContent:
        assert url == guidance.landing_url
        return FetchedContent(
            url=url,
            data=b'<a href="/media/abc/download">PDF</a>',
            content_type="text/html",
        )

    source = await resolve_guidance_source(
        guidance,
        fetcher=fetcher,
        base_url="https://www.fda.gov",
    )

    assert source.url == "https://www.fda.gov/media/abc/download"
    assert source.artifact_kind == "raw_pdf"


async def test_resolve_guidance_source_uses_landing_html_when_no_pdf_found() -> None:
    """Landing-page HTML is preserved when no PDF link can be resolved."""
    guidance = _guidance(pdf_url=None)

    async def fetcher(url: str) -> FetchedContent:
        return FetchedContent(url=url, data=b"<html>No PDF</html>", content_type="text/html")

    source = await resolve_guidance_source(guidance, fetcher=fetcher)

    assert source.url == guidance.landing_url
    assert source.artifact_kind == "raw_html"
    assert source.preloaded_content is not None


async def test_acquire_guidance_content_preserves_pdf_and_metadata(tmp_path: Path) -> None:
    """Tier 2 acquisition writes raw content and returns source artifact metadata."""
    guidance = _guidance(pdf_url="https://www.fda.gov/media/example/download")
    payload = b"%PDF-1.7 example"
    expected_hash = hashlib.sha256(payload).hexdigest()
    session = _FakeSession()

    async def fetcher(url: str) -> FetchedContent:
        return FetchedContent(url=url, data=payload, content_type="application/pdf")

    result = await acquire_guidance_content(
        session,
        guidance,
        fetcher=fetcher,
        store=LocalArtifactStore(tmp_path),
    )

    assert result.version_hash == expected_hash
    assert result.raw_object_key == f"raw/{guidance.slug}/{expected_hash}.pdf"
    assert result.artifact.document_slug == guidance.slug
    assert result.artifact.artifact_kind == "raw_pdf"
    assert result.artifact.source_url == guidance.pdf_url
    assert result.artifact.size_bytes == len(payload)
    assert session.added == [result.artifact]


async def test_acquire_guidance_content_reuses_existing_version(tmp_path: Path) -> None:
    """Unchanged source bytes reuse existing artifact metadata instead of rewriting."""
    guidance = _guidance(pdf_url="https://www.fda.gov/media/example/download")
    payload = b"%PDF-1.7 example"
    version_hash = hashlib.sha256(payload).hexdigest()
    existing = SourceArtifact(
        storage_backend="local",
        object_key=f"raw/{guidance.slug}/{version_hash}.pdf",
        artifact_kind="raw_pdf",
        content_type="application/pdf",
        sha256=version_hash,
        size_bytes=len(payload),
        source_url=guidance.pdf_url,
        document_slug=guidance.slug,
        version_hash=version_hash,
    )
    session = _FakeSession(existing_artifact=existing)

    async def fetcher(url: str) -> FetchedContent:
        return FetchedContent(url=url, data=payload, content_type="application/pdf")

    result = await acquire_guidance_content(
        session,
        guidance,
        fetcher=fetcher,
        store=LocalArtifactStore(tmp_path),
    )

    assert result.artifact is existing
    assert result.raw_object_key == existing.object_key
    assert session.added == []
    assert not LocalArtifactStore(tmp_path).exists(existing.object_key)


def _guidance(*, pdf_url: str | None) -> GuidanceRegistry:
    return GuidanceRegistry(
        slug="example-guidance",
        title="Example Guidance",
        landing_url="https://www.fda.gov/regulatory-information/example-guidance",
        pdf_url=pdf_url,
        status="Final",
        raw_payload={},
        topics=[],
    )


class _FakeSession:
    def __init__(self, existing_artifact=None) -> None:
        self.added = []
        self.existing_artifact = existing_artifact

    def add(self, instance) -> None:
        self.added.append(instance)

    async def execute(self, statement):
        del statement
        return _FakeResult(self.existing_artifact)


class _FakeResult:
    def __init__(self, artifact) -> None:
        self.artifact = artifact

    def scalars(self):
        return self

    def first(self):
        return self.artifact
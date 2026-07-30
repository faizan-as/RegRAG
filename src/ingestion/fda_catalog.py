"""FDA guidance catalog fetch, snapshot, and normalization helpers."""

from __future__ import annotations

import json
from json import JSONDecodeError
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html import unescape
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.settings import get_settings
from src.common.storage import ArtifactWriteResult, LocalArtifactStore, get_artifact_store
from src.db.models import LifecycleState, SourceArtifact

if TYPE_CHECKING:
    from src.ingestion.registry import RegistryChange


@dataclass(frozen=True)
class CatalogLink:
    """Text and absolute URL extracted from an FDA catalog HTML fragment."""

    text: str | None
    url: str | None


@dataclass(frozen=True)
class NormalizedCatalogRecord:
    """Normalized FDA catalog row ready for registry upsert."""

    slug: str
    title: str
    landing_url: str
    pdf_url: str | None
    status: str | None
    lifecycle_state: LifecycleState
    center: str | None
    communication_type: str | None
    topics: list[str]
    regulated_product: str | None
    docket_id: str | None
    docket_url: str | None
    issue_date: date | None
    comment_close_date: date | None
    open_comment: bool | None
    fda_last_changed: datetime | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class CatalogSyncResult:
    """Result of a Tier 1 catalog sync run."""

    artifact: SourceArtifact
    record_count: int
    change_count: int
    changes: list[RegistryChange]


async def fetch_catalog_bytes(url: str | None = None) -> bytes:
    """Fetch the static FDA guidance catalog JSON as bytes."""
    import httpx

    settings = get_settings()
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(url or settings.fda_guidance_json_url)
        response.raise_for_status()
        return response.content


async def sync_fda_catalog(
    session: AsyncSession,
    *,
    data: bytes | None = None,
    retrieved_at: datetime | None = None,
    store: LocalArtifactStore | None = None,
) -> CatalogSyncResult:
    """Run Tier 1 catalog sync: snapshot raw JSON, normalize rows, and sync registry."""
    from src.ingestion.registry import sync_guidance_registry

    settings = get_settings()
    snapshot_time = retrieved_at or datetime.now(UTC)
    catalog_bytes = data if data is not None else await fetch_catalog_bytes(settings.fda_guidance_json_url)
    write_result = snapshot_catalog_bytes(catalog_bytes, retrieved_at=snapshot_time, store=store)
    artifact = source_artifact_from_write_result(
        write_result,
        artifact_kind="catalog_snapshot",
        source_url=settings.fda_guidance_json_url,
    )
    session.add(artifact)

    rows = load_catalog_rows(catalog_bytes)
    records = normalize_catalog_rows(rows, base_url=settings.fda_base_url)
    changes = await sync_guidance_registry(session, records, synced_at=snapshot_time)
    return CatalogSyncResult(
        artifact=artifact,
        record_count=len(records),
        change_count=len(changes),
        changes=changes,
    )


def snapshot_catalog_bytes(
    data: bytes,
    *,
    retrieved_at: datetime | None = None,
    store: LocalArtifactStore | None = None,
) -> ArtifactWriteResult:
    """Persist a raw FDA catalog snapshot to local artifact storage."""
    timestamp = (retrieved_at or datetime.now(UTC)).astimezone(UTC)
    object_key = PurePosixPath(
        "catalog",
        "search-for-guidance",
        f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json",
    ).as_posix()
    artifact_store = store or get_artifact_store()
    return artifact_store.put_bytes(object_key, data, content_type="application/json")


def source_artifact_from_write_result(
    result: ArtifactWriteResult,
    *,
    artifact_kind: str,
    source_url: str | None = None,
    document_slug: str | None = None,
    version_hash: str | None = None,
) -> SourceArtifact:
    """Build a source-artifact metadata row from a storage write result."""
    return SourceArtifact(
        storage_backend="local",
        object_key=result.object_key,
        artifact_kind=artifact_kind,
        content_type=result.content_type,
        sha256=result.sha256,
        size_bytes=result.size_bytes,
        source_url=source_url,
        document_slug=document_slug,
        version_hash=version_hash,
    )


def load_catalog_rows(data: bytes | str | Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Load FDA catalog rows from bytes, text, list payloads, or DataTables-style objects."""
    if isinstance(data, bytes):
        payload = _loads_catalog_payload(data.decode("utf-8"))
    elif isinstance(data, str):
        payload = _loads_catalog_payload(data)
    else:
        payload = data

    rows: Any
    if isinstance(payload, Mapping):
        rows = payload.get("data", [])
    else:
        rows = payload

    if not isinstance(rows, list):
        raise ValueError("FDA catalog payload must be a JSON array or contain a data array")

    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _loads_catalog_payload(text: str) -> Any:
    try:
        return json.loads(text)
    except JSONDecodeError:
        return _loads_concatenated_json_values(text)


def _loads_concatenated_json_values(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    length = len(text)

    while index < length:
        while index < length and (text[index].isspace() or text[index] == ","):
            index += 1
        if index >= length:
            break
        if text[index] == "]":
            break
        value, index = decoder.raw_decode(text, index)
        values.append(value)

    return values


def normalize_catalog_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    base_url: str | None = None,
) -> list[NormalizedCatalogRecord]:
    """Normalize raw FDA catalog rows into registry-ready records."""
    settings = get_settings()
    return [normalize_catalog_row(row, base_url=base_url or settings.fda_base_url) for row in rows]


def normalize_catalog_row(
    row: Mapping[str, Any],
    *,
    base_url: str | None = None,
) -> NormalizedCatalogRecord:
    """Normalize one FDA catalog row from the static JSON catalog."""
    settings = get_settings()
    fda_base_url = base_url or settings.fda_base_url
    title_link = _extract_link(_string_value(row.get("title")), base_url=fda_base_url)
    if not title_link.text or not title_link.url:
        raise ValueError("FDA catalog row is missing a title link")

    pdf_link = _extract_link(
        _string_value(row.get("field_associated_media_2")),
        base_url=fda_base_url,
    )
    docket_link = _extract_link(_string_value(row.get("field_docket_number")), base_url=fda_base_url)
    changed_value = _extract_time(_string_value(row.get("changed")))
    slug = _slug_from_url(title_link.url)

    return NormalizedCatalogRecord(
        slug=slug,
        title=title_link.text,
        landing_url=title_link.url,
        pdf_url=pdf_link.url,
        status=_clean_text(row.get("field_final_guidance_1")),
        lifecycle_state=LifecycleState.ACTIVE,
        center=_clean_text(row.get("field_center"))
        or _clean_text(row.get("field_issuing_office_taxonomy")),
        communication_type=_clean_text(row.get("field_communication_type")),
        topics=_split_topics(row.get("topics-product") or row.get("term_node_tid")),
        regulated_product=_clean_text(row.get("field_regulated_product_field")),
        docket_id=docket_link.text,
        docket_url=docket_link.url,
        issue_date=_parse_date(_clean_text(row.get("field_issue_datetime"))),
        comment_close_date=_parse_date(_clean_text(row.get("field_comment_close_date"))),
        open_comment=_parse_open_comment(_clean_text(row.get("open-comment"))),
        fda_last_changed=_parse_datetime(changed_value),
        raw_payload=dict(row),
    )


def _extract_link(fragment: str | None, *, base_url: str) -> CatalogLink:
    if not fragment:
        return CatalogLink(text=None, url=None)

    soup = BeautifulSoup(unescape(fragment), "html.parser")
    anchor = soup.find("a")
    if anchor is None:
        text = soup.get_text(" ", strip=True)
        return CatalogLink(text=text or None, url=None)

    text = anchor.get_text(" ", strip=True)
    href = anchor.get("href")
    return CatalogLink(text=text or None, url=urljoin(base_url, href) if href else None)


def _extract_time(fragment: str | None) -> str | None:
    if not fragment:
        return None
    soup = BeautifulSoup(unescape(fragment), "html.parser")
    time_node = soup.find("time")
    if time_node is None:
        return soup.get_text(" ", strip=True) or None
    datetime_value = time_node.get("datetime")
    return str(datetime_value) if datetime_value else time_node.get_text(" ", strip=True) or None


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = PurePosixPath(path).name
    if not slug:
        raise ValueError(f"Cannot derive FDA guidance slug from URL: {url!r}")
    return slug


def _split_topics(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    return [topic.strip() for topic in text.split(",") if topic.strip()]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%m/%d/%Y").date()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_open_comment(value: str | None) -> bool | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _clean_text(value: Any) -> str | None:
    text = _string_value(value)
    if text is None:
        return None
    cleaned = BeautifulSoup(unescape(text), "html.parser").get_text(" ", strip=True)
    return cleaned or None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
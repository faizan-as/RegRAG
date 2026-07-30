"""PDF parsing helpers for preserved FDA guidance source files."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any


_NUMBERED_HEADING_RE = re.compile(r"^(?:[IVXLCDM]+|\d+)[.)]\s+(?P<title>\S.*)$")
_KNOWN_HEADING_RE = re.compile(
    r"^(?:Introduction|Background|Scope|Recommendations?|Conclusion)\b",
    re.IGNORECASE,
)
_SECTION_ID_RE = re.compile(r"[^a-z0-9]+")
_KNOWN_SINGLE_WORD_HEADINGS = {"BACKGROUND", "INTRODUCTION", "SCOPE", "CONCLUSION"}


@dataclass(frozen=True)
class ParsedPdfPage:
    """Text extracted from a single PDF page with document-level offsets."""

    page_number: int
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ParsedPdfSection:
    """A lightweight section span detected from extracted PDF text."""

    section_id: str
    title: str
    page_number: int
    char_start: int
    char_end: int
    text: str


@dataclass(frozen=True)
class ParsedPdfTable:
    """Table extracted from a PDF with page and optional HTML metadata."""

    table_id: str
    page_number: int | None
    text: str
    html: str | None = None


@dataclass(frozen=True)
class ParsedPdfDocument:
    """Parsed PDF text, page offsets, and section spans."""

    document_id: str
    version_hash: str
    source_url: str
    text: str
    pages: list[ParsedPdfPage]
    sections: list[ParsedPdfSection]
    tables: list[ParsedPdfTable]


PdfOpener = Callable[[bytes], object]
TableExtractor = Callable[[bytes], list[ParsedPdfTable]]


def parse_pdf_bytes(
    data: bytes,
    *,
    document_id: str,
    version_hash: str,
    source_url: str,
    opener: PdfOpener | None = None,
    table_extractor: TableExtractor | None = None,
    extract_tables: bool = False,
) -> ParsedPdfDocument:
    """Parse PDF bytes into text, page offsets, and lightweight sections."""
    document = (opener or _open_with_pymupdf)(data)
    close = getattr(document, "close", None)
    try:
        pages = _extract_pages(document)
    finally:
        if close is not None:
            close()

    full_text = "\n".join(page.text for page in pages)
    tables = _extract_tables(data, table_extractor=table_extractor, extract_tables=extract_tables)
    return ParsedPdfDocument(
        document_id=document_id,
        version_hash=version_hash,
        source_url=source_url,
        text=full_text,
        pages=pages,
        sections=detect_sections(pages),
        tables=tables,
    )


def extract_tables_with_unstructured(data: bytes) -> list[ParsedPdfTable]:
    """Extract PDF tables with Unstructured's table-structure inference."""
    try:
        from unstructured.partition.pdf import partition_pdf
    except ImportError as exc:
        raise RuntimeError(
            "Unstructured is required for PDF table extraction. Install the unstructured package."
        ) from exc

    elements = partition_pdf(file=BytesIO(data), infer_table_structure=True)
    tables: list[ParsedPdfTable] = []
    for element in elements:
        if not _is_unstructured_table(element):
            continue
        metadata = getattr(element, "metadata", None)
        tables.append(
            ParsedPdfTable(
                table_id=f"table-{len(tables) + 1}",
                page_number=_metadata_page_number(metadata),
                text=_element_text(element),
                html=getattr(metadata, "text_as_html", None) if metadata is not None else None,
            )
        )
    return tables


def _extract_tables(
    data: bytes,
    *,
    table_extractor: TableExtractor | None,
    extract_tables: bool,
) -> list[ParsedPdfTable]:
    if table_extractor is not None:
        return table_extractor(data)
    if extract_tables:
        return extract_tables_with_unstructured(data)
    return []


def detect_sections(pages: Sequence[ParsedPdfPage]) -> list[ParsedPdfSection]:
    """Detect coarse section spans from page text headings."""
    candidates = _heading_candidates(pages)
    if not pages:
        return []
    if not candidates:
        return []

    sections: list[ParsedPdfSection] = []
    first_candidate = candidates[0]
    if first_candidate.char_start > 0:
        preamble_text = _slice_pages_text(pages, 0, first_candidate.char_start).strip()
        if preamble_text:
            sections.append(
                ParsedPdfSection(
                    section_id="preamble",
                    title="Preamble",
                    page_number=pages[0].page_number,
                    char_start=0,
                    char_end=first_candidate.char_start,
                    text=preamble_text,
                )
            )

    for index, candidate in enumerate(candidates):
        next_start = candidates[index + 1].char_start if index + 1 < len(candidates) else pages[-1].char_end
        section_text = _slice_pages_text(pages, candidate.char_start, next_start).strip()
        sections.append(
            ParsedPdfSection(
                section_id=_section_id(candidate.title, index=index),
                title=candidate.title,
                page_number=candidate.page_number,
                char_start=candidate.char_start,
                char_end=next_start,
                text=section_text,
            )
        )
    return sections


def _extract_pages(document: object) -> list[ParsedPdfPage]:
    pages: list[ParsedPdfPage] = []
    offset = 0
    page_count = len(document)  # type: ignore[arg-type]
    for page_index in range(page_count):
        page = document.load_page(page_index)  # type: ignore[attr-defined]
        text = page.get_text("text").strip()
        char_start = offset
        char_end = char_start + len(text)
        pages.append(
            ParsedPdfPage(
                page_number=page_index + 1,
                text=text,
                char_start=char_start,
                char_end=char_end,
            )
        )
        offset = char_end + 1
    return pages


@dataclass(frozen=True)
class _HeadingCandidate:
    title: str
    page_number: int
    char_start: int


def _heading_candidates(pages: Sequence[ParsedPdfPage]) -> list[_HeadingCandidate]:
    candidates: list[_HeadingCandidate] = []
    for page in pages:
        page_offset = 0
        for line in page.text.split("\n"):
            stripped = line.strip()
            line_start = page.char_start + page_offset + line.find(stripped) if stripped else page.char_start + page_offset
            if _looks_like_section_heading(stripped):
                candidates.append(
                    _HeadingCandidate(
                        title=stripped,
                        page_number=page.page_number,
                        char_start=line_start,
                    )
                )
            page_offset += len(line) + 1
    return candidates


def _looks_like_section_heading(line: str) -> bool:
    if not line or len(line) > 140:
        return False
    words = line.split()
    numbered_match = _NUMBERED_HEADING_RE.match(line)
    if numbered_match:
        title_words = numbered_match.group("title").split()
        return len(title_words) <= 10 and not numbered_match.group("title").endswith(".")
    if line.isupper() and len(words) <= 12:
        return len(words) > 1 or line in _KNOWN_SINGLE_WORD_HEADINGS
    if _KNOWN_HEADING_RE.match(line):
        return True
    return False


def _slice_pages_text(pages: Sequence[ParsedPdfPage], char_start: int, char_end: int) -> str:
    parts: list[str] = []
    for page in pages:
        if page.char_end < char_start or page.char_start > char_end:
            continue
        start = max(char_start, page.char_start) - page.char_start
        end = min(char_end, page.char_end) - page.char_start
        parts.append(page.text[start:end])
    return "\n".join(part for part in parts if part)


def _section_id(title: str, *, index: int) -> str:
    normalized = _SECTION_ID_RE.sub("-", title.lower()).strip("-")
    return normalized or f"section-{index + 1}"


def _is_unstructured_table(element: object) -> bool:
    category = getattr(element, "category", None)
    return category == "Table" or element.__class__.__name__ == "Table"


def _metadata_page_number(metadata: object | None) -> int | None:
    page_number = getattr(metadata, "page_number", None) if metadata is not None else None
    return page_number if isinstance(page_number, int) else None


def _element_text(element: Any) -> str:
    text = getattr(element, "text", None)
    return str(text if text is not None else element).strip()


def _open_with_pymupdf(data: bytes) -> object:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF parsing. Install the pymupdf package.") from exc
    return fitz.open(stream=data, filetype="pdf")
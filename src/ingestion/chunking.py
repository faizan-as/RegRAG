"""Parent-child chunking for parsed FDA guidance documents."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.api.schemas.chunks import Chunk, ChunkType
from src.ingestion.pdf_parser import ParsedPdfDocument, ParsedPdfPage, ParsedPdfSection


_PARAGRAPH_RE = re.compile(r"\S.*?(?=\n\s*\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class _TextSpan:
    text: str
    char_start: int
    char_end: int


def chunk_parsed_pdf(
    document: ParsedPdfDocument,
    *,
    parent_chunk_size: int = 8000,
    child_chunk_size: int = 1200,
    child_chunk_overlap: int = 150,
) -> list[Chunk]:
    """Create section parent chunks and paragraph child chunks from a parsed PDF.

    Args:
        document: Parsed PDF document with page and section offsets.
        parent_chunk_size: Maximum parent chunk character size before splitting a long section.
        child_chunk_size: Maximum child chunk character size before splitting a long paragraph.
        child_chunk_overlap: Character overlap used only when splitting oversized child paragraphs.

    Returns:
        Ordered parent and child chunks with stable IDs and citation offsets.
    """
    _validate_chunk_sizes(parent_chunk_size, child_chunk_size, child_chunk_overlap)

    chunks: list[Chunk] = []
    chunk_no = 0
    for section in _document_sections(document):
        section_text = document.text[section.char_start : section.char_end]
        for parent_span in _parent_spans(section_text, section.char_start, parent_chunk_size):
            parent_id = _chunk_id(document, chunk_no)
            chunk_no += 1
            chunks.append(
                _build_chunk(
                    document,
                    chunk_id=parent_id,
                    chunk_type=ChunkType.PARENT,
                    parent_chunk_id=None,
                    span=parent_span,
                    section=section,
                )
            )

            for child_span in _child_spans(
                parent_span.text,
                parent_span.char_start,
                child_chunk_size,
                child_chunk_overlap,
            ):
                chunks.append(
                    _build_chunk(
                        document,
                        chunk_id=_chunk_id(document, chunk_no),
                        chunk_type=ChunkType.CHILD,
                        parent_chunk_id=parent_id,
                        span=child_span,
                        section=section,
                    )
                )
                chunk_no += 1
    return chunks


def _validate_chunk_sizes(
    parent_chunk_size: int,
    child_chunk_size: int,
    child_chunk_overlap: int,
) -> None:
    if parent_chunk_size <= 0:
        raise ValueError("parent_chunk_size must be greater than 0")
    if child_chunk_size <= 0:
        raise ValueError("child_chunk_size must be greater than 0")
    if child_chunk_overlap < 0:
        raise ValueError("child_chunk_overlap must be greater than or equal to 0")
    if child_chunk_overlap >= child_chunk_size:
        raise ValueError("child_chunk_overlap must be smaller than child_chunk_size")


def _document_sections(document: ParsedPdfDocument) -> list[ParsedPdfSection]:
    if document.sections:
        return document.sections
    if not document.text.strip():
        return []
    return [
        ParsedPdfSection(
            section_id="document",
            title="Document",
            page_number=document.pages[0].page_number if document.pages else 1,
            char_start=0,
            char_end=len(document.text),
            text=document.text.strip(),
        )
    ]


def _parent_spans(text: str, base_offset: int, max_size: int) -> list[_TextSpan]:
    paragraphs = _paragraph_spans(text, base_offset)
    if not paragraphs:
        return []

    parents: list[_TextSpan] = []
    current_start: int | None = None
    current_end: int | None = None
    for paragraph in paragraphs:
        if len(paragraph.text) > max_size:
            if current_start is not None and current_end is not None:
                parents.append(_trim_span(text, base_offset, current_start - base_offset, current_end - base_offset))
                current_start = None
                current_end = None
            parents.extend(_window_spans(paragraph.text, paragraph.char_start, max_size, overlap=0))
            continue

        if current_start is None or current_end is None:
            current_start = paragraph.char_start
            current_end = paragraph.char_end
            continue

        if paragraph.char_end - current_start > max_size:
            parents.append(_trim_span(text, base_offset, current_start - base_offset, current_end - base_offset))
            current_start = paragraph.char_start
        current_end = paragraph.char_end

    if current_start is not None and current_end is not None:
        parents.append(_trim_span(text, base_offset, current_start - base_offset, current_end - base_offset))
    return parents


def _child_spans(
    text: str,
    base_offset: int,
    max_size: int,
    overlap: int,
) -> list[_TextSpan]:
    spans: list[_TextSpan] = []
    for paragraph in _paragraph_spans(text, base_offset):
        if len(paragraph.text) <= max_size:
            spans.append(paragraph)
        else:
            spans.extend(_window_spans(paragraph.text, paragraph.char_start, max_size, overlap=overlap))
    return spans


def _paragraph_spans(text: str, base_offset: int) -> list[_TextSpan]:
    spans: list[_TextSpan] = []
    for match in _PARAGRAPH_RE.finditer(text):
        spans.append(_trim_span(text, base_offset, match.start(), match.end()))
    return [span for span in spans if span.text]


def _window_spans(text: str, base_offset: int, max_size: int, *, overlap: int) -> list[_TextSpan]:
    spans: list[_TextSpan] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + max_size, text_length)
        if end < text_length:
            end = _prefer_word_boundary(text, start, end, max_size)
        span = _trim_span(text, base_offset, start, end)
        if span.text:
            spans.append(span)
        if end >= text_length:
            break
        # Start the next window on a word boundary so overlapped chunks never
        # begin mid-word; fall back to the window end if alignment stalls.
        aligned_start = _align_overlap_start(text, end - overlap)
        start = aligned_start if aligned_start > start else end
    return spans


def _prefer_word_boundary(text: str, start: int, end: int, max_size: int) -> int:
    boundary = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
    if boundary > start + max_size // 2:
        return boundary
    return end


def _align_overlap_start(text: str, pos: int) -> int:
    if pos <= 0:
        return 0
    boundary = max(text.rfind(" ", 0, pos), text.rfind("\n", 0, pos))
    if boundary == -1:
        return 0
    return boundary + 1


def _trim_span(text: str, base_offset: int, start: int, end: int) -> _TextSpan:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return _TextSpan(text=text[start:end], char_start=base_offset + start, char_end=base_offset + end)


def _build_chunk(
    document: ParsedPdfDocument,
    *,
    chunk_id: str,
    chunk_type: ChunkType,
    parent_chunk_id: str | None,
    span: _TextSpan,
    section: ParsedPdfSection,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document.document_id,
        chunk_type=chunk_type,
        parent_chunk_id=parent_chunk_id,
        text=span.text,
        version_hash=document.version_hash,
        source_url=document.source_url,
        section_id=section.section_id,
        section_title=section.title,
        page_number=_page_for_offset(document.pages, span.char_start) or section.page_number,
        char_start=span.char_start,
        char_end=span.char_end,
        token_count=_approx_token_count(span.text),
    )


def _page_for_offset(pages: list[ParsedPdfPage], char_start: int) -> int | None:
    for page in pages:
        if page.char_start <= char_start <= page.char_end:
            return page.page_number
    return None


def _chunk_id(document: ParsedPdfDocument, chunk_no: int) -> str:
    return f"{document.document_id}:{document.version_hash}:{chunk_no}"


def _approx_token_count(text: str) -> int:
    return len(text.split())
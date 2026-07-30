"""Tests for parent-child PDF chunking."""

from __future__ import annotations

import pytest

from apps.api.schemas.chunks import ChunkType
from src.ingestion.chunking import chunk_parsed_pdf
from src.ingestion.pdf_parser import ParsedPdfDocument, ParsedPdfPage, ParsedPdfSection


def test_chunk_parsed_pdf_creates_section_parents_and_paragraph_children() -> None:
    text = "I. INTRODUCTION\nFirst paragraph.\n\nSecond paragraph.\nII. SCOPE\nThird paragraph."
    first_end = text.index("II. SCOPE")
    document = _document(
        text=text,
        sections=[
            ParsedPdfSection(
                section_id="i-introduction",
                title="I. INTRODUCTION",
                page_number=1,
                char_start=0,
                char_end=first_end,
                text=text[:first_end].strip(),
            ),
            ParsedPdfSection(
                section_id="ii-scope",
                title="II. SCOPE",
                page_number=2,
                char_start=first_end,
                char_end=len(text),
                text=text[first_end:].strip(),
            ),
        ],
        pages=[
            ParsedPdfPage(page_number=1, text=text[:first_end].rstrip(), char_start=0, char_end=first_end - 1),
            ParsedPdfPage(page_number=2, text=text[first_end:], char_start=first_end, char_end=len(text)),
        ],
    )

    chunks = chunk_parsed_pdf(document)

    parents = [chunk for chunk in chunks if chunk.chunk_type == ChunkType.PARENT]
    children = [chunk for chunk in chunks if chunk.chunk_type == ChunkType.CHILD]
    assert [parent.section_id for parent in parents] == ["i-introduction", "ii-scope"]
    assert len(children) == 3
    assert all(child.parent_chunk_id in {parent.chunk_id for parent in parents} for child in children)
    assert children[0].text == "I. INTRODUCTION\nFirst paragraph."
    assert children[0].char_start == 0
    assert children[0].char_end == len(children[0].text)
    assert children[-1].page_number == 2
    assert chunks[0].version_hash == "a" * 64
    assert chunks[0].source_url == "https://www.fda.gov/media/example/download"


def test_chunk_parsed_pdf_falls_back_to_document_parent_without_sections() -> None:
    document = _document(text="Standalone paragraph.\n\nAnother paragraph.", sections=[])

    chunks = chunk_parsed_pdf(document)

    assert chunks[0].chunk_type == ChunkType.PARENT
    assert chunks[0].section_id == "document"
    assert [chunk.text for chunk in chunks[1:]] == ["Standalone paragraph.", "Another paragraph."]


def test_chunk_parsed_pdf_splits_long_child_with_overlap() -> None:
    document = _document(
        text="I. INTRODUCTION\nAlpha beta gamma delta epsilon zeta eta theta iota kappa.",
        sections=[
            ParsedPdfSection(
                section_id="i-introduction",
                title="I. INTRODUCTION",
                page_number=1,
                char_start=0,
                char_end=70,
                text="I. INTRODUCTION\nAlpha beta gamma delta epsilon zeta eta theta iota kappa.",
            )
        ],
    )

    chunks = chunk_parsed_pdf(document, child_chunk_size=30, child_chunk_overlap=6)
    children = [chunk for chunk in chunks if chunk.chunk_type == ChunkType.CHILD]

    assert len(children) > 1
    assert all(len(child.text) <= 30 for child in children)
    assert children[1].char_start < children[0].char_end
    # Overlapped windows must start on a word boundary, never mid-word.
    for child in children:
        assert not child.text[:1].isspace()
        if child.char_start > 0:
            assert document.text[child.char_start - 1] in " \n\t"


def test_chunk_parsed_pdf_splits_large_section_into_multiple_parents() -> None:
    text = "I. INTRODUCTION\nFirst paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    document = _document(
        text=text,
        sections=[
            ParsedPdfSection(
                section_id="i-introduction",
                title="I. INTRODUCTION",
                page_number=1,
                char_start=0,
                char_end=len(text),
                text=text,
            )
        ],
    )

    chunks = chunk_parsed_pdf(document, parent_chunk_size=40)

    parents = [chunk for chunk in chunks if chunk.chunk_type == ChunkType.PARENT]
    assert len(parents) == 2
    assert all(parent.section_id == "i-introduction" for parent in parents)


def test_chunk_parsed_pdf_rejects_invalid_sizes() -> None:
    document = _document(text="Body")

    with pytest.raises(ValueError, match="child_chunk_overlap"):
        chunk_parsed_pdf(document, child_chunk_size=10, child_chunk_overlap=10)


def _document(
    *,
    text: str,
    sections: list[ParsedPdfSection] | None = None,
    pages: list[ParsedPdfPage] | None = None,
) -> ParsedPdfDocument:
    return ParsedPdfDocument(
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        text=text,
        pages=pages or [ParsedPdfPage(page_number=1, text=text, char_start=0, char_end=len(text))],
        sections=sections or [],
        tables=[],
    )
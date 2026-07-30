"""Tests for PDF text and section parsing helpers."""

from __future__ import annotations

import pytest
import src.ingestion.pdf_parser as pdf_parser

from src.ingestion.pdf_parser import (
    ParsedPdfTable,
    extract_tables_with_unstructured,
    parse_pdf_bytes,
)


def test_parse_pdf_bytes_extracts_pages_offsets_and_sections() -> None:
    """Parser extracts page text, page offsets, and coarse section spans."""
    document = parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(
            [
                "I. INTRODUCTION\nThis guidance explains scope.",
                "II. RECOMMENDATIONS\nApplicants should retain records.",
            ]
        ),
    )

    assert document.document_id == "example-guidance"
    assert len(document.pages) == 2
    assert document.pages[0].page_number == 1
    assert document.pages[0].char_start == 0
    assert document.pages[1].char_start == document.pages[0].char_end + 1
    assert [section.title for section in document.sections] == [
        "I. INTRODUCTION",
        "II. RECOMMENDATIONS",
    ]
    assert document.sections[0].page_number == 1
    assert document.sections[1].text.startswith("II. RECOMMENDATIONS")
    assert document.tables == []
    for section in document.sections:
        assert document.text[section.char_start : section.char_end].strip() == section.text


def test_parse_pdf_bytes_includes_extracted_tables() -> None:
    """Parser carries table extraction results alongside text and sections."""
    table = ParsedPdfTable(
        table_id="table-1",
        page_number=2,
        text="Column A | Column B",
        html="<table><tr><td>Column A</td><td>Column B</td></tr></table>",
    )

    document = parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(["I. INTRODUCTION\nBody text"]),
        table_extractor=lambda data: [table],
    )

    assert document.tables == [table]


def test_parse_pdf_bytes_can_opt_into_unstructured_table_extraction(monkeypatch) -> None:
    """Callers can request the default Unstructured extractor explicitly."""
    table = ParsedPdfTable(table_id="table-1", page_number=1, text="A | B")
    monkeypatch.setattr(pdf_parser, "extract_tables_with_unstructured", lambda data: [table])

    document = pdf_parser.parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(["I. INTRODUCTION\nBody text"]),
        extract_tables=True,
    )

    assert document.tables == [table]


def test_parse_pdf_bytes_preserves_preamble_before_first_heading() -> None:
    """Cover-page text before the first heading is retained as a preamble section."""
    document = parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(
            ["Contains Nonbinding Recommendations\nIssued July 2026\nI. INTRODUCTION\nBody text"]
        ),
    )

    assert [section.title for section in document.sections] == ["Preamble", "I. INTRODUCTION"]
    assert document.sections[0].section_id == "preamble"
    assert document.sections[0].text == "Contains Nonbinding Recommendations\nIssued July 2026"
    assert document.text[document.sections[0].char_start : document.sections[0].char_end].strip() == document.sections[0].text


def test_parse_pdf_bytes_returns_no_sections_when_no_headings_detected() -> None:
    """Documents without detectable headings keep page text but have no sections."""
    document = parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(["This document has paragraph text only."]),
    )

    assert document.text == "This document has paragraph text only."
    assert document.sections == []


def test_parse_pdf_bytes_sections_can_span_pages() -> None:
    """Section ranges can span page boundaries and still map to full document text."""
    document = parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(
            [
                "I. INTRODUCTION\nThis starts on page one.",
                "Continues on page two.\nII. BACKGROUND\nNext section.",
            ]
        ),
    )

    introduction = document.sections[0]
    assert introduction.title == "I. INTRODUCTION"
    assert "Continues on page two." in introduction.text
    assert document.text[introduction.char_start : introduction.char_end].strip() == introduction.text


def test_parse_pdf_bytes_heading_offsets_handle_crlf_text() -> None:
    """CRLF page text does not drift heading offsets after earlier line breaks."""
    document = parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(["Cover line\r\nI. INTRODUCTION\r\nBody text"]),
    )

    introduction = document.sections[1]
    assert document.text[introduction.char_start : introduction.char_end].strip() == introduction.text


def test_parse_pdf_bytes_avoids_common_false_positive_headings() -> None:
    """Numbered sentences and single all-caps warnings are not treated as headings."""
    document = parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: _FakePdfDocument(
            ["1. The applicant must retain records.\nWARNING\nBACKGROUND\nActual section text"]
        ),
    )

    assert [section.title for section in document.sections] == ["Preamble", "BACKGROUND"]


def test_parse_pdf_bytes_closes_document() -> None:
    """Parser closes PyMuPDF-like documents after extraction."""
    fake_document = _FakePdfDocument(["BACKGROUND\nText"])

    parse_pdf_bytes(
        b"pdf bytes",
        document_id="example-guidance",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        opener=lambda data: fake_document,
    )

    assert fake_document.closed is True


def test_parse_pdf_bytes_reports_missing_pymupdf(monkeypatch) -> None:
    """A missing PyMuPDF dependency produces an actionable runtime error."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fitz":
            raise ImportError("missing fitz")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="PyMuPDF is required"):
        parse_pdf_bytes(
            b"pdf bytes",
            document_id="example-guidance",
            version_hash="a" * 64,
            source_url="https://www.fda.gov/media/example/download",
        )


def test_extract_tables_with_unstructured_reports_missing_dependency(monkeypatch) -> None:
    """A missing Unstructured dependency produces an actionable runtime error."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "unstructured.partition.pdf":
            raise ImportError("missing unstructured")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="Unstructured is required"):
        extract_tables_with_unstructured(b"pdf bytes")


class _FakePdfDocument:
    def __init__(self, page_texts: list[str]) -> None:
        self.page_texts = page_texts
        self.closed = False

    def __len__(self) -> int:
        return len(self.page_texts)

    def load_page(self, index: int):
        return _FakePdfPage(self.page_texts[index])

    def close(self) -> None:
        self.closed = True


class _FakePdfPage:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_text(self, kind: str) -> str:
        assert kind == "text"
        return self.text
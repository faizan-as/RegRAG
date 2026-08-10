"""Tests for bounded local FDA catalog seeding."""

from __future__ import annotations

import json

import pytest

from src.ingestion.local_seed import directly_downloadable_rows


def test_directly_downloadable_rows_filters_and_limits_catalog() -> None:
    source = json.dumps(
        [
            {"title": "Landing only", "field_associated_media_2": ""},
            {"title": "First PDF", "field_associated_media_2": "<a>PDF</a>"},
            {"title": "Second PDF", "field_associated_media_2": "<a>PDF</a>"},
        ]
    ).encode()

    selected = json.loads(directly_downloadable_rows(source, limit=1))

    assert [row["title"] for row in selected] == ["First PDF"]


def test_directly_downloadable_rows_requires_pdf() -> None:
    with pytest.raises(ValueError, match="directly downloadable"):
        directly_downloadable_rows(b'[{"field_associated_media_2": ""}]', limit=1)

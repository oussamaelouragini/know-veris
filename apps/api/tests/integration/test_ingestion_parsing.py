"""Parsers, language detection, and chunker against the bootstrap corpus.

No Ollama / DB involved — pure text extraction and splitting on the committed
synthetic documents.
"""

from pathlib import Path

import pytest

from app.services.ingestion.chunker import chunk_blocks, estimate_tokens
from app.services.ingestion.language import detect_language, fts_config_for
from app.services.ingestion.parsers import (
    DOCX_MIME,
    PDF_MIME,
    parse_document,
)

BOOTSTRAP = Path(__file__).parents[1] / "data" / "bootstrap"

FR_PDF = BOOTSTRAP / "fr-obligations-vigilance.pdf"
EN_PDF = BOOTSTRAP / "en-sanctions-screening.pdf"
EN_DOCX = BOOTSTRAP / "en-customer-due-diligence.docx"
AR_DOCX = BOOTSTRAP / "ar-alainaya-alwajiba.docx"
FR_DOCX = BOOTSTRAP / "fr-declaration-soupcon.docx"


def test_pdf_blocks_are_page_anchored():
    result = parse_document(FR_PDF, PDF_MIME)
    assert result.page_count == 2
    assert result.blocks, "expected non-empty PDF text"
    for block in result.blocks:
        assert block.page_number in (1, 2)
        assert block.section_title is None
        assert block.text.strip()


def test_docx_blocks_are_section_anchored():
    result = parse_document(EN_DOCX, DOCX_MIME)
    assert result.page_count is None
    assert result.blocks
    for block in result.blocks:
        assert block.page_number is None
        assert block.section_title  # non-null anchor (CHECK constraint)
        assert block.text.strip()


@pytest.mark.parametrize(
    ("path", "mime", "expected"),
    [
        (FR_PDF, PDF_MIME, "fr"),
        (EN_PDF, PDF_MIME, "en"),
        (EN_DOCX, DOCX_MIME, "en"),
        (AR_DOCX, DOCX_MIME, "ar"),
        (FR_DOCX, DOCX_MIME, "fr"),
    ],
)
def test_language_detection(path, mime, expected):
    result = parse_document(path, mime)
    sample = "\n".join(b.text for b in result.blocks)
    assert detect_language(sample) == expected


def test_fts_config_mapping():
    assert fts_config_for("fr") == "french"
    assert fts_config_for("en") == "english"
    assert fts_config_for("ar") == "arabic"
    assert fts_config_for(None) == "simple"
    assert fts_config_for("de") == "simple"


def test_every_chunk_keeps_a_source_anchor():
    for path, mime in [(FR_PDF, PDF_MIME), (AR_DOCX, DOCX_MIME)]:
        result = parse_document(path, mime)
        chunks = chunk_blocks(result.blocks)
        assert chunks
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.content.strip()
            # ADR-005: page OR section, never neither.
            assert (chunk.page_number is not None) or (chunk.section_title is not None)


def test_estimate_tokens_monotonic():
    assert estimate_tokens("") == 1
    assert estimate_tokens("one two three") < estimate_tokens("one two three four five six")

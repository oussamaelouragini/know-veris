"""Document parsers — extract text with a source anchor for every block.

The anchor is the project's reason to exist (ADR-005): a PDF block carries its
`page_number`, a DOCX block carries its `section_title`. Every returned block
has exactly one of the two set, so a citation is always possible downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document as DocxDocument

# DOCX text before the first heading still needs a non-null anchor (the CHECK
# constraint), so it is attributed to this default section.
_DEFAULT_SECTION = "Introduction"

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class SourceBlock:
    """A contiguous span of text and where it came from.

    Exactly one of page_number / section_title is set — PDF vs DOCX (ADR-005).
    """

    text: str
    page_number: int | None = None
    section_title: str | None = None


@dataclass
class ParseResult:
    blocks: list[SourceBlock]
    page_count: int | None  # None for DOCX — Word paginates only at render time


def parse_pdf(path: str | Path) -> ParseResult:
    """One block per page; each block anchored by its 1-based page number."""
    blocks: list[SourceBlock] = []
    with fitz.open(path) as doc:
        page_count = doc.page_count
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                blocks.append(SourceBlock(text=text, page_number=index))
    return ParseResult(blocks=blocks, page_count=page_count)


def _is_heading(style_name: str | None) -> bool:
    if not style_name:
        return False
    name = style_name.lower()
    return name.startswith("heading") or name == "title"


def parse_docx(path: str | Path) -> ParseResult:
    """One block per heading-delimited section; anchored by section title.

    Paragraphs are accumulated under the most recent Heading/Title; text before
    the first heading falls under a default `Introduction` section so it still
    carries an anchor.
    """
    doc = DocxDocument(str(path))
    blocks: list[SourceBlock] = []
    current_title = _DEFAULT_SECTION
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            blocks.append(SourceBlock(text=text, section_title=current_title))
        buffer.clear()

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if _is_heading(para.style.name if para.style else None):
            flush()
            current_title = text
        else:
            buffer.append(text)
    flush()

    return ParseResult(blocks=blocks, page_count=None)


def parse_document(path: str | Path, mime_type: str) -> ParseResult:
    """Dispatch on MIME type. Raises ValueError for unsupported types."""
    if mime_type == PDF_MIME:
        return parse_pdf(path)
    if mime_type == DOCX_MIME:
        return parse_docx(path)
    raise ValueError(f"Unsupported document type: {mime_type}")

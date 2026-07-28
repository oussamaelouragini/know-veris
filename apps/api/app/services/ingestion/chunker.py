"""Chunker — split each source block into overlapping, anchor-preserving chunks.

Blocks are split independently so a chunk never spans two pages/sections and
always keeps a single source anchor (ADR-005). Sizes come from settings
(chunk_size=500, overlap=80 — CPU budget, docs.md/PLAN §5).

Length is measured in *estimated tokens*: the real BGE-M3 tokenizer lives in
Ollama, not this process, so we approximate. Exactness is not required here — it
only has to be consistent; the hard context ceiling is enforced later by Ollama
`num_ctx`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings
from app.services.ingestion.parsers import SourceBlock

settings = get_settings()

_WORD = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    """Rough multilingual token estimate (~1.3 tokens per whitespace word)."""
    return max(1, round(len(_WORD.findall(text)) * 1.3))


@dataclass
class Chunk:
    content: str
    chunk_index: int
    page_number: int | None
    section_title: str | None


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=estimate_tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_blocks(blocks: list[SourceBlock]) -> list[Chunk]:
    """Flatten blocks into globally-indexed chunks, carrying each block's anchor."""
    splitter = _splitter()
    chunks: list[Chunk] = []
    for block in blocks:
        for piece in splitter.split_text(block.text):
            content = piece.strip()
            if not content:
                continue
            chunks.append(
                Chunk(
                    content=content,
                    chunk_index=len(chunks),
                    page_number=block.page_number,
                    section_title=block.section_title,
                )
            )
    return chunks

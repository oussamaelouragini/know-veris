"""Prompt construction for grounded generation.

Two hard rules from the project conventions shape this module:

1. The **system prompt is stable** — never interpolated with variable content —
   so Ollama's prefix cache is hit on every request (docs.md §CPU constraints).
   Everything variable (context, question, target language) goes in the *user*
   message instead.
2. Each context block is labelled `[S1]..[Sn]` and carries its citation anchor
   (document + page/section), because the model is told to cite those markers
   and a downstream guardrail validates them (ADR-005).
"""

from __future__ import annotations

from app.services.rag.retriever import RetrievedChunk

# The literal the model must emit when the context does not answer the question.
# Kept out of the prose so post-generation code can match it exactly.
NOT_FOUND_SENTINEL = "INFORMATION_NOT_FOUND"

# Stable across every request — do NOT interpolate anything into this string.
SYSTEM_PROMPT = (
    "You are KnowVeris, an assistant for bank employees. "
    "Answer the question using ONLY the information in the provided context. "
    "Do not use any outside knowledge. "
    "Cite every claim with its source marker in square brackets, e.g. [S1] or [S2]. "
    f"If the context does not contain the answer, reply with exactly {NOT_FOUND_SENTINEL} "
    "and nothing else. "
    "Answer in the language requested by the user."
)

# Human-readable language names for the explicit instruction. A 4B model drifts
# language, so we inject the target rather than let it guess (PLAN Flow B).
_LANGUAGE_NAMES = {
    "fr": "French",
    "en": "English",
    "ar": "Arabic",
}


def _anchor(chunk: RetrievedChunk) -> str:
    """Compact source descriptor: `doc="x.pdf" page=12` or `doc="y.docx" §3.2`."""
    if chunk.page_number is not None:
        return f'doc="{chunk.filename}" page={chunk.page_number}'
    return f'doc="{chunk.filename}" §{chunk.section_title}'


def build_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as labelled `[Sx]` blocks for the prompt."""
    return "\n\n".join(
        f"[S{i}] {_anchor(chunk)}\n{chunk.content}" for i, chunk in enumerate(chunks, start=1)
    )


def build_user_prompt(question: str, chunks: list[RetrievedChunk], language: str | None) -> str:
    """Assemble the variable user message: language instruction + context + question."""
    language_name = _LANGUAGE_NAMES.get(language or "", "the language of the question")
    context = build_context(chunks)
    return f"Answer in {language_name}.\n\nContext:\n{context}\n\nQuestion: {question}"

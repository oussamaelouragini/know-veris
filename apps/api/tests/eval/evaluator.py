"""Golden-set evaluation harness.

Two layers, deliberately separated by cost:

* **Retrieval eval** (fast, embeddings only) — Recall@k, MRR, and the
  guardrail-1 refusal decision (best cosine vs threshold). Because it needs no
  generation it doubles as the *threshold-calibration* tool: sweep the threshold
  and read off correct- vs false-refusal rates.
* **Generation eval** (slow, ~minutes/question on CPU) — answer language,
  expected-substring coverage, and citation validity, via the real pipeline.
  Opt-in; never part of the fast suite.

Document-level recall (does the expected file appear in the top-k) is the robust
metric used here; page/section precision is left for the demo-corpus golden set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.config import get_settings
from app.services.rag.retriever import RetrievedChunk, retrieve

settings = get_settings()

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.yaml"


@dataclass
class GoldenItem:
    id: str
    question: str
    lang: str
    category: str
    type: str
    expected_docs: set[str]
    expected_answer_contains: list[str]
    must_refuse: bool


@dataclass
class ItemRetrieval:
    item: GoldenItem
    retrieved: list[RetrievedChunk]
    best_score: float  # max cosine over the top rerank_top_k (the guardrail-1 signal)


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[GoldenItem]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items: list[GoldenItem] = []
    for entry in raw:
        expected_docs = {src["document"] for src in entry.get("expected_sources", [])}
        items.append(
            GoldenItem(
                id=entry["id"],
                question=entry["question"],
                lang=entry["lang"],
                category=entry["category"],
                type=entry["type"],
                expected_docs=expected_docs,
                expected_answer_contains=entry.get("expected_answer_contains", []),
                must_refuse=entry["must_refuse"],
            )
        )
    return items


async def run_retrieval(
    items: list[GoldenItem],
    db,
    *,
    top_k: int = 10,
    use_fts: bool = True,
) -> list[ItemRetrieval]:
    """Retrieve for every item with real embeddings (needs Ollama + indexed corpus)."""
    results: list[ItemRetrieval] = []
    for item in items:
        retrieved = await retrieve(
            item.question, db, top_k=top_k, language=item.lang, use_fts=use_fts
        )
        # Guardrail 1 looks at the top rerank_top_k only.
        head = retrieved[: settings.rerank_top_k]
        best_score = max((c.score for c in head), default=0.0)
        results.append(ItemRetrieval(item=item, retrieved=retrieved, best_score=best_score))
    return results


def _ranked_docs(retrieved: list[RetrievedChunk]) -> list[str]:
    """Filenames in rank order, de-duplicated (keep first occurrence)."""
    seen: list[str] = []
    for chunk in retrieved:
        if chunk.filename not in seen:
            seen.append(chunk.filename)
    return seen


def _first_hit_rank(retrieved: list[RetrievedChunk], expected: set[str]) -> int | None:
    for rank, doc in enumerate(_ranked_docs(retrieved), start=1):
        if doc in expected:
            return rank
    return None


@dataclass
class RetrievalMetrics:
    n_positive: int
    n_negative: int
    recall_at: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    correct_refusal_rate: float = 0.0  # negatives correctly below threshold
    false_refusal_rate: float = 0.0  # positives wrongly below threshold


def retrieval_metrics(
    results: list[ItemRetrieval],
    *,
    threshold: float | None = None,
    k_values: tuple[int, ...] = (3, 10),
) -> RetrievalMetrics:
    thr = threshold if threshold is not None else settings.relevance_threshold
    positives = [r for r in results if not r.item.must_refuse]
    negatives = [r for r in results if r.item.must_refuse]

    recall_at: dict[int, float] = {}
    for k in k_values:
        hits = [
            1.0 if set(_ranked_docs(r.retrieved)[:k]) & r.item.expected_docs else 0.0
            for r in positives
        ]
        recall_at[k] = sum(hits) / len(hits) if hits else 0.0

    rr = []
    for r in positives:
        rank = _first_hit_rank(r.retrieved, r.item.expected_docs)
        rr.append(1.0 / rank if rank else 0.0)
    mrr = sum(rr) / len(rr) if rr else 0.0

    correct = [1.0 if r.best_score < thr else 0.0 for r in negatives]
    false = [1.0 if r.best_score < thr else 0.0 for r in positives]

    return RetrievalMetrics(
        n_positive=len(positives),
        n_negative=len(negatives),
        recall_at=recall_at,
        mrr=mrr,
        correct_refusal_rate=sum(correct) / len(correct) if correct else 0.0,
        false_refusal_rate=sum(false) / len(false) if false else 0.0,
    )


def sweep_threshold(
    results: list[ItemRetrieval], thresholds: list[float]
) -> list[tuple[float, float, float]]:
    """For each threshold → (threshold, correct_refusal_rate, false_refusal_rate)."""
    rows = []
    for thr in thresholds:
        m = retrieval_metrics(results, threshold=thr)
        rows.append((thr, m.correct_refusal_rate, m.false_refusal_rate))
    return rows

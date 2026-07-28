"""Golden-set retrieval evaluation (live — marked `eval`).

Run explicitly:  pytest tests/eval -m eval -s

Measures Recall@k / MRR and the guardrail-1 refusal behaviour on the bootstrap
corpus, prints a report, and asserts the retrieval targets from PLAN §1. The
generation-quality metrics (answer language, substrings, citations) are a
separate opt-in path — each answer costs minutes on CPU.
"""

import pytest
from evaluator import (
    load_golden_set,
    retrieval_metrics,
    run_retrieval,
    sweep_threshold,
)

from app.db.session import SessionLocal

pytestmark = pytest.mark.eval


def _print_metrics(title, m):
    print(f"\n== {title} ==")
    print(f"  items: {m.n_positive} positive / {m.n_negative} negative")
    for k, v in m.recall_at.items():
        print(f"  Recall@{k}: {v:.2%}")
    print(f"  MRR: {m.mrr:.3f}")
    print(f"  correct-refusal (negatives): {m.correct_refusal_rate:.2%}")
    print(f"  false-refusal   (positives): {m.false_refusal_rate:.2%}")


async def test_golden_set_retrieval_report(indexed_corpus):
    items = load_golden_set()
    print(f"\nGolden set: {len(items)} questions")

    async with SessionLocal() as db:
        hybrid = await run_retrieval(items, db, top_k=10, use_fts=True)
    async with SessionLocal() as db:
        vector_only = await run_retrieval(items, db, top_k=10, use_fts=False)

    m_hybrid = retrieval_metrics(hybrid)
    m_vector = retrieval_metrics(vector_only)
    _print_metrics("Hybrid (vector + FTS + RRF)", m_hybrid)
    _print_metrics("Vector-only", m_vector)

    print("\n== Threshold sweep (correct-refusal / false-refusal) ==")
    for thr, correct, false in sweep_threshold(
        hybrid, [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    ):
        print(f"  thr={thr:.2f}  correct-refusal={correct:.0%}  false-refusal={false:.0%}")

    # Per-item misses, to make failures diagnosable.
    for r in hybrid:
        if not r.item.must_refuse:
            docs = [c.filename for c in r.retrieved[:3]]
            hit = bool(set(docs) & r.item.expected_docs)
            if not hit:
                print(f"  MISS {r.item.id}: got {docs}, wanted {r.item.expected_docs}")

    # PLAN §1 retrieval target.
    assert m_hybrid.recall_at[3] >= 0.85, f"Recall@3 {m_hybrid.recall_at[3]:.2%} < 85%"
    # Hybrid must not regress against vector-only on this corpus.
    assert m_hybrid.recall_at[3] >= m_vector.recall_at[3]


async def test_threshold_is_calibratable(indexed_corpus):
    """A threshold must exist that meets both refusal targets (PLAN §1)."""
    items = load_golden_set()
    async with SessionLocal() as db:
        results = await run_retrieval(items, db, top_k=10, use_fts=True)

    ok = [
        (thr, c, f)
        for thr, c, f in sweep_threshold(results, [round(0.20 + 0.025 * i, 3) for i in range(20)])
        if c >= 0.90 and f <= 0.10
    ]
    print("\n== Thresholds meeting both targets (correct≥90%, false≤10%) ==")
    for thr, c, f in ok:
        print(f"  thr={thr:.3f}  correct-refusal={c:.0%}  false-refusal={f:.0%}")
    assert ok, "no threshold meets correct-refusal≥90% and false-refusal≤10%"

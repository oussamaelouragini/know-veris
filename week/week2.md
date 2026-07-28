# Week 2 — Summary

RAG quality + complete API. Branch `feat/week2-rag-quality` (off `project`, never `main`).
Order followed: PLAN D1→D5, but the golden set was built early so every later change is
measured. Default suite **44 passed, 2 eval deselected**; live golden-set eval run separately.

## D1 — Hybrid retrieval (vector + FTS + RRF)

1. Hybrid retriever — `app/services/rag/retriever.py` — added a per-language Postgres FTS leg (`websearch_to_tsquery` on the detected language config + `ts_rank_cd`) alongside the pgvector leg, fused by **Reciprocal Rank Fusion** (k=60). Fusion decides ordering; each chunk keeps its **cosine** similarity as `score` (so Guardrail 1 stays interpretable) and gains `rrf_score`. `use_fts` toggle for A/B; `rerank_score` field added.
2. Guardrail 1 signal — `app/services/rag/pipeline.py` — refusal now uses `max(cosine)` across results (RRF may not order by cosine) instead of `chunks[0].score`.
3. Hybrid test — `test_retriever.py` — seeded an EN doc with a keyword chunk (vector-far) + generic chunk (vector-near); confirmed FTS/RRF surfaces the "PEP" chunk above the vector-closest one, and `use_fts=False` reverts. (32 passed.)
4. Commit — `8e31ae1` feat(rag): hybrid retrieval — pgvector + Postgres FTS fused with RRF.

## D5 (built early) — Golden set + evaluation harness

5. Golden set — `tests/eval/golden_set.yaml` — 18 questions on the bootstrap corpus (FR/EN/AR; factual/multi_hop/negative/acronym/cross_lingual), `expected_sources` + `expected_answer_contains` + `must_refuse`. (The ~35-question FATF demo golden set waits on `corpus/demo/`.)
6. Evaluator — `tests/eval/evaluator.py` — loads the set, runs retrieval, computes **Recall@k, MRR**, and guardrail-1 **correct/false-refusal** rates; `sweep_threshold` for calibration. Retrieval eval is fast (no generation); generation eval is a separate opt-in path.
7. Eval fixture + tests — `tests/eval/conftest.py` (+`test_golden_set.py`) — ingest the 5 bootstrap docs with **real** bge-m3 into the isolated test DB once, skip if Ollama down; marked `eval` and excluded from the default suite (`pytest tests/eval -m eval`). Fixed an asyncio-loop leak by disposing the engine after the `asyncio.run` ingest.
8. 🎯 **First eval run** — **Recall@3 = 100%, Recall@10 = 100%, MRR = 0.929** (hybrid *and* vector-only — the 5-doc corpus is too small to separate them on aggregate recall; the FTS mechanism is proven by step 3). **Threshold sweep exposed a real refusal bug**: at 0.35, correct-refusal = **0%** (bge-m3 scores unrelated questions ~0.4–0.5); **0.50 → 100% correct-refusal at 7% false-refusal**.
9. Commit — `a219be0` feat(eval): golden set + retrieval evaluation harness.

## D2 — Reranker (flagged) + threshold calibration

10. Threshold calibrated — `app/core/config.py` + `.env(.example)` — `relevance_threshold` **0.35 → 0.50**, measured (step 8), applied to cosine (not the reranker scale).
11. Reranker — `app/services/rag/reranker.py` — feature-flagged bge-reranker-v2-m3 that **reorders + trims** the fused candidate pool; only sets `rerank_score`, leaves cosine `score` intact so the calibrated threshold stays valid. Heavy model lazy-imported (`FlagEmbedding`), scorer injectable so the default suite needs no torch.
12. Pipeline wiring — `pipeline.py` — when `reranker_enabled`, retrieve `retrieval_top_k` (20) then rerank to `rerank_top_k` (3); else fused top-3 directly.
13. Tests — `test_reranker.py` (unit: reorder/trim/keep-cosine) + `test_chat_endpoint.py` (enabled path pulls the full pool and reranks, stubbed scorer). (35 passed.)
14. Commit — `2b4b814` feat(rag): cross-encoder reranker (flagged) + threshold calibrated to 0.50.

## D3 — SSE streaming

15. Streaming generator — `app/services/rag/generator.py` — refactored to share one payload; added `stream_generate` (Ollama `stream=true` → token deltas + a terminal `StreamChunk` with timings).
16. Streaming pipeline — `pipeline.py` — `answer_question_stream` yields `("token", delta)` then one `("final", ChatAnswer)`; guardrail-1 refusals stream no tokens; sentinel refusal still wins at the end. Shared `_retrieve_chunks` / `_is_refusal` helpers.
17. SSE endpoint — `app/api/v1/endpoints/chat.py` — `POST /api/v1/chat/stream` (`text/event-stream`): `token` events then a `final` event with the full `ChatResponse`. Blocking `POST /chat` kept for tests + the current UI.
18. Tests — `test_chat_endpoint.py` — token-stream-then-final (citations in the final event) + refusal-streams-no-tokens, with a mocked stream. (37 passed.)
19. Commit — `3f75373` feat(chat): SSE streaming endpoint (POST /api/v1/chat/stream).

## D4 (part 1) — Document deletion + audit

20. Audit helper — `app/services/audit.py` — single writer for `audit_logs` (consistent action vocabulary, thin endpoints).
21. Delete service — `app/services/ingestion/uploader.py` — `delete_document` (DB row first → chunks cascade, citations keep history with nulled `chunk_id`; then remove the file) + `document_path`.
22. Endpoints — `app/api/v1/endpoints/documents.py` — `DELETE /api/v1/documents/{id}` (admin, 204/404) + audit on `document.uploaded` / `document.deleted`.
23. Tests — `test_documents_endpoint.py` — delete cascades chunks + writes audit + removes file; missing → 404. (39 passed.)
24. Commit — `3282ea9` feat(documents): delete endpoint (cascade + file removal) + audit logging.

## D4 (part 2) — admin/users via the Keycloak Admin REST API

25. Internal Keycloak URL — `app/core/config.py` + `.env(.example)` — added `keycloak_internal_url` (`http://keycloak:8080`) for server-to-server Admin REST + service-account token, distinct from the browser-facing `keycloak_url`.
26. Admin client — `app/services/keycloak/admin_client.py` — `KeycloakAdmin` async context manager (client_credentials on `knowveris-admin-cli`): `create_user`, `set_password`, `assign_realm_role`, `list_users`, `set_enabled`; `KeycloakConflict`(409) subclass.
27. Provisioning service — `app/services/keycloak/provisioning.py` — orchestrates create employee (Keycloak user → temp password → `employee` role) → mirror into `users` (keycloak_sub) → audit `user.created`, all in one commit; plus list / enable-disable / reset-password (temp password returned once).
28. Endpoints — `app/api/v1/endpoints/admin_users.py` (+ wired in `main.py`) — admin-only `POST /admin/users` (201, temp password once), `GET`, `PATCH /{id}` (enable/disable, 204), `POST /{id}/reset-password`. **No DELETE** — disable, never delete (traceability). Keycloak errors → 409/502.
29. Schemas — `app/schemas/admin_user.py` — `AdminUserCreate/Created/Read/Update`, `PasswordReset` (str email to avoid the `email-validator` dep).
30. Tests — `test_admin_users_endpoint.py` — Keycloak mocked: create provisions+mirrors+audits (create→password→role order), list, disable audit, reset-password secret, 403 non-admin. (**44 passed**.)
31. Commit — `c6d71e9` feat(admin): admin/users endpoints via Keycloak Admin REST API (service account).

## Final measurement + a config-reload catch

32. ⚠️ Env-reload catch — the calibrated `RELEVANCE_THRESHOLD=0.50` did not take effect until the api container was recreated: `.env` is read into the container env at `up` time, and the stale `0.35` env var overrode the new code default (env var > default in Pydantic). Fixed with `docker compose up -d api`; verified `get_settings().relevance_threshold == 0.5` in-container.
33. 🎯 **Week 2 measured checkpoint** (bootstrap golden set, calibrated threshold 0.50, hybrid): **Recall@3 = 100%, Recall@10 = 100%, MRR = 0.929, correct-refusal = 100%, false-refusal = 7.1%**. The "measured API" checkpoint is met.
34. Docs — updated `PLAN.md` (Week 2 rows ticked, checkpoint numbers) and this file.

## Status — Week 2 complete

**Done:** D1 hybrid · D2 reranker (flagged) + threshold calibration · D3 SSE · D4 doc-deletion+audit · D4 admin/users · golden set + eval harness (D5). Persistence was already done in Week 1. Default suite **44 passed, 2 eval deselected**; live golden-set eval green.

**Deferred (measurement-only, need external resources — feed the report, don't block Week 3):**

- **Live with/without-reranker precision/latency table** — needs `FlagEmbedding`+torch installed (~2 GB image/RAM; a confirmed infra decision). Reranker code + flag + wiring are done and unit-tested with a stub.
- **Quiet-machine latency re-benchmark** + `OLLAMA_NUM_PREDICT` tuning — needs the demo machine idle (VSCode/Chrome closed).
- **Generation-quality eval** (answer language / substrings / citations over the golden set) — retrieval eval is done; generation path is ~minutes/answer on CPU, run on demand.
- **~35-question FATF/ACPR demo golden set** — ✅ first slice authored: `tests/eval/golden_set_demo.yaml`, 15 questions on the real FATF 40 Recommendations (GAFI-2012 FR/EN/AR in `corpus/demo/`), kept separate from the bootstrap set. Type mix per PLAN §6 (5 factual · 3 multi_hop · 4 negative · 2 acronym · 1 cross_lingual; 6 FR / 5 EN / 4 AR); loads via the existing evaluator. Live retrieval/generation run against it is deferred to the demo machine (needs the demo PDFs indexed with bge-m3); ACPR/BCBS/EBA questions are added as those docs land (commit `e597116`).

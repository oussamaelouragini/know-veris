# Week 1 — Summary

Sequential steps of the Week 1 session: Ollama fix, DB foundation, auth, ingestion
pipeline, and the admin upload endpoint. Branch `feat/db-models-migrations`.

1. Diagnose Ollama models loss — `docker inspect` — ollama container had been destroyed & recreated (new container, RestartCount 0), not a config drift.
2. Confirm volume mount intact — `knowveris_ollama_models:/root/.ollama` correctly wired → one-time fix, not recurring.
3. Re-pull models into the container, one at a time — `docker compose exec ollama ollama pull bge-m3 / qwen3:4b-instruct-2507-q4_K_M / qwen3:1.7b`.
4. [Manual] Verify persistence — `docker compose down` + `up` — models survive restart; `ollama list` shows all 3 (bge-m3, qwen3:1.7b, qwen3:4b-instruct-2507-q4_K_M). Issue fully resolved.
5. Verify Postgres FTS (`Full Text Search`) configs — `docker compose exec postgres psql -tAc "SELECT cfgname FROM pg_ts_config"` — `arabic`, `french`, `english`, `simple` all present (PG16); Week 0 "arabic FTS absent" risk resolved, no `simple` fallback needed.
6. Verify extensions installed — `SELECT extname FROM pg_extension` — `vector`, `pg_trgm`, `uuid-ossp` present.
7. Update PLAN.md — check off Week 0 FTS/extension items, mark the arabic-FTS risk resolved.
8. Create feature branch — `git checkout -b feat/db-models-migrations` — no more direct work on `main`.
9. SQLAlchemy 2.0 (ORM) models — `backend/app/models/` — 7 tables (users, documents, document_chunks, conversations, messages, message_citations, audit_logs), native PG enums, `Vector(1024)`, `TSVECTOR`, page-or-section CHECK (ADR-005), cascade rules (ADR-006).
10. Async DB layer — `backend/app/db/` — `base.py` (constraint naming convention), `session.py` (async engine + `get_db`).
11. Alembic ( Alembic is the tool that manages database modifications ) setup — `backend/alembic/` (async `env.py`) + hand-written `0001_initial_schema.py` — (HNSW : Hierarchical Navigable Small World) ,(`vector_cosine_ops ,(Use cosine similarity to compare embeddings`) + (GIN :Generalized Inverted Index) (`content_tsv : Text Search Vector`) indexes, (enums : Status of a document) , CHECK.
12. Apply + verify migration — `docker compose exec api alembic upgrade head` — 7 tables + HNSW/GIN + CHECK + 3 enums; downgrade→upgrade round-trip clean; ORM insert/select round-trip OK.
13. Commit DB foundation — `git commit` — `9e0aa1d` feat: SQLAlchemy models, async DB layer, initial Alembic migration.
14. Security layer — `backend/app/core/security.py` — Keycloak JWKS validation (RS256, iss+aud), TTL key cache with rotation refetch, `get_current_user` (JIT provisioning, ADR-006), `require_admin` RBAC, `CurrentUser`/`AdminUser` aliases.
15. Security tests — `backend/tests/integration/test_security.py` + `tests/conftest.py` — self-signed RSA + stubbed JWKS: JIT create/promote, admin rejection, expired + wrong-audience → 401/403 (4 tests).
16. Commit security — `git commit` — `d0815ca` feat: JWT validation, RBAC deps, JIT provisioning.
17. Mount bootstrap corpus into api — `docker-compose.yml` (`./corpus/bootstrap:/app/tests/data/bootstrap:ro`) + `docker compose up -d api` — test suite can read the committed synthetic docs.
18. Parsers — `app/services/ingestion/parsers.py` — PyMuPDF per-page (`page_number`) + python-docx per-heading (`section_title`); every block carries exactly one anchor.
19. Language detection — `app/services/ingestion/language.py` — lingua FR/EN/AR + Postgres FTS config mapping.
20. Chunker — `app/services/ingestion/chunker.py` — RecursiveCharacterTextSplitter per-block (anchors survive), token-estimated length (chunk_size=500, overlap=80).
21. Embedder — `app/services/rag/embedder.py` — BGE-M3 batch/query embeddings via Ollama `/api/embed` (ADR-004), dimension-validated.
22. Indexer — `app/services/ingestion/indexer.py` — `PENDING→PARSING→EMBEDDING→INDEXED|FAILED` state machine, per-language `to_tsvector`, injectable embedder.
23. Ingestion tests — `test_ingestion_parsing.py` + `test_indexer.py` — parsing/language/chunker on corpus; indexer end-to-end with mocked embedder incl. real french-config FTS match (12 tests).
24. Commit ingestion — `git commit` — `fdc626b` feat: ingestion pipeline (parsers, chunker, language, embedder, indexer).
25. Upload service — `app/services/ingestion/uploader.py` — `register_upload`: SHA-256 dedup, save file, insert `Document(PENDING)`; `UnsupportedDocumentType`→415, `DuplicateDocument`→409.
26. Background worker — `app/workers/tasks.py` — `process_document` opens its own session and runs the indexer (PLAN Flow A).
27. Documents endpoint — `app/api/v1/endpoints/documents.py` + wired in `main.py` — `POST /api/v1/documents` (202 + schedule ingestion), `GET` list, `GET /{id}` status; admin-only.
28. Endpoint tests — `test_documents_endpoint.py` — 202+schedule, 409 dedup, 415 type, list/get/404, 403 non-admin (task stubbed → no Ollama; storage → tmp) (5 tests).
29. Commit upload endpoint — `git commit` — `5c671ec` feat: admin document upload endpoint + background ingestion wiring.
30. Full suite green — `docker compose exec api pytest -q` — 21 passed .
31. Retriever — `app/services/rag/retriever.py` — pgvector cosine top-k over `document_chunks` joined to `documents`, query embedding via BGE-M3 (injectable for tests) — ready to wire into the chat endpoint at J5.

## J5 — Walking skeleton: naive chat endpoint + first live end-to-end query

32. Prompt builder — `app/services/rag/prompt.py` — **stable** `SYSTEM_PROMPT` (never interpolated → Ollama prefix cache), `[Sx]` context blocks carrying each anchor, explicit language instruction, `INFORMATION_NOT_FOUND` sentinel.
33. Generator — `app/services/rag/generator.py` — Qwen3 via Ollama `/api/chat` (`stream:false`), `temperature=0`, `num_ctx=4096`, `num_thread=8`; returns text + timing counters (prompt/eval tokens, tok/s) for the model benchmark.
34. Chat pipeline — `app/services/rag/pipeline.py` — `answer_question`: detect language → retrieve top-3 → **Guardrail 1** (refuse before LLM if best score < threshold) → generate → sentinel check → **Guardrail 2** (keep only `[Sx]` citations that map to a supplied chunk; flag `unverified` if none) → persist conversation + user/assistant messages + `message_citations` + `audit_log`.
35. Chat schema + endpoint — `app/schemas/chat.py` + `app/api/v1/endpoints/chat.py` (wired in `main.py`) — `POST /api/v1/chat` (any authenticated user), thin: validate → delegate → serialize; `ConversationNotFound`→404.
36. Chat tests — `test_chat_endpoint.py` — grounded+cited (real seeded chunks for FK), Guardrail 1 refusal (no LLM call), unverified answer (no citation), unknown conversation→404 (retriever+generator mocked) (4 tests).
37. Full suite green — `docker compose exec api pytest -q` — **27 passed**.
38. 🎯 **First live end-to-end query** — real bge-m3 ingestion of the 5 bootstrap docs (lang ar/en/fr auto-detected, 3–4 chunks each, all INDEXED) + real Qwen3 generation. FR & EN questions → grounded, cited, cross-lingual retrieval confirmed (EN question cites a FR source [S3]); out-of-corpus crypto question → correct refusal via the `INFORMATION_NOT_FOUND` sentinel.
39. ⚠️ **Latency finding** — ~245–250 s per answered query, well over the 60–90 s budget (PLAN §5). Likely model-swap thrash: each query embeds with bge-m3 then generates with qwen3:4b, and the tight RAM budget forces Ollama to reload the 4B (cold prefill) every call. → motivates the J5 model benchmark (qwen3:4b vs qwen3:1.7b) and a keep-alive / ordering mitigation. Next session.

## J5 (cont.) — Latency root cause + model benchmark

40. Root cause found — `docker-compose.yml` had `OLLAMA_MAX_LOADED_MODELS: "1"` (hardcoded), so Ollama held exactly one model resident: every request evicted qwen3 to load bge-m3, then reloaded qwen3 (cold prefill). Keep-alive was irrelevant under a count cap of 1.
41. Fix — `OLLAMA_MAX_LOADED_MODELS` env-driven, set to **2** (hold bge-m3 + generation model together, as PLAN §5 RAM budget already assumes) + `OLLAMA_KEEP_ALIVE` 5m→**30m**; recreated the ollama container. **Confirmed**: per-call `load_ms` drops 28 s (cold, once per model) → ~0.7 s (warm) — no more per-request reload.
42. 🎯 **Benchmark** (5 bootstrap Q, FR×2/EN×2/AR×1, real retriever+prompt, warm) — **qwen3:4b: avg 225 s (34–354 s), 2.6 tok/s** · **qwen3:1.7b: avg 178 s (86–230 s), 3.8 tok/s**. Eviction is fixed, but raw CPU throughput is ~3× below PLAN's 6–9 tok/s estimate and both models miss the <90 s target — the machine was under full IDE load, and generations run long (300–700 tokens). Next levers: cap generation length (`num_predict` + concise instruction; measure on golden set), re-benchmark on a quiet machine (close VSCode/Chrome per PLAN §5), reconsider 1.7B as default.

## J5 (cont.) — num_predict cap + frontend walking skeleton

43. Generation cap — `ollama_num_predict` setting (default **-1 = off**), always passed in the Ollama options; ready to bound answer length in Week 2 measured on the golden set (commit `d52e7dd`). +4 generator unit tests (payload/options, timing parse, model override, empty-output guard) → **31 passed**.
44. Test-isolation fix — the J5 live ingestion had left 5 INDEXED bootstrap docs in the shared dev DB, which broke the documents/retriever integration tests (hash-dedup collision + extra retrieved chunks). Cleaned the live-E2E footprint; suite green again. (Lesson: these integration tests are not isolated from persistent rows — a dedicated test DB / transactional fixtures is a future cleanup.)
45. Frontend deps — `react-oidc-context` + `oidc-client-ts` added (only the minimum to purge the real OIDC+PKCE integration risk; TanStack Query/Axios/Router/shadcn stay in Week 3).
46. OIDC wiring — `src/lib/oidc.ts` (authority/realm/client from `VITE_*`, code+PKCE S256, localStorage store, post-redirect URL cleanup), `main.tsx` wraps `<App>` in `<AuthProvider>`.
47. Walking-skeleton UI — `src/App.tsx`: login/logout, question textarea → `POST /api/v1/chat` (Bearer token via `src/lib/api.ts`), renders answer + source cards (doc + page/section + score), `refused`/`unverified` badges, `dir="rtl"` when `language==="ar"`. `src/types.ts` mirrors `ChatResponse`.
48. Demo user — created `employee` / `employee123` (employee role) via kcadm in the running Keycloak **and** added to the versioned `realm-export.json` (reproducible on reset). Temporary bootstrap; the real admin-driven creation flow is Week 2 D4.
49. Verified headless — `npm run build` clean (tsc strict + vite); OIDC discovery issuer matches the API's `keycloak_issuer`; CORS preflight on `/api/v1/chat` from `http://localhost:5173` returns allow-origin + `authorization,content-type` + POST. **Remaining manual step**: click through the browser login (interactive PKCE can't be driven headlessly).

## J5 (cont.) — test-database isolation (permanent fix for step 44)

50. Isolated test DB — `tests/conftest.py` now overrides `DATABASE_URL` (→ `knowveris_test`, overridable via `TEST_DATABASE_URL`) **before** any `app.*` import, so the app engine binds to a dedicated DB; provisions it once at collection (CREATE DATABASE if missing via an AUTOCOMMIT admin connection, extensions, `drop_all`/`create_all`). Perf-only HNSW/GIN indexes skipped (correctness-neutral).
51. Coexistence proven — re-ingested the 5 bootstrap docs into the **dev** DB (browser demo now returns sourced answers) and the suite still **31 passed**; `knowveris` (5 INDEXED docs) and `knowveris_test` (empty, schema-only) are fully separate. The step-44 collision is structurally gone.

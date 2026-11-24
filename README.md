# KnowVeris AI

Internal AI assistant for bank employees. A **RAG** (Retrieval-Augmented Generation)
system, 100% self-hosted: an authenticated employee asks a question in natural language and
receives an answer generated **solely** from the indexed internal documents, with an exact
source citation (document + page for PDFs, document + section for DOCX files).

**Structural constraint: no data leaves the machine.** No external API (neither OpenAI,
Google AI Studio, nor Anthropic) for embedding or generation. Everything runs locally.

**Multilingual FR / EN / AR**: the assistant detects the language of the question and answers in
that same language. No translation, no imposed language.

4-week internship — see [PLAN.md](PLAN.md) for the detailed architecture and schedule.

---

## Tech stack

| Layer        | Technology                                                                                         |
| ------------ | -------------------------------------------------------------------------------------------------- |
| Frontend     | React 18 + Vite + TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Axios, React Router         |
| Auth (front) | `react-oidc-context` (OIDC + PKCE)                                                               |
| API          | FastAPI, Pydantic v2,`python-jose` (JWT validation via JWKS)                                     |
| DB           | PostgreSQL 16 +**pgvector**, SQLAlchemy 2.0, Alembic                                         |
| Auth (back)  | Keycloak 26 — realm`knowveris`, roles `employee` / `admin`, registration **disabled** |
| Ingestion    | PyMuPDF (PDF), python-docx (DOCX),`langchain-text-splitters`                                     |
| Embeddings   | **BGE-M3** via Ollama (1024D, 100+ languages, cross-lingual)                                 |
| Retrieval    | pgvector (cosine) + Postgres FTS + RRF + BGE-reranker-v2-m3 reranker (feature-flagged)             |
| Generation   | Ollama →**Qwen3 4B Instruct 2507** (Apache 2.0), fallback `qwen3:1.7b`, `temperature=0` |
| Tests        | pytest, httpx, RAG evaluation golden set                                                           |
| Monorepo     | **Nx 23** (`apps/api`, `apps/web`) + npm workspaces — every target runs in a container      |
| Python env   | **Poetry 2** (`pyproject.toml` + `poetry.lock`), installed into the image, no venv        |
| Infra        | Docker Compose (postgres · keycloak · ollama · api · web)                                      |

**Target hardware: CPU-only** (AMD Ryzen 7 4700U, 16 GB RAM, no GPU). Every technical
decision is constrained by this — see the "CPU constraints" section below.

---

## Folder structure

Nx monorepo: **two apps, no root `.env`** — each service owns the env file next to
the code that reads it, and `docker-compose.yml` points `env_file` at it.

```
knowveris/                      # Nx workspace root
├── nx.json                     # Nx config — every target delegates to docker compose
├── package.json                # npm workspaces (apps/web) + nx devDependency
├── tsconfig.base.json          # shared TS options, extended by apps/web
├── docker-compose.yml          # only host ports live here (inline defaults)
├── .dockerignore               # root build context (apps/web image)
│
├── tools/scripts/init-env.mjs  # `npm run setup` → creates every .env from .env.example
│
├── infra/
│   ├── postgres/               # init.sql (CREATE EXTENSION vector) + .env.example
│   ├── keycloak/               # realm-export.json (versioned realm) + .env.example
│   └── ollama/.env.example     # server-side tuning (keep-alive, max loaded models)
│
├── corpus/
│   ├── bootstrap/              # 3-5 short synthetic docs, committed, for automated tests
│   └── demo/                   # real public documents (FATF, ACPR, BCBS) — gitignored
│
├── docs/
│   ├── cahier-des-charges.md
│   ├── specifications-techniques.md
│   ├── plan-de-tests.md
│   └── adr/                    # Architecture Decision Records
│
└── apps/
    ├── api/
    │   ├── project.json        # Nx targets: test, lint, migrate, migration, lock, shell
    │   ├── pyproject.toml      # Poetry (package-mode = false) + poetry.lock
    │   ├── Dockerfile          # poetry install into the image, no venv
    │   ├── docker-entrypoint.sh# `alembic upgrade head` before uvicorn
    │   ├── .env.example        # the only env source for the api container
    │   ├── alembic/versions/
    │   ├── app/
    │   │   ├── main.py
    │   │   ├── core/           # config.py (Pydantic Settings), security.py (JWT/JWKS/RBAC), logging.py
    │   │   ├── db/             # session.py, base.py
    │   │   ├── models/         # SQLAlchemy: user, document, conversation, audit_log
    │   │   ├── schemas/        # Pydantic DTOs
    │   │   ├── api/v1/endpoints/   # documents, chat, conversations, admin_users, health
    │   │   ├── services/
    │   │   │   ├── ingestion/  # parsers.py, chunker.py, indexer.py
    │   │   │   ├── rag/        # embedder, retriever, reranker, prompt, generator, guardrails
    │   │   │   └── keycloak/   # admin_client.py (Admin REST API, service account)
    │   │   └── workers/tasks.py    # BackgroundTasks
    │   └── tests/
    │       ├── unit/  integration/
    │       └── eval/golden_set.yaml    # RAG evaluation
    │
    └── web/
        ├── project.json        # Nx targets: serve, build, typecheck, install, shell
        ├── Dockerfile          # built from the workspace root (hoisted node_modules)
        ├── .env.example        # read by both docker-compose and Vite
        ├── vite.config.ts
        └── src/
            ├── app/            # router, providers, layouts
            ├── features/       # auth/ chat/ documents/ dashboard/ admin/
            ├── components/ui/  # shadcn/ui
            ├── lib/            # apiClient (Axios + JWT interceptor), oidc.ts
            └── types/
```

---

## Main commands

Nothing runs on the host: `npm install` at the root only installs Nx, and every Nx
target shells out to `docker compose`. Python, Node, pytest, ruff and Alembic all
live inside the containers.

```bash
# --- First run ---
npm install                               # Nx + the web workspace (host tooling only)
npm run setup                             # create every .env from its .env.example
npm run build                             # docker compose build
npm run up                                # docker compose up -d

# --- Infra ---
npm run up / down / reset / logs / ps     # thin wrappers over docker compose
docker compose down -v                    # full reset (⚠️ deletes the volumes)

# --- Models (one-time, ~4 GB — INSIDE the container, not the host's Ollama) ---
# The API queries the container (OLLAMA_URL=http://ollama:11434): the models
# must live in the ollama_models volume, otherwise /health returns "0 model(s)".
docker compose exec ollama ollama pull qwen3:4b-instruct-2507-q4_K_M   # generation
docker compose exec ollama ollama pull qwen3:1.7b                       # fast fallback
docker compose exec ollama ollama pull bge-m3                           # embeddings
docker compose exec ollama ollama list                                 # verify

# --- API (apps/api) ---
npx nx run api:serve                      # docker compose up -d api
npx nx run api:logs
npx nx run api:test                       # pytest (unit + integration)
npx nx run api:test-eval                  # RAG evaluation on the golden set
npx nx run api:lint                       # ruff check
npx nx run api:format                     # ruff check --fix && ruff format
npx nx run api:migrate                    # alembic upgrade head (also runs on every start)
npx nx run api:migration --message="add x"   # alembic revision --autogenerate
npx nx run api:lock                       # poetry lock after editing pyproject.toml
npx nx run api:shell

# --- Web (apps/web) ---
npx nx run web:serve                      # → http://localhost:5173
npx nx run web:build                      # tsc -b && vite build, in the container
npx nx run web:typecheck
npx nx run web:install                    # after adding a dependency: npm install + restart
npx nx run web:shell

# --- Workspace ---
npx nx run-many -t test lint              # every project that has the target
npx nx graph                              # project graph

# --- URLs ---
# Frontend    http://localhost:5173
# API + docs  http://localhost:8000/docs      (Swagger UI auto-generated by FastAPI)
# Keycloak    http://localhost:8080           (admin/admin locally)
```

**Adding a Python dependency**: edit `apps/api/pyproject.toml`, then
`npx nx run api:lock` and `npx nx run api:build` — `poetry.lock` is committed and
the image installs from it.

**Adding a Node dependency**: edit `apps/web/package.json`, `npm install` at the
root (updates the single root `package-lock.json`), then `npx nx run web:install`.

---

## CPU constraints (never lose sight of these)

No GPU. The bottleneck is **not** generation, it is the **prefill**: the time it takes to feed
the context into the model. Every context token has a cost.

Direct consequences for the code:

- `chunk_size = 500` tokens, `overlap = 80` — not 800/100. Short context = faster answer.
- `top_k = 3` after reranking (not 5). We retrieve 20 candidates and keep 3.
- Explicit `num_ctx = 4096` in the Ollama options. Higher = a KV cache that eats the RAM.
- The system prompt must be **stable** (never interpolated with variable content) to benefit
  from Ollama's prefix caching.
- The reranker is behind `RERANKER_ENABLED` (feature flag) — it costs 3 to 8 s on CPU.
- BGE-M3 goes through **Ollama**, not a `SentenceTransformer` loaded in the FastAPI process:
  Ollama unloads idle models, and the RAM is too tight to keep everything resident.
- RAM budget ≈ 14 GB out of 15.4 available. Close VSCode/Chrome during the demo.

**Expected and accepted latency: 60-75 s per answer with Qwen3 4B.** SSE streaming is
mandatory — not for performance, but for perception.

---

## Conventions

**General**

- All code, comments, variable names, commit messages, and documentation are in **English**.
- No secret in the code. Everything goes through the service's own `.env` (the API reads
  it via Pydantic Settings). **Never a root `.env`** — an env var belongs next to the
  service that consumes it. Keep the matching `.env.example` up to date.
- One ADR in `docs/adr/` for each structural decision.

**Backend**

- Python 3.11+, mandatory type hints. `ruff` for linting + formatting.
- **Endpoints contain no business logic** — they validate, delegate to `services/`,
  and serialize. An endpoint longer than 20 lines is a warning sign.
- SQLAlchemy 2.0 style (`select()`, not `Query`). Async everywhere.
- Pydantic schemas separated by intent: `DocumentCreate`, `DocumentRead`, `DocumentUpdate`.
- Never store a password in the database. **Keycloak owns identity**, Postgres owns the business data.
  The `users` table merely mirrors Keycloak via `keycloak_sub` (JIT provisioning).
- Every schema migration goes through Alembic. Never `create_all()`. The api container
  entrypoint runs `alembic upgrade head` before uvicorn, so a fresh `up` is always at head
  — a migration that fails stops the container instead of serving a stale schema.
- Dependencies are managed with Poetry; `apps/api/poetry.lock` is committed and is what
  the image installs. Never `pip install` into a running container.

**RAG**

- A chunk without source metadata (`document_id` + `page_number` OR `section_title`) is a bug.
  Citation is the whole point of the project.
- `temperature=0` in generation. Always.
- Two non-negotiable guardrails: (1) refusal **before** the LLM call if the best retrieval
  score is below the threshold; (2) validation **after** generation that every cited `[Sx]`
  actually exists in the supplied context.
- Any pipeline change (chunking, threshold, prompt, model) is measured on the golden set
  before/after. No "it looks better".

**Frontend**

- Strict TypeScript. No `any`.
- Organized by `features/`, not by file type.
- The JWT is injected via a single **Axios interceptor**. Never pass a token by hand.
- API calls go through TanStack Query — no manual `useEffect` + `setState`.
- Arabic messages are rendered with `dir="rtl"`. Detect the message language, not the page language.

**Git**

- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- One branch per feature, never a direct commit on `main`.

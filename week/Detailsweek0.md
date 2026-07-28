# Week 0 — Detailed Breakdown

Every component built or configured in Week 0, in the same order as [week0.md](week0.md).
For each: location, command(s), and role.

---

## 1. Git repository & project structure

- **Location:** repo root `KnowVeris/`
- **Commands:** `git init` · `git add -A` · `git status`
- **Role:** Version-controlled monorepo (backend, frontend, infra, corpus, docs) on branch `main`. One feature branch per feature going forward; Conventional Commits.

## 2. Cahier des charges 

- **Location:** [docs/cahier-des-charges.md](docs/cahier-des-charges.md)
- **Commands:** authored (no command)
- **Role:** Functional spec — scope, actors, requirements, the "no data leaves the machine" constraint, multilingual FR/EN/AR requirement. The contract for the whole project.

## 3. Architecture & planning

- **Location:** [PLAN.md](PLAN.md)
- **Commands:** authored
- **Role:** Full technical architecture, 4-week phasing, RAG pipeline design, CPU-only constraints. The build roadmap.

## 4. Session bootstrap doc

- **Location:** [docs.md](docs.md)
- **Commands:** loaded via hook `cat docs.md`
- **Role:** Condensed project context (stack, folder map, commands, conventions) auto-injected at each Claude Code session start.

## 5. Ignore rules & env template

- **Location:** [.gitignore](.gitignore) · [.env.example](.env.example)
- **Commands:** `cp .env.example .env` (then fill secrets)
- **Role:** `.gitignore` keeps secrets/volumes/`corpus/demo` out of git. `.env.example` templates every config key (Postgres, Keycloak, Ollama, RAG tuning, API, Web) read via Pydantic Settings.

## 6. Docker Compose — 5 services

- **Location:** [docker-compose.yml](docker-compose.yml)
- **Commands:** `docker compose up -d` · `docker compose logs -f api` · `docker compose down -v`
- **Role:** Orchestrates the full local stack: `postgres` · `keycloak` · `ollama` · `api` · `web`. One command brings the environment up.

## 7. Postgres init script

- **Location:** [infra/postgres/init.sql](infra/postgres/init.sql)
- **Commands:** runs automatically on first container start
- **Role:** Installs superuser-only extensions `vector` (pgvector), `pg_trgm`, `uuid-ossp`. Schema itself stays owned by Alembic (never `create_all()`).

## 8. Keycloak realm export

- **Location:** [infra/keycloak/realm-export.json](infra/keycloak/realm-export.json)
- **Commands:** imported by the `keycloak` container at startup
- **Role:** Reproducible identity setup — realm `knowveris`, roles `employee`/`admin`, self-registration disabled, clients `knowveris-web` (SPA, OIDC+PKCE) and `knowveris-api` (audience/JWT validation).

## 9. Backend scaffold (FastAPI)

- **Location:** [backend/](backend/) — [app/main.py](backend/app/main.py), [app/core/config.py](backend/app/core/config.py), [app/api/v1/endpoints/health.py](backend/app/api/v1/endpoints/health.py), [app/schemas/health.py](backend/app/schemas/health.py), [pyproject.toml](backend/pyproject.toml)
- **Commands:** `uv sync` · `uv run uvicorn app.main:app --reload` · `curl localhost:8000/api/v1/health`
- **Role:** FastAPI app skeleton with CORS, Pydantic Settings config, and a real `/api/v1/health` endpoint that verifies pgvector is installed and lists loaded Ollama models. `services/` folders (ingestion, rag, keycloak) stubbed for later.

## 10. Backend Dockerfile

- **Location:** [backend/Dockerfile](backend/Dockerfile)
- **Commands:** built by `docker compose` (service `api`)
- **Role:** `python:3.12-slim` + `uv` (from distroless image); layered dependency install cached until `pyproject`/lock change; runs uvicorn with reload on `:8000`.

## 11. Frontend scaffold (Vite + React + TS)

- **Location:** [frontend/](frontend/) — [src/App.tsx](frontend/src/App.tsx), [src/main.tsx](frontend/src/main.tsx), [vite.config.ts](frontend/vite.config.ts), [tsconfig.json](frontend/tsconfig.json), [package.json](frontend/package.json)
- **Commands:** `npm install` · `npm run dev` (→ `localhost:5173`) · `npm run build`
- **Role:** React 18 + Vite + TypeScript SPA skeleton; entry point and base app shell ready for the `features/` structure.

## 12. Frontend Dockerfile

- **Location:** [frontend/Dockerfile](frontend/Dockerfile)
- **Commands:** built by `docker compose` (service `web`)
- **Role:** `node:22-slim`; layered `npm install` cached until manifests change; runs the Vite dev server on `:5173`.

## 13. Bootstrap corpus

- **Location:** [corpus/bootstrap/](corpus/bootstrap/) — 5 files + [README.md](corpus/bootstrap/README.md)
- **Commands:** committed binaries (regen via PyMuPDF `fitz.Story` for PDF, `python-docx` for DOCX)
- **Role:** Synthetic banking-compliance docs, committed for deterministic tests. `fr-obligations-vigilance.pdf`, `en-customer-due-diligence.docx`, `ar-alainaya-alwajiba.docx` (cross-lingual CDD triplet FR/EN/AR), `en-sanctions-screening.pdf`, `fr-declaration-soupcon.docx`. Exercises both parsers (page vs. section attribution) and cross-lingual retrieval.

## 14. Demo corpus placeholder

- **Location:** [corpus/demo/](corpus/demo/) — [README.md](corpus/demo/README.md) + `.gitkeep`
- **Commands:** none (gitignored contents)
- **Role:** Slot for real public documents (GAFI/FATF, ACPR, BCBS); kept out of git, README documents sourcing.

## 15. Claude Code settings / hook

- **Location:** [.claude/settings.json](.claude/settings.json)
- **Commands:** `SessionStart` hook runs `cat docs.md` (bash, 10s timeout)
- **Role:** On session `startup|resume|clear`, injects `docs.md` into context so project conventions are always loaded.

## 16. Ollama models *(manual)*

- **Location:** Ollama model store (`ollama` container / host volume)
- **Commands:** `ollama pull qwen3:4b-instruct-2507-q4_K_M` · `ollama pull qwen3:1.7b` · `ollama pull bge-m3`
- **Role:** Generation model, fast fallback, and BGE-M3 embeddings — all local, no external API (~4 Go). Surfaced by the `/health` check.

## 17. Environment secrets *(manual)*

- **Location:** `.env` (untracked, from `.env.example`)
- **Commands:** `cp .env.example .env` then edit; `git status` to confirm untracked
- **Role:** Real secrets (DB password, Keycloak admin + client secret) set locally; verified none committed.

## 18. Stack bring-up & verify *(manual)*

- **Location:** whole stack
- **Commands:** `docker compose up -d` · `docker compose ps` · `GET localhost:8000/api/v1/health`
- **Role:** All 5 containers running; health endpoint returns `ok` (pgvector present, Ollama models listed).

## 19. GitHub setup *(manual)*

- **Location:** remote `origin`
- **Commands:** `git remote add origin <url>` · `git commit -m "Week 0: infra stack, bootstrap corpus, cahier des charges"` · `git push -u origin main`
- **Role:** Published Week 0 baseline — commit `6f8bdbc` on `main`.

# Week 0 — Summary

Sequential steps to bootstrap the KnowVeris project (infra, corpus, docs).

1. Init Git repo + project structure — `git init` — empty repo on `main`.
2. Write cahier des charges — `docs/cahier-des-charges.md` — scope, requirements, constraints fixed.
3. Write architecture & planning — `PLAN.md` — stack, phases, RAG pipeline documented.
4. Write session bootstrap doc — `docs.md` — project context injected at each session start.
5. Add `.gitignore` + `.env.example` — all config keys templated (Postgres, Keycloak, Ollama, RAG, API, Web).
6. Docker Compose config (5 services) — `docker-compose.yml` — postgres · keycloak · ollama · api · web.
7. Postgres init script — `infra/postgres/init.sql` — extensions `vector`, `pg_trgm`, `uuid-ossp`.
8. Keycloak realm export — `infra/keycloak/realm-export.json` — realm `knowveris`, roles `employee`/`admin`, registration disabled, clients `knowveris-web`/`knowveris-api`.
9. Backend scaffold — `backend/` (FastAPI, `pyproject.toml`, `config.py` Pydantic Settings, `main.py`) — app skeleton + `/health` endpoint.
10. Backend Dockerfile — `backend/Dockerfile` — uv-based image.
11. Frontend scaffold — `frontend/` (Vite + React 18 + TS, `App.tsx`, `vite.config.ts`) — SPA skeleton.
12. Frontend Dockerfile — `frontend/Dockerfile` — Node build image.
13. Bootstrap corpus — `corpus/bootstrap/` — 5 synthetic docs (FR/EN/AR, PDF + DOCX) for the ingestion/retrieval tests.
14. Demo corpus placeholder — `corpus/demo/` (README + `.gitkeep`, gitignored) — real public docs kept out of git.
15. Claude Code settings — `.claude/settings.json` — session config.
16. [Manual] Pull Ollama models — `ollama pull qwen3:4b-instruct-2507-q4_K_M && ollama pull qwen3:1.7b && ollama pull bge-m3` — generation, fallback, embedding models cached (~4 Go).
17. [Manual] Fill `.env` from `.env.example` — copied and set secrets (DB password, Keycloak admin, client secret) — verified no secret committed.
18. [Manual] Bring stack up — `docker compose up -d` — 5 containers running; `GET localhost:8000/health` OK.
19. [Manual] Commit + push to GitHub — `git add -A && git commit -m "Week 0: infra stack, bootstrap corpus, cahier des charges" && git push` — commit `6f8bdbc` on `main`.

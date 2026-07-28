# KnowVeris — Project Structure

This document lists every folder and file in the project and explains, in plain
language, what each one is for. It is meant to be read without a technical
background.

**What the project is:** KnowVeris is an internal AI assistant for bank
employees. An employee asks a question in plain language and receives an answer
built **only** from the bank's own internal documents, always with the exact
source cited. Everything runs on a single local machine — no data ever leaves it,
and no external AI service is used.

---

## Root of the project

| File / Folder          | What it is for                                                                                                        |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `docs.md`            | The main project overview: goal, technologies used, and how to run it. Read first.                                    |
| `PLAN.md`            | The detailed plan: project architecture, the week-by-week schedule, and the working method.                           |
| `docker-compose.yml` | A single recipe that starts all the pieces of the app together (database, login server, AI engine, backend, website). |
| `nx.json`            | The monorepo control panel: one place to run any task of any app, always inside its container.                        |
| `package.json`       | The workspace manifest — declares the two apps and the few tools needed on this machine.                              |
| `tsconfig.base.json` | The shared code rules for the website's language, so future shared pieces stay consistent.                            |
| `tools/scripts/init-env.mjs` | A one-shot helper that creates each app's private settings file from its template.                            |
| `.gitignore`         | Tells the version-control system which files to ignore and never save.                                                |
| `.dockerignore`      | Tells the packaging tool which files to leave out when building the website image.                                    |
| `StructDetails.md`   | This document.                                                                                                        |

There is deliberately **no settings file at the root**. Each service keeps its own
`.env` next to the code that reads it (`apps/api/`, `apps/web/`, `infra/postgres/`,
`infra/keycloak/`, `infra/ollama/`), each with a matching `.env.example` template.

---

## `infra/` — Infrastructure setup

Configuration that prepares the supporting services so the environment can be
rebuilt identically anywhere.

| File / Folder                        | What it is for                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `infra/postgres/init.sql`          | Prepares the database so it can store and compare AI "meaning fingerprints" of text.                          |
| `infra/keycloak/realm-export.json` | A saved copy of the login-and-roles setup (employees vs. administrators), so it can be recreated in one step. |
| `infra/*/.env.example`             | The settings template for each supporting service (database, login server, AI engine).                        |

---

## `corpus/` — The documents the assistant reads

The reference documents the assistant is allowed to answer from.

| File / Folder                  | What it is for                                                                                                        |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `corpus/bootstrap/`          | A small set of short sample documents (French, English, Arabic) kept with the project and used for automated testing. |
| `corpus/bootstrap/README.md` | Explains what these sample documents are.                                                                             |
| `corpus/demo/`               | A place for real public documents used for demonstrations. These are kept out of version control.                     |
| `corpus/demo/README.md`      | Explains which demo documents to place here and where to find them.                                                   |

---

## `docs/` — Written documentation (in French)

| File / Folder                  | What it is for                                                    |
| ------------------------------ | ----------------------------------------------------------------- |
| `docs/cahier-des-charges.md` | The requirements document: what the project must deliver and why. |

---

## `week/` — Weekly progress notes

| File / Folder                             | What it is for                                                  |
| ----------------------------------------- | --------------------------------------------------------------- |
| `week/week0.md`, `week/week1.md`, ... | Personal progress journal, one file per week of the internship. |
| `week/Detailsweek0.md`                  | More detailed notes for a given week.                           |

---

## `apps/api/` — The engine (the part that does the work)

This is the "behind the scenes" program: it receives questions, searches the
documents, and builds the answers. Users never see it directly.

| File / Folder                                       | What it is for                                                                |
| --------------------------------------------------- | ----------------------------------------------------------------------------- |
| `apps/api/project.json`                            | The list of tasks for this app (test, check, migrate…), each run in its container. |
| `apps/api/Dockerfile`                              | Instructions to package the backend so it runs the same way everywhere.       |
| `apps/api/docker-entrypoint.sh`                    | Runs at every start: updates the database structure, then switches the backend on. |
| `apps/api/pyproject.toml`                          | The list of external building blocks (libraries) the backend depends on.      |
| `apps/api/poetry.lock`                             | The exact versions of those building blocks, so every machine installs the same ones. |
| `apps/api/.env.example`                            | The settings template for the backend.                                        |
| `apps/api/alembic.ini`, `apps/api/alembic/`       | Tools that keep the database's structure up to date as the project evolves.   |
| `apps/api/alembic/versions/0001_initial_schema.py` | The first version of the database structure (the tables and how they relate). |

### `apps/api/app/` — The application itself

| File / Folder                         | What it is for                                                                                 |
| ------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `app/main.py`                       | The starting point: switches the backend on and wires everything together.                     |
| `app/core/config.py`                | Reads and validates all the app's settings.                                                    |
| `app/core/security.py`              | Handles who is allowed in and what they can do (login checks and permissions).                 |
| `app/db/`                           | Manages the connection to the database.                                                        |
| `app/models/`                       | Describes the data the app stores.                                                             |
| `app/models/user.py`                | An employee's record (a mirror of the login system).                                           |
| `app/models/document.py`            | An uploaded document and its ingestion status.                                                 |
| `app/models/conversation.py`        | A saved chat between an employee and the assistant.                                            |
| `app/models/audit_log.py`           | A trace of important actions, for accountability.                                              |
| `app/schemas/`                      | Defines the exact shape of the information exchanged with the website, and checks it is valid. |
| `app/api/v1/endpoints/`             | The "doors" the website knocks on to talk to the backend.                                      |
| `app/api/v1/endpoints/documents.py` | Handles uploading and managing documents.                                                      |
| `app/api/v1/endpoints/health.py`    | A quick self-check to confirm everything is running.                                           |

### `apps/api/app/services/` — The core know-how

Where the real logic lives. Endpoints stay simple and hand the work to these.

| File / Folder                      | What it is for                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| `services/ingestion/parsers.py`  | Reads the text out of PDF and Word documents.                                                     |
| `services/ingestion/language.py` | Detects the language of a piece of text (French, English, Arabic).                                |
| `services/ingestion/chunker.py`  | Cuts long documents into small, searchable passages.                                              |
| `services/ingestion/indexer.py`  | Files those passages away so they can be found later.                                             |
| `services/ingestion/uploader.py` | Handles receiving and storing an uploaded file.                                                   |
| `services/rag/embedder.py`       | Turns text into a "meaning fingerprint" so passages can be compared by meaning.                   |
| `services/rag/retriever.py`      | Finds the passages most relevant to the employee's question.                                      |
| `services/keycloak/`             | Talks to the login system to manage employee accounts.                                            |
| `app/workers/tasks.py`           | Runs slower jobs (like processing a new document) in the background, so the app stays responsive. |

### `apps/api/tests/` — Automated checks

| File / Folder          | What it is for                                                                          |
| ---------------------- | --------------------------------------------------------------------------------------- |
| `tests/conftest.py`  | Shared setup used by all the tests.                                                     |
| `tests/unit/`        | Small checks on individual pieces in isolation.                                         |
| `tests/integration/` | Checks that several pieces work correctly together (uploading, security, search, etc.). |

---

## `apps/web/` — The website (the part employees see)

The screens an employee uses to log in, ask questions, and read answers.

| File / Folder                  | What it is for                                                          |
| ------------------------------ | ----------------------------------------------------------------------- |
| `apps/web/project.json`      | The list of tasks for this app (start, build, check), each run in its container. |
| `apps/web/Dockerfile`        | Instructions to package the website so it runs the same way everywhere. |
| `apps/web/package.json`      | The list of external building blocks the website depends on.            |
| `apps/web/.env.example`      | The settings template for the website.                                  |
| `apps/web/index.html`        | The single web page that hosts the whole application.                   |
| `apps/web/public/favicon.svg`| The small icon shown in the browser tab.                                |
| `apps/web/vite.config.ts`    | Settings for the tool that builds and previews the website.             |
| `apps/web/tsconfig.json`     | Rules that keep the website's code consistent and catch mistakes early. |
| `apps/web/src/main.tsx`      | The starting point that displays the website in the browser.            |
| `apps/web/src/index.css`     | The colours and spacing rules shared by every screen (light and dark).  |
| `apps/web/src/vite-env.d.ts` | A small technical helper file for the build tool.                       |

### `apps/web/src/app/` — The frame around every screen

| File / Folder             | What it is for                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------------ |
| `app/router.tsx`        | The map of addresses: which screen each web address shows, and who is allowed to see it.               |
| `app/providers.tsx`     | Switches on the shared services every screen relies on: the login session, data fetching, and notices. |
| `app/ErrorBoundary.tsx` | Shows a readable "something broke" screen instead of a blank page if the app crashes.                  |
| `app/layouts/`          | The page frame: the side menu, and — on a phone — the slide-out version of it.                        |

### `apps/web/src/features/` — The screens themselves

Grouped by what the user is doing, not by file type.

| File / Folder      | What it is for                                                                                 |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| `features/auth/`         | Logging in through Keycloak, and telling the user when their session has expired.        |
| `features/chat/`         | Asking a question, watching the answer arrive word by word, and seeing its sources.      |
| `features/conversations/`| The list of past conversations, and deleting one.                                        |
| `features/dashboard/`    | The home screen: a few figures plus recent history, next to the chat panel.               |
| `features/documents/`    | Admin only — dropping in PDF/Word files and following their indexing progress.           |
| `features/admin/`        | Admin only — creating employee accounts, disabling them, resetting passwords.            |

### `apps/web/src/components/` and `apps/web/src/lib/` — Shared pieces

| File / Folder            | What it is for                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------ |
| `components/ui/`       | Small reusable building blocks: buttons, cards, tables, dialogs, notices, loading placeholders. |
| `lib/apiClient.ts`     | The single place that talks to the backend and attaches the user's proof of identity.     |
| `lib/oidc.ts`          | Manages the login session with Keycloak, including renewing it in the background.         |
| `lib/session.ts`       | Signals the rest of the app the moment a session expires, and remembers the page to return to. |
| `lib/rtl.ts`           | Decides whether a message should read left-to-right or right-to-left (Arabic).            |
| `lib/theme.ts`         | The light/dark mode switch.                                                               |
| `src/types/`           | The exact shape of everything exchanged with the backend.                                 |

---

## `.claude/` — Assistant configuration

| File / Folder             | What it is for                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| `.claude/settings.json` | Settings for the AI coding assistant used during development. Not part of the running app. |

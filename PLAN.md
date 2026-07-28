# KnowVeris AI — Architecture & Development Plan

> Project reference document. For day-to-day context (stack, commands, conventions),
> see [docs.md](docs.md).

---

## 1. Context and objectives

Bank employees search manually across dozens of internal PDF/DOCX procedures
(compliance, KYC, credit, operations). It is slow, error-prone, and untraceable.

**KnowVeris** lets an authenticated employee ask a question in natural language and get
an answer generated **solely** from the indexed documents, with every answer citing its
exact source.

### Measurable objectives

| Objective                                             | Target         |
| ----------------------------------------------------- | -------------- |
| The correct source is in the returned top 3           | Recall@3 > 85% |
| Correct refusal on an out-of-corpus question          | > 90%          |
| False refusal on an in-corpus question                | < 10%          |
| Answer in the language of the question (FR/EN/AR)     | 100%           |
| Every answer carries at least one verifiable citation | 100%           |
| End-to-end latency (CPU-only)                         | < 90 s         |

### Constraints

1. **Strictly self-hosted** — no data leaves the machine. No external API.
2. **CPU-only** — AMD Ryzen 7 4700U, 8 Zen 2 cores (no SMT), 16 GB RAM, no GPU.
3. **Multilingual FR/EN/AR** — automatic detection, answer in the language of the question.
4. **Open-source models** — permissive licenses only (Apache 2.0 / MIT).
5. **4 weeks, one person.**

---

## 2. Structural technical decisions

Each decision below warrants an ADR in `docs/adr/`.

### ADR-001 — pgvector rather than ChromaDB

PostgreSQL is already in the project. Adding ChromaDB would mean two databases to deploy,
back up, and synchronize, with a real risk of inconsistency (document deleted on the
Postgres side, orphaned vectors on the Chroma side). `pgvector` keeps chunks, embeddings,
metadata, and conversations in the same transaction, allows a `JOIN` between a vector and
its parent document, and provides **hybrid search** for free via Postgres's native
full-text search. Chroma would be justified for millions of chunks; we have a few thousand.

### ADR-002 — LangChain reduced to `langchain-text-splitters`

The full pipeline (parse → chunk → embed → store → retrieve → prompt → generate) fits in
~150 lines of Python. LangChain's frequent breaking changes are an unacceptable risk over
4 weeks, and the abstraction hides exactly what the defense must demonstrate. We keep the
one genuinely well-built component, `RecursiveCharacterTextSplitter`, and write the rest
by hand.

### ADR-003 — Qwen3 4B Instruct 2507 for generation

The two initial candidates are eliminated by **verified facts**:

- **Llama 3.2 3B** — Meta's official model card lists 8 supported languages: English,
  German, French, Italian, Portuguese, Hindi, Spanish, Thai. **Arabic is not among them.**
  The model would produce degraded Arabic, outside the scope of the Acceptable Use Policy
  without fine-tuning. → **Disqualified by the AR requirement.**
- **Qwen2.5 3B** — the entire Qwen2.5 family is under Apache 2.0 **except the 3B and 72B
  variants**, which are under the *Qwen Research License* (non-commercial restriction). A
  project intended for a bank cannot rely on it. → **Disqualified by the open-source
  license requirement.**

**Selected: Qwen3 4B Instruct 2507** — Apache 2.0, trained on 36T tokens covering 119
languages (Arabic included), the `-Instruct-2507` variant with no *thinking mode*
(essential: explicit reasoning would double the latency on CPU). Ollama tag:
`qwen3:4b-instruct-2507-q4_K_M`.

**Fallback: `qwen3:1.7b`** — same license, same language coverage, ~2× faster. To be
adopted if the Week 1 benchmark shows the 4B is untenable.

### ADR-004 — BGE-M3 for embeddings, served by Ollama

100+ languages, 8192-token context, 1024 dimensions, SOTA on MIRACL (multilingual) and
**MKQA (cross-lingual)**. That last point is decisive: a question in Arabic can retrieve a
passage in French.

**No conflict with the LLM choice** — the two models are fully decoupled. BGE-M3 decides
*which passages are retrieved*, Qwen3 decides *how the answer is phrased*. This is a useful
architectural property: we can change one without touching the other, and benchmark them
separately.

Served via `ollama pull bge-m3` rather than loaded in the FastAPI process: Ollama unloads
idle models, and the RAM budget (~14 GB out of 15.4) does not allow keeping everything
resident.

### ADR-005 — Citation: page for PDFs, section for DOCX

A DOCX **has no notion of pages** — pagination is computed by Word at render time; it does
not exist in the XML. The citation model is therefore `{document, page?, section?}`:

- PDF → `KYC_guide_v3.pdf, page 12`
- DOCX → `Procedure_credit.docx, § 3.2 Identity verification`

Rejected alternative: converting DOCX to PDF via headless LibreOffice (one more container,
added fragility, for a cosmetic gain).

### ADR-006 — Keycloak owns identity, Postgres owns the business data

No password in the application database. The `users` table mirrors Keycloak via
`keycloak_sub` (the JWT `sub` claim), populated through **JIT provisioning** on the first
API call. This gives a stable foreign key for `conversations` and `audit_logs` without
duplicating authentication management.

Employee account creation goes through the **Keycloak Admin REST API** via a service
account — never through a homegrown auth system.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React SPA (Vite)  ──── OIDC + PKCE ────►  Keycloak 26      │
│  Employee / Admin dashboards               realm knowveris   │
└──────────────┬──────────────────────────┐  registration=off │
               │ HTTP + Bearer JWT        └────────┬──────────┘
               ▼                                   │ JWKS
┌──────────────────────────────────────────┐       │ (public keys)
│  FastAPI                                 │◄──────┘
│  ├─ security : JWT verify + RBAC + audit │
│  ├─ /api/v1/chat          (SSE stream)   │──── Admin REST API ──►┐
│  ├─ /api/v1/documents     (admin)        │   (service account)   │
│  ├─ /api/v1/conversations                │                       │
│  └─ /api/v1/admin/users   (admin)        │◄──────────────────────┘
│                                          │
│  services/ingestion ──┐   ┌── services/rag
└──────────┬────────────┘   └────────┬─────┘
           │                         │
           ▼                         ▼
┌────────────────────────┐  ┌──────────────────────────┐
│ PostgreSQL 16          │  │ Ollama                   │
│ + pgvector (HNSW)      │  │ ├─ qwen3:4b-instruct     │
│ + FTS (GIN)            │  │ └─ bge-m3 (embeddings)   │
│                        │  └──────────────────────────┘
│ users · documents      │  ┌──────────────────────────┐
│ document_chunks        │  │ Python (lazy, flagged)   │
│ conversations·messages │  │ └─ bge-reranker-v2-m3    │
│ message_citations      │  └──────────────────────────┘
│ audit_logs             │
└────────────────────────┘
```

### PostgreSQL schema

```
users             (id, keycloak_sub UNIQUE, email, full_name, role, created_at, last_login_at)

documents         (id, filename, mime_type, file_hash UNIQUE, page_count, language,
                   status, error_message, uploaded_by → users, created_at)
                   -- file_hash SHA-256: rejects duplicates on upload (409)
                   -- status: PENDING → PARSING → EMBEDDING → INDEXED | FAILED

document_chunks   (id, document_id → documents, chunk_index, content,
                   page_number NULL, section_title NULL, language,
                   embedding vector(1024), content_tsv tsvector)
                   -- CHECK (page_number IS NOT NULL OR section_title IS NOT NULL)
                   -- HNSW index (vector_cosine_ops) + GIN index (content_tsv)

conversations     (id, user_id → users, title, created_at, updated_at)
messages          (id, conversation_id → conversations, role, content, language,
                   model_used, latency_ms, refused BOOLEAN, created_at)
message_citations (id, message_id → messages, chunk_id → document_chunks, relevance_score)
audit_logs        (id, user_id, action, resource_type, resource_id,
                   metadata jsonb, ip_address, created_at)
```

`message_citations` is the table that materializes **traceability**: for any answer
produced, we know exactly which passages of which documents grounded it.

### Keycloak configuration

**Realm `knowveris`** — exported to `infra/keycloak/realm-export.json` (versioned: without
it, we reconfigure by hand on every reset and lose hours).

```
registrationAllowed      : false     ← no self-registration
resetPasswordAllowed     : false     ← the admin resets passwords
rememberMe               : false
verifyEmail              : false     ← no SMTP locally
loginWithEmailAllowed    : true
bruteForceProtected      : true
accessTokenLifespan      : 5 min
ssoSessionIdleTimeout    : 30 min
ssoSessionMaxLifespan    : 8 h       ← a working day
```

**Clients**

| Client                  | Type                                       | Role                                                                                                                     |
| ----------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `knowveris-web`       | public, standard flow +**PKCE S256** | the SPA. No implicit flow, no direct access grants. Audience mapper to`knowveris-api`.                                 |
| `knowveris-api`       | bearer-only                                | audience validated by FastAPI                                                                                            |
| `knowveris-admin-cli` | **confidential, service account**    | what FastAPI uses to call the Admin REST API. Roles`manage-users` + `view-users`. Secret in an environment variable. |

**Realm roles**: `employee`, `admin` (composite, includes `employee`). Default: `employee`.

### Employee account creation flow

```
[Admin] form in the admin dashboard
   │
   ▼
POST /api/v1/admin/users   (JWT, role=admin)
   │
   ├─► FastAPI obtains a service-account token
   │     (client_credentials on knowveris-admin-cli)
   │
   ├─► POST   {kc}/admin/realms/knowveris/users
   │            { username, email, firstName, lastName, enabled: true }
   ├─► PUT    {kc}/admin/realms/knowveris/users/{id}/reset-password
   │            { temporary: true, value: <generated password> }
   │            └─ temporary=true forces a change at first login
   ├─► POST   {kc}/admin/realms/knowveris/users/{id}/role-mappings/realm
   │            [{ employee }]
   │
   ├─► INSERT users(keycloak_sub, ...) into Postgres (mirror)
   └─► INSERT audit_logs(action='user.created', ...)
   │
   ▼
{ temporary_password }   ← shown ONLY ONCE to the admin
```

Endpoints: `POST /admin/users` · `GET /admin/users` · `PATCH /admin/users/{id}` (enable/disable) ·
`POST /admin/users/{id}/reset-password`. **No DELETE** — we disable, we do not delete
(traceability).

---

## 4. Data flow

### Flow A — Ingestion (admin)

```
[Admin] drag & drop of a PDF/DOCX into the Center Panel
   │
   ▼
POST /api/v1/documents  (multipart, Bearer JWT)
   ├─► verify JWT via JWKS ──── role != admin ──► 403
   ├─► check file_hash ──────── already present ─► 409 Conflict
   ├─► save file + INSERT documents(status=PENDING)
   └─► 202 Accepted { document_id }        ◄── immediate response, no timeout
   │
   ▼  BackgroundTask (asynchronous)
┌────────────────────────────────────────────────────────────┐
│ 1. PARSING              status=PARSING                     │
│    PDF  → PyMuPDF      → [(text, page_number)]             │
│    DOCX → python-docx  → [(text, section_title)]           │
│    language detection (lingua-py) → documents.language      │
│                                                            │
│ 2. CHUNKING                                                │
│    RecursiveCharacterTextSplitter, 500 tokens, overlap 80   │
│    → each chunk RETAINS its page / its section              │
│                                                            │
│ 3. EMBEDDING            status=EMBEDDING                   │
│    BGE-M3 via Ollama (batch) → 1024D vector per chunk       │
│                                                            │
│ 4. INDEXING                                                │
│    INSERT document_chunks (content, page_number|section,    │
│           language, embedding, content_tsv)                 │
│    content_tsv built with the FTS config of the detected    │
│           language (french | english | arabic | simple)     │
│    status=INDEXED    (or FAILED + error_message)            │
└────────────────────────────────────────────────────────────┘
   │
   ▼
Frontend: TanStack Query polls GET /api/v1/documents (5 s)
   → the indexing-status table updates on its own
```

### Flow B — Question → sourced answer (employee)

```
[Employee] « ما هي إجراءات العناية الواجبة للعميل المعرض سياسياً ؟ »
   │
   ▼
POST /api/v1/chat  { conversation_id, question }   (Bearer JWT)
   ├─► verify JWT (JWKS) → user JIT-provisioned → INSERT audit_log
   │
   ▼
LANGUAGE DETECTION (lingua-py) → lang = "ar"
   │
   ▼
BGE-M3 → question vector (1024D)
   │
   ├───────────────────────┬──────────────────────────┐
   ▼                       ▼                          │
VECTOR SEARCH         KEYWORD SEARCH                  │
pgvector cosine       Postgres FTS (config = lang)    │ ← catches "PEP", "AML-CFT"
top_k = 20            top_k = 20                      │   that the vector alone misses
   │                       │                          │
   │  cross-lingual: BGE-M3 bridges AR→FR.            │
   │  BM25 does not — the vector carries the          │
   │  load on cross-lingual questions.                │
   └───────────┬───────────┘                          │
               ▼                                      │
       RRF fusion (Reciprocal Rank Fusion)            │
               │                                      │
               ▼                                      │
   RERANKER bge-reranker-v2-m3  [if RERANKER_ENABLED] │
   top_k = 3                                          │
               │                                      │
               ▼                                      │
   ╔══════════════════════════════════════════════╗   │
   ║ GUARDRAIL 1 — relevance threshold            ║   │
   ║ if best_score < THRESHOLD :                  ║   │
   ║   → "Information not found in the indexed    ║   │
   ║      documents." (in the language of the     ║   │
   ║      question)                               ║   │
   ║   → NO call to the LLM → 0 hallucination     ║   │
   ║      possible, and an answer in < 2 s        ║   │
   ╚══════════════════════════════════════════════╝   │
               │ otherwise                            │
               ▼                                      │
PROMPT BUILDER                                        │
  system (STABLE → Ollama prefix cache) :             │
    "Answer ONLY from the context.                    │
      Cite your sources [S1]..[S3].                   │
      If the information is absent from the context,  │
      answer exactly 'INFORMATION_NOT_FOUND'."        │
  explicit language instruction: "Answer in           │
    Arabic."  ← injected, not guessed: a 4B drifts    │
  context :                                           │
    [S1] doc="FATF_AR.pdf" page=12 → "..."            │
    [S2] doc="KYC_guide.docx" § 3.2 → "..."           │
  user : the question                                 │
               │                                      │
               ▼                                      │
OLLAMA — qwen3:4b-instruct-2507, temperature=0,       │
         num_ctx=4096, num_thread=8                   │
               │                                      │
               ▼  SSE stream, token by token          │
   ╔══════════════════════════════════════════════╗   │
   ║ GUARDRAIL 2 — post-generation validation     ║   │
   ║ · every cited [Sx] must exist in the         ║   │
   ║   context → otherwise it is removed          ║   │
   ║ · answer without any citation → "unverified" ║   │
   ║   flag shown on screen                       ║   │
   ╚══════════════════════════════════════════════╝   │
               │                                      │
               ▼                                      │
INSERT message + message_citations + audit_log ◄──────┘
               │
               ▼
[Frontend] streamed answer, rendered dir="rtl"
           + clickable source cards:
             📄 FATF_AR.pdf — page 12       (score 0.87)
             📄 KYC_guide.docx — § 3.2      (score 0.81)
```

---

## 5. Performance budget (CPU-only)

This is the constraint that structures everything else. On a Ryzen 7 4700U (8 Zen 2 cores
**without SMT**, DDR4 dual-channel ~35 GB/s effective):

| Step                                            | Estimated cost                           |
| ----------------------------------------------- | ---------------------------------------- |
| Language detection                              | < 50 ms                                  |
| Question embedding (BGE-M3)                     | ~0.2 s                                   |
| Vector search + FTS + RRF                       | < 100 ms                                 |
| Reranker (20 candidates × 500 tokens)          | **3-8 s**                          |
| **LLM prefill** (~1800 tokens of context) | **30-45 s** ← the real bottleneck |
| Generation (~200 tokens @ 6-9 tok/s)            | **25-35 s**                        |
| **Total**                                 | **≈ 60-90 s**                     |

**The prefill dominates, not the generation.** This is counterintuitive and is what
justifies the aggressive parameters: `chunk_size=500`, `top_k=3`, `num_ctx=4096`. Moving to
`top_k=5` with 800-token chunks would push the context to ~4000 tokens and the prefill to
60-100 s — unusable.

With `qwen3:1.7b`: prefill 12-18 s, generation ~15-20 tok/s → **total ≈ 25-35 s**. This is
the fallback if the 4B is judged untenable at the Week 1 benchmark.

**RAM budget** (15.4 GB usable):

```
Windows 11                      ~4.0 GB
Ollama + qwen3:4b Q4_K_M        ~3.0 GB
Ollama + bge-m3                 ~1.2 GB   (unloaded after 5 min of inactivity)
bge-reranker-v2-m3 (Python)     ~1.3 GB   (lazy, feature-flagged)
Keycloak (JVM, heap limited 512m) ~0.9 GB
PostgreSQL                      ~0.5 GB
FastAPI / Python                ~0.4 GB
Vite dev + Node                 ~0.5 GB
VSCode + browser                ~2.0 GB
─────────────────────────────────────────
Total                          ~13.8 GB / 15.4
```

Feasible but tight. Measures: `JAVA_OPTS_KC_HEAP=-Xms256m -Xmx512m` on Keycloak, BGE-M3 in
Ollama (not in FastAPI), lazy-loaded reranker, and **close VSCode/Chrome during the demo**
(or serve the built frontend via nginx rather than the Vite dev server).

---

## 6. The golden set

This is the artifact that turns "it seems to work" into "here are the numbers". Without it,
no claim in the defense is defensible.

### Structure

`apps/api/tests/eval/golden_set.yaml`

```yaml
- id: kyc-pep-fr-001
  question: "Quelle est la procédure de vigilance renforcée pour un client PEP ?"
  lang: fr
  category: kyc
  type: factual
  expected_sources:
    - document: "FATF_Recommandations_FR.pdf"
      pages: [12, 13]
  expected_answer_contains: ["vigilance renforcée", "approbation de la direction"]
  must_refuse: false

- id: oos-crypto-fr-014
  question: "Quelle est la politique de la banque sur les crypto-actifs ?"
  lang: fr
  category: out_of_scope
  type: negative
  expected_sources: []
  must_refuse: true            # ← nothing in the corpus answers this

- id: xling-pep-ar-022
  question: "ما هي إجراءات العناية الواجبة المعززة للأشخاص المعرضين سياسياً ؟"
  lang: ar
  category: kyc
  type: cross_lingual
  expected_sources:
    - document: "FATF_Recommandations_FR.pdf"   # ← AR question, FR source
      pages: [12]
  must_refuse: false
```

> Note: the golden-set entries are intentionally multilingual (FR/EN/AR question strings
> and expected substrings) — they mirror the multilingual corpus and must not be translated.

### Composition (~35 questions)

| Type                                                    | Share          | What it measures                            |
| ------------------------------------------------------- | -------------- | ------------------------------------------- |
| `factual` — answer in a single chunk                 | ~35%           | basic retrieval                             |
| `multi_hop` — requires 2+ chunks, sometimes 2 docs   | ~20%           | quality of the RRF fusion                   |
| **`negative` — answer absent from the corpus** | **~25%** | **the anti-hallucination guardrails** |
| `acronym` — banking jargon (PEP, AML-CFT, AML)       | ~12%           | the value of hybrid search vs vector alone  |
| `cross_lingual` — AR/EN question, FR source          | ~8%            | BGE-M3's cross-lingual ability              |

Language distribution: ~15 FR, ~10 EN, ~10 AR.

**The `negative` questions are the most important in the set.** Without them, we literally
cannot measure anti-hallucination — which is the project's #1 objective. This is the
classic trap of tutorial golden sets: they contain only questions the system knows how to
answer, and therefore measure everything except what matters in banking.

### Metrics produced

- **Retrieval**: Recall@3, Recall@10, MRR
- **Guardrails**: correct-refusal rate (on `negative`), false-refusal rate (on the rest)
- **Citations**: % of answers whose citations all point to a chunk actually supplied
- **Language**: % of answers in the language of the question
- **Perf**: P50 / P95 latency, tokens/s

Execution: `uv run pytest tests/eval -v`. Every pipeline change is measured before/after.

---

## 7. The corpus — and why it blocks nothing

No access to the real internal documents (confidentiality). The demo corpus will be built
from **public** banking-regulation documents. This is a constraint to embrace, and even to
leverage in the report: since the corpus is public, the project is demonstrable and
publishable without any confidentiality risk — a genuine argument before the panel.

### Two distinct corpora

| Corpus                | Content                                                                    | Use                                    | Git                 |
| --------------------- | -------------------------------------------------------------------------- | -------------------------------------- | ------------------- |
| `corpus/bootstrap/` | 3-5 short**synthetic** documents (2-5 pages), hand-written, FR/EN/AR | automated tests — fast, deterministic | **committed** |
| `corpus/demo/`      | real public documents                                                      | demo + golden set                      | gitignored (volume) |

### Recommended public sources

- **FATF** — the 40 Recommendations exist in **French, English AND Arabic**, word for word.
  This is the ideal source: it allows testing cross-lingual retrieval on strictly
  equivalent content. To prioritize.
- **ACPR / Banque de France** — AML-CFT guidelines (FR)
- **Basel Committee (BCBS)** — *Sound management of risks related to money laundering* (EN)
- **EBA** — KYC/CDD guidelines (EN)
- **Bank Al-Maghrib / SAMA / Central Bank of the UAE** — circulars (AR)

Aim for ~10-15 documents, 20-80 pages each.

### The corpus blocks neither phase 1 nor phase 2

**No, and it is deliberately designed that way.** The ingestion pipeline does not depend on
the *content* of the documents, only on their *format* (PDF, DOCX). Splitting into two
corpora fully decouples the two efforts:

- The synthetic `corpus/bootstrap/` is written **in Week 0**, in an hour. It is enough to
  develop and test the entire ingestion pipeline, chunking, embedding, retrieval, and
  guardrails.
- The `corpus/demo/` is collected **in parallel**, in the background during Weeks 1 and 2
  (downloading public PDFs requires no code).
- The only milestone that truly depends on the real corpus is the **final golden set**, in
  Week 2 Day 5.

In other words: when the real documents arrive, they are *just data*. The code does not
change. This is exactly the benefit expected from a well-decoupled pipeline — and it is an
architectural argument to make at the defense.

---

## 8. Methodology: V-Model

**Decision: V-Model, with iterative delivery.** Not Waterfall.

### Why not the Waterfall model

Waterfall and the V-Model share exactly the same descending branch (requirements →
specifications → design → coding). The difference lies entirely in where testing sits:

- **In Waterfall**, testing is **a single phase, at the end**. A design flaw discovered
  during that phase forces going back up the whole chain. On a 4-week project, that is
  unforgiving: there is no slack for a full round trip.
- **In the V-Model**, each design level is **paired from the start with its test level**.
  You write the test plan when you write the specification, not three weeks later.

Choosing the V-Model therefore loses nothing from Waterfall — the V *contains* its
sequencing — and adds requirement ↔ test traceability. Waterfall is also considered
obsolete in the literature since the 1990s; defending it before a panel costs more than it
gains.

### Why the V-Model fits here

1. The scope is **frozen and known in advance** — that is the prerequisite of the V-Model,
   and it is met.
2. The developer is **alone**: solo Scrum (a daily standup with yourself, a sprint review
   in front of no one) is theater, and a knowledgeable panel penalizes it.
3. The **banking** context expects documentary rigor and traceability — the V-Model is
   culturally aligned with it.
4. **The V-Model produces exactly the report outline** — this is the decisive argument:

```
Requirements ─────────────────────────────► Acceptance / Business validation
  └─ Functional specifications ───────────► Validation tests (golden set)
      └─ Architectural design ────────────► Integration tests (API + DB + Keycloak)
          └─ Detailed design ─────────────► Unit tests (pytest)
              └────────── Coding ─────────┘
```

Each descending branch = a report chapter. Each ascending branch = a delivered proof.

### Why "with iterative delivery"

The strict V-Model assumes the specification is fully knowable up front. **That is false
for the RAG part**: you cannot specify "the answer will be relevant". RAG quality is
**empirical** — chunk size, similarity threshold, prompt, model choice are determined by
measurement, not by specification.

The chosen compromise:

- **V-Model for the overall structure** — the documentary deliverables (requirements
  specification, specifications, test plan, acceptance report).
- **3 short iterations in the implementation phase** (= Weeks 1, 2, 3), each closed by its
  test level.
- **A deliberate chapter "Empirical tuning of the RAG pipeline"** in the report,
  documenting the quantified experiments. This is not a methodological deviation to hide:
  it is the internship's technical contribution.

To say at the defense: *"I chose the V-Model because the scope was frozen and the banking
context demands traceability. I adapted it with iterative delivery, because the quality of
a RAG system cannot be specified — it is measured."*

### Documentary deliverables

`cahier-des-charges.md` (W0) · `specifications-fonctionnelles.md` (W0-W1) ·
`specifications-techniques.md` (W1) · `plan-de-tests.md` (W2) · `PV-de-recette.md` (W3) ·
ADRs on an ongoing basis.

**Written as we go, not in Week 4.**

---

## 9. Development phases

### Guiding principle: walking skeleton first

The initial plan was **horizontal**: all of auth, then all of RAG, then all of the
frontend. The risk is classic and severe — you discover integration problems (CORS, JWT
audience, Keycloak redirect URI, docker networking) in Week 3, when there is no slack left.

**Inverted logic: an end-to-end vertical slice by the end of Week 1.** Even if ugly, even
with a single document: Keycloak login → question → sourced answer in the browser. All the
integration risks are purged in Week 1 instead of blowing up in Week 3.

---

### Week 0 — Preparation (2-3 days)

- [X] Complete Docker Compose: postgres+pgvector, keycloak, ollama, api, web.
  **Everything must come up with a single `docker compose up`.** — 5 containers `running`.
- [X] Keycloak realm configured (registration off, 3 clients, 2 roles) and **exported as versioned JSON**

- [~] `ollama pull qwen3:4b-instruct-2507-q4_K_M` + `qwen3:1.7b` + `bge-m3` (~4 GB)
  — re-pull in progress into the `knowveris_ollama_models` volume (bge-m3 OK, qwen3 4B/1.7B in progress)

- [X] Postgres extensions verified: `vector`, `pg_trgm`, `uuid-ossp` installed (init.sql).
- [X] Verify available FTS configs: `SELECT cfgname FROM pg_ts_config;`
  → **`arabic`, `french`, `english`, `simple` all present** (Postgres 16). No fallback
  needed: the AR path of hybrid search is fully supported (W0 risk cleared).

**Deliverable:** reproducible environment + `docs/cahier-des-charges.md`

---

### Week 1 — Foundations + walking skeleton

| Day   | Objective                                                                                                                                                            |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1-D2 | SQLAlchemy models, Alembic migrations,`CREATE EXTENSION vector`, HNSW + GIN indexes                                                                                |
| D2-D3 | `core/security.py`: JWT validation via JWKS, audience check, deps `get_current_user` / `require_admin`, JIT provisioning                                       |
| D3-D4 | Ingestion pipeline: PDF/DOCX parsers (page/section), language detection, chunker, BGE-M3 embedder, indexer +`status` state machine                                 |
| D5    | **🎯 Walking skeleton**: naive `POST /api/v1/chat` (vector search only, top-3, simple prompt) + minimal React page with Keycloak login                       |
| D5    | **🎯 Model benchmark**: `qwen3:4b` vs `qwen3:1.7b` on 5 bootstrap questions → measure tok/s, prefill, total latency. **Decide now, not in Week 4.** |

**W1 checkpoint:** an employee logs in and gets an answer citing a document. If that is not
the case by Friday evening, **the schedule is at risk** — alert the supervisor immediately.

---

### Week 2 — RAG quality + complete API

| Day   | Objective                                                                                                                                                                                                                                                                   | Status                                                         |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| D1    | Hybrid search: Postgres FTS per language + RRF fusion                                                                                                                                                                                                                       | ✅ done                                                        |
| D2    | Reranker behind a feature flag + similarity-threshold calibration                                                                                                                                                                                                           | ✅ done (threshold 0.35→0.50, measured)                       |
| D2-D3 | Guardrails: strict system prompt,`temperature=0`, refusal below threshold, post-generation citation validation, explicit language instruction                                                                                                                             | ✅ done (W1 + calibrated)                                      |
| D3    | SSE streaming + persistence of conversations/messages/citations                                                                                                                                                                                                             | ✅ done (persistence W1)                                       |
| D4    | Admin endpoints: upload, list, status, deletion (cascade over chunks) +`audit_logs`                                                                                                                                                                                       | ✅ done                                                        |
| D4    | `admin/users` endpoints via the **Keycloak Admin REST API** (service account)                                                                                                                                                                                       | ✅ done                                                        |
| D5    | **Golden set** (~35 Q/A) + evaluation script. Measure **with and without the reranker** → latency/precision table for the report                                                                                                                               | ✅ harness + 18-Q bootstrap set; live reranker table deferred* |
| D5    | **Latency re-benchmark on a quiet machine** (VSCode/Chrome closed, §5) + tune `OLLAMA_NUM_PREDICT` — the W1 J5 run measured ~2.6/3.8 tok/s (4b/1.7b) under full IDE load, ~3× below estimate; re-measure alongside the golden set to lock the 4b-vs-1.7b default | ⏳ deferred (needs quiet machine)*                             |

**W2 checkpoint:** complete, tested, **measured** API. Recall@3 and correct-refusal-rate
figures available. **✅ Met** — on the 18-question bootstrap golden set (calibrated
threshold 0.50): **Recall@3 = 100%, MRR = 0.929, correct-refusal = 100%, false-refusal = 7.1%**.

\* Deferred measurement-only items (need external resources, not code): the live
**with/without-reranker** precision/latency table needs the `FlagEmbedding`+torch
dependency installed (~2 GB image/RAM — a confirmed infra decision), and the
**quiet-machine latency re-benchmark** + `OLLAMA_NUM_PREDICT` tuning needs the demo
machine idle. Both feed the report; neither blocks Week 3. The ~35-question FATF/ACPR
demo golden set is authored once `corpus/demo/` is collected (PLAN §7).

---

### Week 3 — Frontend

| Day | Objective                                                                                                         | Status                          |
| --- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| D1  | Setup: React Router,`react-oidc-context`, TanStack Query, JWT Axios interceptor, ProtectedRoute + RoleGuard     | ✅ done                         |
| D2  | 3-column layout + Left Sidebar (avatar, profile)                                                                  | ✅ done                         |
| D2  | Center Panel: StatsCard (conversation count) + HistoryCard → History page                                        | ✅ done (+ delete conversation) |
| D3  | Right Panel: chat with streaming +**SourceCard** (document, page/section, score) + RTL rendering for Arabic | ✅ done                         |
| D4  | Admin: drag & drop DropZone + indexing-status table (polling)                                                     | ✅ done                         |
| D4  | Admin: employee-account management screen (creation + temporary password shown once)                              | ✅ done                         |
| D5  | Error handling, loading states, responsive design, session expiration                                             | ✅ done (+ favicon)             |
| D5  | *Nice-to-have if time permits*: multi-turn (see below)                                                          | ⏳ not started                  |

**W3 checkpoint:** complete, end-to-end demonstrable application. **✅ Met** — routing +
OIDC, 3-column layout, SSE streaming chat with sources and RTL, admin documents and
employee accounts, and (D5) a hardened shell: error boundary, retryable error states,
toast notifications, mobile drawer layout, and an explicit session-expiration dialog that
returns the user to the page they were on.

---

### Week 4 — Report, defense, buffer

| Day   | Objective                                                                                                                |
| ----- | ------------------------------------------------------------------------------------------------------------------------ |
| D1    | **Buffer** — this is where we absorb the delay (there will be some). If all goes well: polish + integration tests |
| D2-D3 | Writing the report                                                                                                       |
| D4    | Slides +**demo rehearsal** (scripted scenario, prepared questions, plan B)                                         |
| D5    | presentation                                                                                                             |

**Rehearse the demo at least twice under real conditions.** Record a **backup video**:
with 60-90 s of latency per answer on CPU, a live demo that goes off the rails costs more
than everything else.

---

### Multi-turn: the lightweight version

Multi-turn ("and for a minor client?") normally requires **query rewriting**: an extra LLM
call to reformulate the question into a standalone question. On CPU, that is **+30 to 60 s
per question** — unacceptable.

**Chosen version (no extra LLM call)**: concatenate the previous question and the current
question *only for the retrieval phase* (a textual "query fusion"), and pass the last 2
turns into the prompt context. This covers the majority of follow-up cases at near-zero
cost.

Triggered by heuristic: question < 8 words, or the presence of an anaphora ("and for",
"this one", "in that case"). Behind a feature flag, measured on the golden set.

LLM-based query rewriting goes into the report's "future work".

---

## 10. Out of scope (to mention as future work, not to code)

Celery/Redis · multi-tenancy · OCR of scans · per-role document partitioning ·
fine-tuning · Kubernetes · semantic cache · Prometheus/Grafana monitoring ·
LLM-based query rewriting · server deployment (the demo runs locally).

---

## 11. Identified risks

| Risk                                             | Impact                                | Mitigation                                                                                   |
| ------------------------------------------------ | ------------------------------------- | -------------------------------------------------------------------------------------------- |
| **Untenable CPU latency** (> 2 min/answer) | demo compromised                      | benchmark from W1 D5,`qwen3:1.7b` fallback locked in, short chunks, top_k=3, SSE streaming |
| **RAM saturated** (~13.8 / 15.4 GB)        | swapping, everything becomes unusable | BGE-M3 in Ollama, limited Keycloak heap, lazy reranker, close VSCode/Chrome for the demo     |
| Keycloak ↔ FastAPI ↔ SPA integration           | multi-day blockage                    | walking skeleton in W1, not W3                                                               |
| Quality Arabic corpus hard to find               | AR requirement not demonstrable       | FATF publishes in AR — identified, to be downloaded in W0                                   |
| `arabic` FTS config missing from Postgres      | degraded AR hybrid search             | ✅ cleared in W0:`arabic` present (Postgres 16), no fallback needed                        |
| Accumulated delay                                | rushed report                         | W4 D1 is an explicit buffer; the documentary deliverables are written on an ongoing basis    |

```

```

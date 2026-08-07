# Task List - FDA Regulatory Intelligence Platform

## Overview
This document tracks all tasks for building the citation-first FDA Regulatory Intelligence Platform. Tasks are organized by phase and component and align with `PLANNING.md`. The MVP is a hybrid RAG product (PostgreSQL + pgvector + OpenSearch + reranking + LangGraph guardrails) with verifiable citations; the temporal knowledge graph (Graphiti + Neo4j) is deferred to V1.

Legend: `[ ]` pending, `[~]` in progress, `[x]` complete.

---

## Phase 1: Foundation & Setup

### Project Structure
- [x] Create repository structure (`apps/`, `src/`, `data/`, `infra/`, `tests/`)
- [x] Set up `.gitignore` for a Python + Node project
- [x] Create `.env.example` with all required variables
- [x] Include Azure OpenAI variables in `.env.example` (`LLM_PROVIDER`, endpoint, API key, API version, deployment, model choice)
- [x] Configure `pyproject.toml` and dependency management
- [~] Author `docker-compose.yml` (PostgreSQL + pgvector, OpenSearch, Langfuse done; local artifact storage requires no service container; API + web app containers deferred to their phases)

### Infrastructure Setup
- [x] Stand up PostgreSQL + pgvector with a persistent volume (dense vectors + relational data in one engine)
- [x] Initialize the PostgreSQL `vector` extension for the MVP database (`infra/docker/postgres-init.sql`)
- [x] Stand up OpenSearch (single-node) with a persistent volume
- [x] Provision the same PostgreSQL instance for metadata, users, sessions, and audit trail
- [x] Replace S3/MinIO requirement with local filesystem artifact storage for raw PDFs, HTML, catalog snapshots, and reports
- [x] Configure Langfuse for tracing
- [~] Add health checks for API readiness, retrieval stores, ingestion scheduler, and background workers (compose service health checks + API `/health` done; scheduler/worker liveness deferred)
- [~] Configure separate development, staging, and pilot environment files (`APP_ENV` switch + `.env.example` done; per-env files deferred)

### Base Models & Configuration
- [x] Create Pydantic v2 settings (`apps/api/settings.py`)
- [x] Add Phase 1 smoke-test coverage for pgvector settings defaults
- [x] Define document and metadata models
- [x] Define chunk and embedding models
- [x] Define `SearchResult` and `Answer` models
- [x] Define the `EvidenceCard` model (per PLANNING schema)
- [x] Define audit trail and alert record models
- [x] Set up structured logging configuration

---

## Phase 2: Ingestion System (Two-Tier, Catalog-First)

> Data source: FDA guidance **static JSON catalog**
> (`https://www.fda.gov/files/api/datatables/static/search-for-guidance.json`).
> Tier 1 = cheap daily metadata sync → PostgreSQL `guidance_registry`.
> Tier 2 = incremental content ingestion (PDF → parse → chunk → embed → index) for NEW/UPDATED docs only.
> See `Docs/implementation/Plan-Phase 2 - Ingestion System.md`.

### Foundations
- [x] Add async SQLAlchemy engine + session factory (`src/common/db.py`, asyncpg)
- [x] Define `GuidanceRegistry` ORM model + `LifecycleState` enum (`src/db/models.py`)
- [x] Add Alembic migration for `guidance_registry` (or `metadata.create_all` bootstrap)
- [x] Refactor storage client to local filesystem artifact adapter (`src/common/storage.py`) with path-safety checks and atomic writes
- [x] Add PostgreSQL source-artifact metadata model + Alembic migration (`source_artifacts`)
- [x] Add shared PostgreSQL (pgvector) + OpenSearch client factories (`src/common/clients.py`)
- [x] Extend `DocumentMetadata` (center, topic, communication_type, regulated_product, issue_date, fda_last_changed, comment_close, open_comment, lifecycle_state) + add `DocumentVersion`
- [x] Add Phase 2 dependencies (`alembic`, `beautifulsoup4`; `pgvector` already present)
- [x] Add settings (`FDA_GUIDANCE_JSON_URL`, `FDA_BASE_URL`, chunk sizes, `EMBED_BATCH_SIZE`, `INGEST_SCHEDULE_CRON`, pgvector table + 1024-dim)

### Tier 1 — Catalog Sync (metadata registry)
- [x] Fetch static FDA JSON catalog and snapshot raw (date-stamped) to local artifact storage + `source_artifacts` metadata
- [x] Normalize rows (HTML unescape, extract href/datetime/text, split topics, decode entities) → derive `slug`
- [x] Upsert `guidance_registry` in PostgreSQL keyed by `slug`
- [x] Diff incoming vs stored → emit NEW / UPDATED / WITHDRAWN change events (`(slug, fda_last_changed, status)`)
- [x] Detect Withdrawn via feed set-diff (prior slug absent → soft-delete `lifecycle_state`)
- [x] Run one-time full metadata backfill (no downloads) (`2787` registry rows loaded from local full FDA snapshot)

### Tier 2 — Content Ingestion (NEW/UPDATED only)
- [x] Resolve PDF URL: registry `pdf_url` first → landing-page fallback (BeautifulSoup) → else HTML body
- [x] Download and preserve raw PDF/HTML to local artifact storage (`raw/{slug}/{sha256}.pdf`) + `source_artifacts` metadata
- [x] Compute SHA-256 content hash; skip re-parse when unchanged; snapshot per version
- [x] Record status/lifecycle transitions (Draft → Final, Active → Withdrawn) + supersedes via `docket_id`
- [x] Implement PDF parsing with PyMuPDF (text, sections, page offsets)
- [x] Add Unstructured for table extraction
- [x] Implement parent-child chunking (section parent, paragraph child)
- [x] Preserve section hierarchy, page, and char offsets in chunk metadata
- [x] Implement BGE-M3 embedding generation with batching and progress tracking

### Indexing
- [x] Index dense vectors in PostgreSQL (pgvector) with evidence-card payloads (deterministic IDs `{slug}:{version_hash}:{chunk_no}`)
- [x] Index BM25 content in OpenSearch with metadata
- [x] Implement re-index-only-changed logic (delete + reindex changed, remove withdrawn); update registry `last_synced_at`

### Orchestration & Reporting
- [x] Generate a daily update report (new / updated / withdrawn) to local artifact storage
- [x] Orchestrate both tiers in `pipeline.py`; schedule Tier-1 daily with APScheduler
- [x] Trigger Tier-2 from change events with a bounded worker pool + rate limiting/backoff
- [x] Add nightly reconciliation (registry active count == indexed doc count) + per-doc outcome logging

---

## Phase 3: Retrieval & Reranking

> Hybrid retrieval: PostgreSQL + pgvector dense search and OpenSearch BM25 keyword search,
> fused with Reciprocal Rank Fusion and reranked with BGE-Reranker-Large, formatted into
> citation-first Evidence Cards.
> See `Docs/implementation/Plan-Phase 3 - Retrieval & Reranking.md`.

### Retrieval Clients
- [x] Implement PostgreSQL + pgvector dense search client
- [x] Implement OpenSearch BM25 client
- [x] Implement metadata filters (center, date, status, docket, CFR, product code)

### Fusion & Reranking
- [x] Implement Reciprocal Rank Fusion of dense + sparse results
- [x] Integrate BGE-Reranker-Large cross-encoder
- [x] Add top-k selection and result formatting
- [ ] Tune retrieval parameters against the gold set (deferred until `eval/golden_set.json` is curated in Phase 6)

---

## Phase 4: Agent Workflow (LangGraph)

> Controlled LangGraph workflow for citation-first answer generation: query understanding,
> hybrid retrieval, confidence checks, grounded generation, fail-closed citation binding,
> faithfulness validation, bounded retries, and refusal behavior.
> See `Docs/implementation/Plan-Phase 4 - Agent Workflow.md`.

### Graph Foundation
- [x] Define typed LangGraph state (query, entities, candidates, evidence, confidence)
- [x] Build the StateGraph assembler (`agents/graph.py`)
- [x] Implement conditional routing edges

### Workflow Nodes
- [x] `query_understand` — rewrite, classify intent, extract FDA entities
- [x] `retrieval_router` — route hybrid vs metadata-constrained
- [x] `hybrid_retrieve` — pgvector + BM25 + RRF
- [x] `merge_rerank` — cross-encoder reranking
- [x] `confidence_check` — refuse-on-low-confidence
- [x] `generate_answer` — citation-first grounded generation
- [x] `citation_bind` — attach Evidence Cards
- [x] `faithfulness_guard` — validate answer against evidence with bounded retry
- [x] `respond` — final payload (answer, citations, confidence)

### LLM Integration
- [x] Implement provider abstraction (`llm/router.py`) with Azure OpenAI primary
- [x] Configure Azure OpenAI endpoint, API version, deployment, and model selection
- [x] Add Claude Sonnet and vLLM (Llama 3.3 / Qwen) fallback support
- [x] Author citation-first prompt templates
- [x] Implement token streaming utilities

### Guardrails
- [x] Implement confidence scoring logic
- [~] Implement faithfulness validation (protocol + deterministic default done; RAGAS / HHEM calibration remains Phase 6)
- [x] Implement refusal responses
- [x] Implement fail-closed citation binding

---

## Phase 5: API Backend, Reporting & Monitoring

> Backend API implementation only. Frontend planning and implementation are intentionally split into a separate future plan.
> See `Docs/implementation/Plan-Phase 5 - API Backend.md`.

- [x] Review and re-baseline the Phase 5 plan against the current implementation

### FastAPI Setup
- [x] Create main FastAPI application and register Phase 5 routers
- [x] Configure CORS, request-id middleware, and structured logging startup
- [x] Set up lifespan / dependency injection with shared process resources
- [x] Add and register global structured exception handlers
- [x] Load BGE-M3, BGE reranker, provider clients, and compiled LangGraph once per process

### API Endpoints
- [x] `chat` endpoint with node-boundary SSE streaming and one durable final event
- [x] `search` endpoint with validated filters and explicit retrieval diagnostics
- [x] `documents` endpoint (metadata, versions, sections, passages, and authorized artifact download by known id)
- [x] `summaries` endpoint
- [x] `exports` endpoint
- [x] `alerts` endpoint
- [x] `health` liveness and dependency-aware readiness endpoints
- [x] Session create/history endpoints backed by server-owned sessions and turns
- [x] Admin audit-inspection endpoint with pagination and recursive payload redaction
- [x] Include tool-usage / node-execution transparency in API responses

### Security & Audit
- [x] Add Supabase JWT authentication, explicit issuer/audience/algorithm validation, application RBAC, and ownership checks
- [x] Add independent route rate limits and per-user concurrent SSE stream caps
- [x] Persist transactional audit records for queries, generated answers, Evidence Cards, refusals, exports, alerts, and downloads
- [x] Validate request payloads and retrieval filters with Pydantic v2 models
- [x] Add server-owned chat session, immutable turn, and grounded-summary ORM records + migration
- [x] Replace client-supplied export content with authorized session/summary identifiers
- [x] Add structured retrieval success/empty/failure outcomes and sanitized diagnostic codes

### Summarization & Export
- [x] Implement citation-bound guidance summaries, key requirements, and version-scoped key changes with faithfulness validation
- [x] Implement durable text / Word / PDF summary export
- [x] Implement authorized chat transcript export from persisted final turns
- [x] Create grounded report templates with citation and version metadata

### Update Monitoring
- [x] Implement alert records with deterministic database-enforced event fingerprints and idempotent upsert
- [x] Implement forward-only alert lifecycle, draft/final tracking, and version diffs
- [x] Wire the daily monitoring scheduler to Phase 2 registry change events

### Phase 5 Validation
- [x] Pass the full repository test suite (`145 passed`)
- [x] Pass Ruff and Black checks for Phase 5 implementation files
- [x] Pass scoped Mypy validation for all 42 Phase 5 source files
- [x] Validate one Alembic head and generate the complete offline PostgreSQL upgrade SQL
- [x] Execute the Phase 5 Alembic migration against live PostgreSQL and verify API tables and key constraints
- [ ] Resolve inherited repository-wide Mypy findings in Phase 2-4 ingestion, retrieval, LLM, and agent modules

### Frontend (Phase 5B - Separate Plan)

> See `Docs/implementation/Plan-Phase 5B - Frontend Application.md`.

- [x] Create the separate Next.js 15 + shadcn/ui frontend implementation plan
- [ ] Add paginated `GET /api/sessions` for session restoration
- [ ] Add stable `chunk_id` targets to Evidence Cards
- [ ] Replace public object-store keys with authorized artifact descriptors
- [ ] Add owner-checked `GET /api/summaries/{summary_id}` for durable reload
- [ ] Add typed search filters, structured errors, and an SSE protocol artifact to OpenAPI generation
- [ ] Expose download/request/rate-limit headers through CORS and emit `Retry-After`
- [ ] Add pagination to `GET /api/alerts`
- [ ] Scaffold `apps/web` with Next.js 15, TypeScript strict mode, Tailwind, and shadcn/ui
- [ ] Add Supabase SSR authentication and protected researcher/admin layouts
- [ ] Generate typed FastAPI contracts and implement the authenticated API/SSE clients
- [ ] Implement hybrid search, filters, evidence results, and diagnostics
- [ ] Implement durable chat sessions, node-boundary streaming, refusals, and citation panels
- [ ] Implement the PDF/HTML document viewer, section navigation, and passage highlighting
- [ ] Implement grounded summaries, key changes, and authorized exports
- [ ] Implement update alerts and admin audit inspection
- [ ] Add responsive, accessibility, security, and performance hardening
- [ ] Add Vitest, Testing Library, MSW, Playwright, and axe coverage
- [ ] Pass frontend lint, typecheck, test, build, accessibility, and browser workflow gates

---

## Phase 6: Evaluation & Observability

### Evaluation
- [ ] Curate the FDA gold set (`eval/golden_set.json`)
- [ ] Implement RAGAS faithfulness and answer-quality evaluation
- [ ] Implement Vectara HHEM hallucination check
- [ ] Add nightly quality regression run

### Observability
- [ ] Integrate Langfuse tracing across LangGraph spans
- [ ] Add prompt and output logging
- [ ] Add usage analytics and error tracking
- [ ] Capture confidence, citation, refusal, and faithfulness metrics

---

## Phase 7: MVP Release Hardening

### Release Quality Gates
- [ ] Citation coverage: 100% of answers include ≥ 1 Evidence Card
- [ ] Citation validity: 100% resolve to source/section/page/passage/version/URL
- [ ] Retrieval recall@10 ≥ 90% on gold set
- [ ] Grounded accuracy ≥ 95%
- [ ] Hallucination rate ≤ 5%
- [ ] Refusal behavior validated on low-evidence queries
- [ ] Latency < 5 seconds for standard Q&A
- [ ] Freshness: daily ingestion detects new/updated/withdrawn guidance

### Deployment & Operations
- [ ] Configure persistent volumes for all stateful services
- [ ] Implement backups (PostgreSQL metadata + vectors, local artifact directory, OpenSearch)
- [ ] Write health-check and deployment runbooks
- [ ] Separate dev / staging / pilot environments
- [ ] Pilot with a controlled FDA guidance corpus
- [ ] Validate Docker Compose deployment on a single VM

---

## Testing

### Unit Tests
- [ ] Ingestion: catalog normalize, registry diff (NEW/UPDATED/WITHDRAWN), PDF resolver, parser, versioning, chunking, embeddings
- [x] Retrieval: dense, BM25, RRF, reranker, filters
- [x] Agent: each node, guardrails, citation binding
- [~] API: focused routing, auth, streaming ordering, validation, readiness, redaction, rate-limit, and export-contract tests complete; add database-backed endpoint integration coverage

### Integration Tests
- [ ] End-to-end ingestion pipeline
- [ ] End-to-end query → citation-bound answer flow
- [ ] Refusal and retry paths
- [ ] Daily update monitoring and alert flow
- [ ] Export flow for summaries and chat transcripts
- [ ] Concurrent operations and error recovery

### Test Infrastructure
- [ ] Create test fixtures and sample FDA corpus
- [ ] Mock external dependencies (LLM, stores)
- [ ] Configure CI test environment

---

## Quality Assurance

### Code Quality
- [ ] Run formatter (black) across the codebase
- [ ] Run linter (ruff) and fix issues
- [ ] Check type hints (mypy)
- [ ] Review for OWASP Top 10 security issues
- [ ] Optimize hot paths (retrieval, embedding, reranking)

### Final Review
- [ ] Review all documentation
- [ ] Validate environment variables and secrets handling
- [ ] Validate data-store schemas and indexes
- [ ] Validate rate limiting, audit trail, and RBAC behavior
- [ ] Verify all MVP features work
- [ ] Create demo scenarios

---

## V1: Knowledge Graph Extension (Deferred)

### Graph Setup
- [ ] Deploy Neo4j alongside PostgreSQL/OpenSearch
- [ ] Configure Graphiti client (`graph/graphiti_client.py`)
- [ ] Define FDA ontology entities and relationships (`graph/ontology.py`)

### Graph Ingestion & Retrieval
- [ ] Implement episode builder (FDA document → Graphiti episode)
- [ ] Implement graph search, related-entity, and timeline queries
- [ ] Add `graph_retrieve` LangGraph node with routing rules

### V1 Capabilities
- [ ] Cross-guidance comparison
- [ ] Draft vs final diff visualization
- [ ] Document-evolution timelines
- [ ] Entity-centric reasoning (CFR, center, docket, product code, topic)

---

## Future Enhancements (Post-V1)

### V2
- [ ] On-prem model serving
- [ ] Multi-tenancy

### V3
- [ ] Fine-tuned embeddings
- [ ] DSPy prompt optimization
- [ ] Multi-hop agent workflows

### Expansion
- [ ] Multi-regulator expansion (EMA, PMDA)
- [ ] Regulatory trend analytics

---

## Discovered During Work
- [x] Widen `guidance_registry.regulated_product` and `guidance_registry.docket_id` for long FDA catalog values (`20260720_0003`)

---

## Project Status

🏗️ **Phase 1 (Foundation & Setup) largely complete.** Repo structure, config, dependency
management, docker-compose infra (PostgreSQL + pgvector, OpenSearch, Langfuse), Pydantic
settings, structured logging, and all core models are in place and validated by smoke tests.

Storage pivot implemented: MVP artifact storage is now local filesystem + PostgreSQL artifact metadata; MinIO/S3 is no longer required for the MVP and remains a possible future adapter.

Phase 2 is implemented: foundation storage/metadata pieces, Tier 1 catalog sync/backfill, Tier 2 raw source acquisition, version tracking, PDF parsing, table extraction, parent-child chunking, BGE-M3 embedding generation, pgvector dense indexing, OpenSearch BM25 indexing, re-index-only-changed cleanup, daily reports, and ingestion orchestration are in place.

Phase 3 retrieval is implemented; gold-set tuning remains pending until the Phase 6 evaluation set exists. Phase 4 LangGraph orchestration and Phase 5 API backend, reporting, monitoring, security, persistence, and live migration validation are implemented.

Next milestone: close the Phase 5B frontend API contract gates, then implement the **Next.js 15 + shadcn/ui frontend application** from `Docs/implementation/Plan-Phase 5B - Frontend Application.md`.

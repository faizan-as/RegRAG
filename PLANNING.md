# FDA Regulatory Intelligence Platform - Project Plan

## Project Overview

This project builds a citation-first, AI-powered regulatory intelligence platform that lets regulatory professionals query FDA guidance documents and retrieve reliable citation-backed answers. The MVP combines hybrid retrieval (dense vector search + BM25 keyword search) with a controlled LangGraph agent workflow and strict faithfulness guardrails. The V1 extension adds guidance comparison and document-evolution intelligence with a temporal knowledge graph after the hybrid RAG core is stable.

The single non-negotiable principle: **every answer ships with a verifiable FDA citation.**

## Reference Implementation

Before implementation work begins, review the reference project [agentic-rag-knowledge-graph](https://github.com/coleam00/ottomator-agents/tree/main/agentic-rag-knowledge-graph). It is a strong conceptual fit because its problem shape — search a corpus, reason over relationships, and track change over time — is structurally similar to FDA guidance intelligence.

Use the reference repo for guidance on:
- Corpus ingestion pipeline structure.
- Agent/tool interface boundaries.
- Streaming API behavior.
- Dual retrieval/graph architecture pattern.
- Episode-based ingestion patterns for future Graphiti work.

Do not copy the reference stack directly for the MVP:
- Use LangGraph instead of Pydantic AI.
- Use PostgreSQL + pgvector for dense retrieval and OpenSearch for BM25 (consolidate relational data and embeddings into one Postgres engine; do not introduce Qdrant in the MVP).
- Keep Graphiti + Neo4j deferred to V1.
- Add FDA-specific Evidence Cards, citation binding, confidence checks, refusal behavior, and faithfulness validation.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend Layer                        │
│  ┌─────────────────┐        ┌────────────────────┐      │
│  │  Next.js 15     │        │   Streaming Chat   │      │
│  │  shadcn/ui      │        │   Document Viewer  │      │
│  └────────┬────────┘        └────────────────────┘      │
├───────────┴──────────────────────────────────────────────┤
│                    API Layer                             │
│  ┌─────────────────┐        ┌────────────────────┐      │
│  │   FastAPI       │        │   Streaming SSE    │      │
│  │   Endpoints     │        │   Responses        │      │
│  └────────┬────────┘        └────────────────────┘      │
├───────────┴──────────────────────────────────────────────┤
│                 Orchestration Layer                      │
│  ┌─────────────────┐        ┌────────────────────┐      │
│  │   LangGraph     │◄──────►│   Agent Nodes      │      │
│  │   State Graph   │        │  - Hybrid Retrieve │      │
│  │   + Guardrails  │        │  - Rerank          │      │
│  └────────┬────────┘        │  - Citation Bind   │      │
│           │                 │  - Faithfulness    │      │
│           │                 └────────────────────┘      │
├───────────┴──────────────────────────────────────────────┤
│                    Retrieval Layer                       │
│  ┌─────────────────┐        ┌────────────────────┐      │
│  │  PostgreSQL     │        │    OpenSearch      │      │
│  │  + pgvector     │        │   (BM25 keyword)   │      │
│  │  (dense vector) │        │                    │      │
│  └─────────────────┘        └────────────────────┘      │
│           RRF fusion + BGE-Reranker-Large                │
└─────────────────────────────────────────────────────────┘
```

## MVP Scope Boundary

### In MVP
- FDA guidance documents only.
- PDF + metadata ingestion.
- Draft / Final / Withdrawn status tracking.
- Hybrid search using PostgreSQL + pgvector dense retrieval and OpenSearch BM25.
- Metadata filters by center, topic, date, status, docket, CFR, and product code.
- Reranking with BGE-Reranker-Large.
- Citation-first RAG answers with Evidence Cards.
- Refuse-on-low-confidence behavior.
- Faithfulness validation before final response.
- Basic document viewer with highlighted passages and section navigation.
- One-click guidance summaries, key requirements, and key changes.
- Export of summaries and chat transcripts.
- Daily update monitoring and alert records.

### V1 / Post-MVP
- Graphiti / Neo4j knowledge graph.
- Entity timelines and graph traversal.
- Cross-regulator coverage (EMA, PMDA, etc.).
- FDA Warning Letters / 483 analysis.
- Compliance decision-making or legal advice.
- Fine-tuned proprietary LLM.
- Full RIM workflow or agentic automation workflows.

## MVP Definition of Done

- A controlled FDA guidance corpus can be ingested end to end.
- Raw PDFs, source landing pages, parsed text, metadata, and version snapshots are persisted.
- Hybrid retrieval returns dense + BM25 results with metadata filters.
- RRF and reranking produce a final evidence set for generation.
- Every generated answer includes at least one valid Evidence Card.
- Unsupported or weakly supported questions route to refusal instead of generation.
- Faithfulness validation runs before the final response is returned.
- Document viewer can open cited source passages from an answer.
- Summaries, key requirements, key changes, and chat transcripts can be exported.
- Daily update monitoring detects new, updated, and withdrawn guidance.
- MVP release quality gates pass on the FDA gold set.

## Core Components

### 1. Agent System (`/src/agents`)
- **state.py**: LangGraph typed state definition (query, entities, candidates, evidence, confidence).
- **nodes.py**: The MVP workflow nodes (query_understand, retrieval_router, hybrid_retrieve, merge_rerank, confidence_check, generate_answer, citation_bind, faithfulness_guard, respond).
- **edges.py**: Conditional routing logic between nodes.
- **guardrails.py**: Confidence check and faithfulness validation with bounded retry.
- **citation.py**: Binds `[n]` references to Evidence Cards.
- **graph.py**: StateGraph builder that assembles nodes and edges.

### 2. LLM System (`/src/llm`)
- **router.py**: Provider abstraction (Azure OpenAI primary; Claude Sonnet and Llama 3.3 / Qwen via vLLM fallback).
- **prompts.py**: Citation-first prompt templates.
- **streaming.py**: Token streaming utilities for SSE.

### 3. Retrieval System (`/src/retrieval`)
- **pgvector_client.py**: Dense vector search (PostgreSQL + pgvector).
- **opensearch_client.py**: BM25 keyword search.
- **hybrid.py**: Reciprocal Rank Fusion of dense + sparse results.
- **reranker.py**: BGE-Reranker-Large cross-encoder for top-k precision.
- **filters.py**: Metadata filters (center, date, status, docket, CFR, product code).

### 4. Ingestion System (`/src/ingestion`)

Two-tier, catalog-first architecture driven by the FDA guidance **static JSON catalog**
(`https://www.fda.gov/files/api/datatables/static/search-for-guidance.json`).

**Tier 1 — Catalog Sync (cheap, complete, daily):**
- **fda_catalog.py**: Fetch the static JSON catalog, snapshot raw to the local artifact store, and normalize
  HTML-escaped rows (title/slug, status, center, topics, docket, dates, `changed`).
- **registry.py**: Upsert the PostgreSQL `guidance_registry` (keyed by `slug`) and diff against the
  previous sync to emit NEW / UPDATED / WITHDRAWN change events.

**Tier 2 — Content Ingestion (incremental, NEW/UPDATED only):**
- **pdf_resolver.py**: Resolve the PDF URL (feed link first, landing-page fallback, else HTML body).
- **pdf_parser.py**: PyMuPDF + Unstructured text and table extraction.
- **version_tracker.py**: SHA-256 content hashing, version snapshots, supersedes detection.
- **chunking.py**: Parent-child chunking (section-level parent, paragraph-level child).
- **embedder.py**: BGE-M3 embedding generation.
- **indexer.py**: PostgreSQL + pgvector dense + OpenSearch BM25 indexing with evidence-card payloads.
- **report.py**: Daily new/updated/withdrawn update report.
- **pipeline.py**: APScheduler orchestration of both tiers (Prefect deferred).

### 5. Summarization & Export System (`/src/reports`)
- **summarizer.py**: Generates guidance summaries, key requirements, and key changes from grounded evidence.
- **exporter.py**: Produces Word / PDF summaries and chat transcript exports.
- **templates.py**: Report templates for regulatory review and internal documentation.

### 6. Update Monitoring System (`/src/monitoring`)
- **alerts.py**: Creates alert records for new, updated, and withdrawn guidance.
- **diffs.py**: Generates draft vs final and version-to-version change summaries.
- **scheduler.py**: Runs daily update checks.

### 7. API Layer (`/apps/api`)
- **main.py**: FastAPI application entrypoint.
- **routes/**: `chat`, `search`, `documents`, `summaries`, `exports`, `alerts`, `health` endpoints with SSE streaming.
- **schemas/**: Pydantic v2 models (Answer, EvidenceCard, SearchResult).
- **deps.py**: Dependency injection for LLM, embedder, PostgreSQL (pgvector), OpenSearch.
- **settings.py**: Pydantic settings.

### 8. Frontend (`/apps/web`)
- Next.js 15 + shadcn/ui streaming chat, search UI, and document viewer with highlighted citations.

### 9. Evaluation (`/src/eval`)
- **golden_set.json**: Curated FDA question/answer gold set.
- **ragas_eval.py**: RAGAS faithfulness and answer-quality evaluation.
- **hhem_check.py**: Vectara HHEM hallucination check.

### 10. Tests (`/tests`)
- Unit, integration, and nightly evaluation regression tests with mocked external dependencies.

## Technical Stack

### Core Technologies
- **Python 3.11+**: Primary language
- **LangGraph**: Agent orchestration framework
- **FastAPI**: API framework
- **PostgreSQL + pgvector**: Relational store and vector database (dense retrieval)
- **OpenSearch**: Keyword search (BM25)
- **BGE-M3**: Embedding model
- **BGE-Reranker-Large**: Cross-encoder reranker
- **Azure OpenAI**: Primary LLM provider (Claude Sonnet and vLLM Llama 3.3 / Qwen fallback)
- **Next.js 15 + shadcn/ui**: Frontend

### Key Libraries
- **llama-index-core**: Ingestion and retrieval helper utilities
- **pgvector / opensearch-py**: Retrieval clients
- **sentence-transformers**: Embeddings and reranking
- **pymupdf / unstructured**: PDF parsing
- **prefect / apscheduler**: Ingestion scheduling
- **pydantic v2 / pydantic-settings**: Validation and config
- **sse-starlette**: Streaming responses
- **supabase / pathlib / SQLAlchemy / asyncpg**: Auth, local artifact storage, and consolidated PostgreSQL access
- **langfuse**: Tracing and observability
- **ragas**: Evaluation
- **pytest + pytest-asyncio**: Testing

## Design Principles

### 1. Citation-First
- Every generated answer must include traceable Evidence Cards (doc ID, section, passage, version hash, source URL).
- No answer is returned without grounded evidence.

### 2. Trust and Safety
- Refuse-on-low-confidence rather than hallucinate.
- Faithfulness guard validates every answer against retrieved evidence before responding.

### 3. Controlled Orchestration
- LangGraph state graph with explicit nodes, conditional edges, retries, and guardrails — not free-form tool selection.

### 4. Type Safety
- Comprehensive type hints and Pydantic models for validation at all boundaries.

### 5. Async-First
- All database and network operations async, with connection pooling and concurrent retrieval.

### 6. Modularity
- Clear separation between ingestion, retrieval, orchestration, and API layers with dependency injection.

### 7. Testing
- Unit tests per component, integration tests for workflows, and nightly gold-set regression.

## Key Features

### 1. Hybrid Search
- Dense vector search (PostgreSQL + pgvector) + BM25 keyword search (OpenSearch).
- Reciprocal Rank Fusion followed by BGE-Reranker cross-encoder for top-k precision.
- Metadata filters by FDA center, topic, date, and status.

### 2. Citation Engine
- Evidence Cards bind each claim to source document, section, exact passage, version, confidence, and FDA source link.

## Evidence Card Schema

Each answer citation must resolve to an Evidence Card with these required fields:

| Field | Purpose |
|-------|---------|
| `citation_id` | Stable answer-local citation marker, such as `[1]`. |
| `document_id` | Stable internal FDA document identifier. |
| `title` | FDA guidance title. |
| `section_id` | Normalized section identifier when available. |
| `section_title` | Human-readable section heading. |
| `page_number` | PDF page number for source inspection. |
| `passage` | Exact quoted or cited source passage. |
| `source_url` | FDA source URL. |
| `version_hash` | SHA-256 hash of the source document version. |
| `document_status` | Draft, Final, or Withdrawn. |
| `retrieval_score` | Dense/BM25/RRF retrieval score used for ranking. |
| `rerank_score` | Cross-encoder reranker score. |
| `confidence` | Final evidence confidence used by guardrails. |
| `retrieved_at` | Timestamp of retrieval for auditability. |

Citation binding fails closed: if the system cannot bind a generated claim to one or more Evidence Cards, the answer is retried or refused.

### 3. Guidance Q&A (RAG)
- Natural-language questions answered with grounded, citation-backed responses.
- Confidence check and faithfulness guard with bounded retry.

### 4. Document Management
- Parent-child chunking preserving FDA document structure.
- Full document retrieval, section navigation, and highlighted passages.
- Draft vs Final status tracking.

### 5. Update Monitoring
- Daily FDA ingestion with version tracking (SHA-256) and alerts for new, updated, or withdrawn guidance.

### 6. Export & Reporting
- Download summaries (Word / PDF) and chat transcripts for submissions and internal reviews.

### 7. API Capabilities
- Streaming responses (SSE), session management, and tool-usage transparency.

## FDA Ingestion Lifecycle

Two-tier, catalog-first. Discovery uses the FDA guidance **static JSON catalog**
(`https://www.fda.gov/files/api/datatables/static/search-for-guidance.json`); the seed-list HTML
crawl is dropped (HTML parsing is retained only as the Tier-2 landing-page PDF fallback).

**Tier 1 — Catalog Sync (metadata registry, daily):**
1. Fetch the static JSON catalog and snapshot the raw response (date-stamped) to the local artifact store.
2. Normalize HTML-escaped rows: title/slug, status, center, communication type, topics,
   regulated product, docket, issue date, comment window, and the `changed` timestamp.
3. Upsert the PostgreSQL `guidance_registry` keyed by `slug` (`docket_id` secondary).
4. Diff against the previous sync to emit NEW / UPDATED / WITHDRAWN change events
   (new slug, newer `changed`/status flip, or a prior slug now absent → withdrawn soft-delete).

**Tier 2 — Content Ingestion (incremental, NEW/UPDATED only):**
5. Resolve the PDF URL (feed link first, landing-page fallback, else landing-page HTML body).
6. Download and preserve the raw PDF/HTML in the local artifact store; compute a SHA-256 content hash,
   record artifact metadata in PostgreSQL, and create a version snapshot (skip re-parse when the hash is unchanged).
7. Detect status transitions such as Draft → Final or Active → Withdrawn.
8. Parse text, sections, tables, and page-level offsets with PyMuPDF + Unstructured.
9. Create parent-child chunks that preserve section hierarchy and page references.
10. Embed child chunks with BGE-M3.
11. Index dense vectors in PostgreSQL (pgvector) and BM25 text in OpenSearch with evidence-card payloads.
12. Re-index only changed documents and generate a daily update report.

## Implementation Strategy

### Phase 1: Foundation
1. Set up project structure and Docker Compose (PostgreSQL + pgvector, OpenSearch, FastAPI).
2. Configure metadata store (PostgreSQL) and local filesystem artifact storage.
3. Implement retrieval clients and base Pydantic models.

### Phase 2: Ingestion (Two-Tier, Catalog-First)
1. Tier 1: fetch the FDA static JSON catalog, normalize, and maintain a PostgreSQL
   `guidance_registry` with NEW/UPDATED/WITHDRAWN change detection.
2. Tier 2: resolve + download PDFs, version-track (SHA-256), and parse with PyMuPDF + Unstructured.
3. Implement parent-child chunking and BGE-M3 embeddings.
4. Index vectors in PostgreSQL (pgvector) and BM25 content in OpenSearch; schedule with APScheduler.

### Phase 3: Retrieval & Reranking
1. Implement dense and keyword search.
2. Add Reciprocal Rank Fusion.
3. Add BGE-Reranker cross-encoder stage.

### Phase 4: Agent Workflow
1. Build the LangGraph state graph and nodes.
2. Implement citation binding and Evidence Cards.
3. Implement confidence check and faithfulness guard with retry.

### Phase 5: API & Frontend
1. Set up FastAPI streaming endpoints.
2. Build Next.js chat, search, and document viewer.
3. Add authentication and export/reporting.
4. Add summary, export, and alert endpoints.

### Phase 6: Evaluation & Observability
1. Integrate Langfuse tracing.
2. Build FDA gold set and RAGAS + HHEM evaluation.
3. Add nightly quality regression.

### Phase 7: MVP Release Hardening
1. Run FDA gold-set evaluation and fix retrieval/citation failures.
2. Add backup, health-check, and deployment runbooks.
3. Pilot with a controlled FDA guidance corpus.

## Release Quality Gates

The MVP is not release-ready until these checks pass:

| Gate | Target |
|------|--------|
| Citation coverage | 100% of generated answers include at least one Evidence Card. |
| Citation validity | 100% of citations resolve to source document, section/page, passage, version hash, and URL. |
| Retrieval recall@10 | ≥ 90% on FDA gold set. |
| Grounded accuracy | ≥ 95% on curated FDA Q&A. |
| Hallucination rate | ≤ 5% by HHEM / faithfulness evaluation. |
| Refusal behavior | Low-evidence queries refuse or ask for clarification. |
| Latency | < 5 seconds for standard Q&A on pilot corpus. |
| Freshness | Daily ingestion detects new, updated, and withdrawn guidance. |

## Configuration

### Environment Variables
```bash
# Vector (pgvector) & Keyword Search
# Dense vectors live in PostgreSQL via pgvector (see DATABASE_URL below).
PGVECTOR_TABLE=guidance_chunks
EMBEDDING_DIM=1024
OPENSEARCH_URL=http://localhost:9200

# LLM Configuration
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
LLM_CHOICE=gpt-4.1
ONPREM_LLM_BASE_URL=http://localhost:8000/v1   # vLLM fallback

# Embeddings & Reranking
EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=BAAI/bge-reranker-large

# Metadata, Artifact Storage & Auth
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/fda_copilot
OBJECT_STORE_BACKEND=local
OBJECT_STORE_BASE_PATH=data/object_store
SUPABASE_URL=...
SUPABASE_KEY=...

# Observability
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...

# Application
APP_ENV=development
LOG_LEVEL=INFO
APP_PORT=8000
```

### Data Stores
- **PostgreSQL + pgvector (single MVP database)**: Guidance catalog registry (`guidance_registry`, Phase 2),
   source artifact metadata, document metadata, dense vector index of child chunks, users, sessions, and audit trail
  (users/sessions/audit come online in the API/auth phase).
- **OpenSearch**: BM25 keyword index with metadata.
- **Local filesystem artifact store**: Immutable raw JSON catalog snapshots, original FDA PDFs/HTML,
   generated reports, and versioned source artifacts under `data/object_store`.

### Artifact Storage Strategy
- MVP default: local filesystem artifact store + PostgreSQL artifact metadata.
- Store only relative artifact keys in application records, such as
   `catalog/search-for-guidance/2026-07-20T120000Z.json` or `raw/{slug}/{sha256}.pdf`.
- PostgreSQL tracks artifact metadata (`storage_backend`, `object_key`, `content_type`, `sha256`,
   `size_bytes`, source URL, document slug, version hash, and timestamps) for auditability.
- S3/MinIO/Azure Blob can be added later as optional storage adapters behind the same application
   storage interface, but they are not required for the MVP.

## Deployment Plan

- MVP deploys with Docker Compose on a single VM for pilot customers.
- Services: API, web app, PostgreSQL (pgvector), OpenSearch, local artifact volume, and Langfuse.
- Persistent volumes are required for PostgreSQL, OpenSearch, the local artifact directory, and Langfuse.
- Health checks cover API readiness, retrieval stores, ingestion scheduler, and background workers.
- Backups cover PostgreSQL metadata + vectors, local artifact source files, and OpenSearch indexes.
- Separate development, staging, and pilot environments use distinct `.env` files and data volumes.

## Security Considerations
- Environment-based configuration with no hardcoded credentials.
- Input validation at all layers (Pydantic).
- Injection prevention on retrieval and metadata queries.
- Authentication and role-based access via Supabase for MVP.
- Rate limiting on API endpoints.
- Audit trail for all queries and answers.

## Performance Optimizations
- Connection pooling for all data stores.
- Embedding and reranking batching during ingestion.
- Indexed vector and keyword searches with metadata pre-filtering.
- Async operations throughout the retrieval and API layers.
- Caching of parsed documents and embeddings.

## Monitoring & Logging
- Structured logging with request context.
- Langfuse tracing across LangGraph spans, prompts, and outputs.
- RAGAS + Vectara HHEM faithfulness and hallucination metrics.
- Nightly evaluation regression against the FDA gold set.
- Usage analytics and error tracking.

## V1 Knowledge Graph Extension

V1 adds Graphiti with Neo4j only after the MVP hybrid RAG core is trusted in pilot usage. Graphiti is a retrieval enhancement, not a replacement for the PostgreSQL/pgvector + OpenSearch hybrid retrieval.

### V1 Architecture Additions
- **Neo4j**: Temporal graph database.
- **Graphiti**: Temporal knowledge graph framework.
- **`/src/graph/graphiti_client.py`**: Wraps graphiti-core.
- **`/src/graph/ontology.py`**: FDA entity and relationship types.
- **`/src/graph/episode_builder.py`**: Converts each FDA document into a Graphiti episode.
- **`/src/graph/graph_search.py`**: Search, related-entity, and timeline queries.
- **`graph_retrieve` LangGraph node**: Invoked only for cross-guidance, temporal, entity-centric, or relationship-based queries.

### V1 Environment Variables
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### V1 FDA Ontology
- **Entity types**: `Guidance`, `Docket`, `CFRReference`, `ProductCode`, `Center`, `TopicArea`.
- **Relationship types**: `SUPERSEDES`, `CITES`, `APPLIES_TO`, `REVISED_FROM`.

### V1 Capabilities
- Cross-guidance comparison.
- Draft vs final diff visualization.
- Document-evolution timelines.
- Entity-centric reasoning over CFR references, centers, dockets, product codes, and topic areas.

## Success Metrics
- Time to answer: < 5 seconds
- Grounded accuracy: ≥ 95%
- Hallucination rate: ≤ 5%
- Retrieval recall@10: ≥ 90%
- Weekly active adoption: ≥ 60%
- Pilot NPS: ≥ 40

## Future Enhancements
- Cross-guidance comparison and draft vs final diff visualization (V1).
- Document-evolution timelines and entity-centric reasoning (V1).
- On-prem model serving and multi-tenancy (V2).
- Fine-tuned embeddings, DSPy prompt optimization, and multi-hop agent workflows (V3).
- Multi-regulator expansion (EMA, PMDA) and regulatory trend analytics.

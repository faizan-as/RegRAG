# FDA Regulatory Intelligence Platform

Citation-first, AI-powered platform for querying FDA guidance documents with verifiable,
citation-backed answers. See [PLANNING.md](PLANNING.md) for architecture and [TASK.md](TASK.md)
for the implementation roadmap.

> **Non-negotiable principle:** every answer ships with a verifiable FDA citation.

## MVP Stack

- **Orchestration:** LangGraph
- **Retrieval:** PostgreSQL + pgvector (dense) + OpenSearch (BM25) + RRF + BGE-Reranker-Large
- **Embeddings:** BGE-M3
- **LLM:** Azure OpenAI (Claude / vLLM fallback)
- **API:** FastAPI + Pydantic v2 + SSE
- **Frontend:** Next.js 15 + shadcn/ui
- **Metadata + Vectors:** PostgreSQL (pgvector) · **Artifacts:** local filesystem · **Auth:** Supabase
- **Observability:** Langfuse · **Evaluation:** RAGAS + Vectara HHEM

## Repository Layout

```text
apps/api/        FastAPI application (routes, schemas, deps, settings)
apps/web/        Next.js 15 authenticated regulatory research frontend
src/agents/      LangGraph workflow (state, nodes, edges, guardrails)
src/ingestion/   FDA scraping, parsing, chunking, embeddings
src/retrieval/   pgvector, OpenSearch, RRF, reranker
src/llm/         Provider router, prompts, streaming
src/reports/     Summaries and exports
src/monitoring/  Update alerts and diffs
src/eval/        Gold set and evaluation
src/common/      Logging, telemetry, errors
src/db/          SQLAlchemy models for registry, artifacts, and pgvector chunks
infra/docker/    Service configuration
data/object_store/ Local raw FDA PDFs, HTML, catalog snapshots, and reports
tests/           Unit and integration tests
```

## Local Development

### Operational Local Demo

The local demo profile keeps PostgreSQL, pgvector, OpenSearch, LangGraph, citation binding,
Supabase RBAC, and audit persistence active. It replaces only cloud LLM and large BGE model
downloads with deterministic development adapters. Never enable it in staging or pilot.

1. Configure `.env` with a database port that matches Docker and both frontend origins:

   ```text
   APP_ENV=development
   LOCAL_DEMO_MODE=true
   POSTGRES_PORT=55432
   DATABASE_URL=postgresql+asyncpg://fda:fda@localhost:55432/fda_copilot
   CORS_ALLOWED_ORIGINS=http://localhost:3100,http://127.0.0.1:3100
   ```

2. Start infrastructure, migrate the application database, and start local Supabase:

   ```powershell
   docker compose up -d --wait
   python -m alembic upgrade head
   npx --yes supabase@latest start
   ```

3. Seed one preserved, parsed, and dual-indexed FDA guidance PDF from the included catalog sample:

   ```powershell
   python -m src.ingestion.local_seed --catalog-path "Docs/search-for-guidance-sample.json" --limit 1
   ```

   The command is idempotent by document version hash and is available only when
   `LOCAL_DEMO_MODE=true`.

4. Start the API and frontend in separate terminals:

   ```powershell
   python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
   ```

   ```powershell
   Set-Location apps/web
   npm install
   npm run dev -- --hostname 127.0.0.1 --port 3100
   ```

5. Create a local user as described below, then open `http://127.0.0.1:3100/login`.
   API liveness and readiness are available at `http://127.0.0.1:8000/health` and
   `http://127.0.0.1:8000/ready`.

To run the credentialed browser suite:

```powershell
Set-Location apps/web
$env:E2E_USER_EMAIL = "admin@regrag.local"
$env:E2E_USER_PASSWORD = "your-local-password"
npm run test:e2e
```

Production and shared environments should leave `LOCAL_DEMO_MODE=false` and configure Azure
OpenAI, BGE-M3, and BGE-Reranker-Large as described in `.env.example`.

### Standard Development Setup

1. Copy the environment template:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Create a virtual environment and install dependencies:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```

3. Start infrastructure services:

   ```powershell
   docker compose up -d
   ```

4. Apply database migrations:

   ```powershell
   python -m alembic upgrade head
   ```

5. Run tests:

   ```powershell
   python -m pytest
   ```

6. Run the API:

   ```powershell
   uvicorn apps.api.main:app --reload --port 8000
   ```

7. Start local Supabase Auth:

   ```powershell
   npx --yes supabase@latest start
   ```

   Supabase Studio is available at `http://127.0.0.1:54323`. Run
   `npx --yes supabase@latest status` to obtain the local API URL and publishable key.

8. Configure and run the frontend:

   ```powershell
   Copy-Item apps/web/.env.example apps/web/.env.local
   Set-Location apps/web
   npm install
   npm run dev -- --port 3100
   ```

   Set the Supabase API URL and publishable key in `apps/web/.env.local`. The frontend runs at
   `http://localhost:3100` and calls the API through `NEXT_PUBLIC_API_BASE_URL`.

### Create Local Login Users

1. Start Supabase and open Studio:

   ```powershell
   npx --yes supabase@latest start
   ```

   Open `http://127.0.0.1:54323`, select **Authentication > Users**, and choose **Add user**.

2. Enter the user's email and a development password. Enable automatic email confirmation so the
   account can sign in immediately without using the local email inbox.

3. Assign the application role in **SQL Editor**. The application reads trusted roles from the
   `app_metadata.roles` JWT claim, which Supabase stores in `auth.users.raw_app_meta_data`.

   Create a researcher:

   ```sql
   UPDATE auth.users
   SET raw_app_meta_data = COALESCE(raw_app_meta_data, '{}'::jsonb)
       || '{"roles":["researcher"]}'::jsonb
   WHERE email = 'researcher@regrag.local';
   ```

   Create an administrator with access to audit and alert-management workflows:

   ```sql
   UPDATE auth.users
   SET raw_app_meta_data = COALESCE(raw_app_meta_data, '{}'::jsonb)
       || '{"roles":["admin","researcher"]}'::jsonb
   WHERE email = 'admin@regrag.local';
   ```

   Replace the example email with the address created in Studio. Do not put authorization roles in
   `raw_user_meta_data`; users can modify that metadata themselves. A user without an explicit
   application role is treated as a researcher.

4. If the user was already signed in when the role changed, sign out and sign in again so Supabase
   issues a new access token containing the updated role claim.

5. Open `http://localhost:3100/login` and sign in with the created email and password. An admin
   account should show the audit navigation and alert-management controls.

Local users persist across `supabase stop` and `supabase start`. Running
`npx --yes supabase@latest db reset` recreates the local database and removes users, so create them
again after a reset.

## Local Configuration

The default local database connection is:

```text
postgresql+asyncpg://fda:fda@localhost:5432/fda_copilot
```

The MVP uses one PostgreSQL database for relational metadata and dense vectors:

- `guidance_registry` - FDA catalog metadata keyed by slug.
- `source_artifacts` - metadata for preserved raw artifacts.
- `guidance_chunks` - child chunks, BGE-M3 embeddings, and Evidence Card payload metadata.

Raw FDA source files and reports are stored on the local filesystem by default:

```text
OBJECT_STORE_BACKEND=local
OBJECT_STORE_BASE_PATH=data/object_store
```

MinIO/S3 is not required for the MVP local stack.

## Services (docker compose)

| Service    | Port | Purpose                                             |
|------------|------|-----------------------------------------------------|
| PostgreSQL | 5432 | Single MVP DB: registry, artifacts, audit, pgvector |
| OpenSearch | 9200 | BM25 keyword search                                 |
| Langfuse   | 3000 | Tracing / observability                             |

If port `5432` is already in use, set a different host port and keep
`DATABASE_URL` aligned with it before starting PostgreSQL:

```powershell
$env:POSTGRES_PORT = "55432"
$env:DATABASE_URL = "postgresql+asyncpg://fda:fda@localhost:55432/fda_copilot"
docker compose up -d --wait postgres
```

Useful Docker commands:

```powershell
docker compose ps
docker compose ps postgres
docker compose logs -f postgres
docker compose up -d postgres opensearch langfuse
docker compose down
```

## Verify Local PostgreSQL + pgvector

Connect with `psql` inside the Docker container:

```powershell
docker compose exec postgres psql -U fda -d fda_copilot
```

Inside `psql`, verify the database, extension, and migration version:

```sql
SELECT current_database(), current_user;
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
SELECT version_num FROM alembic_version;
```

Expected migration version after the current Phase 2 work:

```text
20260720_0004
```

Verify the dense vector table and indexes:

```sql
\d guidance_chunks

SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'guidance_chunks'
ORDER BY indexname;
```

The vector index should include:

```text
USING hnsw (embedding vector_cosine_ops)
```

Optional smoke test for a 1024-dimensional vector row:

```sql
INSERT INTO guidance_chunks (
  chunk_id,
  document_slug,
  version_hash,
  chunk_type,
  text,
  embedding,
  embedding_model,
  evidence_payload
)
VALUES (
  'local-test:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:0',
  NULL,
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'child',
  'Local pgvector smoke test.',
  ('[' || array_to_string(array_fill(0.001::float8, ARRAY[1024]), ',') || ']')::vector,
  'BAAI/bge-m3',
  '{"source":"local smoke test"}'::jsonb
);

SELECT
  chunk_id,
  text,
  embedding <=> ('[' || array_to_string(array_fill(0.001::float8, ARRAY[1024]), ',') || ']')::vector AS cosine_distance
FROM guidance_chunks
ORDER BY embedding <=> ('[' || array_to_string(array_fill(0.001::float8, ARRAY[1024]), ',') || ']')::vector
LIMIT 5;

DELETE FROM guidance_chunks
WHERE chunk_id = 'local-test:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:0';
```

For GUI tools such as DBeaver or pgAdmin, use:

```text
Host: localhost
Port: 5432
Database: fda_copilot
User: fda
Password: fda
```

## Ingestion Pipeline Status

Phase 2 implementation includes:

- FDA static JSON catalog normalization and registry backfill.
- Raw PDF/HTML acquisition into local artifact storage.
- SHA-256 version tracking and lifecycle transition detection.
- PyMuPDF text/section/page-offset parsing.
- Unstructured table extraction support.
- Parent-child chunking with section, page, and character offsets.
- BGE-M3 embedding generation with batching and progress callbacks.
- Dense pgvector upsert with Evidence Card payload metadata.
- OpenSearch BM25 indexing with metadata.
- Reindex-only-changed cleanup and withdrawn-document removal.
- Daily update reports and ingestion orchestration.

## Retrieval Status

Phase 3 retrieval implementation includes:

- Query embedding helper for BGE-M3-compatible dense search.
- Internal retrieval candidate model for carrying Evidence Card payloads across retrieval stages.
- Shared metadata filters for PostgreSQL and OpenSearch.
- PostgreSQL + pgvector dense search over `guidance_chunks`.
- OpenSearch BM25 keyword search over the configured guidance index.
- Reciprocal Rank Fusion for dense + sparse candidates.
- BGE-Reranker-Large wrapper with injectable test doubles.
- Evidence Card and SearchResult formatting.
- Unified hybrid retrieval client with dense-only or keyword-only fallback when one store is unavailable.

Run focused retrieval tests:

```powershell
python -m pytest tests/retrieval
```

## Agent Workflow Status

Phase 4 implementation includes:

- Typed LangGraph state for query understanding, retrieval, evidence, confidence, retries, refusals, and final answers.
- Azure OpenAI-first LLM routing with Anthropic and vLLM-compatible fallback wrappers.
- Citation-first prompt templates and provider-neutral streaming event helpers.
- Fail-closed citation binding against pre-assigned Evidence Card ids.
- Confidence, refusal, compliance-boundary, retry, and faithfulness guardrails.
- The controlled MVP graph nodes: query understanding, retrieval routing, hybrid retrieval, merge/rerank normalization, confidence check, answer generation, citation binding, faithfulness guard, and response.

Run focused Phase 4 tests:

```powershell
python -m pytest tests/llm tests/agents
```

Run the full regression suite:

```powershell
python -m pytest
```

Gold-set retrieval tuning remains pending until the evaluation corpus is curated.

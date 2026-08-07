# Plan: Phase 5 - API Backend

## Goal

Implement the backend API surface for the MVP: FastAPI route groups, dependency injection, SSE chat delivery, search and document access, grounded summaries and exports, update-monitoring APIs, Supabase-backed authorization, rate limiting, audit persistence, and API tests.

This phase intentionally excludes the Next.js frontend. Frontend implementation should be planned separately after the backend contracts are stable.

Build thin FastAPI routes over the Phase 2 ingestion, Phase 3 retrieval, and Phase 4 LangGraph workflow layers. Before adding routes, close the prerequisite contract gaps identified below: server-owned sessions and turns, structured retrieval outcomes, shared heavyweight model lifecycle, grounded summary/change semantics, and database-enforced alert idempotency. Routes validate requests, authorize the caller, call an injected domain service, persist required audit records, and return typed Pydantic responses with Evidence Cards and sanitized execution transparency.

## Scope

### In Scope

- FastAPI application structure, middleware, lifespan, dependency injection, and route registration.
- API route groups for `chat`, `search`, `documents`, `summaries`, `exports`, `alerts`, and `health`.
- SSE chat endpoint that exposes the node-boundary streaming semantics Phase 4 currently supports and never commits unvalidated answers.
- Request and response schemas for chat, search, document navigation, summaries, exports, alerts, auth context, errors, and transparency metadata.
- Supabase JWT authentication and role-based authorization hooks for MVP API access.
- Rate limiting for user-facing routes.
- Server-owned chat sessions and immutable turn snapshots for authorization, audit correlation, and transcript export.
- Audit persistence for queries, answers, Evidence Cards, refusals, retrieval diagnostics, and export actions.
- Summary, key-requirement, key-change, transcript-export, and report-export backend services.
- Update-monitoring backend services for alert records and version diffs.
- Health and readiness checks for the API, PostgreSQL, OpenSearch, artifact storage, LLM configuration, and scheduler state where available.
- Unit and integration tests with mocked LLM, PostgreSQL/pgvector, OpenSearch, Supabase, Langfuse, and artifact storage.

### Out of Scope

- Next.js 15 app setup, shadcn/ui, browser-side streaming chat, document viewer UI, and frontend auth screens.
- Graphiti, Neo4j, entity timelines, graph ingestion, or graph retrieval.
- Gold-set evaluation, RAGAS/HHEM calibration, nightly quality regression, and release quality gates beyond API test coverage.
- Production cloud deployment automation.
- Legal or compliance decision workflows.
- Token-by-token chat streaming. It requires a separate Phase 4 change to wire `LLMClient.stream` into guarded generation and is not part of the Phase 5 MVP contract.

## Current Implementation Baseline

Already present:

- `apps/api/main.py` creates the FastAPI app, configures logging in lifespan, and exposes basic `/health` liveness.
- `apps/api/deps.py`, `errors.py`, `security.py`, and `ratelimit.py` provide initial dependency, structured-error, Supabase JWT, RBAC, and single-process rate-limit implementations. They are not yet registered by `main.py` and require the corrections in Phase 5.1/5.2.
- `apps/api/settings.py` includes CORS, Supabase JWT secret/audience, auth bypass, and rate-limit settings.
- `apps/api/schemas` contains initial chat, search, document, summary, export, alert, health, error, audit, Evidence Card, and transparency schemas.
- `src/agents/graph.py::run_agent` is the Phase 4 handoff for non-streaming chat. `run_agent_stream` yields state at node boundaries only.
- `src/retrieval/client.py::hybrid_search` is the Phase 3 handoff for search, but it must distinguish empty results from dependency failures and stop carrying raw exception text into public diagnostics.
- `src/reports/{summarizer,templates,exporter}.py` and `src/monitoring/{alerts,diffs,scheduler}.py` contain initial implementations that require focused correctness work and tests.
- `AuditEventRecord`, `AlertRecordORM`, and `ExportRecordORM` plus migration `20260730_0005_create_audit_export_alert_tables.py` already exist.
- `pyjwt`, `python-docx`, and `reportlab` are already declared in `pyproject.toml`.

Still missing:

- Registered API routers, CORS/request-id middleware, exception-handler registration, and `/ready`.
- Server-owned chat session and turn persistence.
- Shared lifespan ownership for the LLM client, BGE-M3 embedder, BGE reranker, and compiled LangGraph.
- Route-level service adapters, export metadata/download handling, and API/report/monitoring tests.
- Database-enforced alert idempotency and explicit audit failure semantics.

## Contract Constraints

- Every non-refusal chat answer returned by the API must include at least one valid Evidence Card.
- Citation binding and faithfulness validation remain owned by Phase 4. API routes must not bypass `run_agent` for answer generation.
- Phase 5 SSE events are `started`, `node`, `committed`, `refused`, `error`, and `done`. There is no `token` event in the MVP because Phase 4 does not expose token streaming through the graph.
- `node` events contain progress metadata only. Answer text appears only in `committed` after citation and faithfulness guards pass, or in the product-safe refusal payload.
- Search endpoints may call retrieval directly, but answer generation endpoints must go through the LangGraph workflow.
- Known retrieval filters are normalized into `RetrievalFilters`; malformed known filters return `422`. Unknown filter keys are ignored for forward compatibility and listed in `ignored_filter_keys`.
- An empty successful search returns `200` with an empty result list. A search in which all configured backends fail returns a sanitized `503`. Partial backend failure returns `200` with sanitized fallback diagnostics.
- Session ids and turn ids are generated by the server. A supplied session id must resolve to a persisted session owned by the authenticated user; string prefixing is not ownership validation.
- Transcript and summary exports resolve content from persisted server-owned records. Export requests must not accept client-supplied `Answer`, Evidence Card, or `SummaryResult` payloads as authoritative content.
- API responses must not expose secrets, raw provider stack traces, database connection details, or raw Supabase keys.
- Transparency diagnostics expose stable codes and safe messages, never `str(exc)` from providers or data stores.
- Refusal is a valid product response and must be audited with the refusal reason and supporting confidence metadata.
- Critical audit events are persisted transactionally with the durable turn, export, or alert mutation. Best-effort operational events may fail without failing the product response, but failures must be logged and metered.
- This backend supports regulatory research. It must not return final legal/compliance determinations such as "you are compliant" or "FDA will approve".

## Resolved Design Decisions

- Use `POST /api/chat/stream` with `fetch` plus `ReadableStream`; native `EventSource` cannot attach the bearer header.
- Use node-boundary SSE for the MVP. Token streaming is deferred until Phase 4 can stream through generation and guardrails without changing the authoritative-final contract.
- Use persisted UUID chat sessions and immutable turn snapshots. Do not namespace arbitrary client strings as a substitute for ownership checks.
- Use a single-worker in-memory rate limiter for the local/pilot MVP. Multi-worker deployment is blocked until a shared limiter is introduced.
- Prefer Supabase JWKS-backed asymmetric verification. Permit HS256 only when explicitly configured for a legacy/local Supabase project; pin algorithms and validate issuer, audience, expiry, not-before, and subject claims.
- Read application roles only from the configured application-role claim (default `app_metadata.roles`). Map a valid Supabase `authenticated` token with no application roles to baseline `researcher`; do not treat Supabase platform roles as application RBAC roles.
- Load the BGE-M3 embedder and BGE reranker once during lifespan, reuse provider HTTP clients, and compile the LangGraph once against factories for request-scoped database resources.
- Generate document summaries with bounded, section-aware evidence selection and synthesis. Do not load an unbounded document into one prompt or assign synthetic retrieval/rerank scores.
- Enforce alert idempotency with a database unique event fingerprint, not only a read-before-insert check.

## Implementation Steps

### Phase 5.0 - Prerequisites and Public Contracts

Complete these prerequisites before route implementation:

- Add `ChatSessionRecord` with server-generated UUID, owner user id, timestamps, and optional title/status.
- Add immutable `ChatTurnRecord` rows containing the session id, request id, query, final answer/refusal, Evidence Card snapshot, confidence/guardrail metadata, and timestamps. A turn is written only after a final answer or refusal is selected.
- Add `GroundedSummaryRecord` containing owner user id, document/version identifiers, summary type, final text/refusal, Evidence Card snapshot, comparison metadata, guardrail outcomes, and timestamps so exports resolve a durable server result.
- Add migration `20260805_0006_add_api_sessions_summaries_alert_fingerprint.py` following the existing revision convention.
- Add a deterministic `event_fingerprint` to alerts and a database unique constraint. Compute it from the change type, document slug, relevant version/status values, and source change timestamp so retries and concurrent schedulers converge on one record.
- Refactor `hybrid_search` to return structured backend outcomes (`success`, `empty`, `failed`) independently from candidate count. Preserve partial fallback behavior while distinguishing a valid empty search from total dependency failure.
- Replace raw retrieval exception strings with internal logs plus stable public diagnostic codes such as `dense_unavailable`, `keyword_unavailable`, and `reranker_unavailable`.
- Add document-scoped evidence selection support, including a document id/slug filter, so summaries can use actual selection and rerank scores rather than synthetic `1.0` values.

Confirm the public route contract:

- `POST /api/sessions` creates a server-owned chat session.
- `GET /api/sessions/{session_id}/turns` returns authorized session history.
- `POST /api/chat` returns a non-streaming final answer/refusal and the server session/turn ids.
- `POST /api/chat/stream` emits node-boundary SSE through `fetch` plus `ReadableStream` with bearer authentication.
- `POST /api/search` performs hybrid retrieval with typed filters.
- `GET /api/documents/{document_id}` returns document metadata and versions.
- `GET /api/documents/{document_id}/sections` returns section navigation.
- `GET /api/documents/{document_id}/passages/{chunk_id}` resolves a cited passage.
- `GET /api/documents/{document_id}/artifacts/{artifact_id}/download` streams an authorized preserved PDF/HTML artifact through the storage adapter.
- `POST /api/summaries` creates a grounded summary, key-requirement result, or version comparison.
- `POST /api/exports` accepts an export kind plus a server-owned `summary_id` or `session_id`; it does not accept authoritative answer/summary bodies from the client.
- `GET /api/exports/{export_id}` returns authorized export metadata.
- `GET /api/exports/{export_id}/download` streams authorized artifact bytes through the storage adapter.
- `GET /api/alerts` lists alerts for authorized users; `PATCH /api/alerts/{alert_id}` is admin/service only.
- `GET /health` is dependency-free liveness; `GET /ready` is timeout-bounded dependency readiness.

Refine Pydantic schemas under `apps/api/schemas`:

- Add session-create, session-history, and turn-summary models.
- Keep top-level request schemas `extra="forbid"`.
- Normalize the filter dictionary against the known `RetrievalFilters` fields; report unknown keys and reject malformed known values.
- Remove client-supplied `summary` and `answers` fields from `ExportRequest`; replace them with server-owned source identifiers.
- Add structured retrieval backend status/diagnostic models with safe codes, not provider exception text.
- Add summary version-comparison metadata containing previous/current hashes and evidence from both versions.
- Keep public field descriptions and the Evidence Card contract aligned with `PLANNING.md`.

### Phase 5.1 - FastAPI App Structure

Complete and register the existing API scaffold:

- Refine `apps/api/deps.py`, `errors.py`, `security.py`, and `ratelimit.py`; do not recreate them.
- Add `apps/api/routes/` with one router module per route group.

Update `apps/api/main.py` to:

- Register route modules under an `/api` prefix except health endpoints.
- Configure CORS from settings.
- Register exception handlers.
- Install request-id middleware before exception/audit handling.
- Initialize shared resources once in lifespan: provider HTTP/LLM client, BGE-M3 embedding model, BGE reranker, OpenSearch client, artifact store, and compiled LangGraph.
- Load blocking embedding/reranker models off the event loop, record startup failures, and expose their readiness without leaking configuration details.
- Compile the graph once against factories for request-scoped SQLAlchemy sessions; do not compile it or construct provider clients per request.
- Close provider and OpenSearch HTTP resources on shutdown when their client APIs support it.
- Keep liveness cheap and dependency-free.
- Keep readiness dependency-aware and timeout-bounded.

Dependency injection should provide:

- Settings.
- Async SQLAlchemy session.
- OpenSearch client.
- Local artifact storage client.
- Shared LLM, embedding, and reranker clients/models.
- The shared compiled graph or an injected agent service.
- Session, retrieval, document, summary, export, monitoring, and audit services so route tests can replace them with fakes.
- Current authenticated user context.
- Optional Langfuse client/span helper.

### Phase 5.2 - Authentication, Authorization, and Rate Limiting

Harden the existing Supabase JWT validation:

- Add settings for `SUPABASE_JWT_ISSUER`, `SUPABASE_JWKS_URL`, allowed algorithms, and the application-role claim path. Retain `SUPABASE_JWT_SECRET` only for explicitly configured HS256 projects.
- Prefer JWKS verification and cache keys with bounded refresh. Pin the configured algorithm allowlist; never infer algorithms from an unverified token header.
- Validate signature, issuer, audience, expiry, not-before, and subject. Apply a small configurable clock-skew allowance.
- Extract user id and email from validated claims. Read application roles from `app_metadata.roles` by default; do not use the Supabase platform `role` claim as application RBAC.
- Give an otherwise valid `authenticated` user the baseline `researcher` role when no application role is assigned.
- Allow development bypass only when both `APP_ENV=development` and `AUTH_DEV_BYPASS=true`; reject that configuration at startup in staging/pilot.
- Look up every supplied session, summary, export, and artifact identifier and verify ownership/visibility in PostgreSQL. Do not authorize by string prefix.

Define MVP roles:

- `researcher`: own sessions/turns, chat, search, documents, summaries, own exports, and read-only alerts.
- `admin`: all researcher permissions plus alert state changes and audit inspection.
- `service`: scheduler/worker-facing operations if needed.

Complete rate limiting:

- Keep the documented single-process in-memory limiter for the single-worker local/pilot MVP and enforce a startup/deployment check that blocks multiple API workers.
- Define independent configurable budgets for chat, active SSE streams, search, summaries, exports, and document reads so inexpensive reads do not consume the chat budget.
- Key limits by authenticated user id. Health/readiness are not rate-limited and do not use client IP accounting.
- Cancel and release active-stream capacity when an SSE client disconnects.
- Return structured `429` responses without leaking implementation details.

### Phase 5.3 - Chat API and SSE Streaming

Implement chat routes over the shared compiled Phase 4 graph through an injected agent service.

Non-streaming route behavior:

- Validate query, optional server-issued session UUID, and retrieval filters.
- Create a session when none is supplied; otherwise load it and require `owner_user_id == current_user.user_id`.
- Run the agent workflow through injected shared dependencies.
- Persist the immutable final turn and its critical audit event in one transaction. Store the final answer/refusal, Evidence Card snapshot, confidence, citation/faithfulness outcomes, provider identity, and sanitized diagnostics.
- Return session id, turn id, final `Answer`, and transparency metadata.

SSE route behavior:

- Expose `POST /api/chat/stream` (not `GET`) so the bearer token travels in the `Authorization` header via `fetch`, consistent with `Phase 5.2` auth.
- Adapt `run_agent_stream` node-state updates into `started` and `node` progress events. Do not emit generated answer text in progress events.
- Emit the authoritative `committed` event only after citation binding and faithfulness validation pass.
- Emit `refused` when the workflow refuses because evidence is missing, weak, unbound, or unfaithful.
- Persist the turn before emitting `committed` or `refused`; the event includes the durable turn id.
- Emit `done` after the final event. Emit a sanitized `error` followed by `done` for recoverable stream failures.
- On client disconnect, cancel downstream graph work, release stream-rate capacity, and record a best-effort cancellation audit event. Do not persist a partial answer as a completed turn.

Testing focus:

- Valid answer with citations.
- Low-confidence refusal.
- Citation-binding failure routes to refusal after retry budget.
- Streaming committed event is not emitted before guardrails pass.
- No answer text appears in `started` or `node` events.
- A committed/refused event references a durable, user-owned turn.
- Client disconnect/cancellation does not leave unhandled tasks.

### Phase 5.4 - Search API

Implement search routes over `src/retrieval/client.py::hybrid_search`.

Behavior:

- Validate query text, bounded top-k overrides, and known metadata-filter value types.
- Split known and unknown filters, convert known values to `RetrievalFilters`, and return ignored keys in transparency metadata.
- Return `SearchResult` list, Evidence Card-ready metadata, and retrieval diagnostics.
- Return `200` with an empty list when at least one configured retrieval backend completed successfully but found no candidates.
- Return `200` with results and safe fallback codes when one backend or reranking fails but a valid fallback result exists.
- Return a sanitized `503` only when all configured retrieval paths fail.
- Keep raw exceptions in structured server logs associated with request id; expose only safe diagnostic codes and timings.
- Audit search query, filters, result count, and retrieval errors.

Do not generate answers in search routes. Search returns retrieved/reranked evidence only.

Testing focus:

- Filter validation.
- Unknown filter handling.
- Dense-only and BM25-only fallback diagnostics.
- Successful empty-result response is distinct from total backend failure.
- Raw provider/database exception text never appears in the response.

### Phase 5.5 - Document and Passage APIs

Implement document access services using PostgreSQL metadata and local artifacts.

Routes should support:

- Document metadata by canonical registry slug (the public `document_id`).
- Document versions and lifecycle status.
- Section tree/navigation.
- Chunk/passages by chunk id.
- Cited passage lookup from Evidence Card metadata.
- Authorized source artifact download for preserved PDF/HTML by artifact UUID.

Behavior:

- Return metadata needed by future frontend citation navigation: document id, title, status, version hash, section id/title, page, char offsets, source URL, and chunk text.
- Verify the requested chunk/artifact belongs to the path document before returning it.
- Never expose object keys or local filesystem paths as download locations. Resolve artifact UUID to an object key server-side and read through the storage adapter.
- Stream downloads with an allowlisted persisted content type and safe filename.
- Audit document and passage reads when tied to user sessions or exports.

Testing focus:

- Existing document lookup.
- Missing document/chunk handling.
- Withdrawn document visibility rules.
- Cross-document chunk/artifact identifiers are rejected.
- Path-safety checks for artifact access.

### Phase 5.6 - Summary and Export Backend

Refine the existing `src/reports` modules:

- `summarizer.py` for grounded guidance summaries, key requirements, and key changes.
- `templates.py` for report templates and transcript layouts.
- `exporter.py` for Word/PDF/text export generation.

Summary behavior:

- Load the requested document/version and enumerate canonical parent sections with a hard limit on section and token counts.
- Run document-scoped section-aware evidence selection/reranking so included cards carry actual selection and rerank scores. Preserve coverage by selecting evidence per section before final global pruning.
- Generate bounded per-section summaries from selected evidence, citation-bind and faithfulness-check each section, then synthesize only from validated section outputs and their Evidence Cards.
- Run citation binding and faithfulness validation on the final summary. Retry within the configured bound, then refuse or return an explicitly partial result with omitted-section metadata.
- Never assign synthetic retrieval, rerank, or confidence values merely because a chunk is canonical.
- For `key_changes`, require a previous version hash and current version hash that both belong to the same document. Compute the deterministic version diff first, select/rerank changed passages from both versions, and bind each change claim to the relevant before/after Evidence Cards.
- Include previous/current version hashes and comparison status in the result. Refuse when either version is unavailable or no bindable changed evidence exists.

Export behavior:

- Resolve summary exports from a persisted grounded summary result owned by or visible to the caller.
- Resolve transcript exports from persisted turns in a user-owned session, ordered by creation time. Do not trust client-submitted answer/evidence bodies.
- Include answer text, citations, Evidence Cards, confidence metadata, document status, version hashes, retrieval timestamp, and user/session metadata where appropriate.
- Create the pending export row, render the artifact, write through `src/common/storage.py`, and atomically mark the record completed with object key/content metadata. Mark failures with a sanitized code; keep raw errors in logs only.
- Authorize metadata/download access by `requested_by` (or admin role) and stream bytes without returning the internal object key.

API routes:

- `POST /api/summaries` to create summary/key-requirement/key-change outputs.
- `POST /api/exports` to generate an artifact from a server-owned summary or session id.
- `GET /api/exports/{export_id}` to fetch export metadata.
- `GET /api/exports/{export_id}/download` to stream the artifact bytes through `src/common/storage.py`; never return a raw filesystem path.

Testing focus:

- Summary generation with evidence.
- Summary refusal when no evidence exists.
- Key changes reject cross-document/missing versions and bind claims to both version contexts.
- Section batching stays within configured limits and final faithfulness runs.
- Export requests cannot inject answer, summary, or Evidence Card content.
- Transcript export includes citations and refusals.
- Users cannot read or download another user's export/session.
- Export artifact path safety.

### Phase 5.7 - Update Monitoring Backend

Refine the existing `src/monitoring` modules:

- `alerts.py` for alert record creation, listing, acknowledgment, and resolution.
- `diffs.py` for draft-vs-final and version-to-version text/metadata diffs.
- `scheduler.py` for wiring daily checks to alert generation through the existing ingestion orchestration.

Behavior:

- Consume the exact Phase 2 change-event batch produced by a successful catalog sync; do not independently reconstruct changes in a second daily scan.
- Convert new, updated, and withdrawn events into alert records with deterministic event fingerprints.
- Insert alerts with a database upsert/on-conflict strategy against the unique fingerprint so scheduler retries and concurrent workers are idempotent.
- Link alerts to registry rows, source artifacts, version hashes, and daily update reports.
- Generate diff summaries for changed documents without claiming legal/compliance outcomes.
- Enforce explicit lifecycle transitions (`open` to `acknowledged` to `resolved`) and record actor/timestamp for every mutation.
- Expose read-only alert listing to researchers and state updates to admin/service roles.

Testing focus:

- New/updated/withdrawn alert creation.
- Idempotency for repeated and concurrently inserted change events at the database constraint boundary.
- Alert acknowledgment/resolution authorization.
- Invalid/backward alert state transitions are rejected.
- Diff output for draft-to-final and version-to-version changes.

### Phase 5.8 - Audit Persistence and Transparency

Retain the existing indexed `AuditEventRecord`, `AlertRecordORM`, and `ExportRecordORM` models and migration `20260730_0005`. Add session, turn, grounded-summary, and alert-fingerprint changes through the new Phase 5.0 migration rather than editing an applied migration.

Keep `event_type`, `user_id`, `session_id`, `route`, and `created_at` as indexed columns so audit inspection does not scan JSON. Audit records capture:

- Request id, user id, session id, route, timestamp, and request category.
- Query text or export action metadata under an explicit redaction and retention policy; never persist bearer tokens, API keys, connection strings, or raw request headers.
- Normalized filters and ignored filters.
- Sanitized retrieval diagnostic codes and result counts.
- Evidence Card ids and version hashes.
- Confidence values, refusal reasons, citation-binding status, and faithfulness status.
- LLM provider used and fallback trace without secrets.
- Export artifact id and document ids when applicable.

Audit failure semantics:

- Critical domain events (`turn_completed`, `turn_refused`, `summary_completed`, `export_created`, `alert_state_changed`) are written in the same transaction as the corresponding durable record. A transaction failure prevents success from being reported.
- Request-received, validation-failed, authentication-failed, cancellation, readiness, and operational diagnostics are best effort because no durable domain mutation exists. Log and meter persistence failure without exposing it to the caller.
- Refactor `record_audit_event` so callers explicitly select critical transactional behavior or best-effort behavior; do not silently swallow failures for critical events.
- Capture validation/auth failures in middleware or exception handlers after request-id assignment. Do not retain raw authorization headers or unvalidated request bodies.

Transparency payloads returned to API clients should include:

- Node execution trace from Phase 4.
- Sanitized retrieval outcome codes and timings from Phase 3.
- Provider fallback trace.
- Guardrail outcomes.
- Timing metadata where available.

API access:

- Add `GET /api/audit` for admin-only, paginated inspection by event type, user id, session id, route, and time range.
- Return redacted payloads and enforce bounded page sizes.

Testing focus:

- Critical audit and domain rows commit or roll back together.
- Best-effort audit failure does not replace the intended validation/auth/cancellation response.
- No secret fields in persisted or returned diagnostics.
- Admin audit pagination/filtering and researcher denial.
- Transparency payload shape remains stable.

### Phase 5.9 - Health, Readiness, and Error Handling

Split liveness and readiness:

- `/health`: process is alive and settings can load.
- `/ready`: run independent timeout-bounded checks for PostgreSQL, OpenSearch, artifact-store read/write/delete, loaded embedding/reranker resources, configured LLM client, and scheduler state when the scheduler is hosted in this process.
- Do not call the external LLM on every readiness request. Verify validated configuration/client initialization and expose provider call health through metrics/circuit-breaker state.
- Return an aggregate `503` when any required component is unavailable and a typed component-status payload without endpoints, credentials, object paths, or exception text.

Add exception mapping:

- Validation errors: `422` with field details.
- Authentication failure: `401`.
- Authorization failure: `403`.
- Rate limit exceeded: `429`.
- Retrieval unavailable: `503` or route-specific structured error.
- Low confidence/refusal: normal `200` answer payload with `refused=true` for chat/summary flows.
- Missing document/export/alert: `404`.
- Unexpected errors: `500` with sanitized message and request id.

Testing focus:

- Error shapes.
- Request ids are present on success and error responses/events.
- Readiness dependency failures.
- Sanitization of provider/database exceptions.

### Phase 5.10 - Test Plan

Add tests under `tests/api`, `tests/reports`, and `tests/monitoring`.

Unit tests:

- Schema validation and error responses.
- Supabase issuer/audience/signature/time-claim validation, application-role mapping, and development-bypass startup guard.
- Session, summary, export, artifact, and alert ownership/role dependencies.
- Independent rate-limit budgets and SSE concurrency release.
- Route dependency wiring with fakes.
- Structured retrieval outcomes and diagnostic sanitization.
- Bounded summary batching, citation binding, faithfulness, and version comparison.
- Report template/export helpers using server-owned source records.
- Alert fingerprinting, state transitions, and diff helpers.
- Critical versus best-effort audit behavior.

Integration-style tests with fakes:

- Session creation and chat request to a durable citation-bound turn.
- Chat request to a durable low-confidence refusal.
- SSE event order (`started`, `node`*, `committed|refused`, `done`) with no answer text before the final event.
- Search success, partial fallback, successful empty result, and total-failure `503`.
- Document lookup to cited passage response.
- Summary/export flow resolves server records, writes a safe artifact, and commits required audit rows.
- Cross-user session/export/artifact access is denied.
- Repeated/concurrent alert delivery creates one alert and supports an authorized lifecycle flow.
- Lifespan initializes heavyweight models and the graph once across multiple requests.

Test constraints:

- Do not call real Azure OpenAI, Supabase, OpenSearch, or PostgreSQL services in unit tests.
- Use fake agent/retrieval/report services for route tests.
- Use temporary local storage for export/artifact tests.
- Use a disposable PostgreSQL test database for transaction, foreign-key, and unique-fingerprint integration tests; mocks cannot validate these guarantees.
- Keep tests deterministic and credential-free.

## Suggested File Map

```text
apps/api/
  deps.py
  errors.py
  security.py
  ratelimit.py
  audit.py
  main.py
  routes/
    __init__.py
    alerts.py
    audit.py
    chat.py
    documents.py
    exports.py
    health.py
    search.py
    sessions.py
    summaries.py
  schemas/
    alerts.py
    chat.py
    common.py
    errors.py
    exports.py
    health.py
    sessions.py
    summaries.py
    transparency.py

src/reports/
  summarizer.py
  exporter.py
  templates.py

src/monitoring/
  alerts.py
  diffs.py
  scheduler.py

migrations/versions/
  20260730_0005_create_audit_export_alert_tables.py
  20260805_0006_add_api_sessions_summaries_alert_fingerprint.py

tests/api/
  test_audit.py
  test_auth.py
  test_chat.py
  test_documents.py
  test_errors.py
  test_exports.py
  test_health.py
  test_search.py
  test_sessions.py
  test_sse.py

tests/reports/
  test_exporter.py
  test_summarizer.py

tests/monitoring/
  test_alerts.py
  test_diffs.py
```

## Milestones

### Milestone 1 - Correctness and Security Foundation

- Current partial implementation is reconciled with this plan and `TASK.md`.
- Session, turn, grounded-summary, and alert-fingerprint migration is applied.
- Retrieval outcomes and diagnostics distinguish success/empty/failure without raw exceptions.
- Supabase verification, RBAC ownership checks, and independent rate-limit budgets are complete.
- Lifespan owns heavyweight models, clients, and one compiled graph.

### Milestone 2 - API Shell, Search, and Documents

- Route package, middleware, handlers, CORS, `/health`, and `/ready` are registered.
- Search supports typed filters, empty/partial/failure outcomes, and sanitized transparency.
- Document, passage, version, and authorized artifact-download routes are complete.
- Focused route tests pass with injected fakes.

### Milestone 3 - Durable Chat and SSE

- Session routes and ownership checks are complete.
- Non-streaming chat writes durable final answer/refusal turns and critical audit rows.
- SSE emits node progress and only durable committed/refused final events.
- Cancellation and independent stream rate limiting are covered by tests.

### Milestone 4 - Reports, Monitoring, and Hardening

- Section-aware summaries and version comparisons pass citation and faithfulness checks.
- Transcript/summary exports resolve server-owned records and enforce ownership.
- Alert ingestion is database-idempotent and lifecycle-controlled.
- Audit inspection, error sanitization, and readiness checks are hardened.
- API, report, and monitoring tests cover success/refusal/error paths.

## Definition of Done

- All Phase 5 backend routes are registered and covered by focused tests.
- Authentication, ownership checks, and route-specific rate limits are active before protected routes are accepted as complete.
- Heavyweight embedding/reranker models, provider clients, and the compiled graph are initialized once per process and injected into requests.
- Chat and summary generation never return unsupported generated content without Evidence Cards, citation binding, and faithfulness validation.
- Chat sessions, turns, and grounded summaries are server-owned durable records; exports never trust client-supplied answer/evidence content.
- SSE emits progress-only node events and an authoritative durable final event only after guardrails pass or refusal is chosen.
- Search distinguishes valid empty results, partial fallback, and total dependency failure while returning only sanitized diagnostics.
- Search, document, export, and alert APIs return typed, documented payloads.
- Alert retries/concurrency are idempotent through a database unique constraint.
- Critical audit rows commit transactionally with turns, summaries, exports, and alert changes; best-effort event failures are observable.
- Health/readiness endpoints distinguish process liveness from dependency readiness.
- `TASK.md` reflects completed and deferred Phase 5 backend work.
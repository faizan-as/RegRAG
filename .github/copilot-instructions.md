# Copilot Instructions - FDA Regulatory Intelligence Platform

## Project Awareness

- Always read `PLANNING.md` before making architecture, implementation, or task-planning changes.
- Always check `TASK.md` before starting implementation work. If a required task is missing, add it under the most relevant phase or under `Discovered During Work`.
- Keep work aligned with the MVP goal: a citation-first hybrid RAG product for FDA guidance documents with verifiable Evidence Cards, confidence checks, and faithfulness validation.
- Treat Graphiti and Neo4j as V1-only. Do not implement graph retrieval, entity timelines, or graph ingestion in the MVP unless explicitly requested.
- Keep `TASK.md` updated when tasks are completed, changed, split, or discovered.

## MVP Architecture Rules

- Use LangGraph as the primary orchestration layer.
- Use PostgreSQL + pgvector for dense vector retrieval and OpenSearch for BM25 keyword retrieval.
- Use Reciprocal Rank Fusion followed by BGE-Reranker-Large before answer generation.
- Use BGE-M3 for embeddings.
- Use Azure OpenAI as the default LLM provider. Claude Sonnet and vLLM-hosted Llama 3.3 / Qwen are fallback options only.
- Use FastAPI + Pydantic v2 + SSE for the API layer.
- Use Next.js 15 + shadcn/ui for the frontend.
- Use Supabase for MVP authentication and role-based access control.
- Consolidate storage into a single PostgreSQL instance for the MVP: the guidance registry, document metadata, dense embeddings (pgvector), users, sessions, alerts, and audit trail. OpenSearch remains a separate engine for BM25. Do not introduce Qdrant in the MVP; Neo4j is added in V1.

## Citation-First Rules

- Every generated answer must include at least one valid Evidence Card.
- Evidence Cards must include source document, section/page, exact passage, source URL, document status, version hash, retrieval/rerank scores, confidence, and retrieval timestamp.
- Citation binding must fail closed. If a claim cannot be bound to evidence, retry or refuse.
- Prefer refusal or clarification over unsupported generation.
- Do not generate compliance/legal determinations such as "you are compliant" or "this submission will be accepted."

## LangGraph Workflow Rules

- Implement the MVP workflow nodes from `PLANNING.md`: `query_understand`, `retrieval_router`, `hybrid_retrieve`, `merge_rerank`, `confidence_check`, `generate_answer`, `citation_bind`, `faithfulness_guard`, and `respond`.
- Keep node responsibilities small and testable.
- Use typed state models for query, entities, retrieval candidates, evidence, confidence, answer, citations, and retry state.
- Add bounded retry behavior for failed faithfulness checks.
- Record node/tool execution details for API transparency and Langfuse tracing.

## Ingestion Rules

- Preserve raw FDA PDFs and landing-page HTML before parsing.
- Compute SHA-256 version hashes for source documents.
- Track Draft, Final, and Withdrawn statuses.
- Preserve section hierarchy, page references, tables, and source URLs in metadata.
- Use parent-child chunking: section-level parent chunks and paragraph-level child chunks.
- Re-index only changed documents when possible.
- Generate daily update reports for new, updated, and withdrawn guidance.

## Code Structure & Modularity

- Follow the structure in `PLANNING.md`: `apps/api`, `apps/web`, `src/agents`, `src/ingestion`, `src/retrieval`, `src/llm`, `src/reports`, `src/monitoring`, `src/eval`, and `tests`.
- Keep modules focused by responsibility. Split files before they become difficult to review or test.
- Prefer Pydantic models at external boundaries and typed dataclasses or Pydantic models for internal state where useful.
- Use clear, consistent imports and avoid circular dependencies.
- Do not add unrelated refactors while completing a task.

## Python Backend Rules

- For Python, FastAPI, LangGraph, ingestion, retrieval, evaluation, and backend code, follow `.github/instructions/python.instructions.md`.
- Keep this file focused on project-wide architecture, MVP scope, citation-first behavior, task tracking, and compliance boundaries.

## API & Frontend Rules

- API endpoints should use Pydantic v2 request/response schemas.
- Streaming chat should use SSE.
- Expose answer payloads with answer text, citations, Evidence Cards, confidence metadata, and node/tool execution transparency.
- Frontend citation interactions must navigate to the cited document passage or section.
- UI work should prioritize regulatory research workflows: search, chat, document viewer, summaries, exports, and alerts.

## Testing & Quality Gates

- Add or update tests for new features, routes, retrieval logic, guardrails, and ingestion behavior.
- Tests should live in `tests/` and mirror the main application structure.
- Include expected, edge, and failure cases for critical logic.
- Mock external dependencies such as LLMs, PostgreSQL/pgvector, OpenSearch, object storage, and Langfuse in unit tests.
- Preserve MVP release gates from `PLANNING.md`: citation coverage, citation validity, retrieval recall@10, grounded accuracy, hallucination rate, refusal behavior, latency, and freshness.

## Documentation Rules

- Update `PLANNING.md` when architecture, scope, or major component decisions change.
- Update `TASK.md` when work is completed or new tasks are discovered.
- Update setup documentation when dependencies, environment variables, deployment steps, or service requirements change.
- Keep documentation concise and implementation-oriented.

## Safety & Compliance Boundaries

- This product supports regulatory research and intelligence, not final compliance decisions or legal advice.
- Preserve auditability for queries, answers, citations, refusals, and source document versions.
- Do not hardcode secrets or credentials.
- Validate all API inputs and retrieval filters.
- Add rate limiting and RBAC for user-facing endpoints.

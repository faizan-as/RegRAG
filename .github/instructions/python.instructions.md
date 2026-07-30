---
description: "Use when writing or modifying Python, FastAPI, LangGraph, ingestion, retrieval, evaluation, or backend code for the FDA Regulatory Intelligence Platform."
applyTo: "**/*.py"
---
# Python, FastAPI, and LangGraph Standards

## Project Context

- Follow `.github/copilot-instructions.md`, `PLANNING.md`, and `TASK.md` before backend implementation work.
- Keep MVP backend work focused on LangGraph + PostgreSQL/pgvector + OpenSearch + BGE-M3 + BGE-Reranker + Azure OpenAI.
- Do not add Graphiti or Neo4j code to MVP Python modules unless explicitly requested.
- Update `TASK.md` when backend tasks are completed, split, or discovered.

## Python Style

- Use Python 3.11+ features only when they improve readability or typing.
- Use type hints for public functions, class attributes, Pydantic models, and LangGraph state.
- Prefer explicit names over abbreviations.
- Keep functions small and single-purpose.
- Format with `black`; lint with `ruff`; check typing with `mypy` when practical.
- Add concise Google-style docstrings for public modules, classes, and functions.
- Add comments only for non-obvious regulatory, retrieval, citation, or guardrail logic.

## Module Boundaries

- Place FastAPI app code under `apps/api`.
- Place LangGraph orchestration under `src/agents`.
- Place FDA ingestion code under `src/ingestion`.
- Place retrieval clients and fusion/reranking under `src/retrieval`.
- Place LLM routing and prompts under `src/llm`.
- Place summaries and exports under `src/reports`.
- Place update alerts and diffs under `src/monitoring`.
- Place evaluation code under `src/eval`.
- Avoid circular imports. Use dependency injection from `apps/api/deps.py` for shared clients.

## Pydantic Standards

- Use Pydantic v2 for request/response schemas, settings, Evidence Cards, retrieval results, and LangGraph state where appropriate.
- Use `pydantic-settings` for environment configuration.
- Validate all external inputs at API boundaries.
- Use explicit field descriptions for public API schemas.
- Keep Evidence Card fields aligned with `PLANNING.md`.

## FastAPI Standards

- Use `APIRouter` per route group: `chat`, `search`, `documents`, `summaries`, `exports`, `alerts`, and `health`.
- Use async route handlers for I/O-bound work.
- Use dependency injection for LLM clients, PostgreSQL (pgvector), OpenSearch, object storage, and Langfuse.
- Use SSE for streaming chat responses.
- Return structured payloads containing answer text, citations, Evidence Cards, confidence metadata, and node/tool execution details.
- Add clear HTTP errors for validation, retrieval failure, low confidence, and unsupported requests.
- Do not expose secrets or raw provider errors in API responses.

## LangGraph Standards

- Keep each node small, typed, and independently testable.
- MVP nodes are: `query_understand`, `retrieval_router`, `hybrid_retrieve`, `merge_rerank`, `confidence_check`, `generate_answer`, `citation_bind`, `faithfulness_guard`, and `respond`.
- Use conditional edges for confidence/refusal and faithfulness retry paths.
- Use bounded retries. Never create unbounded generation or retrieval loops.
- Persist enough state to trace query understanding, retrieval candidates, reranked evidence, confidence, citations, refusals, and final responses.
- Emit Langfuse spans for important nodes and external provider calls.

## Retrieval Standards

- PostgreSQL + pgvector is the MVP dense vector store (consolidated with the registry, metadata, and audit data in one Postgres instance).
- OpenSearch is the MVP BM25 keyword store.
- Use metadata filters for center, topic, date, status, docket, CFR reference, and product code.
- Combine dense and sparse results with Reciprocal Rank Fusion.
- Rerank final candidates with BGE-Reranker-Large before generation.
- Retrieval result objects must carry source metadata required for Evidence Cards.

## Citation and Guardrail Standards

- Do not return generated answers without Evidence Cards.
- Citation binding must fail closed: retry or refuse if evidence cannot be bound.
- Implement refusal responses for weak, missing, or conflicting evidence.
- Faithfulness validation must run before final response.
- Keep compliance boundaries clear: the system provides regulatory intelligence, not legal or compliance decisions.

## Ingestion Standards

- Preserve raw PDFs and FDA landing-page HTML before parsing.
- Track version hashes using SHA-256.
- Preserve Draft, Final, and Withdrawn statuses.
- Preserve section hierarchy, page references, tables, docket/CFR references, product codes, and source URL metadata.
- Use parent-child chunking: section-level parent and paragraph-level child chunks.
- Re-index only changed documents when possible.

## Testing Standards

- Add or update tests for every new backend feature.
- Place tests under `tests/` mirroring the source structure.
- Include expected, edge, and failure cases for retrieval, ingestion, guardrails, citation binding, and API routes.
- Mock Azure OpenAI, PostgreSQL/pgvector, OpenSearch, object storage, and Langfuse in unit tests.
- Add integration tests for end-to-end ingestion and query-to-citation-bound-answer flows.

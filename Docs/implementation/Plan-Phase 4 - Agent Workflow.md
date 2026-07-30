# Plan: Phase 4 - Agent Workflow

## Goal

Implement the LangGraph agent layer as a controlled, citation-first workflow that wraps the completed Phase 3 hybrid retrieval client, Azure OpenAI-first LLM routing, fail-closed citation binding, confidence and refusal guardrails, and bounded faithfulness retries.

The recommended approach is to implement small, independently testable state, LLM, citation, guardrail, node, edge, and graph modules before wiring a full end-to-end graph run.

## Scope

### In Scope

- Typed LangGraph state for query understanding, retrieval, evidence, confidence, citations, retries, refusals, and response payloads.
- LangGraph StateGraph assembler with the MVP workflow nodes from `PLANNING.md`.
- Conditional routing edges for confidence, citation binding, faithfulness validation, retries, refusals, and final response.
- Azure OpenAI-first LLM provider abstraction with Claude and vLLM fallback wrappers.
- Citation-first prompt templates.
- Token streaming utilities that can later feed FastAPI SSE routes.
- Confidence scoring and refusal helpers.
- Fail-closed citation binding.
- Bounded faithfulness validation with a protocol-based validator.
- Unit tests with fake LLM, retrieval, and validator dependencies.

### Out of Scope

- FastAPI chat/search endpoints and SSE route wiring.
- Frontend chat or search UI.
- Supabase authentication and API security.
- Persistent audit tables or full Langfuse span integration beyond injectable hooks.
- Gold-set tuning and nightly quality regression.
- Neo4j, Graphiti, graph retrieval, or V1 knowledge graph workflows.

## Existing Anchors

- `src/retrieval/client.py` exposes `hybrid_search`, which returns candidates, `SearchResult` objects, Evidence Cards, and retrieval diagnostics.
- `src/retrieval/models.py` defines `HybridSearchResult` and `RetrievalCandidate`.
- `apps/api/schemas/answer.py` defines the final `Answer` response contract.
- `apps/api/schemas/evidence.py` defines the required Evidence Card citation contract.
- `apps/api/schemas/audit.py` defines audit event shapes for future persistence and transparency.
- `apps/api/settings.py` already includes LLM provider settings, Azure OpenAI settings, Anthropic/vLLM fallback settings, confidence threshold, and faithfulness retry count.
- `src/common/logging.py` provides structured logging.
- `pyproject.toml` already declares `langgraph`, `openai`, `anthropic`, `ragas`, `sse-starlette`, and `langfuse`.
- `src/agents` and `src/llm` currently contain package stubs only, so Phase 4 can define these module boundaries cleanly.

## Implementation Steps

### Phase 4.0 - Confirm Dependencies and Boundaries

Before implementation, confirm these constraints:

- Use existing dependencies already declared in `pyproject.toml`: `langgraph`, `openai`, `anthropic`, `ragas`, `sse-starlette`, and `langfuse`.
- Treat Phase 5 API routes and SSE endpoints as out of scope; Phase 4 may provide token-streaming utilities only.
- Treat gold-set tuning and nightly quality regression as Phase 6.
- Treat Neo4j, Graphiti, and graph retrieval as V1 only.
- Keep tests deterministic and credential-free with fake LLM, retrieval, and validator dependencies.

### Phase 4.1 - Typed Agent State

Create `src/agents/state.py`.

Define LangGraph-compatible state for:

- Input: query text, session id, raw filters, normalized retrieval filters.
- Understanding: rewritten query, intent, extracted FDA entities, retrieval route.
- Retrieval: `HybridSearchResult`, retrieval candidates, search results, Evidence Cards, retrieval diagnostics.
- Generation: generated answer text, prompt version, LLM provider, token usage metadata when available.
- Guardrails: confidence, confidence sufficiency, citation binding status, faithfulness status, retry count, max retries, refusal status, refusal reason.
- Transparency: node execution trace, provider fallback trace, retrieval errors, guardrail errors.

State shape (decided):

- Use a `TypedDict` for the top-level graph state. `HybridSearchResult` and `RetrievalCandidate` are frozen dataclasses and `EvidenceCard` is a Pydantic model; a `TypedDict` holds these directly as nested values with the least merge friction in LangGraph.
- Use Pydantic v2 models only for nested validated payloads such as execution trace entries, query understanding results, binding results, and refusal metadata.
- Nodes should return partial state updates rather than replacing the full state.

### Phase 4.2 - LLM Provider Abstraction

Create `src/llm/router.py`.

Define an async provider protocol:

```python
class LLMClient(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        ...

    async def stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> AsyncIterator[str]:
        ...
```

Implement provider wrappers for:

- Azure OpenAI primary.
- Anthropic Claude fallback.
- vLLM/OpenAI-compatible fallback.

Behavior:

- Use existing `apps/api/settings.py` fields: `LLM_PROVIDER`, Azure endpoint/key/version/deployment, `ANTHROPIC_API_KEY`, and `ONPREM_LLM_BASE_URL`.
- Validate missing credentials/configuration with safe, non-secret error messages.
- Do not expose raw SDK clients to agent nodes.
- Keep all unit tests fake-client based.

### Phase 4.3 - Citation-First Prompt Templates

Create `src/llm/prompts.py`.

Add versioned prompt templates for:

- `query_understand`
- grounded answer generation
- faithfulness validation
- refusal wording

Prompt requirements:

- Answer only from provided Evidence Cards/passages.
- Use inline `[n]` citation markers that correspond to the pre-assigned Evidence Card ids. Phase 3 (`candidates_to_evidence_cards`) already assigns each card a stable `citation_id` of the form `[1]`, `[2]`, ... over the reranked set; the prompt must present evidence using those exact ids and must not renumber them.
- Prefer refusal or clarification over unsupported claims.
- Do not make final legal/compliance determinations such as "you are compliant" or "FDA will approve".
- Preserve the product boundary: regulatory intelligence, not legal advice.

Also add an evidence-context formatter that preserves:

- citation id
- document title
- section title/id
- page number
- exact passage
- document status
- source URL
- version hash
- retrieval/rerank/confidence scores

### Phase 4.4 - Token Streaming Utilities

Create `src/llm/streaming.py`.

Provide provider-neutral async iterator helpers for:

- token events
- final message events
- error events

Streaming vs. fail-closed constraint: `citation_bind` and `faithfulness_guard` run after `generate_answer`, so tokens emitted while generating are a non-authoritative preview only. Streamed tokens must not be presented to the user as the final answer before guardrails pass. Phase 5 SSE integration must either (a) stream a preview and then send an authoritative committed/refused event after guardrails, or (b) stream only after validation. Emit a distinct final/committed event (separate from token events) so consumers can distinguish preview from validated output.

Keep FastAPI `EventSourceResponse` and SSE route construction out of scope until Phase 5.

### Phase 4.5 - Citation Binding

Create `src/agents/citation.py`.

Implement fail-closed citation binding. Citation binding is a validation/subset step, not an assignment step: `citation_id` values are pre-assigned by Phase 3, so binding parses the markers the LLM emitted and confirms they reference existing card ids.

- Parse generated answer markers such as `[1]`, `[2]`, including repeated and out-of-order markers.
- Match markers against the pre-assigned `EvidenceCard.citation_id` values from retrieval; the bound cards are the subset of retrieved cards actually cited.
- Fail closed when generated text has no citations, unknown citations, malformed citation ids, or cites evidence that is unavailable.
- Return a structured binding result with bound cards, cited ids, missing ids, and a boolean success flag.

Rules:

- Non-refused answers require at least one bound Evidence Card.
- Refusal answers may carry empty evidence.
- Citation binding failure routes to retry only while retry budget remains; otherwise it routes to refusal.

### Phase 4.6 - Guardrails and Refusals

Create `src/agents/guardrails.py`.

Implement:

- Confidence scoring over retrieved/reranked evidence using Evidence Card confidence values. Aggregate the per-card `confidence` values into a single answer-level score by taking the maximum over the reranked top-k cards (a single strong, faithful passage is sufficient to support a grounded answer). Empty evidence yields confidence `0.0`.
- Threshold check using `settings.confidence_threshold`.
- The aggregated confidence is the value carried into `Answer.confidence`. Refusals still emit a valid confidence float (the computed aggregate, which is `0.0` when there is no usable evidence).
- Refusal builders for:
  - no evidence
  - low confidence
  - retrieval failure
  - citation binding failure
  - faithfulness failure
  - unsupported query
  - compliance/legal determination risk
- Bounded retry decision helpers using `settings.max_faithfulness_retries`.
- Conservative compliance-boundary detector for prohibited determinations such as:
  - "you are compliant"
  - "you are not compliant"
  - "FDA will approve"
  - "this submission will be accepted"
  - equivalent final regulatory/legal determinations

Define a faithfulness validator protocol:

```python
class FaithfulnessValidator(Protocol):
    async def validate(
        self,
        *,
        answer_text: str,
        evidence_cards: list[EvidenceCard],
    ) -> FaithfulnessResult:
        ...
```

Phase 4 can provide an LLM/prompt-based validator and fake validators for tests. Keep deeper RAGAS/HHEM calibration for Phase 6 unless implementation reveals a low-friction adapter.

### Phase 4.7 - Workflow Nodes

Create `src/agents/nodes.py`, or split into `src/agents/nodes/*.py` if the file grows too large.

Implement the MVP nodes from `PLANNING.md`:

1. `query_understand`
   - Rewrite/classify the query and extract FDA entities using the LLM.
   - Safe fallback: keep the original query if understanding fails.

2. `retrieval_router`
   - Owns filter conversion: map the request's `dict[str, str]` filters into a `RetrievalFilters` model, ignoring unrecognized keys (do not fail the request on unknown filter keys) and recording ignored keys in the node trace.
   - Normalize filters and choose hybrid retrieval for MVP.
   - Metadata-constrained retrieval is represented as hybrid retrieval with filters.

3. `hybrid_retrieve`
   - Call `src/retrieval/client.py::hybrid_search` with injected DB/OpenSearch/model dependencies.
   - Preserve `HybridSearchResult` diagnostics.

4. `merge_rerank`
   - Do not duplicate Phase 3 RRF/reranking logic.
   - Normalize Phase 3 output into agent state and record diagnostics.

5. `confidence_check`
   - Compute confidence and route low-confidence states toward refusal before generation.

6. `generate_answer`
   - Call the LLM with citation-first evidence context.
   - Require `[n]` markers that correspond to Evidence Cards.

7. `citation_bind`
   - Invoke fail-closed citation binding.
   - Mark binding failure for retry/refusal routing.

8. `faithfulness_guard`
   - Validate the answer against bound evidence.
   - Increment retry count.
   - Request retry or refusal based on bounded retry state.

9. `respond`
   - Produce `apps/api/schemas/answer.py::Answer` with answer text, bound Evidence Cards, aggregated confidence, refusal state, session id, and generated timestamp.
   - The authoritative `Answer` is only produced here, after citation binding and faithfulness validation have passed. Any tokens streamed during `generate_answer` are a non-authoritative preview and must not be treated as the committed answer.

### Phase 4.8 - Conditional Routing Edges

Create `src/agents/edges.py`.

Define deterministic edge functions for:

- confidence route
- citation route
- faithfulness route
- terminal response route

Routing rules:

- Low confidence -> refusal response.
- Missing evidence -> refusal response.
- Retrieval failure -> refusal response.
- Compliance-risk output -> refusal response.
- Citation binding failure -> retry generation if retry budget remains, else refusal.
- Faithfulness failure -> retry generation if retry budget remains, else refusal.
- Successful faithfulness + citation binding -> final response.

### Phase 4.9 - LangGraph Graph Assembly

Create `src/agents/graph.py`.

Build a `StateGraph` with:

- `query_understand`
- `retrieval_router`
- `hybrid_retrieve`
- `merge_rerank`
- `confidence_check`
- `generate_answer`
- `citation_bind`
- `faithfulness_guard`
- `respond`

Provide a graph factory that accepts injectable dependencies for:

- LLM client
- retrieval callable
- PostgreSQL session factory
- OpenSearch client factory
- embedding model
- reranker model
- faithfulness validator
- tracing callbacks

Export the public graph/state APIs from `src/agents/__init__.py`.

### Phase 4.10 - Instrumentation and Transparency

Add node execution trace records to state:

- node name
- started_at
- completed_at
- status
- error type/message
- provider used
- evidence count
- confidence score
- retry count
- key retrieval diagnostics

Use `src/common/logging.py::get_logger` for structured node logs.

Keep Langfuse calls behind optional/injectable hooks so tests do not require Langfuse credentials.

### Phase 4.11 - Documentation and Task Tracking

After implementation and focused tests pass:

- Mark Phase 4 task checkboxes in `TASK.md`.
- Add README notes for running agent and LLM unit tests.
- Link this implementation plan from the Phase 4 section in `TASK.md`.

## Testing Plan

Create `tests/agents/` and `tests/llm/` with credential-free tests.

### Required Tests

1. `tests/agents/test_state.py`
   - State initialization.
   - Retry defaults.
   - Refusal state.
   - Execution trace model.
   - Serialization of nested payloads.

2. `tests/llm/test_router.py`
   - Provider selection.
   - Missing credential errors.
   - Azure config validation.
   - Anthropic/vLLM fallback selection.
   - Fake client generation.

3. `tests/llm/test_prompts.py`
   - Evidence context formatting.
   - Citation marker instructions.
   - Prompt contains citation-first and compliance-boundary instructions.

4. `tests/llm/test_streaming.py`
   - Token event iteration.
   - Final event.
   - Error event.
   - Provider-neutral behavior.

5. `tests/agents/test_citation.py`
   - Valid markers.
   - Repeated markers.
   - Out-of-order markers.
   - Missing marker failure.
   - Unknown citation failure.
   - No-citation failure.

6. `tests/agents/test_guardrails.py`
   - Confidence threshold behavior.
   - Refusal builders.
   - Compliance determination detection.
   - Bounded retry decisions.
   - Fake faithfulness validator pass/fail/retry cases.

7. `tests/agents/test_nodes.py` or `tests/agents/test_nodes/*.py`
   - Each of the nine nodes with injected fake LLM, retrieval, and validator dependencies.

8. `tests/agents/test_edges.py`
   - Low-confidence route.
   - Citation-failure route.
   - Faithfulness-failure route.
   - Retry-available route.
   - Retry-exhausted route.
   - Successful answer route.

9. `tests/agents/test_graph.py`
   - Graph compiles.
   - All MVP nodes are reachable.
   - Successful path reaches `respond`.
   - Refusal path reaches `respond`.
   - Retry path is bounded.

### Validation Commands

Run focused tests by slice:

```powershell
python -m pytest tests/llm
python -m pytest tests/agents/test_citation.py tests/agents/test_guardrails.py
python -m pytest tests/agents
```

Run the full regression before marking Phase 4 complete:

```powershell
python -m pytest
```

Optional local smoke after unit tests:

1. Run the graph with fake LLM plus live Phase 3 retrieval over indexed fixture data.
2. Verify supported queries return `Answer(refused=False)` with at least one Evidence Card.
3. Verify unsupported or low-evidence queries return `Answer(refused=True)` with a clear refusal reason.

## Key Decisions

- Phase 4 uses LangGraph for orchestration but keeps node logic as plain, independently testable functions.
- Nodes return partial state updates for LangGraph merge semantics.
- Azure OpenAI is the default provider.
- Claude Sonnet and vLLM are fallback providers through the same protocol, not direct dependencies in agent nodes.
- Phase 4 unit tests must not require live LLM, Langfuse, PostgreSQL, OpenSearch, or Azure credentials.
- Non-refused answers require at least one bound Evidence Card.
- Citation binding fails closed.
- Refusals may return `Answer(refused=True)` with a clear `refusal_reason` and empty evidence.
- The `merge_rerank` node does not duplicate Phase 3 RRF/reranking logic.
- Faithfulness validation is protocol-based. Phase 4 can ship an LLM/prompt validator and test doubles; deeper RAGAS/HHEM calibration belongs with Phase 6 evaluation.
- Compliance/legal determinations are blocked or refused.
- `citation_id` values are pre-assigned by Phase 3; the agent reuses them and never renumbers citations.
- Answer-level confidence is the maximum per-card confidence over the reranked top-k (0.0 when no evidence), and refusals still carry a valid confidence float.
- Streaming utilities are in scope, but FastAPI SSE route integration is Phase 5. Streamed tokens are a non-authoritative preview; the authoritative answer is only committed after citation binding and faithfulness validation pass.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Live LLM credentials unavailable in CI | Tests become flaky or blocked | Use fake clients for all unit tests and keep live smoke manual/staging only |
| LangGraph state merge friction with Pydantic models | Node updates become awkward | Use `TypedDict` for graph state and Pydantic models for nested validated payloads |
| Citation binding failure rate too high | Many refusals | Fail closed for MVP, log binding failures, tune prompts later with evaluation data |
| Faithfulness validation latency | User-visible delay | Keep validator protocol-based; use LLM prompt validator first and benchmark RAGAS/HHEM in Phase 6 |
| Retry loops inflate latency | SLA risk | Use `settings.max_faithfulness_retries` and deterministic edge tests |
| Compliance/legal determination leakage | Product safety risk | Add post-generation compliance-boundary check and route violations to refusal |
| Evidence context exceeds token limits | Generation failure or truncation | Limit to reranked top-k Evidence Cards and record truncation in node trace |\n| Streaming unvalidated tokens bypasses guardrails | Fail-closed / safety violation | Treat streamed tokens as a non-authoritative preview; commit the authoritative answer only after citation binding and faithfulness pass, and emit a distinct final/committed event |

## Definition of Done

Phase 4 is complete when:

- Typed agent state exists and is covered by tests.
- LLM provider abstraction supports Azure OpenAI primary plus Claude/vLLM fallback wrappers with fake-client tests.
- Citation-first prompts and streaming utilities exist.
- Fail-closed citation binding is implemented and tested.
- Confidence, refusal, faithfulness, retry, and compliance-boundary guardrails are implemented and tested.
- All nine MVP workflow nodes are implemented with injected dependencies.
- Conditional edges route success, retry, and refusal paths deterministically.
- LangGraph StateGraph assembler compiles and passes graph tests.
- Non-refused responses produce valid `Answer` objects with at least one Evidence Card.
- Refusal responses produce clear `Answer(refused=True)` objects.
- Focused agent/LLM tests and full project regression pass.
- `TASK.md` and README are updated after implementation.

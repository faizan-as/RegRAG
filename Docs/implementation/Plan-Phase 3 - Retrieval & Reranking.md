# Plan: Phase 3 - Retrieval & Reranking

## Goal

Build the retrieval layer as a small, testable package under `src/retrieval`: PostgreSQL + pgvector dense search, OpenSearch BM25 search, shared metadata filters, Reciprocal Rank Fusion, BGE-Reranker-Large reranking, and Evidence Card-ready result formatting.

The Phase 3 implementation should keep dense and keyword clients independently usable, then compose them in a unified hybrid client that Phase 4 LangGraph nodes and Phase 5 API routes can call.

## Scope

### In Scope

- PostgreSQL + pgvector dense search over `guidance_chunks`.
- OpenSearch BM25 keyword search over the `fda_guidance` index.
- Shared metadata filters for both retrieval stores.
- Reciprocal Rank Fusion of dense and sparse results.
- BGE-Reranker-Large cross-encoder reranking.
- Top-k result selection and Evidence Card-ready formatting.
- Retrieval parameter tuning hooks and test scaffolding.

### Out of Scope

- LangGraph workflow nodes.
- Chat or search API routes.
- Frontend search UI.
- Neo4j, Graphiti, or graph retrieval.
- Final parameter tuning before a curated gold set exists.

## Existing Anchors

- `src/db/models.py` contains `GuidanceChunk` with pgvector embeddings and `evidence_payload` JSONB.
- `src/ingestion/indexer.py` defines the dense and OpenSearch indexed payload shape.
- `apps/api/schemas/search.py` defines `SearchResult` and `RetrievalSource`.
- `apps/api/schemas/evidence.py` defines the required `EvidenceCard` contract.
- `apps/api/schemas/documents.py` defines document status and metadata fields.
- `apps/api/settings.py` already includes retrieval top-k, rerank top-k, embedding model, reranker model, OpenSearch, and pgvector settings.
- `src/common/clients.py` provides shared PostgreSQL and OpenSearch client factories.
- `src/ingestion/embedder.py` provides the model-loading and test-injection pattern to reuse for query embedding and reranking.

## Contract Constraints Discovered During Review

These existing-code facts drive several decisions below and must be honored:

- `src/ingestion/embedder.py::embed_chunks` only accepts `Chunk` objects and filters to `ChunkType.CHILD`. It cannot embed a raw query string. Only the `EmbeddingModel.encode()` protocol is directly reusable, so Phase 3 must add a dedicated query-embedding helper.
- `apps/api/schemas/search.py::SearchResult` uses `model_config = ConfigDict(extra="forbid")` and has no field for `evidence_payload`. It cannot carry the raw payload between retrieval and formatting, so an internal candidate model is required.
- `apps/api/schemas/evidence.py::EvidenceCard` makes `retrieval_score`, `rerank_score`, `confidence`, `source_url` (`HttpUrl`), `version_hash`, and `document_status` all **required**. Every produced card must supply a rerank score and a confidence value, including on fallback paths.
- The indexer stores the page number as `page` in OpenSearch and in `evidence_payload`, but as `page_number` in the pgvector row. `chunk_type` is stored as a string in both stores but is a `ChunkType` enum on the `Chunk` model. Formatting must normalize both.

## Implementation Steps

### Phase 3.0 - Internal Candidate Model and Query Embedding (Required Foundations)

These two foundations are required because existing contracts cannot carry Phase 3 data as-is.

Create `src/retrieval/models.py`:

- Define an internal `RetrievalCandidate` dataclass (or `extra="forbid"` model) that carries the reconstructed `Chunk`, the `RetrievalSource`, per-stage scores (`dense_score`, `keyword_score`, `rrf_score`, `rerank_score`, `rank`), and the raw `evidence_payload` dict.
- All retrieval stages (dense, keyword, RRF, rerank) operate on `RetrievalCandidate`. Convert to `SearchResult` and `EvidenceCard` only at the API/formatting boundary, since `SearchResult` forbids extra fields and cannot hold `evidence_payload`.

Add a query-embedding helper (in `src/retrieval/pgvector_client.py` or a small `src/retrieval/query_embedding.py`):

```python
def embed_query(
    query_text: str,
    *,
    model: EmbeddingModel | None = None,
    model_name: str = "BAAI/bge-m3",
) -> list[float]:
    ...
```

- Reuse the `EmbeddingModel` protocol and `load_embedding_model()` from `src/ingestion/embedder.py`.
- Call `model.encode([query_text], normalize_embeddings=True)` and return the single vector as `list[float]`.
- Keep the model injectable so tests never load the real BGE-M3 model.

### Phase 3.1 - Shared Retrieval Filters

Create `src/retrieval/filters.py`.

Define a shared `RetrievalFilters` model and query builders for both SQLAlchemy and OpenSearch.

Support MVP filters:

- `center`
- `status`
- `lifecycle_state`
- `docket_id`
- `topics`
- `communication_type`
- `regulated_product`
- `issue_date_from`
- `issue_date_to`
- `section_id`
- `cfr_references`, where indexed data exists
- `product_codes`, where indexed data exists

Default behavior:

- Exclude withdrawn guidance unless `lifecycle_state` explicitly requests it.
- Use exact-match filters only for MVP.
- Do not automatically widen filters when no results are found.

### Phase 3.2 - PostgreSQL + pgvector Dense Search

Create `src/retrieval/pgvector_client.py`.

Implement:

```python
async def search_dense_chunks(
    session,
    query_embedding: list[float],
    *,
    filters: RetrievalFilters | None = None,
    top_k: int,
) -> list[RetrievalCandidate]:
    ...
```

Behavior:

- Query `GuidanceChunk` using pgvector cosine distance.
- Score as similarity: `1 - distance`.
- Validate the query embedding length against `settings.embedding_dim` or `get_pgvector_config()`.
- Prefer child chunks as evidence candidates.
- Preserve `parent_chunk_id`, `section_id`, `section_title`, `page_number`, `char_start`, `char_end`, `source_url`, `version_hash`, and `evidence_payload` on the `RetrievalCandidate`.
- Apply the SQLAlchemy filter clauses from `filters.py`.

### Phase 3.3 - OpenSearch BM25 Search

Create `src/retrieval/opensearch_client.py`.

Implement:

```python
def search_keyword_chunks(
    client,
    query_text: str,
    *,
    filters: RetrievalFilters | None = None,
    top_k: int,
    index_name: str,
) -> list[RetrievalCandidate]:
    ...
```

Behavior:

- Query `text`, `doc_title`, and `section_title` using a boosted `multi_match` query.
- Apply OpenSearch filter clauses from `filters.py`.
- Map hits back to `RetrievalCandidate` objects using `_source.evidence_payload` plus indexed chunk fields, coercing `chunk_type` (string) to `ChunkType` and reading the page from the `page` field.
- Return an empty list for zero hits.
- Let connection or index errors bubble up so the unified client can apply fallback policy.

### Phase 3.4 - Reciprocal Rank Fusion

Create `src/retrieval/hybrid.py`.

Implement:

```python
def reciprocal_rank_fusion(
    dense_results: Sequence[RetrievalCandidate],
    keyword_results: Sequence[RetrievalCandidate],
    *,
    rrf_k: int = 60,
    top_k: int,
) -> list[RetrievalCandidate]:
    ...
```

Formula:

```text
rrf_score = sum(1 / (rrf_k + rank_position))
```

Behavior:

- Deduplicate by `chunk_id`.
- Preserve original dense score, keyword score, and source ranks.
- Set `source=RetrievalSource.FUSED`.
- Set `rrf_score` and final score.
- Deterministic tie-break: higher RRF score, best source rank, then `chunk_id`.

### Phase 3.5 - BGE-Reranker-Large Wrapper

Create `src/retrieval/reranker.py`.

Define an injectable protocol, for example:

```python
class RerankerModel(Protocol):
    def predict(self, pairs: Sequence[tuple[str, str]]) -> Sequence[float]:
        ...
```

Implement:

```python
def rerank_results(
    query_text: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    model: RerankerModel | None = None,
    model_name: str = "BAAI/bge-reranker-large",
    top_k: int,
    batch_size: int = 16,
) -> list[RetrievalCandidate]:
    ...
```

Behavior:

- Lazy-load the reranker only when no model is injected.
- Score `(query_text, candidate.chunk.text)` pairs.
- Batch inference for performance.
- Sort by rerank score descending.
- Set `source=RetrievalSource.RERANKED` and populate `rerank_score` on each candidate.
- Truncate to `top_k`.
- Keep tests fully fake-model based so they do not load the real BGE model.
- The reranker runs on whatever candidates survive fusion, including single-source (dense-only or keyword-only) fallback sets, so that every candidate carries a `rerank_score` before formatting. Only skip reranking if the reranker itself fails; see the fallback rerank-score rule in Phase 3.7.

### Phase 3.6 - Evidence Card and Result Formatting

Create `src/retrieval/formatting.py`.

Implement helpers to convert reranked retrieval results into `EvidenceCard` instances and final `SearchResult` lists.

Use fields from the ingestion evidence payload:

- `slug`
- `doc_title`
- `version_hash`
- `status`
- `source_url`
- `section_id`
- `section_title`
- `page`
- `char_start`
- `char_end`
- `parent_id`

Evidence Card behavior:

- `document_id` comes from `slug` / chunk document id.
- `title` comes from `doc_title`.
- `passage` uses full child chunk text for MVP.
- `retrieval_score` comes from RRF score when available, otherwise the source score.
- `rerank_score` comes from the cross-encoder score.
- `confidence` uses the MVP formula defined below; calibrated confidence is deferred to evaluation.
- Normalize store field differences: read the page from `page` (OpenSearch/`evidence_payload`) or `page_number` (pgvector), and coerce `chunk_type` back to the `ChunkType` enum.
- Fail closed with a clear exception if any required Evidence Card field is missing (`retrieval_score`, `rerank_score`, `confidence`, `source_url`, `version_hash`, `document_status`, `passage`, `title`, `document_id`).

MVP confidence formula (provisional, replace after evaluation):

- Map the cross-encoder `rerank_score` through a logistic squash into `[0, 1]`: `confidence = 1 / (1 + exp(-rerank_score))`.
- If a candidate has no rerank score because the reranker failed (see Phase 3.7 fallback), use the fallback rerank score and set `confidence = 0.0` so guardrails treat it as low-confidence rather than trusted.

### Phase 3.7 - Unified Hybrid Retrieval Client

Create `src/retrieval/client.py`.

Implement:

```python
async def hybrid_search(
    query_text: str,
    *,
    session,
    opensearch_client,
    embedding_model=None,
    reranker_model=None,
    filters: RetrievalFilters | None = None,
    top_k: int | None = None,
    rerank_top_k: int | None = None,
) -> HybridSearchResult:
    ...
```

Flow:

1. Generate the query embedding with the `embed_query` helper (BGE-M3).
2. Run dense retrieval and keyword retrieval.
3. Fuse candidates with RRF.
4. Rerank fused candidates with BGE-Reranker-Large (also runs on single-source fallback sets).
5. Format final results and Evidence Cards.

Retriever fallback policy:

- If dense search fails but BM25 succeeds, rerank and return keyword-only results with degraded-source metadata.
- If BM25 fails but dense succeeds, rerank and return dense-only results.
- If both fail, raise a retrieval failure.

Reranker fallback rule (protects the required `EvidenceCard.rerank_score`):

- The reranker always runs on the surviving candidate set, even when only one retriever succeeded.
- If the reranker itself fails or is unavailable, assign a documented fallback `rerank_score` (the fused/source score, or `0.0` when no score exists) and set `confidence = 0.0` so downstream guardrails treat those cards as low-confidence.
- Never emit an Evidence Card without a `rerank_score`; formatting fails closed if one is missing.

### Phase 3.8 - Tuning Hooks and Gold-Set Scaffold

Add a lightweight retrieval evaluation harness under `src/eval/` or `tests/retrieval/`.

Prepare for:

- recall@10
- filtered recall
- dense-only vs BM25-only comparison
- RRF result quality
- reranked precision

Do not tune final parameters until `src/eval/golden_set.json` exists.

### Phase 3.9 - Documentation and Task Tracking

After implementation and tests pass:

- Mark Phase 3 tasks complete in `TASK.md`.
- Add README instructions for local retrieval smoke validation against Docker PostgreSQL + OpenSearch.
- Record any discovered data gaps under `TASK.md` > `Discovered During Work`.

## Testing Plan

Create `tests/retrieval/` with focused unit tests.

### Required Tests

1. `test_models.py`
   - `RetrievalCandidate` construction and score fields.
   - Round-trip of `evidence_payload` through a candidate.

2. `test_query_embedding.py`
   - `embed_query` returns a single vector via an injected fake `EmbeddingModel`.
   - No real model is loaded in tests.

3. `test_filters.py`
   - SQLAlchemy filter builder for center, status, lifecycle state, docket, topics, and dates.
   - OpenSearch filter builder for the same fields.
   - Default active-only behavior.

4. `test_pgvector_client.py`
   - Embedding-dimension validation.
   - Dense score mapping.
   - Empty result handling.
   - Metadata filter application.
   - `RetrievalCandidate` construction including `evidence_payload`.

5. `test_opensearch_client.py`
   - BM25 request body construction.
   - Filter clause construction.
   - Hit mapping to `RetrievalCandidate`, including `page` and `chunk_type` coercion.
   - Empty result handling.

6. `test_hybrid.py`
   - RRF score math.
   - Deduplication by `chunk_id`.
   - Dense-only and keyword-only inputs.
   - Deterministic tie-breaking.

7. `test_reranker.py`
   - Fake model scoring.
   - Batch behavior.
   - Top-k truncation.
   - Empty candidate list.
   - Single-source candidate sets still receive rerank scores.

8. `test_formatting.py`
   - Evidence Card construction.
   - Required-field failure (missing `rerank_score`, `confidence`, `source_url`, etc.).
   - Source URL validation.
   - Status mapping.
   - Page normalization across `page`/`page_number`.
   - MVP confidence formula output range.
   - Retrieval/rerank score propagation.

9. `test_client.py`
   - Full injected flow: query embedding -> dense/BM25 -> RRF -> rerank -> Evidence Cards.
   - Dense failure fallback (keyword-only still reranked).
   - Keyword failure fallback (dense-only still reranked).
   - Reranker failure assigns fallback score and zero confidence.
   - Both retrievers failing raises retrieval failure.

### Validation Commands

Run focused tests after each implementation slice:

```powershell
python -m pytest tests/retrieval/test_models.py
python -m pytest tests/retrieval/test_query_embedding.py
python -m pytest tests/retrieval/test_filters.py
python -m pytest tests/retrieval/test_pgvector_client.py
python -m pytest tests/retrieval/test_opensearch_client.py
python -m pytest tests/retrieval/test_hybrid.py
python -m pytest tests/retrieval/test_reranker.py
python -m pytest tests/retrieval/test_formatting.py
python -m pytest tests/retrieval/test_client.py
```

Run the full regression before marking Phase 3 complete:

```powershell
python -m pytest
```

Optional local smoke after unit tests:

1. Start Docker PostgreSQL + OpenSearch.
2. Ensure a small fixture document is indexed.
3. Run one hybrid query.
4. Verify at least one Evidence Card resolves to source URL, version hash, section/page, passage, retrieval score, and rerank score.

## Key Decisions

- MVP filters are exact-match and fail closed.
- Withdrawn guidance is excluded from retrieval by default.
- Child chunks are the primary evidence unit.
- Parent IDs are preserved for future context expansion and document-viewer navigation.
- Evidence Card `passage` uses full child chunk text for MVP.
- RRF starts with `k = 60`.
- BGE-Reranker-Large is mandatory in the final hybrid path but must be injectable for tests.
- Retrieval stages operate on an internal `RetrievalCandidate` model; `SearchResult`/`EvidenceCard` are produced only at the boundary because `SearchResult` forbids extra fields and cannot carry `evidence_payload`.
- A dedicated `embed_query` helper wraps the `EmbeddingModel.encode()` protocol; `embed_chunks` is not reused for queries because it is chunk-only.
- The reranker runs on every surviving candidate set, including single-source fallback, so all Evidence Cards carry a `rerank_score`. If the reranker fails, cards get a documented fallback score and `confidence = 0.0`.
- MVP confidence is a provisional logistic squash of the rerank score, replaced after evaluation.
- Graph retrieval, LangGraph nodes, API endpoints, and frontend UI are out of scope for this plan.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| BGE-Reranker-Large latency on CPU | May threaten the MVP latency target | Keep model injectable, batch reranking, benchmark before choosing a smaller fallback |
| CFR/product-code filters may not be populated yet | Filters may be structurally supported but sparse | Implement safe optional filters and add discovered ingestion gaps to `TASK.md` |
| Missing evidence payload fields in older indexed chunks | Evidence Card formatting may fail closed | Repair ingestion/indexing payloads rather than weakening validation |
| OpenSearch outage | Hybrid retrieval degradation | Allow dense-only fallback in unified client |
| PostgreSQL/pgvector issue | Hybrid retrieval degradation | Allow keyword-only fallback in unified client |
| RRF parameter uncertainty | Lower retrieval quality | Keep `k` configurable and tune against the gold set later |

## Definition of Done

Phase 3 is complete when:

- A query-embedding helper produces a query vector from the BGE-M3 protocol.
- An internal `RetrievalCandidate` model carries chunk, scores, and evidence payload across stages.
- Dense pgvector retrieval returns scored candidates.
- OpenSearch BM25 retrieval returns scored candidates.
- Shared filters work consistently across both stores.
- RRF fuses dense and sparse candidates deterministically.
- BGE-Reranker-Large reranks fused and single-source candidate sets with injectable test doubles.
- Final retrieval output can be formatted into valid Evidence Cards, with every card carrying required `retrieval_score`, `rerank_score`, and `confidence`.
- Focused retrieval tests and the full project test suite pass.
- `TASK.md` and README are updated after implementation.

# Plan: Phase 2 — Ingestion System (Two-Tier, Catalog-First)

## Goal

Build the FDA guidance ingestion pipeline end-to-end using a **two-tier, catalog-first**
architecture driven by the FDA guidance **JSON catalog**:

> **Tier 1 (Catalog Sync):** fetch FDA JSON catalog → snapshot raw → normalize → upsert PostgreSQL
> registry → diff (NEW / UPDATED / WITHDRAWN).
>
> **Tier 2 (Content Ingestion):** for NEW/UPDATED only → resolve PDF → download + preserve raw →
> SHA-256 version → parse → parent-child chunk → BGE-M3 embed → index (pgvector dense + OpenSearch BM25)
> → snapshot → daily update report.

Every chunk must carry fail-closed provenance metadata so downstream Evidence Cards resolve to an
exact FDA source (document, section/page, passage, version hash, URL).

## Data Source

The FDA guidance search UI is backed by a **single static JSON file** (not a paginated endpoint):

```
https://www.fda.gov/files/api/datatables/static/search-for-guidance.json
```

- One record per guidance document (~2,788 rows) with structured, HTML-escaped metadata.
- Fetch the whole file once per run; **no pagination**. Snapshot it date-stamped before parsing.
- Records are **metadata rows, not content** — PDF/landing-page fetch happens in Tier 2.
- Fixtures: `Docs/search-for-guidance-sample.json` (4 rows) and
  `Docs/search-for-guidance-17072026-1815.json` (full snapshot).

### Field Map (raw JSON → normalized)

| Raw JSON field | Normalized field | Transform |
|---|---|---|
| `title` | `title`, `landing_url`, `slug` | HTML anchor → text + relative href; slug = last path segment |
| `field_associated_media_2` | `pdf_url` | HTML anchor → `/media/<id>/download`; **often empty (~75%)** |
| `field_issue_datetime` | `issue_date` | `MM/DD/YYYY` → ISO date |
| `field_final_guidance_1` | `status` | `Draft` / `Final` |
| `field_center` / `field_issuing_office_taxonomy` | `center` | e.g. "Human Foods Program", CDER, CBER, CDRH |
| `field_communication_type` | `comm_type` | e.g. "Guidance Document" |
| `topics-product` / `term_node_tid` | `topics[]` | comma-separated → array |
| `field_regulated_product_field` | `regulated_product` | HTML entity decode (`&amp;` → `&`) |
| `field_docket_number` | `docket_id`, `docket_url` | anchor → `FDA-YYYY-D-NNNN` + regulations.gov URL |
| `field_comment_close_date` | `comment_close` | draft comment window |
| `open-comment` | `open_comment` | " No " / "Yes" → boolean |
| `changed` | `fda_last_changed` | `<time datetime="…">` → ISO timestamp — **drives change detection** |

## Store Roles (Phase 2)

| Store | Role in Phase 2 |
|-------|-----------------|
| **PostgreSQL `guidance_registry`** | Tier-1 catalog registry: one row per document keyed by `slug`. Full normalized metadata + `fda_last_changed` + `lifecycle_state`. Drives change detection, re-index-only-changed, PRD search filters, and daily reports. |
| **Local artifact storage + PostgreSQL `source_artifacts`** | Durable archive metadata and bytes: date-stamped raw JSON catalog snapshots, raw PDFs / landing HTML (`raw/{slug}/{sha256}.pdf`), per-version parsed snapshots, daily report JSON. PostgreSQL records storage backend, object key, SHA-256, content type, size, source URL, document slug, and version hash. |
| **PostgreSQL `guidance_chunks` (pgvector)** | Child-chunk dense vectors (1024-dim, cosine) + rich evidence-card metadata, in the same Postgres instance as the registry. |
| **OpenSearch `fda_guidance`** | BM25 keyword index (text + metadata). |

> **PostgreSQL is brought forward into Phase 2** (it already runs in `docker-compose.yml` and is the
> PRD's metadata store). This supersedes the earlier "no PostgreSQL / Qdrant registry" decision, and
> dense embeddings are now consolidated into the same Postgres instance via pgvector (no Qdrant in the MVP).
> Users, sessions, and the audit trail remain deferred to the API/auth phase.

## Modules

Supporting:

- `src/common/db.py` — async SQLAlchemy 2.0 engine + session factory from `settings.database_url` (asyncpg).
- `src/common/storage.py` — local filesystem artifact adapter: path-safe, atomic writes for catalog snapshots, raw PDF/HTML, parsed snapshots, and reports.
- `src/common/clients.py` — shared PostgreSQL (pgvector) + OpenSearch client factories (read + write).

Data model & migrations:

- `src/db/models.py` — `GuidanceRegistry`, `SourceArtifact`, and `LifecycleState` ORM models.
- Alembic migrations for `guidance_registry` and `source_artifacts`.

Ingestion (`src/ingestion/`):

**Tier 1 — Catalog Sync**

- `fda_catalog.py` — fetch static JSON (httpx), snapshot raw to local artifact storage + `source_artifacts`, normalize rows (`html.unescape` + strip tags, extract href/`datetime`/text, split topics), derive `slug`.
- `registry.py` — PostgreSQL CRUD + diff over `guidance_registry`; emit NEW / UPDATED / WITHDRAWN change events.

**Tier 2 — Content Ingestion**

- `pdf_resolver.py` — resolve PDF URL: registry `pdf_url` first → landing-page fallback (BeautifulSoup `/media/<id>/download`) → else ingest landing-page HTML body.
- `pdf_parser.py` — PyMuPDF text/sections/page offsets + Unstructured table extraction.
- `version_tracker.py` — SHA-256 content hashing, version snapshots, status/lifecycle transition events.
- `chunking.py` — parent-child chunking (section-level parent, paragraph-level child).
- `embedder.py` — BGE-M3 batch embedding generation.
- `indexer.py` — write dense vectors + payload → PostgreSQL `guidance_chunks` (pgvector); BM25 docs → OpenSearch. Deterministic chunk IDs `{slug}:{version_hash}:{chunk_no}` for idempotent upserts.

**Orchestration & reporting**

- `report.py` — `IngestionReport` (new/updated/withdrawn) for the daily summary.
- `pipeline.py` — orchestrates both tiers; APScheduler daily schedule; one-time full backfill; bounded Tier-2 worker pool.

## Model & Settings Changes

- Extend `DocumentMetadata` (`apps/api/schemas/documents.py`, `extra="forbid"`): add `center`, `topic`,
  `communication_type`, `regulated_product`, `issue_date`, `fda_last_changed`, `comment_close`,
  `open_comment`, `lifecycle_state`; keep `cfr_references: list[str]` and `product_codes: list[str]`
  (PDF-derived). `document_id` = `slug`.
- Add `DocumentVersion` model (`document_id`/`slug`, `version_hash`, `status`, snapshot keys, `indexed_at`, `supersedes`).
- Add settings: `FDA_GUIDANCE_JSON_URL` (static catalog file), `FDA_BASE_URL`, chunk sizes,
  `EMBED_BATCH_SIZE`, `INGEST_SCHEDULE_CRON`, pgvector table name + vector dimension (1024 for BGE-M3),
  `OBJECT_STORE_BACKEND=local`, and `OBJECT_STORE_BASE_PATH=data/object_store`.
- `database_url` is now **used** in Phase 2 (asyncpg driver).
- Add deps: `alembic` (migrations) and `beautifulsoup4` (landing-page fallback parse).

## PostgreSQL Registry Schema

```sql
CREATE TABLE guidance_registry (
    slug              TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    landing_url       TEXT NOT NULL,
    pdf_url           TEXT,                 -- may be NULL; resolved in Tier 2
    status            TEXT,                 -- Draft | Final
    center            TEXT,
    comm_type         TEXT,
    topics            TEXT[],
    regulated_product TEXT,
    docket_id         TEXT,
    docket_url        TEXT,
    issue_date        DATE,
    comment_close     DATE,
    open_comment      BOOLEAN,
    fda_last_changed  TIMESTAMPTZ,          -- from feed `changed`
    first_seen_at     TIMESTAMPTZ DEFAULT now(),
    last_synced_at    TIMESTAMPTZ,
    lifecycle_state   TEXT DEFAULT 'active' -- active | withdrawn
);
CREATE INDEX ix_reg_status  ON guidance_registry(status);
CREATE INDEX ix_reg_center  ON guidance_registry(center);
CREATE INDEX ix_reg_docket  ON guidance_registry(docket_id);
CREATE INDEX ix_reg_changed ON guidance_registry(fda_last_changed);
```

## Source Artifact Metadata Schema

```sql
CREATE TABLE source_artifacts (
  id              UUID PRIMARY KEY,
  storage_backend TEXT NOT NULL DEFAULT 'local',
  object_key      TEXT NOT NULL UNIQUE,
  artifact_kind   TEXT NOT NULL,
  content_type    TEXT NOT NULL,
  sha256          CHAR(64) NOT NULL,
  size_bytes      BIGINT NOT NULL,
  source_url      TEXT,
  document_slug   TEXT REFERENCES guidance_registry(slug) ON DELETE SET NULL,
  version_hash    CHAR(64),
  created_at      TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE INDEX ix_source_artifacts_document_slug ON source_artifacts(document_slug);
CREATE INDEX ix_source_artifacts_sha256 ON source_artifacts(sha256);
CREATE INDEX ix_source_artifacts_version_hash ON source_artifacts(version_hash);
```

## Chunk Payload (pgvector row / OpenSearch doc)

Every child chunk carries the metadata needed to build an Evidence Card at answer time:

```json
{
  "slug": "guidance-industry-voluntary-labeling...",
  "doc_title": "Guidance for Industry: Voluntary Labeling...",
  "version_hash": "sha256:ab12...",
  "status": "Final",
  "center": "Human Foods Program",
  "comm_type": "Guidance Document",
  "topics": ["Bioengineering / GMOs", "Labeling"],
  "docket_id": "FDA-2000-D-0075",
  "issue_date": "2019-03-11",
  "source_url": "https://www.fda.gov/media/120958/download",
  "section_title": "III. Labeling Recommendations",
  "page": 7,
  "char_start": 1423,
  "char_end": 2011,
  "parent_id": "…"
}
```

## Steps

### 2A — Foundations (parallelizable)

1. `src/common/db.py` async SQLAlchemy engine + session factory (asyncpg from settings).
2. `src/db/models.py` `GuidanceRegistry` model + `LifecycleState` enum; Alembic migration (or `create_all`).
3. `storage.py` local artifact adapter + source artifact metadata model/migration.
4. `clients.py` shared PostgreSQL (pgvector) + OpenSearch client factories.
5. Extend `DocumentMetadata` + add `DocumentVersion`; add ingestion + FDA JSON settings; add `alembic` + `beautifulsoup4` deps.

### 2B — Tier 1: Catalog Sync (depends on 2A.1–2A.3, 2A.5)

6. `fda_catalog.py`: fetch static JSON; snapshot raw date-stamped to local artifact storage and `source_artifacts`; normalize rows
   (HTML unescape, extract href/datetime/text, split topics, decode entities); derive `slug`.
7. `registry.py`: ensure/upsert `guidance_registry`; diff incoming vs stored on `(slug, fda_last_changed, status)`.
   New slug → NEW; same slug + newer `changed` or status flip → UPDATED; prior slug absent → WITHDRAWN
   (soft-delete, `lifecycle_state='withdrawn'`). Emit change events.
8. One-time full metadata backfill of all rows (no downloads).

### 2C — Tier 2: Content Ingestion (depends on 2B; runs for NEW/UPDATED)

9. `pdf_resolver.py`: registry `pdf_url` first → landing-page fallback (BeautifulSoup) → else HTML body.
10. Download PDF/HTML; preserve raw to `raw/{slug}/{sha256}.pdf` in local artifact storage.
11. `version_tracker.py`: SHA-256 over downloaded bytes; skip re-parse if hash unchanged; snapshot to local artifact
  storage and `source_artifacts`; record status/lifecycle transitions (Draft → Final, Active → Withdrawn); supersedes detection via `docket_id`.
12. `pdf_parser.py`: PyMuPDF text + sections + page offsets; Unstructured table extraction.
13. `chunking.py`: section parents + paragraph children; carry `section_title` / `page` / `char_start/end` / `parent_id`.
14. `embedder.py`: BGE-M3 (sentence-transformers), batched, with progress logging.

### 2D — Indexing (depends on 2C)

15. `indexer.py`: ensure the pgvector `guidance_chunks` table (1024-dim vector column + cosine index) + upsert child vectors with evidence-card
    payload using deterministic IDs `{slug}:{version_hash}:{chunk_no}`; ensure OpenSearch index + bulk index
    text + metadata. Delete + reindex changed; remove withdrawn from retrieval; update registry `last_synced_at`.

### 2E — Orchestration & Reporting (depends on 2B, 2D)

16. `report.py`: `IngestionReport` (new/updated/withdrawn); write daily report JSON to local artifact storage.
17. `pipeline.py`: orchestrate both tiers; APScheduler daily Tier-1 sync; Tier-2 triggered by change events;
    bounded worker pool (4–8) with polite rate limiting + backoff; nightly reconciliation
    (registry active count == indexed doc count); log per-document outcomes to Langfuse.

### 2F — Tests

18. `tests/ingestion/*` mirroring modules; mock network / PostgreSQL / pgvector / OpenSearch / storage; sample JSON +
    sample PDF fixtures; unit tests for HTML unescape, date parsing, status mapping, slug stability, and the
    NEW/UPDATED/WITHDRAWN diff; integration test: fixture catalog → registry upsert → resolve PDF → parse →
    chunk → embed → index → snapshot → report.

## Decisions

- **Catalog-first, two-tier.** Cheap daily Tier-1 metadata sync of all docs; expensive Tier-2 content
  ingestion runs incrementally only for NEW/UPDATED. Decoupled for completeness, idempotency, resumability,
  and two clean audit ledgers (what FDA published vs. what we indexed).
- **PostgreSQL registry now** (`guidance_registry`) — brought forward into Phase 2; drives change detection
  and PRD filters. Overrides the earlier Qdrant-registry / no-PostgreSQL decision. Dense embeddings also
  live in this Postgres instance via pgvector — no Qdrant in the MVP.
- **Static JSON catalog** as the authoritative discovery source; the seed-list HTML crawl is dropped.
  HTML parsing is retained only as the Tier-2 landing-page PDF fallback.
- **Identity:** `slug` (landing-page last path segment) is the primary key; `docket_id` is a secondary index.
- **PDF acquisition:** JSON `field_associated_media_2` link first, landing-page fallback second (~75% lack a feed link).
- **Withdrawn detection included:** slug present in a prior sync but absent from the current feed → soft-delete.
- **Change detection:** `fda_last_changed` (cheap, pre-download) confirmed by SHA-256 of PDF bytes (post-download).
- **Fixture-first** development for deterministic tests, then validate against the live static URL.
- **APScheduler** for scheduling (Prefect deferred).
- pgvector vector dimension 1024 (BGE-M3), cosine distance; embed child chunks only (parents used for context expansion).
- Daily report lives in `src/ingestion/report.py`; `src/monitoring/alerts.py` integration deferred to its phase.

## Edge Cases

- **No PDF in feed (~75%)** → resolve from landing page; if still none, ingest landing-page HTML body.
- **HTML-escaped fields** (`\u003C`, `&amp;`) → unicode-unescape + `html.unescape` + strip tags.
- **Multi-value topics** → split on comma into arrays; normalize whitespace.
- **Scanned/image PDFs** → detect low extracted-text ratio → flag for OCR (deferred, out of MVP scope).
- **Large tables** → Unstructured table extraction; keep tables as a distinct chunk type.
- **Duplicate docket, different slug** → group by `docket_id` for supersession detection (V1 graph).
- **fda.gov errors / throttling** → exponential backoff, resumable queue, dated raw-catalog snapshot for replay.

## Verification

- Unit tests per module: `.venv\Scripts\python.exe -m pytest tests/ingestion -q`.
- Integration test end-to-end on a fixture catalog + PDF (catalog → registry → resolve → parse → chunk →
  embed → index → snapshot → report).
- Change detection: unchanged `changed` → skipped; newer `changed`/status flip → reindexed; absent slug →
  withdrawn soft-delete.
- Manual: run pipeline against the live static URL in dev; confirm registry row count, source artifact row
  count, pgvector chunk row count, OpenSearch doc count, and report JSON in local artifact storage.
- `get_errors` clean; ruff / black / mypy pass.
- Update `TASK.md` Phase 2 checkboxes and `PLANNING.md` ingestion sections.

## Excluded Scope

- OCR for scanned PDFs; broad HTML crawl; Graphiti / Neo4j; `src/monitoring` alerts wiring;
  users / sessions / audit-trail tables (deferred to the API/auth phase).

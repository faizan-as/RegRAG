# Tech Stack Key Decision Document

## Project Details

**Project Name:** AI-Powered FDA Regulatory Intelligence Platform

**Positioning:** Solo-founder, accuracy-first, open-source-first regulatory intelligence product for FDA guidance documents.

**Objective:** Build a citation-first AI-powered search and RAG platform that helps users query FDA guidance content, retrieve reliable answers, compare guidance documents, and understand document evolution over time.

**Primary MVP Goal:** Ship a trusted hybrid RAG product that answers FDA guidance questions with verifiable citations, confidence checks, and faithfulness validation.

**V1 Goal:** Add Graphiti with Neo4j to support cross-guidance reasoning, temporal fact tracking, entity relationships, and document lifecycle intelligence.

---

## Constraints Applied Throughout

| Constraint | Decision Impact |
|-----------|-----------------|
| **Accuracy & trust first** | Retrieval quality, citation binding, reranking, faithfulness checks, and refusal logic are treated as non-negotiable. |
| **Hybrid deployment** | Architecture supports cloud deployment first, with optional on-prem path for regulated or enterprise customers. |
| **Graphiti role** | Graphiti enhances RAG in V1; it does not replace hybrid RAG and should not be part of the MVP. |
| **Solo-founder execution** | Keep the MVP operationally simple with fewer moving parts, fewer databases, and Docker Compose deployment. |
| **Open-source-first stack** | Prefer self-hostable components such as PostgreSQL + pgvector, OpenSearch, LangGraph, BGE models, Langfuse, Neo4j, and Graphiti OSS. |
| **Citation-first product moat** | Every answer must include traceable evidence from source FDA documents. |

---

## Recommended Stack

| Layer | Recommended Choice | MVP / V1 |
|------|--------------------|----------|
| Orchestration | LangGraph | MVP |
| Retrieval | PostgreSQL + pgvector (dense) + OpenSearch (BM25) | MVP |
| Embeddings | BGE-M3 | MVP |
| Reranker | BGE-Reranker-Large | MVP |
| LLM | Claude Sonnet API | MVP |
| On-prem LLM fallback | Llama 3.3 70B or Qwen via vLLM | MVP / V1 |
| Ingestion | Python + PyMuPDF + Unstructured | MVP |
| API | FastAPI + Pydantic v2 + SSE | MVP |
| Frontend | Next.js 15 + shadcn/ui + Vercel AI SDK | MVP |
| Auth | Supabase or Clerk | MVP |
| Observability | Langfuse | MVP |
| Evaluation | RAGAS + Vectara HHEM + curated FDA gold set | MVP |
| Knowledge Graph | Graphiti + Neo4j | V1 |
| Deployment | Docker Compose on single VM | MVP |
| Enterprise deployment | ECS, Fly.io, Kubernetes, or on-prem container deployment | V1 / V2 |

**Final stack direction:** LangGraph + PostgreSQL/pgvector + BGE-M3 + Azure OpenAI for MVP, with OpenSearch (BM25), reranking, evidence cards, and faithfulness guardrails added before pilot launch. Dense vectors and relational data are consolidated into a single Postgres instance; Graphiti + Neo4j is introduced in V1 only after hybrid RAG is stable.

---

# 1. Production-Ready Open-Source-First Tech Stack

## 1.1 Recommended Stack: MVP + V1

The recommended architecture is a layered, open-source-first stack where the MVP is built around hybrid RAG and V1 extends the platform with temporal knowledge graph capabilities.

### MVP Core

- **LangGraph** as the primary orchestration layer.
- **PostgreSQL + pgvector** as the primary vector database, consolidated with the registry, metadata, and audit data in a single Postgres engine.
- **OpenSearch** for BM25 keyword retrieval.
- **BGE-M3** for embeddings.
- **BGE-Reranker-Large** for precision improvement.
- **Claude Sonnet API** for high-quality grounded generation.
- **FastAPI** as the backend API layer.
- **Next.js 15** as the frontend layer.
- **Langfuse** for tracing and observability.
- **RAGAS + Vectara HHEM** for quality and faithfulness evaluation.

### V1 Extension

- **Graphiti + Neo4j** for temporal, entity-centric, and cross-guidance reasoning.
- Graphiti should be introduced as a retrieval enhancement, not as a replacement for the PostgreSQL/pgvector + OpenSearch hybrid retrieval.
- LangGraph should route to Graphiti only when the query requires relationship, timeline, or cross-document reasoning.

## 1.2 Figure 1: Recommended Layered Architecture

The architecture represented in Figure 1 should be interpreted as a layered stack:

Refer the [Architecture_and_Workflow.md](./Architecture_and_Workflow.md) for mermaid diagram.

```text
┌──────────────────────────────────────────────────────────────┐
│                        Frontend Layer                        │
│          Next.js 15 + shadcn/ui + Streaming UI               │ 
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                          API Layer                           │
│                 FastAPI + Pydantic + SSE                     │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                       │
│                         LangGraph                            │
│      Query understanding, routing, retry, guardrails         │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                      Retrieval Layer                         │
│     pgvector dense search + OpenSearch BM25 + RRF + reranker │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                   Knowledge Graph Layer, V1                  │
│                    Graphiti + Neo4j                          │
│       Temporal facts, document relationships, entity graph   │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                  Ingestion and Evaluation Layer              │
│ PyMuPDF, Unstructured, BGE-M3, Langfuse, RAGAS, HHEM         │
└──────────────────────────────────────────────────────────────┘
```

### Layer-by-Layer Choices

| Layer | Component | Final Choice | Reason |
|------|-----------|--------------|--------|
| Language / Runtime | Python | Python 3.11 | Best fit for LangGraph, LlamaIndex, Graphiti, RAGAS, and AI tooling. |
| Orchestration | Agent workflow | LangGraph | Supports stateful nodes, conditional edges, checkpointing, streaming, and retry logic. |
| Retrieval primitives | Connectors and chunking | LlamaIndex inside LangGraph nodes | Useful for ingestion, parent-child chunking, and retriever utilities without becoming the top-level orchestrator. |
| Vector DB | Dense retrieval | PostgreSQL + pgvector | Consolidates vectors with relational/registry/audit data in one engine; fewer moving parts for a solo founder; strong filtered search. |
| Keyword search | Sparse retrieval | OpenSearch | Improves FDA term matching, exact phrase lookup, CFR references, and metadata filtering. |
| Knowledge graph | Graph retrieval | Graphiti + Neo4j | V1-only enhancement for temporal and relationship reasoning. |
| Embeddings | Dense embedding model | BGE-M3 | Strong multilingual and long-context retrieval performance; self-hostable. |
| Reranker | Cross-encoder | BGE-Reranker-Large | Improves top-k precision before generation. |
| LLM | Hosted model | Claude Sonnet API | Recommended MVP model for grounded answer quality and citation-oriented generation. |
| On-prem fallback | Local model serving | Llama 3.3 70B or Qwen via vLLM | Supports customers that require local or private deployment. |
| PDF ingestion | Parsing | PyMuPDF + Unstructured | Preserves text, structure, sections, and tables from FDA PDFs. |
| API | Backend | FastAPI | Async, typed, Python-native API layer. |
| Frontend | UI | Next.js 15 + shadcn/ui | Fast product iteration and good streaming UX. |
| Auth | Identity | Supabase or Clerk | Solo-founder friendly identity and RBAC shortcut. |
| Observability | Tracing | Langfuse | LLM tracing, LangGraph spans, prompt and output inspection. |
| Evaluation | Quality | RAGAS + Vectara HHEM | Measures faithfulness, hallucination risk, and answer quality. |
| Deployment | Runtime | Docker Compose, then managed services | Single-node deployment is enough for pilots; migrate when required. |

---

# 2. LangGraph

LangGraph should be used as the top-level workflow engine because it gives the application a stateful graph model.

**Final decision:** Use LangGraph as the orchestrator and LlamaIndex as a retrieval/helper library inside LangGraph nodes.

Recommended split:

- **LangGraph:** workflow orchestration, state, conditional edges, retries, guardrails.
- **LlamaIndex:** ingestion utilities, chunking support, simple retrieval abstractions.
- **LangChain Core:** model integrations only where useful.
- **Graphiti:** V1 graph retrieval enhancement only.

## 2.1 LangGraph Node/Edge Design for FDA RAG

The LangGraph workflow should be designed as a controlled decision graph rather than a generic chatbot chain.

### Figure: LangGraph Node/Edge Design for FDA RAG

Refer the [Architecture_and_Workflow.md](./Architecture_and_Workflow.md) for mermaid diagram.

```text
User Query
   │
   ▼
┌────────────────────┐
│ 1. query_understand │
│ rewrite, classify,  │
│ extract entities    │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│ 2. retrieval_router │
│ decide hybrid only  │
│ or hybrid + graph   │
└───────┬───────┬────┘
        │       │
        │       └──────────────────────┐
        ▼                              ▼
┌────────────────────┐       ┌────────────────────┐
│ 3. hybrid_retrieve │       │ 4. graph_retrieve  │
│ pgvector + BM25 +  │       │ Graphiti, V1 only  │
│ metadata filters   │       │                    │
└─────────┬──────────┘       └─────────┬──────────┘
          │                            │
          └────────────┬───────────────┘
                       ▼
             ┌────────────────────┐
             │ 5. merge_rerank     │
             │ BGE cross-encoder   │
             └─────────┬──────────┘
                       ▼
             ┌────────────────────┐
             │ 6. confidence_check │
             │ low confidence?     │
             └───────┬───────┬────┘
                     Yes      No
                      │       │
                      ▼       ▼
       ┌──────────────────┐  ┌────────────────────┐
       │ refuse_response  │  │ 7. generate_answer  │
       │ cite reason      │  │ citation-first LLM  │
       └──────────────────┘  └─────────┬──────────┘
                                        ▼
                              ┌────────────────────┐
                              │ 8. citation_bind    │
                              │ evidence cards      │
                              └─────────┬──────────┘
                                        ▼
                              ┌────────────────────┐
                              │ 9. faithfulness_guard │
                              │ validate answer       │
                              └───────┬────────────┘
                                      │
                         Fail ────────┘ retry with limit
                                      │ Pass
                                      ▼
                              ┌────────────────────┐
                              │ 10. respond         │
                              │ final answer +      │
                              │ evidence payload    │
                              └────────────────────┘
```

## 2.4 The Ten Nodes You Actually Need

| # | Node | Responsibility | Key Libraries / Components |
|---|------|----------------|----------------------------|
| 1 | `query_understand` | Rewrite the user question, classify intent, and extract entities such as drug, device, CFR reference, center, guidance type, or regulatory topic. | LlamaIndex, Pydantic |
| 2 | `retrieval_router` | Decide which retrieval path to use. Hybrid retrieval should be default; graph retrieval should be used only in V1 for cross-guidance, temporal, or entity-centric queries. | LangGraph conditional edges |
| 3 | `hybrid_retrieve` | Run dense vector search, BM25 keyword search, metadata filters, and reciprocal rank fusion. | PostgreSQL + pgvector, OpenSearch, LlamaIndex |
| 4 | `graph_retrieve` | Query Graphiti for related entities, temporal facts, timelines, and cross-document relationships. This is V1 only. | Graphiti Core, Neo4j |
| 5 | `merge_rerank` | Merge retrieval results and rerank top candidates using a cross-encoder. | Sentence Transformers, BGE-Reranker |
| 6 | `confidence_check` | Validate retrieval strength and route to refusal if confidence is below threshold. | Pydantic, custom scoring |
| 7 | `generate_answer` | Generate a citation-first answer using grounded context only. | Anthropic SDK, OpenAI-compatible client |
| 8 | `citation_bind` | Attach each citation to document ID, section, passage, version hash, and source URL. | Custom evidence-card logic |
| 9 | `faithfulness_guard` | Check whether the generated answer is supported by retrieved evidence and retry if needed. | RAGAS, Vectara HHEM |
| 10 | `respond` | Return final response payload to the UI, including answer, citations, confidence, and evidence cards. | FastAPI, SSE |

---

# 5.  Retrieval Architectures for FDA

## 5.1 Pure Hybrid RAG for MVP
Ship citation-first Q&A, prove trust, sign 5–10 pilots

## 5.2 Hybrid RAG + Graphiti (with second database Neo4j) for V1 
Add Graphiti layer for cross-guidance comparison, temporal drift, and entity-centric queries. LangGraph routes to graph search only for graph-shaped questions

# 6. Final Recommendation

## 6.1 MVP Architecture: Ship This First

The MVP should be a citation-first hybrid RAG platform without Graphiti.

### MVP Components

- **Orchestration:** LangGraph using the controlled node/edge workflow.
- **Retrieval:** PostgreSQL + pgvector dense retrieval + OpenSearch BM25.
- **Reranking:** BGE-Reranker-Large for top-k precision.
- **Ingestion:** Python + PyMuPDF + Unstructured + APScheduler or Prefect.
- **LLM:** Claude Sonnet API as the primary MVP model.
- **On-prem fallback:** Llama 3.3 70B or Qwen via vLLM behind an OpenAI-compatible endpoint.
- **Embeddings:** BGE-M3 using Sentence Transformers or a text-embedding inference container.
- **UI:** Next.js 15 + shadcn/ui + Vercel AI SDK for streaming UX.
- **API:** FastAPI + Pydantic v2 + SSE for streaming responses.
- **Auth:** Supabase or Clerk.
- **Storage:** A single PostgreSQL instance for the guidance registry, metadata, dense embeddings (pgvector), users, sessions, and audit trail; S3-compatible storage for original PDFs. OpenSearch runs separately for BM25.
- **Observability:** Langfuse.
- **Evaluation:** RAGAS + Vectara HHEM + curated FDA gold set.
- **Deployment:** Single VM with Docker Compose for pilots.

### MVP Principle

Graphiti should not be included in the MVP. The first product milestone should prove that the system can deliver accurate, citation-backed FDA guidance answers with robust retrieval, reranking, and faithfulness checks.

## 6.2 Where Graphiti Belongs

Graphiti belongs in **V1, Month 6+**, after hybrid RAG is already working and trusted.

### V1 Graphiti Scope

- Deploy Neo4j Community Edition alongside PostgreSQL and OpenSearch.
- Add Graphiti as a temporal knowledge graph layer.
- Ingest each FDA guidance document as a Graphiti episode.
- Use a prescribed FDA ontology.

### Suggested FDA Ontology

#### Entity Types

- `Guidance`
- `Docket`
- `CFRReference`
- `ProductCode`
- `Center`
- `TopicArea`

#### Relationship Types

- `SUPERSEDES`
- `CITES`
- `APPLIES_TO`
- `REVISED_FROM`

### Routing Rule

The `graph_retrieve` node should be invoked only when the query is:

- Cross-guidance
- Temporal
- Entity-centric
- Relationship-based

Examples:

- "Which guidances cite 21 CFR 312.23?"
- "How did FDA guidance on real-world evidence evolve between 2019 and 2024?"
- "Which guidance superseded this draft?"

## 6.4 Migration Path: MVP to Advanced Platform

| Milestone | Additions | Purpose |
|----------|-----------|---------|
| M0-M3 PoC | LangGraph + PostgreSQL/pgvector + BGE + Azure OpenAI | Validate core FDA hybrid RAG quality. |
| M3-M6 MVP | OpenSearch, reranker, faithfulness guard, evidence cards, Langfuse | Ship citation-first product to pilot users. |
| M6-M9 V1 | Neo4j + Graphiti, `graph_retrieve` node, cross-guidance comparison | Unlock temporal and relationship reasoning. |
| M9-M15 V2 | vLLM on-prem model serving, multi-tenancy, Azure OpenAI option | Enable enterprise and regulated deployments. |
| M15+ V3 | Fine-tuned embeddings, DSPy prompt optimization, multi-hop agent workflows | Improve accuracy and differentiated intelligence. |

---

# 7. Implementation Blueprint

## 7.1 Repository Structure

```text
fda-regulatory-copilot/
├── pyproject.toml
├── docker-compose.yml       # PostgreSQL (pgvector), OpenSearch, Neo4j (V1), Langfuse, App
├── .env.example
├── README.md
│
├── apps/
│   ├── api/                 # FastAPI app
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── chat.py
│   │   │   ├── search.py
│   │   │   ├── documents.py
│   │   │   └── health.py
│   │   ├── schemas/         # Pydantic v2 models (Answer, EvidenceCard, ...)
│   │   ├── deps.py          # DI: LLM, embedder, pgvector, opensearch, graphiti
│   │   └── settings.py      # Pydantic Settings
│   │
│   └── web/                 # Next.js 15 + shadcn/ui (optional at MVP)
│
├── src/
│   ├── ingestion/
│   │   ├── fda_scraper.py       # Guidance-search page + PDF URLs
│   │   ├── pdf_parser.py         # pymupdf + unstructured wrapper
│   │   ├── metadata_extractor.py # docket, center, topic, status, dates
│   │   ├── chunking.py           # parent-child (section→paragraph)
│   │   ├── embedder.py           # BGE-M3 client
│   │   ├── version_tracker.py    # SHA-256 content hash + supersedes graph
│   │   └── pipeline.py           # Prefect/APScheduler flow
│   │
│   ├── retrieval/
│   │   ├── pgvector_client.py
│   │   ├── opensearch_client.py
│   │   ├── hybrid.py             # Reciprocal Rank Fusion
│   │   ├── reranker.py           # BGE-Reranker cross-encoder
│   │   └── filters.py            # center, date, status filters
│   │
│   ├── graph/                    # V1
│   │   ├── graphiti_client.py    # wraps graphiti-core
│   │   ├── ontology.py           # Pydantic entity/edge types
│   │   ├── episode_builder.py    # FDA doc → Graphiti episode
│   │   └── graph_search.py       # search + get_related + timeline
│   │
│   ├── llm/
│   │   ├── router.py             # Claude vs Llama vs Azure OpenAI
│   │   ├── prompts.py            # citation-first templates
│   │   └── streaming.py
│   │
│   ├── agents/
│   │   ├── state.py              # LangGraph typed state
│   │   ├── nodes.py              # 10 nodes from Section 2.4
│   │   ├── edges.py              # conditional routing logic
│   │   ├── guardrails.py         # HHEM + confidence check
│   │   ├── citation.py           # bind [n] → EvidenceCard
│   │   └── graph.py              # StateGraph builder
│   │
│   ├── eval/
│   │   ├── golden_set.json       # 200 curated FDA Q&A
│   │   ├── ragas_eval.py
│   │   └── hhem_check.py
│   │
│   └── common/
│       ├── logging.py
│       ├── telemetry.py          # Langfuse tracing
│       └── errors.py
│
├── data/
│   ├── raw_pdfs/                 # S3/MinIO in prod
│   ├── parsed/                   # cached parsed docs
│   └── snapshots/                # daily version snapshots
│
├── infra/
│   ├── docker/
│   │   ├── postgres.Dockerfile
│   │   ├── opensearch.Dockerfile
│   │   ├── neo4j.Dockerfile      #v1
│   │   └── app.Dockerfile
│   └── k8s/                      #later
│
└── tests/
    ├── unit/
    ├── integration/
    └── eval/                     # nightly quality regression
```

## 7.2 Minimal Viable Pipeline: Step-by-Step Data Flow

| Step | Component | What Happens |
|-----|-----------|--------------|
| 1 | `fda_scraper.py` | Daily crawl of FDA guidance pages and discovery of new or updated documents. |
| 2 | `fda_scraper.py` | Download PDF and landing HTML, then store raw files with SHA-256 hash. |
| 3 | `pdf_parser.py` | Parse PDF text and structure using PyMuPDF and extract tables using Unstructured. |
| 4 | `metadata_extractor.py` | Extract document metadata such as title, center, topic, status, issue date, docket, and source URL. |
| 5 | `version_tracker.py` | Detect new versions or content changes and record document snapshots. |
| 6 | `chunking.py` | Create parent-child chunks, where parent is section-level and child is paragraph-level. |
| 7 | `embedder.py` | Generate BGE-M3 dense embeddings for child chunks. |
| 8 | `pgvector_client.py` and `opensearch_client.py` | Index vectors in PostgreSQL (pgvector) and BM25 content in OpenSearch with metadata filters. |
| 9 | `episode_builder.py`, V1 | Convert FDA guidance documents into Graphiti episodes and extract domain entities and relationships. |
| 10 | `agents/graph.py` | Execute LangGraph workflow from query understanding to final citation-bound response. |
| 11 | `telemetry.py` | Capture Langfuse traces and run nightly evaluation regression on the gold set. |

## 7.3 Reference Docker Compose: MVP

```yaml
services:
  api:
    build: ./apps/api
    depends_on:
      - postgres
      - opensearch
      - langfuse
    env_file: .env
    ports:
      - "8000:8000"

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=fda
      - POSTGRES_PASSWORD=fda
      - POSTGRES_DB=fda_copilot
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  opensearch:
    image: opensearchproject/opensearch:2
    environment:
      - discovery.type=single-node
      - plugins.security.disabled=true
    volumes:
      - os_data:/usr/share/opensearch/data
    ports:
      - "9200:9200"

  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"

  # V1 addition: uncomment when adding Graphiti
  # neo4j:
  #   image: neo4j:5.26-community
  #   environment:
  #     - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
  #   volumes:
  #     - neo4j_data:/data
  #   ports:
  #     - "7474:7474"
  #     - "7687:7687"

volumes:
  postgres_data:
  os_data:
  # neo4j_data:
```

## 7.4 Reference Python Dependencies

```text
# Orchestration
langgraph>=0.2.60
langchain-core>=0.3
langchain-anthropic>=0.3
langchain-openai>=0.3

# Retrieval primitives
llama-index-core>=0.12
llama-index-vector-stores-postgres>=0.4
llama-index-embeddings-huggingface>=0.4

# Vector and keyword retrieval
pgvector>=0.3
asyncpg>=0.29
opensearch-py>=2.7

# Embeddings and reranking
sentence-transformers>=3.2

# Ingestion
pymupdf>=1.24
unstructured[pdf]>=0.15
beautifulsoup4>=4.12
httpx>=0.27
prefect>=3.0
apscheduler>=3.10

# API
fastapi>=0.115
uvicorn[standard]>=0.32
pydantic>=2.9
pydantic-settings>=2.6
sse-starlette>=2.1

# Auth and storage
supabase>=2.9
boto3>=1.35
psycopg[binary]>=3.2

# Observability and evaluation
langfuse>=2.50
ragas>=0.2
opentelemetry-sdk>=1.27

# V1 additions
graphiti-core>=0.29
neo4j>=5.26
```

## 7.5 First Working Prototype: Two Weeks Solo

| Day | Deliverable |
|-----|-------------|
| 1-2 | Repo scaffold, Docker Compose, PostgreSQL (pgvector), OpenSearch, and FastAPI hello-world. |
| 3-4 | FDA scraper for sample guidance documents, PDF parsing, and metadata extraction. |
| 5-6 | Parent-child chunking, BGE-M3 embeddings, and pgvector indexing. |
| 7 | BM25 index in OpenSearch and hybrid reciprocal-rank fusion. |
| 8 | BGE-Reranker top-20 to top-5 reranking. |
| 9-10 | LangGraph 5-node workflow: understand, retrieve, rerank, confidence, answer. |
| 11 | Evidence Card schema and citation binding. |
| 12 | Faithfulness guardrail node and retry edge. |
| 13 | Langfuse tracing, 30-question gold set, and RAGAS evaluation. |
| 14 | Streaming UI with pilot validation flow. |

### Two-Week Prototype End State

By the end of the first two weeks, the project should have a working prototype that can:

- Ingest a controlled set of FDA guidance documents.
- Parse and chunk guidance content.
- Retrieve relevant passages using hybrid retrieval.
- Rerank evidence before generation.
- Generate citation-first answers.
- Refuse low-confidence answers.
- Validate answer faithfulness.
- Stream responses to a basic UI.
- Capture traces and evaluation outputs.

---

# Final Bottom Line

For the AI-powered FDA Regulatory Intelligence Platform, the best practical decision is:

> **Build the MVP with LangGraph + PostgreSQL/pgvector + OpenSearch + BGE-M3 + BGE-Reranker + Azure OpenAI. Add Graphiti + Neo4j in V1 only after the citation-first hybrid RAG product is stable.**

This gives the fastest path to a trustworthy MVP while preserving a clear upgrade path toward differentiated temporal and cross-guidance reasoning.

> **The One Non Negotiable** Every answer must ship with a verifiable citation from day one.
This is your only real moat against Veeva, Cortellis, and every ChatGPT wrapper. Guard it with a faithfulness check and a refuse-on-low-confidence node - even in the MVP.

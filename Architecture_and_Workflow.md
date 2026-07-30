# Architeture diagram

## Layered Architecture diagram
```mermaid
flowchart TB

    %% Layer 1
    subgraph L1["Presentation Layer"]
        UI["Next.js 15 + React<br/>shadcn/ui<br/>Streaming Chat UI"]
    end

    %% Layer 2
    subgraph L2["API Layer"]
        API["FastAPI<br/>Pydantic v2<br/>SSE Streaming"]
    end

    %% Layer 3
    subgraph L3["AI Orchestration Layer"]
        LG["LangGraph<br/>State Management<br/>Conditional Routing<br/>Retries & Guardrails"]
    end

    %% Layer 4
    subgraph L4["Hybrid Retrieval Layer (MVP Core)"]
        QD["PostgreSQL + pgvector<br/>Dense Vector Search"]
        OS["OpenSearch<br/>BM25 Search"]
        RRF["Reciprocal Rank Fusion"]
        RR["BGE-Reranker-Large"]
    end

    %% Layer 5
    subgraph L5["Knowledge Layer"]
        EMB["BGE-M3 Embeddings"]
        LLM["Claude Sonnet API"]
        OSSLLM["Llama 3.3 / Qwen via vLLM<br/>On-Prem Fallback"]
    end

    %% Layer 6
    subgraph L6["Data Processing & Ingestion Layer"]
        PDF["PyMuPDF + Unstructured"]
        META["Metadata Extraction<br/>Version Tracking"]
        PIPE["FDA Ingestion Pipeline"]
    end

    %% Layer 7
    subgraph L7["Platform Services"]
        OBS["Langfuse Observability"]
        EVAL["RAGAS + Vectara HHEM"]
        AUTH["Supabase Auth"]
        STORE["PostgreSQL + Object Storage"]
    end

    %% V1 Layer
    subgraph V1["V1 Enhancement (Optional)"]
        GRAPH["Graphiti + Neo4j<br/>Temporal Knowledge Graph<br/>Cross-Guidance Reasoning"]
    end

    UI --> API
    API --> LG

    LG --> QD
    LG --> OS

    QD --> RRF
    OS --> RRF

    RRF --> RR

    RR --> LLM
    RR --> OSSLLM

    PIPE --> PDF
    PDF --> META
    META --> EMB

    EMB --> QD

    LG --> OBS
    LG --> EVAL
    API --> AUTH
    API --> STORE

    LG -. Graph Queries .-> GRAPH
    GRAPH -. Graph Results .-> LG

    classDef mvp fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px;
    classDef platform fill:#E3F2FD,stroke:#1565C0,stroke-width:2px;
    classDef v1 fill:#FFFFFF,stroke:#8E24AA,stroke-width:2px,stroke-dasharray: 8 4;

    class UI,API,LG,QD,OS,RRF,RR,EMB,LLM,OSSLLM,PDF,META,PIPE mvp;
    class OBS,EVAL,AUTH,STORE platform;
    class GRAPH v1;
```
---
# Figure 2: LangGraph Node/Edge Design for the FDA Regulatory RAG Workflow

**Description:** LangGraph node/edge design for the FDA regulatory RAG workflow, including a retrieval router (hybrid + Graphiti + metadata), reranking, a faithfulness guardrail, and a refuse-on-low-confidence path. Solid green boxes represent MVP components; dashed purple components represent the V1 Graphiti + Neo4j knowledge graph enhancement, introduced after the hybrid RAG core is stable.

---

## Diagram

```mermaid
flowchart TD

    %% =========================
    %% User Entry
    %% =========================
    UQ["User Query<br/>FDA regulatory question"]

    %% =========================
    %% LangGraph Core Workflow
    %% =========================
    subgraph LG["LangGraph FDA RAG Workflow"]
        QN["1. query_understand<br/>Rewrite query<br/>Extract entities<br/>Classify intent"]

        RR["2. retrieval_router<br/>Route by intent<br/>Hybrid / Graphiti / Metadata"]

        HR["3. hybrid_retrieve<br/>pgvector dense search<br/>OpenSearch BM25<br/>Reciprocal Rank Fusion"]

        MF["metadata_filter<br/>Center<br/>Guidance status<br/>Date range<br/>Docket / CFR / product code"]

        GR["4. graph_retrieve, V1<br/>Graphiti + Neo4j<br/>Temporal facts<br/>Entity relationships<br/>Cross-guidance links"]

        MR["5. merge_rerank<br/>Merge candidates<br/>BGE-Reranker-Large<br/>Top-k evidence selection"]

        CC{"6. confidence_check<br/>Is evidence confidence<br/>above threshold?"}

        REF["refuse_response<br/>Low confidence<br/>Ask for clarification<br/>Do not hallucinate"]

        GA["7. generate_answer<br/>Citation-first prompt<br/>Grounded LLM response"]

        CB["8. citation_bind<br/>Attach Evidence Cards<br/>doc_id, section, passage<br/>version_hash, source_url"]

        FG{"9. faithfulness_guard<br/>Is answer supported<br/>by retrieved evidence?"}

        RETRY{"Retry limit<br/>reached?"}

        RESP["10. respond<br/>Final answer<br/>Citations<br/>Evidence cards<br/>Confidence metadata"]
    end

    %% =========================
    %% Data / Retrieval Stores
    %% =========================
    subgraph STORE["Retrieval and Knowledge Stores"]
        QD["PostgreSQL + pgvector<br/>Dense vector index"]
        OS["OpenSearch<br/>BM25 keyword index"]
        PG["PostgreSQL (same instance)<br/>Document metadata<br/>Sessions<br/>Audit trail"]
        GDB["Neo4j<br/>Graphiti temporal KG, V1"]
    end

    %% =========================
    %% Quality / Observability
    %% =========================
    subgraph QUALITY["Quality and Observability"]
        LF["Langfuse<br/>Tracing and prompt observability"]
        EV["RAGAS + Vectara HHEM<br/>Faithfulness and hallucination checks"]
    end

    %% =========================
    %% Color Legend
    %% =========================
    subgraph LEGEND["Color Legend"]
        direction TB
        L1["MVP Workflow Node"]
        L2["Decision / Guardrail Node"]
        L3["Refuse-on-Low-Confidence Path"]
        L4["Retrieval / Knowledge Store"]
        L5["Quality & Observability"]
        L6["V1 Enhancement (Graphiti + Neo4j)"]
    end

    %% =========================
    %% Main Flow
    %% =========================
    UQ --> QN
    QN --> RR

    %% Router Paths
    RR -->|"Default FDA Q&A"| HR
    RR -->|"Metadata-constrained query"| MF
    RR -.->|"V1: cross-guidance / temporal / entity-centric"| GR

    %% Retrieval Store Connections
    HR --> QD
    HR --> OS
    MF --> PG
    GR -.-> GDB

    %% Return Retrieval Results
    QD --> HR
    OS --> HR
    PG --> MF
    GDB -.-> GR

    HR --> MR
    MF --> MR
    GR -.-> MR

    %% Confidence Path
    MR --> CC
    CC -->|"No"| REF
    CC -->|"Yes"| GA

    %% Generation and Validation
    GA --> CB
    CB --> FG

    FG -->|"Pass"| RESP
    FG -->|"Fail"| RETRY
    RETRY -->|"No, retry retrieval or generation"| RR
    RETRY -->|"Yes"| REF

    %% Observability and Evaluation
    QN --> LF
    RR --> LF
    HR --> LF
    GR -.-> LF
    MR --> LF
    GA --> LF
    FG --> EV
    EV --> LF

    %% =========================
    %% Styling
    %% =========================
    classDef mvp fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#000;
    classDef decision fill:#FFF8E1,stroke:#F9A825,stroke-width:2px,color:#000;
    classDef refuse fill:#FFEBEE,stroke:#C62828,stroke-width:2px,color:#000;
    classDef store fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#000;
    classDef quality fill:#F3E5F5,stroke:#6A1B9A,stroke-width:2px,color:#000;
    classDef v1 fill:#FFFFFF,stroke:#8E24AA,stroke-width:2px,stroke-dasharray:8 4,color:#000;
    classDef legendbox fill:#FAFAFA,stroke:#9E9E9E,stroke-width:1px,color:#000;

    %% Workflow Node Classes
    class UQ,QN,RR,HR,MF,MR,GA,CB,RESP mvp;
    class CC,FG,RETRY decision;
    class REF refuse;
    class QD,OS,PG store;
    class LF,EV quality;
    class GR,GDB v1;

    %% Legend Node Classes
    class L1 mvp;
    class L2 decision;
    class L3 refuse;
    class L4 store;
    class L5 quality;
    class L6 v1;
    class LEGEND legendbox;
```

---

## Legend Reference

- **Green (solid):** MVP workflow nodes — the core citation-first hybrid RAG flow.
- **Amber (diamond):** Decision and guardrail nodes — confidence check, faithfulness guard, and retry logic.
- **Red:** Refuse-on-low-confidence path — the safety exit that prevents hallucinated answers.
- **Blue:** Retrieval and knowledge stores — PostgreSQL + pgvector and OpenSearch.
- **Purple (solid):** Quality and observability — Langfuse tracing plus RAGAS and Vectara HHEM evaluation.
- **Purple (dashed):** V1 enhancement — Graphiti and Neo4j temporal knowledge graph, added after the MVP is stable.

---

## The Ten Nodes

| # | Node | Responsibility | Key Libraries / Components |
|---|------|----------------|----------------------------|
| 1 | `query_understand` | Rewrite the question, classify intent, extract entities (drug, device, CFR, center, guidance type). | LlamaIndex, Pydantic |
| 2 | `retrieval_router` | Decide retrieval path. Hybrid by default; graph only for cross-guidance, temporal, or entity-centric queries (V1). | LangGraph conditional edges |
| 3 | `hybrid_retrieve` | Dense vector search, BM25 keyword search, metadata filters, and reciprocal rank fusion. | PostgreSQL + pgvector, OpenSearch, LlamaIndex |
| 4 | `graph_retrieve` | Query Graphiti for related entities, temporal facts, timelines, and cross-document relationships (V1 only). | Graphiti Core, Neo4j |
| 5 | `merge_rerank` | Merge candidates and rerank top results using a cross-encoder. | Sentence Transformers, BGE-Reranker |
| 6 | `confidence_check` | Validate retrieval strength; route to refusal if below threshold. | Pydantic, custom scoring |
| 7 | `generate_answer` | Generate a citation-first answer using grounded context only. | Anthropic SDK / OpenAI-compatible client |
| 8 | `citation_bind` | Attach each citation to doc ID, section, passage, version hash, and source URL. | Custom evidence-card logic |
| 9 | `faithfulness_guard` | Check whether the answer is supported by retrieved evidence; retry if needed. | RAGAS, Vectara HHEM |
| 10 | `respond` | Return final payload: answer, citations, confidence, and evidence cards. | FastAPI, SSE |

"""Hybrid retrieval: PostgreSQL + pgvector, OpenSearch, fusion, and reranking."""

from src.retrieval.client import RetrievalError, hybrid_search
from src.retrieval.filters import RetrievalFilters
from src.retrieval.formatting import EvidenceFormattingError
from src.retrieval.hybrid import reciprocal_rank_fusion
from src.retrieval.models import HybridSearchResult, RetrievalCandidate
from src.retrieval.opensearch_client import search_keyword_chunks
from src.retrieval.pgvector_client import search_dense_chunks
from src.retrieval.query_embedding import embed_query
from src.retrieval.reranker import rerank_results

__all__ = [
	"EvidenceFormattingError",
	"HybridSearchResult",
	"RetrievalCandidate",
	"RetrievalError",
	"RetrievalFilters",
	"embed_query",
	"hybrid_search",
	"reciprocal_rank_fusion",
	"rerank_results",
	"search_dense_chunks",
	"search_keyword_chunks",
]

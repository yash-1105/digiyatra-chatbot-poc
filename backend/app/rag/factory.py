"""Construct embedders/retrievers from settings and the index metadata."""

from __future__ import annotations

import logging

from app.config import Settings
from app.rag.embeddings import Embedder, LexicalEmbedder, SarvamEmbedder
from app.rag.retriever import Retriever
from app.rag.store import KnowledgeIndex

log = logging.getLogger(__name__)


def sarvam_embedder(settings: Settings) -> SarvamEmbedder | None:
    if not settings.sarvam_configured:
        return None
    assert settings.sarvam_api_key is not None
    return SarvamEmbedder(
        settings.sarvam_api_key.get_secret_value(), settings.sarvam_base_url, settings.sarvam_embedding_model
    )


def choose_index_embedder(settings: Settings) -> tuple[Embedder, str]:
    """Pick the embedder for (re)building the index. Returns (embedder, reason)."""
    if settings.embedding_provider == "lexical":
        return LexicalEmbedder(), "EMBEDDING_PROVIDER=lexical"
    emb = sarvam_embedder(settings)
    if emb is None:
        if settings.embedding_provider == "sarvam":
            raise RuntimeError("EMBEDDING_PROVIDER=sarvam but SARVAM_API_KEY is not set.")
        return LexicalEmbedder(), "SARVAM_API_KEY not set; using lexical fallback"
    ok, detail = emb.probe()
    if ok:
        return emb, f"Sarvam {settings.sarvam_embedding_model} available: {detail}"
    if settings.embedding_provider == "sarvam":
        raise RuntimeError(f"Sarvam embeddings unavailable: {detail}")
    return LexicalEmbedder(), f"Sarvam {settings.sarvam_embedding_model} unavailable ({detail}); using lexical fallback"


def query_embedder(index: KnowledgeIndex, settings: Settings) -> Embedder:
    """The query embedder MUST match the one that built the index."""
    lexical = index.load_embedder()
    if lexical is not None:
        return lexical
    emb = sarvam_embedder(settings)
    if emb is None:
        raise RuntimeError("Index was built with Sarvam embeddings but SARVAM_API_KEY is not set; reindex or set the key.")
    return emb


def build_retriever(settings: Settings, index: KnowledgeIndex | None = None) -> Retriever:
    index = index or KnowledgeIndex(settings.index_dir, settings.index_table)
    return Retriever(
        index,
        query_embedder(index, settings),
        candidates=settings.retrieval_candidates,
        vector_weight=settings.retrieval_vector_weight,
        min_score=settings.retrieval_min_score,
        max_per_source=settings.retrieval_max_per_source,
    )

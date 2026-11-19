"""LanceDB index lifecycle: build, upsert, delete, reindex, filtering, citation lookup."""

from __future__ import annotations

import copy

import pytest

from app.rag.embeddings import LexicalEmbedder
from app.rag.store import KnowledgeIndex


def test_build_counts(index, chunks):
    meta = index.meta()
    assert meta["chunk_count"] == len(chunks) == 119
    assert meta["document_count"] == 26
    assert meta["approval_statuses"] == ["approved"]
    assert meta["embedder"]["kind"] == "lexical" and meta["embedder"]["neural"] is False


def test_citation_lookup(index, chunks):
    c = chunks[5]
    row = index.get_chunk(c["chunk_id"])
    assert row["source_file"] == c["source_file"] and row["text"] == c["text"]
    assert index.get_chunk("does-not-exist") is None


def test_vector_search_scores_and_filter(index):
    emb = index.load_embedder()
    rows = index.vector_search(emb.embed_query("Which airports support Digi Yatra?"), 5)
    assert "available_airports.md" in [r["source_file"] for r in rows[:4]]
    assert all(0.0 <= r["vector_score"] <= 1.0 for r in rows)
    assert rows == sorted(rows, key=lambda r: r["vector_score"], reverse=True)


def test_refuses_non_approved_chunks(tmp_path, chunks):
    bad = copy.deepcopy(chunks[:2])
    bad[1]["approval_status"] = "draft"
    with pytest.raises(ValueError):
        KnowledgeIndex(tmp_path).build(bad, LexicalEmbedder())


def test_upsert_delete_and_reindex_single_document(tmp_path, chunks):
    idx = KnowledgeIndex(tmp_path / "db")
    emb = LexicalEmbedder()
    idx.build(chunks, emb)
    total = idx.meta()["chunk_count"]
    target = "support_04_general_information.md"
    own = [c for c in chunks if c["source_file"] == target]

    removed = idx.delete_source(target, emb)
    assert removed == len(own) and idx.meta()["chunk_count"] == total - len(own)
    assert target not in idx.meta()["documents"]

    idx.upsert(own, emb)
    assert idx.meta()["chunk_count"] == total

    # Updating an existing chunk in place (same chunk_id) does not duplicate it.
    changed = copy.deepcopy(own[0])
    changed["text"] = changed["text"] + " (updated)"
    idx.upsert([changed], emb)
    assert idx.meta()["chunk_count"] == total
    assert idx.get_chunk(changed["chunk_id"])["text"].endswith("(updated)")

    # replace_source = delete + upsert for one document
    assert idx.replace_source(target, own[:1], emb) == 1
    assert idx.meta()["chunk_count"] == total - len(own) + 1

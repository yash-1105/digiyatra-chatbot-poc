"""The deployment corpus is the only knowledge shipped to production."""

from __future__ import annotations

import json

import pytest

from ingestion.corpus import corpus_hash, load_corpus
from tests.conftest import DEPLOY, HAS_RAW


def test_deploy_corpus_is_valid_and_approved_only():
    chunks, meta = load_corpus(DEPLOY)
    assert len(chunks) == meta["chunk_count"] == 119 and meta["document_count"] == 26
    assert all(c["approval_status"] == "approved" for c in chunks)
    assert meta["approval"]["content_owner_signoff"] == "PENDING"
    assert "FAQ_DY-IPT_Draft_26102026 1.docx" in meta["excluded_documents"]
    text = (DEPLOY / "chunks.jsonl").read_text()
    for banned in ("DY-IPT", "ePassport", "AI Impact Summit", "Schengen", "Khadakbhavi", "15.52 million"):
        assert banned not in text


def test_tampered_corpus_is_refused(tmp_path):
    d = tmp_path / "deploy"
    d.mkdir()
    (d / "corpus.json").write_text((DEPLOY / "corpus.json").read_text())
    (d / "chunks.jsonl").write_text((DEPLOY / "chunks.jsonl").read_text().replace("voluntary", "mandatory", 1))
    with pytest.raises(ValueError, match="hash mismatch"):
        load_corpus(d)


def test_non_approved_chunk_refused(tmp_path):
    d = tmp_path / "deploy"
    d.mkdir()
    line = json.loads((DEPLOY / "chunks.jsonl").read_text().splitlines()[0]) | {"approval_status": "draft"}
    (d / "chunks.jsonl").write_text(json.dumps(line) + "\n")
    (d / "corpus.json").write_text(json.dumps({"corpus_sha256": corpus_hash(d / "chunks.jsonl"), "chunk_count": 1}))
    with pytest.raises(ValueError, match="non-approved"):
        load_corpus(d)


@pytest.mark.skipif(not HAS_RAW, reason="needs knowledge/raw")
def test_export_is_deterministic(tmp_path, pipeline):
    from ingestion.corpus import export_corpus
    from tests.conftest import MANIFEST

    a = export_corpus(pipeline[0], MANIFEST, tmp_path / "a")
    b = export_corpus(pipeline[0], MANIFEST, tmp_path / "b")
    assert a["corpus_sha256"] == b["corpus_sha256"] == load_corpus(DEPLOY)[1]["corpus_sha256"]


def test_ensure_index_rebuilds_missing_index_and_keeps_valid_one(tmp_path, capsys):
    from app.cli import cmd_ensure_index
    from app.config import Settings

    s = Settings(_env_file=None, index_dir=tmp_path / "idx", embedding_provider="lexical", knowledge_corpus_dir=DEPLOY)
    assert cmd_ensure_index(s) == 0 and "Rebuilding index (index missing)" in capsys.readouterr().out
    assert cmd_ensure_index(s) == 0 and "no rebuild" in capsys.readouterr().out
    import shutil

    shutil.rmtree(tmp_path / "idx")  # ephemeral storage wiped on redeploy
    assert cmd_ensure_index(s) == 0 and "Rebuilding index" in capsys.readouterr().out

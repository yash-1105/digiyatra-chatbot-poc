"""Deployment knowledge corpus (knowledge/deploy/).

The ONLY knowledge artefact that is shipped to production:
    chunks.jsonl   approved, sanitised retrieval chunks (byte-for-byte deterministic for the same input)
    corpus.json    provenance: counts, per-document hashes, approval status, conflict guidance, corpus hash

Never ship knowledge/raw (originals incl. drafts and document metadata) or knowledge/curated
(review artefacts that also contain sanitised records of UNAPPROVED files).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from ingestion.manifest import load_manifest
from ingestion.pipeline import IngestionResult

CHUNKS = "chunks.jsonl"
CORPUS = "corpus.json"


def corpus_hash(chunks_path: Path) -> str:
    return hashlib.sha256(chunks_path.read_bytes()).hexdigest()


def export_corpus(result: IngestionResult, manifest_path: Path, out_dir: Path) -> dict:
    chunks = sorted((c.to_dict() for c in result.chunks), key=lambda c: (c["order"], c["chunk_id"]))
    if any(c["approval_status"] != "approved" for c in chunks):
        raise ValueError("Deployment corpus may only contain approved chunks.")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / CHUNKS
    path.write_text("".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in chunks), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    per_doc = Counter(c["source_file"] for c in chunks)
    info = {
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "corpus_sha256": corpus_hash(path),
        "chunk_count": len(chunks),
        "document_count": len(per_doc),
        "approval": {
            "authority": manifest.approval_authority,
            "content_owner_signoff": "PENDING",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
        "documents": [
            {"source_file": f.file, "source_sha256": f.sha256, "chunks": per_doc[f.file], "category": f.category}
            for f in result.files
            if f.status == "approved"
        ],
        "excluded_documents": sorted(f.file for f in result.files if f.status != "approved"),
        "conflicts": [{"id": c.id, "topic": c.topic, "guidance": c.guidance} for c in manifest.conflicts],
    }
    (out_dir / CORPUS).write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return info


def load_corpus(corpus_dir: Path) -> tuple[list[dict], dict]:
    path, meta_path = corpus_dir / CHUNKS, corpus_dir / CORPUS
    if not path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Deployment corpus not found in {corpus_dir}. Run `python -m app.cli ingest`.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if corpus_hash(path) != meta["corpus_sha256"]:
        raise ValueError("Deployment corpus is corrupted or was edited by hand (hash mismatch). Re-run ingest.")
    chunks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(c.get("approval_status") != "approved" for c in chunks):
        raise ValueError("Deployment corpus contains non-approved chunks; refusing to use it.")
    return chunks, meta

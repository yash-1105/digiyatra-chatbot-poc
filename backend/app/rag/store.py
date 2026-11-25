"""LanceDB-backed knowledge index: build, upsert, delete, vector search, citation lookup."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from app.rag.embeddings import Embedder, LexicalEmbedder

log = logging.getLogger(__name__)

META_FILE = "index_meta.json"
LEXICAL_FILE = "lexical_idf.json"

_STR_FIELDS = [
    "chunk_id", "record_id", "source_file", "doc_title", "section", "record_type", "question", "text",
    "embed_text", "approval_status", "category", "as_of", "verification_status", "content_hash",
    # Official-source records (optional for corpus chunks): applicability window and language.
    "effective_from", "expires_on", "language",
]


def _schema(dim: int) -> pa.Schema:
    return pa.schema(
        [pa.field(f, pa.string()) for f in _STR_FIELDS]
        + [
            pa.field("time_sensitive", pa.bool_()),
            pa.field("conflict_ids", pa.list_(pa.string())),
            pa.field("urls", pa.list_(pa.string())),
            pa.field("order", pa.int64()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class IndexNotBuilt(RuntimeError):
    pass


class KnowledgeIndex:
    def __init__(self, index_dir: Path, table_name: str = "knowledge_chunks") -> None:
        self.index_dir = index_dir
        self.table_name = table_name
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(index_dir))

    # ---------------------------------------------------------------- meta
    @property
    def meta_path(self) -> Path:
        return self.index_dir / META_FILE

    def meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            raise IndexNotBuilt("Knowledge index has not been built. Run `python -m app.cli reindex`.")
        return json.loads(self.meta_path.read_text())

    def exists(self) -> bool:
        return self.meta_path.exists() and self.table_name in self._db.list_tables().tables

    def load_embedder(self) -> Embedder | None:
        """Lexical embedders are fully restorable from disk; neural ones need an API client (caller builds)."""
        meta = self.meta()
        if meta["embedder"]["kind"] == "lexical":
            return LexicalEmbedder.load(self.index_dir / LEXICAL_FILE)
        return None

    def _write_meta(self, embedder: Embedder, extra: dict | None = None) -> None:
        tbl = self._db.open_table(self.table_name)
        rows = tbl.to_arrow().select(["source_file", "approval_status"]).to_pylist()
        meta = {
            "embedder": embedder.describe(),
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "chunk_count": len(rows),
            "document_count": len({r["source_file"] for r in rows}),
            "documents": sorted({r["source_file"] for r in rows}),
            "approval_statuses": sorted({r["approval_status"] for r in rows}),
        }
        if extra:
            meta.update(extra)
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    # ------------------------------------------------------------- writing
    def _rows(self, chunks: list[dict], embedder: Embedder) -> list[dict]:
        vectors = embedder.embed_documents([c["embed_text"] for c in chunks])
        rows = []
        for c, v in zip(chunks, vectors):
            row = {f: c.get(f) for f in _STR_FIELDS}
            row.update(
                time_sensitive=bool(c.get("time_sensitive")),
                conflict_ids=list(c.get("conflict_ids") or []),
                urls=list(c.get("urls") or []),
                order=int(c.get("order", 0)),
                vector=[float(x) for x in v],
            )
            rows.append(row)
        return rows

    def build(self, chunks: list[dict], embedder: Embedder, extra_meta: dict | None = None) -> int:
        """Drop and recreate the table from scratch."""
        if any(c.get("approval_status") != "approved" for c in chunks):
            raise ValueError("Refusing to index non-approved chunks.")
        if isinstance(embedder, LexicalEmbedder):
            embedder.fit([c["embed_text"] for c in chunks])
            embedder.save(self.index_dir / LEXICAL_FILE)
        rows = self._rows(chunks, embedder)
        table = pa.Table.from_pylist(rows, schema=_schema(embedder.dim))
        self._db.create_table(self.table_name, data=table, mode="overwrite")
        self._write_meta(embedder, extra_meta)
        log.info("Index built: %d chunks with %s", len(rows), embedder.describe()["name"])
        return len(rows)

    def upsert(self, chunks: list[dict], embedder: Embedder) -> int:
        """Insert or update chunks by chunk_id (lexical IDF statistics stay fixed until a full rebuild)."""
        if not chunks:
            return 0
        if any(c.get("approval_status") != "approved" for c in chunks):
            raise ValueError("Refusing to index non-approved chunks.")
        tbl = self._db.open_table(self.table_name)
        data = pa.Table.from_pylist(self._rows(chunks, embedder), schema=_schema(embedder.dim))
        tbl.merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all().execute(data)
        self._write_meta(embedder)
        return len(chunks)

    def delete_source(self, source_file: str, embedder: Embedder) -> int:
        tbl = self._db.open_table(self.table_name)
        before = tbl.count_rows()
        tbl.delete(f"source_file = {_quote(source_file)}")
        removed = before - tbl.count_rows()
        self._write_meta(embedder)
        return removed

    def replace_source(self, source_file: str, chunks: list[dict], embedder: Embedder) -> int:
        """Reindex a single document: delete its chunks, then upsert the new ones."""
        self.delete_source(source_file, embedder)
        return self.upsert([c for c in chunks if c["source_file"] == source_file], embedder)

    # ------------------------------------------------------------- reading
    def table(self):
        if not self.exists():
            raise IndexNotBuilt("Knowledge index has not been built. Run `python -m app.cli reindex`.")
        return self._db.open_table(self.table_name)

    def all_chunks(self, approved_only: bool = True) -> list[dict]:
        tbl = self.table()
        cols = [c for c in tbl.schema.names if c != "vector"]
        rows = tbl.to_arrow().select(cols).to_pylist()
        return [r for r in rows if r["approval_status"] == "approved"] if approved_only else rows

    def vector_search(self, vector: list[float], limit: int, approved_only: bool = True) -> list[dict]:
        q = self.table().search(vector).distance_type("cosine").limit(limit)
        if approved_only:
            q = q.where("approval_status = 'approved'", prefilter=True)
        rows = q.to_list()
        for r in rows:
            r.pop("vector", None)
            r["vector_score"] = max(0.0, 1.0 - float(r.pop("_distance", 1.0)))
        return rows

    def get_chunk(self, chunk_id: str) -> dict | None:
        rows = self.table().search().where(f"chunk_id = {_quote(chunk_id)}").limit(1).to_list()
        if not rows:
            return None
        rows[0].pop("vector", None)
        return rows[0]

"""Turn sanitised records into retrieval chunks."""

from __future__ import annotations

import hashlib

from ingestion.models import Chunk, Record
from ingestion.sanitize import normalise_for_hash

MAX_CHARS = 1100


def _split_paragraphs(text: str, limit: int) -> list[str]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras:
        return []
    # Very long single paragraphs get split on line boundaries.
    expanded: list[str] = []
    for p in paras:
        if len(p) <= limit:
            expanded.append(p)
            continue
        cur = ""
        for line in p.splitlines():
            if cur and len(cur) + len(line) + 1 > limit:
                expanded.append(cur)
                cur = line
            else:
                cur = f"{cur}\n{line}" if cur else line
        if cur:
            expanded.append(cur)
    out, cur = [], ""
    for p in expanded:
        if cur and len(cur) + len(p) + 2 > limit:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def chunk_record(record: Record) -> list[Chunk]:
    section = " > ".join(record.section_path)
    header = record.doc_title + (f" > {section}" if section else "")
    if record.question:
        q_budget = MAX_CHARS - len(record.question) - 10
        bodies = _split_paragraphs(record.text, max(q_budget, 400))
        texts = [f"Q: {record.question}\nA: {b}" for b in bodies]
    else:
        texts = _split_paragraphs(record.text, MAX_CHARS)

    chunks = []
    for i, text in enumerate(texts):
        norm = normalise_for_hash(text)
        content_hash = hashlib.sha256(norm.encode()).hexdigest()[:16]
        chunk_id = hashlib.sha256(f"{record.source_file}|{record.record_id}|{i}|{content_hash}".encode()).hexdigest()[:20]
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                record_id=record.record_id,
                source_file=record.source_file,
                doc_title=record.doc_title,
                section=section or record.doc_title,
                record_type=record.record_type,
                question=record.question,
                text=text,
                embed_text=f"{header}\n{text}",
                approval_status=record.approval_status,
                category=record.category,
                time_sensitive=record.time_sensitive,
                as_of=record.as_of,
                verification_status=record.verification_status,
                conflict_ids=list(record.conflict_ids),
                urls=list(record.urls),
                content_hash=content_hash,
                order=record.order * 100 + i,
            )
        )
    return chunks

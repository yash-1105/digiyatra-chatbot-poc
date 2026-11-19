"""Data structures produced by the ingestion pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

RecordType = Literal["faq", "section", "table_row", "csv_row", "note"]


@dataclass
class ParsedRecord:
    """One logical unit of knowledge extracted from a source file, before sanitisation."""

    record_type: RecordType
    section_path: list[str]
    text: str
    question: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Record:
    """A sanitised, classified knowledge record (written to curated/records.jsonl)."""

    record_id: str
    source_file: str
    doc_title: str
    section_path: list[str]
    record_type: RecordType
    question: str | None
    text: str
    approval_status: str
    category: str
    time_sensitive: bool
    time_markers: list[str]
    as_of: str | None
    verification_status: str
    conflict_ids: list[str]
    urls: list[str]
    redactions: dict[str, int]
    order: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Chunk:
    """A retrieval unit (written to curated/chunks.jsonl and indexed in LanceDB)."""

    chunk_id: str
    record_id: str
    source_file: str
    doc_title: str
    section: str
    record_type: str
    question: str | None
    text: str
    embed_text: str
    approval_status: str
    category: str
    time_sensitive: bool
    as_of: str | None
    verification_status: str
    conflict_ids: list[str]
    urls: list[str]
    content_hash: str
    order: int

    def to_dict(self) -> dict:
        return asdict(self)

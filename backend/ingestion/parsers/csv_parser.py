"""CSV parser: one record per row, using the header row as field names."""

from __future__ import annotations

import csv
from pathlib import Path

from ingestion.models import ParsedRecord


def parse_csv(path: Path) -> list[ParsedRecord]:
    records: list[ParsedRecord] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = [f.strip().lower() for f in (reader.fieldnames or [])]
        for row in reader:
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            title = row.get("title") or row.get(fields[0], "") if fields else ""
            content = row.get("content") or " ".join(v for k, v in row.items() if k != "title")
            extra = {k: v for k, v in row.items() if k not in ("title", "content") and v}
            if not content:
                continue
            records.append(ParsedRecord("csv_row", [title] if title else [], content, extra=extra))
    return records

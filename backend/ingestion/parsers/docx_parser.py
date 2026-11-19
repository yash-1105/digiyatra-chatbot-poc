"""DOCX parser: paragraphs and tables in document order.

Only the main document body is read. Document properties (author, etc.),
comments, headers/footers and tracked-change metadata are never ingested.
"""

from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from ingestion.models import ParsedRecord

_HEADING_STYLE = re.compile(r"(?i)^(heading|title)")


def _is_question(text: str) -> bool:
    return text.endswith("?") and len(text) <= 260


def _table_lines(table: Table) -> tuple[list[str], list[list[str]]]:
    rows = []
    for row in table.rows:
        cells = []
        prev = None
        for cell in row.cells:  # merged cells repeat; de-duplicate consecutive repeats
            t = re.sub(r"\s+", " ", cell.text).strip()
            if cell._tc is prev:
                continue
            prev = cell._tc
            cells.append(t)
        rows.append(cells)
    if len(rows) == 1 or all(len(r) == 1 for r in rows):
        return [" ".join(c for r in rows for c in r if c)], []
    header, body = rows[0], rows[1:]
    lines = ["; ".join(f"{h}: {c}" for h, c in zip(header, r) if c) for r in body]
    return lines, rows


def parse_docx(path: Path) -> list[ParsedRecord]:
    document = docx.Document(str(path))
    records: list[ParsedRecord] = []
    section: list[str] = []
    title_lines: list[str] = []
    question: str | None = None
    answer: list[str] = []
    seen_heading_or_question = False

    def flush() -> None:
        nonlocal question, answer
        if question and answer:
            records.append(ParsedRecord("faq", list(section), "\n".join(answer).strip(), question=question))
        elif answer:
            records.append(ParsedRecord("section", list(section), "\n".join(answer).strip()))
        question, answer = None, []

    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            raw = item.text.strip()
            if not raw:
                continue
            style = item.style.name if item.style is not None else ""
            if _HEADING_STYLE.match(style):
                flush()
                section = [raw]
                seen_heading_or_question = True
                continue
            # A paragraph may hold "Question?\nAnswer..." in one block.
            parts = raw.split("\n", 1)
            first = parts[0].strip()
            if _is_question(first):
                flush()
                question = first
                seen_heading_or_question = True
                if len(parts) > 1 and parts[1].strip():
                    answer.append(parts[1].strip())
                continue
            if not seen_heading_or_question:
                title_lines.append(raw)
                continue
            bullet = "- " if "list" in style.lower() else ""
            answer.append(f"{bullet}{raw}")
        elif isinstance(item, Table):
            lines, rows = _table_lines(item)
            if not seen_heading_or_question:
                records.append(ParsedRecord("note", ["Notice"], "\n".join(lines)))
                continue
            # Tables stay attached to the current question/section, in order.
            answer.extend(lines)
            for r in rows[1:]:
                records.append(
                    ParsedRecord(
                        "table_row",
                        list(section) + ([question] if question else []),
                        "; ".join(f"{h}: {c}" for h, c in zip(rows[0], r) if c),
                    )
                )
    flush()
    if title_lines:
        records.insert(0, ParsedRecord("note", ["Title"], "\n".join(title_lines)))
    return records

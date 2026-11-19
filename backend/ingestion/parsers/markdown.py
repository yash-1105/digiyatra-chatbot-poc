"""Markdown parser that preserves FAQ question/answer structure.

Handles the patterns found in knowledge/raw:
  * headings that are questions ("## Is Digi Yatra mandatory?")
  * "Query / Issue | Resolution" tables
  * free-text "question line(s)" followed by a (possibly quoted) answer
  * ordinary sections (heading + paragraphs / lists)
"""

from __future__ import annotations

import re

from ingestion.models import ParsedRecord
from ingestion.sanitize import clean_quotes, strip_markup

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_WRAPPER_TAG = re.compile(r"^</?[a-z_]+>$")
_QUESTION_HEADER = re.compile(r"(?i)\b(query|issue|question)\b")
_INTERROGATIVE = re.compile(
    r"(?i)^(what|how|why|when|where|who|which|can|could|is|are|do|does|will|should|if)\b"
)


def _strip_md_inline(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("`", "").strip()


def _is_question(paragraph: str) -> bool:
    p = clean_quotes(_strip_md_inline(paragraph)).strip()
    if not p or len(p) > 260:
        return False
    # All lines should be question-like (allows two alternative phrasings on separate lines).
    lines = [ln.strip().strip('",') for ln in p.splitlines() if ln.strip()]
    if p.rstrip().endswith("?") or (len(lines) > 1 and all(ln.endswith("?") for ln in lines)):
        return True
    # Short interrogative line(s) without a closing "?" (e.g. "...Verifier node? Why").
    joined = " ".join(lines)
    return (
        len(joined) <= 200
        and bool(_INTERROGATIVE.match(joined))
        and not joined.endswith((".", ":", "!"))
        and ("?" in joined or len(joined.split()) >= 5)
    )


def _split_table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def _parse_table(lines: list[str], section_path: list[str]) -> list[ParsedRecord]:
    rows = [_split_table_row(ln) for ln in lines if ln.strip()]
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
    if len(rows) < 2:
        return []
    header, body = rows[0], rows[1:]
    out: list[ParsedRecord] = []
    faq_like = len(header) == 2 and _QUESTION_HEADER.search(header[0])
    for r in body:
        if faq_like and len(r) >= 2:
            q, a = _strip_md_inline(r[0]), _strip_md_inline(r[1])
            out.append(ParsedRecord("faq", section_path, a, question=q))
        else:
            pairs = [f"{h}: {_strip_md_inline(c)}" for h, c in zip(header, r) if c]
            out.append(ParsedRecord("table_row", section_path, "; ".join(pairs)))
    return out


def _paragraphs(lines: list[str]) -> list[str]:
    paras, cur = [], []
    for ln in lines:
        if ln.strip() == "":
            if cur:
                paras.append("\n".join(cur))
                cur = []
        else:
            cur.append(ln.rstrip())
    if cur:
        paras.append("\n".join(cur))
    return paras


def _section_records(lines: list[str], section_path: list[str]) -> list[ParsedRecord]:
    """Turn a section body into FAQ records (question paragraph + answer) or section text."""
    out: list[ParsedRecord] = []
    paras = _paragraphs(lines)
    pending_q: list[str] = []
    answer: list[str] = []
    leading: list[str] = []

    def flush() -> None:
        nonlocal pending_q, answer
        if pending_q and answer:
            q_lines = [
                clean_quotes(_strip_md_inline(ln)).strip('",')
                for x in pending_q
                for ln in x.splitlines()
                if ln.strip().strip('",')
            ]
            q = ""
            for ln in q_lines:  # wrapped lines join with a space; separate questions with " / "
                q = ln if not q else (f"{q} / {ln}" if q.endswith("?") else f"{q} {ln}")
            a = "\n\n".join(clean_quotes(x) for x in answer)
            out.append(ParsedRecord("faq", section_path, a, question=re.sub(r"\s+", " ", q)))
        elif pending_q:  # question with no answer -> keep as text
            leading.extend(pending_q)
        pending_q, answer = [], []

    for p in paras:
        if _is_question(p):
            if answer:
                flush()
            pending_q.append(p)
        elif pending_q:
            answer.append(p)
        else:
            leading.append(p)
    flush()

    if leading:
        text = "\n\n".join(clean_quotes(x) for x in leading)
        out.insert(0, ParsedRecord("section", section_path, text))
    return out


def parse_markdown(raw: str) -> list[ParsedRecord]:
    text = strip_markup(raw)  # drop <video> blocks etc. before structure parsing
    lines = [ln for ln in text.splitlines() if not _WRAPPER_TAG.match(ln.strip())]

    records: list[ParsedRecord] = []
    headings: list[tuple[int, str]] = []
    body: list[str] = []
    table: list[str] = []
    heading_is_question = False

    def section_path() -> list[str]:
        return [h for _, h in headings]

    def flush_body() -> None:
        nonlocal body, heading_is_question
        if heading_is_question and headings:
            answer = "\n".join(body).strip()
            if answer:
                q = headings[-1][1]
                records.append(ParsedRecord("faq", section_path()[:-1], clean_quotes(answer), question=q))
        elif any(b.strip() for b in body):
            records.extend(_section_records(body, section_path()))
        body = []

    def flush_table() -> None:
        nonlocal table
        if table:
            records.extend(_parse_table(table, section_path()))
        table = []

    for ln in lines:
        m = _HEADING.match(ln)
        if m:
            flush_table()
            flush_body()
            level, title = len(m.group(1)), _strip_md_inline(m.group(2))
            # Remove leading section numbering like "5. Careers ..."
            title = re.sub(r"^\d+\.\s+", "", title)
            headings = [h for h in headings if h[0] < level]
            headings.append((level, title))
            heading_is_question = title.endswith("?")
            continue
        if ln.lstrip().startswith("|"):
            if body and not heading_is_question:
                flush_body()
            table.append(ln)
            continue
        if table:
            flush_table()
        body.append(ln)
    flush_table()
    flush_body()
    return records

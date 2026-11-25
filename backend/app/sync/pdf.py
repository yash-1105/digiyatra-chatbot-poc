"""Safe PDF text extraction: pypdf in a resource-limited child process.

The parent passes the bytes on stdin; the child (``python -I app/sync/_pdf_child.py``, stdlib +
pypdf only, nothing from the project on its import path) runs with
address-space, CPU-time and file-size limits and returns JSON pages on stdout. A malformed
or hostile PDF can therefore exhaust only the child, which is killed on timeout.
Scanned PDFs without a text layer are reported as such (no OCR), never as success.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CHILD = Path(__file__).with_name("_pdf_child.py")


@dataclass
class PdfText:
    pages: list[str]
    page_count: int
    title: str | None
    reason: str | None = None   # no_text_layer | garbled_text | too_many_pages | parse_error | timeout

    @property
    def ok(self) -> bool:
        return self.reason is None


def _limits(memory_mb: int, cpu_s: int):
    def apply():
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 2**20, memory_mb * 2**20))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    return apply


def quality(text: str) -> str | None:
    letters = re.findall(r"[A-Za-zऀ-ॿ]", text)
    if len(letters) < 200:
        return "no_text_layer"
    # Legacy Hindi fonts extract as Latin mojibake / private-use glyphs; refuse rather than index noise.
    odd = len(re.findall(r"[-�]|[ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]", text))
    if odd / max(1, len(text)) > 0.02:
        return "garbled_text"
    return None


def extract_pdf(data: bytes, *, max_pages: int, timeout_s: int = 60, memory_mb: int = 768) -> PdfText:
    if not data.startswith(b"%PDF-"):
        return PdfText([], 0, None, "not_a_pdf")
    try:
        # Fixed argv: this interpreter, the bundled child script and an integer. Untrusted bytes go to stdin only.
        proc = subprocess.run(  # noqa: S603
            [sys.executable, "-I", str(CHILD), str(max_pages)], input=data, capture_output=True,
            timeout=timeout_s, cwd=CHILD.parent, preexec_fn=_limits(memory_mb, timeout_s), check=False,
        )
    except subprocess.TimeoutExpired:
        return PdfText([], 0, None, "timeout")
    if proc.returncode != 0 or len(proc.stdout) > 20_000_000:
        return PdfText([], 0, None, "parse_error")
    out = json.loads(proc.stdout)
    if out.get("reason"):
        return PdfText([], out.get("page_count", 0), None, out["reason"])
    pages = [re.sub(r"[ \t]+", " ", p).strip() for p in out["pages"]]
    return PdfText(pages, out["page_count"], out.get("title"), quality("\n".join(pages)))

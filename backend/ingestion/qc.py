"""Quality control: time-sensitive claims, numeric-claim contradictions, shared passages."""

from __future__ import annotations

import re
from collections import defaultdict

TIME_MARKERS = re.compile(
    r"(?i)\b(currently|at present|as of|recent(?:ly)?|latest|upcoming|planned|soon|in the future|"
    r"future roadmap|by early \d{4}|surpassed|million|crore|lakh|\d+(?:\.\d+)?%|"
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}|"
    r"\b20\d{2}\b)"
)

# Metrics whose values should agree across documents.
METRICS: dict[str, re.Pattern] = {
    "number_of_live_airports": re.compile(r"(?i)\b(?:live at|available at the following|available at)\s+(\d+)\s+airports"),
    "app_downloads_million": re.compile(r"(?i)(?:over|surpassed)\s+([\d.]+)\s*million\s+downloads|downloads\W+over\s+([\d.]+)\s*million"),
    "journeys_million": re.compile(r"(?i)(?:over\s+)?([\d.]+)\s*million\s+(?:seamless\s+)?(?:trips|journeys)|journeys facilitated\W+over\s+([\d.]+)\s*million"),
    "airport_data_purge_hours": re.compile(r"(?i)(?:purged?|delete[sd]?|deleted)[^.]{0,80}?within\s+(\d+)\s+hours"),
    "credential_share_window": re.compile(r"(?i)from\s+(\d+\s+hours?)\s+up\s+to\s+(\d+\s+minutes)"),
    "launch_date": re.compile(r"(?i)(?:introduced in|launch date\W+)\s*([A-Z][a-z]+\s+\d{4})"),
    "infants_supported": re.compile(r"(?i)(infants?[^.]{0,60}(?:can use|allows adding|not recommended|cannot be registered))"),
}


def time_markers(text: str) -> list[str]:
    seen: list[str] = []
    for m in TIME_MARKERS.finditer(text):
        v = m.group(0).strip()
        if v.lower() not in (s.lower() for s in seen):
            seen.append(v)
    return seen


def extract_metric_values(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for name, pat in METRICS.items():
        for m in pat.finditer(text):
            val = " to ".join(g for g in m.groups() if g)
            if name == "infants_supported":
                low = val.lower()
                val = "restricted" if ("not recommended" in low or "cannot" in low) else "allowed"
            out[name].append(val.strip())
    return out


def find_metric_conflicts(doc_texts: dict[str, tuple[str, str]]) -> list[dict]:
    """doc_texts: filename -> (status, text). Returns metrics with differing values."""
    values: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for fname, (status, text) in doc_texts.items():
        for metric, vals in extract_metric_values(text).items():
            for v in vals:
                values[metric][v.lower()].add(f"{fname} [{status}]")
    conflicts = []
    for metric, by_val in values.items():
        if len(by_val) > 1:
            conflicts.append(
                {"metric": metric, "values": {v: sorted(files) for v, files in sorted(by_val.items())}}
            )
    return conflicts


def find_shared_passages(doc_texts: dict[str, str], min_len: int = 160) -> list[dict]:
    """Exact sentence-level passages that appear in more than one document."""
    owners: dict[str, set[str]] = defaultdict(set)
    for fname, text in doc_texts.items():
        for sent in re.split(r"(?<=[.!?])\s+", text):
            norm = re.sub(r"\s+", " ", sent).strip().lower()
            if len(norm) >= min_len:
                owners[norm].add(fname)
    return [
        {"passage": p[:160] + ("…" if len(p) > 160 else ""), "files": sorted(f)}
        for p, f in owners.items()
        if len(f) > 1
    ]

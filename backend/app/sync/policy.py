"""Validation, sanitisation and verification policy for extracted official content.

Deterministic rules only: an LLM never extracts, approves or rewrites a claim.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from app.security.guardrails import assess_input
from app.sync.extract import Extraction
from app.sync.sources import DIGI_YATRA, EXCLUDED_PATH

MIN_ANSWER_CHARS = 12
MIN_SECTION_CHARS = 60
MAX_RECORD_CHARS = 6000

# CLAUDE.md: download / journey / usage statistics are never presented as current fact.
_BIG = r"\b\d[\d.,]*\s*(?:\+\s*)?-?\s*(?:crores?|lakhs?|millions?|billions?|mn|cr)\b"
_USAGE = r"\b(?:users?|usages?|journeys?|downloads?|onboard|passengers?|registrations?|travellers?|traffic|milestone)\b"
_S = r"[^.!?।\n]*"
USAGE_STAT = re.compile(
    rf"{_S}{_BIG}{_S}{_USAGE}{_S}[.!?।]?[\"”’']?"          # "… 26.5 million users …"
    rf"|{_S}{_USAGE}{_S}{_BIG}{_S}[.!?।]?[\"”’']?"          # "… passenger traffic … 50 crores …"
    r"|[^.!?।\n]*\d[\d.,]*\s*(?:करोड़|लाख)[^.!?।\n]*(?:यात्रा|उपयोग|डाउनलोड|उपयोगकर्ता|यात्री)[^.!?।\n]*[.!?।]?",
    re.I,
)
AIRPORT_COUNT = re.compile(r"\b(\d{1,3})\s+(?:\w+\s+){0,2}airports\b|(\d{1,3})\s+(?:\S+\s+){0,2}हवाई\s+अड्डों", re.I)
TRIAL_RANGE = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
                         r"\s+(?:to|–|-|and)\s+(january|february|march|april|may|june|july|august|september|october|"
                         r"november|december)\s+(\d{4})", re.I)
MONTHS = {m: i for i, m in enumerate(("january february march april may june july august september october "
                                       "november december").split(), 1)}
BOILERPLATE_LINE = re.compile(r"^(?:posted on:?|\(release id:.*\)|release id:.*|share|print|follow us.*|"
                              r"\*+|ministry of civil aviation|पत्र सूचना कार्यालय.*|visitor counter.*)$", re.I)


@dataclass
class Candidate:
    record_key: str
    record_type: str            # faq | section | document
    title: str
    category: str | None
    question: str | None
    body: str
    anchor: str | None
    language: str
    published_on: str | None
    updated_on: str | None
    effective_from: str | None
    expires_on: str | None
    flags: list[str] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256("\x1f".join(str(x or "") for x in (
            self.record_type, self.title, self.category, self.question, self.body, self.published_on,
            self.effective_from, self.expires_on)).encode()).hexdigest()


@dataclass
class Assessment:
    candidates: list[Candidate]
    complete: bool
    reason: str | None = None
    excluded: int = 0
    stripped_statistics: int = 0


def normalise_text(text: str) -> str:
    seen, out = set(), []
    for ln in (line.strip() for line in text.split("\n")):
        if not ln or BOILERPLATE_LINE.match(ln) or not re.search(r"\w", ln):
            continue
        if len(ln) > 25 and ln.lower() in seen:
            continue  # repeated title/date/print-version lines
        seen.add(ln.lower())
        out.append(ln)
    return re.sub(r"[ \t]+", " ", "\n".join(out)).strip()


# Facts that must survive when a sentence is removed for usage statistics: coverage counts of
# airports / terminals / airlines / languages, with the source's own number and qualifier.
PROTECTED_FACT = re.compile(
    r"\b(\d{1,3})\s+((?:domestic|international|major|additional|more|participating|operational)\s+)?"
    r"(airports?|terminals?|airlines?|languages?)\b"
    r"(\s*,?\s*serving\s+(?:domestic|international)\s+airlines)?",
    re.I,
)
PROTECTED_FACT_HI = re.compile(r"(\d{1,3})\s+(घरेलू\s+|अंतरराष्ट्रीय\s+)?(हवाई\s+अड्डों|हवाई\s+अड्डे|एयरलाइनों|भाषाओं)")
RETAINED_PREFIX = "Reported Digi Yatra coverage"


def retained_facts(sentence: str) -> list[str]:
    """Deterministic, number-preserving restatement of coverage facts found in a removed sentence.
    Wording is fixed; only the source's own number/qualifier/noun are reused (no inference)."""
    facts = []
    for m in PROTECTED_FACT.finditer(sentence):
        phrase = " ".join(x.strip() for x in (m.group(1), m.group(2) or "", m.group(3)) if x and x.strip())
        if m.group(4):
            phrase += ", " + m.group(4).strip(" ,")
        facts.append(f"{RETAINED_PREFIX}: {phrase}.")
    for m in PROTECTED_FACT_HI.finditer(sentence):
        phrase = " ".join(x.strip() for x in m.groups() if x and x.strip())
        facts.append(f"डिजी यात्रा का रिपोर्ट किया गया कवरेज: {phrase}।")
    return list(dict.fromkeys(facts))


def strip_statistics(text: str) -> tuple[str, int]:
    """Remove usage/download/journey statistics (never presented as current fact) while keeping
    relevant coverage facts from the same sentence (e.g. '39 domestic airports')."""
    count = 0

    def repl(m):
        nonlocal count
        count += 1
        kept = retained_facts(m.group(0))
        return (" " + " ".join(kept)) if kept else ""

    cleaned = USAGE_STAT.sub(repl, text)
    cleaned = re.sub(r"(^|\n)[\s\"“”'’,;:]+(?=\S)", r"\1", cleaned)  # punctuation left by a removed quote
    return re.sub(r"\n{2,}", "\n", re.sub(r"[ \t]{2,}", " ", cleaned)).strip(), count


def key_for(source_id: str, kind: str, label: str) -> str:
    norm = re.sub(r"\W+", " ", label.lower()).strip()
    return hashlib.sha256(f"{source_id}\x1f{kind}\x1f{norm}".encode()).hexdigest()[:32]


def trial_window(text: str) -> tuple[str | None, str | None]:
    m = TRIAL_RANGE.search(text)
    if not m or "trial" not in text.lower():
        return None, None
    start, end, year = MONTHS[m.group(1).lower()], MONTHS[m.group(2).lower()], int(m.group(3))
    if end < start:
        return None, None
    last = (date(year + (end == 12), end % 12 + 1, 1) - timedelta(days=1))
    return date(year, start, 1).isoformat(), last.isoformat()


def airport_counts(text: str) -> set[int]:
    return {int(a or b) for a, b in AIRPORT_COUNT.findall(text) if 3 <= int(a or b) <= 400}


def _dedupe_sections(sections):
    kept = []
    for s in sorted(sections, key=lambda s: -len(s.text)):
        words = set(re.findall(r"\w+", s.text.lower()))
        if any(words and len(words & k[1]) / len(words) > 0.85 for k in kept):
            continue
        kept.append((s, words))
    order = {id(s): i for i, s in enumerate(sections)}
    return [s for s, _ in sorted(kept, key=lambda k: order[id(k[0])])]


def _chunks(text: str, limit: int = 1400) -> list[str]:
    paras, out, cur = [p for p in text.split("\n") if p.strip()], [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 1 > limit:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def assess(source_id: str, spec, ex: Extraction, url: str) -> Assessment:
    """Turn an extraction into record candidates, or explain why it is unusable."""
    if ex.blocked:
        return Assessment([], False, "blocked_page_returned")
    if ex.social_embed:
        return Assessment([], False, "social_embed_excluded")  # Task 2 integrates social sources properly
    if EXCLUDED_PATH.search(url):
        return Assessment([], False, "excluded_path")
    stripped = 0
    candidates: list[Candidate] = []
    effective, expires = spec.effective_from, spec.expires_on
    page_text = "\n".join([ex.title] + [s.text for s in ex.sections] + [f.question + " " + f.answer for f in ex.faqs])
    if not effective and not expires:
        effective, expires = trial_window(page_text)
    title, n_title = strip_statistics(ex.title or "")
    if n_title or not title:
        title = f"{spec.organization} announcement" + (f" ({ex.published_on})" if ex.published_on else "")
    ex = replace(ex, title=title)
    if spec.source_type == "html_faq" or ex.faqs:
        if ex.unanswered_questions or any(len(f.answer) < MIN_ANSWER_CHARS for f in ex.faqs):
            return Assessment([], False, f"partial_faq_extraction:{ex.unanswered_questions or 'short_answers'}")
        if spec.source_type == "html_faq" and not ex.faqs:
            return Assessment([], False, "no_faq_items_found")
        for f in ex.faqs:
            answer, n = strip_statistics(normalise_text(f.answer))
            stripped += n
            candidates.append(Candidate(key_for(source_id, "faq", (f.category or "") + "|" + f.question), "faq",
                                        ex.title or spec.organization, f.category, f.question, answer[:MAX_RECORD_CHARS],
                                        f.anchor, ex.language, ex.published_on, ex.updated_on, effective, expires))
    else:
        sections = [s for s in _dedupe_sections(ex.sections) if len(s.text) >= MIN_SECTION_CHARS]
        if spec.section_filter:
            sections = [s for s in sections if re.search(spec.section_filter, s.heading + " " + s.text[:300], re.I)]
        for s in sections:
            body, n = strip_statistics(normalise_text(s.text))
            stripped += n
            if len(body) < MIN_SECTION_CHARS:
                continue
            for i, part in enumerate(_chunks(body)):
                label = f"{s.heading}|{i}"
                candidates.append(Candidate(key_for(source_id, "section", label), "section", ex.title or spec.organization,
                                            s.heading or None, None, part, s.anchor, ex.language,
                                            ex.published_on, ex.updated_on, effective, expires))
    for c in candidates:
        if RETAINED_PREFIX in c.body or "रिपोर्ट किया गया कवरेज" in c.body:
            c.flags.append("coverage fact restated from a sentence whose usage statistics were removed")
    if not candidates:
        return Assessment([], False, "no_relevant_content", stripped_statistics=stripped)
    relevant = DIGI_YATRA.search(page_text) is not None
    if not relevant:
        return Assessment([], False, "not_digi_yatra_related", stripped_statistics=stripped)
    for c in candidates:
        if assess_input(f"{c.question or ''}\n{c.body}").injection:
            return Assessment([], False, "prompt_injection_pattern_in_source")
    return Assessment(candidates, True, stripped_statistics=stripped)


def is_historical(spec, published_on: str | None, today: date) -> bool:
    return bool(spec.historical_after_days and published_on
                and date.fromisoformat(published_on) < today - timedelta(days=spec.historical_after_days))


def review_decision(spec, cand: Candidate, *, first_version: bool, auto_publish: bool,
                    conflicts: list[str]) -> tuple[str, str | None]:
    """verified only for low-risk, first-version, conflict-free records with auto-publication enabled."""
    if conflicts:
        return "conflict", "; ".join(conflicts)[:300]
    if spec.risk == "high":
        return "pending_review", "consequential topic requires human review"
    if not first_version:
        return "pending_review", "changed content of a previously verified record"
    if not auto_publish:
        return "pending_review", "automatic publication disabled"
    return "verified", None


def detect_conflicts(cand: Candidate, verified_counts: dict[int, str | None]) -> list[str]:
    """Airport-count claims that disagree with currently verified, differently dated records."""
    counts = airport_counts(f"{cand.question or ''} {cand.body}")
    out = []
    for n in sorted(counts):
        others = {m: d for m, d in verified_counts.items() if m != n}
        if others:
            out.append(f"airport count {n} differs from verified {sorted(others)}")
    return out


def capture_provenance(data: bytes, target_url: str) -> str:
    """Check URLs embedded in an operator capture against the page it claims to be.
    Raises on a mismatch; returns a provenance note for the reviewer otherwise."""
    from app.sync.extract import embedded_urls
    from app.sync.sources import canonical_url

    def norm(u):
        c = canonical_url(u) or ""
        return c.rstrip("/")

    if data.startswith(b"%PDF-"):
        return "pdf capture (no embedded page URL check)"
    found = [u for u in embedded_urls(data.decode("utf-8", "replace")) if u.startswith(("http://", "https://"))]
    if not found:
        return "no embedded page URL (provenance attested by the operator only)"
    if any(norm(u) != norm(target_url) for u in found):
        raise ValueError("Capture rejected: embedded page URL does not match the target official page")
    return "embedded page URL matches the official page"

"""Sentence-level grounding of model answers against retrieved evidence.

The answer-level check (at least one valid [S#]) is not enough: a model can attach a real
citation to a sentence the source never supports. Here every sentence is checked:

* factual sentences must be lexically supported by the evidence they cite
  (share of the sentence's content words found in that evidence);
* a citation pointing at the wrong source is re-attributed to the retrieved source that
  supports the sentence, or removed;
* factual sentences with no supporting evidence are dropped;
* numbers/dates in a sentence must occur in its supporting evidence (no invented figures);
* short procedural/advisory sentences ("please check the official website") are kept as-is.

This is a lexical heuristic (no NLI model is available): it reliably catches fabricated
figures, unrelated attributions and off-evidence claims, and errs on keeping paraphrases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.rag.embeddings import tokenize
from app.rag.multilingual import concepts
from app.rag.query import evidence_tokens

KEEP_SUPPORT = 0.4  # min share of a sentence's content words found in a cited source
REATTRIBUTE_SUPPORT = 0.5  # stricter bar for moving a sentence to a different / uncited source
MIN_FACTUAL_TOKENS = 1  # short instructions and "you can" claims still need evidence

# Words that carry no evidential content in this domain.
GENERIC = frozenset(
    tokenize(
        "digi yatra digiyatra app information official website evidence source sources provided approved "
        "please note however also therefore additionally currently may might changed change check verify "
        "confirm recommend recommended suggest advised available help support passenger passengers user users "
        "you your yours here say says said following below above detail details guidance process step steps "
        "need needs required require use using used able ensure make sure way ways one first next then finally "
        "information time sensitive latest updated update item items relevant second third"
    )
)
_ADVISORY = re.compile(
    r"(?i)^\s*((please )?(check|verify|contact)|for (more|further|the latest)|do not share|don't share|never share|"
    r"for support)\b"
)
# Statements ABOUT the evidence ("no phone number is listed", "I cannot confirm…") assert no new fact.
_DECLINE = re.compile(
    r"(?i)\b(i (cannot|can't|can not|could not|couldn't|am unable to|'m unable to)|unable to (confirm|determine|find)|"
    r"(does|do|did) not (mention|include|list|specify|contain|state|say|cover)|"
    r"(is|are|was|were) not (listed|mentioned|specified|included|stated|available in the)|no [\w\s-]{1,40} (is|are) (listed|mentioned|given|provided))\b"
)
_MARKER = re.compile(r"\[(\d+)\]")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w.])")
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+(?=\S)")
_LIST_PREFIX = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")


@dataclass
class GroundingResult:
    text: str
    cited_hits: list[int]  # 0-based indices into the evidence list, in order of first citation
    dropped: int = 0
    reattributed: int = 0
    removed_markers: int = 0
    details: list[str] = field(default_factory=list)


def _split(text: str) -> list[str]:
    """Split into sentences; markers written after the full stop ("…OTP. [1]") stay with their sentence."""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        para = line.rstrip("\r\n")
        if not para.strip():
            out.append("\n")
            continue
        prefix = _LIST_PREFIX.match(para)
        if prefix:
            para = para[prefix.end() :]
        parts = _SENTENCE_END.split(para)
        merged: list[str] = []
        for p in parts:
            m = re.match(r"^((?:\[\d+\]\s*)+)(.*)$", p, re.S)
            if m and merged:
                merged[-1] = merged[-1].rstrip() + " " + m.group(1).strip()
                p = m.group(2)
                if not p.strip():
                    continue
            merged.append(p)
        if prefix and merged:
            merged[0] = prefix.group() + merged[0]
        out.extend(merged)
        out.append("\n" if line.endswith("\n") else " ")
    return out


def _content(sentence: str) -> set[str]:
    return evidence_tokens(_MARKER.sub(" ", sentence)) - evidence_tokens(" ".join(GENERIC))


def _support(words: set[str], evidence_tokens: set[str]) -> float:
    return len(words & evidence_tokens) / len(words) if words else 1.0


def _numbers_ok(sentence: str, evidence_texts: list[str]) -> bool:
    nums = {n.replace(",", "") for n in _NUMBER.findall(_MARKER.sub(" ", concepts(sentence)))}
    if not nums:
        return True
    pool = " ".join(evidence_texts).replace(",", "")
    return all(re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", pool) for n in nums)


def _polarity_ok(sentence: str, evidence: str) -> bool:
    """Reject common policy reversals that bag-of-words overlap alone cannot detect.

    This supplements lexical support; it is deliberately not a semantic entailment model.
    FAQ question premises must never override their answers.
    """
    if _DECLINE.match(sentence):
        return True
    answer = re.sub(r"^Q:.*?(?:\n| )A:\s*", "", evidence, flags=re.S).lower()
    claim = concepts(sentence).lower().replace("’", "'")
    # A required platform, identity provider, format or technology must actually
    # occur in the evidence. Other overlapping words cannot establish its policy.
    anchors = evidence_tokens("NFC OTP QR Android iOS iPhone DigiLocker Aadhaar PDF JPEG PNG lounge payment")
    if (evidence_tokens(claim) & anchors) - evidence_tokens(answer):
        return False
    if "aadhaar" in claim:
        required = bool(re.search(r"\b(mandatory|required|necessary)\b", answer))
        denied = bool(re.search(r"\bnot (?:mandatory|required|necessary)\b|\b(?:mandatory|required|necessary) not\b", claim))
        bypass = "without" in claim and bool(re.search(r"\b(can|may)\b", claim)) and not re.search(r"\b(not|cannot|can't)\b", claim)
        if required and (denied or bypass):
            return False
    if re.search(r"\b(centrally|central(?:ized|ised)?|central server)\b", claim) and re.search(
        r"\b(stor\w*|sav\w*)\b", claim
    ):
        if re.search(r"\b(no|not|never|isn't|aren't)\b.{0,65}\b(central\w*|stor\w*)\b", answer) and not re.search(
            r"\b(no|not|never|isn't|aren't)\b", claim
        ):
            return False
    if re.search(r"\b(mandatory|required|compulsory)\b", claim) and "aadhaar" not in claim:
        if "voluntary" in answer and not re.search(r"\b(not|isn't|never)\b", claim):
            return False
    return True


def ground_answer(text: str, marker_to_hit: dict[int, int], evidence: list[str]) -> GroundingResult:
    """`text` uses [n] markers; marker_to_hit maps n -> 0-based evidence index. Returns re-numbered text."""
    ev_tokens = [evidence_tokens(e) for e in evidence]
    res = GroundingResult(text="", cited_hits=[])
    pieces: list[str] = []

    for sent in _split(text):
        if not sent.strip():
            pieces.append(sent)
            continue
        prefix_match = _LIST_PREFIX.match(sent)
        prefix = prefix_match.group() if prefix_match else ""
        if prefix_match:
            sent = sent[prefix_match.end() :]
        hits = [marker_to_hit[int(m)] for m in _MARKER.findall(sent) if int(m) in marker_to_hit]
        hits = list(dict.fromkeys(hits))
        body = _MARKER.sub("", sent).rstrip()
        body = re.sub(r"\s+([.,;:!?])", r"\1", body)
        words = _content(body)
        factual = len(words) >= MIN_FACTUAL_TOKENS and not _ADVISORY.match(body) and not _DECLINE.match(body)
        if any(not _polarity_ok(body, evidence[h]) for h in (hits or list(range(len(evidence))))):
            factual = True

        if not factual:
            keep = hits  # connective / advisory text: leave its markers untouched
        else:
            keep = [
                h for h in hits if _support(words, ev_tokens[h]) >= KEEP_SUPPORT and _polarity_ok(body, evidence[h])
            ]
            res.removed_markers += len(hits) - len(keep)
            if not keep:
                best = max(
                    (i for i in range(len(evidence)) if _polarity_ok(body, evidence[i])),
                    key=lambda i: _support(words, ev_tokens[i]),
                    default=None,
                )
                if best is not None and _support(words, ev_tokens[best]) >= REATTRIBUTE_SUPPORT:
                    keep = [best]
                    res.reattributed += 1
                    res.details.append(f"reattributed to evidence {best + 1}")
            if not keep or not _numbers_ok(body, [evidence[h] for h in keep]):
                res.dropped += 1
                res.details.append("dropped unsupported sentence")
                continue

        for h in keep:
            if h not in res.cited_hits:
                res.cited_hits.append(h)
        marks = "".join(f"[{res.cited_hits.index(h) + 1}]" for h in sorted(keep, key=res.cited_hits.index))
        if marks:
            m = re.match(r"^(.*?)([.!?।]*)$", body, re.S)
            body = f"{m.group(1)} {marks}{m.group(2)}" if m else f"{body} {marks}"
        pieces.append(prefix + body + " ")

    res.text = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", "".join(pieces))).strip()
    res.text = re.sub(r"\n{3,}", "\n\n", res.text)
    # Unsupported steps can be removed; the remaining list must still read 1, 2, 3.
    step = 0

    def renumber(match: re.Match) -> str:
        nonlocal step
        step += 1
        return f"{step}. "

    res.text = re.sub(r"(?m)^\d+[.)]\s+", renumber, res.text)
    return res

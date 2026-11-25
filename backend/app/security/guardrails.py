"""Guardrails applied before and after the LLM call.

Input side:  prompt-injection / secret-extraction detection, PII detection and
             redaction, greeting / live-status / out-of-scope classification.
Output side: removal of fabricated actions (escalations, complaints), secret or
             system-prompt leakage, non-allow-listed URLs, invalid citations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# --------------------------------------------------------------------- input
_INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(previous|prior|above|earlier|all|your|the)\b.{0,30}\b(instructions?|rules|prompts?|guidelines|polic(y|ies)|context)\b",
    r"\b(system|developer|hidden|initial|original)\s+(prompt|message|instructions?)\b",
    r"\b(reveal|show|print|repeat|output|display|tell me|give me|what (is|are)|leak|dump)\b.{0,40}\b(prompt|instructions?|rules you (follow|were given)|server configuration|config file|api[\s_-]?key|secrets?|access token|admin(istrator)? password|env(ironment)? variables?)\b",
    r"\b(api[\s_-]?key|sarvam_api_key|subscription[\s_-]?key|access token|bearer token)\b",
    r"\b(jailbreak|dan mode|developer mode|god mode|do anything now)\b",
    r"\byou are (now|no longer)\b",
    r"\b(pretend|roleplay|role-play)\b",
    r"\bact as (an? |my |the )?(ai|assistant|chatbot|system|developer|admin|administrator|unrestricted|different)\b",
    r"\bnew (instructions?|rules|persona)\b",
    r"\b(internal|private|confidential)\s+(data|documents?|database|files?|notes|logs)\b",
    r"\b(list|show|dump|export)\b.{0,30}\b(database|index|vector store|lancedb|knowledge base|all documents|other users?|conversations?)\b",
    r"\b(draft|unapproved|unreleased|unpublished)\b.{0,30}\b(documents?|content|faq|policy|policies)\b",
    r"<\s*/?\s*(system|evidence|instructions?)\s*>",
]
_INJECTION = [re.compile(p, re.I | re.S) for p in _INJECTION_PATTERNS]

_PII_PATTERNS: dict[str, re.Pattern] = {
    "aadhaar": re.compile(r"(?<!\d)[2-9]\d{3}[\s._-]?\d{4}[\s._-]?\d{4}(?!\d)"),
    "otp": re.compile(r"(?i)(?<!\w)(otp|one[\s-]?time[\s-]?password|verification code|code|ओटीपी)(?=\W|\d)\W{0,5}(is|:|=)?\W{0,5}\d{4,8}(?!\d)"),
    "passport": re.compile(r"(?i)\bpassport\b.{0,25}\b[A-Z]\d{7}\b|\b[A-PR-WY][1-9]\d{5}[1-9]\b"),
    "phone": re.compile(r"(?<![\w.])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\w.])"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "password": re.compile(r"(?i)(?<!\w)(password|passcode|पासवर्ड|पासकोड)\s*(?:is\s+|[:=]\s*)[^\s]{4,128}"),
    "pnr": re.compile(r"(?i)\bpnr\b\W{0,8}(?:no\.?|number|is|:)?\W{0,4}[A-Z0-9]{6}\b"),
}
_PII_LABEL = {
    "aadhaar": "an Aadhaar-like number",
    "otp": "an OTP / verification code",
    "passport": "a passport number",
    "phone": "a phone number",
    "email": "an email address",
    "pnr": "a PNR",
    "password": "a password or passcode",
}
_SENSITIVE_UPLOAD = re.compile(
    r"(?i)\b(here is|attached|sending|sharing|uploaded?)\b.{0,30}\b(aadhaar|passport|boarding pass|otp)\b"
)

_GREETING = re.compile(
    r"(?i)^\s*(hi+|hello+|hey+|namaste|namaskar|good (morning|afternoon|evening)|thanks?( you)?|thank you( so much)?|ok(ay)?|bye|goodbye)[\s!.,?]*$"
)
# Real-time / transactional requests the assistant cannot answer from static knowledge.
_LIVE_STATUS = re.compile(
    r"(?i)\b(flight status|is my flight|my flight (number|is)|delayed|delay(ed)? today|gate number|which gate|"
    r"(queue|wait(ing)?) (time|length).{0,20}(now|today|right now)|(right now|today|currently).{0,30}(working|down|open|queue)|"
    r"(e-?gates?|gates?|digi ?yatra|lanes?|counters?)\b.{0,40}\b(working|down|open|closed|functional|operational|running)\b.{0,25}\b(now|today|right now|currently|at the moment|tonight)|"
    r"(now|today|right now|currently|at the moment)\b.{0,40}\b(e-?gates?|digi ?yatra|lanes?)\b.{0,30}\b(working|down|open|closed|functional|operational)|"
    r"pnr status|book (a )?(ticket|flight)|cancel (my )?(ticket|flight)|refund|baggage allowance|check[- ]?in status|seat (number|availability))\b"
)
_ACTION_REQUEST = re.compile(
    r"(?i)\b(file|raise|register|lodge|submit|log|escalate|forward)\b.{0,25}\b(complaint|grievance|ticket|issue|case|request)\b"
    r"|\bescalate\b|\bcomplain on my behalf\b"
)
DOMAIN_TERMS = re.compile(
    r"(?i)\b(digi ?yatra|dyce|dyf|airport|e-?gates?|boarding|flight|travel|passenger|aadhaar|aadhar|digilocker|selfie|"
    r"face|biometric|credential|wallet|app|otp|enrol|enroll|register|registration|privacy|data|consent|security|"
    r"check|terminal|airline|minor|child|infant|kid|verify|verification|upload|uninstall|delete|support|customer care|"
    r"contact|complaint|vc|did|ssi|domestic|international|passport|turban|phone|mobile|login|error|"
    r"smart ?share|dy-?ipt|nfc|e-?passport)\b"
)


@dataclass
class InputAssessment:
    redacted_text: str
    pii_types: list[str] = field(default_factory=list)
    injection: bool = False
    greeting: bool = False
    live_status: bool = False
    action_request: bool = False
    domain_related: bool = False


def detect_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION) or bool(re.search(r"(?i)\b(rules|instructions)\b.{0,50}\bignore\b", text)) or bool(re.search(
        r"(नियम|निर्देश).{0,35}(अनदेखा|ignore)|(?:अनदेखा|ignore).{0,35}(नियम|निर्देश)|(?:कुंजी|पासवर्ड|प्रॉम्प्ट).{0,25}(दिखाओ|बताओ|उजागर)", text))


def detect_and_redact_pii(text: str) -> tuple[str, list[str]]:
    found: list[str] = []
    redacted = text
    for name, pat in _PII_PATTERNS.items():
        if pat.search(redacted):
            found.append(name)
            redacted = pat.sub(f"[{name} removed]", redacted)
    if _SENSITIVE_UPLOAD.search(text) and "document" not in found:
        found.append("document")
    return redacted, found


def assess_input(text: str) -> InputAssessment:
    from app.rag.multilingual import concepts, digits, normalize_question
    normalized = normalize_question(text)
    redacted, pii = detect_and_redact_pii(digits(text))
    translated, translated_pii = detect_and_redact_pii(concepts(text))
    if set(translated_pii) - set(pii):
        redacted, pii = translated, sorted(set(pii) | set(translated_pii))
    return InputAssessment(
        redacted_text=redacted,
        pii_types=pii,
        injection=detect_injection(normalized),
        greeting=bool(_GREETING.match(normalized)),
        live_status=bool(_LIVE_STATUS.search(normalized)),
        action_request=bool(_ACTION_REQUEST.search(normalized)),
        domain_related=bool(DOMAIN_TERMS.search(normalized)),
    )


def pii_notice(pii_types: list[str]) -> str:
    labels = [_PII_LABEL.get(t, "a personal document") for t in pii_types]
    what = ", ".join(labels)
    return (
        f"For your safety, your message appeared to contain {what}, which was removed before processing. "
        "Please never share OTPs, Aadhaar numbers, passport details, passwords or boarding passes in this chat."
    )


# -------------------------------------------------------------------- output
_FABRICATED_ACTION = re.compile(
    r"(?i)[^.\n\]]*\b("
    r"(i|we)\s+(have|'ve|will|'ll|am going to|shall)\s+(now\s+)?(filed|file|raised|raise|escalated|escalate|registered|register|logged|log|"
    r"forwarded|forward|shared|share|reported|report|submitted|submit|passed|pass|notified|notify|contacted|contact)\b(?!\s+(you|the user)\b)"
    r"|(your|this|the)\s+(complaint|feedback|issue|request|case|ticket|suggestion|details)\s+(has|have)\s+(been\s+)?"
    r"(filed|raised|escalated|registered|logged|forwarded|shared|reported|submitted|passed|noted)"
    r"|ticket (number|id)\s*(is|:)"
    r")[^.\n]*[.\n]?"
)
_URL = re.compile(r"https?://[^\s)\]>\"']+")
# Internal evidence annotations that must never reach the user.
_INTERNAL_LABELS = re.compile(
    r"\s*[\[(]\s*(known conflict|conflict group|conflict note)[^\])]*[\])]|\b(conflict group|known conflict)\s+C\d+\b",
    re.I,
)
_CITATION_GROUP = re.compile(r"\[\s*((?:S?\s*\d+\s*[,;]?\s*)+)\]", re.I)


@dataclass
class OutputCheck:
    text: str
    removed_actions: int = 0
    removed_urls: int = 0
    leaked: bool = False
    cited: list[int] = field(default_factory=list)
    invalid_citations: int = 0


def strip_fabricated_actions(text: str) -> tuple[str, int]:
    hindi_action = re.compile(r"[^।.\n]*(?:(?:मैंने|हमने).{0,50}(?:शिकायत|टिकट|मामला).{0,25}(?:दर्ज|भेज)|(?:शिकायत|टिकट).{0,25}(?:दर्ज कर दी|भेज दी|दर्ज हो गई))[^।.\n]*[।.\n]?")
    text, hi_n = hindi_action.subn("", text)
    new, n = _FABRICATED_ACTION.subn("", text)
    n += hi_n
    return re.sub(r"[ \t]{2,}", " ", new).strip(), n


def filter_urls(text: str, allowed: set[str], allowed_prefixes: tuple[str, ...]) -> tuple[str, int]:
    removed = 0

    def repl(m: re.Match) -> str:
        nonlocal removed
        url = m.group(0).rstrip(".,;:")
        tail = m.group(0)[len(url):]
        try:
            target = urlsplit(url)
            official = any(
                target.scheme == p.scheme and target.hostname == p.hostname
                and target.port in (None, 443) and not target.username and not target.password
                for p in map(urlsplit, allowed_prefixes)
            )
        except ValueError:
            official = False
        if url in allowed or official:
            return m.group(0)
        removed += 1
        return "[link removed]" + tail

    return _URL.sub(repl, text), removed


def validate_citations(text: str, n_sources: int) -> tuple[str, list[int], int]:
    """Keep only markers that refer to provided evidence; renumber in order of first use.
    Returns (text_with_[n]_markers, original_source_indices_in_order, invalid_count)."""
    order: list[int] = []
    invalid = 0

    def repl(m: re.Match) -> str:
        nonlocal invalid
        nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
        keep = []
        for n in nums:
            if 1 <= n <= n_sources:
                if n not in order:
                    order.append(n)
                keep.append(order.index(n) + 1)
            else:
                invalid += 1
        keep = sorted(set(keep))
        return "".join(f"[{k}]" for k in keep)

    new = _CITATION_GROUP.sub(repl, text)
    new = re.sub(r"\s+([.,;:])", r"\1", new)
    return new.strip(), order, invalid


def check_output(
    text: str,
    *,
    n_sources: int,
    secrets: list[str],
    canary: str,
    allowed_urls: set[str],
    allowed_url_prefixes: tuple[str, ...],
) -> OutputCheck:
    leaked = canary in text or any(s and len(s) >= 8 and s in text for s in secrets)
    if leaked:
        return OutputCheck(text="", leaked=True)
    text = _INTERNAL_LABELS.sub("", text)
    text, n_actions = strip_fabricated_actions(text)
    text, n_urls = filter_urls(text, allowed_urls, allowed_url_prefixes)
    text, cited, invalid = validate_citations(text, n_sources)
    return OutputCheck(text=text, removed_actions=n_actions, removed_urls=n_urls, cited=cited, invalid_citations=invalid)

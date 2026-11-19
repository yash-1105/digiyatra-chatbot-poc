"""Privacy-safe question categorisation.

Questions are mapped to a FIXED topic list plus up to five keywords drawn from a
fixed allow-list. No user-written text is ever stored, so names, numbers and
other identifiers cannot reach the analytics database.
"""

from __future__ import annotations

import re

# Ordered: first matching rule wins (more specific topics first).
_RULES: list[tuple[str, re.Pattern]] = [
    ("international_travel", re.compile(r"(?i)\b(international|abroad|foreign|overseas|e-?passport|passport|visa|nri)\b")),
    ("digilocker_verification", re.compile(r"(?i)\bdigi\s?locker\b")),
    ("boarding_pass_upload", re.compile(r"(?i)\b(boarding\s?pass|bp|pdf|upload|scan(ning)?|name mismatch|itinerary|seat)\b")),
    ("minors_family", re.compile(r"(?i)\b(child|children|kid|kids|minor|infant|baby|son|daughter|family|dependent|wife|husband|spouse)\b")),
    ("privacy_deletion", re.compile(r"(?i)\b(privacy|data|delete|deletion|uninstall|remove|stored?|storage|retain|retention|share|shared|consent|safe|secure|security)\b")),
    ("app_errors", re.compile(r"(?i)\b(error|forbidden|crash|crashing|freez|hang|not working|otp|login|log in|selfie|camera|install|update|passcode|device lock|bug|fail(s|ed|ing)?)\b")),
    ("airport_availability", re.compile(r"(?i)\b(airports?|which (city|cities)|available at|supported|upcoming)\b")),
    ("airport_journey", re.compile(r"(?i)\b(e-?gates?|gate|entry|security check|boarding gate|terminal|queue|journey|at the airport)\b")),
    ("aadhaar_registration", re.compile(r"(?i)\b(aadhaa?r|aadhar|adhaar|register|registration|enrol+|enrol+ment|sign ?up|onboard(ing)?|credential)\b")),
    ("contact_support", re.compile(r"(?i)\b(contact|customer care|support|help ?line|email|complaint|grievance|phone number)\b")),
    ("general_information", re.compile(r"(?i)\b(digi ?yatra|what is|how does|mandatory|voluntary|who (runs|operates)|benefit|cost|fee|free|language)\b")),
]

# Fixed keyword vocabulary (the ONLY words that may be stored).
KEYWORDS: dict[str, re.Pattern] = {
    k: re.compile(p, re.I)
    for k, p in {
        "aadhaar": r"\baadhaa?r|\badhaar|\baadhar",
        "digilocker": r"\bdigi\s?locker",
        "otp": r"\botp\b",
        "selfie": r"\bselfie",
        "boarding pass": r"\bboarding\s?pass|\bbp\b",
        "pdf": r"\bpdf\b",
        "name mismatch": r"\bname\b.{0,30}\b(match|mismatch|different)",
        "airport list": r"\b(which|list of|supported)\b.{0,20}\bairports?",
        "e-gate": r"\be-?gates?\b",
        "international": r"\binternational|\babroad|\bforeign",
        "passport": r"\bpassport",
        "child / minor": r"\b(child|children|kid|minor|infant|baby)",
        "delete account": r"\b(delete|uninstall|remove)\b",
        "data storage": r"\b(stored?|storage|retention|retain)\b",
        "login": r"\blog\s?in|\bforbidden",
        "app crash": r"\bcrash|\bfreez|\bhang",
        "language": r"\blanguage|\bhindi|\btamil",
        "fees": r"\b(fee|cost|charge|price)",
        "phone number": r"\bphone number|\bhelpline|\btoll[- ]free",
        "train": r"\btrain|\brailway",
        "statistics": r"\bhow many (people|passengers|users)|\bstatistic",
        "transit": r"\btransit|\btransfer|\bconnecting",
    }.items()
}


def classify(text: str) -> str:
    for slug, pattern in _RULES:
        if pattern.search(text):
            return slug
    return "other"


def keywords(text: str, limit: int = 5) -> str | None:
    found = [k for k, p in KEYWORDS.items() if p.search(text)][:limit]
    return ", ".join(found) or None

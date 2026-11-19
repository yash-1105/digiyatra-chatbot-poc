"""Passenger query normalization and evidence-based intent signals; never adds answer facts."""

from __future__ import annotations

import re

from app.rag.embeddings import tokenize
from app.rag.multilingual import HINDI_STOP, concepts, normalize_question


def normalize_query(text: str) -> str:
    text = normalize_question(text).lower().replace("’", "'")
    for pattern, replacement in (
        (r"\bdigiyatra\b", "digi yatra"),
        (r"\b(?:boarding[- ]?pass|bp)\b", "boarding pass"),
        (r"\b(?:aadhar|adhaar|adhar)\b", "aadhaar"),
        (r"\b(?:don't have|doesn't have|do not have|does not have|no)\s+(?:an?\s+)?aadhaar\b", "without aadhaar"),
        (r"\b(?:iphone|i-phone|ipad)\b", "ios"),
        (r"\bplaystore\b", "play store"),
        (r"\bappstore\b", "app store"),
        (r"\b(?:e-ticket|flight ticket)\b", "boarding pass ticket"),
        (r"\b(?:samsung|oneplus|pixel)\b", "android phone"),
        (r"\b(?:sign[- ]?up|get started)\b", "registration"),
    ):
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def query_intent(text: str) -> str | None:
    q = normalize_query(text)
    if re.search(r"\b(manual|normally|regular|alternative)\b", q) and re.search(
        r"\b(down|fail\w*|not work|doesn.t work|instead)\b", q
    ):
        return "manual_alternative"
    if "without aadhaar" in q:
        return (
            "child_without_aadhaar" if re.search(r"\b(child|children|minor|infant|kid)\b", q) else "aadhaar_requirement"
        )
    if re.search(r"\b(selfie|face|photo)\b", q) and re.search(r"\b(error|fail\w*|unreal|capture|blurry)\b", q):
        return "selfie_problem"
    if re.search(r"\b(otp|one.time password)\b", q) and re.search(
        r"\b(receiv\w*|getting|arriv\w*|problem|fail\w*)\b", q
    ):
        return "otp_problem"
    if "boarding pass" in q and re.search(r"\b(fail\w*|uploading|isn't|doesn't|error|won't|not working)\b", q):
        return "boarding_problem"
    if "pdf" in q and re.search(r"\b(upload|share|send|add|phone|file)\b", q):
        return "boarding_pdf"
    if "boarding pass" in q and re.search(r"\bscan\b", q):
        return "boarding_scan"
    if "boarding pass" in q and re.search(r"\b(upload|add|where|how|ticket)\b", q):
        return "boarding_upload"
    if re.search(r"\b(download|install)\b", q) or (
        re.search(r"\b(android|ios|play store|app store)\b", q)
        and re.search(r"\b(use|work|available|only|also|on|download|app)\b", q)
    ):
        return "app_download"
    if re.search(r"\b(register\w*|registration|enrol\w*)\b", q):
        return "registration"
    return None


INTENT_TERMS = {
    "manual_alternative": "system down regular manual processes alternative identity verification boarding",
    "aadhaar_requirement": "without aadhaar mandatory verification registration",
    "child_without_aadhaar": "child infant without aadhaar manual guardian",
    "app_download": "download app android ios google play store apple app store",
    "boarding_pdf": "boarding pass pdf phone files share digi yatra consent",
    "boarding_upload": "boarding pass upload scan image pdf share consent",
    "boarding_scan": "scan boarding pass clear valid QR code app option",
    "boarding_problem": "boarding pass upload failing name aadhaar valid qr scan",
    "registration": "register registration aadhaar digilocker otp selfie",
    "otp_problem": "otp receiving mobile verification network uidai",
    "selfie_problem": "selfie capture unreal image lighting background glasses",
}


def intent_match(intent: str | None, chunk: dict) -> float:
    """Promotion requires anchors in the approved chunk itself, not just its filename."""
    text = normalize_query(chunk["text"])
    if intent == "manual_alternative":
        return float(all(w in text for w in ("system", "down", "regular manual", "alternative")))
    if intent == "aadhaar_requirement":
        return float("without aadhaar" in text and "mandatory" in text)
    if intent == "child_without_aadhaar":
        return float(all(w in text for w in ("child", "aadhaar", "manual", "guardian")))
    if intent == "app_download":
        return float("play.google.com/" in text and "apps.apple.com/" in text)
    if intent == "boarding_pdf":
        return float(all(w in text for w in ("pdf", "share", "consent")))
    if intent == "boarding_scan":
        if "scan boarding pass" in text and "qr" in text:
            return 1.0
        return 0.8 if all(w in text for w in ("boarding pass", "scan", "image", "pdf")) else 0.0
    if intent == "boarding_upload":
        if "boarding pass" not in text:
            return 0.0
        if all(w in text for w in ("scan", "image", "pdf")):
            return 1.0
        if all(w in text for w in ("pdf", "share", "consent")):
            return 0.9
        return 0.65 if "scan boarding pass" in text else 0.0
    if intent == "boarding_problem":
        return float(all(w in text for w in ("boarding pass", "upload", "fail", "qr")))
    if intent == "registration":
        return float(all(w in text for w in ("register", "digilocker", "otp", "selfie")))
    if intent == "otp_problem":
        return float("otp" in text and "network" in text and "uidai" in text)
    if intent == "selfie_problem":
        return float("selfie" in text and "background" in text and ("unreal" in text or "lighting" in text))
    return 0.0


# Equivalent wording for claim validation; expansions never contribute new policy facts.
_EQUIVALENTS = {
    "iphone": "ios",
    "lit": "lighting",
    "locally": "local",
    "securely": "secure",
    "permanently": "permanent",
    "illuminated": "lighting",
    "ipad": "ios",
    "android": "android",
    "save": "store",
    "storage": "store",
    "erase": "delete",
    "remove": "delete",
    "smartphone": "phone",
    "device": "phone",
    "cellphone": "phone",
    "permission": "consent",
    "permissions": "consent",
    "authorize": "consent",
    "choose": "select",
    "pick": "select",
    "tap": "select",
    "click": "select",
    "picture": "image",
    "photo": "image",
    "photograph": "image",
    "enrol": "register",
    "enroll": "register",
    "registration": "register",
    "enrollment": "register",
    "enrolment": "register",
    "scan": "scan",
    "scann": "scan",
    "upload": "upload",
    "download": "download",
    "install": "download",
    "mandatory": "required",
    "require": "required",
    "necessary": "required",
    "purge": "delete",
    "purg": "delete",
    "retention": "retain",
}


_ALIASES = {tokenize(k)[0]: tokenize(v)[0] for k, v in _EQUIVALENTS.items() if tokenize(k) and tokenize(v)}


def evidence_tokens(text: str) -> set[str]:
    # FAQ questions are not evidence for their own premises; only the answer is authoritative.
    text = re.sub(r"^Q:.*?(?:\n| )A:\s*", "", text, flags=re.S)
    text = concepts(text)
    unknown = {w for w in re.findall(r"[\u0900-\u0963\u0971-\u097f]+", text) if w not in HINDI_STOP}
    return {_ALIASES.get(t, t) for t in tokenize(text)} | unknown

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
    if re.search(r"\be[- ]?passports?\b", q) and re.search(r"\b(digi yatra|international|travel)\b", q):
        return "epassport_scope"
    if re.search(r"\b(?:international (?:flights?|travel|passengers?|journeys?)|abroad|overseas)\b", q):
        return "international_scope"
    if "digi yatra" in q and re.search(r"\b(price|pricing|costs?|fees?|charg(?:e|es|ed)|free|money|pay)\b", q):
        if re.search(r"\b(download|install)\b", q):
            return "download_cost"
        if not re.search(r"\b(baggage|luggage|fare|flight ticket|parking|cancellation|register\w*|registration|lounge)\b", q):
            return "service_cost"
    if (re.search(r"\b(internet|wifi|wi-fi|offline|mobile data)\b", q)
            and re.search(r"\b(without|offline|needs?|require\w*|necessary|connection|not|required)\b", q)
            and not re.search(r"\b(offline aadhaar|otp|login error)\b", q)):
        return "connectivity"
    if "digilocker" in q and re.search(r"\b(difference|different|compare|vs|versus|same)\b", q):
        return "digilocker_comparison"
    if re.search(r"\b(face|facial|biometric)\b", q) and re.search(r"\b(verification|recognition|validation|match|scan)\b", q) and re.search(r"\b(fail\w*|error|not work\w*|not match\w*)\b", q):
        return "face_verification"
    if re.search(r"\b(airport|airports|cities)\b", q) and re.search(r"\b(data|biometric|biometrics)\b", q) and re.search(r"\b(retain\w*|retention|stored|storage|purge|delete|long|hours?)\b", q):
        return "airport_retention"
    if re.search(r"\b(airport|airports|cities)\b", q) and re.search(r"\b(which|list|support\w*|available|availability|where|upcoming|planned|future)\b", q):
        return "airport_planned" if re.search(r"\b(upcoming|planned|future)\b", q) else "airport_catalog"
    if re.search(r"\b(government|govt|organization|organisation|operat\w*|runs?|owns?|ownership|company|foundation|ministry|moca|industry)\b", q) and re.search(r"\b(digi yatra|foundation|app|application|initiative|it|this)\b", q):
        return "organization"
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
    "download_cost": "app download free app store google play price fee",
    "service_cost": "service fee free of charge cost to use",
    "connectivity": "internet connection offline registration boarding pass share airport facial verification",
    "international_scope": "international flights domestic flights departing supported airports integration roadmap",
    "epassport_scope": "international passengers e-passport enrollment roadmap domestic flights",
    "face_verification": "face validation selfie capture lighting plain background glasses steady gate regular manual system down",
    "digilocker_comparison": "DigiLocker Aadhaar link register Digi Yatra airport facial verification digital credential",

    "organization": "operator operated foundation not for profit company section 8 industry led ministry civil aviation framework",
    "airport_catalog": "which airports currently support available supported airports documented list",
    "airport_planned": "which airports planned future upcoming implementation",
    "airport_retention": "how long biometric data stored airport verifier node retention purge hours flight departure",
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


SCOPED_INTENTS = frozenset({
    "download_cost", "service_cost", "connectivity", "international_scope",
    "epassport_scope", "face_verification", "digilocker_comparison",
})


def pricing_claim(text: str) -> bool:
    return bool(re.search(r"\b(?:free of charge|free to (?:download|use|install)|no (?:fee|charge)s?|"
                          r"(?:download|service|usage) (?:fee|charge)s?|(?:pay|cost)\s+(?:₹|rs\b|inr\b|\d))", text, re.I))


def connectivity_claim(text: str) -> bool:
    return bool(re.search(r"\b(?:requires?|needs?) (?:an? )?(?:(?:active|stable|working) )?(?:internet|wi-fi|network)\b|"
                          r"\b(?:works?|use) (?:fully )?offline\b|"
                          r"\b(?:works?|use) without (?:an? )?internet\b", text, re.I))


def scoped_match(intent: str, raw: str) -> float:
    text = normalize_query(re.sub(r"^Q:.*?(?:\n| )A:\s*", "", raw, flags=re.S))
    if intent in {"download_cost", "service_cost"}:
        if pricing_claim(text):
            relevant = "download" in text or "install" in text
            return 1.15 if relevant == (intent == "download_cost") else 0.0
        return float(intent == "download_cost" and "play.google.com/" in text and "apps.apple.com/" in text)
    if intent in {"international_scope", "epassport_scope"}:
        domestic = "domestic flights" in text and ("supported airports" in text or "integration may vary" in text)
        roadmap = bool(re.search(r"\be[- ]?passports?\b", text)) and "roadmap" in text
        # Verified official trial evidence (date-bounded; expired rows are filtered by the retriever).
        full = normalize_query(raw)  # includes an official FAQ's question, which carries the trial context
        trial = "international" in full and bool(re.search(r"\btrials?\b|\bdy-?ipt\b", full))
        if intent == "epassport_scope":
            return 1.2 if trial and re.search(r"\be[- ]?passports?\b", text) else (
                1.15 if roadmap else (0.9 if domestic else 0.0))
        return 1.12 if trial else (1.1 if domestic else 0.0)
    if intent == "face_verification":
        if all(w in text for w in ("lighting", "background", "camera steady")):
            return 1.15
        return float(all(w in text for w in ("system is down", "manual", "identity verification", "boarding")))
    if intent == "digilocker_comparison":
        if all(w in text for w in ("digilocker", "aadhaar", "digital credential")):
            return 1.12
        if "facial verification" in text and "e-gate" in text and "identity" in text:
            return 1.1
        return float(all(w in text for w in ("digilocker", "aadhaar", "registration", "selfie")))
    if intent == "connectivity":
        if connectivity_claim(text):
            return 1.15
        # Choose the journey stages rather than an unrelated login error or Offline Aadhaar alone.
        if all(w in text for w in ("registration", "otp", "selfie")):
            return 1.08
        gates = "facial verification" in text and ("e-gate" in text or "boarding gate" in text)
        sharing = all(w in text for w in ("boarding pass", "share", "airport"))
        if gates and sharing:
            return 1.1
        if sharing and not re.search(r"\b(child|children|minor|infant)\b", text):
            return 1.03
        return float(gates)
    return 0.0


def intent_match(intent: str | None, chunk: dict) -> float:
    """Promotion requires anchors in the approved chunk itself, not just its filename."""
    if intent in SCOPED_INTENTS:
        return scoped_match(intent, chunk["text"])
    text = normalize_query(chunk["text"])
    if intent == "organization":
        if "not-for-profit" in text and "section 8" in text:
            return 1.1 if "ministry of civil aviation" in text else (1.05 if "who operates" in text else 1.0)
        return 0.7 if "ministry of civil aviation" in text and "digi yatra" in text else 0.0
    if intent == "airport_catalog":
        if re.search(r"(?m)^\d+\.\s*\([A-Z]{3}\)", chunk["text"]):
            return 1.0 if "currently support" in text and "planned" not in text else 0.0
        return 0.65 if "currently support" in text and "planned" not in text else 0.0
    if intent == "airport_planned":
        return float("planned" in text and "airports" in text)
    if intent == "airport_retention":
        if "airport" in text and ("purge" in text or "purged" in text) and re.search(r"\b\d+\s*hours?\b", text) and "departure" in text:
            return 1.0
        return 0.65 if "airport" in text and "retention" in text and "biometric" in text else 0.0
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

"""Hybrid retrieval: vector similarity (LanceDB) + BM25 keyword ranking, with
approval filtering, duplicate suppression, per-source caps and score thresholds."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field, replace

from app.rag.embeddings import Embedder, features, tokenize
from app.rag.query import INTENT_TERMS, intent_match, normalize_query, query_intent
from app.rag.store import KnowledgeIndex

# Query expansion for common passenger phrasings (applied to keyword ranking only).
SYNONYMS: dict[str, str] = {
    "register": "registration enrol enrollment",
    "registration": "register enrol enrollment",
    "enrol": "registration enrollment",
    "enroll": "registration enrollment",
    "sign up": "registration register",
    "signup": "registration register",
    "don't have": "without",
    "do not have": "without",
    "doesn't have": "without",
    "does not have": "without",
    "no aadhaar": "without aadhaar",
    "launched": "introduced",
    "launch": "introduced",
    "started": "introduced",
    "kid": "child minor",
    "kids": "children minor",
    "child": "minor dependent",
    "children": "minor dependent",
    "son": "child minor",
    "daughter": "child minor",
    "baby": "infant",
    "infants": "infant",
    "toddler": "infant child",
    "wife": "spouse adult pnr",
    "husband": "spouse adult pnr",
    "family": "minor dependent adult",
    "delete": "uninstall remove",
    "remove": "delete uninstall",
    "deactivate": "delete uninstall",
    "aadhar": "aadhaar",
    "adhaar": "aadhaar",
    "adhar": "aadhaar",
    "bp": "boarding pass",
    "ticket": "boarding pass",
    "hindi": "language regional",
    "tamil": "language regional",
    "languages": "language",
    "abroad": "international",
    "foreigner": "foreign citizens",
    "nri": "foreign international",
    "otp": "otp",
    "safe": "security privacy",
    "hack": "security breach",
    "stored": "storage store",
    "lost": "lose change phone",
    "new phone": "change phone device",
    "cities": "airports",
    "city": "airport",
    "gates": "gate e-gate",
    "crash": "crashing freezing hanging",
    "selfie": "selfie face capture",
    "photo": "selfie photo",
    "turban": "turban",
    "complaint": "customer care support contact email",
    "contact": "customer care email support",
    "email": "customercare email contact",
}


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_file: str
    doc_title: str
    section: str
    text: str
    question: str | None
    score: float
    vector_score: float
    keyword_score: float
    coverage: float
    time_sensitive: bool
    as_of: str | None
    verification_status: str
    conflict_ids: list[str]
    urls: list[str]
    category: str
    extra: dict = field(default_factory=dict)


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def max_score(self, terms: list[str]) -> float:
        """Upper bound of a document's score for these terms; unseen terms count with maximal IDF,
        so queries about things absent from the corpus get low normalised scores."""
        n = len(self.docs)
        unseen_idf = math.log(1 + (n + 0.5) / 0.5)
        return sum(self.idf.get(t, unseen_idf) * (self.k1 + 1) for t in set(terms))

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for d, dl in zip(self.docs, self.lens):
            s = 0.0
            for t in query:
                tf = d.get(t)
                if not tf:
                    continue
                s += self.idf.get(t, 0.0) * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            out.append(s)
        return out


def expand_query(query: str) -> str:
    query = normalize_query(query)
    low = query
    extra = [v for k, v in SYNONYMS.items() if re.search(rf"\b{re.escape(k)}\b", low) and v]
    if intent := query_intent(query):
        extra.append(INTENT_TERMS[intent])
    return query + (" " + " ".join(extra) if extra else "")


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class Retriever:
    def __init__(
        self,
        index: KnowledgeIndex,
        embedder: Embedder,
        *,
        candidates: int = 30,
        vector_weight: float = 0.45,
        min_score: float = 0.15,
        max_per_source: int = 2,
    ) -> None:
        self.index = index
        self.embedder = embedder
        self.candidates = candidates
        self.vector_weight = vector_weight
        self.min_score = min_score
        self.max_per_source = max_per_source
        self.reload()

    def reload(self) -> None:
        self._chunks = sorted(self.index.all_chunks(approved_only=True), key=lambda c: (c["order"], c["chunk_id"]))
        self._positions = {c["chunk_id"]: i for i, c in enumerate(self._chunks)}
        self._by_id = {c["chunk_id"]: c for c in self._chunks}
        self._faq_groups: dict[tuple, list[dict]] = {}
        for c in self._chunks:
            if c.get("question"):
                self._faq_groups.setdefault((c["source_file"], c["section"], c["question"]), []).append(c)
        self.corpus_revision = hashlib.sha256(json.dumps(self._chunks, sort_keys=True, default=str).encode()).hexdigest()
        # URLs and file paths otherwise drown out the short FAQ / store-listing text.
        self._tokens = [tokenize(normalize_query(re.sub(r"https?://\S+", " ", c["embed_text"]))) for c in self._chunks]
        self._bm25 = BM25(self._tokens)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def lookup(self, chunk_id: str) -> dict | None:
        """Citation lookup: only approved, indexed chunks resolve."""
        return self._by_id.get(chunk_id)

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not query.strip() or not self._chunks:
            return []
        expanded = expand_query(query)
        q_terms = list(dict.fromkeys(tokenize(expanded)))
        q_core = set(tokenize(normalize_query(query))) - {"digi", "yatra"}
        intent = query_intent(query)

        # 1) keyword ranking over all approved chunks
        bm = self._bm25.scores(q_terms)
        # Absolute normalisation against the original (unexpanded) query terms.
        bm_max = self._bm25.max_score(tokenize(normalize_query(query))) * 0.6

        # 2) vector candidates (approval filter applied inside LanceDB)
        vec_rows = self.index.vector_search(self.embedder.embed_query(expanded), self.candidates, approved_only=True)
        vec_score = {r["chunk_id"]: r["vector_score"] for r in vec_rows}

        candidate_ids = set(vec_score)
        ranked_bm = sorted(range(len(bm)), key=lambda i: bm[i], reverse=True)[: self.candidates]
        candidate_ids.update(self._chunks[i]["chunk_id"] for i in ranked_bm if bm[i] > 0)
        # An approved FAQ that directly addresses a recognized intent gets a chance
        # even if colloquial wording missed both initial candidate lists.
        candidate_ids.update(c["chunk_id"] for c in self._chunks if intent_match(intent, c))

        scored: list[RetrievedChunk] = []
        for cid in candidate_ids:
            i = self._positions.get(cid)
            if i is None:
                continue  # not approved / not in memory
            c = self._chunks[i]
            kw = min(1.0, bm[i] / bm_max) if bm_max > 0 else 0.0
            doc_terms = set(self._tokens[i])
            coverage = len(q_core & doc_terms) / len(q_core) if q_core else 0.0
            vs = vec_score.get(cid, 0.0)
            score = self.vector_weight * vs + (1 - self.vector_weight) * (0.5 * kw + 0.5 * coverage)
            relevance = intent_match(intent, c)
            score = min(1.0, score + 0.55 * relevance)
            scored.append(
                RetrievedChunk(
                    chunk_id=cid,
                    source_file=c["source_file"],
                    doc_title=c["doc_title"],
                    section=c["section"],
                    text=c["text"],
                    question=c.get("question"),
                    score=round(score, 4),
                    vector_score=round(vs, 4),
                    keyword_score=round(kw, 4),
                    coverage=round(coverage, 4),
                    time_sensitive=bool(c.get("time_sensitive")),
                    as_of=c.get("as_of"),
                    verification_status=c.get("verification_status") or "not_applicable",
                    conflict_ids=list(c.get("conflict_ids") or []),
                    urls=list(c.get("urls") or []),
                    category=c.get("category") or "",
                )
            )
        scored.sort(key=lambda r: (r.score, intent_match(intent, {"text": r.text}),
                                   r.keyword_score, r.vector_score, r.chunk_id), reverse=True)

        # Platform/download questions need store evidence, not nearby device-error FAQs.
        if intent in {"app_download", "boarding_upload", "boarding_pdf", "boarding_scan", "airport_catalog", "airport_planned"}:
            direct = [r for r in scored if intent_match(intent, {"text": r.text}) >= (0.8 if intent == "boarding_scan" else 0.9)]
            if direct:
                scored = direct

        # Reassemble approved parts of the SAME FAQ before caps/budgets. A short
        # count/link fragment must not displace its actual list or procedure.
        assembled, seen_groups = [], set()
        for hit in scored:
            key = (hit.source_file, hit.section, hit.question)
            if hit.question and key in seen_groups:
                continue
            seen_groups.add(key)
            parts = self._faq_groups.get(key, [])
            if len(parts) > 1:
                bodies = list(dict.fromkeys(re.sub(r"^Q:.*?\nA:\s*", "", p["text"], flags=re.S) for p in parts))
                dates = {p.get("as_of") for p in parts}
                hit = replace(hit, text=f"Q: {hit.question}\nA: " + "\n\n".join(bodies),
                    time_sensitive=any(p.get("time_sensitive") for p in parts),
                    as_of=next(iter(dates)) if len(dates) == 1 else None,
                    verification_status="unverified" if any(p.get("verification_status") == "unverified" for p in parts) else hit.verification_status,
                    conflict_ids=list(dict.fromkeys(cid for p in parts for cid in p.get("conflict_ids", []))),
                    urls=list(dict.fromkeys(url for p in parts for url in p.get("urls", []))),
                    extra={"source_chunks": [p["chunk_id"] for p in parts]})
            assembled.append(hit)
        scored = assembled

        # 3) threshold, duplicate suppression, per-source cap
        selected: list[RetrievedChunk] = []
        seen_feats: list[set[str]] = []
        per_source: Counter = Counter()
        for r in scored:
            if r.score < self.min_score:
                break
            feats = set(features(r.text))
            if any(_jaccard(feats, s) > 0.6 for s in seen_feats):
                continue
            if per_source[r.source_file] >= self.max_per_source:
                continue
            selected.append(r)
            seen_feats.append(feats)
            per_source[r.source_file] += 1
            if len(selected) >= top_k:
                break
        return selected

    def retry_search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Second lexical/FAQ phrasing pass, with identical approval and score filters."""
        intent = query_intent(query)
        alternate = INTENT_TERMS.get(intent, expand_query(query))
        hits = self.search(alternate, max(top_k, 10))
        hits.sort(key=lambda h: (bool(h.question), intent_match(intent, {"text": h.text}), h.score), reverse=True)
        return hits[:top_k]

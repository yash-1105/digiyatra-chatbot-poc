"""Embedding abstraction.

Two implementations:
  * LexicalEmbedder  — deterministic hashed TF-IDF vectors (word unigrams + bigrams).
                       This is a LEXICAL representation, not a neural semantic embedding.
  * SarvamEmbedder   — hosted `embeddinggemma-2` (768-d neural embeddings), used only
                       when the API key has Provisioned Throughput access.

The index records which embedder built it; queries must use the same one
(`python -m app.cli reindex` migrates between them).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np

STOPWORDS = frozenset(
    """a an the and or but if of to in on at for from by with as is are was were be been being it its this that these
    those i me my we our you your he she they them their do does did doing have has had having can could would should
    will shall may might must not no yes so than then there here what which who whom when where why how all any both each
    few more most other some such only own same too very just about into over after before again further once also""".split()
)

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokenize(text: str) -> list[str]:
    toks = _TOKEN.findall(text.lower().replace("digiyatra", "digi yatra"))
    out = []
    for t in toks:
        if t in STOPWORDS or len(t) == 1:
            continue
        # light stemming
        for suf in ("ing", "ed", "es", "s"):
            if len(t) > 4 and t.endswith(suf) and not t.endswith("ss"):
                t = t[: -len(suf)]
                break
        out.append(t)
    return out


def features(text: str) -> list[str]:
    toks = tokenize(text)
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


class Embedder(Protocol):
    name: str
    kind: str  # "lexical" | "neural"
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def describe(self) -> dict: ...


class LexicalEmbedder:
    """Hashed TF-IDF with sublinear TF and L2 normalisation (cosine-ready)."""

    kind = "lexical"

    def __init__(self, dim: int = 4096, idf: dict[int, float] | None = None, n_docs: int = 0) -> None:
        self.dim = dim
        self.idf = idf or {}
        self.n_docs = n_docs
        self.name = f"lexical-hashed-tfidf-{dim}"

    @staticmethod
    def _bucket(feature: str, dim: int) -> int:
        return int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big") % dim

    def fit(self, texts: list[str]) -> LexicalEmbedder:
        df: Counter = Counter()
        for t in texts:
            df.update({self._bucket(f, self.dim) for f in features(t)})
        self.n_docs = len(texts)
        self.idf = {b: math.log((1 + self.n_docs) / (1 + c)) + 1.0 for b, c in df.items()}
        return self

    def _vector(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        default_idf = math.log(1 + self.n_docs) + 1.0 if self.n_docs else 1.0
        for b, tf in Counter(self._bucket(f, self.dim) for f in features(text)).items():
            vec[b] = (1 + math.log(tf)) * self.idf.get(b, default_idf)
        norm = float(np.linalg.norm(vec))
        return (vec / norm).tolist() if norm else vec.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def describe(self) -> dict:
        return {"name": self.name, "kind": self.kind, "dim": self.dim, "neural": False}

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"dim": self.dim, "n_docs": self.n_docs, "idf": self.idf}))

    @classmethod
    def load(cls, path: Path) -> LexicalEmbedder:
        data = json.loads(path.read_text())
        return cls(dim=data["dim"], idf={int(k): v for k, v in data["idf"].items()}, n_docs=data["n_docs"])


class EmbeddingUnavailable(RuntimeError):
    pass


class SarvamEmbedder:
    """Hosted embeddinggemma-2 via POST /v2/embeddings (OpenAI-compatible)."""

    kind = "neural"
    dim = 768
    QUERY_PREFIX = "task: search result | query: "
    DOC_PREFIX = "title: none | text: "

    def __init__(self, api_key: str, base_url: str, model: str = "embeddinggemma-2", timeout: float = 30.0) -> None:
        self._key = api_key
        self._url = f"{base_url.rstrip('/')}/v2/embeddings"
        self.model = model
        self.timeout = timeout
        self.name = f"sarvam-{model}"

    def _post(self, inputs: list[str]) -> list[list[float]]:
        try:
            resp = httpx.post(
                self._url,
                headers={"api-subscription-key": self._key, "Content-Type": "application/json"},
                json={"model": self.model, "input": inputs},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailable(f"network error: {type(exc).__name__}") from None
        if resp.status_code != 200:
            code, msg = "", ""
            try:
                err = resp.json().get("error", {})
                code, msg = err.get("code", ""), str(err.get("message", ""))[:200].replace(self._key, "[REDACTED]")
            except (ValueError, AttributeError):
                pass
            raise EmbeddingUnavailable(f"HTTP {resp.status_code} {code}: {msg}".strip(" :"))
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            out += self._post([self.DOC_PREFIX + t for t in texts[i : i + 32]])
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._post([self.QUERY_PREFIX + text])[0]

    def describe(self) -> dict:
        return {"name": self.name, "kind": self.kind, "dim": self.dim, "neural": True}

    def probe(self) -> tuple[bool, str]:
        try:
            vec = self._post([self.QUERY_PREFIX + "probe"])[0]
            return True, f"ok ({len(vec)} dimensions)"
        except EmbeddingUnavailable as exc:
            return False, str(exc)

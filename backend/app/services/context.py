"""Lossless context budgeting and a narrow, bounded public-FAQ cache."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

from app.rag.query import normalize_query
from app.services.usage import estimate_tokens


def select_context(hits, budget: int, top_k: int):
    selected, seen, used = [], set(), 0
    for hit in hits:
        if hit.chunk_id in seen or len(selected) >= top_k:
            continue
        # Never remove a conflicting partner just to save tokens.
        group = [h for h in hits if set(h.conflict_ids) & set(hit.conflict_ids)] if hit.conflict_ids else [hit]
        group = [h for h in group if h.chunk_id not in seen]
        cost = sum(estimate_tokens(h.text) + 80 for h in group)
        if used + cost > budget:
            continue  # retain complete approved chunks; never truncate facts or Hindi text
        selected.extend(group)
        seen.update(h.chunk_id for h in group)
        used += cost
    return selected


def limited_history(turns, budget: int, limit: int):
    selected, used = [], 0
    for turn in reversed(turns[-limit:]):
        cost = estimate_tokens(turn.content) + 10
        if used + cost > budget:
            break
        selected.append(turn)
        used += cost
    return list(reversed(selected))


_CACHE_QUESTIONS = {
    "can i use digi yatra on android?",
    "is digi yatra only for ios?",
    "where can i download digi yatra?",
    "how do i register for digi yatra?",
    "where do i upload my boarding pass?",
    "how do i upload a pdf from my phone?",
    "what is an otp?",
    "what is nfc?",
    "what does qr code mean?",
    "what is android?",
}


def faq_key(question: str) -> str | None:
    q = normalize_query(question).rstrip("?.! ")
    return q if q in {normalize_query(s).rstrip("?.! ") for s in _CACHE_QUESTIONS} else None


class FAQCache:
    def __init__(self, ttl: int = 300, limit: int = 256):
        self.ttl, self.limit = ttl, limit
        self._items = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._items.get(key)
            if not item or time.monotonic() - item[0] >= self.ttl:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return item[1].model_copy(deep=True)

    def put(self, key, response):
        if not self.ttl:
            return
        with self._lock:
            self._items[key] = (time.monotonic(), response.model_copy(deep=True))
            self._items.move_to_end(key)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

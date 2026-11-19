"""Server-side conversation memory (bounded, TTL-based, in-process).

The server's own record of a conversation is authoritative. Client-supplied
history is only used to recover *user* turns when the server has no record
(e.g. after a restart) — client-supplied assistant turns are never trusted.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str
    content: str


@dataclass
class Conversation:
    turns: list[Turn] = field(default_factory=list)
    touched: float = field(default_factory=time.monotonic)


class ConversationStore:
    def __init__(self, max_conversations: int = 2000, ttl_s: float = 3600, max_turns: int = 20) -> None:
        self._data: OrderedDict[str, Conversation] = OrderedDict()
        self._lock = threading.Lock()
        self.max_conversations = max_conversations
        self.ttl_s = ttl_s
        self.max_turns = max_turns

    def _evict(self) -> None:
        now = time.monotonic()
        for key in [k for k, c in self._data.items() if now - c.touched > self.ttl_s]:
            del self._data[key]
        while len(self._data) > self.max_conversations:
            self._data.popitem(last=False)

    def history(self, conversation_id: str) -> list[Turn] | None:
        with self._lock:
            self._evict()
            conv = self._data.get(conversation_id)
            return list(conv.turns) if conv else None

    def append(self, conversation_id: str, user: str, assistant: str) -> None:
        with self._lock:
            conv = self._data.setdefault(conversation_id, Conversation())
            conv.turns += [Turn("user", user), Turn("assistant", assistant)]
            conv.turns = conv.turns[-self.max_turns :]
            conv.touched = time.monotonic()
            self._data.move_to_end(conversation_id)
            self._evict()

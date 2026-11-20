"""Whole-passage context and history budgeting."""

from __future__ import annotations

from app.rag.query import evidence_tokens
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
    for turn in reversed(turns[-limit:] if limit else []):
        cost = estimate_tokens(turn.content) + 10
        if used + cost > budget:
            break
        selected.append(turn)
        used += cost
    return list(reversed(selected))



def optimized_context(hits, query, budget, top_k, conflict_guidance):
    """Keep the original lead and favor novel query coverage among remaining whole chunks."""
    from app.services.prompts import format_evidence

    selected = []
    pending = list(hits)
    uncovered = evidence_tokens(query)
    coverage = {h.chunk_id: uncovered & evidence_tokens(h.text) for h in hits}
    # Deduplicate exact text only when its provenance and all caveat metadata agree.
    seen = set()
    while pending:
        if selected:
            pending.sort(key=lambda h: (len(uncovered & coverage[h.chunk_id]), h.score), reverse=True)
        lead = pending.pop(0)
        group = [lead]
        conflicts = set(lead.conflict_ids)
        if conflicts:
            # Close transitively so nested conflict groups cannot be split.
            for member in group:
                conflicts.update(member.conflict_ids)
                for h in pending[:]:
                    if conflicts.intersection(h.conflict_ids):
                        group.append(h)
                        pending.remove(h)
        unique = []
        for h in group:
            identity = (h.source_file, h.section, h.text, h.time_sensitive, h.as_of,
                        h.verification_status, tuple(h.urls), tuple(h.conflict_ids))
            if identity not in seen:
                unique.append(h)
                seen.add(identity)
        proposed = [*selected, *unique]
        if len(proposed) > top_k and selected and not conflicts:
            continue
        if estimate_tokens(format_evidence(proposed, conflict_guidance)) > budget:
            continue
        selected = proposed
        for h in unique:
            uncovered -= coverage[h.chunk_id]
    return selected

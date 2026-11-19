"""Approval manifest loading. The manifest is the single source of truth for what may be indexed."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

VALID_STATUSES = {"approved", "draft", "historical", "irrelevant", "non_knowledge", "review_required", "duplicate"}


@dataclass
class FileRule:
    status: str
    category: str = "uncategorised"
    reason: str = ""
    notes: str = ""
    drop_sections: list[str] = field(default_factory=list)
    drop_patterns: list[str] = field(default_factory=list)
    time_sensitive: bool = False
    as_of: str | None = None
    verification_status: str | None = None
    in_manifest: bool = True


@dataclass
class Conflict:
    id: str
    topic: str
    files: list[str]
    description: str
    guidance: str
    keywords: list[str]


@dataclass
class Manifest:
    files: dict[str, FileRule]
    conflicts: list[Conflict]
    approval_authority: str
    redact_terms: list[str] = field(default_factory=list)

    def rule_for(self, filename: str) -> FileRule:
        rule = self.files.get(filename)
        if rule is None:
            return FileRule(
                status="review_required",
                category="unknown",
                reason="File is not listed in the approval manifest.",
                in_manifest=False,
            )
        return rule


def load_manifest(path: Path) -> Manifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    files: dict[str, FileRule] = {}
    for name, spec in data.get("files", {}).items():
        status = spec.get("status")
        if status not in VALID_STATUSES:
            raise ValueError(f"Manifest entry {name!r} has invalid status {status!r}")
        files[name] = FileRule(
            status=status,
            category=spec.get("category", "uncategorised"),
            reason=spec.get("reason", ""),
            notes=spec.get("notes", ""),
            drop_sections=list(spec.get("drop_sections", [])),
            drop_patterns=list(spec.get("drop_patterns", [])),
            time_sensitive=bool(spec.get("time_sensitive", False)),
            as_of=spec.get("as_of"),
            verification_status=spec.get("verification_status"),
        )
    conflicts = [
        Conflict(
            id=c["id"],
            topic=c["topic"],
            files=list(c["files"]),
            description=c["description"],
            guidance=c["guidance"],
            keywords=[k.lower() for k in c.get("keywords", [])],
        )
        for c in data.get("known_conflicts", [])
    ]
    return Manifest(
        files=files,
        conflicts=conflicts,
        approval_authority=data.get("approval_authority", ""),
        redact_terms=list(data.get("redact_terms", {}).get("terms", [])),
    )

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Candidate:
    source: str
    source_kind: str
    url: str
    text: str
    author: str = ""
    title: str = ""
    published_at: str = ""
    language: str = ""
    query: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ClassifiedCandidate:
    candidate: Candidate
    classification: str
    score: int
    reasons: list[str] = field(default_factory=list)
    reject_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = self.candidate.as_dict()
        payload.update(
            {
                "classification": self.classification,
                "score": self.score,
                "reasons": list(self.reasons),
                "reject_reason": self.reject_reason,
            }
        )
        return payload

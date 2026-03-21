from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class JobLead:
    job_key: str
    source_key: str
    source_name: str
    company: str
    title: str
    detail_url: str
    source_url: str
    location: str = ""
    posted_date: str = ""
    description: str = ""
    source_context: str = ""
    discovered_via: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    hub_matches: list[str] = field(default_factory=list)
    bucket: str = "discard"
    status: str = "active"
    first_seen: str = ""
    last_seen: str = ""
    expired_on: str = ""
    seen_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobLead":
        return cls(**payload)


@dataclass
class SourceReport:
    source_key: str
    source_name: str
    source_url: str
    status: str = "ok"
    total_fetched: int = 0
    total_relevant: int = 0
    used_browser: bool = False
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceReport":
        return cls(**payload)


@dataclass
class RunArtifacts:
    generated_at: str
    timezone: str
    jobs: list[JobLead]
    reports: list[SourceReport]


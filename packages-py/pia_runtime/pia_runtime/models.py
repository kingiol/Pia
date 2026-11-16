from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    REVIEWING = "REVIEWING"
    PAUSED = "PAUSED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    NO_ACTION = "NO_ACTION"
    RETRYABLE = "RETRYABLE"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    DONE = "DONE"


class DecisionStatus(StrEnum):
    BUY_CANDIDATE = "BUY_CANDIDATE"
    SELL_CANDIDATE = "SELL_CANDIDATE"
    HOLD = "HOLD"
    WATCH = "WATCH"
    NO_ACTION = "NO_ACTION"
    BLOCKED = "BLOCKED"


@dataclass(slots=True)
class Evidence:
    source: str
    title: str
    observed_at: str
    as_of: str
    expires_at: str
    quality: str
    excerpt: str
    snapshot_id: str
    source_uri: str | None = None
    source_type: str = "market"
    provider_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("evidence"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RuleReason:
    rule_id: str
    code: str
    severity: str
    actual: Any
    expected: Any
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RuleResult:
    decision: str
    reasons: list[RuleReason]
    warnings: list[RuleReason]
    rule_snapshot_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "rule_snapshot_id": self.rule_snapshot_id,
        }


@dataclass(slots=True)
class Decision:
    status: DecisionStatus
    confidence: str
    risk_level: str
    rationale: list[str]
    next_action: str
    invalidation: list[str]
    rule_result: RuleResult
    synthesis: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("decision"))
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "confidence": self.confidence,
            "risk_level": self.risk_level,
            "rationale": self.rationale,
            "next_action": self.next_action,
            "invalidation": self.invalidation,
            "rule_result": self.rule_result.to_dict(),
            "synthesis": self.synthesis,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class Task:
    id: str
    user_id: str
    trigger_type: str
    target: dict[str, Any]
    status: TaskStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    data_snapshot_id: str | None = None
    rule_snapshot_id: str | None = None
    error: dict[str, Any] | None = None
    parent_task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value

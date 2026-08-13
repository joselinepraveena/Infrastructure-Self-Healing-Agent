"""Domain models shared by the self-healing workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Decision(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    DRY_RUN = "dry_run"


class Outcome(StrEnum):
    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class Alert:
    alert_id: str
    name: str
    severity: str
    monitor_condition: str
    resource_id: str
    fired_at: datetime
    essentials: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Resource:
    resource_id: str
    subscription_id: str
    resource_group: str
    provider: str
    resource_type: str
    name: str
    tags: dict[str, str]
    default_hostname: str | None = None


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str


@dataclass
class HealingResult:
    alert_id: str
    resource_id: str
    decision: Decision
    outcome: Outcome
    reason: str
    action: str = "restart"
    validation_status: str = "not_run"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    attempt_count: int = 0

    def complete(self) -> HealingResult:
        self.completed_at = datetime.now(UTC)
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "alertId": self.alert_id,
            "resourceId": self.resource_id,
            "decision": self.decision.value,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "action": self.action,
            "validationStatus": self.validation_status,
            "attemptCount": self.attempt_count,
            "startedAt": self.started_at.isoformat(),
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }

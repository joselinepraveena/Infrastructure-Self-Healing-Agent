"""Fail-closed remediation policy."""

from __future__ import annotations

from .config import Settings
from .models import Alert, Decision, PolicyResult, Resource


def evaluate(alert: Alert, resource: Resource, settings: Settings) -> PolicyResult:
    tags = {key.lower(): value.strip() for key, value in resource.tags.items()}

    if alert.monitor_condition.lower() != "fired":
        return PolicyResult(Decision.DENIED, "Only fired alerts can trigger remediation")
    if alert.severity not in settings.allowed_severities:
        return PolicyResult(Decision.DENIED, "Alert severity is not allowlisted")
    if tags.get("selfheal", "").lower() != "enabled":
        return PolicyResult(Decision.DENIED, "Resource tag SelfHeal=Enabled is required")
    if tags.get("selfhealaction", "").lower() != "restart":
        return PolicyResult(Decision.DENIED, "Resource tag SelfHealAction=Restart is required")
    allowed_alerts = {
        item.strip().lower()
        for item in tags.get("selfhealalertrules", "").split(",")
        if item.strip()
    }
    if alert.name.lower() not in allowed_alerts:
        return PolicyResult(Decision.DENIED, "Alert rule is not allowlisted by the resource")
    if tags.get("selfhealpaused", "").lower() in {"true", "yes", "1"}:
        return PolicyResult(Decision.DENIED, "Self-healing is paused for this resource")
    environment = tags.get("environment", "").lower()
    if environment not in settings.allowed_environments:
        return PolicyResult(Decision.DENIED, "Resource environment is not allowlisted")
    if settings.dry_run:
        return PolicyResult(Decision.DRY_RUN, "Policy approved; dry-run mode prevented execution")
    return PolicyResult(Decision.APPROVED, "Policy approved")

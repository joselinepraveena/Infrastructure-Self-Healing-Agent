"""Azure Monitor common alert schema parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .models import Alert


class InvalidAlert(ValueError):
    """Raised when an alert cannot safely identify one remediation target."""


def _required(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidAlert(f"Missing or invalid alert field: {key}")
    return value.strip()


def parse_common_alert(payload: dict[str, Any]) -> Alert:
    """Parse one Azure Monitor common-schema alert.

    Multi-resource alerts are rejected because a remediation invocation must have
    a bounded blast radius.
    """
    try:
        essentials = payload["data"]["essentials"]
    except (KeyError, TypeError) as exc:
        raise InvalidAlert("Expected data.essentials common alert schema") from exc
    if not isinstance(essentials, dict):
        raise InvalidAlert("data.essentials must be an object")

    targets = essentials.get("alertTargetIDs")
    if not isinstance(targets, list) or len(targets) != 1 or not isinstance(targets[0], str):
        raise InvalidAlert("Exactly one alertTargetID is required")

    fired_raw = essentials.get("firedDateTime")
    if isinstance(fired_raw, str):
        try:
            fired_at = datetime.fromisoformat(fired_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidAlert("firedDateTime is not ISO-8601") from exc
    else:
        fired_at = datetime.now(UTC)

    return Alert(
        alert_id=_required(essentials, "alertId"),
        name=_required(essentials, "alertRule"),
        severity=_required(essentials, "severity"),
        monitor_condition=_required(essentials, "monitorCondition"),
        resource_id=targets[0].rstrip("/"),
        fired_at=fired_at,
        essentials=essentials,
    )

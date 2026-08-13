from datetime import UTC, datetime

import pytest

from self_healing.config import Settings
from self_healing.models import Alert, Decision, Resource
from self_healing.policy import evaluate


@pytest.fixture
def settings():
    return Settings(
        dry_run=False,
        allowed_environments=frozenset({"dev"}),
        allowed_severities=frozenset({"Sev2"}),
        cooldown_minutes=30,
        max_attempts=1,
        stabilization_seconds=0,
        validation_attempts=1,
        validation_timeout_seconds=1,
        state_table_name="attempts",
    )


@pytest.fixture
def alert():
    return Alert(
        alert_id="alert-1",
        name="high-5xx",
        severity="Sev2",
        monitor_condition="Fired",
        resource_id="/resource",
        fired_at=datetime.now(UTC),
    )


@pytest.fixture
def resource():
    return Resource(
        resource_id="/resource",
        subscription_id="sub",
        resource_group="rg",
        provider="Microsoft.Web",
        resource_type="sites",
        name="app",
        tags={
            "SelfHeal": "Enabled",
            "SelfHealAction": "Restart",
            "SelfHealAlertRules": "high-5xx",
            "Environment": "dev",
        },
    )


def test_approves_explicitly_allowlisted_resource(alert, resource, settings):
    assert evaluate(alert, resource, settings).decision is Decision.APPROVED


def test_fails_closed_without_opt_in_tag(alert, resource, settings):
    resource.tags.pop("SelfHeal")

    result = evaluate(alert, resource, settings)

    assert result.decision is Decision.DENIED
    assert "SelfHeal=Enabled" in result.reason


def test_denies_alert_rule_not_approved_for_resource(alert, resource, settings):
    resource.tags["SelfHealAlertRules"] = "latency-alert,dependency-alert"

    result = evaluate(alert, resource, settings)

    assert result.decision is Decision.DENIED
    assert "Alert rule" in result.reason


def test_dry_run_records_intent_without_approval(alert, resource, settings):
    dry_run = Settings(**{**settings.__dict__, "dry_run": True})

    result = evaluate(alert, resource, dry_run)

    assert result.decision is Decision.DRY_RUN

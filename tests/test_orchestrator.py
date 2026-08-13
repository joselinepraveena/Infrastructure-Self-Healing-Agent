from datetime import UTC, datetime

from self_healing.config import Settings
from self_healing.models import Alert, Decision, Outcome, Resource
from self_healing.orchestrator import HealingOrchestrator
from self_healing.state import Attempt


class Resources:
    def __init__(self, resource):
        self.resource = resource
        self.restarts = 0

    def get(self, resource_id):
        return self.resource

    def restart(self, resource):
        self.restarts += 1


class State:
    def __init__(self, attempt=None):
        self.attempt = attempt or Attempt(True, True, 1, "reserved", "p", "r")
        self.finished = []

    def begin(self, alert, resource, cooldown_minutes, max_attempts):
        return self.attempt

    def finish(self, attempt, result):
        self.finished.append(result)


class Validator:
    def __init__(self, healthy):
        self.healthy = healthy

    def validate(self, resource):
        return self.healthy


def settings(dry_run=False):
    return Settings(
        dry_run=dry_run,
        allowed_environments=frozenset({"dev"}),
        allowed_severities=frozenset({"Sev2"}),
        cooldown_minutes=30,
        max_attempts=1,
        stabilization_seconds=0,
        validation_attempts=1,
        validation_timeout_seconds=1,
        state_table_name="attempts",
    )


def alert():
    return Alert(
        "alert-1",
        "high-5xx",
        "Sev2",
        "Fired",
        "/resource",
        datetime.now(UTC),
    )


def resource():
    return Resource(
        "/resource",
        "sub",
        "rg",
        "Microsoft.Web",
        "sites",
        "app",
        {
            "SelfHeal": "Enabled",
            "SelfHealAction": "Restart",
            "SelfHealAlertRules": "high-5xx",
            "Environment": "dev",
        },
        "app.azurewebsites.net",
    )


def test_restarts_and_validates_approved_resource():
    resources = Resources(resource())
    state = State()
    agent = HealingOrchestrator(settings(), resources, state, Validator(True))

    result = agent.handle(alert())

    assert result.outcome is Outcome.SUCCEEDED
    assert result.validation_status == "passed"
    assert resources.restarts == 1
    assert len(state.finished) == 1


def test_validation_failure_is_a_failed_remediation():
    agent = HealingOrchestrator(settings(), Resources(resource()), State(), Validator(False))

    result = agent.handle(alert())

    assert result.outcome is Outcome.FAILED
    assert result.validation_status == "failed"


def test_dry_run_does_not_reserve_or_restart():
    resources = Resources(resource())
    state = State()
    result = HealingOrchestrator(settings(True), resources, state, Validator(True)).handle(alert())

    assert result.decision is Decision.DRY_RUN
    assert result.outcome is Outcome.SKIPPED
    assert resources.restarts == 0
    assert state.finished == []


def test_retry_limit_blocks_restart_and_records_denial():
    attempt = Attempt(False, True, 2, "Retry limit reached", "p", "r")
    resources = Resources(resource())
    state = State(attempt)

    result = HealingOrchestrator(settings(), resources, state, Validator(True)).handle(alert())

    assert result.decision is Decision.DENIED
    assert resources.restarts == 0
    assert len(state.finished) == 1

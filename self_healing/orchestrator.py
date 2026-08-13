"""Observe-decide-act-validate orchestration."""

from __future__ import annotations

import logging

from .config import Settings
from .models import Alert, Decision, HealingResult, Outcome
from .policy import evaluate
from .resources import ResourceService
from .state import StateStore
from .validation import Validator

LOGGER = logging.getLogger("self_healing")


class HealingOrchestrator:
    def __init__(
        self,
        settings: Settings,
        resources: ResourceService,
        state: StateStore,
        validator: Validator,
    ):
        self.settings = settings
        self.resources = resources
        self.state = state
        self.validator = validator

    def handle(self, alert: Alert) -> HealingResult:
        resource = self.resources.get(alert.resource_id)
        policy = evaluate(alert, resource, self.settings)
        result = HealingResult(
            alert_id=alert.alert_id,
            resource_id=resource.resource_id,
            decision=policy.decision,
            outcome=Outcome.SKIPPED,
            reason=policy.reason,
        )
        if policy.decision is not Decision.APPROVED:
            return self._emit(result.complete())

        attempt = self.state.begin(
            alert,
            resource,
            self.settings.cooldown_minutes,
            self.settings.max_attempts,
        )
        result.attempt_count = attempt.count
        if not attempt.accepted:
            result.decision = Decision.DENIED
            result.reason = attempt.reason
            result.complete()
            if attempt.created:
                self.state.finish(attempt, result)
            return self._emit(result)

        try:
            self.resources.restart(resource)
            healthy = self.validator.validate(resource)
            result.validation_status = "passed" if healthy else "failed"
            result.outcome = Outcome.SUCCEEDED if healthy else Outcome.FAILED
            result.reason = (
                "Resource recovered after restart"
                if healthy
                else "Restart completed but health validation failed"
            )
        except Exception as exc:
            LOGGER.exception("Remediation failed", extra={"alertId": alert.alert_id})
            result.outcome = Outcome.FAILED
            result.reason = f"Remediation failed: {type(exc).__name__}"
        finally:
            result.complete()
            self.state.finish(attempt, result)
        return self._emit(result)

    @staticmethod
    def _emit(result: HealingResult) -> HealingResult:
        LOGGER.info("Self-healing result", extra={"custom_dimensions": result.as_dict()})
        return result

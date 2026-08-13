"""Environment-backed runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    dry_run: bool
    allowed_environments: frozenset[str]
    allowed_severities: frozenset[str]
    cooldown_minutes: int
    max_attempts: int
    stabilization_seconds: int
    validation_attempts: int
    validation_timeout_seconds: int
    state_table_name: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            dry_run=_bool("DRY_RUN", True),
            allowed_environments=frozenset(
                item.strip().lower()
                for item in os.getenv("ALLOWED_ENVIRONMENTS", "dev,test,staging").split(",")
                if item.strip()
            ),
            allowed_severities=frozenset(
                item.strip()
                for item in os.getenv("ALLOWED_SEVERITIES", "Sev0,Sev1,Sev2,Sev3").split(",")
                if item.strip()
            ),
            cooldown_minutes=max(1, int(os.getenv("COOLDOWN_MINUTES", "30"))),
            max_attempts=max(1, int(os.getenv("MAX_ATTEMPTS", "1"))),
            stabilization_seconds=max(0, int(os.getenv("STABILIZATION_SECONDS", "30"))),
            validation_attempts=max(1, int(os.getenv("VALIDATION_ATTEMPTS", "3"))),
            validation_timeout_seconds=max(1, int(os.getenv("VALIDATION_TIMEOUT_SECONDS", "10"))),
            state_table_name=os.getenv("STATE_TABLE_NAME", "healingattempts"),
        )

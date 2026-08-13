"""Durable retry, cooldown, and alert-deduplication state."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .models import Alert, HealingResult, Resource


@dataclass(frozen=True)
class Attempt:
    accepted: bool
    created: bool
    count: int
    reason: str
    partition_key: str
    row_key: str


class StateStore(Protocol):
    def begin(
        self, alert: Alert, resource: Resource, cooldown_minutes: int, max_attempts: int
    ) -> Attempt: ...

    def finish(self, attempt: Attempt, result: HealingResult) -> None: ...


def _digest(value: str) -> str:
    return hashlib.sha256(value.lower().encode()).hexdigest()


class TableStateStore:
    """Azure Table Storage-backed attempt ledger."""

    def __init__(self, table_client: Any):
        self.table = table_client

    @classmethod
    def from_account_url(
        cls, account_url: str, table_name: str, credential: Any
    ) -> TableStateStore:
        from azure.data.tables import TableServiceClient

        service = TableServiceClient(endpoint=account_url, credential=credential)
        table = service.create_table_if_not_exists(table_name)
        return cls(table)

    def begin(
        self, alert: Alert, resource: Resource, cooldown_minutes: int, max_attempts: int
    ) -> Attempt:
        from azure.core.exceptions import ResourceExistsError

        partition_key = _digest(resource.resource_id)
        row_key = _digest(alert.alert_id)
        now = datetime.now(UTC)
        entity = {
            "PartitionKey": partition_key,
            "RowKey": row_key,
            "AlertId": alert.alert_id,
            "ResourceId": resource.resource_id,
            "StartedAt": now,
            "Status": "started",
        }
        try:
            self.table.create_entity(entity)
        except ResourceExistsError:
            return Attempt(False, False, 0, "Alert was already processed", partition_key, row_key)

        cutoff = now - timedelta(minutes=cooldown_minutes)
        query = "PartitionKey eq @partition and StartedAt ge @cutoff"
        attempts = list(
            self.table.query_entities(
                query_filter=query,
                parameters={"partition": partition_key, "cutoff": cutoff},
                select=["RowKey"],
            )
        )
        count = len(attempts)
        accepted = count <= max_attempts
        reason = "Attempt reserved" if accepted else "Retry limit reached during cooldown"
        return Attempt(accepted, True, count, reason, partition_key, row_key)

    def finish(self, attempt: Attempt, result: HealingResult) -> None:
        from azure.data.tables import UpdateMode

        self.table.update_entity(
            {
                "PartitionKey": attempt.partition_key,
                "RowKey": attempt.row_key,
                "Status": result.outcome.value,
                "Decision": result.decision.value,
                "Reason": result.reason,
                "ValidationStatus": result.validation_status,
                "CompletedAt": result.completed_at or datetime.now(UTC),
            },
            mode=UpdateMode.MERGE,
        )

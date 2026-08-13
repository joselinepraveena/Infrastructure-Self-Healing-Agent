from datetime import UTC

import pytest

from self_healing.alerts import InvalidAlert, parse_common_alert


def payload(targets=None):
    return {
        "schemaId": "azureMonitorCommonAlertSchema",
        "data": {
            "essentials": {
                "alertId": "alert-123",
                "alertRule": "high-5xx",
                "severity": "Sev2",
                "monitorCondition": "Fired",
                "firedDateTime": "2026-08-13T18:00:00Z",
                "alertTargetIDs": targets
                or ["/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Web/sites/app"],
            }
        },
    }


def test_parses_common_alert_schema():
    alert = parse_common_alert(payload())

    assert alert.alert_id == "alert-123"
    assert alert.resource_id.endswith("Microsoft.Web/sites/app")
    assert alert.fired_at.tzinfo == UTC


@pytest.mark.parametrize("targets", [[], ["one", "two"], None])
def test_rejects_unbounded_or_missing_targets(targets):
    body = payload(["placeholder"])
    body["data"]["essentials"]["alertTargetIDs"] = targets

    with pytest.raises(InvalidAlert):
        parse_common_alert(body)

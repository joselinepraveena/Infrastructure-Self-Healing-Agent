"""Azure Functions entry point for the self-healing agent."""

from __future__ import annotations

import json
import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential

from self_healing.alerts import InvalidAlert, parse_common_alert
from self_healing.config import Settings
from self_healing.orchestrator import HealingOrchestrator
from self_healing.resources import AzureResourceService, UnsupportedResource
from self_healing.state import TableStateStore
from self_healing.validation import HttpValidator

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
LOGGER = logging.getLogger("self_healing")
_orchestrator: HealingOrchestrator | None = None


def build_orchestrator() -> HealingOrchestrator:
    settings = Settings.from_env()
    credential = DefaultAzureCredential()
    account_url = os.environ["STATE_STORAGE_ACCOUNT_URL"]
    return HealingOrchestrator(
        settings=settings,
        resources=AzureResourceService(credential),
        state=TableStateStore.from_account_url(account_url, settings.state_table_name, credential),
        validator=HttpValidator(
            settings.stabilization_seconds,
            settings.validation_attempts,
            settings.validation_timeout_seconds,
        ),
    )


@app.function_name(name="HandleMonitorAlert")
@app.route(route="alerts", methods=["POST"])
def handle_monitor_alert(request: func.HttpRequest) -> func.HttpResponse:
    global _orchestrator
    try:
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise InvalidAlert("Request body must be a JSON object")
        alert = parse_common_alert(payload)
        if _orchestrator is None:
            _orchestrator = build_orchestrator()
        result = _orchestrator.handle(alert)
        return func.HttpResponse(
            json.dumps(result.as_dict()), status_code=200, mimetype="application/json"
        )
    except UnsupportedResource as exc:
        return func.HttpResponse(
            json.dumps({"error": str(exc)}), status_code=422, mimetype="application/json"
        )
    except (InvalidAlert, ValueError) as exc:
        return func.HttpResponse(
            json.dumps({"error": str(exc)}), status_code=400, mimetype="application/json"
        )
    except Exception:
        LOGGER.exception("Unhandled self-healing request failure")
        return func.HttpResponse(
            json.dumps({"error": "Internal processing failure"}),
            status_code=500,
            mimetype="application/json",
        )

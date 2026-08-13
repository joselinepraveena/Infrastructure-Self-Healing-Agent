# Azure Infrastructure Self-Healing Agent

A policy-controlled Azure Function that handles Azure Monitor common-schema
alerts and implements one intentionally narrow remediation pattern:

1. Parse an alert that targets exactly one resource.
2. Read the target App Service and its tags with managed identity.
3. Require explicit resource, action, severity, and environment allowlists.
4. Deduplicate alerts and enforce a retry limit in Azure Table Storage.
5. Restart the App Service.
6. Validate its HTTPS health endpoint.
7. Write a structured result to Application Insights and the attempt ledger.

The deployment defaults to dry-run mode. It never changes a resource until
`DRY_RUN=false` and all policy checks pass.

## Safety policy

Only top-level `Microsoft.Web/sites` resources are supported. A target must have:

| Tag | Required value | Purpose |
| --- | --- | --- |
| `SelfHeal` | `Enabled` | Explicitly opts the resource in |
| `SelfHealAction` | `Restart` | Approves this specific action |
| `SelfHealAlertRules` | Comma-separated exact rule names | Limits which alerts may act |
| `Environment` | An `ALLOWED_ENVIRONMENTS` value | Separates rollout stages |
| `SelfHealPaused` | Optional `true` | Emergency or maintenance stop |
| `SelfHealHealthPath` | Optional relative path, default `/health` | Recovery check |

Multi-resource alerts, resolved alerts, unsupported severities, malformed health
paths, duplicate alert IDs, and attempts over the cooldown limit fail closed.
The health URL always uses the Azure-reported App Service hostname over HTTPS;
the alert cannot provide an arbitrary URL.

## Project layout

```text
function_app.py             Azure Functions HTTP trigger
self_healing/               parsing, policy, Azure operations, state, validation
infra/main.bicep            Function App, identity, storage, monitoring, RBAC
tests/                      unit tests for policy and orchestration behavior
```

## Run locally

Python 3.12 is the deployed runtime.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest
ruff check .
```

Copy `local.settings.example.json` to `local.settings.json`, update the storage
URL, authenticate with `az login`, and start Azure Functions Core Tools with
`func start`. Keep `DRY_RUN=true` for local alert simulations.

## Deploy

The deployer needs permission to create role definitions and assignments.

```bash
az deployment group create \
  --resource-group <resource-group> \
  --template-file infra/main.bicep \
  --parameters namePrefix=<3-to-12-character-prefix> dryRun=true

zip -r function.zip function_app.py host.json requirements.txt self_healing
az functionapp deployment source config-zip \
  --resource-group <resource-group> \
  --name <functionAppName-output> \
  --src function.zip \
  --build-remote true
```

The custom remediation role is assigned at the deployment resource group so
the function can inspect tags and restart apps there. For a smaller blast
radius, move the generated role assignment to each approved App Service scope.
The function uses identity-based host and table storage; no storage key is put
in application settings.

After code deployment, create an Azure Monitor Action Group Azure Function
receiver for:

- Function App: the `functionAppName` deployment output
- Function: `HandleMonitorAlert`
- Common alert schema: enabled

Using the Azure Function receiver keeps the function access key out of the
template and alert configuration. Do not expose the endpoint as an anonymous
webhook.

## Rollout

1. Deploy with `dryRun=true` and send representative test alerts.
2. Confirm denials and intended actions in Application Insights.
3. Opt in a sandbox App Service with the required tags.
4. Set its health endpoint and test restart/recovery behavior manually.
5. Change `dryRun=false` only after the action group, RBAC scope, retry policy,
   alerts, endpoint, owner, and escalation path have been reviewed.
6. Add production to `allowedEnvironments` only as a separate approval.

Failed remediation is recorded and returned as an accepted workflow result; it
does not create an incident by itself. Route failed result logs to a separate
Azure Monitor alert and ITSM action group so escalation remains independent
from mutation.

Example Application Insights query:

```kusto
traces
| where message == "Self-healing result"
| extend d = todynamic(customDimensions.custom_dimensions)
| project timestamp, alertId=d.alertId, resourceId=d.resourceId,
          decision=d.decision, outcome=d.outcome,
          validation=d.validationStatus, reason=d.reason
| order by timestamp desc
```

## Configuration

| Setting | Default |
| --- | --- |
| `DRY_RUN` | `true` |
| `ALLOWED_ENVIRONMENTS` | `dev,test,staging` |
| `ALLOWED_SEVERITIES` | `Sev0,Sev1,Sev2,Sev3` |
| `COOLDOWN_MINUTES` | `30` |
| `MAX_ATTEMPTS` | `1` |
| `STABILIZATION_SECONDS` | `30` |
| `VALIDATION_ATTEMPTS` | `3` |
| `VALIDATION_TIMEOUT_SECONDS` | `10` |
| `STATE_TABLE_NAME` | `healingattempts` |

Configuration changes restart the Function App. Use Azure App Configuration and
Key Vault references if policies need independent lifecycle management.

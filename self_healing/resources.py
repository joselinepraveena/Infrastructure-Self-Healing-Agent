"""Azure resource discovery and App Service remediation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from .models import Resource

RESOURCE_ID = re.compile(
    r"^/subscriptions/(?P<subscription>[^/]+)/resourceGroups/(?P<group>[^/]+)"
    r"/providers/(?P<provider>[^/]+)/(?P<type>[^/]+)/(?P<name>[^/]+)$",
    re.IGNORECASE,
)


class UnsupportedResource(ValueError):
    pass


class ResourceService(Protocol):
    def get(self, resource_id: str) -> Resource: ...

    def restart(self, resource: Resource) -> None: ...


@dataclass
class AzureResourceService:
    """Resource operations authenticated by DefaultAzureCredential."""

    credential: Any

    def get(self, resource_id: str) -> Resource:
        match = RESOURCE_ID.fullmatch(resource_id)
        if not match:
            raise UnsupportedResource("Resource ID must identify one top-level Azure resource")
        values = match.groupdict()
        if values["provider"].lower() != "microsoft.web" or values["type"].lower() != "sites":
            raise UnsupportedResource("Only Microsoft.Web/sites is currently supported")

        from azure.mgmt.resource import ResourceManagementClient
        from azure.mgmt.web import WebSiteManagementClient

        resource_client = ResourceManagementClient(self.credential, values["subscription"])
        generic = resource_client.resources.get_by_id(resource_id, api_version="2023-12-01")
        web_client = WebSiteManagementClient(self.credential, values["subscription"])
        app = web_client.web_apps.get(values["group"], values["name"])

        return Resource(
            resource_id=resource_id,
            subscription_id=values["subscription"],
            resource_group=values["group"],
            provider=values["provider"],
            resource_type=values["type"],
            name=values["name"],
            tags={str(k): str(v) for k, v in (generic.tags or {}).items()},
            default_hostname=app.default_host_name,
        )

    def restart(self, resource: Resource) -> None:
        from azure.mgmt.web import WebSiteManagementClient

        client = WebSiteManagementClient(self.credential, resource.subscription_id)
        client.web_apps.restart(resource.resource_group, resource.name)

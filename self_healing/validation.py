"""Post-remediation App Service health validation."""

from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.request
from typing import Protocol

from .models import Resource


class Validator(Protocol):
    def validate(self, resource: Resource) -> bool: ...


class HttpValidator:
    def __init__(
        self,
        stabilization_seconds: int,
        attempts: int,
        timeout_seconds: int,
        sleeper=time.sleep,
    ):
        self.stabilization_seconds = stabilization_seconds
        self.attempts = attempts
        self.timeout_seconds = timeout_seconds
        self.sleeper = sleeper

    def validate(self, resource: Resource) -> bool:
        if not resource.default_hostname:
            return False
        tags = {key.lower(): value.strip() for key, value in resource.tags.items()}
        path = tags.get("selfhealhealthpath", "/health")
        if not path.startswith("/") or path.startswith("//") or "\\" in path:
            return False
        url = f"https://{resource.default_hostname}{path}"

        if self.stabilization_seconds:
            self.sleeper(self.stabilization_seconds)
        for number in range(self.attempts):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "azure-self-healing-agent/1.0"}
                )
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                    context=ssl.create_default_context(),
                ) as response:
                    if 200 <= response.status < 400:
                        return True
            except (urllib.error.URLError, TimeoutError):
                pass
            if number + 1 < self.attempts:
                self.sleeper(min(5 * (number + 1), 15))
        return False

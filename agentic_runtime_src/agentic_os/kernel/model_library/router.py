from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class ModelEndpoint:
    name: str
    provider: str = "unconfigured"
    enabled: bool = True
    base_url: str = ""
    capabilities: tuple[str, ...] = ("chat",)


class SequentialModelRouter:
    """Round-robin model router adapted from AIOS LLM routing."""

    def __init__(self, endpoints: list[ModelEndpoint]) -> None:
        self.endpoints = [endpoint for endpoint in endpoints if endpoint.enabled]
        self._idx = 0
        self._lock = Lock()

    def select(self, capability: str = "chat") -> ModelEndpoint | None:
        candidates = [endpoint for endpoint in self.endpoints if capability in endpoint.capabilities]
        if not candidates:
            return None
        with self._lock:
            endpoint = candidates[self._idx % len(candidates)]
            self._idx += 1
        return endpoint


class ModelLibrary:
    """Registry for edge/cloud/VLA model endpoints.

    This module intentionally does not call LLM APIs directly. It owns the
    kernel-side selection and metadata contract; concrete network clients can be
    mounted by runtime services.
    """

    def __init__(self, endpoints: list[ModelEndpoint] | None = None) -> None:
        self._endpoints = list(endpoints or [])
        self._router = SequentialModelRouter(self._endpoints)

    def register(self, endpoint: ModelEndpoint) -> None:
        self._endpoints.append(endpoint)
        self._router = SequentialModelRouter(self._endpoints)

    def route(self, capability: str = "chat") -> dict[str, Any]:
        endpoint = self._router.select(capability)
        if endpoint is None:
            return {"success": False, "error_code": "MODEL_ENDPOINT_NOT_FOUND", "capability": capability}
        return {"success": True, "endpoint": endpoint.__dict__}

    def list(self) -> list[dict[str, Any]]:
        return [endpoint.__dict__ for endpoint in self._endpoints]

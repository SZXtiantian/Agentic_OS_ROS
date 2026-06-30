from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4


SENSITIVE_KEY_PARTS = ("api_key", "apikey", "token", "secret", "password", "content", "messages", "prompt", "data")


@dataclass(frozen=True)
class KernelHookEvent:
    event_id: str
    event_type: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class KernelEventSink(Protocol):
    def emit(self, event_type: str, **metadata: Any) -> KernelHookEvent:
        ...

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        ...


class InMemoryKernelEventSink:
    def __init__(self, max_events: int = 1000) -> None:
        self.max_events = max_events
        self._events: list[KernelHookEvent] = []
        self._lock = Lock()

    def emit(self, event_type: str, **metadata: Any) -> KernelHookEvent:
        event = KernelHookEvent(
            event_id=f"kev_{uuid4().hex[:16]}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=sanitize_event_payload(metadata),
        )
        with self._lock:
            self._events.append(event)
            self._events = self._events[-self.max_events :]
        return event

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events[-limit:])
        return [event.to_dict() for event in events]

    def count(self) -> int:
        with self._lock:
            return len(self._events)


def sanitize_event_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered == "sanitized_metadata":
                sanitized[key_text] = sanitize_event_payload(item)
                continue
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = sanitize_event_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_event_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_event_payload(item) for item in value]
    return value

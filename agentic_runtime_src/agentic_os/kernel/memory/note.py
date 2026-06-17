from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RobotMemoryMetadata:
    robot_id: str = ""
    place_id: str = ""
    frame_id: str = ""
    pose: dict[str, float] = field(default_factory=dict)
    sensor_refs: list[str] = field(default_factory=list)
    safety_context: dict[str, Any] = field(default_factory=dict)
    retention_class: str = "task_log"
    privacy: str = "private"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryNote:
    content: Any
    id: str = field(default_factory=lambda: f"mem_{uuid4().hex}")
    owner_agent: str = ""
    user_id: str = ""
    context: str = ""
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    category: str = ""
    timestamp: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    sharing_policy: str = "private"
    memory_type: str = "episodic"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "owner_agent": self.owner_agent,
            "user_id": self.user_id,
            "context": self.context,
            "keywords": list(self.keywords),
            "tags": list(self.tags),
            "category": self.category,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
            "sharing_policy": self.sharing_policy,
            "memory_type": self.memory_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

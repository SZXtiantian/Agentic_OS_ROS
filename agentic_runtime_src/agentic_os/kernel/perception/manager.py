from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PerceptionFrame:
    source: str
    frame_type: str
    data: dict[str, Any]
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PerceptionManager:
    """Agent-friendly perception normalization layer."""

    def __init__(self) -> None:
        self._latest: dict[str, PerceptionFrame] = {}

    def ingest(self, source: str, frame_type: str, data: dict[str, Any]) -> PerceptionFrame:
        frame = PerceptionFrame(source=source, frame_type=frame_type, data=dict(data))
        self._latest[source] = frame
        return frame

    def latest(self, source: str | None = None) -> dict[str, Any]:
        if source is not None:
            frame = self._latest.get(source)
            return {"success": frame is not None, "frame": frame.to_dict() if frame else None}
        return {"success": True, "frames": {key: frame.to_dict() for key, frame in self._latest.items()}}

    def normalize_inspection(self, place: str, payload: dict[str, Any]) -> dict[str, Any]:
        anomalies = list(payload.get("anomalies") or [])
        objects = list(payload.get("objects") or [])
        summary = payload.get("summary") or (f"{place}检查完成，未发现异常。" if not anomalies else f"{place}检查完成，发现异常。")
        frame = self.ingest(
            source=f"inspection:{place}",
            frame_type="inspection",
            data={"place": place, "objects": objects, "anomalies": anomalies, "summary": summary},
        )
        return {"success": True, "inspection": frame.to_dict()}


from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result
from agentic_runtime.types import ObservationResult, PhotoCaptureResult


class PerceptionAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def observe(self, target: str = "workspace", timeout_s: int = 10) -> ObservationResult:
        result = await self.ctx.call_skill("perception.observe", {"target": target, "timeout_s": timeout_s})
        raise_for_result(result)
        return ObservationResult(
            success=True,
            summary=str(result.data.get("summary", "")),
            objects=list(result.data.get("objects", [])),
            evidence_path=str(result.data.get("evidence_path", "")),
            evidence=dict(result.data.get("evidence", {})),
        )

    async def capture_photo(self, target: str = "workspace", label: str = "photo", timeout_s: int = 5) -> PhotoCaptureResult:
        result = await self.ctx.call_skill(
            "perception.capture_photo",
            {"target": target, "label": label, "timeout_s": timeout_s},
        )
        raise_for_result(result)
        return PhotoCaptureResult(
            success=True,
            image_path=str(result.data.get("image_path", "")),
            metadata_path=str(result.data.get("metadata_path", "")),
            evidence=dict(result.data.get("evidence", {})),
            audit_id=result.audit_id,
        )

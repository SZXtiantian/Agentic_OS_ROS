from __future__ import annotations

from typing import Any


def run(args: dict[str, Any], context=None) -> dict[str, Any]:
    candidates = args.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_NOT_FOUND",
            "reason": "no color block candidates were provided",
        }
    indexed = [(index, candidate) for index, candidate in enumerate(candidates) if isinstance(candidate, dict)]
    if not indexed:
        return {
            "success": False,
            "error_code": "COLOR_BLOCK_NOT_FOUND",
            "reason": "color block candidates must be objects",
        }

    def score(item: tuple[int, dict[str, Any]]) -> tuple[float, float]:
        _, candidate = item
        confidence = float(candidate.get("confidence", 0.0) or 0.0)
        center = candidate.get("center") if isinstance(candidate.get("center"), dict) else {}
        x = float(center.get("x", 0.5) or 0.5)
        y = float(center.get("y", 0.5) or 0.5)
        centered = 1.0 - min(abs(x - 0.5) + abs(y - 0.5), 1.0)
        return confidence, centered

    index, selected = max(indexed, key=score)
    return {"success": True, "selected": selected, "index": index}

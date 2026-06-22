from __future__ import annotations

from typing import Any


SIMULATED_BACKEND_DISABLED = "SIMULATED_BACKEND_DISABLED"


def simulated_backend_disabled(source: str) -> dict[str, Any]:
    return {
        "success": False,
        "status": "failed",
        "error_code": SIMULATED_BACKEND_DISABLED,
        "message": f"{source} requested simulated backend mode, which is disabled for production entrypoints",
        "reason": "Configure a real backend/service or use isolated unit-test fixtures outside production runtime paths.",
    }

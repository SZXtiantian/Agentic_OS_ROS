from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agentic_os.kernel.world_model import WorldModel

from agentic_runtime.config import load_places, load_safety


class MockRosBridgeClient:
    def __init__(self, repo_root: Path, navigation_sleep_s: float = 0.05) -> None:
        self.repo_root = repo_root
        self.places = load_places(repo_root)
        self.world_model = WorldModel()
        self.world_model.load_places_data(self.places)
        self.safety = load_safety(repo_root)
        self.navigation_sleep_s = navigation_sleep_s
        self.navigation_calls: list[dict[str, Any]] = []
        self.stop_calls: list[dict[str, Any]] = []
        self.reports: list[str] = []
        self.estop_pressed = False
        self.is_localized = True

    async def resolve_place(self, name: str) -> dict[str, Any]:
        resolved = self.world_model.resolve_place(name)
        if not resolved.get("success"):
            return {"success": False, "error_code": resolved.get("error_code", "PLACE_NOT_FOUND"), "reason": f"unknown place: {name}"}
        place = dict(resolved.get("target") or {})
        return {
            "success": True,
            "place": {
                "id": place.get("id", name),
                "name": name,
                "frame_id": place.get("frame_id", "map"),
                "pose": place.get("pose", {}),
                "allowed": bool(place.get("allowed", True)),
                "metadata": place.get("metadata", {}),
            },
        }

    async def get_robot_state(self) -> dict[str, Any]:
        return {
            "success": True,
            "state": {
                "robot_id": "mock_robot",
                "mode": "mock",
                "battery_state": "normal",
                "battery_percent": 80.0,
                "is_localized": self.is_localized,
                "is_moving": False,
                "estop_pressed": self.estop_pressed,
                "current_place": "",
                "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
                "active_task_id": "",
                "state": {"source": "mock"},
            },
        }

    async def check_safety(self, skill_name: str, args: dict[str, Any], app_id: str) -> dict[str, Any]:
        del app_id
        if self.estop_pressed:
            return {"allowed": False, "error_code": "ESTOP_PRESSED", "reason": "estop is pressed"}
        if skill_name == "robot.navigate_to":
            place_name = args.get("place", "")
            resolved = await self.resolve_place(place_name)
            if not resolved.get("success"):
                return {
                    "allowed": False,
                    "error_code": resolved.get("error_code", "PLACE_NOT_FOUND"),
                    "reason": resolved.get("reason", "place not found"),
                }
            place = resolved["place"]
            forbidden = set(self.safety.get("forbidden_zones", []))
            if not place.get("allowed", True) or place.get("id") in forbidden:
                return {"allowed": False, "error_code": "FORBIDDEN_ZONE", "reason": f"forbidden place: {place_name}"}
            if not self.is_localized:
                return {"allowed": False, "error_code": "ROBOT_NOT_LOCALIZED", "reason": "robot is not localized"}
        return {"allowed": True, "error_code": "", "reason": ""}

    async def navigate_to(self, place: str, timeout_s: int, cancel_event=None) -> dict[str, Any]:
        self.navigation_calls.append({"place": place, "timeout_s": timeout_s})
        elapsed = 0.0
        step = 0.05
        while elapsed < self.navigation_sleep_s:
            if cancel_event is not None and cancel_event.is_set():
                return {"success": False, "error_code": "SKILL_CANCELLED", "reason": "navigation cancelled"}
            await asyncio.sleep(step)
            elapsed += step
        return {"success": True, "reason": "", "result": {"place": place, "mode": "mock"}}

    async def inspect_area(self, place: str, timeout_s: int) -> dict[str, Any]:
        del timeout_s
        return {
            "success": True,
            "summary": f"{place}检查完成，未发现异常。",
            "objects": ["table", "chair"],
            "anomalies": [],
        }

    async def stop_robot(self, reason: str) -> dict[str, Any]:
        self.stop_calls.append({"reason": reason})
        return {"success": True, "message": "stop accepted", "reason": reason}

    async def ask_human(
        self,
        question: str,
        options=None,
        timeout_s: int = 60,
        require_confirmation: bool = False,
    ) -> dict[str, Any]:
        del question, timeout_s, require_confirmation
        answer = options[0] if options else "ok"
        return {"answered": True, "answer": answer, "reason": "mock"}

    async def report_say(self, message: str) -> dict[str, Any]:
        self.reports.append(message)
        print(message)
        return {"success": True, "message": message}

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from agentic_os.kernel.world_model import WorldModel

from agentic_runtime.config import load_places, load_safety


def _write_mock_photo(image_path: Path, label: str) -> bool:
    try:
        import cv2
        import numpy as np
    except Exception:
        return False
    digest = hashlib.sha256(str(label).encode("utf-8")).digest()
    seed = digest[0]
    seed_b = digest[1] or 1
    seed_c = digest[2] or 1
    height, width = 400, 640
    x = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    y = np.tile(np.linspace(0, 255, height, dtype=np.uint8).reshape(height, 1), (1, width))
    image = np.dstack(
        (
            ((x.astype(np.uint16) + seed) % 255).astype(np.uint8),
            ((y.astype(np.uint16) + seed_b * 2) % 255).astype(np.uint8),
            ((x.astype(np.uint16) // 2 + y.astype(np.uint16) // 2 + seed_c * 3) % 255).astype(np.uint8),
        )
    )
    center = (int(80 + digest[3] % 480), int(80 + digest[4] % 240))
    color = (int(digest[5]), int(digest[6]), int(digest[7]))
    cv2.circle(image, center, 45 + int(digest[8] % 55), color, -1)
    cv2.line(image, (0, int(digest[9] % height)), (width - 1, int(digest[10] % height)), color, 5)
    cv2.putText(image, str(label), (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255 - seed, seed_b, seed_c), 3)
    return bool(cv2.imwrite(str(image_path), image))


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
        self.arm_calls: list[dict[str, Any]] = []
        self.gripper_calls: list[dict[str, Any]] = []
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
        if skill_name == "arm.move_named":
            name = {"camera_up": "camera_pitch_up_15"}.get(str(args.get("name", "")), args.get("name"))
            if name not in {
                "arm_home",
                "camera_center",
                "camera_yaw_left_15",
                "camera_yaw_right_15",
                "camera_pitch_up_15",
            }:
                return {"allowed": False, "error_code": "ARM_ACTION_NOT_ALLOWED", "reason": "arm action is not allowlisted"}
            if int(args.get("timeout_s", 8)) > 8:
                return {"allowed": False, "error_code": "ARM_TIMEOUT_LIMIT_EXCEEDED", "reason": "arm timeout exceeds max"}
        if skill_name == "gripper.set":
            command = args.get("command")
            force = args.get("force", "low")
            if command not in {"open", "open_gripper", "close", "close_gripper_low_force"}:
                return {"allowed": False, "error_code": "GRIPPER_COMMAND_NOT_ALLOWED", "reason": "gripper command is not allowlisted"}
            if force != "low":
                return {"allowed": False, "error_code": "GRIPPER_FORCE_NOT_ALLOWED", "reason": "gripper force is not allowlisted"}
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
            "objects": [],
            "anomalies": [],
            "evidence_path": "",
            "evidence": {"source": "mock_camera_metadata", "place": place, "perception_backend_status": "MOCK"},
        }

    async def observe(self, target: str, timeout_s: int) -> dict[str, Any]:
        del timeout_s
        return {
            "success": True,
            "summary": f"{target} camera metadata observation complete (mock).",
            "objects": [],
            "evidence_path": "",
            "evidence": {"source": "mock_camera_metadata", "target": target, "perception_backend_status": "MOCK"},
        }

    async def capture_photo(self, target: str, label: str, timeout_s: int) -> dict[str, Any]:
        del timeout_s
        timestamp = int(time.time())
        photo_dir = Path(os.environ.get("AGENTIC_PHOTO_EVIDENCE_ROOT", "/tmp/agentic_mock_photos"))
        photo_dir.mkdir(parents=True, exist_ok=True)
        image_path = photo_dir / f"{label}_{timestamp}.png"
        metadata_path = photo_dir / f"{label}_{timestamp}.json"
        evidence = {
            "source": "mock_camera_capture",
            "target": target,
            "label": label,
            "topic": "mock",
            "width": 640,
            "height": 400,
            "encoding": "bgr8",
            "image_path": str(image_path),
            "metadata_path": str(metadata_path),
            "perception_backend_status": "MOCK",
        }
        if not _write_mock_photo(image_path, label):
            image_path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="))
        metadata_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        with (photo_dir / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "photo", **evidence, "created_unix": time.time()}, ensure_ascii=False, sort_keys=True) + "\n")
        return {
            "success": True,
            "image_path": str(image_path),
            "metadata_path": str(metadata_path),
            "evidence": evidence,
        }

    async def get_arm_state(self) -> dict[str, Any]:
        return {
            "success": True,
            "state": {
                "readiness": "mock_ready",
                "active_action": "",
                "is_moving": False,
                "gripper_ready": True,
                "stop_available": False,
                "state": {"source": "mock"},
            },
        }

    async def move_arm_named(self, name: str, timeout_s: int, cancel_event=None) -> dict[str, Any]:
        self.arm_calls.append({"name": name, "timeout_s": timeout_s})
        if cancel_event is not None and cancel_event.is_set():
            return {"success": False, "error_code": "SKILL_CANCELLED", "reason": "arm action cancelled"}
        await asyncio.sleep(0.01)
        return {"success": True, "reason": "", "result": {"name": name, "mode": "mock"}}

    async def set_gripper(
        self,
        command: str,
        force: str = "low",
        percentage: float | None = None,
        timeout_s: int = 5,
    ) -> dict[str, Any]:
        self.gripper_calls.append({"command": command, "force": force, "percentage": percentage, "timeout_s": timeout_s})
        return {"success": True, "reason": "", "result": {"command": command, "force": force, "mode": "mock"}}

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

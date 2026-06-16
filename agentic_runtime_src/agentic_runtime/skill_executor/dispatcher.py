from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentic_runtime.ros_bridge_client.types import RosBridgeClient


class SkillDispatcher:
    def __init__(self, bridge_client: RosBridgeClient, memory_store) -> None:
        self.bridge_client = bridge_client
        self.memory_store = memory_store

    async def dispatch(
        self,
        skill_name: str,
        args: dict[str, Any],
        app_id: str,
        session_id: str,
        cancel_event=None,
    ) -> dict[str, Any]:
        if skill_name == "world.resolve_place":
            return await self.bridge_client.resolve_place(args["name"])
        if skill_name == "robot.get_state":
            return await self.bridge_client.get_robot_state()
        if skill_name == "robot.navigate_to":
            return await self.bridge_client.navigate_to(
                args["place"],
                int(args.get("timeout_s", 120)),
                cancel_event=cancel_event,
            )
        if skill_name == "robot.inspect_area":
            return await self.bridge_client.inspect_area(args["place"], int(args.get("timeout_s", 60)))
        if skill_name == "perception.observe":
            return await self.bridge_client.observe(args.get("target", "workspace"), int(args.get("timeout_s", 10)))
        if skill_name == "perception.capture_photo":
            return await self.bridge_client.capture_photo(
                args.get("target", "workspace"),
                args.get("label", "photo"),
                int(args.get("timeout_s", 5)),
            )
        if skill_name == "arm.get_state":
            return await self.bridge_client.get_arm_state()
        if skill_name == "arm.move_named":
            return await self.bridge_client.move_arm_named(
                args["name"],
                int(args.get("timeout_s", 8)),
                cancel_event=cancel_event,
            )
        if skill_name == "gripper.set":
            return await self.bridge_client.set_gripper(
                args["command"],
                force=str(args.get("force", "low")),
                percentage=args.get("percentage"),
                timeout_s=int(args.get("timeout_s", 5)),
            )
        if skill_name == "robot.stop":
            return await self.bridge_client.stop_robot(args.get("reason", "app_requested"))
        if skill_name == "memory.remember":
            self.memory_store.remember(app_id, session_id, args["key"], args.get("value"))
            return {"success": True}
        if skill_name == "memory.recall":
            return {"success": True, "value": self.memory_store.recall(app_id, args["key"])}
        if skill_name == "storage.list_recent_photos":
            return self._list_recent_photos(int(args.get("limit", 5)), app_id=app_id)
        if skill_name == "human.ask":
            return await self.bridge_client.ask_human(
                args["question"],
                options=args.get("options"),
                timeout_s=int(args.get("timeout_s", 60)),
                require_confirmation=bool(args.get("require_confirmation", False)),
            )
        if skill_name == "report.say":
            return await self.bridge_client.report_say(args["message"])
        return {"success": False, "error_code": "BACKEND_UNAVAILABLE", "reason": f"no dispatcher for {skill_name}"}

    def _list_recent_photos(self, limit: int, app_id: str = "") -> dict[str, Any]:
        app_index = self._app_photo_index(app_id)
        if app_index is not None and app_index.exists():
            app_result = self._read_photo_index(app_index, limit)
            if app_result.get("success") and app_result.get("photos"):
                app_result["source"] = "app_storage"
                return app_result
        photos_root = Path(os.environ.get("AGENTIC_PHOTO_EVIDENCE_ROOT", "/opt/agentic/var/evidence/photos"))
        index_path = photos_root / "index.jsonl"
        raw_result = self._read_photo_index(index_path, limit)
        raw_result["source"] = "runtime_raw_evidence"
        return raw_result

    def _app_photo_index(self, app_id: str) -> Path | None:
        if app_id != "robot_photographer_agent":
            return None
        storage_root = Path(
            os.environ.get(
                "AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT",
                "/home/ubuntu/agentic_ws/src/robot_photographer_agent/storage",
            )
        ).expanduser()
        return storage_root / "indexes" / "photos.jsonl"

    def _read_photo_index(self, index_path: Path, limit: int) -> dict[str, Any]:
        if not index_path.exists():
            return {"success": True, "photos": [], "index_path": str(index_path)}
        entries: list[dict[str, Any]] = []
        try:
            for line in index_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    entries.append(parsed)
        except (OSError, json.JSONDecodeError) as exc:
            return {"success": False, "error_code": "PHOTO_INDEX_CORRUPT", "reason": str(exc), "index_path": str(index_path)}
        return {"success": True, "photos": entries[-max(limit, 0) :], "index_path": str(index_path)}

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any

from agentic_runtime.config import find_repo_root
from agentic_runtime.human_channel import FileHumanQueueChannel
from agentic_runtime.ros_bridge_client.types import RosBridgeClient


class SkillDispatcher:
    def __init__(self, bridge_client: RosBridgeClient, memory_store, human_channel: FileHumanQueueChannel | None = None) -> None:
        self.bridge_client = bridge_client
        self.memory_store = memory_store
        self.human_channel = human_channel

    async def dispatch(
        self,
        skill_name: str,
        args: dict[str, Any],
        app_id: str,
        session_id: str,
        cancel_event=None,
        call_id: str = "",
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
            return await self.bridge_client.inspect_area(args["place"], int(args.get("timeout_s", 60)), request_id=call_id)
        if skill_name == "perception.observe":
            return await self.bridge_client.observe(args.get("target", "workspace"), int(args.get("timeout_s", 10)))
        if skill_name == "perception.capture_photo":
            return await self.bridge_client.capture_photo(
                args.get("target", "workspace"),
                args.get("label", "photo"),
                int(args.get("timeout_s", 5)),
            )
        if skill_name == "perception.detect_color_block":
            if hasattr(self.bridge_client, "detect_color_block"):
                return await self.bridge_client.detect_color_block(
                    color=args["color"],
                    target=args.get("target", "workspace"),
                    evidence_label=args.get("evidence_label", "color_block"),
                    timeout_s=int(args.get("timeout_s", 30)),
                )
            return _missing_color_block_backend(
                "COLOR_BLOCK_CAPABILITY_UNAVAILABLE",
                "bridge client does not expose detect_color_block",
                missing=["perception.detect_color_block"],
                next_action="Expose /agentic/perception/detect_color_block in the Agentic perception bridge.",
            )
        if skill_name == "perception.center_color_block":
            if hasattr(self.bridge_client, "center_color_block"):
                return await self.bridge_client.center_color_block(
                    color=args["color"],
                    target=args.get("target", "workspace"),
                    evidence_label=args.get("evidence_label", "center_color_block"),
                    timeout_s=int(args.get("timeout_s", 8)),
                )
            return _missing_color_block_backend(
                "COLOR_BLOCK_ALIGNMENT_UNAVAILABLE",
                "bridge client does not expose center_color_block",
                missing=["perception.center_color_block"],
                next_action="Expose /agentic/perception/center_color_block in the Agentic perception bridge.",
            )
        if skill_name == "perception.verify_held_color_block":
            if hasattr(self.bridge_client, "verify_held_color_block"):
                return await self.bridge_client.verify_held_color_block(
                    color=args["color"],
                    target=args.get("target", "workspace"),
                    detection=dict(args.get("detection") or {}),
                    pick_result=dict(args.get("pick_result") or {}),
                    evidence_label=args.get("evidence_label", "held_color_block"),
                    timeout_s=int(args.get("timeout_s", 30)),
                )
            return _missing_color_block_backend(
                "COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE",
                "bridge client does not expose verify_held_color_block",
                missing=["perception.verify_held_color_block"],
                next_action="Expose /agentic/perception/verify_held_color_block in the Agentic perception bridge.",
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
        if skill_name == "manipulation.pick_color_block":
            if hasattr(self.bridge_client, "pick_color_block"):
                return await self.bridge_client.pick_color_block(
                    color=args["color"],
                    target=args.get("target", "workspace"),
                    detection=dict(args.get("detection") or {}),
                    evidence=dict(args.get("evidence") or {}),
                    timeout_s=int(args.get("timeout_s", 60)),
                )
            return _missing_color_block_backend(
                "MANIPULATION_BACKEND_UNAVAILABLE",
                "bridge client does not expose pick_color_block",
                missing=["manipulation.pick_color_block"],
                next_action="Expose /agentic/manipulation/pick_color_block in the Agentic manipulation bridge.",
            )
        if skill_name == "manipulation.place_color_block":
            if hasattr(self.bridge_client, "place_color_block"):
                return await self.bridge_client.place_color_block(
                    color=args.get("color", ""),
                    place_target=args["place_target"],
                    pick_result=dict(args.get("pick_result") or {}),
                    timeout_s=int(args.get("timeout_s", 60)),
                )
            return _missing_color_block_backend(
                "MANIPULATION_BACKEND_UNAVAILABLE",
                "bridge client does not expose place_color_block",
                missing=["manipulation.place_color_block"],
                next_action="Expose /agentic/manipulation/place_color_block in the Agentic manipulation bridge.",
            )
        if skill_name == "robot.stop":
            return await self.bridge_client.stop_robot(args.get("reason", "app_requested"))
        if skill_name == "memory.remember":
            result = self.memory_store.remember(app_id, session_id, args["key"], args.get("value"))
            if isinstance(result, dict):
                if "success" not in result or not isinstance(result.get("success"), bool):
                    return {
                        "success": False,
                        "error_code": "MEMORY_RESULT_INVALID",
                        "reason": "memory remember result missing boolean success field",
                        "raw_type": type(result).__name__,
                    }
                return result if not result.get("success", False) else {"success": True, **result}
            return {
                "success": False,
                "error_code": "MEMORY_RESULT_INVALID",
                "reason": f"memory remember backend returned {type(result).__name__}",
            }
        if skill_name == "memory.recall":
            if hasattr(self.memory_store, "recall_result"):
                result = self.memory_store.recall_result(app_id, args["key"])
                if isinstance(result, dict):
                    if "success" not in result or not isinstance(result.get("success"), bool):
                        return {
                            "success": False,
                            "error_code": "MEMORY_RESULT_INVALID",
                            "reason": "memory recall result missing boolean success field",
                            "raw_type": type(result).__name__,
                        }
                    return result
                return {
                    "success": False,
                    "error_code": "MEMORY_RESULT_INVALID",
                    "reason": f"memory recall backend returned {type(result).__name__}",
                }
            return {
                "success": False,
                "error_code": "MEMORY_BACKEND_UNAVAILABLE",
                "reason": "memory backend does not implement recall_result contract",
            }
        if skill_name == "storage.list_recent_photos":
            return self._list_recent_photos(int(args.get("limit", 5)), app_id=app_id)
        if skill_name == "human.ask":
            if self.human_channel is None:
                return {"success": False, "answered": False, "answer": "", "error_code": "HUMAN_BACKEND_UNAVAILABLE"}
            return await self.human_channel.ask(
                question=args["question"],
                options=list(args.get("options") or []),
                timeout_s=int(args.get("timeout_s", 60)),
                require_confirmation=bool(args.get("require_confirmation", False)),
                app_id=app_id,
                session_id=session_id,
                correlation_id=str(args.get("correlation_id") or ""),
                cancel_event=cancel_event,
            )
        if skill_name == "report.say":
            return await self.bridge_client.report_say(args["message"])
        return {"success": False, "error_code": "BACKEND_UNAVAILABLE", "reason": f"no dispatcher for {skill_name}"}

    async def checkpoint_capability(
        self,
        skill_name: str,
        args: dict[str, Any],
        app_id: str,
        session_id: str,
        *,
        syscall_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checkpoint_method = getattr(self.bridge_client, "checkpoint_capability", None)
        if callable(checkpoint_method):
            result = checkpoint_method(
                skill_name=skill_name,
                args=dict(args),
                app_id=app_id,
                session_id=session_id,
                syscall_id=syscall_id,
                metadata=dict(metadata or {}),
            )
            if inspect.isawaitable(result):
                result = await result
            return result
        checkpoint_method = getattr(self.bridge_client, "checkpoint_request", None)
        if callable(checkpoint_method):
            result = checkpoint_method(syscall_id, skill_name=skill_name, session_id=session_id, metadata=dict(metadata or {}))
            if inspect.isawaitable(result):
                result = await result
            return result
        return {
            "success": False,
            "error_code": "SCHEDULER_PREEMPTION_UNSUPPORTED",
            "reason": "bridge client does not expose checkpoint capability",
            "skill_name": skill_name,
            "syscall_id": syscall_id,
        }

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
        app_root = Path(os.environ.get("AGENTIC_APP_ROOT", find_repo_root().parent / "agentic_apps")).expanduser()
        storage_root = Path(
            os.environ.get(
                "AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT",
                str(app_root / "robot_photographer_agent" / "storage"),
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


def _missing_color_block_backend(error_code: str, reason: str, *, missing: list[str], next_action: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": error_code,
        "reason": reason,
        "missing": missing,
        "next_action": next_action,
    }

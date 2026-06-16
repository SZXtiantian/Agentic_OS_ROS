from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from agentic_runtime.server import RuntimeServer

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from planner import plan_task
from validation import PhotoPlanValidationError, validate_plan


class RobotPhotographerAgent:
    def __init__(self, agent_name: str = "robot_photographer_agent", runtime: RuntimeServer | None = None, mock: bool = True) -> None:
        self.agent_name = agent_name
        self.runtime = runtime
        self.mock = mock

    def run(self, task_input: Any) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(task_input))
        raise RuntimeError("RobotPhotographerAgent.run cannot be called from an active event loop; use arun instead")

    async def arun(self, task_input: Any) -> dict[str, Any]:
        task = _normalize_task(task_input)
        runtime = self.runtime or RuntimeServer.create(mock=bool(task.get("mock", self.mock)))
        try:
            plan = plan_task(task, llm_chat=getattr(runtime, "llm_chat", None))
        except Exception as exc:
            return {
                "schema_version": "1.0",
                "success": False,
                "plan_id": "",
                "planner_mode": "",
                "steps": [],
                "error_code": "ROBOT_PHOTOGRAPHER_LLM_REQUIRED_FAILED",
                "reason": f"required LLM photo planning failed: {exc.__class__.__name__}: {str(exc)[:160]}",
            }
        try:
            validated = validate_plan(
                plan,
                allow_arm_motion=bool(task.get("allow_arm_motion", False)),
                assume_yes=bool(task.get("assume_yes", False)),
            )
        except PhotoPlanValidationError as exc:
            return {
                "schema_version": "1.0",
                "success": False,
                "plan_id": str(plan.get("plan_id", "")),
                "planner_mode": str(plan.get("planner_mode", "")),
                "steps": [],
                "error_code": exc.code,
                "reason": exc.reason,
                "plan": plan,
            }

        return await runtime.scheduler.run_app(
            "robot_photographer_agent",
            plan=validated,
            task_input=task,
            mock=bool(task.get("mock", self.mock)),
        )


def _normalize_task(task_input: Any) -> dict[str, Any]:
    if isinstance(task_input, dict):
        data = dict(task_input)
        if "text" not in data and "task" in data:
            data["text"] = data["task"]
        return data
    return {"text": str(task_input)}

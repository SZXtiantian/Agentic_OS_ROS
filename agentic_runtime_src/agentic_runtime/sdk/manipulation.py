from __future__ import annotations

from agentic_runtime.skill_executor.executor import raise_for_result
from agentic_runtime.types import ArmState, SkillResult


class ArmAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def get_state(self) -> ArmState:
        result = await self.ctx.call_skill("arm.get_state", {})
        raise_for_result(result)
        state = dict(result.data.get("state", {}))
        return ArmState(
            readiness=str(state.get("readiness", "")),
            active_action=str(state.get("active_action", "")),
            is_moving=bool(state.get("is_moving", False)),
            gripper_ready=bool(state.get("gripper_ready", False)),
            stop_available=bool(state.get("stop_available", False)),
            state=dict(state.get("state", {})),
        )

    async def move_named(self, name: str, timeout_s: int = 8) -> SkillResult:
        mapped = "arm_home" if name in {"home", "init"} else name
        result = await self.ctx.call_skill("arm.move_named", {"name": mapped, "timeout_s": timeout_s})
        raise_for_result(result)
        return result


class GripperAPI:
    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def open(self, timeout_s: int = 5) -> SkillResult:
        return await self.set("open", force="low", timeout_s=timeout_s)

    async def close(self, force: str = "low", timeout_s: int = 5) -> SkillResult:
        command = "close_gripper_low_force" if force == "low" else "close"
        return await self.set(command, force=force, timeout_s=timeout_s)

    async def set(self, command: str, force: str = "low", percentage: float | None = None, timeout_s: int = 5) -> SkillResult:
        args = {"command": command, "force": force, "timeout_s": timeout_s}
        if percentage is not None:
            args["percentage"] = percentage
        result = await self.ctx.call_skill("gripper.set", args)
        raise_for_result(result)
        return result

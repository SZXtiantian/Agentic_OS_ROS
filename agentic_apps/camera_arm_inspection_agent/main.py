import os

from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.sdk import AgentContext


async def run(
    ctx: AgentContext,
    target: str = "workspace",
    place: str | None = None,
    arm_action: str = "camera_up",
    move_arm: bool | None = None,
):
    if place:
        target = place
    allow_motion = os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION") == "1" if move_arm is None else bool(move_arm)
    await ctx.report.say(f"Starting camera-arm inspection for {target}.")

    try:
        robot_state = await ctx.robot.get_state()
        arm_state = await ctx.arm.get_state()
        observation = await ctx.perception.observe(target=target, timeout_s=5)

        report = {
            "success": True,
            "target": target,
            "motion_enabled": allow_motion,
            "robot_state": robot_state.to_dict(),
            "arm_state": arm_state.to_dict(),
            "observation": observation.to_dict(),
            "arm_action": None,
            "gripper_action": None,
        }
        await ctx.memory.remember("last_camera_arm_observation", report["observation"])
        await ctx.report.say(observation.summary)

        if not allow_motion:
            await ctx.report.say("Arm motion disabled by policy environment; read-only observation complete.")
            return report

        report["arm_action"] = (await ctx.arm.move_named(arm_action, timeout_s=8)).to_dict()
        report["gripper_action"] = (await ctx.gripper.open(timeout_s=5)).to_dict()
        await ctx.memory.remember("last_camera_arm_action", {"arm_action": arm_action, "gripper": "open"})
        await ctx.report.say(f"Completed allowed arm action {arm_action}.")
        return report

    except AgenticRuntimeError as exc:
        stop_result = None
        try:
            stop_result = (await ctx.robot.stop(reason=f"camera_arm_inspection_error:{exc.code}")).to_dict()
        except AgenticRuntimeError as stop_exc:
            stop_result = {"success": False, "error_code": stop_exc.code, "reason": stop_exc.message}
        await ctx.report.say(f"Camera-arm inspection failed: {exc.code}")
        return {
            "success": False,
            "target": target,
            "motion_enabled": allow_motion,
            "error_code": exc.code,
            "reason": exc.message,
            "stop_result": stop_result,
        }

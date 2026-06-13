from agentic_runtime.errors import AgenticRuntimeError, SafetyRejectedError, SkillExecutionError, SkillTimeoutError
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, place: str = "厨房"):
    await ctx.report.say(f"收到任务：准备去{place}检查。")

    try:
        resolved = await ctx.world.resolve_place(place)
        if not resolved.allowed:
            await ctx.report.say(f"地点不可用：{place}")
            return {"success": False, "reason": "PLACE_NOT_AVAILABLE", "error_code": "FORBIDDEN_ZONE"}

        state = await ctx.robot.get_state()
        if state.estop_pressed:
            await ctx.report.say("机器人处于急停状态，无法执行任务。")
            return {"success": False, "reason": "ESTOP_PRESSED", "error_code": "ESTOP_PRESSED"}

        await ctx.memory.remember("last_requested_place", place)

        nav_result = await ctx.robot.navigate_to(place, timeout_s=120)
        if not nav_result.success:
            answer = await ctx.human.ask(
                question=f"导航到{place}失败，是否重试一次？",
                options=["重试", "取消任务"],
                timeout_s=30,
                require_confirmation=True,
            )
            if answer.answer == "重试":
                nav_result = await ctx.robot.navigate_to(place, timeout_s=120)
            else:
                await ctx.robot.stop(reason="navigation_failed_user_cancelled")
                await ctx.report.say("任务已取消。")
                return {"success": False, "reason": "NAVIGATION_FAILED", "error_code": "NAVIGATION_FAILED"}

        inspection = await ctx.robot.inspect_area(place, timeout_s=60)

        await ctx.memory.remember(
            "last_inspection",
            {
                "place": place,
                "summary": inspection.summary,
                "objects": inspection.objects,
                "anomalies": inspection.anomalies,
            },
        )

        if inspection.anomalies:
            message = f"{place}检查完成，发现异常：{inspection.anomalies}"
        else:
            message = f"{place}检查完成，未发现异常。"

        await ctx.report.say(message)

        return {
            "success": True,
            "place": place,
            "inspection": inspection.to_dict(),
        }

    except SafetyRejectedError as exc:
        await ctx.robot.stop(reason="safety_rejected")
        await ctx.report.say(f"任务被安全系统拒绝：{exc.code}")
        return {"success": False, "reason": "SAFETY_REJECTED", "error_code": exc.code}

    except SkillTimeoutError as exc:
        await ctx.robot.stop(reason="task_timeout")
        await ctx.report.say("任务超时，机器人已停止。")
        return {"success": False, "reason": "TIMEOUT", "error_code": exc.code, "detail": str(exc)}

    except SkillExecutionError as exc:
        await ctx.robot.stop(reason="skill_execution_error")
        await ctx.report.say(f"任务执行失败：{exc.code}")
        return {"success": False, "reason": "SKILL_EXECUTION_ERROR", "error_code": exc.code}

    except AgenticRuntimeError as exc:
        await ctx.report.say(f"任务无法执行：{exc.code}")
        return {"success": False, "reason": exc.message, "error_code": exc.code}

    except Exception as exc:
        await ctx.robot.stop(reason="unexpected_error")
        await ctx.report.say("任务出现未知错误，机器人已停止。")
        return {"success": False, "reason": "UNEXPECTED_ERROR", "error_code": "UNEXPECTED_ERROR", "detail": str(exc)}

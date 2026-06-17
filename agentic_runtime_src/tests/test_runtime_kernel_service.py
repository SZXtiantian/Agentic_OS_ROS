from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agentic_os.kernel.system_call import LLMQuery, MemoryQuery, ToolQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest, SkillResult


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


def make_app() -> AppManifest:
    return AppManifest(
        name="kernel_test_app",
        version="0",
        description="",
        entrypoint="main:run",
        permissions=["robot.move"],
        required_capabilities=[],
    )


def test_kernel_service_starts_and_stops_scheduler(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    service.start()
    assert service.status()["scheduler"]["active"] is True

    service.stop()
    assert service.status()["scheduler"]["active"] is False


def test_kernel_service_executes_llm_query(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request("agent_a", LLMQuery(operation_type="chat"), timeout_s=1.0)
    finally:
        service.stop()

    assert result.success is True
    assert result.metadata["queue_name"] == "llm"


def test_kernel_service_executes_memory_query(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            MemoryQuery(operation_type="remember", params={"memory_id": "x", "content": "hello"}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert result.success is True


def test_robot_skill_not_routed_to_generic_tool(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            ToolQuery(operation_type="call_tool", params={"name": "robot.navigate_to", "args": {"place": "kitchen"}}),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"


def test_sdk_kernel_llm_chat_uses_kernel_service(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used")

    async def run():
        service.start()
        try:
            ctx = AgentContext(FakeExecutor(), make_app(), "sess_1")
            result = await ctx.kernel.llm.chat(messages=[{"role": "user", "content": "hi"}], timeout_s=1.0)
            assert result.success is True
            assert result.metadata["queue_name"] == "llm"
        finally:
            service.stop()

    asyncio.run(run())


def test_call_skill_still_uses_skill_executor():
    class FakeExecutor:
        kernel_service = None

        async def execute(self, app, name, args, session_id):
            return SkillResult(True, data={"skill": name, "args": args, "session_id": session_id})

    async def run():
        ctx = AgentContext(FakeExecutor(), make_app(), "sess_skill")
        result = await ctx.call_skill("robot.navigate_to", {"place": "kitchen"})
        assert result.data["skill"] == "robot.navigate_to"
        assert result.data["session_id"] == "sess_skill"

    asyncio.run(run())

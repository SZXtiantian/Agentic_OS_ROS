import asyncio
from pathlib import Path
from types import SimpleNamespace

import agentic_runtime
import pytest
from agentic_os.kernel.system_call import KernelResponse, LLMQuery, MemoryQuery, SkillQuery, StorageQuery
from agentic_runtime.app_manager import AppManager
from agentic_runtime.audit import AuditLogger
from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server
from agentic_runtime.sdk import AgentContext, KernelAccessDeniedError, KernelSDKResult
from agentic_runtime.types import AppManifest, SkillResult


def test_sdk_template_flow_uses_existing_agent_lifecycle_and_access_checks():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        session_id = "sess_sdk_template"
        agent = server.kernel_service.create_agent(app_id="app_template", session_id=session_id, agent_id="agent_sdk_template")
        server.kernel_service.start_agent(agent.agent_id)
        result = await manager.run_app("app_template", message="sdk smoke", session_id=session_id, agent_id=agent.agent_id)
        assert result["agent_id"] == agent.agent_id
        assert result["result"]["results"]["storage"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED"
        assert server.kernel_service.get_agent(agent.agent_id)["status"] == "ready"
        assert server.test_bridge_calls == []

    asyncio.run(run())


def test_sdk_no_forbidden_patterns():
    sdk_root = Path(agentic_runtime.__file__).resolve().parent / "sdk"
    forbidden = [
        "import " + "rclpy",
        "from " + "rclpy",
        "/" + "cmd_vel",
        "/" + "scan",
        "/" + "odom",
        "/" + "tf",
    ]
    for path in sdk_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in text


def test_sdk_capture_photo_reports_ros_bridge_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path / "photos"))

    async def run():
        server = create_test_runtime_server()
        app = AppManifest(
            name="photo_test",
            version="0",
            description="",
            entrypoint="main:run",
            permissions=["perception.capture"],
            required_capabilities=["perception.capture_photo"],
        )
        agent = server.kernel_service.create_agent(app_id=app.name, session_id="sess_photo", agent_id="agent_photo")
        server.kernel_service.start_agent(agent.agent_id)
        ctx = AgentContext(server.executor, app, "sess_photo", agent_id=agent.agent_id)
        with pytest.raises(AgenticRuntimeError) as exc:
            await ctx.perception.capture_photo(target="workspace", label="sdk", timeout_s=5)
        assert exc.value.code == "ROS_BRIDGE_UNAVAILABLE"
        assert server.test_bridge_calls[0]["command"][3] == "/agentic/safety/check"

    asyncio.run(run())


def test_kernel_sdk_llm_uses_kernel_query():
    captured = {}

    class FakeService:
        def execute_request(self, agent_name, query, timeout_s=None):
            captured["agent_name"] = agent_name
            captured["query"] = query
            captured["timeout_s"] = timeout_s
            return SimpleNamespace(success=True, response={"ok": True}, error_code="", metadata={})

    class FakeExecutor:
        kernel_service = FakeService()

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used for kernel llm")

    async def run():
        app = AppManifest("sdk_kernel_app", "0", "", "main:run", ["llm.external.call"], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_kernel")
        result = await ctx.kernel.llm.chat(messages=[{"role": "user", "content": "hello"}], timeout_s=1.5)
        assert result.success is True
        assert isinstance(result, KernelSDKResult)

    asyncio.run(run())

    assert captured["agent_name"] == "sdk_kernel_app"
    assert isinstance(captured["query"], LLMQuery)
    assert captured["query"].messages[0]["content"] == "hello"
    assert captured["query"].metadata["permissions"] == ("llm.external.call",)
    assert captured["timeout_s"] == 1.5


def test_sdk_llm_json_uses_runtime_owned_llm_chat():
    class RuntimeOwnedLLMChat:
        def __init__(self):
            self.calls = []

        def chat_json(self, *, system_prompt, user_prompt):
            self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
            return {"planner_mode": "llm", "answer": "ok"}

    llm_chat = RuntimeOwnedLLMChat()

    class Executor:
        kernel_service = SimpleNamespace(runtime_server=SimpleNamespace(llm_chat=llm_chat))

        async def execute(self, *args, **kwargs):
            raise AssertionError("ctx.llm must not use skill executor")

    async def run():
        app = AppManifest("sdk_llm_app", "0", "", "main:run", ["llm.external.call"], ["agenticos.runtime.llm_chat"])
        ctx = AgentContext(Executor(), app, "sess_llm")
        result = await ctx.llm.chat_json(system_prompt="return JSON", user_prompt="hello", timeout_s=1)
        assert result.success is True
        assert result.plan["planner_mode"] == "llm"
        assert result.metadata["provider_owner"] == "RuntimeServer"

    asyncio.run(run())

    assert llm_chat.calls == [{"system_prompt": "return JSON", "user_prompt": "hello"}]


def test_sdk_llm_json_without_runtime_llm_returns_stable_error():
    class Executor:
        kernel_service = SimpleNamespace(runtime_server=None)

        async def execute(self, *args, **kwargs):
            raise AssertionError("ctx.llm must not use skill executor")

    async def run():
        app = AppManifest("sdk_llm_app", "0", "", "main:run", ["llm.external.call"], ["agenticos.runtime.llm_chat"])
        ctx = AgentContext(Executor(), app, "sess_llm")
        result = await ctx.llm.chat_json(system_prompt="return JSON", user_prompt="hello", timeout_s=1)
        assert result.success is False
        assert result.error_code == "LLMCHAT_UNAVAILABLE"
        assert result.metadata["provider_owner"] == "RuntimeServer"

    asyncio.run(run())


def test_kernel_sdk_storage_uses_storage_query():
    captured = {}

    class FakeService:
        def execute_request(self, agent_name, query, timeout_s=None):
            captured["agent_name"] = agent_name
            captured["query"] = query
            captured["timeout_s"] = timeout_s
            return SimpleNamespace(success=True, response={"path": "reports/x.md"}, error_code="", metadata={})

    class FakeExecutor:
        kernel_service = FakeService()

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used for kernel storage")

    async def run():
        app = AppManifest("sdk_storage_app", "0", "", "main:run", [], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_storage")
        result = await ctx.kernel.storage.write("reports/x.md", "hello", timeout_s=2)
        assert result.success is True

    asyncio.run(run())

    assert captured["agent_name"] == "sdk_storage_app"
    assert isinstance(captured["query"], StorageQuery)
    assert captured["query"].operation_type == "sto_write"
    assert captured["query"].params["path"] == "reports/x.md"
    assert captured["query"].params["content"] == "hello"
    assert captured["timeout_s"] == 2


def test_kernel_sdk_memory_search_and_storage_retrieve_use_queries():
    captured = []

    class FakeService:
        def execute_request(self, agent_name, query, timeout_s=None):
            captured.append((agent_name, query, timeout_s))
            return SimpleNamespace(success=True, response={"ok": True}, error_code="", metadata={})

    class FakeExecutor:
        kernel_service = FakeService()

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used for kernel facade")

    async def run():
        app = AppManifest("sdk_query_app", "0", "", "main:run", [], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_query")
        memory = await ctx.kernel.memory.search("kitchen", limit=3, place_id="kitchen")
        storage = await ctx.kernel.storage.retrieve("report", collection_name="reports", limit=2)
        assert memory.success is True
        assert storage.success is True

    asyncio.run(run())

    assert isinstance(captured[0][1], MemoryQuery)
    assert captured[0][1].operation_type == "mem_search"
    assert captured[0][1].params["filters"]["place_id"] == "kitchen"
    assert isinstance(captured[1][1], StorageQuery)
    assert captured[1][1].operation_type == "sto_retrieve"
    assert captured[1][1].params["collection_name"] == "reports"


def test_kernel_sdk_skill_call_preserves_call_id():
    captured = {}

    class FakeService:
        def execute_request(self, agent_name, query, timeout_s=None):
            captured["agent_name"] = agent_name
            captured["query"] = query
            captured["timeout_s"] = timeout_s
            return SimpleNamespace(success=True, response={"ok": True}, error_code="", metadata={})

    class FakeExecutor:
        kernel_service = FakeService()

        async def execute(self, *args, **kwargs):
            raise AssertionError("kernel skill facade must use KernelService")

    async def run():
        app = AppManifest("sdk_skill_app", "0", "", "main:run", ["report.say"], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_skill")
        result = await ctx.kernel.skill.call("report.say", {"message": "done"}, call_id="skill_call_1", timeout_s=2)
        assert result.success is True

    asyncio.run(run())

    query = captured["query"]
    assert captured["agent_name"] == "sdk_skill_app"
    assert captured["timeout_s"] == 2
    assert isinstance(query, SkillQuery)
    assert query.call_id == "skill_call_1"
    assert query.params["call_id"] == "skill_call_1"


def test_kernel_sdk_cancel_uses_kernel_service_cancel_request():
    captured = {}

    class FakeService:
        def cancel_request(self, syscall_id):
            captured["syscall_id"] = syscall_id
            return KernelResponse.ok(
                {"cancelled": [syscall_id]},
                metadata={"syscall_id": syscall_id, "status": "cancelled"},
                data={"cancelled": [syscall_id]},
            )

    class FakeExecutor:
        kernel_service = FakeService()

        async def execute(self, *args, **kwargs):
            raise AssertionError("kernel cancel must use KernelService.cancel_request")

    async def run():
        app = AppManifest("sdk_cancel_app", "0", "", "main:run", [], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_cancel")
        result = await ctx.kernel.cancel("ksc_queued")
        assert result.success is True
        assert result.syscall_id == "ksc_queued"

    asyncio.run(run())

    assert captured["syscall_id"] == "ksc_queued"


def test_kernel_sdk_result_includes_syscall_and_audit_id(tmp_path):
    audit = AuditLogger(tmp_path / "audit.jsonl")
    service = KernelService(
        config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"),
        audit_logger=audit,
    )

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used for kernel storage")

    async def run():
        app = AppManifest("sdk_result_app", "0", "", "main:run", [], [])
        agent = service.create_agent(app_id=app.name, session_id="sess_result", agent_id="agent_sdk_result")
        service.start_agent(agent.agent_id)
        ctx = AgentContext(FakeExecutor(), app, "sess_result", agent_id=agent.agent_id)
        result = await ctx.kernel.storage.write("reports/result.md", "hello", timeout_s=1)
        assert result.success is True
        assert result.syscall_id.startswith("ksc_")
        assert result.audit_id.startswith("audit_")
        assert result.metadata["queue_name"] == "storage"

    asyncio.run(run())


def test_robot_sdk_does_not_use_tool_manager():
    calls = []

    class FakeService:
        def execute_request(self, *args, **kwargs):
            raise AssertionError("robot SDK must not use generic kernel tool/syscall path")

    class FakeExecutor:
        kernel_service = FakeService()

        async def execute(self, app, name, args, session_id):
            calls.append((app.name, name, args, session_id))
            return SkillResult(success=True, data={"ok": True})

    async def run():
        app = AppManifest("robot_sdk_app", "0", "", "main:run", ["robot.move"], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_robot")
        result = await ctx.robot.navigate_to("kitchen", timeout_s=3)
        assert result.success is True

    asyncio.run(run())

    assert calls == [("robot_sdk_app", "robot.navigate_to", {"place": "kitchen", "timeout_s": 3}, "sess_robot")]


def test_kernel_tool_sdk_rejects_robot_capability(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("generic tool SDK must not use skill executor")

    async def run():
        app = AppManifest("sdk_tool_app", "0", "", "main:run", [], [])
        agent = service.create_agent(app_id=app.name, session_id="sess_tool", agent_id="agent_sdk_tool")
        service.start_agent(agent.agent_id)
        ctx = AgentContext(FakeExecutor(), app, "sess_tool", agent_id=agent.agent_id)
        result = await ctx.kernel.tool.call("robot.navigate_to", {"place": "kitchen"}, timeout_s=1)
        assert result.success is False
        assert result.error_code == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"

    asyncio.run(run())


def test_sdk_access_denied_surfaces_clear_error(tmp_path):
    service = KernelService(config=SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"))

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used for kernel access")

    async def run():
        app = AppManifest("access_app", "0", "", "main:run", [], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_access")
        decision = await ctx.kernel.access.check(
            "write",
            "storage",
            "private/report.md",
            owner_agent="other_app",
        )
        assert decision["allowed"] is False
        assert decision["error_code"] == "ACCESS_DENIED"
        with pytest.raises(KernelAccessDeniedError) as exc:
            await ctx.kernel.access.assert_allowed(
                "write",
                "storage",
                "private/report.md",
                owner_agent="other_app",
            )
        assert exc.value.error_code == "ACCESS_DENIED"

    asyncio.run(run())

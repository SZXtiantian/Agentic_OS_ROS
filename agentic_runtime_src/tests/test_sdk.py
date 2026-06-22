import asyncio
from pathlib import Path
from types import SimpleNamespace

import agentic_runtime
import pytest
from agentic_os.kernel.system_call import LLMQuery, MemoryQuery, StorageQuery
from agentic_runtime.app_manager import AppManager
from agentic_runtime.audit import AuditLogger
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server
from agentic_runtime.sdk import AgentContext, KernelAccessDeniedError, KernelSDKResult
from agentic_runtime.types import AppManifest, SkillResult


def test_sdk_room_flow_and_memory():
    async def run():
        server = create_test_runtime_server()
        manager = AppManager(server.config.app_root, server.executor)
        result = await manager.run_app("inspection_agent", place="厨房")
        assert result["result"]["success"] is True
        value = server.executor.dispatcher.memory_store.recall("inspection_agent", "last_inspection")
        assert value["place"] == "厨房"

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


def test_sdk_capture_photo_writes_mock_evidence(tmp_path, monkeypatch):
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
        ctx = AgentContext(server.executor, app, "sess_photo")
        result = await ctx.perception.capture_photo(target="workspace", label="sdk", timeout_s=5)
        assert result.success is True
        assert Path(result.image_path).exists()
        assert Path(result.metadata_path).exists()
        assert result.evidence["perception_backend_status"] == "MOCK"

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
        app = AppManifest("sdk_kernel_app", "0", "", "main:run", [], [])
        ctx = AgentContext(FakeExecutor(), app, "sess_kernel")
        result = await ctx.kernel.llm.chat(messages=[{"role": "user", "content": "hello"}], timeout_s=1.5)
        assert result.success is True
        assert isinstance(result, KernelSDKResult)

    asyncio.run(run())

    assert captured["agent_name"] == "sdk_kernel_app"
    assert isinstance(captured["query"], LLMQuery)
    assert captured["query"].messages[0]["content"] == "hello"
    assert captured["timeout_s"] == 1.5


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
        ctx = AgentContext(FakeExecutor(), app, "sess_result")
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
        ctx = AgentContext(FakeExecutor(), app, "sess_tool")
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

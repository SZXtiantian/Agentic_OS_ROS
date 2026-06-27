import asyncio
import time
from threading import Event, Thread
from types import SimpleNamespace

from agentic_os.kernel.agent import AgentStatus
from agentic_os.kernel.hooks import KernelQueueName
from agentic_os.kernel.system_call import KernelResponse, MemoryQuery
from agentic_runtime.context_manager import ContextManager
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.scheduler import SessionRunner
from agentic_runtime.sdk import AgentContext
from agentic_runtime.session import SessionManager, SessionStore
from agentic_runtime.storage import StorageManager
from agentic_runtime.types import AppManifest, SkillResult


class SuccessAppFactory:
    async def run_app(self, app_id, **kwargs):
        return {"session_id": kwargs["session_id"], "agent_id": kwargs["agent_id"], "app_id": app_id, "result": {"success": True}}


class FailureAppFactory:
    async def run_app(self, app_id, **kwargs):
        return {
            "session_id": kwargs["session_id"],
            "agent_id": kwargs["agent_id"],
            "app_id": app_id,
            "result": {"success": False, "error_code": "APP_DECLINED", "reason": "nope"},
        }


class CrashAppFactory:
    async def run_app(self, app_id, **kwargs):
        raise RuntimeError("boom")


def _service(tmp_path):
    return KernelService(config=SimpleNamespace(storage_root=tmp_path / "kernel-storage", tool_root=tmp_path / "tools"))


def _runner(tmp_path, app_factory, service):
    runner = SessionRunner(
        app_factory,
        SessionManager(SessionStore(tmp_path / "sessions")),
        StorageManager(tmp_path / "storage"),
        ContextManager(tmp_path / "context"),
    )
    runner.kernel_service = service
    return runner


def _app():
    return AppManifest("app_a", "0", "", "main:run", ["memory.write"], [])


def test_session_runner_creates_acb_for_app_session(tmp_path):
    async def run():
        service = _service(tmp_path)
        runner = _runner(tmp_path, SuccessAppFactory(), service)

        result = await runner.run_app("app_a", place="lab")

        assert result["agent_id"].startswith("agent_")
        agent = service.agent_table.get(result["agent_id"], include_reaped=True)
        assert agent is not None
        assert agent.session_id == result["session_id"]

    asyncio.run(run())


def test_app_success_marks_agent_exited(tmp_path):
    async def run():
        service = _service(tmp_path)
        runner = _runner(tmp_path, SuccessAppFactory(), service)

        result = await runner.run_app("app_a", place="lab")

        assert service.agent_table.require(result["agent_id"]).status == AgentStatus.EXITED

    asyncio.run(run())


def test_app_failure_marks_agent_failed(tmp_path):
    async def run():
        service = _service(tmp_path)
        runner = _runner(tmp_path, FailureAppFactory(), service)

        result = await runner.run_app("app_a", place="lab")

        agent = service.agent_table.require(result["agent_id"])
        assert agent.status == AgentStatus.FAILED
        assert agent.error_code == "APP_DECLINED"

    asyncio.run(run())


def test_app_exception_marks_agent_crashed(tmp_path):
    async def run():
        service = _service(tmp_path)
        runner = _runner(tmp_path, CrashAppFactory(), service)

        result = await runner.run_app("app_a", place="lab")

        assert service.agent_table.require(result["agent_id"]).status == AgentStatus.CRASHED
        assert result["result"]["error_code"] == "APP_EXCEPTION"

    asyncio.run(run())


def test_agent_context_receives_agent_id():
    class FakeExecutor:
        kernel_service = None

        async def execute(self, app, name, args, session_id, *, agent_id="", **kwargs):
            return SkillResult(success=True, data={"agent_id": agent_id, "session_id": session_id})

    async def run():
        ctx = AgentContext(FakeExecutor(), _app(), "sess_1", agent_id="agent_1")
        result = await ctx.call_skill("report.say", {"message": "hi"})
        assert result.data["agent_id"] == "agent_1"

    asyncio.run(run())


def test_kernel_sdk_adds_agent_id_to_query_metadata():
    captured = {}

    class FakeService:
        def execute_request(self, agent_name, query, timeout_s=None):
            captured["query"] = query
            return SimpleNamespace(success=True, response={}, error_code="", metadata={})

    class FakeExecutor:
        kernel_service = FakeService()

    async def run():
        ctx = AgentContext(FakeExecutor(), _app(), "sess_1", agent_id="agent_1")
        await ctx.kernel.memory.add("hello", key="k")

    asyncio.run(run())

    assert captured["query"].metadata["agent_id"] == "agent_1"
    assert captured["query"].metadata["app_id"] == "app_a"
    assert captured["query"].metadata["session_id"] == "sess_1"


def test_kernel_service_status_contains_agents(tmp_path):
    service = _service(tmp_path)
    agent = service.create_agent(app_id="app_a", session_id="sess_1", agent_id="agent_1")

    status = service.status()

    assert status["agents"]["live_count"] == 1
    assert status["agents"]["items"][0]["agent_id"] == agent.agent_id
    assert "agent_resources" in status


def test_syscall_wait_timeout_does_not_detach_running_agent_syscall(tmp_path):
    service = _service(tmp_path)
    agent = service.create_agent(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    service.start_agent(agent.agent_id)
    running = Event()
    release = Event()

    class SlowManager:
        def address_request(self, syscall):
            running.set()
            release.wait(timeout=2.0)
            return KernelResponse.ok({"done": True})

    service.managers["memory"] = SlowManager()
    service.scheduler.managers["memory"] = service.managers["memory"]
    service.start()
    try:
        result_box = {}

        def call():
            query = MemoryQuery(
                operation_type="mem_remember",
                params={"memory_id": "k", "content": "v"},
                metadata={"agent_id": agent.agent_id, "app_id": "app_a", "session_id": "sess_1"},
            )
            result_box["result"] = service.execute_request("app_a", query, timeout_s=0.05)

        thread = Thread(target=call)
        thread.start()
        assert running.wait(timeout=1.0) is True
        thread.join(timeout=1.0)

        result = result_box["result"]
        assert result.success is False
        assert result.error_code == "KERNEL_SYSCALL_TIMEOUT"
        assert result.syscall.syscall_id in service.agent_table.require(agent.agent_id).running_syscall_ids

        release.set()
        assert result.syscall.wait(timeout_s=1.0) is True
        deadline = time.monotonic() + 1.0
        while result.syscall.syscall_id in service.agent_table.require(agent.agent_id).running_syscall_ids and time.monotonic() < deadline:
            time.sleep(0.01)
        assert result.syscall.syscall_id not in service.agent_table.require(agent.agent_id).running_syscall_ids
    finally:
        release.set()
        service.stop()


def test_kill_agent_cancels_session_and_releases_resources(tmp_path):
    class Cancellation:
        def __init__(self):
            self.cancelled = []
            self.cleared = []

        def cancel_session(self, session_id):
            self.cancelled.append(session_id)

        def clear_session(self, session_id):
            self.cleared.append(session_id)

    class Resources:
        def __init__(self):
            self.released = []

        def release_by_agent(self, agent_id):
            self.released.append(agent_id)

    cancellation = Cancellation()
    resources = Resources()
    runtime = SimpleNamespace(executor=SimpleNamespace(cancellation_manager=cancellation, resource_manager=resources))
    service = KernelService(
        runtime_server=SimpleNamespace(
            **runtime.__dict__,
            config=SimpleNamespace(ros_bridge_mode="cli", storage_root=tmp_path / "storage", tool_root=tmp_path / "tools"),
            registry=SimpleNamespace(list_skills=lambda: []),
            monitor=SimpleNamespace(status=lambda skills, ros_bridge="cli": {}),
            bridge_client=SimpleNamespace(status=lambda: {"success": True, "state": "ready"}),
        )
    )
    agent = service.create_agent(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    service.start_agent(agent.agent_id)
    service.agent_lifecycle.register_resource(agent_id=agent.agent_id, resource_type="skill_lock", resource_id="base")

    response = service.kill_agent(agent.agent_id)

    assert response.success is True
    assert cancellation.cancelled == ["sess_1"]
    assert resources.released == ["agent_1"]
    assert service.agent_resources.snapshot()["items"][0]["state"] == "released"


def test_suspend_agent_blocks_new_kernel_syscall(tmp_path):
    service = _service(tmp_path)
    agent = service.create_agent(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    service.start_agent(agent.agent_id)
    service.suspend_agent(agent.agent_id)

    result = service.execute_request(
        "app_a",
        MemoryQuery(operation_type="mem_get", metadata={"agent_id": agent.agent_id}),
        timeout_s=0.01,
    )

    assert result.success is False
    assert result.error_code == "AGENT_SUSPENDED"


def test_resume_agent_allows_new_kernel_syscall(tmp_path):
    service = _service(tmp_path)
    agent = service.create_agent(app_id="app_a", session_id="sess_1", agent_id="agent_1")
    service.start_agent(agent.agent_id)
    service.suspend_agent(agent.agent_id)
    service.resume_agent(agent.agent_id)

    result = service.execute_request(
        "app_a",
        MemoryQuery(operation_type="mem_get", params={"memory_id": "missing"}, metadata={"agent_id": agent.agent_id}),
        timeout_s=1.0,
    )

    assert result.error_code != "AGENT_SUSPENDED"
    assert result.metadata["queue_name"] == KernelQueueName.MEMORY

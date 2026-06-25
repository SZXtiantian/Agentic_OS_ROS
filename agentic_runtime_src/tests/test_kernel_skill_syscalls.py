from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agentic_os.kernel.skill_library import RuntimeSkillBackend, SkillManager
from agentic_os.kernel.system_call import SkillQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.kernel_service.robot_backend import RuntimeRobotCapabilityBackend
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest, SkillResult


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


class RuntimeCompatibleExecutor:
    def __init__(self) -> None:
        self.cancelled_sessions: list[str] = []
        self.cancelled_calls: list[tuple[str, str]] = []
        self.cancellation_manager = SimpleNamespace(
            cancel_session=lambda session_id: self.cancelled_sessions.append(session_id),
            cancel_call=lambda session_id, call_id: self.cancelled_calls.append((session_id, call_id)) or call_id == "call_1",
            active_calls=lambda: [{"session_id": "sess_1", "call_id": "call_1"}],
        )
        self.calls: list[tuple[str, dict, str]] = []

    async def execute(self, app, skill_name, args, session_id):
        self.calls.append((skill_name, dict(args), session_id))
        return SkillResult(True, data={"skill": skill_name, "args": dict(args), "app": app.name, "session_id": session_id})


class RuntimeCompatibleRegistry:
    def __init__(self) -> None:
        self.skill = SimpleNamespace(
            name="report.say",
            version="1",
            description="Say a report message",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            permission_requirements=["report.say"],
            resource_requirements={"locks": []},
            safety_constraints={},
            timeout_s=5,
            backend={"type": "runtime"},
        )

    def list_skills(self):
        return [self.skill]

    def get_skill(self, name):
        if name != "report.say":
            raise KeyError(name)
        return self.skill


def test_skill_manager_without_backend_fails_fast():
    manager = SkillManager()
    response = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="skill_call", params={"skill_name": "report.say", "args": {"message": "hi"}})
    )

    assert response.success is False
    assert response.error_code == "SKILL_BACKEND_UNAVAILABLE"


def test_runtime_skill_backend_call_list_describe_cancel():
    executor = RuntimeCompatibleExecutor()
    backend = RuntimeSkillBackend(SimpleNamespace(executor=executor, registry=RuntimeCompatibleRegistry()))
    manager = SkillManager(backend)

    called = manager.call("report.say", {"message": "done"}, app_id="agent_a", session_id="sess_1", permissions=("report.say",))
    listed = manager.list()
    described = manager.describe("report.say")
    status = manager.status(call_id="call_1")
    cancelled = manager.cancel("sess_1", call_id="call_1")
    missing_cancel = manager.cancel("sess_1", call_id="missing")
    missing_call_id_cancel = manager.cancel("sess_1")

    assert called["success"] is True
    assert called["result"]["data"]["skill"] == "report.say"
    assert listed["skills"][0]["name"] == "report.say"
    assert described["skill"]["name"] == "report.say"
    assert status["state"] == "ready"
    assert cancelled["success"] is True
    assert missing_cancel["success"] is False
    assert missing_cancel["error_code"] == "SYSCALL_NOT_FOUND"
    assert missing_call_id_cancel["success"] is False
    assert missing_call_id_cancel["error_code"] == "SYSCALL_NOT_FOUND"
    assert executor.cancelled_calls == [("sess_1", "call_1"), ("sess_1", "missing")]
    assert executor.cancelled_sessions == []


def test_runtime_robot_capability_backend_unwraps_sdk_args():
    class Executor:
        def __init__(self) -> None:
            self.calls = []

        async def execute(self, app, skill_name, args, session_id):
            self.calls.append((app, skill_name, dict(args), session_id))
            return SkillResult(True, data={"args": dict(args)})

    executor = Executor()
    backend = RuntimeRobotCapabilityBackend(SimpleNamespace(executor=executor))
    query = SkillQuery(
        operation_type="skill_call",
        skill_name="perception.detect_color_block",
        app_id="color_block_grasper_agent",
        session_id="sess_color",
        params={"args": {"color": "red", "target": "workspace"}, "permissions": ("perception.detect.color_block",)},
    )
    response = backend.execute_capability(SimpleNamespace(agent_name="color_block_grasper_agent", operation_type="skill_call", params=query.params, query=query))

    assert response["success"] is True
    assert executor.calls[0][1] == "perception.detect_color_block"
    assert executor.calls[0][2] == {"color": "red", "target": "workspace"}
    assert executor.calls[0][3] == "sess_color"


def test_runtime_skill_backend_cancel_requires_call_id():
    executor = RuntimeCompatibleExecutor()
    backend = RuntimeSkillBackend(SimpleNamespace(executor=executor, registry=RuntimeCompatibleRegistry()))

    result = backend.cancel("sess_1")

    assert result["success"] is False
    assert result["error_code"] == "SYSCALL_NOT_FOUND"
    assert result["reason"] == "call_id required"
    assert executor.cancelled_calls == []
    assert executor.cancelled_sessions == []


def test_skill_manager_rejects_non_object_backend_response():
    class BadBackend:
        def call(self, *args, **kwargs):
            return "ok"

    manager = SkillManager(BadBackend())
    response = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="skill_call",
            params={"skill_name": "report.say", "args": {"message": "hi"}},
        )
    )

    assert response.success is False
    assert response.error_code == "SKILL_RESULT_INVALID"
    assert response.metadata["raw_type"] == "str"


def test_skill_manager_rejects_non_boolean_backend_success_and_audits():
    from agentic_os.kernel.hooks import InMemoryKernelEventSink

    class BadBackend:
        def call(self, *args, **kwargs):
            return {"success": "true", "result": {"message": "fake success"}}

    sink = InMemoryKernelEventSink()
    manager = SkillManager(BadBackend(), event_sink=sink)
    response = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="skill_call",
            params={"skill_name": "report.say", "args": {"message": "hi"}},
        )
    )

    assert response.success is False
    assert response.error_code == "SKILL_RESULT_INVALID"
    assert response.metadata["success_type"] == "str"
    audit = [event for event in sink.recent(limit=5) if event["event_type"] == "skill.audit"][-1]
    assert audit["metadata"]["success"] is False
    assert audit["metadata"]["error_code"] == "SKILL_RESULT_INVALID"
    assert audit["metadata"]["reason"] == "skill backend response success field must be boolean"


def test_skill_manager_rejects_backend_response_without_success_and_audits():
    from agentic_os.kernel.hooks import InMemoryKernelEventSink

    class BadBackend:
        def status(self):
            return {"state": "ready"}

    sink = InMemoryKernelEventSink()
    manager = SkillManager(BadBackend(), event_sink=sink)
    response = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="skill_status", params={})
    )

    assert response.success is False
    assert response.error_code == "SKILL_RESULT_INVALID"
    assert response.metadata["data"] == {"state": "ready"}
    audit = [event for event in sink.recent(limit=5) if event["event_type"] == "skill.audit"][-1]
    assert audit["metadata"]["error_code"] == "SKILL_RESULT_INVALID"


def test_skill_status_rejects_non_boolean_success_before_call_id_lookup():
    from agentic_os.kernel.hooks import InMemoryKernelEventSink

    class BadBackend:
        def status(self):
            return {"success": "true", "state": "ready", "active_calls": []}

    sink = InMemoryKernelEventSink()
    manager = SkillManager(BadBackend(), event_sink=sink)
    response = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="skill_status", params={"call_id": "missing"})
    )

    assert response.success is False
    assert response.error_code == "SKILL_RESULT_INVALID"
    assert response.metadata["success_type"] == "str"
    audit = [event for event in sink.recent(limit=5) if event["event_type"] == "skill.audit"][-1]
    assert audit["metadata"]["error_code"] == "SKILL_RESULT_INVALID"


def test_skill_status_unknown_call_id_returns_not_found_and_audits():
    from agentic_os.kernel.hooks import InMemoryKernelEventSink

    class Backend:
        def status(self):
            return {"success": True, "state": "ready", "active_calls": [{"session_id": "sess_1", "call_id": "call_1"}]}

    sink = InMemoryKernelEventSink()
    manager = SkillManager(Backend(), event_sink=sink)
    response = manager.address_request(
        SimpleNamespace(agent_name="agent_a", operation_type="skill_status", params={"call_id": "missing"})
    )

    assert response.success is False
    assert response.error_code == "SYSCALL_NOT_FOUND"
    assert response.metadata["call_id"] == "missing"
    audit = [event for event in sink.recent(limit=5) if event["event_type"] == "skill.audit"][-1]
    assert audit["metadata"]["error_code"] == "SYSCALL_NOT_FOUND"


def test_kernel_service_skill_without_runtime_returns_stable_error(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            SkillQuery(operation_type="skill_call", skill_name="report.say", params={"args": {"message": "hi"}}),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "SKILL_BACKEND_UNAVAILABLE"
    assert result.metadata["queue_name"] == "skill"
    assert status["skill"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
    assert any(
        event["event_type"] == "skill.audit" and event["metadata"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
        for event in status["events"]["recent"]
    )


def test_kernel_skill_robot_motion_routes_to_robot_lane_and_fails_without_backend(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            SkillQuery(operation_type="skill_call", skill_name="robot.navigate_to", params={"args": {"place": "kitchen"}}),
            timeout_s=1.0,
        )
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "SKILL_BACKEND_UNAVAILABLE"
    assert result.metadata["queue_name"] == "robot_motion"
    assert any(
        event["event_type"] == "robot.audit" and event["metadata"]["error_code"] == "SKILL_BACKEND_UNAVAILABLE"
        for event in status["events"]["recent"]
    )


def test_kernel_skill_sdk_facade_uses_kernel_service(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    class Executor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("kernel skill SDK must use kernel service")

    async def run():
        service.start()
        try:
            app = AppManifest("skill_sdk_app", "0", "", "main:run", ["report.say"], [])
            ctx = AgentContext(Executor(), app, "sess_skill")
            result = await ctx.kernel.skill.call("report.say", {"message": "done"}, timeout_s=1.0)
            listed = await ctx.kernel.skill.list(timeout_s=1.0)
            assert result.success is False
            assert result.error_code == "SKILL_BACKEND_UNAVAILABLE"
            assert listed.error_code == "SKILL_BACKEND_UNAVAILABLE"
        finally:
            service.stop()

    asyncio.run(run())

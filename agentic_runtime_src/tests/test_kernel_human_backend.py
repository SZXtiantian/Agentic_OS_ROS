from __future__ import annotations

from types import SimpleNamespace

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_os.kernel.hooks import InMemoryKernelEventSink
from agentic_os.kernel.human import HumanInteractionManager
from agentic_os.kernel.system_call import SkillQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.kernel_service.human_backend import RuntimeHumanBackend
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server
from agentic_runtime.types import SkillResult


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


class RuntimeCompatibleExecutor:
    def __init__(self) -> None:
        self.cancelled_sessions: list[str] = []
        self.cancelled_calls: list[tuple[str, str]] = []
        self.cancellation_manager = SimpleNamespace(
            cancel_session=lambda session_id: self.cancelled_sessions.append(session_id),
            cancel_call=lambda session_id, call_id: self.cancelled_calls.append((session_id, call_id)) or call_id == "call_1",
        )

    async def execute(self, app, skill_name, args, session_id):
        assert skill_name == "human.ask"
        assert args["timeout_s"] == 3
        return SkillResult(True, data={"answered": True, "answer": "yes", "session_id": session_id, "app": app.name})


def test_human_lane_without_runtime_returns_stable_error(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            SkillQuery(
                operation_type="skill_call",
                skill_name="human.ask",
                params={"args": {"question": "Ready?", "timeout_s": 3}},
                session_id="sess_human",
            ),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    status = service.status()
    assert result.success is False
    assert result.error_code == "HUMAN_BACKEND_UNAVAILABLE"
    assert result.metadata["queue_name"] == "human"
    assert status["human"]["error_code"] == "HUMAN_BACKEND_UNAVAILABLE"
    assert any(
        event["event_type"] == "human.audit" and event["metadata"]["error_code"] == "HUMAN_BACKEND_UNAVAILABLE"
        for event in status["events"]["recent"]
    )


def test_human_manager_audits_ask_and_cancel():
    class Backend:
        def address_request(self, syscall):
            return {"success": True, "answered": True, "answer": "yes", "correlation_id": "human_1"}

        def cancel(self, session_id, call_id=""):
            return {"success": False, "error_code": "SYSCALL_NOT_FOUND", "session_id": session_id, "call_id": call_id}

        def status(self):
            return {"success": True, "state": "ready", "backend": "test_backend"}

    sink = InMemoryKernelEventSink()
    manager = HumanInteractionManager(Backend(), event_sink=sink)

    ask = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human.ask",
            params={"session_id": "sess_human", "correlation_id": "human_1"},
        )
    )
    cancel = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human_cancel",
            params={"session_id": "sess_human", "call_id": "human_1"},
        )
    )

    assert ask.success is True
    assert cancel.success is False
    assert cancel.error_code == "SYSCALL_NOT_FOUND"
    events = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"]
    assert [event["metadata"]["action"] for event in events] == ["ask", "cancel"]
    assert events[0]["metadata"]["success"] is True
    assert events[1]["metadata"]["error_code"] == "SYSCALL_NOT_FOUND"


def test_human_ask_requires_explicit_permission_before_backend_call():
    class Backend:
        calls = 0

        def address_request(self, syscall):
            self.calls += 1
            return {"success": True, "answered": True, "answer": "yes"}

    sink = InMemoryKernelEventSink()
    backend = Backend()
    manager = HumanInteractionManager(backend, access_manager=AccessManager(event_sink=sink), event_sink=sink)

    denied = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human.ask",
            params={"session_id": "sess_human", "question": "Ready?"},
            query=SimpleNamespace(app_id="agent_a", session_id="sess_human", metadata={}),
        )
    )

    assert denied.success is False
    assert denied.error_code == "ACCESS_DENIED"
    assert backend.calls == 0
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"][-1]
    assert audit["metadata"]["error_code"] == "ACCESS_DENIED"


def test_human_ask_with_permission_requires_intervention_by_default():
    class Backend:
        calls = 0

        def address_request(self, syscall):
            self.calls += 1
            return {"success": True, "answered": True, "answer": "yes"}

    sink = InMemoryKernelEventSink()
    backend = Backend()
    manager = HumanInteractionManager(backend, access_manager=AccessManager(event_sink=sink), event_sink=sink)

    denied = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human.ask",
            params={"session_id": "sess_human", "question": "Ready?"},
            query=SimpleNamespace(
                app_id="agent_a",
                session_id="sess_human",
                metadata={"permissions": ["human.ask"]},
            ),
        )
    )

    assert denied.success is False
    assert denied.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert backend.calls == 0
    assert any(
        event["event_type"] == "access.checked" and event["metadata"]["requires_intervention"] is True
        for event in sink.recent(limit=10)
    )
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"][-1]
    assert audit["metadata"]["error_code"] == "ACCESS_INTERVENTION_REQUIRED"


def test_human_ask_runs_after_operator_intervention_allows():
    class Backend:
        calls = 0

        def address_request(self, syscall):
            self.calls += 1
            return {"success": True, "answered": True, "answer": "yes"}

    sink = InMemoryKernelEventSink()
    backend = Backend()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider(), event_sink=sink)
    manager = HumanInteractionManager(backend, access_manager=access, event_sink=sink)

    result = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human.ask",
            params={"session_id": "sess_human", "question": "Ready?"},
            query=SimpleNamespace(
                app_id="agent_a",
                session_id="sess_human",
                metadata={"permissions": ["human.ask"]},
            ),
        )
    )

    assert result.success is True
    assert backend.calls == 1
    assert any(event["event_type"] == "access.checked" for event in sink.recent(limit=10))


def test_runtime_human_backend_uses_skill_executor_contract():
    executor = RuntimeCompatibleExecutor()
    backend = RuntimeHumanBackend(SimpleNamespace(executor=executor, registry=SimpleNamespace()))

    result = backend.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="skill_call",
            params={"args": {"question": "Ready?", "timeout_s": 3}},
            query=SimpleNamespace(skill_name="human.ask", app_id="agent_a", session_id="sess_human", metadata={"permissions": ["human.ask"]}),
        )
    )
    cancel = backend.cancel("sess_human", call_id="call_1")
    missing_cancel = backend.cancel("sess_human", call_id="missing")

    assert result["success"] is True
    assert result["result"]["data"]["answer"] == "yes"
    assert cancel["success"] is True
    assert missing_cancel["success"] is False
    assert missing_cancel["error_code"] == "SYSCALL_NOT_FOUND"
    assert executor.cancelled_calls == [("sess_human", "call_1"), ("sess_human", "missing")]
    assert executor.cancelled_sessions == []


def test_runtime_human_backend_does_not_inject_default_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = create_test_runtime_server()
    backend = RuntimeHumanBackend(server)

    result = backend.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="skill_call",
            params={"args": {"question": "Ready?", "timeout_s": 3}},
            query=SimpleNamespace(skill_name="human.ask", app_id="agent_a", session_id="sess_human", metadata={}),
        )
    )

    assert result["success"] is False
    assert result["error_code"] == "PERMISSION_DENIED"

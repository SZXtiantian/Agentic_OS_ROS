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
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider(), event_sink=sink)
    manager = HumanInteractionManager(Backend(), access_manager=access, event_sink=sink)

    ask = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human.ask",
            params={"session_id": "sess_human", "correlation_id": "human_1"},
            query=SimpleNamespace(
                app_id="agent_a",
                session_id="sess_human",
                metadata={"permissions": ["human.ask"]},
            ),
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


def test_human_cancel_requires_call_id_before_backend_call():
    class Backend:
        calls = 0

        def cancel(self, session_id, call_id=""):
            self.calls += 1
            return {"success": True, "session_id": session_id, "call_id": call_id}

        def status(self):
            return {"success": True, "state": "ready", "backend": "test_backend"}

    sink = InMemoryKernelEventSink()
    backend = Backend()
    manager = HumanInteractionManager(backend, event_sink=sink)

    missing = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human_cancel",
            params={"session_id": "sess_human"},
        )
    )

    assert missing.success is False
    assert missing.error_code == "SYSCALL_NOT_FOUND"
    assert backend.calls == 0
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"][-1]
    assert audit["metadata"]["action"] == "cancel"
    assert audit["metadata"]["error_code"] == "SYSCALL_NOT_FOUND"


def test_human_cancel_requires_backend_cancel_contract():
    class Backend:
        def status(self):
            return {"success": True, "state": "ready", "backend": "test_backend"}

    manager = HumanInteractionManager(Backend())

    result = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human_cancel",
            params={"session_id": "sess_human", "call_id": "human_1"},
        )
    )

    assert result.success is False
    assert result.error_code == "HUMAN_BACKEND_UNAVAILABLE"
    assert result.metadata["reason"] == "human backend does not support cancel"


def test_human_status_requires_active_call_id_and_audits():
    class Backend:
        def status(self):
            return {
                "success": True,
                "state": "ready",
                "backend": "test_backend",
                "human_channel": {"active": ["human_1"]},
                "active_calls": [{"session_id": "sess_human", "call_id": "human_2"}],
            }

    sink = InMemoryKernelEventSink()
    manager = HumanInteractionManager(Backend(), event_sink=sink)

    active = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human_status",
            params={"session_id": "sess_human", "call_id": "human_2"},
        )
    )
    missing = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human_status",
            params={"session_id": "sess_human", "call_id": "missing"},
        )
    )

    assert active.success is True
    assert active.data["call_id"] == "human_2"
    assert missing.success is False
    assert missing.error_code == "SYSCALL_NOT_FOUND"
    assert missing.metadata["active"] == ["human_1", "human_2"]
    events = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"]
    assert [event["metadata"]["action"] for event in events] == ["status", "status"]
    assert events[-1]["metadata"]["error_code"] == "SYSCALL_NOT_FOUND"


def test_human_status_requires_backend_status_contract():
    class Backend:
        def address_request(self, syscall):
            return {"success": True, "answered": True, "answer": "yes"}

    sink = InMemoryKernelEventSink()
    manager = HumanInteractionManager(Backend(), event_sink=sink)

    status = manager.address_request(
        SimpleNamespace(
            agent_name="agent_a",
            operation_type="human_status",
            params={"session_id": "sess_human"},
        )
    )

    assert status.success is False
    assert status.error_code == "HUMAN_BACKEND_STATUS_UNAVAILABLE"
    assert status.metadata["backend"] == "Backend"
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"][-1]
    assert audit["metadata"]["action"] == "status"
    assert audit["metadata"]["error_code"] == "HUMAN_BACKEND_STATUS_UNAVAILABLE"


def test_human_status_rejects_backend_status_without_success_field():
    class Backend:
        def status(self):
            return {"state": "ready", "backend": "test_backend"}

    manager = HumanInteractionManager(Backend())

    status = manager.status()

    assert status["success"] is False
    assert status["state"] == "unavailable"
    assert status["error_code"] == "HUMAN_RESULT_INVALID"


def test_human_ask_requires_access_manager_before_backend_call():
    class Backend:
        calls = 0

        def address_request(self, syscall):
            self.calls += 1
            return {"success": True, "answered": True, "answer": "yes"}

    sink = InMemoryKernelEventSink()
    backend = Backend()
    manager = HumanInteractionManager(backend, event_sink=sink)

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
    assert denied.error_code == "ACCESS_MANAGER_UNAVAILABLE"
    assert backend.calls == 0
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"][-1]
    assert audit["metadata"]["error_code"] == "ACCESS_MANAGER_UNAVAILABLE"


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


def test_human_manager_normalizes_legacy_answered_backend_contract():
    class Backend:
        def __init__(self, result):
            self.result = result

        def address_request(self, syscall):
            return dict(self.result)

    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider(), event_sink=sink)

    answered = HumanInteractionManager(
        Backend({"answered": True, "answer": "yes"}),
        access_manager=access,
        event_sink=sink,
    ).address_request(
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
    unanswered = HumanInteractionManager(
        Backend({"answered": False, "answer": "", "reason": "operator declined"}),
        access_manager=access,
        event_sink=sink,
    ).address_request(
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

    assert answered.success is True
    assert answered.data["success"] is True
    assert answered.data["answered"] is True
    assert unanswered.success is False
    assert unanswered.error_code == "HUMAN_UNANSWERED"


def test_human_manager_rejects_non_object_backend_result():
    class Backend:
        def address_request(self, syscall):
            return "yes"

    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider(), event_sink=sink)
    manager = HumanInteractionManager(Backend(), access_manager=access, event_sink=sink)

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

    assert result.success is False
    assert result.error_code == "HUMAN_RESULT_INVALID"
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "human.audit"][-1]
    assert audit["metadata"]["error_code"] == "HUMAN_RESULT_INVALID"


def test_human_manager_rejects_backend_response_missing_success_and_answered():
    class Backend:
        def address_request(self, syscall):
            return {"answer": "yes"}

    sink = InMemoryKernelEventSink()
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider(), event_sink=sink)
    manager = HumanInteractionManager(Backend(), access_manager=access, event_sink=sink)

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

    assert result.success is False
    assert result.error_code == "HUMAN_RESULT_INVALID"
    assert result.metadata["data"] == {"answer": "yes"}


def test_human_manager_rejects_non_boolean_success_field():
    class Backend:
        def address_request(self, syscall):
            return {"success": "yes", "answered": True, "answer": "yes"}

    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider())
    manager = HumanInteractionManager(Backend(), access_manager=access)

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

    assert result.success is False
    assert result.error_code == "HUMAN_RESULT_INVALID"
    assert result.metadata["reason"] == "human backend response success field must be bool"


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

from __future__ import annotations

from types import SimpleNamespace

from agentic_os.kernel.system_call import SkillQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.kernel_service.human_backend import RuntimeHumanBackend
from agentic_runtime.types import SkillResult


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


class RuntimeCompatibleExecutor:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.cancellation_manager = SimpleNamespace(cancel_session=lambda session_id: self.cancelled.append(session_id))

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

    assert result.success is False
    assert result.error_code == "HUMAN_BACKEND_UNAVAILABLE"
    assert result.metadata["queue_name"] == "human"
    assert service.status()["human"]["error_code"] == "HUMAN_BACKEND_UNAVAILABLE"


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

    assert result["success"] is True
    assert result["result"]["data"]["answer"] == "yes"
    assert cancel["success"] is True
    assert executor.cancelled == ["sess_human"]

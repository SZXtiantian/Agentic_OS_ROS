from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

from agentic_os.kernel.access import AlwaysAllowTestInterventionProvider
from agentic_os.kernel.scheduler import RoundRobinKernelScheduler
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall, LLMQuery, MemoryQuery, RobotCapabilityQuery, ToolQuery
from agentic_runtime.kernel_service import KernelService
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server
from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest, SkillResult


def make_config(tmp_path):
    return SimpleNamespace(storage_root=tmp_path / "storage", tool_root=tmp_path / "tools")


def make_kernel_config(tmp_path, kernel):
    return SimpleNamespace(
        repo_root=tmp_path,
        storage_root=tmp_path / "storage",
        tool_root=tmp_path / "tools",
        scheduler_policy="fifo",
        kernel=kernel,
    )


def make_app() -> AppManifest:
    return AppManifest(
        name="kernel_test_app",
        version="0",
        description="",
        entrypoint="main:run",
        permissions=["robot.move", "llm.external.call"],
        required_capabilities=[],
    )


class _OpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path.endswith("/chat/completions"):
            messages = body.get("messages") or [{"content": "ok"}]
            content = messages[-1].get("content", "ok")
            payload = {"choices": [{"message": {"role": "assistant", "content": f"ack: {content}"}}]}
        elif self.path.endswith("/embeddings"):
            inputs = body.get("input", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            payload = {"model": body.get("model", "embedding"), "data": [{"embedding": [float(len(str(item))), 1.0]} for item in inputs]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        return


def openai_config(tmp_path):
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    server = HTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = make_kernel_config(
        tmp_path,
        {
            "llm": {
                "configs": [
                    {
                        "name": "local-openai",
                        "backend": "openai_compatible",
                        "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                        "api_key": "test-key",
                        "model": "local-chat",
                        "capabilities": ["chat", "complete", "embed"],
                    }
                ]
            }
        },
    )
    return server, config


def test_kernel_service_starts_and_stops_scheduler(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    service.start()
    assert service.status()["scheduler"]["active"] is True

    service.stop()
    assert service.status()["scheduler"]["active"] is False


def test_kernel_service_configured_llm_requires_explicit_permission(tmp_path):
    server, config = openai_config(tmp_path)
    service = KernelService(config=config)
    service.start()
    try:
        result = service.execute_request("agent_a", LLMQuery(operation_type="chat", metadata={"kernel_internal": True}), timeout_s=1.0)
    finally:
        service.stop()
        server.shutdown()

    assert result.success is False
    assert result.error_code == "ACCESS_DENIED"
    assert result.metadata["queue_name"] == "llm"


def test_kernel_service_executes_llm_query_after_intervention_approval(tmp_path):
    server, config = openai_config(tmp_path)
    service = KernelService(config=config)
    service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            LLMQuery(operation_type="chat", metadata={"permissions": ["llm.external.call"], "kernel_internal": True}),
            timeout_s=1.0,
        )
    finally:
        service.stop()
        server.shutdown()

    assert result.success is True
    assert result.metadata["queue_name"] == "llm"


def test_kernel_service_default_config_reports_llm_unavailable(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    status = service.status()

    assert status["config"]["llm"]["configs"][0]["name"] == "unconfigured"
    assert status["config"]["llm"]["configs"][0]["backend"] == "openai_compatible"
    assert status["llm"]["state"] == "unavailable"
    assert status["llm"]["providers"][0]["error_code"] == "LLM_PROVIDER_UNCONFIGURED"


def _runtime_with_bridge_client(bridge_client):
    return SimpleNamespace(
        bridge_client=bridge_client,
        config=SimpleNamespace(ros_bridge_mode="cli", storage_root="/tmp/agentic-test-storage", tool_root="/tmp/agentic-test-tools"),
        registry=SimpleNamespace(list_skills=lambda: []),
        monitor=SimpleNamespace(status=lambda skills, ros_bridge="cli": {"ros_bridge": ros_bridge, "skills": skills}),
    )


def test_kernel_service_status_rejects_bridge_client_without_status():
    service = KernelService(runtime_server=_runtime_with_bridge_client(object()))

    status = service.status()

    assert status["bridge_client"]["success"] is False
    assert status["bridge_client"]["error_code"] == "ROS_BRIDGE_STATUS_UNAVAILABLE"
    assert status["bridge_client"]["reason"] == "bridge client does not expose status()"
    assert any(
        event["event_type"] == "ros_bridge.status"
        and event["metadata"]["error_code"] == "ROS_BRIDGE_STATUS_UNAVAILABLE"
        for event in status["events"]["recent"]
    )


def test_kernel_service_status_rejects_invalid_bridge_status_result():
    class BadStatusClient:
        def status(self):
            return "ready"

    service = KernelService(runtime_server=_runtime_with_bridge_client(BadStatusClient()))

    status = service.status()

    assert status["bridge_client"]["success"] is False
    assert status["bridge_client"]["error_code"] == "ROS_RESULT_INVALID"
    assert status["bridge_client"]["reason"] == "bridge client status returned str"
    assert any(
        event["event_type"] == "ros_bridge.status" and event["metadata"]["error_code"] == "ROS_RESULT_INVALID"
        for event in status["events"]["recent"]
    )


def test_kernel_service_uses_rr_scheduler_from_kernel_config(tmp_path):
    service = KernelService(config=make_kernel_config(tmp_path, {"scheduler_policy": "rr"}))

    assert isinstance(service.scheduler, RoundRobinKernelScheduler)


def test_kernel_service_uses_configured_llm_without_status_secret_leak(tmp_path):
    service = KernelService(
        config=make_kernel_config(
            tmp_path,
            {
                "llm": {
                    "routing_strategy": "sequential",
                    "configs": [
                        {
                            "name": "configured-openai",
                            "backend": "openai_compatible",
                            "enabled": True,
                            "api_key": "super-secret",
                            "base_url": "https://example.test/v1",
                            "model": "configured-chat",
                            "capabilities": ["chat", "json"],
                        }
                    ],
                }
            },
        )
    )

    status = service.status()
    rendered = str(status)

    assert status["config"]["llm"]["configs"][0]["name"] == "configured-openai"
    assert "super-secret" not in rendered
    assert "api_key" not in rendered


def test_kernel_service_execute_request_lazily_starts_scheduler(tmp_path):
    service = KernelService(config=make_config(tmp_path))

    try:
        result = service.execute_request("agent_a", LLMQuery(operation_type="chat", metadata={"kernel_internal": True}), timeout_s=1.0)
        status = service.status()
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "LLM_PROVIDER_UNCONFIGURED"
    assert status["scheduler"]["active"] is True
    assert status["scheduler"]["threads"]


def test_kernel_service_cancel_request_reports_missing_and_cancels_queued(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    queued = KernelSyscall.create("agent_a", "memory", "remember", {"memory_id": "queued"})
    service.queue_store.add("memory", queued)

    cancelled = service.cancel_request(queued.syscall_id)
    missing = service.cancel_request("ksc_missing")
    status = service.status()

    assert cancelled.success is True
    assert queued.status == "cancelled"
    assert service.queue_store.size("memory") == 0
    assert missing.success is False
    assert missing.error_code == "SYSCALL_NOT_FOUND"
    assert any(
        event["event_type"] == "kernel.cancel_request"
        and event["metadata"]["error_code"] == "SYSCALL_NOT_FOUND"
        for event in status["events"]["recent"]
    )


def test_kernel_service_checkpoint_request_rejects_manager_without_real_checkpoint_support(tmp_path):
    class BlockingMemoryManager:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.active_syscall = None

        def address_request(self, syscall):
            self.active_syscall = syscall
            self.started.set()
            self.release.wait(timeout=2.0)
            return {"success": False, "error_code": "MEMORY_INTERRUPTED"}

    manager = BlockingMemoryManager()
    service = KernelService(config=make_config(tmp_path), managers={"memory": manager})
    service.start()
    try:
        result_holder = {}

        def submit_request():
            result_holder["result"] = service.execute_request(
                "agent_a",
                MemoryQuery(operation_type="recall", metadata={"kernel_internal": True}),
                timeout_s=2.0,
            )

        thread = threading.Thread(target=submit_request)
        thread.start()
        assert manager.started.wait(timeout=2.0)
        syscall = manager.active_syscall
        assert syscall is not None

        response = service.checkpoint_request(syscall.syscall_id, reason="operator_suspend")
        manager.release.set()

        assert response.success is False
        assert response.error_code == "SCHEDULER_PREEMPTION_UNSUPPORTED"
        assert response.metadata["reason"] == "manager does not expose checkpoint_request"
        assert any(
            event["event_type"] == "kernel.checkpoint_request"
            and event["metadata"]["error_code"] == "SCHEDULER_PREEMPTION_UNSUPPORTED"
            for event in service.status()["events"]["recent"]
        )
        thread.join(timeout=2.0)
    finally:
        manager.release.set()
        service.stop()


def test_kernel_service_checkpoint_request_delegates_and_persists_real_checkpoint(tmp_path):
    class CheckpointRobotSensorManager:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.active_syscall = None
            self.checkpoint_calls = []

        def address_request(self, syscall):
            self.active_syscall = syscall
            self.started.set()
            self.release.wait(timeout=2.0)
            return {"success": False, "error_code": "ROBOT_CAPABILITY_INTERRUPTED"}

        def checkpoint_request(self, syscall, **metadata):
            self.checkpoint_calls.append((syscall, metadata))
            self.release.set()
            return KernelResponse.ok(
                {
                    "checkpoint_id": "inspect_cp_real_1",
                    "partial_result": {"visited_waypoints": ["north_hall"]},
                    "completed_coverage": ["zone_north"],
                },
                data={
                    "checkpoint_id": "inspect_cp_real_1",
                    "partial_result": {"visited_waypoints": ["north_hall"]},
                    "completed_coverage": ["zone_north"],
                },
            )

    manager = CheckpointRobotSensorManager()
    service = KernelService(config=make_config(tmp_path), managers={"robot_sensor": manager})
    service.start()
    try:
        result_holder = {}

        def submit_request():
            result_holder["result"] = service.execute_request(
                "agent_a",
                RobotCapabilityQuery(
                    operation_type="robot.inspect_area",
                    skill_name="robot.inspect_area",
                    app_id="app",
                    session_id="sess_checkpoint",
                    metadata={"kernel_internal": True, "session_id": "sess_checkpoint"},
                ),
                timeout_s=2.0,
            )

        thread = threading.Thread(target=submit_request)
        thread.start()
        assert manager.started.wait(timeout=2.0)
        syscall = manager.active_syscall
        assert syscall is not None

        response = service.checkpoint_request(
            syscall.syscall_id,
            reason="operator_suspend",
            node_id="inspect_node",
            task_graph_id="graph_checkpoint",
            agent_id="agent_checkpoint",
        )
        thread.join(timeout=2.0)

        recovered = service.context.recover("sess_checkpoint", "agent_a", checkpoint="inspect_cp_real_1")

        assert response.success is True
        assert response.data["checkpoint"]["checkpoint_id"] == "inspect_cp_real_1"
        assert response.data["checkpoint"]["partial_result"] == {"visited_waypoints": ["north_hall"]}
        assert response.data["checkpoint"]["completed_coverage"] == ["zone_north"]
        assert manager.checkpoint_calls[0][0] is syscall
        assert manager.checkpoint_calls[0][1]["node_id"] == "inspect_node"
        assert recovered is not None
        assert recovered.state["checkpoint"] == response.data["checkpoint"]
        assert recovered.state["completed_coverage"] == ["zone_north"]
        assert any(
            event["event_type"] == "kernel.checkpoint_request"
            and event["metadata"]["checkpoint_id"] == "inspect_cp_real_1"
            and event["metadata"]["completed_coverage"] == ["zone_north"]
            for event in service.status()["events"]["recent"]
        )
    finally:
        manager.release.set()
        service.stop()


def test_kernel_service_executes_memory_query(tmp_path):
    service = KernelService(config=make_config(tmp_path))
    service.start()
    try:
        result = service.execute_request(
            "agent_a",
            MemoryQuery(
                operation_type="remember",
                params={"memory_id": "x", "content": "hello"},
                metadata={"kernel_internal": True},
            ),
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
            ToolQuery(
                operation_type="call_tool",
                params={"name": "robot.navigate_to", "args": {"place": "kitchen"}},
                metadata={"kernel_internal": True},
            ),
            timeout_s=1.0,
        )
    finally:
        service.stop()

    assert result.success is False
    assert result.error_code == "TOOL_FORBIDDEN_ROBOT_CAPABILITY"


def test_sdk_kernel_llm_chat_uses_kernel_service(tmp_path):
    server, config = openai_config(tmp_path)
    service = KernelService(config=config)
    service.access_manager.intervention_provider = AlwaysAllowTestInterventionProvider()

    class FakeExecutor:
        kernel_service = service

        async def execute(self, *args, **kwargs):
            raise AssertionError("skill executor should not be used")

    async def run():
        service.start()
        try:
            agent = service.create_agent(app_id=make_app().name, session_id="sess_1", agent_id="agent_sdk_llm")
            service.start_agent(agent.agent_id)
            ctx = AgentContext(FakeExecutor(), make_app(), "sess_1", agent_id=agent.agent_id)
            result = await ctx.kernel.llm.chat(messages=[{"role": "user", "content": "hi"}], timeout_s=1.0)
            assert result.success is True
            assert result.metadata["queue_name"] == "llm"
        finally:
            service.stop()
            server.shutdown()

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


def test_runtime_server_shutdown_stops_kernel_scheduler(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = create_test_runtime_server()

    server.kernel_service.start()
    assert server.kernel_service.status()["scheduler"]["active"] is True
    server.shutdown()

    assert server.kernel_service.status()["scheduler"]["active"] is False
    assert server.kernel_service.status()["scheduler"]["threads"] == {}


def test_runtime_server_shares_kernel_access_manager_with_runtime_wrappers(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_VAR", str(tmp_path / "var"))
    server = create_test_runtime_server()

    access = server.kernel_service.access_manager
    event_sink = server.kernel_service.event_sink

    assert server.executor.access_manager is access
    assert server.context_manager.kernel.access_manager is access
    assert server.context_manager.kernel.event_sink is event_sink
    assert server.storage_manager.kernel.access_manager is access
    assert server.storage_manager.kernel.event_sink is event_sink
    assert server.tool_manager.kernel.access_manager is access
    assert server.tool_manager.kernel.event_sink is event_sink
    assert server.executor.dispatcher.memory_store.kernel.access_manager is access
    assert server.executor.dispatcher.memory_store.kernel.event_sink is event_sink

    snapshot = server.context_manager.snapshot("sess_shared", "inspection_agent", task={"place": "lab"})
    recovered = server.context_manager.recover("sess_shared")

    assert snapshot.task == {"place": "lab"}
    assert recovered is not None
    assert recovered.task == {"place": "lab"}
    assert any(
        event["event_type"] == "context.audit"
        and event["metadata"]["operation_type"] == "ctx_snapshot"
        and event["metadata"]["session_id"] == "sess_shared"
        for event in event_sink.recent(limit=20)
    )
    assert any(
        event["event_type"] == "context.audit"
        and event["metadata"]["operation_type"] == "ctx_recover"
        and event["metadata"]["session_id"] == "sess_shared"
        for event in event_sink.recent(limit=20)
    )

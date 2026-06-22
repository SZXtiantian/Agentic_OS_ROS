from agentic_os.kernel.context import GenerationSnapshot, SessionContextManager, SimpleGenerationContextManager
from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.llm_core import LLMAdapter, LLMConfig
from agentic_os.kernel.scheduler import RoundRobinKernelScheduler, SchedulerLaneSpec
from agentic_os.kernel.system_call import KernelResponse, LLMQuery, RobotCapabilityQuery, SyscallExecutor


class RecordingStreamingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, query):
        return KernelResponse.ok({"text": "non-streaming"})

    def complete_with_time_slice(self, query, time_slice_s, snapshot=None):
        self.calls += 1
        if snapshot is None:
            return (
                KernelResponse.ok({"partial_text": "hel"}, metadata={"suspended": True}),
                GenerationSnapshot(
                    generation_id="",
                    syscall_id="",
                    prompt_hash="",
                    partial_response="hel",
                    partial_text="hel",
                    model="stream",
                    status="suspended",
                ),
            )
        return KernelResponse.ok({"text": snapshot.partial_text + "lo"}), None


def test_session_context_snapshot_recover_still_works(tmp_path):
    manager = SessionContextManager(tmp_path / "context")
    manager.snapshot(
        "sess_1",
        "inspection_agent",
        task={"place": "kitchen"},
        current_skill="robot.inspect_area",
        audit_correlation_id="audit_1",
    )

    snapshot = manager.recover("sess_1")

    assert snapshot is not None
    assert snapshot.task == {"place": "kitchen"}
    assert snapshot.current_skill == "robot.inspect_area"
    assert snapshot.audit_correlation_id == "audit_1"


def test_generation_context_save_restore_partial_response():
    manager = SimpleGenerationContextManager()
    prompt = [{"role": "user", "content": "inspect"}]

    saved = manager.save("gen_1", "ksc_1", prompt, partial_response="partial", metadata={"model": "recording"})
    restored = manager.restore("gen_1")

    assert restored is saved
    assert restored.partial_response == "partial"
    assert restored.metadata["model"] == "recording"


def test_generation_context_prompt_hash_changes_on_prompt_change():
    manager = SimpleGenerationContextManager()

    first = manager.prompt_hash([{"role": "user", "content": "a"}])
    second = manager.prompt_hash([{"role": "user", "content": "b"}])

    assert first != second


def test_rr_scheduler_does_not_preempt_robot_motion():
    scheduler = RoundRobinKernelScheduler(KernelQueueStore(), managers={})

    assert scheduler.can_preempt_lane(KernelQueueName.ROBOT_MOTION) is False
    assert scheduler.can_preempt_lane(KernelQueueName.LLM) is True


def test_rr_scheduler_suspends_requeues_and_resumes_recording_streaming_llm():
    store = KernelQueueStore()
    provider = RecordingStreamingProvider()
    manager = LLMAdapter([LLMConfig(name="stream", backend="openai_compatible")], providers={"stream": provider})
    lane = SchedulerLaneSpec(
        "llm",
        KernelQueueName.LLM,
        concurrent=True,
        manager_key="llm",
        preemptible=True,
        batchable=False,
    )
    context = SimpleGenerationContextManager()
    scheduler = RoundRobinKernelScheduler(
        store,
        managers={"llm": manager},
        lanes=(lane,),
        time_slice_s=0.001,
        generation_context=context,
    )
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        result = executor.execute_request(
            "agent_a",
            LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hello"}]),
            timeout_s=1.0,
        )
    finally:
        scheduler.stop()

    snapshot = context.restore(result.syscall.syscall_id)
    assert provider.calls == 2
    assert result.success is True
    assert result.response.response_message == {"text": "hello"}
    assert result.syscall.status == "done"
    assert result.syscall.params["partial_text"] == "hel"
    assert snapshot is not None
    assert snapshot.partial_text == "hello"
    assert snapshot.status == "done"


def test_llm_adapter_time_slice_marks_non_preemptible_provider():
    class Provider:
        def complete(self, query):
            return KernelResponse.ok({"text": "done"})

    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": Provider()})

    response, snapshot = adapter.complete_with_time_slice(LLMQuery(operation_type="chat"), time_slice_s=0.001)

    assert response.success is True
    assert response.metadata["non_preemptible_llm_call"] is True
    assert snapshot is None


def test_llm_time_slice_path_enforces_external_access_gate():
    class Provider:
        calls = 0

        def complete(self, query):
            self.calls += 1
            return KernelResponse.ok({"text": "done"})

    provider = Provider()
    adapter = LLMAdapter(
        [
            LLMConfig(
                name="configured",
                backend="openai_compatible",
                hostname="https://example.test/v1",
                api_key="test-key",
                model="real-model",
            )
        ],
        providers={"configured": provider},
        access_manager=AccessManager(),
    )

    response, snapshot = adapter.complete_with_time_slice(LLMQuery(operation_type="chat"), time_slice_s=0.001)

    assert response.success is False
    assert response.error_code == "ACCESS_DENIED"
    assert provider.calls == 0
    assert snapshot is None


def test_rr_scheduler_does_not_put_robot_motion_through_generation_context():
    class RobotManager:
        def address_request(self, syscall):
            return {"success": True}

    store = KernelQueueStore()
    lane = SchedulerLaneSpec(
        "robot_motion",
        KernelQueueName.ROBOT_MOTION,
        concurrent=False,
        manager_key="robot_motion",
        preemptible=False,
    )
    context = SimpleGenerationContextManager()
    scheduler = RoundRobinKernelScheduler(store, managers={"robot_motion": RobotManager()}, lanes=(lane,), generation_context=context)
    executor = SyscallExecutor(queue_store=store, default_timeout_s=1.0)

    scheduler.start()
    try:
        result = executor.execute_request(
            "agent_a",
            RobotCapabilityQuery(operation_type="execute_skill", skill_name="robot.navigate_to"),
            timeout_s=1.0,
        )
    finally:
        scheduler.stop()

    assert result.success is True
    assert result.syscall.status == "done"
    assert context.restore(result.syscall.syscall_id) is None

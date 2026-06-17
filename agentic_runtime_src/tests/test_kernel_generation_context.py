from agentic_os.kernel.context import SessionContextManager, SimpleGenerationContextManager
from agentic_os.kernel.hooks import KernelQueueName, KernelQueueStore
from agentic_os.kernel.scheduler import RoundRobinKernelScheduler


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

    saved = manager.save("gen_1", "ksc_1", prompt, partial_response="partial", metadata={"model": "mock"})
    restored = manager.restore("gen_1")

    assert restored is saved
    assert restored.partial_response == "partial"
    assert restored.metadata["model"] == "mock"


def test_generation_context_prompt_hash_changes_on_prompt_change():
    manager = SimpleGenerationContextManager()

    first = manager.prompt_hash([{"role": "user", "content": "a"}])
    second = manager.prompt_hash([{"role": "user", "content": "b"}])

    assert first != second


def test_rr_scheduler_does_not_preempt_robot_motion():
    scheduler = RoundRobinKernelScheduler(KernelQueueStore(), managers={})

    assert scheduler.can_preempt_lane(KernelQueueName.ROBOT_MOTION) is False
    assert scheduler.can_preempt_lane(KernelQueueName.LLM) is True

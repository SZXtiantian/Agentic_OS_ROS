from agentic_runtime.context_manager import ContextManager


def test_context_snapshot_recover(tmp_path):
    manager = ContextManager(tmp_path / "context")
    manager.snapshot("sess_1", "inspection_agent", task={"place": "厨房"}, current_skill="robot.inspect_area")

    snapshot = manager.recover("sess_1")
    assert snapshot is not None
    assert snapshot.task["place"] == "厨房"
    assert snapshot.current_skill == "robot.inspect_area"

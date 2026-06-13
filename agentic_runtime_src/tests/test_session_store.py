from agentic_runtime.session import SessionManager, SessionStatus, SessionStore


def test_session_store_persists_records_and_syscalls(tmp_path):
    manager = SessionManager(SessionStore(tmp_path / "sessions"))
    record = manager.create_session("inspection_agent", {"place": "厨房"})
    manager.start_session(record.session_id)
    manager.append_syscall(record.session_id, {"skill_name": "robot.get_state", "status": "done"})
    manager.complete_session(record.session_id, {"success": True})

    loaded = manager.get_session(record.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.COMPLETED
    assert manager.read_syscalls(record.session_id) == [{"skill_name": "robot.get_state", "status": "done"}]
    assert manager.list_sessions()[0].session_id == record.session_id

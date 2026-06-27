import pytest

from agentic_os.kernel.agent import AGENT_ALREADY_EXISTS, AgentLifecycleError, AgentStatus, AgentTable


def test_agent_table_create_and_require():
    table = AgentTable()

    agent = table.create("app_a", "sess_1", agent_id="agent_1")

    assert table.require("agent_1") is agent
    assert agent.status == AgentStatus.CREATED


def test_agent_table_rejects_duplicate_agent_id():
    table = AgentTable()
    table.create("app_a", "sess_1", agent_id="agent_1")

    with pytest.raises(AgentLifecycleError) as exc:
        table.create("app_b", "sess_2", agent_id="agent_1")

    assert exc.value.error_code == AGENT_ALREADY_EXISTS


def test_agent_table_find_by_session():
    table = AgentTable()
    first = table.create("app_a", "sess_1", agent_id="agent_1")
    table.create("app_b", "sess_2", agent_id="agent_2")

    assert table.find_by_session("sess_1") == [first]
    assert table.find_one_by_session("sess_1", "app_a") is first


def test_agent_table_attach_detach_syscall():
    table = AgentTable()
    table.create("app_a", "sess_1", agent_id="agent_1")

    table.attach_syscall("agent_1", "ksc_1")
    table.mark_syscall_running("agent_1", "ksc_1")
    table.detach_syscall("agent_1", "ksc_1")

    agent = table.require("agent_1")
    assert agent.owned_syscall_ids == []
    assert agent.running_syscall_ids == []


def test_agent_table_move_to_tombstone():
    table = AgentTable()
    agent = table.create("app_a", "sess_1", agent_id="agent_1")
    agent.mark_terminal(status=AgentStatus.EXITED, exit_kind="success")

    reaped = table.move_to_tombstone("agent_1")

    assert reaped.status == AgentStatus.REAPED
    assert table.get("agent_1") is None
    assert table.get("agent_1", include_reaped=True) is reaped


def test_agent_table_snapshot_counts_live_terminal_reaped():
    table = AgentTable()
    live = table.create("app_a", "sess_1", agent_id="agent_1")
    terminal = table.create("app_b", "sess_2", agent_id="agent_2")
    reaped = table.create("app_c", "sess_3", agent_id="agent_3")
    terminal.mark_terminal(status=AgentStatus.FAILED, exit_kind="failure")
    reaped.mark_terminal(status=AgentStatus.EXITED, exit_kind="success")
    table.move_to_tombstone("agent_3")

    snapshot = table.snapshot(include_reaped=True)

    assert snapshot["live_count"] == 2
    assert snapshot["terminal_count"] == 1
    assert snapshot["reaped_count"] == 1
    assert {item["agent_id"] for item in snapshot["items"]} == {live.agent_id, terminal.agent_id, "agent_3"}

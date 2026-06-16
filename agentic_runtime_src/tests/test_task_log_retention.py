from agentic_runtime.task_log import TaskLogManager


def test_task_log_create_update_and_recent(tmp_path):
    manager = TaskLogManager(tmp_path / "tasks", retain_recent_n=3)
    plan = {
        "task_id": "task_1",
        "route_plan_id": "plan_1",
        "planner_mode": "rule_based",
        "selected_app_id": "robot_photographer_agent",
        "risk_class": "read_only",
        "requires_robot_motion": False,
        "needs_confirmation": False,
    }
    manager.write_route_plan(plan)
    record = manager.create_task("拍一张照片", plan, "sess_dispatch")
    assert record.status == "planned"
    manager.mark_running("task_1", [{"agent_id": "robot_photographer_agent", "role": "primary_executor"}])
    manager.attach_agent_session("task_1", "robot_photographer_agent", "sess_child")
    completed = manager.complete_task("task_1", {"success": True, "summary": "done", "app_output_paths": ["/tmp/a.png"]})
    assert completed.status == "completed"
    assert manager.list_recent()[0].selected_agents[0]["session_id"] == "sess_child"
    assert (tmp_path / "tasks" / "recent_tasks.json").exists()
    assert (tmp_path / "tasks" / "plans" / "plan_1.json").exists()


def test_task_log_retention_keeps_recent_failed_and_rejected(tmp_path):
    manager = TaskLogManager(tmp_path / "tasks", retain_recent_n=2, retain_failed_n=1, retain_rejected_n=1)
    for idx in range(6):
        plan = {
            "task_id": f"task_{idx}",
            "route_plan_id": f"plan_{idx}",
            "planner_mode": "rule_based",
            "selected_app_id": "builtin.tasks",
            "risk_class": "read_only",
        }
        manager.write_route_plan(plan)
        manager.create_task(f"task {idx}", plan, "sess")
        if idx == 1:
            manager.fail_task(f"task_{idx}", "FAILED", "failed")
        elif idx == 2:
            manager.reject_task(f"task_{idx}", "REJECTED", "rejected")
        else:
            manager.complete_task(f"task_{idx}", {"success": True, "summary": "ok"})

    report = manager.compact(force=True)
    retained = {record.task_id for record in manager.list_recent(limit=20)}
    assert report.compacted is True
    assert {"task_1", "task_2"}.issubset(retained)
    assert len(retained) <= 4

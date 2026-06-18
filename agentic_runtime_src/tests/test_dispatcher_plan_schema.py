from jsonschema import Draft202012Validator

from agentic_runtime.dispatcher.app_index import AppIndex
from agentic_runtime.dispatcher.planner import DispatcherPlanner
from agentic_runtime.nl_gateway import GatewayFlags


def test_dispatcher_rule_plan_matches_schema(app_root):
    planner = DispatcherPlanner()
    plan = planner.plan(
        "拍一张照片",
        AppIndex.load(app_root),
        GatewayFlags(mock=True),
        task_id="task_test",
        route_plan_id="plan_route_test",
    )

    schema = planner._plan_with_llm.__globals__["_schema"]()
    Draft202012Validator(schema).validate(plan)
    assert plan["selected_app_id"] == "robot_photographer_agent"
    assert plan["intent"] == "capture_photo"

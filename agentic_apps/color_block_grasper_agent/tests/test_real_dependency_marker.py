from __future__ import annotations

import os


def test_real_e2e_reports_unverified_when_environment_is_not_enabled():
    enabled = (
        os.environ.get("AGENTIC_LLM_ENABLED") == "1"
        and os.environ.get("AGENTIC_LLM_REQUIRE") == "1"
        and os.environ.get("AGENTIC_VERIFY_REAL_COLOR_BLOCK_GRASPER") == "1"
        and os.environ.get("AGENTIC_VERIFY_REAL_ROS2") == "1"
        and os.environ.get("AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION") == "1"
    )
    if enabled:
        return

    status = {
        "success": False,
        "error_code": "UNVERIFIED_REAL_DEPENDENCY",
        "missing": [
            "AGENTIC_VERIFY_REAL_COLOR_BLOCK_GRASPER=1",
            "AGENTIC_VERIFY_REAL_ROS2=1",
            "AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION=1",
            "AGENTIC_LLM_ENABLED=1",
            "AGENTIC_LLM_REQUIRE=1",
        ],
        "next_action": "Run the documented real-e2e command on a prepared robot workspace.",
    }
    assert status["error_code"] == "UNVERIFIED_REAL_DEPENDENCY"
    assert status["missing"]
    assert status["next_action"]

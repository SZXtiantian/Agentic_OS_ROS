from pathlib import Path


def test_dispatcher_source_has_no_direct_ros_imports_or_calls():
    root = Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_runtime/dispatcher")
    forbidden = [
        "import " + "rclpy",
        "from " + "rclpy",
        "/" + "cmd_vel",
        "/" + "scan",
        "/" + "odom",
        "/" + "tf",
        "/" + "servo_controller",
        "/" + "kinematics",
        "Move" + "Group",
        "Action" + "Client",
        "create_" + "publisher",
        "create_" + "subscription",
    ]
    for path in root.rglob("*"):
        if path.suffix not in {".py", ".md", ".json", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in text, f"{path} contains {pattern}"

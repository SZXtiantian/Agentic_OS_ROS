# Testing Agent Apps

Recommended coverage:

- Manifest fields
- Forbidden ROS2 calls
- Permission-denied failures
- Missing-bridge failures
- SDK call order
- Structured error returns

## Commands

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
```

## Boundary tests

Tests should ensure app source does not contain:

- `rclpy`
- `/cmd_vel`
- `NavigateToPose`
- `MoveGroup`
- `ros2`

Without a real bridge, robot paths should return `ROS_BRIDGE_UNAVAILABLE` or a related structured error.

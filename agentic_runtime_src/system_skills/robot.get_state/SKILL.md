# robot.get_state

```json agentic-skill
{
  "access": {
    "required": false
  },
  "implementation": {
    "bridge": "state_bridge_node",
    "client_method": "get_robot_state",
    "service": "/agentic/robot/get_state",
    "service_type": "agentic_msgs/srv/GetRobotState",
    "type": "ros2_service"
  },
  "input_schema": {
    "properties": {},
    "required": [],
    "type": "object"
  },
  "name": "robot.get_state",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "state": {
        "type": "object"
      },
      "success": {
        "type": "boolean"
      }
    },
    "required": [
      "success",
      "state"
    ],
    "type": "object"
  },
  "permission_requirements": [
    "robot.state.read"
  ],
  "resource_requirements": {
    "locks": []
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": false,
    "require_estop_released": false
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 10
}
```

## Purpose

Get current robot state.

## Usage

Call this skill through the Agentic Runtime skill API. Agent Apps must not call ROS2, Nav2, MoveIt, robot topics, or vendor drivers directly.

## Inputs

The Runtime validates arguments against `input_schema` from the `agentic-skill` metadata block.

## Outputs

The Runtime normalizes provider responses against `output_schema` and returns a structured `SkillResult`.

## Safety

Permission checks, access checks, resource locks, safety checks, timeouts, cancellation, system call records, and audit logs are enforced by the Runtime before the implementation is invoked.

## Implementation

Execution is selected from `implementation.type`; Runtime dispatch must not route by skill name.

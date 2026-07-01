# robot.stop

```json agentic-skill
{
  "access": {
    "irreversible": false,
    "required": true,
    "resource_type": "robot_motion"
  },
  "implementation": {
    "bridge": "safety_guard_node",
    "cancels_session": true,
    "client_defaults": {
      "reason": "app_requested"
    },
    "client_method": "stop_robot",
    "request_id_field": "request_id",
    "service": "/agentic/robot/stop",
    "service_type": "agentic_msgs/srv/StopRobot",
    "type": "ros2_service"
  },
  "input_schema": {
    "properties": {
      "reason": {
        "type": "string"
      }
    },
    "required": [],
    "type": "object"
  },
  "name": "robot.stop",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "message": {
        "type": "string"
      },
      "success": {
        "type": "boolean"
      }
    },
    "required": [
      "success"
    ],
    "type": "object"
  },
  "permission_requirements": [
    "robot.stop"
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
    "audit_required": true,
    "bypass_normal_queue": true,
    "highest_priority": true
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 10
}
```

## Purpose

Stop robot immediately through safety guard.

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

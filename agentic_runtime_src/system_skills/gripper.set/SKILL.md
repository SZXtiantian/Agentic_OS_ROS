# gripper.set

```json agentic-skill
{
  "access": {
    "irreversible": true,
    "required": true,
    "resource_type": "robot_motion"
  },
  "implementation": {
    "bridge": "manipulation_bridge_node",
    "client_defaults": {
      "force": "low",
      "timeout_s": 5
    },
    "client_method": "set_gripper",
    "json_output_fields": {
      "result": "result_json"
    },
    "request_id_field": "request_id",
    "ros2_backend_type": "servo_controller",
    "service": "/agentic/gripper/set",
    "service_type": "agentic_msgs/srv/SetGripper",
    "type": "ros2_service"
  },
  "input_schema": {
    "properties": {
      "command": {
        "type": "string"
      },
      "force": {
        "type": "string"
      },
      "percentage": {
        "maximum": 100,
        "minimum": 0,
        "type": "number"
      },
      "timeout_s": {
        "maximum": 5,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "command"
    ],
    "type": "object"
  },
  "name": "gripper.set",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "error_code": {
        "type": "string"
      },
      "reason": {
        "type": "string"
      },
      "result": {
        "type": "object"
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
    "gripper.control"
  ],
  "resource_requirements": {
    "locks": [
      "gripper"
    ]
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": true,
    "gripper_allowlist": true,
    "max_duration_s": 5,
    "require_estop_released": true,
    "runtime_timeout_margin_s": 1
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 5
}
```

## Purpose

Execute an allowlisted gripper command through AgenticOS bridge limits.

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

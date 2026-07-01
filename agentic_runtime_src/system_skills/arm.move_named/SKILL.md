# arm.move_named

```json agentic-skill
{
  "access": {
    "irreversible": true,
    "required": true,
    "resource_type": "robot_motion"
  },
  "implementation": {
    "action": "/agentic/arm/move_named",
    "action_type": "agentic_msgs/action/MoveArmNamed",
    "bridge": "manipulation_bridge_node",
    "client_defaults": {
      "timeout_s": 8
    },
    "client_method": "move_arm_named",
    "json_output_fields": {
      "result": "result_json"
    },
    "request_id_field": "request_id",
    "ros2_backend_type": "openclaw_action_group",
    "type": "ros2_action"
  },
  "input_schema": {
    "properties": {
      "name": {
        "type": "string"
      },
      "timeout_s": {
        "maximum": 8,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "name"
    ],
    "type": "object"
  },
  "name": "arm.move_named",
  "observability": {
    "audit": true,
    "record_feedback": true,
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
    "arm.move.named"
  ],
  "resource_requirements": {
    "locks": [
      "arm"
    ]
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": true,
    "max_duration_s": 8,
    "named_action_allowlist": true,
    "require_estop_released": true,
    "runtime_timeout_margin_s": 2,
    "workspace_bounds_check": true
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 8
}
```

## Purpose

Execute an allowlisted named arm action.

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

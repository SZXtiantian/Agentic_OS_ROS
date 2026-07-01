# robot.navigate_to

```json agentic-skill
{
  "access": {
    "irreversible": true,
    "required": true,
    "resource_type": "robot_motion"
  },
  "implementation": {
    "action": "/agentic/robot/navigate_to_place",
    "action_type": "agentic_msgs/action/NavigateToPlace",
    "bridge": "navigation_bridge_node",
    "client_defaults": {
      "timeout_s": 120
    },
    "client_method": "navigate_to",
    "json_output_fields": {
      "result": "result_json"
    },
    "request_id_field": "request_id",
    "ros2_backend_action": "/navigate_to_pose",
    "ros2_backend_action_type": "nav2_msgs/action/NavigateToPose",
    "type": "ros2_action"
  },
  "input_schema": {
    "properties": {
      "place": {
        "type": "string"
      },
      "timeout_s": {
        "maximum": 300,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "place"
    ],
    "type": "object"
  },
  "name": "robot.navigate_to",
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
      "success",
      "reason"
    ],
    "type": "object"
  },
  "permission_requirements": [
    "robot.move"
  ],
  "resource_requirements": {
    "locks": [
      "base"
    ]
  },
  "retry_policy": {
    "max_attempts": 1,
    "retry_on": [
      "NAVIGATION_TRANSIENT_FAILURE"
    ]
  },
  "safety_constraints": {
    "allow_cancel": true,
    "forbidden_zone_check": true,
    "max_duration_s": 120,
    "max_linear_speed_mps": 0.5,
    "require_estop_released": true,
    "require_known_place": true,
    "require_localized": true
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 120
}
```

## Purpose

Navigate robot to a registered place.

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

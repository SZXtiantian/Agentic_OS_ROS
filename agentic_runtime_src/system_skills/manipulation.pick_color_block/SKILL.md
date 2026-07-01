# manipulation.pick_color_block

```json agentic-skill
{
  "access": {
    "irreversible": true,
    "required": true,
    "resource_type": "robot_motion"
  },
  "implementation": {
    "action": "/agentic/manipulation/pick_color_block",
    "action_type": "agentic_msgs/action/PickColorBlock",
    "availability": "real_bridge_required",
    "bridge": "manipulation_bridge_node",
    "client_defaults": {
      "detection": {},
      "evidence": {},
      "target": "workspace",
      "timeout_s": 60
    },
    "client_method": "pick_color_block",
    "json_output_fields": {
      "result": "result_json"
    },
    "json_payload_fields": {
      "detection_json": "detection",
      "evidence_json": "evidence"
    },
    "request_id_field": "request_id",
    "type": "ros2_action"
  },
  "input_schema": {
    "properties": {
      "color": {
        "enum": [
          "red",
          "green",
          "blue",
          "yellow"
        ],
        "type": "string"
      },
      "detection": {
        "type": "object"
      },
      "evidence": {
        "type": "object"
      },
      "target": {
        "type": "string"
      },
      "timeout_s": {
        "maximum": 60,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "color"
    ],
    "type": "object"
  },
  "name": "manipulation.pick_color_block",
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
    "manipulation.pick.color_block"
  ],
  "resource_requirements": {
    "locks": [
      "arm",
      "gripper",
      "camera",
      "manipulation_backend"
    ]
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": true,
    "max_duration_s": 60,
    "require_estop_released": true,
    "runtime_timeout_margin_s": 5,
    "workspace_bounds_check": true
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 60
}
```

## Purpose

Pick a detected colored block through the Agentic manipulation bridge.

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

# perception.center_color_block

```json agentic-skill
{
  "access": {
    "irreversible": false,
    "required": true,
    "resource_type": "robot_sensor"
  },
  "implementation": {
    "availability": "real_bridge_required",
    "bridge": "inspection_bridge_node",
    "client_defaults": {
      "evidence_label": "center_color_block",
      "target": "workspace",
      "timeout_s": 8
    },
    "client_method": "center_color_block",
    "json_output_fields": {
      "alignment": "alignment_json",
      "evidence": "evidence_json"
    },
    "request_id_field": "request_id",
    "service": "/agentic/perception/center_color_block",
    "service_type": "agentic_msgs/srv/CenterColorBlock",
    "type": "ros2_service"
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
      "evidence_label": {
        "default": "center_color_block",
        "type": "string"
      },
      "target": {
        "default": "workspace",
        "type": "string"
      },
      "timeout_s": {
        "default": 8,
        "maximum": 30,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "color"
    ],
    "type": "object"
  },
  "name": "perception.center_color_block",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "alignment": {
        "type": "object"
      },
      "error_code": {
        "type": "string"
      },
      "evidence": {
        "type": "object"
      },
      "reason": {
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
    "perception.center.color_block",
    "arm.move.named"
  ],
  "resource_requirements": {
    "locks": [
      "camera",
      "arm",
      "color_block_detector"
    ]
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": true,
    "camera_target_allowlist": true,
    "max_duration_s": 30,
    "require_estop_released": true,
    "runtime_timeout_margin_s": 5
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 30
}
```

## Purpose

Slow visual alignment of a detected color block into the camera center before grasp planning.

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

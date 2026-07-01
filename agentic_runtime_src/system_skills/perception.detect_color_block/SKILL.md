# perception.detect_color_block

```json agentic-skill
{
  "access": {
    "irreversible": false,
    "required": true,
    "resource_type": "robot_sensor"
  },
  "implementation": {
    "availability": "real_bridge_required",
    "bridge": "perception_bridge_node",
    "client_defaults": {
      "evidence_label": "color_block",
      "target": "workspace",
      "timeout_s": 30
    },
    "client_method": "detect_color_block",
    "json_output_fields": {
      "detection": "detection_json",
      "evidence": "evidence_json"
    },
    "request_id_field": "request_id",
    "service": "/agentic/perception/detect_color_block",
    "service_type": "agentic_msgs/srv/DetectColorBlock",
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
        "type": "string"
      },
      "target": {
        "type": "string"
      },
      "timeout_s": {
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
  "name": "perception.detect_color_block",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "detection": {
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
    "perception.detect.color_block"
  ],
  "resource_requirements": {
    "locks": [
      "camera",
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
    "require_estop_released": false,
    "runtime_timeout_margin_s": 5
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 30
}
```

## Purpose

Detect a real colored block through the Agentic perception bridge.

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

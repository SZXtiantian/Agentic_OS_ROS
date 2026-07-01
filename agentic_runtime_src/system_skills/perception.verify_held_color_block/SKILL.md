# perception.verify_held_color_block

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
      "detection": {},
      "evidence_label": "held_color_block",
      "pick_result": {},
      "target": "workspace",
      "timeout_s": 30
    },
    "client_method": "verify_held_color_block",
    "json_output_fields": {
      "evidence": "evidence_json",
      "verification": "verification_json"
    },
    "json_payload_fields": {
      "detection_json": "detection",
      "pick_result_json": "pick_result"
    },
    "request_id_field": "request_id",
    "service": "/agentic/perception/verify_held_color_block",
    "service_type": "agentic_msgs/srv/VerifyHeldColorBlock",
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
      "detection": {
        "type": "object"
      },
      "evidence_label": {
        "type": "string"
      },
      "pick_result": {
        "type": "object"
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
      "color",
      "detection",
      "pick_result"
    ],
    "type": "object"
  },
  "name": "perception.verify_held_color_block",
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
      "evidence": {
        "type": "object"
      },
      "reason": {
        "type": "string"
      },
      "success": {
        "type": "boolean"
      },
      "verification": {
        "type": "object"
      },
      "verified_held": {
        "type": "boolean"
      }
    },
    "required": [
      "success",
      "verified_held"
    ],
    "type": "object"
  },
  "permission_requirements": [
    "perception.verify.color_block_held"
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

Independently verify a picked colored block is visible in the gripper-held ROI through the Agentic perception bridge.

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

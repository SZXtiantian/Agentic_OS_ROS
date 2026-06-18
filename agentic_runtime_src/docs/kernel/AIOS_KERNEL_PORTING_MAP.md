# AIOS Kernel Porting Map

This map is the Phase 2 reference for comparing AIOS kernel concepts with the
Agentic OS ROS kernel. AIOS is used as an architecture reference only; robot
motion remains behind Agentic OS safety, access, resource, audit, and bridge
boundaries.

| AIOS reference | Agentic OS ROS landing zone | Porting status |
| --- | --- | --- |
| `AIOS/aios/syscall` | `agentic_os/kernel/system_call` | typed syscall lifecycle, queues, and structured responses |
| `AIOS/aios/scheduler` | `agentic_os/kernel/scheduler` | FIFO/RR scheduler lanes and processing threads |
| `AIOS/aios/context` | `agentic_os/kernel/context` | session and generation context snapshots |
| `AIOS/aios/llm_core` | `agentic_os/kernel/llm_core` | provider registry, routing, batching, and normalization |
| `AIOS/aios/memory` | `agentic_os/kernel/memory` | two-tier memory, retrieval, and compression shells |
| `AIOS/aios/storage` | `agentic_os/kernel/storage` | safe storage syscall surface and LSFS-compatible semantics |
| `AIOS/aios/tool` | `agentic_os/kernel/tool` | manifest tools, sandbox policy, MCP lifecycle shell, conflict locks |
| AIOS access docs | `agentic_os/kernel/access` | persistent ACL, dynamic ACL, intervention, and decision logs |
| `AIOS/aios/hooks` | `agentic_os/kernel/hooks` | queue events, metrics, and observability hooks |
| `AIOS/aios/terminal` | admin diagnostics only | not ported to robot motion paths |

## Safety Boundaries

- `agentic_os/**`, `agentic_runtime/**`, and `agentic_apps/**` must not import
  `rclpy`.
- ROS2-specific code belongs under `ros2_bridge_src/**`.
- Generic tools must not expose `robot.*`, `arm.*`, `gripper.*`,
  `perception.*`, `ros2.*`, `nav2.*`, `moveit.*`, `cmd_vel`, or `/cmd_vel`.
- Robot motion must go through `RobotCapabilityManager` or `SkillExecutor`,
  with permission checks, access checks, resource arbitration, safety guards,
  audit logging, and the bridge client.

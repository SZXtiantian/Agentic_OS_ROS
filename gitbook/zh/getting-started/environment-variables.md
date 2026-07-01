# 环境变量配置

常用环境变量：

| 变量 | 用途 |
| --- | --- |
| `AGENTIC_RUNTIME_SRC` | Runtime 源码根目录 |
| `AGENTIC_APP_ROOT` | Agent App 根目录 |
| `AGENTIC_SKILL_PROVIDER_ROOT` | system skills 根目录 |
| `AGENTIC_HOME` | 安装根，默认 `/opt/agentic` |
| `AGENTIC_VAR` | audit、memory、session、report 等运行状态根目录 |
| `AGENTIC_SESSION_ROOT` | session/syscall 存储目录 |
| `AGENTIC_STORAGE_ROOT` | Runtime storage 根目录 |
| `AGENTIC_CONTEXT_ROOT` | Runtime context 根目录 |
| `AGENTIC_REPORT_LOG` | `report.say` 文件输出路径 |
| `AGENTIC_OPERATOR_INTERVENTION_APPROVED` | operator intervention 许可开关 |
| `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION` | 允许真实机械臂动作 |
| `AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION` | 允许真实抓取/放置类 manipulation |

## Real-only 约束

配置中的 `mock`、`fake`、`stub`、`dummy`、`simulated` backend/type 值会被拒绝。缺少真实依赖时必须返回结构化错误，例如 `ROS_BRIDGE_UNAVAILABLE` 或 `UNVERIFIED_REAL_DEPENDENCY`。

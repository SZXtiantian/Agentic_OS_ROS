# Summary

## 中文

* [欢迎](zh/README.md)

### Getting Started
* [安装](zh/getting-started/installation.md)
* [快速开始](zh/getting-started/quickstart.md)
* [环境变量配置](zh/getting-started/environment-variables.md)

### Agentic Runtime
* [Runtime 概览](zh/agentic-runtime/overview.md)
* [架构边界](zh/agentic-runtime/architecture.md)
* [权限、安全与审计](zh/agentic-runtime/permissions-safety-audit.md)
* [Runtime 错误模型](zh/agentic-runtime/errors.md)

### Agent App
* [如何使用 Agent App](zh/agentic-app/overview.md)
* [如何开发 Agent App](zh/agentic-app/develop-agent-apps.md)
* [App Manifest](zh/agentic-app/app-manifest.md)
* [测试 Agent App](zh/agentic-app/testing.md)

### Agent App SDK
* [SDK 概览](zh/sdk/overview.md)
* [Robot API](zh/sdk/robot-api/README.md)
  * [ctx.robot.get_state](zh/sdk/robot-api/get_state.md)
  * [ctx.robot.navigate_to](zh/sdk/robot-api/navigate_to.md)
  * [ctx.robot.inspect_area](zh/sdk/robot-api/inspect_area.md)
  * [ctx.robot.stop](zh/sdk/robot-api/stop.md)
* [World API](zh/sdk/world-api/README.md)
  * [ctx.world.resolve_place](zh/sdk/world-api/resolve_place.md)
* [Memory API](zh/sdk/memory-api/README.md)
  * [ctx.memory.remember](zh/sdk/memory-api/remember.md)
  * [ctx.memory.recall](zh/sdk/memory-api/recall.md)
* [Human API](zh/sdk/human-api/README.md)
  * [ctx.human.ask](zh/sdk/human-api/ask.md)
* [Report API](zh/sdk/report-api/README.md)
  * [ctx.report.say](zh/sdk/report-api/say.md)
  * [ctx.report.log](zh/sdk/report-api/log.md)
* [LLM API](zh/sdk/llm-api/README.md)
  * [ctx.llm.chat_json](zh/sdk/llm-api/chat_json.md)
* [Perception API](zh/sdk/perception-api/README.md)
  * [ctx.perception.observe](zh/sdk/perception-api/observe.md)
  * [ctx.perception.capture_photo](zh/sdk/perception-api/capture_photo.md)
  * [perception.detect_color_block](zh/sdk/perception-api/detect_color_block.md)
  * [perception.center_color_block](zh/sdk/perception-api/center_color_block.md)
  * [perception.verify_held_color_block](zh/sdk/perception-api/verify_held_color_block.md)
* [Arm API](zh/sdk/arm-api/README.md)
  * [ctx.arm.get_state](zh/sdk/arm-api/get_state.md)
  * [ctx.arm.move_named](zh/sdk/arm-api/move_named.md)
* [Gripper API](zh/sdk/gripper-api/README.md)
  * [ctx.gripper.open](zh/sdk/gripper-api/open.md)
  * [ctx.gripper.close](zh/sdk/gripper-api/close.md)
  * [ctx.gripper.set](zh/sdk/gripper-api/set.md)
* [Storage API](zh/sdk/storage-api/README.md)
  * [ctx.storage.list_recent_photos](zh/sdk/storage-api/list_recent_photos.md)
* [Kernel API](zh/sdk/kernel-api/README.md)
  * [context](zh/sdk/kernel-api/context.md)
  * [memory](zh/sdk/kernel-api/memory.md)
  * [storage](zh/sdk/kernel-api/storage.md)
  * [tool](zh/sdk/kernel-api/tool.md)
  * [skill](zh/sdk/kernel-api/skill.md)
  * [llm](zh/sdk/kernel-api/llm.md)
  * [access](zh/sdk/kernel-api/access.md)

### Reference
* [System Skills](zh/reference/system-skills.md)
* [错误码](zh/reference/errors.md)

### Community
* [如何贡献](zh/community/contribute.md)

## English

* [Welcome](en/README.md)

### Getting Started
* [Installation](en/getting-started/installation.md)
* [Quickstart](en/getting-started/quickstart.md)
* [Environment Variables Configuration](en/getting-started/environment-variables.md)

### Agentic Runtime
* [Runtime Overview](en/agentic-runtime/overview.md)
* [Architecture Boundaries](en/agentic-runtime/architecture.md)
* [Permissions, Safety, and Audit](en/agentic-runtime/permissions-safety-audit.md)
* [Runtime Error Model](en/agentic-runtime/errors.md)

### Agent App
* [How to Use Agent Apps](en/agentic-app/overview.md)
* [How to Develop Agent Apps](en/agentic-app/develop-agent-apps.md)
* [App Manifest](en/agentic-app/app-manifest.md)
* [Testing Agent Apps](en/agentic-app/testing.md)

### Agent App SDK
* [SDK Overview](en/sdk/overview.md)
* [Robot API](en/sdk/robot-api/README.md)
  * [ctx.robot.get_state](en/sdk/robot-api/get_state.md)
  * [ctx.robot.navigate_to](en/sdk/robot-api/navigate_to.md)
  * [ctx.robot.inspect_area](en/sdk/robot-api/inspect_area.md)
  * [ctx.robot.stop](en/sdk/robot-api/stop.md)
* [World API](en/sdk/world-api/README.md)
  * [ctx.world.resolve_place](en/sdk/world-api/resolve_place.md)
* [Memory API](en/sdk/memory-api/README.md)
  * [ctx.memory.remember](en/sdk/memory-api/remember.md)
  * [ctx.memory.recall](en/sdk/memory-api/recall.md)
* [Human API](en/sdk/human-api/README.md)
  * [ctx.human.ask](en/sdk/human-api/ask.md)
* [Report API](en/sdk/report-api/README.md)
  * [ctx.report.say](en/sdk/report-api/say.md)
  * [ctx.report.log](en/sdk/report-api/log.md)
* [LLM API](en/sdk/llm-api/README.md)
  * [ctx.llm.chat_json](en/sdk/llm-api/chat_json.md)
* [Perception API](en/sdk/perception-api/README.md)
  * [ctx.perception.observe](en/sdk/perception-api/observe.md)
  * [ctx.perception.capture_photo](en/sdk/perception-api/capture_photo.md)
  * [perception.detect_color_block](en/sdk/perception-api/detect_color_block.md)
  * [perception.center_color_block](en/sdk/perception-api/center_color_block.md)
  * [perception.verify_held_color_block](en/sdk/perception-api/verify_held_color_block.md)
* [Arm API](en/sdk/arm-api/README.md)
  * [ctx.arm.get_state](en/sdk/arm-api/get_state.md)
  * [ctx.arm.move_named](en/sdk/arm-api/move_named.md)
* [Gripper API](en/sdk/gripper-api/README.md)
  * [ctx.gripper.open](en/sdk/gripper-api/open.md)
  * [ctx.gripper.close](en/sdk/gripper-api/close.md)
  * [ctx.gripper.set](en/sdk/gripper-api/set.md)
* [Storage API](en/sdk/storage-api/README.md)
  * [ctx.storage.list_recent_photos](en/sdk/storage-api/list_recent_photos.md)
* [Kernel API](en/sdk/kernel-api/README.md)
  * [context](en/sdk/kernel-api/context.md)
  * [memory](en/sdk/kernel-api/memory.md)
  * [storage](en/sdk/kernel-api/storage.md)
  * [tool](en/sdk/kernel-api/tool.md)
  * [skill](en/sdk/kernel-api/skill.md)
  * [llm](en/sdk/kernel-api/llm.md)
  * [access](en/sdk/kernel-api/access.md)

### Reference
* [System Skills](en/reference/system-skills.md)
* [Error Codes](en/reference/errors.md)

### Community
* [How to Contribute](en/community/contribute.md)

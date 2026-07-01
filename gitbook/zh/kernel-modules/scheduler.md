# scheduler

Source: `agentic_runtime_src/agentic_os/kernel/scheduler`

`scheduler` 管理 Runtime 内部 syscall、task graph、lane、resource lease、preemption 和 audit lifecycle。

## App 可用入口

当前暂无直接 App API。

## 当前状态

App 通过 SDK/skill 发起请求，Runtime 再把请求交给 scheduler。面向 App 的调度状态查询、任务图诊断和取消接口会在后续完善。

## 开发者注意

- App 不应该直接构造 scheduler TaskNode 来调用 ROS2、Nav2 或 MoveIt。
- 机器人运动走专用 lane，并且默认不可抢占。
- App 想取消任务时，应使用 Runtime 暴露的 cancel/status facade，而不是直接操作 scheduler 内部队列。

# model_library

Source: `agentic_runtime_src/agentic_os/kernel/model_library`

`model_library` 是 edge、side 和 optional model 管理 contract。

## App 可用入口

当前暂无稳定的直接 App API。

## 当前状态

该模块用于未来模型路由和模型资产管理。面向 App 的模型查询、模型选择和本地模型调用接口会在后续完善。

## 开发者注意

当前 App 应通过 `ctx.llm.*` 或明确的 perception/system skill 使用模型能力，不要直接依赖 `model_library` 内部类。

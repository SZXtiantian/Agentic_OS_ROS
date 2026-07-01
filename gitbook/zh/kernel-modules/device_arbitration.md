# device_arbitration

Source: `agentic_runtime_src/agentic_os/kernel/device_arbitration`

`device_arbitration` 负责物理设备所有权和资源仲裁，例如 base、camera、arm、gripper。

## App 可用入口

当前暂无直接 App API。

## 当前状态

App 通过 system skill 的 `resource_requirements.locks` 间接触发资源仲裁。面向 App 的设备占用查询、等待队列查询和诊断接口会在后续完善。

## 开发者注意

- 在 `app.yaml` 的 `resources` 里声明 App 需要的设备。
- 在 skill contract 中声明资源锁。
- App 不应该自行实现设备锁。

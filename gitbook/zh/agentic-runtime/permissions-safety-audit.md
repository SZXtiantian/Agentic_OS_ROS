# 权限、安全与审计

危险机器人动作必须经过完整 Runtime 链路。

## 执行顺序

1. JSON Schema 输入校验
2. App manifest 权限检查
3. Kernel access/intervention
4. Safety guard
5. Resource lock
6. Timeout/cancellation
7. Backend dispatch
8. Audit/syscall/session 记录
9. 释放资源锁

## 资源锁

| 资源 | 典型能力 |
| --- | --- |
| `base` | 导航 |
| `camera` | 检查、观察、拍照 |
| `arm` | 机械臂命名动作 |
| `gripper` | 夹爪控制 |
| `color_block_detector` | 色块检测/验证 |

## Audit

Audit log 是 JSONL，记录 app、session、skill、args、permission、safety、resource lock、backend、status、error code 和 duration。

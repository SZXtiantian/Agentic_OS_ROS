# Module Mapping

## Installation And Workspace Layers

```text
/opt/ros/humble
  -> ROS2 系统安装层

/opt/agentic
  -> Agentic OS 系统安装层

/home/ubuntu/ros2_ws
  -> Robot ROS2 application workspace

/home/ubuntu/agentic_ws
  -> Agentic Runtime source + Agent Apps development workspace

/home/ubuntu/agentic_ws/src
  -> Agent App workspace

/home/ubuntu/agentic_ws/src/agentic_runtime_src
  -> Agentic Runtime source, installer, tests, and AgenticOS kernel source

/home/ubuntu/agentic_ws/ros2_bridge_src
  -> Agentic-owned ROS2 bridge source packages
```

## Architecture Module Paths

```text
Agentic APP
  -> /home/ubuntu/agentic_ws/src/*_agent

巡检Agent
  -> /home/ubuntu/agentic_ws/src/inspection_agent

取件Agent
  -> /home/ubuntu/agentic_ws/src/pickup_agent

叠衣Agent
  -> /home/ubuntu/agentic_ws/src/laundry_agent

Robotic Coding Agent
  -> /home/ubuntu/agentic_ws/src/robotic_coding_agent

RobotOps
  -> /home/ubuntu/agentic_ws/src/robotops_agent

Agentic SDK
  -> /opt/agentic/sdk
  -> runtime implementation: /opt/agentic/lib/python3/agentic_runtime/sdk

Embodied-Oriented Agentic OS Kernel
  -> /opt/agentic/agentic_os/kernel
  -> source: /home/ubuntu/agentic_ws/src/agentic_runtime_src/agentic_os/kernel
  -> import namespace: agentic_os.kernel

Agentic System Call
  -> /opt/agentic/agentic_os/kernel/system_call

Capability Registry / HAL Table
  -> /opt/agentic/agentic_os/kernel/capability
  -> maps Agent APIs to runtime_internal, ROS2 service/action/topic, Nav2, MoveIt, perception, or hardware-driver capabilities

系统 skill 库
  -> /opt/agentic/agentic_os/kernel/skill_library
  -> /opt/agentic/system_skills

Memory Management
  -> /opt/agentic/agentic_os/kernel/memory
  -> /opt/agentic/var/memory

端侧模型库
  -> /opt/agentic/agentic_os/kernel/model_library

Context Management
  -> /opt/agentic/agentic_os/kernel/context

Tool Management
  -> /opt/agentic/agentic_os/kernel/tool

Storage Management
  -> /opt/agentic/agentic_os/kernel/storage
  -> /opt/agentic/var/storage

Agent Scheduler
  -> /opt/agentic/agentic_os/kernel/scheduler

Agent-friendly Perception
  -> /opt/agentic/agentic_os/kernel/perception

Device Arbitration
  -> /opt/agentic/agentic_os/kernel/device_arbitration

World Model
  -> /opt/agentic/agentic_os/kernel/world_model
  -> /opt/agentic/var/world_model

Security
  -> /opt/agentic/agentic_os/security

模型安全性
  -> /opt/agentic/agentic_os/security/model_security

系统安全性
  -> /opt/agentic/agentic_os/security/system_security

传感器/执行器安全
  -> /opt/agentic/agentic_os/security/sensor_actuator_security

Traditional OS Kernel
  -> /opt/ros/humble
  -> /home/ubuntu/ros2_ws

Agentic ROS2 Bridge
  -> /home/ubuntu/agentic_ws/ros2_bridge_src
  -> source-only current colcon workspace for AgenticOS-owned bridge packages
  -> build: /home/ubuntu/agentic_ws/build/ros2_bridge
  -> install: /home/ubuntu/agentic_ws/install/ros2_bridge
  -> installed ownership/config: /opt/agentic/bridges/ros2

Hardware Contracts
  -> /opt/agentic/agentic_os/hardware

Concrete Hardware / Middleware Adapters
  -> /opt/agentic/bridges/<type>
```

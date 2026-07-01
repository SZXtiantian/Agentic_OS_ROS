# ROS2 System Skill Nodes

ROS2 remains installed at `/opt/ros/humble`.

Agentic-owned ROS2 adapter packages live in `/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_*` and are the only Agentic layer allowed to import `rclpy`.

Runtime uses `skill_provider_transport: cli` to call Agentic-owned system skill services/actions without importing ROS2 Python APIs. Agent Apps and `agentic_runtime` code must stay free of `rclpy`, ROS2 topic clients, Nav2 action clients, MoveIt clients, and vendor driver imports.

Build system skill nodes:

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/agentic_ws
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_system_skill_nodes.sh
```

Run robot skills:

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_skills.sh
```

Robot profile files live under:

```text
agentic_runtime_src/configs/robot_profiles/
/opt/agentic/etc/robot_profiles/
```

`/home/ubuntu/ros2_ws/src` is reserved for robot ROS2 application packages such as calibration, drivers, navigation, perception, launch files, and robot-specific nodes. It must not contain Agentic Runtime or Agent App source packages.

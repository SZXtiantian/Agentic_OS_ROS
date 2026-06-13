# Nav2 Integration Plan

MVP navigation can use `MockRosBridgeClient` for offline unit tests, but this
host is configured as a real-robot test environment.

The ROS2 `navigation_bridge_node` also has a real Nav2 path: with
`mock_nav:=false`, it translates AgenticOS `NavigateToPlace` goals into Nav2
`NavigateToPose` goals inside the bridge package. Runtime, SDK, and Agent Apps
still do not import `rclpy` or `nav2_msgs`.

For real Nav2:

1. Source environments in order:

   ```bash
   source /opt/ros/humble/setup.bash
   source /opt/agentic/setup.bash
   source /home/ubuntu/ros2_ws/install/setup.bash
   source /home/ubuntu/agentic_ws/setup.bash
   ```

2. Start robot bringup, map, localization, and Nav2.
3. Verify:

   ```bash
   ros2 action list | grep navigate
   ros2 action info /navigate_to_pose
   ```

4. Run the Agentic navigation bridge against Nav2:

   ```bash
   ros2 run agentic_capability_bridge navigation_bridge_node --ros-args \
     -p mock_nav:=false \
     -p places_file:=/opt/agentic/etc/places.yaml \
     -p nav2_action_name:=/navigate_to_pose
   ```

5. Use the real-robot runtime profile:

   ```bash
   export AGENTIC_RUNTIME_CONFIG=/opt/agentic/etc/agentic_robot.yaml
   ```

   Then run the app with `--real` so Runtime uses the non-rclpy ROS2 CLI transport.
6. Keep forbidden-zone checks in Runtime and safety guard. A forbidden place
   must not send a Nav2 goal.

Not yet verified automatically in this workspace:

- A running Nav2 stack accepting `/navigate_to_pose`.
- Physical navigation success.

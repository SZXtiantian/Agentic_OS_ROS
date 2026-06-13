from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    places_file = LaunchConfiguration("places_file")
    safety_file = LaunchConfiguration("safety_file")
    robot_id = LaunchConfiguration("robot_id")
    nav2_action_name = LaunchConfiguration("nav2_action_name")

    return LaunchDescription(
        [
            DeclareLaunchArgument("places_file", default_value="/opt/agentic/etc/places.yaml"),
            DeclareLaunchArgument("safety_file", default_value="/opt/agentic/etc/safety.yaml"),
            DeclareLaunchArgument("robot_id", default_value="real_robot"),
            DeclareLaunchArgument("nav2_action_name", default_value="/navigate_to_pose"),
            Node(
                package="agentic_world_model",
                executable="world_model_node",
                output="screen",
                parameters=[{"places_file": places_file}],
            ),
            Node(
                package="agentic_safety_guard",
                executable="safety_guard_node",
                output="screen",
                parameters=[{"places_file": places_file, "safety_file": safety_file}],
            ),
            Node(
                package="agentic_capability_bridge",
                executable="state_bridge_node",
                output="screen",
                parameters=[{"robot_id": robot_id, "mode": "real_nav2"}],
            ),
            Node(package="agentic_capability_bridge", executable="inspection_bridge_node", output="screen"),
            Node(
                package="agentic_capability_bridge",
                executable="navigation_bridge_node",
                output="screen",
                parameters=[
                    {
                        "mock_nav": False,
                        "places_file": places_file,
                        "nav2_action_name": nav2_action_name,
                        "nav2_server_timeout_s": 10.0,
                    }
                ],
            ),
        ]
    )

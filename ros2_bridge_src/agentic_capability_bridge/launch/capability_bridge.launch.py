from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    places_file = LaunchConfiguration("places_file")
    robot_id = LaunchConfiguration("robot_id")
    nav2_action_name = LaunchConfiguration("nav2_action_name")
    bridge_profile_file = LaunchConfiguration("bridge_profile_file")

    return LaunchDescription(
        [
            DeclareLaunchArgument("places_file", default_value="/opt/agentic/etc/places.yaml"),
            DeclareLaunchArgument("robot_id", default_value="real_robot"),
            DeclareLaunchArgument("nav2_action_name", default_value="/navigate_to_pose"),
            DeclareLaunchArgument(
                "bridge_profile_file",
                default_value="/opt/agentic/etc/robot_profiles/rosorin_arm_camera.yaml",
            ),
            Node(
                package="agentic_capability_bridge",
                executable="state_bridge_node",
                output="screen",
                parameters=[{"robot_id": robot_id, "mode": "real_nav2", "bridge_profile_file": bridge_profile_file}],
            ),
            Node(
                package="agentic_capability_bridge",
                executable="inspection_bridge_node",
                output="screen",
                parameters=[{"bridge_profile_file": bridge_profile_file}],
            ),
            Node(
                package="agentic_capability_bridge",
                executable="manipulation_bridge_node",
                output="screen",
                parameters=[{"bridge_profile_file": bridge_profile_file}],
            ),
            Node(
                package="agentic_capability_bridge",
                executable="navigation_bridge_node",
                output="screen",
                parameters=[
                    {
                        "places_file": places_file,
                        "nav2_action_name": nav2_action_name,
                    }
                ],
            ),
        ]
    )

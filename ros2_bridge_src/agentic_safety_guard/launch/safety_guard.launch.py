from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bridge_profile_file = LaunchConfiguration("bridge_profile_file")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "bridge_profile_file",
                default_value="/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml",
            ),
            Node(
                package="agentic_safety_guard",
                executable="safety_guard_node",
                name="safety_guard_node",
                output="screen",
                parameters=[{"bridge_profile_file": bridge_profile_file}],
            )
        ]
    )

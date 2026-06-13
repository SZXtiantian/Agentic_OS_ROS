from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="agentic_safety_guard",
                executable="safety_guard_node",
                name="safety_guard_node",
                output="screen",
            )
        ]
    )

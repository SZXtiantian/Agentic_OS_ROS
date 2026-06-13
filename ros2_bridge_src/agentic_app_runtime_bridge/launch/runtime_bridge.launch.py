from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="agentic_app_runtime_bridge",
                executable="runtime_bridge_node",
                name="runtime_bridge_node",
                output="screen",
            )
        ]
    )

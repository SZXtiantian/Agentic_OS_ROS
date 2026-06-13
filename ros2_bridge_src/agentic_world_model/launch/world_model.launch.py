from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="agentic_world_model",
                executable="world_model_node",
                name="world_model_node",
                output="screen",
            )
        ]
    )

import rclpy
from rclpy.node import Node


class RuntimeBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("runtime_bridge_node")
        self.get_logger().info(
            "agentic runtime bridge skeleton ready; foundation Runtime uses direct bridge client abstraction"
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RuntimeBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

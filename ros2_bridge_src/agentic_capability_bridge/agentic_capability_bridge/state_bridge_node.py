import json

import rclpy
from agentic_msgs.srv import GetRobotState
from rclpy.node import Node


class StateBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("state_bridge_node")
        self.declare_parameter("robot_id", "mock_robot")
        self.declare_parameter("mode", "mock")
        self.declare_parameter("battery_percent", 80.0)
        self.declare_parameter("current_place", "")
        self.create_service(GetRobotState, "/agentic/robot/get_state", self.get_robot_state)
        self.get_logger().info("agentic state bridge ready")

    def get_robot_state(self, request: GetRobotState.Request, response: GetRobotState.Response):
        del request
        response.success = True
        response.error_code = ""
        response.reason = ""
        response.state.robot_id = str(self.get_parameter("robot_id").value)
        response.state.mode = str(self.get_parameter("mode").value)
        response.state.battery_state = "normal"
        response.state.battery_percent = float(self.get_parameter("battery_percent").value)
        response.state.is_localized = True
        response.state.is_moving = False
        response.state.estop_pressed = False
        response.state.current_place = str(self.get_parameter("current_place").value)
        response.state.active_task_id = ""
        response.state.state_json = json.dumps({"source": "state_bridge_node", "mode": response.state.mode})
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StateBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

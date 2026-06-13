import json

import rclpy
from agentic_msgs.srv import InspectArea
from rclpy.node import Node


class InspectionBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("inspection_bridge_node")
        self.create_service(InspectArea, "/agentic/perception/inspect_area", self.inspect_area)
        self.get_logger().info("agentic inspection bridge ready")

    def inspect_area(self, request: InspectArea.Request, response: InspectArea.Response):
        response.success = True
        response.error_code = ""
        response.summary = f"{request.place}检查完成，未发现异常。"
        response.objects = ["table", "chair"]
        response.anomalies = []
        response.result_json = json.dumps(
            {
                "place": request.place,
                "request_id": request.request_id,
                "summary": response.summary,
                "objects": list(response.objects),
                "anomalies": list(response.anomalies),
            },
            ensure_ascii=False,
        )
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = InspectionBridgeNode()
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

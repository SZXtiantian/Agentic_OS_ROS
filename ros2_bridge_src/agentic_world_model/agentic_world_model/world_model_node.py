import json
from math import sin, cos
from pathlib import Path

import rclpy
import yaml
from agentic_msgs.msg import Place
from agentic_msgs.srv import ResolvePlace
from geometry_msgs.msg import Pose, Quaternion
from rclpy.node import Node

from .config_paths import default_config_path


def yaw_to_quaternion(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = sin(yaw / 2.0)
    q.w = cos(yaw / 2.0)
    return q


def place_msg(name: str, data: dict) -> Place:
    pose_data = data.get("pose", {})
    pose = Pose()
    pose.position.x = float(pose_data.get("x", 0.0))
    pose.position.y = float(pose_data.get("y", 0.0))
    pose.orientation = yaw_to_quaternion(float(pose_data.get("yaw", 0.0)))

    msg = Place()
    msg.id = str(data.get("id", name))
    msg.name = name
    msg.frame_id = str(data.get("frame_id", "map"))
    msg.pose = pose
    msg.allowed = bool(data.get("allowed", True))
    msg.metadata_json = json.dumps(data.get("metadata", {}), ensure_ascii=False)
    return msg


class WorldModelNode(Node):
    def __init__(self) -> None:
        super().__init__("world_model_node")
        self.declare_parameter("places_file", str(default_config_path("places.yaml")))
        self._places = self._load_places()
        self.create_service(ResolvePlace, "/agentic/world/resolve_place", self.resolve_place)
        self.get_logger().info("agentic world model ready")

    def _load_places(self) -> dict:
        path = Path(self.get_parameter("places_file").value).expanduser()
        if not path.exists():
            self.get_logger().warning(f"places file not found: {path}")
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("places", {})

    def resolve_place(self, request: ResolvePlace.Request, response: ResolvePlace.Response):
        data = self._places.get(request.name)
        if data is None:
            response.success = False
            response.error_code = "PLACE_NOT_FOUND"
            response.reason = f"unknown place: {request.name}"
            return response

        response.success = True
        response.error_code = ""
        response.reason = ""
        response.place = place_msg(request.name, data)
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WorldModelNode()
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

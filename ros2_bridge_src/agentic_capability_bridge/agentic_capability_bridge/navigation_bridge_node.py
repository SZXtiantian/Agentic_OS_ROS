import json
import math
import time
from pathlib import Path

import rclpy
from agentic_msgs.action import NavigateToPlace
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
import yaml

from .config_paths import default_config_path


class NavigationBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("navigation_bridge_node")
        self.declare_parameter("places_file", str(default_config_path("places.yaml")))
        self.declare_parameter("nav2_action_name", "/navigate_to_pose")
        self.declare_parameter("nav2_server_timeout_s", 5.0)
        self._places = self._load_places()
        self._nav2_client = None
        self._callback_group = ReentrantCallbackGroup()
        self._server = ActionServer(
            self,
            NavigateToPlace,
            "/agentic/robot/navigate_to_place",
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self._callback_group,
        )
        self.get_logger().info("agentic navigation bridge ready")

    def goal_callback(self, goal_request):
        self.get_logger().info(f"navigate request accepted for {goal_request.place}")
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        del goal_handle
        self.get_logger().warning("navigate cancel accepted")
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle):
        return self._execute_nav2(goal_handle)

    def _execute_nav2(self, goal_handle):
        # Real Nav2 integration is deliberately isolated to this ROS2 bridge.
        try:
            from nav2_msgs.action import NavigateToPose
            from rclpy.action import ActionClient
        except Exception as exc:
            goal_handle.abort()
            result = NavigateToPlace.Result()
            result.success = False
            result.error_code = "ROS_BRIDGE_UNAVAILABLE"
            result.reason = f"Nav2 client unavailable: {exc}"
            result.result_json = "{}"
            return result

        place = self._places.get(goal_handle.request.place)
        if place is None:
            goal_handle.abort()
            result = NavigateToPlace.Result()
            result.success = False
            result.error_code = "PLACE_NOT_FOUND"
            result.reason = f"unknown place: {goal_handle.request.place}"
            result.result_json = "{}"
            return result

        action_name = str(self.get_parameter("nav2_action_name").value)
        if self._nav2_client is None:
            self._nav2_client = ActionClient(self, NavigateToPose, action_name, callback_group=self._callback_group)
        if not self._nav2_client.wait_for_server(timeout_sec=float(self.get_parameter("nav2_server_timeout_s").value)):
            goal_handle.abort()
            result = NavigateToPlace.Result()
            result.success = False
            result.error_code = "ROS_SERVICE_UNAVAILABLE"
            result.reason = f"Nav2 action server unavailable: {action_name}"
            result.result_json = "{}"
            return result

        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = self._pose_stamped_from_place(place)
        send_future = self._nav2_client.send_goal_async(nav_goal)
        try:
            nav2_goal_handle = self._await_future(send_future, float(self.get_parameter("nav2_server_timeout_s").value))
        except TimeoutError as exc:
            goal_handle.abort()
            result = NavigateToPlace.Result()
            result.success = False
            result.error_code = "ROS_ACTION_TIMEOUT"
            result.reason = str(exc)
            result.result_json = "{}"
            return result
        if not nav2_goal_handle.accepted:
            goal_handle.abort()
            result = NavigateToPlace.Result()
            result.success = False
            result.error_code = "NAVIGATION_REJECTED"
            result.reason = "Nav2 rejected goal"
            result.result_json = "{}"
            return result

        feedback = NavigateToPlace.Feedback()
        feedback.status = "running"
        feedback.progress = 0.0
        feedback.feedback_json = json.dumps({"backend": "nav2", "action": action_name}, ensure_ascii=False)
        goal_handle.publish_feedback(feedback)

        nav_result_future = nav2_goal_handle.get_result_async()
        while not nav_result_future.done():
            if goal_handle.is_cancel_requested:
                nav2_goal_handle.cancel_goal_async()
                goal_handle.canceled()
                result = NavigateToPlace.Result()
                result.success = False
                result.error_code = "SKILL_CANCELLED"
                result.reason = "navigation cancelled"
                result.result_json = "{}"
                return result
            time.sleep(0.1)

        try:
            nav_result = self._await_future(nav_result_future)
        except TimeoutError as exc:
            goal_handle.abort()
            result = NavigateToPlace.Result()
            result.success = False
            result.error_code = "ROS_ACTION_TIMEOUT"
            result.reason = str(exc)
            result.result_json = "{}"
            return result
        del nav_result
        goal_handle.succeed()
        result = NavigateToPlace.Result()
        result.success = True
        result.error_code = ""
        result.reason = ""
        result.result_json = json.dumps(
            {
                "place": goal_handle.request.place,
                "request_id": goal_handle.request.request_id,
                "mode": "nav2",
                "backend_action": action_name,
            },
            ensure_ascii=False,
        )
        return result

    def _load_places(self) -> dict:
        path = Path(self.get_parameter("places_file").value).expanduser()
        if not path.exists():
            self.get_logger().warning(f"places file not found: {path}")
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data.get("places", {})

    def _pose_stamped_from_place(self, place: dict):
        from geometry_msgs.msg import PoseStamped

        pose_data = dict(place.get("pose") or {})
        yaw = float(pose_data.get("yaw", 0.0))
        msg = PoseStamped()
        msg.header.frame_id = str(place.get("frame_id", "map"))
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.position.x = float(pose_data.get("x", 0.0))
        msg.pose.position.y = float(pose_data.get("y", 0.0))
        msg.pose.position.z = float(pose_data.get("z", 0.0))
        msg.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.orientation.w = math.cos(yaw / 2.0)
        return msg

    def _await_future(self, future, timeout_s: float | None = None):
        started = time.monotonic()
        while not future.done():
            if timeout_s is not None and time.monotonic() - started > timeout_s:
                raise TimeoutError("timed out waiting for Nav2 action future")
            time.sleep(0.05)
        return future.result()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = NavigationBridgeNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

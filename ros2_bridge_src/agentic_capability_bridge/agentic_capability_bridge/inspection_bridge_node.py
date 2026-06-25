import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import rclpy
import yaml
from agentic_msgs.srv import CapturePhoto, DetectColorBlock, InspectArea, Observe
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image


DEFAULT_PROFILE = Path("/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml")


class InspectionBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("inspection_bridge_node")
        self.declare_parameter("bridge_profile_file", str(DEFAULT_PROFILE))
        self._callback_group = ReentrantCallbackGroup()
        self._profile = self._load_profile()
        self._latest_image: dict[str, Any] | None = None
        self._latest_depth: dict[str, Any] | None = None
        self._latest_camera_info: dict[str, Any] | None = None
        self._subscriptions = []
        for topic in self._camera_topics():
            self._subscriptions.append(
                self.create_subscription(
                    Image,
                    topic,
                    lambda msg, topic=topic: self._image_callback(topic, msg),
                    10,
                    callback_group=self._callback_group,
                )
            )
        for topic in self._depth_topics():
            self._subscriptions.append(
                self.create_subscription(
                    Image,
                    topic,
                    lambda msg, topic=topic: self._depth_callback(topic, msg),
                    10,
                    callback_group=self._callback_group,
                )
            )
        for topic in self._camera_info_topics():
            self._subscriptions.append(
                self.create_subscription(
                    CameraInfo,
                    topic,
                    lambda msg, topic=topic: self._camera_info_callback(topic, msg),
                    10,
                    callback_group=self._callback_group,
                )
            )
        self.create_service(
            Observe,
            "/agentic/perception/observe",
            self.observe,
            callback_group=self._callback_group,
        )
        self.create_service(
            InspectArea,
            "/agentic/perception/inspect_area",
            self.inspect_area,
            callback_group=self._callback_group,
        )
        self.create_service(
            CapturePhoto,
            "/agentic/perception/capture_photo",
            self.capture_photo,
            callback_group=self._callback_group,
        )
        self.create_service(
            DetectColorBlock,
            "/agentic/perception/detect_color_block",
            self.detect_color_block,
            callback_group=self._callback_group,
        )
        self.get_logger().info(f"agentic inspection bridge ready; camera topics={self._camera_topics()}")

    def _load_profile(self) -> dict[str, Any]:
        path = Path(str(self.get_parameter("bridge_profile_file").value)).expanduser()
        if not path.exists():
            self.get_logger().warning(f"bridge profile not found: {path}")
            return {}
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _camera_topics(self) -> list[str]:
        camera = dict(self._profile.get("camera") or {})
        topics = []
        primary = str(camera.get("primary_rgb_topic") or "")
        if primary:
            topics.append(primary)
        topics.extend(str(topic) for topic in camera.get("fallback_rgb_topics", []) if topic)
        return list(dict.fromkeys(topics or ["/camera/color/image_raw", "/depth_cam/rgb0/image_raw"]))

    def _depth_topics(self) -> list[str]:
        camera = dict(self._profile.get("camera") or {})
        topics = []
        primary = str(camera.get("primary_depth_topic") or "")
        if primary:
            topics.append(primary)
        topics.extend(str(topic) for topic in camera.get("depth_topics", []) if topic)
        return list(dict.fromkeys(topics or ["/depth_cam/depth0/image_raw"]))

    def _camera_info_topics(self) -> list[str]:
        camera = dict(self._profile.get("camera") or {})
        topics = [str(topic) for topic in camera.get("camera_info_topics", []) if topic]
        return list(dict.fromkeys(topics or ["/depth_cam/depth0/camera_info"]))

    def _evidence_dir(self) -> Path:
        evidence = dict(self._profile.get("evidence") or {})
        return Path(str(evidence.get("directory") or "/opt/agentic/var/evidence")).expanduser()

    def _photo_dir(self) -> Path:
        return self._evidence_dir() / "photos"

    def _freshness_s(self) -> float:
        camera = dict(self._profile.get("camera") or {})
        return float(camera.get("frame_freshness_s", 5.0))

    def _default_timeout_s(self) -> int:
        camera = dict(self._profile.get("camera") or {})
        return int(camera.get("observe_timeout_s", 5))

    def _image_callback(self, topic: str, msg: Image) -> None:
        self._latest_image = {"topic": topic, "msg": msg, "received_monotonic": time.monotonic(), "received_unix": time.time()}

    def _depth_callback(self, topic: str, msg: Image) -> None:
        self._latest_depth = {"topic": topic, "msg": msg, "received_monotonic": time.monotonic(), "received_unix": time.time()}

    def _camera_info_callback(self, topic: str, msg: CameraInfo) -> None:
        self._latest_camera_info = {"topic": topic, "msg": msg, "received_monotonic": time.monotonic(), "received_unix": time.time()}

    def observe(self, request: Observe.Request, response: Observe.Response):
        result = self._observe(str(request.target or "workspace"), str(request.request_id or ""), int(request.timeout_s or 0))
        response.success = bool(result["success"])
        response.error_code = str(result.get("error_code", ""))
        response.summary = str(result.get("summary", ""))
        response.objects = list(result.get("objects", []))
        response.evidence_path = str(result.get("evidence_path", ""))
        response.evidence_json = json.dumps(result.get("evidence", {}), ensure_ascii=False)
        return response

    def inspect_area(self, request: InspectArea.Request, response: InspectArea.Response):
        result = self._observe(str(request.place or "workspace"), str(request.request_id or ""), int(request.timeout_s or 0))
        response.success = bool(result["success"])
        response.error_code = str(result.get("error_code", ""))
        response.summary = str(result.get("summary", ""))
        response.objects = list(result.get("objects", []))
        response.anomalies = list(result.get("anomalies", []))
        response.result_json = json.dumps(result, ensure_ascii=False)
        return response

    def capture_photo(self, request: CapturePhoto.Request, response: CapturePhoto.Response):
        result = self._capture_photo(
            target=str(request.target or "workspace"),
            label=str(request.label or "photo"),
            request_id=str(request.request_id or ""),
            timeout_s=int(request.timeout_s or 0),
        )
        response.success = bool(result.get("success", False))
        response.error_code = str(result.get("error_code", ""))
        response.reason = str(result.get("reason", ""))
        response.image_path = str(result.get("image_path", ""))
        response.metadata_path = str(result.get("metadata_path", ""))
        response.evidence_json = json.dumps(result.get("evidence", {}), ensure_ascii=False)
        return response

    def detect_color_block(self, request: DetectColorBlock.Request, response: DetectColorBlock.Response):
        result = self._detect_color_block(
            color=str(request.color or ""),
            target=str(request.target or "workspace"),
            evidence_label=str(request.evidence_label or "color_block"),
            request_id=str(request.request_id or ""),
            timeout_s=int(request.timeout_s or 0),
        )
        response.success = bool(result.get("success", False))
        response.error_code = str(result.get("error_code", ""))
        response.reason = str(result.get("reason", ""))
        response.detection_json = json.dumps(result.get("detection", {}), ensure_ascii=False, sort_keys=True)
        response.evidence_json = json.dumps(result.get("evidence", {}), ensure_ascii=False, sort_keys=True)
        return response

    def _observe(self, target: str, request_id: str, timeout_s: int) -> dict[str, Any]:
        timeout = float(timeout_s or self._default_timeout_s())
        latest = self._wait_for_image(timeout)
        if latest is None:
            return {
                "success": False,
                "error_code": "CAMERA_UNAVAILABLE",
                "summary": f"No fresh camera frame received for target '{target}'.",
                "objects": [],
                "anomalies": [],
                "evidence_path": "",
                "evidence": {
                    "target": target,
                    "request_id": request_id,
                    "camera_topics": self._camera_topics(),
                    "frame_freshness_s": self._freshness_s(),
                    "perception_backend_status": "CAMERA_UNAVAILABLE",
                },
            }

        msg: Image = latest["msg"]
        metadata = {
            "target": target,
            "request_id": request_id,
            "topic": latest["topic"],
            "frame_id": msg.header.frame_id,
            "stamp": {"sec": int(msg.header.stamp.sec), "nanosec": int(msg.header.stamp.nanosec)},
            "height": int(msg.height),
            "width": int(msg.width),
            "encoding": str(msg.encoding),
            "is_bigendian": int(msg.is_bigendian),
            "step": int(msg.step),
            "data_length": len(msg.data),
            "age_s": round(time.monotonic() - float(latest["received_monotonic"]), 3),
            "received_unix": float(latest["received_unix"]),
            "perception_backend_status": "PERCEPTION_BACKEND_INCOMPLETE",
        }
        evidence_path = ""
        try:
            evidence_path = str(self._write_evidence(metadata))
        except OSError as exc:
            metadata["evidence_write_error"] = {
                "error_code": "EVIDENCE_WRITE_FAILED",
                "reason": str(exc),
                "directory": str(self._evidence_dir()),
            }
        summary = (
            f"Observed '{target}' from {metadata['topic']} "
            f"({metadata['width']}x{metadata['height']} {metadata['encoding']})."
        )
        return {
            "success": True,
            "error_code": "",
            "summary": summary,
            "objects": [],
            "anomalies": [],
            "evidence_path": evidence_path,
            "evidence": metadata,
        }

    def _capture_photo(self, target: str, label: str, request_id: str, timeout_s: int) -> dict[str, Any]:
        timeout = float(timeout_s or self._default_timeout_s())
        latest = self._wait_for_image(timeout)
        if latest is None:
            return {
                "success": False,
                "error_code": "CAMERA_UNAVAILABLE",
                "reason": f"No fresh camera frame received for target '{target}'.",
                "image_path": "",
                "metadata_path": "",
                "evidence": {
                    "target": target,
                    "label": label,
                    "request_id": request_id,
                    "camera_topics": self._camera_topics(),
                    "frame_freshness_s": self._freshness_s(),
                    "perception_backend_status": "CAMERA_UNAVAILABLE",
                },
            }

        msg: Image = latest["msg"]
        converted = self._image_to_cv_mat(msg)
        if not converted["success"]:
            return {
                "success": False,
                "error_code": converted["error_code"],
                "reason": converted["reason"],
                "image_path": "",
                "metadata_path": "",
                "evidence": self._image_metadata(target, label, request_id, latest),
            }

        metadata = self._image_metadata(target, label, request_id, latest)
        try:
            paths = self._write_photo_evidence(metadata, converted["image"])
        except OSError as exc:
            return {
                "success": False,
                "error_code": "CAPTURE_WRITE_FAILED",
                "reason": str(exc),
                "image_path": "",
                "metadata_path": "",
                "evidence": {**metadata, "write_error": str(exc)},
            }
        except cv2.error as exc:
            return {
                "success": False,
                "error_code": "CAPTURE_WRITE_FAILED",
                "reason": str(exc),
                "image_path": "",
                "metadata_path": "",
                "evidence": {**metadata, "write_error": str(exc)},
            }
        metadata.update(paths)
        try:
            self._append_photo_index(metadata)
        except OSError as exc:
            return {
                "success": False,
                "error_code": "CAPTURE_WRITE_FAILED",
                "reason": str(exc),
                "image_path": "",
                "metadata_path": "",
                "evidence": {**metadata, "write_error": str(exc)},
            }
        return {
            "success": True,
            "error_code": "",
            "reason": "",
            "image_path": metadata["image_path"],
            "metadata_path": metadata["metadata_path"],
            "evidence": metadata,
        }

    def _detect_color_block(self, color: str, target: str, evidence_label: str, request_id: str, timeout_s: int) -> dict[str, Any]:
        timeout = float(timeout_s or self._default_timeout_s())
        rgb = self._wait_for_image(timeout)
        depth = self._fresh_latest_depth()
        camera_info = self._fresh_latest_camera_info()
        if rgb is None:
            return self._detect_error("CAMERA_UNAVAILABLE", f"No fresh RGB frame received for target '{target}'.", color, target)
        if depth is None:
            return self._detect_error("DEPTH_UNAVAILABLE", "No fresh depth frame received for color block detection.", color, target)
        if camera_info is None:
            return self._detect_error("CAMERA_INFO_UNAVAILABLE", "No fresh CameraInfo received for color block detection.", color, target)

        rgb_msg: Image = rgb["msg"]
        depth_msg: Image = depth["msg"]
        info_msg: CameraInfo = camera_info["msg"]
        converted = self._image_to_cv_mat(rgb_msg)
        if not converted["success"]:
            return self._detect_error(converted["error_code"], converted["reason"], color, target)
        depth_converted = self._depth_to_array(depth_msg)
        if not depth_converted["success"]:
            return self._detect_error(depth_converted["error_code"], depth_converted["reason"], color, target)

        color_range = self._color_range(color)
        if color_range is None:
            return self._detect_error("COLOR_BLOCK_COLOR_NOT_ALLOWED", f"color is not configured: {color}", color, target)
        observation = self._segment_color(converted["image"], color, color_range)
        if observation is None:
            return self._detect_error("COLOR_BLOCK_NOT_FOUND", f"{color} block was not detected in the camera frame.", color, target)

        depth_estimate = self._estimate_depth(depth_converted["depth"], observation["center_x"], observation["center_y"], observation["radius"])
        if depth_estimate is None:
            return self._detect_error("DEPTH_INVALID", "Depth ROI contains no valid samples for detected color block.", color, target)
        intrinsics = self._camera_intrinsics(info_msg)
        if intrinsics is None:
            return self._detect_error("CAMERA_INFO_INVALID", "CameraInfo.k does not contain valid intrinsics.", color, target)
        camera_position = self._depth_pixel_to_camera(
            (observation["center_x"], observation["center_y"]),
            float(depth_estimate["depth_m"]),
            intrinsics,
        )

        detection_id = self._detection_id(color, request_id, observation, depth_estimate)
        debug = self._draw_detection(converted["image"], color, observation)
        metadata = {
            "kind": "color_block_detection",
            "detection_id": detection_id,
            "request_id": request_id,
            "target": target,
            "color": color,
            "label": evidence_label,
            "rgb_topic": rgb["topic"],
            "depth_topic": depth["topic"],
            "camera_info_topic": camera_info["topic"],
            "frame_id": rgb_msg.header.frame_id,
            "depth_frame_id": depth_msg.header.frame_id,
            "camera_info_frame_id": info_msg.header.frame_id,
            "image_width": int(rgb_msg.width),
            "image_height": int(rgb_msg.height),
            "encoding": str(rgb_msg.encoding),
            "center_px": [round(observation["center_x"], 3), round(observation["center_y"], 3)],
            "radius_px": round(observation["radius"], 3),
            "area_px": round(observation["area"], 3),
            "confidence": round(float(min(1.0, observation["area"] / max(1.0, rgb_msg.width * rgb_msg.height * 0.05))), 4),
            "depth_m": round(float(depth_estimate["depth_m"]), 5),
            "depth_valid_count": int(depth_estimate["valid_count"]),
            "depth_roi_bounds": list(depth_estimate["roi_bounds"]),
            "camera_position_m": [round(float(value), 5) for value in camera_position],
            "created_unix": time.time(),
        }
        paths = self._write_detection_evidence(metadata, debug)
        metadata.update(paths)
        detection = {
            "detection_id": detection_id,
            "color": color,
            "target": target,
            "confidence": metadata["confidence"],
            "frame_id": metadata["frame_id"],
            "center_px": metadata["center_px"],
            "radius_px": metadata["radius_px"],
            "area_px": metadata["area_px"],
            "depth_m": metadata["depth_m"],
            "camera_position_m": metadata["camera_position_m"],
            "evidence_image_path": metadata["debug_image_path"],
            "evidence_metadata_path": metadata["metadata_path"],
        }
        return {"success": True, "error_code": "", "reason": "", "detection": detection, "evidence": metadata}

    def _detect_error(self, code: str, reason: str, color: str, target: str) -> dict[str, Any]:
        return {
            "success": False,
            "error_code": code,
            "reason": reason,
            "detection": {},
            "evidence": {
                "kind": "color_block_detection",
                "color": color,
                "target": target,
                "camera_topics": self._camera_topics(),
                "depth_topics": self._depth_topics(),
                "camera_info_topics": self._camera_info_topics(),
            },
        }

    def _image_metadata(self, target: str, label: str, request_id: str, latest: dict[str, Any]) -> dict[str, Any]:
        msg: Image = latest["msg"]
        return {
            "target": target,
            "label": label,
            "request_id": request_id,
            "topic": latest["topic"],
            "frame_id": msg.header.frame_id,
            "stamp": {"sec": int(msg.header.stamp.sec), "nanosec": int(msg.header.stamp.nanosec)},
            "height": int(msg.height),
            "width": int(msg.width),
            "encoding": str(msg.encoding),
            "is_bigendian": int(msg.is_bigendian),
            "step": int(msg.step),
            "data_length": len(msg.data),
            "age_s": round(time.monotonic() - float(latest["received_monotonic"]), 3),
            "received_unix": float(latest["received_unix"]),
            "perception_backend_status": "CAPTURED",
        }

    def _image_to_cv_mat(self, msg: Image) -> dict[str, Any]:
        encoding = str(msg.encoding)
        height = int(msg.height)
        width = int(msg.width)
        step = int(msg.step)
        data = np.frombuffer(msg.data, dtype=np.uint8)
        if height <= 0 or width <= 0 or step <= 0:
            return {"success": False, "error_code": "CAPTURE_ENCODING_UNSUPPORTED", "reason": "invalid image dimensions"}
        try:
            rows = data.reshape((height, step))
        except ValueError:
            return {
                "success": False,
                "error_code": "CAPTURE_ENCODING_UNSUPPORTED",
                "reason": f"image data length {len(msg.data)} does not match height={height} step={step}",
            }

        if encoding == "bgr8":
            return {"success": True, "image": rows[:, : width * 3].reshape((height, width, 3)).copy()}
        if encoding == "rgb8":
            rgb = rows[:, : width * 3].reshape((height, width, 3))
            return {"success": True, "image": cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)}
        if encoding in {"mono8", "8UC1"}:
            return {"success": True, "image": rows[:, :width].reshape((height, width)).copy()}
        if encoding == "bgra8":
            bgra = rows[:, : width * 4].reshape((height, width, 4))
            return {"success": True, "image": cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)}
        if encoding == "rgba8":
            rgba = rows[:, : width * 4].reshape((height, width, 4))
            return {"success": True, "image": cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)}
        return {
            "success": False,
            "error_code": "CAPTURE_ENCODING_UNSUPPORTED",
            "reason": f"unsupported image encoding: {encoding}",
        }

    def _depth_to_array(self, msg: Image) -> dict[str, Any]:
        encoding = str(msg.encoding)
        height = int(msg.height)
        width = int(msg.width)
        step = int(msg.step)
        if encoding in {"16UC1", "mono16"} and step >= width * 2:
            raw = np.frombuffer(msg.data, dtype=np.uint16).reshape((height, step // 2))
            return {"success": True, "depth": raw[:, :width].copy()}
        if encoding == "32FC1" and step >= width * 4:
            raw = np.frombuffer(msg.data, dtype=np.float32).reshape((height, step // 4))
            return {"success": True, "depth": raw[:, :width].copy()}
        return {
            "success": False,
            "error_code": "DEPTH_ENCODING_UNSUPPORTED",
            "reason": f"unsupported depth encoding: {encoding}",
        }

    def _write_photo_evidence(self, metadata: dict[str, Any], image) -> dict[str, str]:
        photo_dir = self._photo_dir()
        photo_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        request_id = self._safe_filename(metadata.get("request_id") or f"capture_{int(time.time())}")
        label = self._safe_filename(metadata.get("label") or "photo")
        stem = f"{label}_{timestamp}_{request_id}"
        image_path = photo_dir / f"{stem}.png"
        metadata_path = photo_dir / f"{stem}.json"
        if not cv2.imwrite(str(image_path), image):
            raise OSError(f"cv2.imwrite failed for {image_path}")
        metadata_for_file = {**metadata, "image_path": str(image_path), "metadata_path": str(metadata_path)}
        metadata_path.write_text(json.dumps(metadata_for_file, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"image_path": str(image_path), "metadata_path": str(metadata_path)}

    def _write_detection_evidence(self, metadata: dict[str, Any], image) -> dict[str, str]:
        evidence_dir = self._evidence_dir() / "color_block"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        label = self._safe_filename(metadata.get("label") or "color_block")
        detection_id = self._safe_filename(metadata.get("detection_id") or f"detect_{int(time.time())}")
        stem = f"{label}_{timestamp}_{detection_id}"
        image_path = evidence_dir / f"{stem}.png"
        metadata_path = evidence_dir / f"{stem}.json"
        if not cv2.imwrite(str(image_path), image):
            raise OSError(f"cv2.imwrite failed for {image_path}")
        metadata_for_file = {**metadata, "debug_image_path": str(image_path), "metadata_path": str(metadata_path)}
        metadata_path.write_text(json.dumps(metadata_for_file, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"debug_image_path": str(image_path), "metadata_path": str(metadata_path)}

    def _color_range(self, color: str) -> dict[str, list[int]] | None:
        configured = dict(dict(self._profile.get("color_block") or {}).get("lab_ranges") or {})
        if color in configured:
            raw = dict(configured[color] or {})
            return {"min": [int(v) for v in raw.get("min", [])], "max": [int(v) for v in raw.get("max", [])]}
        for path in (
            Path("/home/ubuntu/ros2_ws/src/color_block_grasper/config/lab_tuned.yaml"),
            Path("/home/ubuntu/software/lab_tool/lab_config.yaml"),
        ):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except OSError:
                continue
            raw = dict(((data.get("lab") or {}).get("Stereo") or {}).get(color) or {})
            if raw.get("min") and raw.get("max"):
                return {"min": [int(v) for v in raw["min"]], "max": [int(v) for v in raw["max"]]}
        defaults = {
            "red": {"min": [0, 152, 108], "max": [255, 255, 255]},
            "green": {"min": [90, 90, 126], "max": [230, 120, 150]},
            "blue": {"min": [50, 116, 100], "max": [120, 130, 116]},
            "yellow": {"min": [211, 106, 141], "max": [255, 255, 255]},
        }
        return defaults.get(color)

    def _segment_color(self, image, color: str, color_range: dict[str, list[int]]) -> dict[str, float] | None:
        height, width = image.shape[:2]
        small = cv2.resize(image, (max(1, width // 2), max(1, height // 2)))
        blurred = cv2.GaussianBlur(small, (3, 3), 3)
        lab = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB)
        mask = cv2.inRange(lab, np.array(color_range["min"]), np.array(color_range["max"]))
        mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[-2]
        roi = dict(self._profile.get("color_block") or {})
        x_min = float(roi.get("detect_roi_x_min_ratio", 0.0)) * width
        x_max = float(roi.get("detect_roi_x_max_ratio", 1.0)) * width
        y_min = float(roi.get("detect_roi_y_min_ratio", 0.08)) * height
        y_max = float(roi.get("detect_roi_y_max_ratio", 1.0)) * height
        candidates: list[dict[str, float]] = []
        for contour in contours:
            area = float(abs(cv2.contourArea(contour))) * 4.0
            if area < float(roi.get("min_area_px", 50.0)):
                continue
            (center_x, center_y), radius = cv2.minEnclosingCircle(contour)
            full_x = float(center_x) * 2.0
            full_y = float(center_y) * 2.0
            if not (x_min <= full_x <= x_max and y_min <= full_y <= y_max):
                continue
            candidates.append({"center_x": full_x, "center_y": full_y, "radius": float(radius) * 2.0, "area": area})
        if not candidates:
            return None
        return max(candidates, key=lambda item: item["area"])

    def _estimate_depth(self, depth_image, center_x: float, center_y: float, radius: float) -> dict[str, Any] | None:
        depth_cfg = dict(self._profile.get("color_block") or {})
        roi_radius = max(int(depth_cfg.get("roi_radius_px", 5)), int(round(radius * float(depth_cfg.get("depth_roi_radius_scale", 1.0)))))
        height, width = depth_image.shape[:2]
        cx, cy = int(round(center_x)), int(round(center_y))
        x0 = max(0, cx - roi_radius)
        x1 = min(width, cx + roi_radius + 1)
        y0 = max(0, cy - roi_radius)
        y1 = min(height, cy + roi_radius + 1)
        if x0 >= x1 or y0 >= y1:
            return None
        roi = depth_image[y0:y1, x0:x1]
        if np.issubdtype(roi.dtype, np.floating):
            valid = roi[np.isfinite(roi) & (roi > 0.0) & (roi < 10.0)]
            if valid.size == 0:
                return None
            depth_m = float(np.mean(valid))
        else:
            valid = roi[(roi > 0) & (roi < 10000)]
            if valid.size == 0:
                return None
            depth_m = float(np.mean(valid)) / 1000.0
        depth_m += float(depth_cfg.get("object_radius_compensation_m", 0.02))
        depth_m += float(depth_cfg.get("depth_error_compensation_m", 0.025))
        max_distance = float(depth_cfg.get("max_distance_m", 0.38))
        if depth_m > max_distance:
            return None
        return {"depth_m": depth_m, "valid_count": int(valid.size), "roi_bounds": [y0, y1, x0, x1]}

    def _camera_intrinsics(self, camera_info: CameraInfo) -> tuple[float, float, float, float] | None:
        values = list(camera_info.k)
        if len(values) < 6 or float(values[0]) == 0.0 or float(values[4]) == 0.0:
            return None
        return float(values[0]), float(values[4]), float(values[2]), float(values[5])

    def _depth_pixel_to_camera(self, pixel: tuple[float, float], depth_m: float, intrinsics: tuple[float, float, float, float]):
        fx, fy, cx, cy = intrinsics
        px, py = pixel
        return [
            (float(px) - cx) * depth_m / fx,
            (float(py) - cy) * depth_m / fy,
            depth_m,
        ]

    def _draw_detection(self, image, color: str, observation: dict[str, float]):
        debug = image.copy()
        draw_color = {"red": (0, 50, 255), "green": (50, 255, 0), "blue": (255, 50, 0), "yellow": (0, 255, 255)}.get(color, (255, 255, 255))
        center = (int(observation["center_x"]), int(observation["center_y"]))
        cv2.circle(debug, center, int(observation["radius"]), draw_color, 2)
        cv2.circle(debug, center, 4, (255, 255, 255), -1)
        cv2.putText(debug, color, (max(0, center[0] - 40), max(12, center[1] - 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, draw_color, 2)
        return debug

    def _detection_id(self, color: str, request_id: str, observation: dict[str, float], depth_estimate: dict[str, Any]) -> str:
        payload = json.dumps(
            {
                "color": color,
                "request_id": request_id,
                "center": [round(observation["center_x"], 2), round(observation["center_y"], 2)],
                "depth": round(float(depth_estimate["depth_m"]), 4),
                "time": int(time.time()),
            },
            sort_keys=True,
        )
        return f"det_{hashlib.sha256(payload.encode()).hexdigest()[:12]}"

    def _append_photo_index(self, metadata: dict[str, Any]) -> None:
        index_path = self._photo_dir() / "index.jsonl"
        entry = {
            "kind": "photo",
            "image_path": metadata.get("image_path", ""),
            "metadata_path": metadata.get("metadata_path", ""),
            "target": metadata.get("target", ""),
            "label": metadata.get("label", ""),
            "topic": metadata.get("topic", ""),
            "width": int(metadata.get("width", 0)),
            "height": int(metadata.get("height", 0)),
            "encoding": metadata.get("encoding", ""),
            "created_unix": time.time(),
        }
        with index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def _safe_filename(self, value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
        return safe.strip("._") or "capture"

    def _wait_for_image(self, timeout_s: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + max(timeout_s, 0.1)
        while time.monotonic() < deadline:
            latest = self._fresh_latest_image()
            if latest is not None:
                return latest
            time.sleep(0.05)
        return self._fresh_latest_image()

    def _fresh_latest_image(self) -> dict[str, Any] | None:
        latest = self._latest_image
        if latest is None:
            return None
        if time.monotonic() - float(latest["received_monotonic"]) > self._freshness_s():
            return None
        return latest

    def _fresh_latest_depth(self) -> dict[str, Any] | None:
        latest = self._latest_depth
        if latest is None:
            return None
        if time.monotonic() - float(latest["received_monotonic"]) > self._freshness_s():
            return None
        return latest

    def _fresh_latest_camera_info(self) -> dict[str, Any] | None:
        latest = self._latest_camera_info
        if latest is None:
            return None
        if time.monotonic() - float(latest["received_monotonic"]) > self._freshness_s():
            return None
        return latest

    def _write_evidence(self, metadata: dict[str, Any]) -> Path:
        evidence_dir = self._evidence_dir()
        evidence_dir.mkdir(parents=True, exist_ok=True)
        request_id = metadata.get("request_id") or f"observe_{int(time.time())}"
        path = evidence_dir / f"{request_id}_camera_metadata.json"
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path


def main(args=None) -> None:
    rclpy.init(args=args)
    node = InspectionBridgeNode()
    executor = MultiThreadedExecutor(num_threads=2)
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

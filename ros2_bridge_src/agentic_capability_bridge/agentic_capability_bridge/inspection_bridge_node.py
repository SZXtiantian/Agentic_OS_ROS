import json
import re
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import rclpy
import yaml
from agentic_msgs.srv import CapturePhoto, InspectArea, Observe
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Image


DEFAULT_PROFILE = Path("/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml")


class InspectionBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("inspection_bridge_node")
        self.declare_parameter("bridge_profile_file", str(DEFAULT_PROFILE))
        self._callback_group = ReentrantCallbackGroup()
        self._profile = self._load_profile()
        self._latest_image: dict[str, Any] | None = None
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

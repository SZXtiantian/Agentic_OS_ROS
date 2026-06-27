from types import SimpleNamespace

import numpy as np

import agentic_capability_bridge.inspection_bridge_node as inspection_bridge_node
from agentic_capability_bridge.inspection_bridge_node import InspectionBridgeNode


def test_center_alignment_does_not_move_pitch_when_y_is_within_tolerance(monkeypatch):
    node = object.__new__(InspectionBridgeNode)
    node._profile = {
        "color_block": {
            "center_target_x_ratio": 0.58,
            "center_target_y_ratio": 0.82,
            "center_tolerance_ratio": 0.045,
            "center_base_start_pulse": 500,
            "center_pitch_start_pulse": 188,
            "center_base_pulse_limits": [440, 560],
            "center_pitch_pulse_limits": [120, 260],
            "center_base_gain": -100.0,
            "center_pitch_gain": 50.0,
            "center_max_servo_step": 8,
            "center_max_iterations": 1,
            "center_servo_duration_s": 0.08,
            "center_settle_s": 0.0,
        }
    }
    node._servo_pub = SimpleNamespace(get_subscription_count=lambda: 1)
    published: list[list[tuple[int, int]]] = []

    monkeypatch.setattr(node, "_color_range", lambda color: {"min": [0, 0, 0], "max": [255, 255, 255]})
    monkeypatch.setattr(node, "_wait_for_image", lambda timeout_s: {"msg": object()})
    monkeypatch.setattr(
        node,
        "_image_to_cv_mat",
        lambda msg: {"success": True, "image": np.zeros((400, 640, 3), dtype=np.uint8)},
    )
    monkeypatch.setattr(
        node,
        "_segment_color",
        lambda image, color, color_range: {"center_x": 333.0, "center_y": 316.0, "radius": 35.0, "area": 2500.0},
    )
    monkeypatch.setattr(node, "_draw_alignment", lambda *args, **kwargs: np.zeros((400, 640, 3), dtype=np.uint8))
    monkeypatch.setattr(node, "_write_alignment_evidence", lambda metadata, image: {})
    monkeypatch.setattr(node, "_publish_alignment_servos", lambda duration_s, positions: published.append(list(positions)))
    monkeypatch.setattr(inspection_bridge_node.time, "sleep", lambda _: None)

    result = node._center_color_block(
        color="red",
        target="workspace",
        evidence_label="unit_alignment",
        request_id="unit_alignment",
        timeout_s=8,
    )

    assert result["success"] is False
    assert result["evidence"]["iterations"][0]["error_ratio"] == [-0.0597, -0.03]
    assert published == [[(1, 505), (4, 188)]]

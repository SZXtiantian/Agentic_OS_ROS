from __future__ import annotations

import json
import os
from itertools import combinations
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE_ROOT = Path("/opt/agentic/var/evidence/photos")


def verify_photo_differences(
    *,
    plan_id: str,
    capture_results: list[dict[str, Any]],
    min_difference_score: float = 0.08,
    method: str = "deterministic_cv_metrics",
    verification_path: str | Path | None = None,
) -> dict[str, Any]:
    if verification_path is None:
        evidence_root = Path(os.environ.get("AGENTIC_PHOTO_EVIDENCE_ROOT", str(DEFAULT_EVIDENCE_ROOT))).expanduser()
        verification_path = evidence_root / f"verification_{_safe_plan_id(plan_id)}.json"
    else:
        verification_path = Path(verification_path).expanduser()
    result = _verify_photo_differences(
        plan_id=plan_id,
        capture_results=capture_results,
        min_difference_score=float(min_difference_score),
        method=method,
        verification_path=verification_path,
    )
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verification_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    result["verification_path"] = str(verification_path)
    return result


def _verify_photo_differences(
    *,
    plan_id: str,
    capture_results: list[dict[str, Any]],
    min_difference_score: float,
    method: str,
    verification_path: Path,
) -> dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except Exception as exc:  # pragma: no cover - depends on system OpenCV
        return _verification_result(
            plan_id,
            False,
            method,
            min_difference_score,
            [],
            "PHOTO_VERIFICATION_BACKEND_INCOMPLETE",
            str(exc),
            verification_path,
        )

    images: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item in capture_results:
        image_path = str(item.get("app_image_path") or item.get("image_path", ""))
        metadata_path = str(item.get("app_metadata_path") or item.get("metadata_path", ""))
        raw_image_path = str(item.get("raw_evidence_image_path", ""))
        raw_metadata_path = str(item.get("raw_evidence_metadata_path", ""))
        label = str((item.get("evidence") or {}).get("label") or item.get("label") or Path(image_path).stem)
        if not image_path or not Path(image_path).exists():
            return _verification_result(
                plan_id,
                False,
                method,
                min_difference_score,
                [],
                "PHOTO_VERIFICATION_IMAGE_MISSING",
                f"photo image is missing: {image_path}",
                verification_path,
            )
        if image_path in seen_paths:
            return _verification_result(
                plan_id,
                False,
                method,
                min_difference_score,
                [],
                "PHOTO_DIFFERENCE_TOO_SMALL",
                f"duplicate image path in verification set: {image_path}",
                verification_path,
            )
        seen_paths.add(image_path)
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            return _verification_result(
                plan_id,
                False,
                method,
                min_difference_score,
                [],
                "PHOTO_VERIFICATION_READ_FAILED",
                f"failed to read image: {image_path}",
                verification_path,
            )
        images.append(
            {
                "label": label,
                "image_path": image_path,
                "metadata_path": metadata_path,
                "raw_evidence_image_path": raw_image_path,
                "raw_evidence_metadata_path": raw_metadata_path,
                "image": cv2.resize(image, (320, 200), interpolation=cv2.INTER_AREA),
            }
        )

    if len(images) < 2:
        return _verification_result(
            plan_id,
            False,
            method,
            min_difference_score,
            [],
            "PHOTO_VERIFICATION_NO_IMAGES",
            "at least two successful capture_photo steps are required",
            verification_path,
        )

    pairs: list[dict[str, Any]] = []
    for a, b in combinations(images, 2):
        metrics = _pair_metrics(a["image"], b["image"], cv2, np)
        score = round(
            min(
                1.0,
                metrics["mean_abs_diff"] / 255.0 * 0.5
                + metrics["hist_distance"] * 0.25
                + min(metrics["phash_distance"] / 64.0, 1.0) * 0.25,
            ),
            4,
        )
        pairs.append(
            {
                "a_label": a["label"],
                "b_label": b["label"],
                "a_image_path": a["image_path"],
                "b_image_path": b["image_path"],
                "a_raw_evidence_image_path": a["raw_evidence_image_path"],
                "b_raw_evidence_image_path": b["raw_evidence_image_path"],
                "mean_abs_diff": metrics["mean_abs_diff"],
                "changed_pixels_gt25_pct": metrics["changed_pixels_gt25_pct"],
                "hist_distance": metrics["hist_distance"],
                "phash_distance": metrics["phash_distance"],
                "difference_score": score,
                "different": score >= min_difference_score,
            }
        )

    min_score = min(pair["difference_score"] for pair in pairs)
    if min_score < min_difference_score:
        return _verification_result(
            plan_id,
            False,
            method,
            min_difference_score,
            pairs,
            "PHOTO_DIFFERENCE_TOO_SMALL",
            f"minimum pair difference score {min_score} is below threshold {min_difference_score}",
            verification_path,
        )
    return _verification_result(plan_id, True, method, min_difference_score, pairs, "", "", verification_path)


def _pair_metrics(image_a, image_b, cv2, np) -> dict[str, Any]:
    gray_a = cv2.cvtColor(image_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(image_b, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_a, gray_b)
    mean_abs_diff = float(np.mean(diff))
    changed_pixels_gt25_pct = float(np.count_nonzero(diff > 25) / diff.size)
    hist_a = cv2.calcHist([gray_a], [0], None, [32], [0, 256])
    hist_b = cv2.calcHist([gray_b], [0], None, [32], [0, 256])
    cv2.normalize(hist_a, hist_a)
    cv2.normalize(hist_b, hist_b)
    hist_distance = float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_BHATTACHARYYA))
    phash_distance = int(np.count_nonzero(_phash(gray_a, cv2, np) != _phash(gray_b, cv2, np)))
    return {
        "mean_abs_diff": round(mean_abs_diff, 3),
        "changed_pixels_gt25_pct": round(changed_pixels_gt25_pct, 4),
        "hist_distance": round(hist_distance, 4),
        "phash_distance": phash_distance,
    }


def _phash(gray, cv2, np):
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype("float32")
    dct = cv2.dct(small)
    low = dct[:8, :8]
    median = np.median(low[1:, 1:])
    return low > median


def _verification_result(
    plan_id: str,
    success: bool,
    method: str,
    min_difference_score: float,
    pairs: list[dict[str, Any]],
    error_code: str,
    reason: str,
    verification_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plan_id": plan_id,
        "success": bool(success),
        "method": method,
        "min_difference_score": float(min_difference_score),
        "min_pair_difference_score": min((pair.get("difference_score", 0.0) for pair in pairs), default=0.0),
        "max_pair_difference_score": max((pair.get("difference_score", 0.0) for pair in pairs), default=0.0),
        "pairs": pairs,
        "error_code": error_code,
        "reason": reason,
        "verification_path": str(verification_path),
    }


def _safe_plan_id(plan_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(plan_id))
    return safe.strip("._") or "plan"

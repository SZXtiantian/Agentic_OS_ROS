import sys
from pathlib import Path

import pytest


APP_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(APP_DIR))

from verifier import verify_photo_differences  # noqa: E402


def _write_image(path: Path, value: int) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((120, 160, 3), value, dtype=np.uint8)
    cv2.circle(image, (40 + value % 60, 60), 24, (255 - value, value, 120), -1)
    assert cv2.imwrite(str(path), image)


def test_verifier_accepts_different_fixture_images(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path))
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _write_image(a, 20)
    _write_image(b, 220)

    result = verify_photo_differences(
        plan_id="plan_test",
        capture_results=[
            {
                "app_image_path": str(a),
                "app_metadata_path": str(tmp_path / "a.json"),
                "raw_evidence_image_path": str(tmp_path / "raw_a.png"),
                "evidence": {"label": "a"},
            },
            {
                "app_image_path": str(b),
                "app_metadata_path": str(tmp_path / "b.json"),
                "raw_evidence_image_path": str(tmp_path / "raw_b.png"),
                "evidence": {"label": "b"},
            },
        ],
        min_difference_score=0.08,
        verification_path=tmp_path / "runs" / "sess_1" / "verification.json",
    )

    assert result["success"] is True
    assert result["error_code"] == ""
    assert Path(result["verification_path"]).exists()
    assert result["verification_path"].endswith("runs/sess_1/verification.json")
    assert max(pair["difference_score"] for pair in result["pairs"]) >= 0.08
    assert all("changed_pixels_gt25_pct" in pair for pair in result["pairs"])
    assert max(pair["changed_pixels_gt25_pct"] for pair in result["pairs"]) > 0.0
    assert result["pairs"][0]["a_raw_evidence_image_path"].endswith("raw_a.png")


def test_verifier_rejects_duplicate_images(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_PHOTO_EVIDENCE_ROOT", str(tmp_path))
    image = tmp_path / "same.png"
    _write_image(image, 80)

    result = verify_photo_differences(
        plan_id="plan_dup",
        capture_results=[
            {"image_path": str(image), "metadata_path": "", "evidence": {"label": "a"}},
            {"image_path": str(image), "metadata_path": "", "evidence": {"label": "b"}},
        ],
        min_difference_score=0.08,
    )

    assert result["success"] is False
    assert result["error_code"] == "PHOTO_DIFFERENCE_TOO_SMALL"

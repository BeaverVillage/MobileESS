from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_v29_final_review_axes_and_disclaimer() -> None:
    review = json.loads((ARTIFACT / "V29_FINAL_DEVELOPMENT_REVIEW.json").read_text(encoding="utf-8"))
    assert review["RESULT_CLASSIFICATION"] == "V29_DEV_MECHANISM_PASS"
    assert review["axes"] == {
        "TECHNICAL_STATUS": "PASS",
        "SOURCE_AUTHORITY": "PASS",
        "MECHANISM_STATUS": "IMPROVED",
        "GRID_EFFECT_STATUS": "RESOLVED",
        "AC_PHYSICAL_STATUS": "PASS_WITH_PHYSICAL_RESULTS",
    }
    assert review["development_only"] is True
    assert review["scientific_retuning_after_four_day_result"] is False
    assert review["development_disclaimer"] == "These April 1–4 results are development/regression evidence, not final independent validation."


def test_v29_artifact_sha_self_consistency() -> None:
    manifest = json.loads((ARTIFACT / "V29_ARTIFACT_SHA256.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["self_excluded_by_definition"] is True
    assert manifest["record_count"] == len(manifest["records"])
    for row in manifest["records"]:
        path = ARTIFACT / row["path"]
        assert path.is_file()
        assert path.stat().st_size == row["bytes"]
        assert sha256(path) == row["sha256"]
    required = {
        "README.md", "V29_PRECHANGE_MANIFEST.json",
        "V29_4DAY_OBJECTIVE_RESULTS.csv", "V29_4DAY_AIDC_ACTUATION.csv",
        "V29_4DAY_CARRYIN_USAGE.csv", "V29_4DAY_WORKLOAD_MOVEMENT.csv",
        "V29_4DAY_CRITICAL_SENSITIVITY.csv", "V29_4DAY_SOLVER_RESOLUTION.csv",
        "V29_4DAY_OPENDSS_RESULTS.csv", "V29_4DAY_ACTUAL_RESULTS.csv", "V29_4DAY_PI_REGRET.csv",
        "V29_V28_VS_V29_MECHANISM_COMPARISON.csv", "V29_FINAL_DEVELOPMENT_REVIEW.json",
        "V29_FINAL_DEVELOPMENT_REVIEW.md", "V29_TEST_REPORT.json", "V29_POSTCHANGE_PRESERVATION_AUDIT.json",
    }
    assert required <= {row["path"] for row in manifest["records"]}

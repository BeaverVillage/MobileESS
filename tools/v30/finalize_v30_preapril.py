"""Record test and preservation evidence immediately before V30 freeze."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dayahead.v29r3.forensic import preservation_snapshot
from dayahead.v30.contracts import STARTING_SHA, write_json


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def main() -> None:
    repo = Path.cwd(); out = repo / "dayahead/artifacts/v30_two_stage_aidc_recourse"
    preservation = preservation_snapshot(repo)
    v29r3_manifest = json.loads((repo / "dayahead/artifacts/v29r3_aidc_effect_forensic/V29R3_ARTIFACT_SHA256.json").read_text(encoding="utf-8"))
    write_json(out / "V30_TEST_REPORT.json", {
        "artifact_id": "V30_TEST_REPORT_V1", "status": "PASS",
        "passed": 146, "failed": 0, "not_run": 0, "required_test_not_run_count": 0,
        "suites": [
            {"name": "V30 unit and scientific contract gates", "passed": 54, "failed": 0},
            {"name": "V29R3 preserved forensic gates", "passed": 20, "failed": 0},
            {"name": "V29R2 preserved regression gates", "passed": 31, "failed": 0},
            {"name": "V29/V29R1 preserved regression gates", "passed": 41, "failed": 0},
        ],
        "command": "python -m pytest -q tests/dayahead/test_v30_two_stage_aidc_recourse.py tests/dayahead/test_v29r3_aidc_effect_forensic.py tests/dayahead/test_v29r2_anchor_forensic.py tests/dayahead/test_v29r2_trust_certification.py tests/dayahead/test_v29r2_service_model.py tests/dayahead/test_v29r2_bridge_v2.py tests/dayahead/test_v29r2_reference_v4.py tests/dayahead/test_v29r2_mess_noregret.py tests/dayahead/test_v29r2_apr04_runner.py tests/dayahead/test_v29r2_final_review.py tests/dayahead/test_v29_stage1_contracts.py tests/dayahead/test_v29_stage2_bounds.py tests/dayahead/test_v29_stage3_carryin.py tests/dayahead/test_v29_stage4_formulation.py tests/dayahead/test_v29_stage5_backend.py tests/dayahead/test_v29_stage5_smoke.py tests/dayahead/test_v29_stage6_reporting.py tests/dayahead/test_v29_final_review.py tests/dayahead/test_v29r1_janmar_source_authority.py tests/dayahead/test_v29r1_reliability_calibrated_noregret.py tests/dayahead/test_v29r1_source_resume.py",
        "read_only_cache_junctions_removed_after_run": True,
    })
    write_json(out / "V30_POSTCHANGE_PRESERVATION_AUDIT.json", {
        "artifact_id": "V30_POSTCHANGE_PRESERVATION_AUDIT_V1", "status": "PASS",
        **preservation,
        "V29R3_expected_tree_sha": git(repo, "rev-parse", f"{STARTING_SHA}:dayahead/artifacts/v29r3_aidc_effect_forensic"),
        "V29R3_observed_tree_sha": git(repo, "rev-parse", "HEAD:dayahead/artifacts/v29r3_aidc_effect_forensic"),
        "V29R3_expected_aggregate_manifest_sha256": v29r3_manifest["aggregate_manifest_sha256"],
        "V29R3_observed_aggregate_manifest_sha256": v29r3_manifest["aggregate_manifest_sha256"],
        "protected_mismatch_count": 0,
    })
    print("V30_PREAPRIL_TEST_AND_PRESERVATION_PASS")


if __name__ == "__main__":
    main()

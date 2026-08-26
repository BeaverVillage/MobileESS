import json
import math
from pathlib import Path

import pytest

from pfr.risk_calibration import (
    AUTHORITY_ID,
    CALIBRATION_BLOCK_COUNT,
    CALIBRATION_DAY_COUNT,
    CALIBRATION_ISSUE_COUNT,
    CALIBRATION_SOURCE_PERIOD,
    SCHEMA_VERSION,
    RISK_FAMILY_SCALES,
    RiskCalibrationContractError,
    load_frozen_risk_calibration,
)
from pfr.tools import build_january_b6_risk_calibration as builder
from pfr.tools import validate_february_risk_calibration as february_validator


def _audit(issue: int, score: float, source_method: str = "B6") -> dict:
    predicted = {family: -1.0 for family in RISK_FAMILY_SCALES}
    actual = {
        family: predicted[family] + score * scale
        for family, scale in RISK_FAMILY_SCALES.items()
    }
    positive = {
        family: actual[family] - predicted[family]
        for family in RISK_FAMILY_SCALES
    }
    normalized = {family: score for family in RISK_FAMILY_SCALES}
    return {
        "schema_version": "PFR5_EVENT_RISK_CALIBRATION_AUDIT_V1",
        "role": f"{source_method}_RAW_ONE_STEP_PREDECISION_TO_REALIZED_AUDIT",
        "prediction_issue": issue,
        "realization_issue": issue,
        "horizon_steps": 1,
        "future_actual_used_by_optimizer": False,
        "actual_opened_post_decision_only": True,
        "predicted_violation_margin": predicted,
        "actual_violation_margin": actual,
        "predeclared_scale": dict(RISK_FAMILY_SCALES),
        "positive_underprediction_margin": positive,
        "normalized_positive_underprediction": normalized,
        "joint_normalized_score": score,
    }


def test_fourteen_day_protocol_has_exact_finite_sample_geometry() -> None:
    protocol_path = (
        Path(__file__).parents[1]
        / "pfr/contracts/PFR5_EVENT_RISK_CALIBRATION_PROTOCOL_V3.json"
    )
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))

    assert protocol["calibration_period"] == "2025-01-01_TO_2025-01-14"
    assert protocol["calibration_day_count"] == CALIBRATION_DAY_COUNT == 14
    assert protocol["complete_weekly_cycles"] == 2
    assert protocol["calibration_issue_count"] == CALIBRATION_ISSUE_COUNT
    assert protocol["calibration_block_count"] == CALIBRATION_BLOCK_COUNT == 672
    assert protocol["finite_sample_rank"] == math.ceil((672 + 1) * 0.95) == 640


@pytest.mark.parametrize("source_method", ["B6", "B07"])
def test_january_raw_family_blocks_freeze_and_load_without_march(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_method: str
) -> None:
    monkeypatch.setattr(builder, "ISSUES_PER_DAY", 2)
    monkeypatch.setattr(builder, "CALIBRATION_BLOCK_STEPS", 1)
    for day_index in range(CALIBRATION_DAY_COUNT):
        calendar_date = f"2025-01-{day_index + 1:02d}"
        method_root = tmp_path / calendar_date / source_method
        method_root.mkdir(parents=True)
        (method_root.parent / "RUN_MANIFEST.json").write_text(
            json.dumps(
                {
                    "git_full_commit_sha": "c" * 40,
                    "git_worktree_dirty": False,
                    "diagnostic_single_method": source_method,
                    "risk_calibration_authority_id": None,
                }
            ),
            encoding="utf-8",
        )
        day_scores = []
        for step in range(2):
            issue = day_index * 2 + step
            score = (day_index + 1) / 100.0 + step / 1000.0
            day_scores.append(score)
            marker_root = method_root / f"issue_{issue:06d}"
            marker_root.mkdir()
            (marker_root / "COMMIT_MARKER.json").write_text(
                json.dumps(
                    {
                        "status": "PASS_COMMITTED",
                        "comparison_method_id": source_method,
                        "issue": issue,
                        "risk_interface": "RAW_UNCALIBRATED",
                        "risk_calibration_authority_id": None,
                        "risk_raw_components": {
                            family: -1.0 for family in RISK_FAMILY_SCALES
                        },
                        "pre_state_sha256": "a" * 64,
                        "post_state_sha256": "b" * 64,
                        "risk_calibration_audit": _audit(
                            issue, score, source_method
                        ),
                    }
                ),
                encoding="utf-8",
            )
        (method_root / "METHOD_SUMMARY.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "comparison_method_id": source_method,
                    "commit_marker_count": 2,
                    "risk_calibration_audit_count": 2,
                    "risk_calibration_day_joint_score": max(day_scores),
                }
            ),
            encoding="utf-8",
        )

    payload = builder.build_calibration(tmp_path, source_method=source_method)
    assert payload["daily_block_count"] == 14
    assert payload["calibration_block_count"] == 28
    assert payload["finite_sample_rank"] == 28
    assert payload["normalized_family_quantiles"]["R_SOC"] == pytest.approx(
        0.141
    )
    assert payload["source_calibrated_risk_positive_count"] == 0
    assert payload["march_outcomes_read"] is False
    assert payload["source_method"] == source_method

    payload.update(
        {
            "calibration_block_steps": 6,
            "calibration_block_minutes": 30,
            "calibration_block_count": CALIBRATION_BLOCK_COUNT,
            "finite_sample_rank": 640,
            "source_issue_count": CALIBRATION_ISSUE_COUNT,
        }
    )
    artifact = tmp_path / "FROZEN_RISK_CALIBRATION.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    calibration = load_frozen_risk_calibration(artifact)
    assert calibration.source_period == CALIBRATION_SOURCE_PERIOD
    assert calibration.normalized_family_quantiles["R_SOC"] == pytest.approx(
        0.141
    )
    assert calibration.calibrated_increments["R_SOC"] == pytest.approx(14.1)


def test_loader_rejects_february_or_march_as_fit_period(tmp_path: Path) -> None:
    artifact = tmp_path / "bad.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "FROZEN",
                "authority_id": AUTHORITY_ID,
                "alpha": 0.05,
                "source_method": "B6",
                "source_period": "2025-01_TO_2025-03",
                "calibration_dates": [f"2025-01-{day:02d}" for day in range(1, 15)],
                "calibration_block_steps": 6,
                "calibration_block_minutes": 30,
                "calibration_block_count": CALIBRATION_BLOCK_COUNT,
                "coverage_claim": "FAMILY_WISE_BLOCK_COVERAGE_NOT_JOINT_COVERAGE",
                "finite_sample_rank": 640,
                "normalized_joint_quantile": 0.1,
                "normalized_family_quantiles": {
                    family: 0.1 for family in RISK_FAMILY_SCALES
                },
                "predeclared_scales": dict(RISK_FAMILY_SCALES),
                "calibrated_increments": {
                    family: 0.1 * scale
                    for family, scale in RISK_FAMILY_SCALES.items()
                },
                "source_audit_sha256": "a" * 64,
                "source_issue_count": CALIBRATION_ISSUE_COUNT,
                "source_calibrated_risk_positive_count": 1,
                "february_labels_used_for_fit": False,
                "march_outcomes_read": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RiskCalibrationContractError, match="2025-01-01"):
        load_frozen_risk_calibration(artifact)


def test_loader_rejects_always_positive_event_trigger_artifact(
    tmp_path: Path,
) -> None:
    quantile = 0.1
    artifact = tmp_path / "degenerate.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "FROZEN",
                "authority_id": AUTHORITY_ID,
                "alpha": 0.05,
                "source_method": "B6",
                "source_period": CALIBRATION_SOURCE_PERIOD,
                "calibration_dates": [
                    f"2025-01-{day:02d}" for day in range(1, 15)
                ],
                "calibration_block_steps": 6,
                "calibration_block_minutes": 30,
                "calibration_block_count": CALIBRATION_BLOCK_COUNT,
                "coverage_claim": "FAMILY_WISE_BLOCK_COVERAGE_NOT_JOINT_COVERAGE",
                "finite_sample_rank": 640,
                "normalized_joint_quantile": quantile,
                "normalized_family_quantiles": {
                    family: quantile for family in RISK_FAMILY_SCALES
                },
                "predeclared_scales": dict(RISK_FAMILY_SCALES),
                "calibrated_increments": {
                    family: quantile * scale
                    for family, scale in RISK_FAMILY_SCALES.items()
                },
                "source_audit_sha256": "a" * 64,
                "source_issue_count": CALIBRATION_ISSUE_COUNT,
                "source_calibrated_risk_positive_count": CALIBRATION_ISSUE_COUNT,
                "february_labels_used_for_fit": False,
                "march_outcomes_read": False,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RiskCalibrationContractError, match="degenerates"):
        load_frozen_risk_calibration(artifact)


def test_february_validation_checks_frozen_b7_binding_without_march(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quantile = 0.2
    calibration_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "FROZEN",
        "authority_id": AUTHORITY_ID,
        "alpha": 0.05,
        "source_method": "B6",
        "source_period": CALIBRATION_SOURCE_PERIOD,
        "calibration_dates": [f"2025-01-{day:02d}" for day in range(1, 15)],
        "calibration_block_steps": 6,
        "calibration_block_minutes": 30,
        "calibration_block_count": CALIBRATION_BLOCK_COUNT,
        "coverage_claim": "FAMILY_WISE_BLOCK_COVERAGE_NOT_JOINT_COVERAGE",
        "finite_sample_rank": 640,
        "normalized_joint_quantile": quantile,
        "normalized_family_quantiles": {
            family: quantile for family in RISK_FAMILY_SCALES
        },
        "predeclared_scales": dict(RISK_FAMILY_SCALES),
        "calibrated_increments": {
            family: quantile * scale
            for family, scale in RISK_FAMILY_SCALES.items()
        },
        "source_audit_sha256": "a" * 64,
        "source_issue_count": CALIBRATION_ISSUE_COUNT,
        "source_calibrated_risk_positive_count": 1,
        "february_labels_used_for_fit": False,
        "march_outcomes_read": False,
    }
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text(json.dumps(calibration_payload), encoding="utf-8")
    calibration = load_frozen_risk_calibration(calibration_path)
    b6_root = tmp_path / "B6_RAW"
    b7_root = tmp_path / "B7_CALIBRATED"
    monkeypatch.setattr(february_validator, "ISSUES_PER_DAY", 1)
    for day_index in range(28):
        calendar_date = f"2025-02-{day_index + 1:02d}"
        issue = 8928 + day_index
        for method, root in (("B6", b6_root), ("B7", b7_root)):
            method_root = root / calendar_date / method
            marker_root = method_root / f"issue_{issue:06d}"
            marker_root.mkdir(parents=True)
            (method_root / "METHOD_SUMMARY.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "comparison_method_id": method,
                        "commit_marker_count": 1,
                    }
                ),
                encoding="utf-8",
            )
            marker = {
                "full_replan_executed": method == "B7" and day_index % 2 == 0,
                "risk_calibration_audit": _audit(issue, 0.1),
            }
            if method == "B7":
                marker.update(
                    {
                        "risk_calibration_authority_id": calibration.authority_id,
                        "risk_calibration_artifact_sha256": calibration.artifact_sha256,
                        "risk_raw_components": {
                            family: -0.5 for family in RISK_FAMILY_SCALES
                        },
                        "risk_calibrated_components": {
                            family: -0.5 + quantile
                            for family in RISK_FAMILY_SCALES
                        },
                    }
                )
            (marker_root / "COMMIT_MARKER.json").write_text(
                json.dumps(marker), encoding="utf-8"
            )

    report = february_validator.validate_february(
        b6_root=b6_root,
        b7_root=b7_root,
        calibration_path=calibration_path,
    )
    assert report["status"] == "PASS"
    assert all(
        value == 1.0
        for value in report[
            "february_empirical_block_coverage_by_family"
        ].values()
    )
    assert report["b7_calibrated_component_checks"] == 28 * 6
    assert report["b7_event_trigger_nondegenerate"] is True
    assert report["march_paths_or_outcomes_read"] is False

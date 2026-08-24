"""Validate frozen January event-risk calibration on February only."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from pfr.risk_calibration import RISK_FAMILY_SCALES, load_frozen_risk_calibration


ISSUES_PER_DAY = 288


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def validate_february(
    *,
    b6_root: Path,
    b7_root: Path,
    calibration_path: Path,
) -> Mapping[str, Any]:
    calibration = load_frozen_risk_calibration(calibration_path)
    quantile = calibration.normalized_joint_quantile
    daily_rows = []
    b6_replans = b7_replans = trigger_divergence = 0
    calibrated_component_checks = 0
    for day_offset in range(28):
        calendar_date = (date(2025, 2, 1) + timedelta(days=day_offset)).isoformat()
        day_scores = []
        for method, root in (("B6", b6_root), ("B7", b7_root)):
            summary = _load(root / calendar_date / method / "METHOD_SUMMARY.json")
            if (
                summary.get("status") != "PASS"
                or summary.get("comparison_method_id") != method
                or int(summary.get("commit_marker_count", -1)) != ISSUES_PER_DAY
            ):
                raise ValueError(f"February {method} day incomplete: {calendar_date}")
        first_issue = 8928 + day_offset * ISSUES_PER_DAY
        for issue in range(first_issue, first_issue + ISSUES_PER_DAY):
            b6 = _load(
                b6_root
                / calendar_date
                / "B6"
                / f"issue_{issue:06d}"
                / "COMMIT_MARKER.json"
            )
            b7 = _load(
                b7_root
                / calendar_date
                / "B7"
                / f"issue_{issue:06d}"
                / "COMMIT_MARKER.json"
            )
            audit = b6.get("risk_calibration_audit")
            if not isinstance(audit, dict):
                raise ValueError(f"February B6 audit missing issue={issue}")
            day_scores.append(float(audit["joint_normalized_score"]))
            if b7.get("risk_calibration_authority_id") != calibration.authority_id:
                raise ValueError(f"February B7 authority ID mismatch issue={issue}")
            if (
                b7.get("risk_calibration_artifact_sha256")
                != calibration.artifact_sha256
            ):
                raise ValueError(f"February B7 authority SHA mismatch issue={issue}")
            raw = b7.get("risk_raw_components")
            calibrated = b7.get("risk_calibrated_components")
            if not isinstance(raw, dict) or not isinstance(calibrated, dict):
                raise ValueError(f"February B7 risk components missing issue={issue}")
            for family in RISK_FAMILY_SCALES:
                difference = float(calibrated[family]) - float(raw[family])
                if not math.isclose(
                    difference, quantile, rel_tol=1e-10, abs_tol=1e-10
                ):
                    raise ValueError(
                        f"February B7 calibrated increment mismatch family={family} issue={issue}"
                    )
                calibrated_component_checks += 1
            b6_triggered = bool(b6.get("full_replan_executed"))
            b7_triggered = bool(b7.get("full_replan_executed"))
            b6_replans += int(b6_triggered)
            b7_replans += int(b7_triggered)
            trigger_divergence += int(b6_triggered != b7_triggered)
        day_score = max(day_scores)
        daily_rows.append(
            {
                "calendar_date": calendar_date,
                "joint_normalized_score": day_score,
                "covered_by_january_quantile": day_score <= quantile,
            }
        )
    covered_days = sum(bool(row["covered_by_january_quantile"]) for row in daily_rows)
    coverage = covered_days / len(daily_rows)
    status = "PASS" if coverage >= 1.0 - calibration.alpha else "FAIL_VALIDATION"
    return {
        "schema_version": "PFR5_EVENT_RISK_FEB2025_VALIDATION_V1",
        "status": status,
        "role": "FEBRUARY_DEVELOPMENT_VALIDATION_ONLY",
        "independent_execution_claim": False,
        "calibration_authority_id": calibration.authority_id,
        "calibration_artifact_sha256": calibration.artifact_sha256,
        "january_normalized_joint_quantile": quantile,
        "target_daily_joint_coverage": 1.0 - calibration.alpha,
        "february_daily_block_count": len(daily_rows),
        "february_covered_daily_blocks": covered_days,
        "february_empirical_daily_joint_coverage": coverage,
        "daily_blocks": daily_rows,
        "b6_full_replan_issues": b6_replans,
        "b7_full_replan_issues": b7_replans,
        "b6_b7_trigger_divergence_issues": trigger_divergence,
        "b7_calibrated_component_checks": calibrated_component_checks,
        "february_labels_used_to_refit_calibration": False,
        "march_paths_or_outcomes_read": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--b6-root", type=Path, required=True)
    parser.add_argument("--b7-root", type=Path, required=True)
    parser.add_argument("--risk-calibration", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = validate_february(
        b6_root=args.b6_root.resolve(),
        b7_root=args.b7_root.resolve(),
        calibration_path=args.risk_calibration.resolve(),
    )
    _atomic_write(args.report.resolve(), report)
    print(json.dumps(report, sort_keys=True), flush=True)
    raise SystemExit(0 if report["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()

"""Freeze PFR5 event-risk margins from January-2025 B6 daily blocks only."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from pfr.risk_calibration import (
    AUTHORITY_ID,
    RISK_FAMILY_SCALES,
    SCHEMA_VERSION,
)


ISSUES_PER_DAY = 288
ALPHA = 0.05


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _validate_audit(audit: Mapping[str, Any], issue: int) -> float:
    if (
        audit.get("schema_version")
        != "PFR5_EVENT_RISK_CALIBRATION_AUDIT_V1"
        or audit.get("role")
        != "B6_RAW_ONE_STEP_PREDECISION_TO_REALIZED_AUDIT"
        or int(audit.get("prediction_issue", -1)) != issue
        or int(audit.get("realization_issue", -1)) != issue
        or int(audit.get("horizon_steps", -1)) != 1
        or audit.get("future_actual_used_by_optimizer") is not False
        or audit.get("actual_opened_post_decision_only") is not True
    ):
        raise ValueError(f"invalid B6 risk calibration audit issue={issue}")
    predicted = audit.get("predicted_violation_margin")
    actual = audit.get("actual_violation_margin")
    scales = audit.get("predeclared_scale")
    positive = audit.get("positive_underprediction_margin")
    normalized = audit.get("normalized_positive_underprediction")
    mappings = (predicted, actual, scales, positive, normalized)
    if any(not isinstance(value, dict) for value in mappings):
        raise ValueError(f"incomplete B6 risk calibration audit issue={issue}")
    if any(set(value) != set(RISK_FAMILY_SCALES) for value in mappings):
        raise ValueError(f"risk family axis mismatch issue={issue}")
    expected_normalized: list[float] = []
    for family, frozen_scale in RISK_FAMILY_SCALES.items():
        if not math.isclose(
            float(scales[family]), frozen_scale, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(f"risk scale changed family={family} issue={issue}")
        expected_positive = max(
            0.0, float(actual[family]) - float(predicted[family])
        )
        if not math.isclose(
            float(positive[family]),
            expected_positive,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(
                f"positive underprediction arithmetic mismatch family={family} issue={issue}"
            )
        expected = expected_positive / frozen_scale
        if not math.isclose(
            float(normalized[family]), expected, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(
                f"normalized underprediction arithmetic mismatch family={family} issue={issue}"
            )
        expected_normalized.append(expected)
    score = max(expected_normalized)
    if not math.isclose(
        float(audit.get("joint_normalized_score", float("nan"))),
        score,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(f"joint normalized score mismatch issue={issue}")
    return score


def build_calibration(source_root: Path, *, alpha: float = ALPHA) -> Mapping[str, Any]:
    source_root = source_root.resolve()
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie in (0,1)")
    dates = tuple(
        (date(2025, 1, 1) + timedelta(days=offset)).isoformat()
        for offset in range(31)
    )
    daily_scores: list[Mapping[str, Any]] = []
    source_audits: list[Mapping[str, Any]] = []
    source_commits: set[str] = set()
    for offset, calendar_date in enumerate(dates):
        day_root = source_root / calendar_date
        method_root = day_root / "B6"
        manifest = _load_json(day_root / "RUN_MANIFEST.json")
        source_commit = str(manifest.get("git_full_commit_sha", ""))
        if (
            len(source_commit) != 40
            or manifest.get("git_worktree_dirty") is not False
            or manifest.get("diagnostic_single_method") != "B6"
            or manifest.get("risk_calibration_authority_id") is not None
        ):
            raise ValueError(
                f"January B6 source manifest is not a clean raw calibration run: {calendar_date}"
            )
        source_commits.add(source_commit)
        summary = _load_json(method_root / "METHOD_SUMMARY.json")
        if (
            summary.get("status") != "PASS"
            or summary.get("comparison_method_id") != "B6"
            or int(summary.get("commit_marker_count", -1)) != ISSUES_PER_DAY
            or int(summary.get("risk_calibration_audit_count", -1))
            != ISSUES_PER_DAY
        ):
            raise ValueError(f"January B6 day is incomplete: {calendar_date}")
        first_issue = offset * ISSUES_PER_DAY
        scores = []
        for issue in range(first_issue, first_issue + ISSUES_PER_DAY):
            marker = _load_json(
                method_root / f"issue_{issue:06d}" / "COMMIT_MARKER.json"
            )
            if (
                marker.get("status") != "PASS_COMMITTED"
                or marker.get("comparison_method_id") != "B6"
                or int(marker.get("issue", -1)) != issue
                or marker.get("risk_interface") != "RAW_UNCALIBRATED"
                or marker.get("risk_calibration_authority_id") is not None
            ):
                raise ValueError(
                    f"January calibration source is not raw B6 issue={issue}"
                )
            audit = marker.get("risk_calibration_audit")
            if not isinstance(audit, dict):
                raise ValueError(f"risk calibration audit missing issue={issue}")
            scores.append(_validate_audit(audit, issue))
            source_audits.append(
                {
                    "calendar_date": calendar_date,
                    "issue": issue,
                    "audit": audit,
                    "pre_state_sha256": marker.get("pre_state_sha256"),
                    "post_state_sha256": marker.get("post_state_sha256"),
                }
            )
        day_score = max(scores)
        if not math.isclose(
            float(summary.get("risk_calibration_day_joint_score", float("nan"))),
            day_score,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(f"daily joint score mismatch: {calendar_date}")
        daily_scores.append(
            {
                "calendar_date": calendar_date,
                "joint_normalized_score": day_score,
                "issue_count": ISSUES_PER_DAY,
            }
        )
    if len(source_commits) != 1:
        raise ValueError("January B6 calibration days use multiple implementation commits")
    ordered = sorted(float(row["joint_normalized_score"]) for row in daily_scores)
    rank = min(math.ceil((len(ordered) + 1) * (1.0 - alpha)), len(ordered))
    quantile = ordered[rank - 1]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "FROZEN",
        "authority_id": AUTHORITY_ID,
        "source_method": "B6",
        "source_risk_interface": "RAW_UNCALIBRATED",
        "source_period": "2025-01",
        "calibration_dates": list(dates),
        "calibration_block": "INDEPENDENT_DAILY_MAX_OVER_288_ISSUES_AND_6_RISK_FAMILIES",
        "one_step_residual": "MAX_0_ACTUAL_MARGIN_MINUS_PREDECISION_MARGIN",
        "joint_score": "MAX_OVER_RISK_FAMILIES_OF_POSITIVE_UNDERPREDICTION_DIVIDED_BY_PREDECLARED_SCALE",
        "alpha": alpha,
        "target_joint_coverage": 1.0 - alpha,
        "daily_block_count": len(daily_scores),
        "finite_sample_rank": rank,
        "normalized_joint_quantile": quantile,
        "predeclared_scales": dict(RISK_FAMILY_SCALES),
        "calibrated_increments": {
            family: quantile * scale
            for family, scale in RISK_FAMILY_SCALES.items()
        },
        "daily_block_scores": daily_scores,
        "source_audit_sha256": _canonical_sha256(source_audits),
        "source_git_full_commit_sha": next(iter(source_commits)),
        "source_root": str(source_root),
        "february_role": "DEVELOPMENT_VALIDATION_ONLY_NO_REFIT_FROM_VALIDATION_LABELS",
        "february_labels_used_for_fit": False,
        "march_role": "INDEPENDENT_EXECUTION_PROHIBITED_FROM_CALIBRATION_OR_VALIDATION_ACCESS",
        "march_outcomes_read": False,
        "no_february_or_march_labels_used_for_fit": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    args = parser.parse_args()
    payload = build_calibration(args.source_root, alpha=args.alpha)
    _atomic_write_json(args.output.resolve(), payload)
    print(
        json.dumps(
            {
                "status": "FROZEN",
                "output": str(args.output.resolve()),
                "daily_blocks": payload["daily_block_count"],
                "finite_sample_rank": payload["finite_sample_rank"],
                "normalized_joint_quantile": payload[
                    "normalized_joint_quantile"
                ],
                "march_outcomes_read": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

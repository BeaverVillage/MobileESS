"""Freeze family-wise PFR5 event-risk margins from January-2025 B6 blocks."""

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
    CALIBRATION_BLOCK_STEPS,
    CALIBRATION_DAY_COUNT,
    CALIBRATION_SOURCE_PERIOD,
    CALIBRATION_START_DATE,
    ELECTRICAL_STRESS_AUTHORITY_ID,
    ELECTRICAL_STRESS_SCHEMA_VERSION,
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


def _validate_audit(
    audit: Mapping[str, Any], issue: int, *, source_method: str = "B6"
) -> Mapping[str, float]:
    if (
        audit.get("schema_version")
        != "PFR5_EVENT_RISK_CALIBRATION_AUDIT_V1"
        or audit.get("role")
        != f"{source_method}_RAW_ONE_STEP_PREDECISION_TO_REALIZED_AUDIT"
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
    return {
        family: float(normalized[family]) for family in RISK_FAMILY_SCALES
    }


def build_calibration(
    source_root: Path,
    *,
    alpha: float = ALPHA,
    source_method: str = "B6",
    authorized_reuse_fingerprints: tuple[str, ...] = (),
) -> Mapping[str, Any]:
    source_root = source_root.resolve()
    if source_method not in {"B6", "B07"}:
        raise ValueError("calibration source method must be B6 or B07")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie in (0,1)")
    if (
        CALIBRATION_BLOCK_STEPS <= 0
        or ISSUES_PER_DAY % CALIBRATION_BLOCK_STEPS != 0
    ):
        raise ValueError("calibration block must exactly partition every day")
    dates = tuple(
        (CALIBRATION_START_DATE + timedelta(days=offset)).isoformat()
        for offset in range(CALIBRATION_DAY_COUNT)
    )
    daily_scores: list[Mapping[str, Any]] = []
    block_scores: list[Mapping[str, Any]] = []
    source_audits: list[Mapping[str, Any]] = []
    source_raw_components: list[Mapping[str, float]] = []
    source_commits: set[str] = set()
    source_lineages: set[tuple[str, str]] = set()
    for offset, calendar_date in enumerate(dates):
        day_root = source_root / calendar_date
        method_root = day_root / source_method
        manifest = _load_json(day_root / "RUN_MANIFEST.json")
        source_commit = str(manifest.get("git_full_commit_sha", ""))
        source_fingerprint = str(
            manifest.get("scientific_implementation_fingerprint", "")
        )
        if (
            len(source_commit) != 40
            or manifest.get("git_worktree_dirty") is not False
            or manifest.get("diagnostic_single_method") != source_method
            or manifest.get("risk_calibration_authority_id") is not None
        ):
            raise ValueError(
                f"January {source_method} source manifest is not a clean raw calibration run: {calendar_date}"
            )
        source_commits.add(source_commit)
        source_lineages.add((source_commit, source_fingerprint))
        summary = _load_json(method_root / "METHOD_SUMMARY.json")
        if (
            summary.get("status") != "PASS"
            or summary.get("comparison_method_id") != source_method
            or int(summary.get("commit_marker_count", -1)) != ISSUES_PER_DAY
            or int(summary.get("risk_calibration_audit_count", -1))
            != ISSUES_PER_DAY
        ):
            raise ValueError(
                f"January {source_method} day is incomplete: {calendar_date}"
            )
        first_issue = offset * ISSUES_PER_DAY
        family_scores: list[Mapping[str, float]] = []
        joint_scores: list[float] = []
        for issue in range(first_issue, first_issue + ISSUES_PER_DAY):
            marker = _load_json(
                method_root / f"issue_{issue:06d}" / "COMMIT_MARKER.json"
            )
            if (
                marker.get("status") != "PASS_COMMITTED"
                or marker.get("comparison_method_id") != source_method
                or int(marker.get("issue", -1)) != issue
                or marker.get("risk_interface") != "RAW_UNCALIBRATED"
                or marker.get("risk_calibration_authority_id") is not None
            ):
                raise ValueError(
                    f"January calibration source is not raw {source_method} issue={issue}"
                )
            audit = marker.get("risk_calibration_audit")
            if not isinstance(audit, dict):
                raise ValueError(f"risk calibration audit missing issue={issue}")
            normalized = _validate_audit(
                audit, issue, source_method=source_method
            )
            family_scores.append(normalized)
            joint_scores.append(max(normalized.values()))
            raw_components = marker.get("risk_raw_components")
            if (
                not isinstance(raw_components, dict)
                or set(raw_components) != set(RISK_FAMILY_SCALES)
                or any(
                    not math.isfinite(float(raw_components[family]))
                    for family in RISK_FAMILY_SCALES
                )
            ):
                raise ValueError(f"raw risk component evidence missing issue={issue}")
            source_raw_components.append(
                {
                    family: float(raw_components[family])
                    for family in RISK_FAMILY_SCALES
                }
            )
            source_audits.append(
                {
                    "calendar_date": calendar_date,
                    "issue": issue,
                    "audit": audit,
                    "pre_state_sha256": marker.get("pre_state_sha256"),
                    "post_state_sha256": marker.get("post_state_sha256"),
                }
            )
        day_score = max(joint_scores)
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
        for block_start in range(0, ISSUES_PER_DAY, CALIBRATION_BLOCK_STEPS):
            block_rows = family_scores[
                block_start : block_start + CALIBRATION_BLOCK_STEPS
            ]
            family_maxima = {
                family: max(row[family] for row in block_rows)
                for family in RISK_FAMILY_SCALES
            }
            block_scores.append(
                {
                    "calendar_date": calendar_date,
                    "block_index_within_day": (
                        block_start // CALIBRATION_BLOCK_STEPS
                    ),
                    "first_issue": first_issue + block_start,
                    "issue_count": CALIBRATION_BLOCK_STEPS,
                    "normalized_family_maxima": family_maxima,
                }
            )
    primary_commits = set(source_commits)
    if len(source_commits) != 1:
        if any(
            len(fingerprint) != 64
            or any(char not in "0123456789abcdef" for char in fingerprint)
            for _commit, fingerprint in source_lineages
        ):
            raise ValueError(
                f"January {source_method} mixed-commit calibration lacks "
                "implementation fingerprints"
            )
        primary_lineages = {
            (commit, fingerprint)
            for commit, fingerprint in source_lineages
            if fingerprint not in authorized_reuse_fingerprints
        }
        primary_fingerprints = {
            fingerprint for _commit, fingerprint in primary_lineages
        }
        primary_commits = {commit for commit, _fingerprint in primary_lineages}
        if len(primary_fingerprints) != 1 or len(primary_commits) != 1:
            raise ValueError(
                f"January {source_method} calibration days use multiple "
                "unapproved implementation lineages"
            )
    rank = min(
        math.ceil((len(block_scores) + 1) * (1.0 - alpha)),
        len(block_scores),
    )
    family_quantiles = {
        family: sorted(
            float(row["normalized_family_maxima"][family])
            for row in block_scores
        )[rank - 1]
        for family in RISK_FAMILY_SCALES
    }
    calibrated_increments = {
        family: family_quantiles[family] * scale
        for family, scale in RISK_FAMILY_SCALES.items()
    }
    source_positive_trigger_count = sum(
        max(
            float(raw[family]) + family_quantiles[family]
            for family in RISK_FAMILY_SCALES
        )
        > 0.0
        for raw in source_raw_components
    )
    if source_positive_trigger_count >= len(source_raw_components):
        raise ValueError(
            "calibration degenerates B7 into an always-positive risk trigger"
        )
    return {
        "schema_version": (
            ELECTRICAL_STRESS_SCHEMA_VERSION
            if source_method == "B07"
            else SCHEMA_VERSION
        ),
        "status": "FROZEN",
        "authority_id": (
            ELECTRICAL_STRESS_AUTHORITY_ID
            if source_method == "B07"
            else AUTHORITY_ID
        ),
        "source_method": source_method,
        "source_risk_interface": "RAW_UNCALIBRATED",
        "source_period": CALIBRATION_SOURCE_PERIOD,
        "calibration_dates": list(dates),
        "calibration_block": "NONOVERLAPPING_30_MINUTE_MAXIMA_WITHIN_CALENDAR_DAY",
        "calibration_block_steps": CALIBRATION_BLOCK_STEPS,
        "calibration_block_minutes": CALIBRATION_BLOCK_STEPS * 5,
        "one_step_residual": "MAX_0_ACTUAL_MARGIN_MINUS_PREDECISION_MARGIN",
        "coverage_claim": "FAMILY_WISE_BLOCK_COVERAGE_NOT_JOINT_COVERAGE",
        "family_block_score": "MAX_WITHIN_NONOVERLAPPING_BLOCK_OF_NORMALIZED_POSITIVE_UNDERPREDICTION",
        "alpha": alpha,
        "target_family_block_coverage": 1.0 - alpha,
        "daily_block_count": len(daily_scores),
        "calibration_block_count": len(block_scores),
        "finite_sample_rank": rank,
        "normalized_family_quantiles": family_quantiles,
        "normalized_joint_quantile": max(family_quantiles.values()),
        "predeclared_scales": dict(RISK_FAMILY_SCALES),
        "calibrated_increments": calibrated_increments,
        "daily_block_scores": daily_scores,
        "family_block_scores": block_scores,
        "source_issue_count": len(source_raw_components),
        "source_calibrated_risk_positive_count": source_positive_trigger_count,
        "source_calibrated_risk_positive_fraction": (
            source_positive_trigger_count / len(source_raw_components)
        ),
        "nondegenerate_event_trigger_gate": (
            f"PASS_NOT_ALWAYS_POSITIVE_ON_SOURCE_{source_method}_STATES"
        ),
        "source_audit_sha256": _canonical_sha256(source_audits),
        "source_git_full_commit_sha": next(iter(primary_commits)),
        "source_git_full_commit_shas": sorted(source_commits),
        "source_scientific_implementation_fingerprints": sorted(
            fingerprint
            for _commit, fingerprint in source_lineages
            if fingerprint
        ),
        "authorized_verified_pass_reuse_fingerprints": sorted(
            set(authorized_reuse_fingerprints)
        ),
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
    parser.add_argument(
        "--reuse-verified-pass-fingerprint",
        action="append",
        default=[],
        help=(
            "Explicitly authorize a clean PASS source lineage already "
            "authorized by the daily campaign and storage verifier."
        ),
    )
    parser.add_argument(
        "--source-method",
        choices=("B6", "B07"),
        default="B07",
        help="Raw-risk January method; B07 is authoritative for B00-B09.",
    )
    args = parser.parse_args()
    if any(
        len(value) != 64
        or value.lower() != value
        or any(char not in "0123456789abcdef" for char in value)
        for value in args.reuse_verified_pass_fingerprint
    ):
        parser.error(
            "--reuse-verified-pass-fingerprint must be a lowercase SHA-256"
        )
    payload = build_calibration(
        args.source_root,
        alpha=args.alpha,
        source_method=args.source_method,
        authorized_reuse_fingerprints=tuple(
            args.reuse_verified_pass_fingerprint
        ),
    )
    _atomic_write_json(args.output.resolve(), payload)
    print(
        json.dumps(
            {
                "status": "FROZEN",
                "output": str(args.output.resolve()),
                "calibration_blocks": payload["calibration_block_count"],
                "finite_sample_rank": payload["finite_sample_rank"],
                "normalized_family_quantiles": payload[
                    "normalized_family_quantiles"
                ],
                "source_calibrated_risk_positive_fraction": payload[
                    "source_calibrated_risk_positive_fraction"
                ],
                "march_outcomes_read": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

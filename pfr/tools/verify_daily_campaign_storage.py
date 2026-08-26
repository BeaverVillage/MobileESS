"""Verify that a daily campaign is complete, parseable, and restart-safe."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from pfr.provenance import scientific_implementation_fingerprint
from pfr.result_storage import validate_campaign_summary
from pfr.risk_calibration import RISK_FAMILY_SCALES
from pfr.runtime import MESS_FLOOR_KWH


METHODS = tuple(f"B{index}" for index in range(8))
B8_METHODS = ("B8",)
ELECTRICAL_STRESS_METHODS = tuple(f"B{index:02d}" for index in range(10))
ISSUES_PER_DAY = 288


def load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _prediction_actual_evidence_errors(marker: Mapping[str, Any]) -> list[str]:
    """Validate the v2 mobility/migration audit payload before accepting storage."""
    if marker.get("schema_version") != "K9H7_RESULT_V2.issue_commit.v2":
        return []
    errors: list[str] = []
    required = {
        "mobility_started_events",
        "mobility_started_route_count",
        "mobility_q50_eta_prediction_error_seconds_started_routes",
        "mobility_q50_energy_prediction_error_kwh_started_routes",
        "mobility_realized_protected_floor_shortfall_kwh_started_routes",
        "mobility_realized_protected_floor_violation_route_count",
        "migration_prediction_actual_events",
        "migration_prediction_actual_event_count",
        "migration_duration_prediction_error_seconds",
    }
    missing = sorted(required - set(marker))
    if missing:
        return [f"prediction/actual evidence fields missing: {missing}"]
    mobility = marker.get("mobility_started_events")
    migrations = marker.get("migration_prediction_actual_events")
    if not isinstance(mobility, list) or not isinstance(migrations, list):
        return ["prediction/actual event evidence is not a list"]
    if int(marker["mobility_started_route_count"]) != len(mobility):
        errors.append("mobility started-route count mismatch")
    if int(marker["migration_prediction_actual_event_count"]) != len(migrations):
        errors.append("migration prediction/actual event count mismatch")
    tolerance = 1e-8
    for event in mobility:
        try:
            eta_error = float(event["sumo_realized_eta_seconds"]) - float(
                event["planned_q50_eta_seconds"]
            )
            energy_error = float(
                event["realized_mobility_energy_route_total_kwh"]
            ) - float(event["planned_mobility_energy_kwh"])
            terminal_energy = float(event["realized_terminal_energy_kwh"])
            floor_shortfall = max(0.0, MESS_FLOOR_KWH - terminal_energy)
            if abs(eta_error - float(event["q50_eta_prediction_error_seconds"])) > tolerance:
                errors.append("mobility ETA prediction/actual error arithmetic mismatch")
            if abs(
                energy_error - float(event["q50_energy_prediction_error_kwh"])
            ) > tolerance:
                errors.append("mobility energy prediction/actual error arithmetic mismatch")
            if event.get("actual_used_by_optimizer") is not False:
                errors.append("mobility realized actual leaked to optimizer")
            if event.get("actual_opened_post_decision_only") is not True:
                errors.append("mobility realized actual was not post-decision only")
            if abs(
                floor_shortfall
                - float(event["realized_protected_floor_shortfall_kwh"])
            ) > tolerance:
                errors.append("mobility realized SOC-floor shortfall arithmetic mismatch")
            if bool(event["realized_route_protected_floor_feasible"]) != (
                terminal_energy >= MESS_FLOOR_KWH - 1e-9
            ):
                errors.append("mobility realized SOC-floor feasibility mismatch")
        except (KeyError, TypeError, ValueError):
            errors.append("mobility prediction/actual event is incomplete")
    for event in migrations:
        try:
            step_error = int(event["realized_total_downtime_steps"]) - int(
                event["predicted_total_downtime_steps"]
            )
            if step_error != int(event["total_downtime_error_steps"]):
                errors.append("migration duration error arithmetic mismatch")
            if int(event["total_downtime_error_seconds"]) != step_error * 300:
                errors.append("migration duration seconds/steps mismatch")
            if event.get("external_observed_wan_telemetry") is not False:
                errors.append("migration telemetry classification is invalid")
        except (KeyError, TypeError, ValueError):
            errors.append("migration prediction/actual event is incomplete")
    try:
        mobility_eta_error = sum(
            float(event["q50_eta_prediction_error_seconds"])
            for event in mobility
        )
        mobility_energy_error = sum(
            float(event["q50_energy_prediction_error_kwh"])
            for event in mobility
        )
        mobility_floor_shortfall = sum(
            float(event["realized_protected_floor_shortfall_kwh"])
            for event in mobility
        )
        mobility_floor_violations = sum(
            not bool(event["realized_route_protected_floor_feasible"])
            for event in mobility
        )
        migration_duration_error = sum(
            int(event["total_downtime_error_seconds"])
            for event in migrations
        )
        if abs(
            mobility_eta_error
            - float(
                marker[
                    "mobility_q50_eta_prediction_error_seconds_started_routes"
                ]
            )
        ) > tolerance:
            errors.append("mobility ETA aggregate error mismatch")
        if abs(
            mobility_energy_error
            - float(
                marker[
                    "mobility_q50_energy_prediction_error_kwh_started_routes"
                ]
            )
        ) > tolerance:
            errors.append("mobility energy aggregate error mismatch")
        if migration_duration_error != int(
            marker["migration_duration_prediction_error_seconds"]
        ):
            errors.append("migration duration aggregate error mismatch")
        if abs(
            mobility_floor_shortfall
            - float(
                marker[
                    "mobility_realized_protected_floor_shortfall_kwh_started_routes"
                ]
            )
        ) > tolerance:
            errors.append("mobility SOC-floor shortfall aggregate mismatch")
        if mobility_floor_violations != int(
            marker["mobility_realized_protected_floor_violation_route_count"]
        ):
            errors.append("mobility SOC-floor violation aggregate mismatch")
    except (KeyError, TypeError, ValueError):
        errors.append("prediction/actual aggregate evidence is incomplete")
    return errors


def _risk_calibration_evidence_errors(marker: Mapping[str, Any]) -> list[str]:
    method = str(marker.get("comparison_method_id", ""))
    if (
        marker.get("schema_version") != "K9H7_RESULT_V2.issue_commit.v2"
        or method not in {"B6", "B07"}
    ):
        return []
    audit = marker.get("risk_calibration_audit")
    if not isinstance(audit, dict):
        return [f"{method} risk calibration audit missing"]
    if (
        audit.get("schema_version")
        != "PFR5_EVENT_RISK_CALIBRATION_AUDIT_V1"
        or audit.get("future_actual_used_by_optimizer") is not False
        or audit.get("actual_opened_post_decision_only") is not True
    ):
        return [f"{method} risk calibration audit authority invalid"]
    predicted = audit.get("predicted_violation_margin")
    actual = audit.get("actual_violation_margin")
    scales = audit.get("predeclared_scale")
    positive = audit.get("positive_underprediction_margin")
    normalized = audit.get("normalized_positive_underprediction")
    mappings = (predicted, actual, scales, positive, normalized)
    if any(not isinstance(value, dict) for value in mappings) or any(
        set(value) != set(RISK_FAMILY_SCALES) for value in mappings
    ):
        return [f"{method} risk calibration family evidence incomplete"]
    errors: list[str] = []
    expected_scores = []
    for family, frozen_scale in RISK_FAMILY_SCALES.items():
        try:
            expected_positive = max(
                0.0, float(actual[family]) - float(predicted[family])
            )
            expected_normalized = expected_positive / frozen_scale
            if abs(float(scales[family]) - frozen_scale) > 1e-12:
                errors.append(f"{method} risk scale mismatch family={family}")
            if abs(float(positive[family]) - expected_positive) > 1e-10:
                errors.append(
                    f"{method} risk positive residual arithmetic mismatch family={family}"
                )
            if abs(float(normalized[family]) - expected_normalized) > 1e-10:
                errors.append(
                    f"{method} risk normalized residual arithmetic mismatch family={family}"
                )
            expected_scores.append(expected_normalized)
        except (TypeError, ValueError, KeyError):
            errors.append(f"{method} risk calibration numeric evidence invalid family={family}")
    try:
        if abs(float(audit["joint_normalized_score"]) - max(expected_scores)) > 1e-10:
            errors.append(f"{method} risk joint score arithmetic mismatch")
    except (TypeError, ValueError, KeyError):
        errors.append(f"{method} risk joint score missing")
    return errors


def inspect_method(
    method_root: Path,
    method: str,
    expected_first_issue: int,
) -> dict[str, Any]:
    errors: list[str] = []
    markers: list[Mapping[str, Any]] = []
    for marker_path in sorted(method_root.glob("issue_*/COMMIT_MARKER.json")):
        try:
            marker = load_json(marker_path)
            if marker.get("status") != "PASS_COMMITTED":
                raise ValueError("status is not PASS_COMMITTED")
            if marker.get("commit_marker") is not True:
                raise ValueError("commit_marker is not true")
            if marker.get("comparison_method_id") != method:
                raise ValueError("comparison_method_id mismatch")
            if marker.get("actual_gurobi_used") is not True:
                raise ValueError("actual Gurobi evidence missing")
            if marker.get("actual_fresh_opendss_used") is not True:
                raise ValueError("fresh OpenDSS evidence missing")
            if marker.get("future_actual_used") is not False:
                raise ValueError("future actual leakage flag")
            if not marker.get("pre_state_sha256") or not marker.get(
                "post_state_sha256"
            ):
                raise ValueError("state-chain hash missing")
            evidence_errors = _prediction_actual_evidence_errors(marker)
            evidence_errors.extend(_risk_calibration_evidence_errors(marker))
            if evidence_errors:
                raise ValueError("; ".join(evidence_errors))
            markers.append(marker)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{marker_path}: {type(exc).__name__}: {exc}")
    markers.sort(key=lambda row: int(row["issue"]))
    issues = [int(row["issue"]) for row in markers]
    expected_issues = list(
        range(expected_first_issue, expected_first_issue + ISSUES_PER_DAY)
    )
    if len(issues) != len(set(issues)):
        errors.append("duplicate committed issue")
    if markers and issues != expected_issues[: len(issues)]:
        errors.append("committed issue axis is not the exact daily 288-step range")
    if any(
        markers[index]["post_state_sha256"]
        != markers[index + 1]["pre_state_sha256"]
        for index in range(max(0, len(markers) - 1))
    ):
        errors.append("state chain is discontinuous")

    summary_path = method_root / "METHOD_SUMMARY.json"
    failure_path = method_root / "FAILURE.json"
    summary: Mapping[str, Any] | None = None
    failure: Mapping[str, Any] | None = None
    try:
        if summary_path.is_file():
            summary = load_json(summary_path)
        if failure_path.is_file():
            failure = load_json(failure_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"method evidence JSON: {type(exc).__name__}: {exc}")
    if summary is not None:
        if summary.get("comparison_method_id") != method:
            errors.append("METHOD_SUMMARY method mismatch")
        if int(summary.get("commit_marker_count", -1)) != len(markers):
            errors.append("METHOD_SUMMARY commit count mismatch")
        if summary.get("status") == "PASS" and len(markers) != ISSUES_PER_DAY:
            errors.append("PASS method does not contain 288 markers")
        if summary.get("status") == "PASS" and method in {"B6", "B07"}:
            if int(summary.get("risk_calibration_audit_count", -1)) != len(markers):
                errors.append(f"PASS {method} risk calibration audit count mismatch")
            marker_scores = [
                float(row["risk_calibration_audit"]["joint_normalized_score"])
                for row in markers
                if isinstance(row.get("risk_calibration_audit"), dict)
            ]
            if marker_scores:
                summary_score = float(
                    summary.get("risk_calibration_day_joint_score", float("nan"))
                )
                if not math.isfinite(summary_score) or abs(
                    summary_score - max(marker_scores)
                ) > 1e-10:
                    errors.append(f"PASS {method} daily risk calibration score mismatch")
        if (
            summary.get("status") == "PASS"
            and summary.get("schema_version") == "K9H7_RESULT_V2.method_run.v2"
        ):
            terminal_state = summary.get("final_mess_in_transit")
            if not isinstance(terminal_state, dict) or not terminal_state:
                errors.append("PASS method lacks terminal MESS transit evidence")
            elif any(bool(value) for value in terminal_state.values()):
                errors.append("PASS method ends with an in-transit MESS route")
            if summary.get("terminal_mobility_complete") is not True:
                errors.append("PASS method terminal mobility completion flag is not true")
        if summary.get("status") != "PASS" and failure is None:
            errors.append("failed method has no FAILURE.json")
    elif method_root.exists() and (markers or failure is not None):
        errors.append("METHOD_SUMMARY.json missing")

    csv_path = method_root / "MATERIALIZED_COMMIT_ROWS.csv"
    csv_issues: list[int] = []
    if csv_path.is_file():
        try:
            csv.field_size_limit(64 * 1024 * 1024)
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None or "issue" not in reader.fieldnames:
                    raise ValueError("issue column missing")
                if any(
                    row.get("schema_version")
                    == "K9H7_RESULT_V2.issue_commit.v2"
                    for row in markers
                ):
                    required_csv_fields = {
                        "mobility_started_events",
                        "mobility_q50_eta_prediction_error_seconds_started_routes",
                        "mobility_q50_energy_prediction_error_kwh_started_routes",
                        "migration_prediction_actual_events",
                        "migration_duration_prediction_error_seconds",
                    }
                    missing_csv = sorted(required_csv_fields - set(reader.fieldnames))
                    if missing_csv:
                        raise ValueError(
                            f"prediction/actual CSV fields missing: {missing_csv}"
                        )
                for row in reader:
                    csv_issues.append(int(row["issue"]))
                    if row.get("comparison_method_id") != method:
                        errors.append("materialized CSV method axis mismatch")
            if csv_issues != issues:
                errors.append("materialized CSV issue axis differs from commit markers")
        except (OSError, ValueError, TypeError, csv.Error) as exc:
            errors.append(f"materialized CSV: {type(exc).__name__}: {exc}")
    elif summary is not None and summary.get("status") == "PASS":
        errors.append("PASS method lacks MATERIALIZED_COMMIT_ROWS.csv")

    issue_directories = sorted(
        path.name for path in method_root.glob("issue_*") if path.is_dir()
    )
    expected_directories = [f"issue_{issue:06d}" for issue in expected_issues]
    if summary is not None and summary.get("status") == "PASS":
        if issue_directories != expected_directories:
            errors.append("PASS method issue-directory axis is incomplete or contains extras")
    return {
        "method": method,
        "status": summary.get("status") if summary is not None else "NOT_RUN",
        "commit_markers": len(markers),
        "first_issue": min(issues) if issues else None,
        "last_issue": max(issues) if issues else None,
        "materialized_csv_rows": len(csv_issues),
        "failure_evidence": failure is not None,
        "errors": errors,
    }


def inspect_day(
    day_root: Path,
    calendar_date: str,
    implementation_fingerprint: str,
    methods: tuple[str, ...] = METHODS,
    authorized_implementation_fingerprints: tuple[str, ...] = (),
) -> dict[str, Any]:
    errors: list[str] = []
    expected_first_issue = (
        date.fromisoformat(calendar_date) - date(2025, 1, 1)
    ).days * ISSUES_PER_DAY
    method_rows = [
        inspect_method(day_root / method, method, expected_first_issue)
        for method in methods
    ]
    errors.extend(
        error for method in method_rows for error in method["errors"]
    )
    temp_files = [str(path) for path in day_root.rglob("*.tmp")]
    if temp_files:
        errors.append("unpublished temporary files remain")

    summary = manifest = None
    try:
        if (day_root / "MATRIX_SUMMARY.json").is_file():
            summary = load_json(day_root / "MATRIX_SUMMARY.json")
        if (day_root / "RUN_MANIFEST.json").is_file():
            manifest = load_json(day_root / "RUN_MANIFEST.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"day JSON: {type(exc).__name__}: {exc}")

    orchestration_failure = None
    try:
        path = day_root / "ORCHESTRATION_FAILURE.json"
        if path.is_file():
            orchestration_failure = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"orchestration failure JSON: {type(exc).__name__}: {exc}")

    marker_count = sum(int(row["commit_markers"]) for row in method_rows)
    scientific_status = "NOT_RUN"
    complete = False
    if summary is not None:
        scientific_status = str(summary.get("status", "UNKNOWN"))
        complete = True
        if int(summary.get("valid_commit_markers", -1)) != marker_count:
            errors.append("MATRIX_SUMMARY commit count mismatch")
        if int(summary.get("method_count", -1)) != len(methods):
            errors.append("MATRIX_SUMMARY method count mismatch")
        if int(summary.get("issues_per_method", -1)) != ISSUES_PER_DAY:
            errors.append("MATRIX_SUMMARY issue-axis size mismatch")
        if int(summary.get("expected_commit_markers", -1)) != (
            ISSUES_PER_DAY * len(methods)
        ):
            errors.append("MATRIX_SUMMARY expected marker matrix mismatch")
        if summary.get("method_execution_order") != list(methods):
            errors.append("MATRIX_SUMMARY method execution axis mismatch")
        if summary.get("continue_to_next_method_after_failure") is not True:
            errors.append("B-failure continuation policy missing")
        if scientific_status == "PASS":
            if marker_count != ISSUES_PER_DAY * len(methods):
                errors.append(
                    "PASS day does not contain the expected method-axis markers"
                )
            if summary.get("all_actual_gurobi") is not True:
                errors.append("PASS day lacks all-actual-Gurobi evidence")
            if summary.get("all_fresh_exact_opendss") is not True:
                errors.append("PASS day lacks fresh-OpenDSS evidence")
            if summary.get("all_state_chains_complete") is not True:
                errors.append("PASS day lacks state-chain evidence")
    elif orchestration_failure is not None:
        scientific_status = "FAIL_CLOSED_ORCHESTRATION_EXCEPTION"
        complete = True

    if manifest is not None:
        artifact_fingerprint = manifest.get(
            "scientific_implementation_fingerprint"
        )
        if (
            artifact_fingerprint != implementation_fingerprint
            and artifact_fingerprint
            not in authorized_implementation_fingerprints
        ):
            errors.append("scientific implementation fingerprint drift")
        if manifest.get("status") != scientific_status and summary is not None:
            errors.append("RUN_MANIFEST/MATRIX_SUMMARY status mismatch")
        if int(manifest.get("count", -1)) != ISSUES_PER_DAY:
            errors.append("RUN_MANIFEST issue count mismatch")
        if int(manifest.get("start_issue", -1)) != expected_first_issue:
            errors.append("RUN_MANIFEST daily issue origin mismatch")
        if len(str(manifest.get("git_full_commit_sha", ""))) != 40:
            errors.append("RUN_MANIFEST full Git SHA missing")
        if manifest.get("git_worktree_dirty") is not False:
            errors.append("RUN_MANIFEST was produced from a dirty worktree")
        source_authority_path = Path(
            str(manifest.get("shared_exogenous_authority_path", ""))
        )
        if (
            not source_authority_path.is_file()
            or manifest.get("shared_exogenous_authority_sha256")
            != sha256(source_authority_path)
        ):
            errors.append("shared exogenous authority path/SHA drift")
    elif summary is not None:
        errors.append("RUN_MANIFEST.json missing")

    return {
        "calendar_date": calendar_date,
        "complete": complete,
        "scientific_status": scientific_status,
        "storage_integrity": "PASS" if not errors else "FAIL",
        "commit_markers": marker_count,
        "methods": method_rows,
        "orchestration_failure_evidence": orchestration_failure is not None,
        "temporary_files": temp_files,
        "artifact_scientific_implementation_fingerprint": (
            manifest.get("scientific_implementation_fingerprint")
            if manifest is not None
            else None
        ),
        "cross_implementation_reuse_authorized": bool(
            manifest is not None
            and manifest.get("scientific_implementation_fingerprint")
            != implementation_fingerprint
            and manifest.get("scientific_implementation_fingerprint")
            in authorized_implementation_fingerprints
        ),
        "errors": errors,
    }


def inspect_campaign_registry(
    root: Path,
    expected_dates: list[str],
    methods: tuple[str, ...],
) -> dict[str, Any]:
    path = root / "CAMPAIGN_SUMMARY.json"
    errors: list[str] = []
    if not path.is_file():
        return {"present": False, "status": "MISSING", "errors": [
            "CAMPAIGN_SUMMARY.json missing"
        ]}
    try:
        summary = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "present": True,
            "status": "UNREADABLE",
            "errors": [f"CAMPAIGN_SUMMARY.json: {type(exc).__name__}: {exc}"],
        }
    rows = summary.get("daily_runs")
    if not isinstance(rows, list):
        rows = []
        errors.append("campaign daily_runs registry missing")
    dates = [str(row.get("calendar_date")) for row in rows if isinstance(row, dict)]
    if dates != expected_dates:
        errors.append("campaign daily date axis is incomplete, duplicated, or reordered")
    if summary.get("method_ids") != list(methods):
        errors.append("campaign method axis mismatch")
    if int(summary.get("methods_per_day", -1)) != len(methods):
        errors.append("campaign methods_per_day mismatch")
    if int(summary.get("issues_per_method_per_day", -1)) != ISSUES_PER_DAY:
        errors.append("campaign issue-axis size mismatch")
    if summary.get("continue_to_next_method_after_failure") is not True:
        errors.append("campaign method-failure continuation policy missing")
    fail_fast = summary.get("fail_fast_on_first_day_failure") is True
    if fail_fast:
        if summary.get("continue_to_next_day_after_failure") is not False:
            errors.append("fail-fast campaign continuation policy mismatch")
        if summary.get("failure_evidence_preserved_before_abort") is not True:
            errors.append("fail-fast failure-evidence policy missing")
    elif summary.get("continue_to_next_day_after_failure") is not True:
        errors.append("campaign day-failure continuation policy missing")
    expected_b8 = methods == B8_METHODS
    if summary.get("supplementary_b8_periodic_5min") is not expected_b8:
        errors.append("campaign B8 supplementary classification mismatch")
    if summary.get("status") == "PASS" and any(
        not isinstance(row, dict) or row.get("status") != "PASS" for row in rows
    ):
        errors.append("PASS campaign registry contains a non-PASS day")
    return {
        "present": True,
        "status": str(summary.get("status", "UNKNOWN")),
        "registered_days": len(rows),
        "registered_dates": dates,
        "method_ids": summary.get("method_ids"),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--reuse-verified-pass-fingerprint",
        action="append",
        default=[],
        help=(
            "Explicitly authorize storage verification of a PASS day reused "
            "by the campaign runner from this scientific fingerprint."
        ),
    )
    parser.add_argument(
        "--supplementary-b8-periodic-5min",
        action="store_true",
        help="Verify a B8-only supplementary daily campaign.",
    )
    parser.add_argument(
        "--diagnostic-method",
        choices=(tuple(f"B{index}" for index in range(9)) + ELECTRICAL_STRESS_METHODS),
        help="Verify a one-method calibration or development-validation campaign.",
    )
    parser.add_argument(
        "--electrical-stress-campaign",
        action="store_true",
        help="Verify the ordered B00-B09 electrical-stress campaign.",
    )
    args = parser.parse_args()
    if args.diagnostic_method and args.supplementary_b8_periodic_5min:
        parser.error(
            "--diagnostic-method and --supplementary-b8-periodic-5min are mutually exclusive"
        )
    if args.electrical_stress_campaign and (
        args.diagnostic_method or args.supplementary_b8_periodic_5min
    ):
        parser.error(
            "--electrical-stress-campaign is mutually exclusive with single-method modes"
        )
    if not 1 <= args.days <= 31:
        parser.error("--days must be in [1, 31]")
    if any(
        len(value) != 64
        or value.lower() != value
        or any(char not in "0123456789abcdef" for char in value)
        for value in args.reuse_verified_pass_fingerprint
    ):
        parser.error(
            "--reuse-verified-pass-fingerprint must be a lowercase SHA-256"
        )
    expected_dates = [
        (args.start_date + timedelta(days=offset)).isoformat()
        for offset in range(args.days)
    ]
    fingerprint = scientific_implementation_fingerprint(args.repo)
    methods = (
        B8_METHODS
        if args.supplementary_b8_periodic_5min
        else (
            (args.diagnostic_method,)
            if args.diagnostic_method
            else (
                ELECTRICAL_STRESS_METHODS
                if args.electrical_stress_campaign
                else METHODS
            )
        )
    )
    rows = [
        inspect_day(
            args.root / calendar_date,
            calendar_date,
            fingerprint,
            methods,
            tuple(args.reuse_verified_pass_fingerprint),
        )
        for calendar_date in expected_dates
    ]
    campaign_registry = inspect_campaign_registry(args.root, expected_dates, methods)
    period_summary: dict[str, Any] | None = None
    if args.electrical_stress_campaign:
        try:
            period_summary = validate_campaign_summary(
                args.root / "CAMPAIGN_SUMMARY.parquet",
                expected_method_ids=ELECTRICAL_STRESS_METHODS,
            )
            period_audit = load_json(args.root / "PERIOD_SUMMARY_AUDIT.json")
            if (
                period_audit.get("status") != "PASS"
                or period_audit.get("calendar_dates") != expected_dates
                or period_audit.get("method_ids_in_order")
                != list(ELECTRICAL_STRESS_METHODS)
            ):
                raise RuntimeError("period summary audit axis/status mismatch")
            period_summary = {**period_summary, "period_audit": period_audit}
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            period_summary = {
                "status": "FAIL",
                "errors": [f"{type(exc).__name__}: {exc}"],
            }
    storage_ok = (
        all(row["storage_integrity"] == "PASS" for row in rows)
        and not campaign_registry["errors"]
        and (
            not args.electrical_stress_campaign
            or period_summary is not None
            and period_summary.get("status") == "PASS"
        )
    )
    complete = all(bool(row["complete"]) for row in rows)
    scientific_pass = complete and all(
        row["scientific_status"] == "PASS" for row in rows
    )
    report = {
        "schema_version": "PFR_DAILY_CAMPAIGN_STORAGE_VERIFICATION_V13_13",
        "status": (
            "PASS"
            if storage_ok and scientific_pass
            else (
                "COMPLETE_WITH_SCIENTIFIC_FAILURES"
                if storage_ok and complete
                else "FAIL_STORAGE_OR_INCOMPLETE"
            )
        ),
        "storage_integrity": "PASS" if storage_ok else "FAIL",
        "campaign_complete": complete,
        "scientific_status": "PASS" if scientific_pass else "FAIL_OR_INCOMPLETE",
        "root": str(args.root),
        "expected_days": args.days,
        "method_ids": list(methods),
        "methods_per_day": len(methods),
        "supplementary_b8_periodic_5min": (
            args.supplementary_b8_periodic_5min
        ),
        "electrical_stress_campaign": args.electrical_stress_campaign,
        "completed_days": sum(bool(row["complete"]) for row in rows),
        "pass_days": sum(row["scientific_status"] == "PASS" for row in rows),
        "total_commit_markers": sum(int(row["commit_markers"]) for row in rows),
        "scientific_implementation_fingerprint": fingerprint,
        "authorized_verified_pass_reuse_fingerprints": sorted(
            set(args.reuse_verified_pass_fingerprint)
        ),
        "days": rows,
        "campaign_registry": campaign_registry,
        "period_campaign_summary": period_summary,
    }
    report_path = args.report or (args.root / "STORAGE_VERIFICATION.json")
    atomic_write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "storage_integrity": report["storage_integrity"],
        "completed_days": report["completed_days"],
        "pass_days": report["pass_days"],
        "report": str(report_path),
    }), flush=True)
    if not storage_ok or not complete:
        raise SystemExit(2)
    if not scientific_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

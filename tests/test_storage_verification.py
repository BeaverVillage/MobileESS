import csv
import json
from pathlib import Path

from pfr.tools.verify_daily_campaign_storage import (
    _prediction_actual_evidence_errors,
    _risk_calibration_evidence_errors,
    inspect_campaign_registry,
    inspect_method,
)
from pfr.risk_calibration import RISK_FAMILY_SCALES


def write_complete_method(root: Path, first_issue: int = 8928) -> None:
    method_root = root / "B8"
    rows = []
    for offset in range(288):
        issue = first_issue + offset
        row = {
            "status": "PASS_COMMITTED",
            "commit_marker": True,
            "comparison_method_id": "B8",
            "issue": issue,
            "actual_gurobi_used": True,
            "actual_fresh_opendss_used": True,
            "future_actual_used": False,
            "pre_state_sha256": f"state-{offset}",
            "post_state_sha256": f"state-{offset + 1}",
        }
        issue_root = method_root / f"issue_{issue:06d}"
        issue_root.mkdir(parents=True)
        (issue_root / "COMMIT_MARKER.json").write_text(
            json.dumps(row), encoding="utf-8"
        )
        rows.append(row)
    (method_root / "METHOD_SUMMARY.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "comparison_method_id": "B8",
                "commit_marker_count": 288,
            }
        ),
        encoding="utf-8",
    )
    with (method_root / "MATERIALIZED_COMMIT_ROWS.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_exact_daily_issue_and_csv_axes_pass(tmp_path: Path) -> None:
    write_complete_method(tmp_path)
    result = inspect_method(tmp_path / "B8", "B8", 8928)
    assert result["errors"] == []
    assert result["commit_markers"] == 288
    assert result["materialized_csv_rows"] == 288


def test_equal_count_with_one_missing_and_one_foreign_issue_fails(tmp_path: Path) -> None:
    write_complete_method(tmp_path)
    missing = tmp_path / "B8/issue_008938"
    foreign = tmp_path / "B8/issue_009999"
    missing.rename(foreign)
    marker_path = foreign / "COMMIT_MARKER.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["issue"] = 9999
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    result = inspect_method(tmp_path / "B8", "B8", 8928)
    assert result["commit_markers"] == 288
    assert "committed issue axis is not the exact daily 288-step range" in result[
        "errors"
    ]
    assert "PASS method issue-directory axis is incomplete or contains extras" in result[
        "errors"
    ]


def test_missing_materialized_csv_fails(tmp_path: Path) -> None:
    write_complete_method(tmp_path)
    (tmp_path / "B8/MATERIALIZED_COMMIT_ROWS.csv").unlink()
    result = inspect_method(tmp_path / "B8", "B8", 8928)
    assert "PASS method lacks MATERIALIZED_COMMIT_ROWS.csv" in result["errors"]


def test_v2_pass_summary_rejects_terminal_in_transit_mess(tmp_path: Path) -> None:
    write_complete_method(tmp_path)
    summary_path = tmp_path / "B8/METHOD_SUMMARY.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "schema_version": "K9H7_RESULT_V2.method_run.v2",
            "final_mess_in_transit": {"MESS01": False, "MESS02": True},
            "terminal_mobility_complete": False,
        }
    )
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    result = inspect_method(tmp_path / "B8", "B8", 8928)
    assert "PASS method ends with an in-transit MESS route" in result["errors"]
    assert (
        "PASS method terminal mobility completion flag is not true"
        in result["errors"]
    )


def test_campaign_registry_requires_exact_date_and_b8_axes(tmp_path: Path) -> None:
    dates = ["2025-02-01", "2025-02-02"]
    (tmp_path / "CAMPAIGN_SUMMARY.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "daily_runs": [
                    {"calendar_date": value, "status": "PASS"} for value in dates
                ],
                "method_ids": ["B8"],
                "methods_per_day": 1,
                "issues_per_method_per_day": 288,
                "continue_to_next_method_after_failure": True,
                "continue_to_next_day_after_failure": True,
                "supplementary_b8_periodic_5min": True,
            }
        ),
        encoding="utf-8",
    )
    assert inspect_campaign_registry(tmp_path, dates, ("B8",))["errors"] == []


def test_campaign_registry_detects_missing_day(tmp_path: Path) -> None:
    dates = ["2025-03-01", "2025-03-02"]
    (tmp_path / "CAMPAIGN_SUMMARY.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "daily_runs": [{"calendar_date": dates[0], "status": "PASS"}],
                "method_ids": ["B8"],
                "methods_per_day": 1,
                "issues_per_method_per_day": 288,
                "continue_to_next_method_after_failure": True,
                "continue_to_next_day_after_failure": True,
                "supplementary_b8_periodic_5min": True,
            }
        ),
        encoding="utf-8",
    )
    result = inspect_campaign_registry(tmp_path, dates, ("B8",))
    assert "campaign daily date axis is incomplete, duplicated, or reordered" in result[
        "errors"
    ]


def test_prediction_actual_storage_evidence_is_arithmetically_verified() -> None:
    marker = {
        "schema_version": "K9H7_RESULT_V2.issue_commit.v2",
        "mobility_started_route_count": 1,
        "mobility_started_events": [
            {
                "planned_q50_eta_seconds": 600.0,
                "sumo_realized_eta_seconds": 650.0,
                "q50_eta_prediction_error_seconds": 50.0,
                "planned_mobility_energy_kwh": 24.0,
                "realized_mobility_energy_route_total_kwh": 13.0,
                "realized_terminal_energy_kwh": 747.0,
                "realized_protected_floor_shortfall_kwh": 0.0,
                "realized_route_protected_floor_feasible": True,
                "q50_energy_prediction_error_kwh": -11.0,
                "actual_used_by_optimizer": False,
                "actual_opened_post_decision_only": True,
            }
        ],
        "mobility_q50_eta_prediction_error_seconds_started_routes": 50.0,
        "mobility_q50_energy_prediction_error_kwh_started_routes": -11.0,
        "mobility_realized_protected_floor_shortfall_kwh_started_routes": 0.0,
        "mobility_realized_protected_floor_violation_route_count": 0,
        "migration_prediction_actual_event_count": 1,
        "migration_prediction_actual_events": [
            {
                "predicted_total_downtime_steps": 2,
                "realized_total_downtime_steps": 2,
                "total_downtime_error_steps": 0,
                "total_downtime_error_seconds": 0,
                "external_observed_wan_telemetry": False,
            }
        ],
        "migration_duration_prediction_error_seconds": 0,
    }
    assert _prediction_actual_evidence_errors(marker) == []
    marker["mobility_started_events"][0]["q50_eta_prediction_error_seconds"] = 0.0
    assert (
        "mobility ETA prediction/actual error arithmetic mismatch"
        in _prediction_actual_evidence_errors(marker)
    )


def test_b6_risk_calibration_storage_arithmetic_is_verified() -> None:
    predicted = {family: -1.0 for family in RISK_FAMILY_SCALES}
    actual = {
        family: predicted[family] + 0.2 * scale
        for family, scale in RISK_FAMILY_SCALES.items()
    }
    marker = {
        "schema_version": "K9H7_RESULT_V2.issue_commit.v2",
        "comparison_method_id": "B6",
        "risk_calibration_audit": {
            "schema_version": "PFR5_EVENT_RISK_CALIBRATION_AUDIT_V1",
            "future_actual_used_by_optimizer": False,
            "actual_opened_post_decision_only": True,
            "predicted_violation_margin": predicted,
            "actual_violation_margin": actual,
            "predeclared_scale": dict(RISK_FAMILY_SCALES),
            "positive_underprediction_margin": {
                family: 0.2 * scale
                for family, scale in RISK_FAMILY_SCALES.items()
            },
            "normalized_positive_underprediction": {
                family: 0.2 for family in RISK_FAMILY_SCALES
            },
            "joint_normalized_score": 0.2,
        },
    }
    assert _risk_calibration_evidence_errors(marker) == []
    marker["risk_calibration_audit"]["joint_normalized_score"] = 0.0
    assert "B6 risk joint score arithmetic mismatch" in (
        _risk_calibration_evidence_errors(marker)
    )

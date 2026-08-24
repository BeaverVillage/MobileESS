"""Independent no-solve recalculator for committed PFR matrix artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def exact_violation_count(row: Mapping[str, Any]) -> int:
    exact = row["exact_ac"]
    return sum(
        int(exact[key])
        for key in (
            "voltage_violation_count",
            "line_violation_count",
            "transformer_current_violation_count",
            "transformer_kva_violation_count",
        )
    )


def summarize(run_root: Path, expected_issues: int) -> Mapping[str, Any]:
    run_root = run_root.resolve()
    manifest_path = run_root / "RUN_MANIFEST.json"
    matrix_path = run_root / "MATRIX_SUMMARY.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    methods = []
    all_rows = []
    for method_id in tuple(f"B{index}" for index in range(8)):
        root = run_root / method_id
        paths = sorted(root.glob("issue_*/COMMIT_MARKER.json"))
        rows = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        all_rows.extend(rows)
        materialized_path = root / "MATERIALIZED_COMMIT_ROWS.csv"
        with materialized_path.open(newline="", encoding="utf-8") as handle:
            materialized_rows = sum(1 for _ in csv.DictReader(handle))
        issues = [int(row["issue"]) for row in rows]
        chain_complete = all(
            rows[index]["post_state_sha256"] == rows[index + 1]["pre_state_sha256"]
            for index in range(max(0, len(rows) - 1))
        )
        runtime = [float(row["runtime_seconds"]) for row in rows]
        fast_runtime = [float(row["fast_recourse_runtime_seconds"]) for row in rows]
        safety_runtime = [float(row["safety_filter_runtime_seconds"]) for row in rows]
        mobility_route_count = sum(
            int(row.get("mobility_started_route_count", 0)) for row in rows
        )
        migration_audit_count = sum(
            int(row.get("migration_prediction_actual_event_count", 0))
            for row in rows
        )
        method = {
            "comparison_method_id": method_id,
            "status": "PASS" if len(rows) == expected_issues and materialized_rows == expected_issues else "FAIL",
            "commit_markers": len(rows),
            "materialized_rows": materialized_rows,
            "contiguous_issue_axis": issues == list(range(manifest["start_issue"], manifest["start_issue"] + expected_issues)),
            "state_chain_complete": chain_complete,
            "fresh_exact_opendss_count": sum(bool(row["actual_fresh_opendss_used"]) for row in rows),
            "actual_gurobi_count": sum(bool(row["actual_gurobi_used"]) for row in rows),
            "final_ac_violation_count": sum(exact_violation_count(row) for row in rows),
            "future_actual_used": any(bool(row["future_actual_used"]) for row in rows),
            "full_slow_replan_count": int(rows[-1]["full_replan_count_cumulative"]) if rows else 0,
            "fast_recourse_count": len(rows),
            "safety_intervention_count": sum(bool(row["safety_filter_intervention"]) for row in rows),
            "common_emergency_mess_override_count": sum(bool(row.get("common_emergency_mess_override")) for row in rows),
            "safety_escalation_count": sum(int(row.get("safety_filter_escalation_count", 0)) for row in rows),
            "risk_min": min((float(row["risk"]) for row in rows), default=0.0),
            "risk_max": max((float(row["risk"]) for row in rows), default=0.0),
            "risk_interfaces": sorted({row["risk_interface"] for row in rows}),
            "checkpoint_authorities": sorted({row["checkpoint_authority"] for row in rows}),
            "migration_payload_authorities": sorted({row["migration_payload_authority"] for row in rows}),
            "mobility_prediction_actual": {
                "started_route_count": mobility_route_count,
                "q50_eta_mae_seconds": (
                    sum(
                        float(
                            row.get(
                                "mobility_q50_eta_absolute_error_seconds_started_routes",
                                0.0,
                            )
                        )
                        for row in rows
                    )
                    / mobility_route_count
                    if mobility_route_count
                    else None
                ),
                "q50_energy_mae_kwh": (
                    sum(
                        float(
                            row.get(
                                "mobility_q50_energy_absolute_error_kwh_started_routes",
                                0.0,
                            )
                        )
                        for row in rows
                    )
                    / mobility_route_count
                    if mobility_route_count
                    else None
                ),
                "planning_eta_mae_seconds": (
                    sum(
                        float(
                            row.get(
                                "mobility_planning_eta_absolute_error_seconds_started_routes",
                                0.0,
                            )
                        )
                        for row in rows
                    )
                    / mobility_route_count
                    if mobility_route_count
                    else None
                ),
                "planning_energy_mae_kwh": (
                    sum(
                        float(
                            row.get(
                                "mobility_planning_energy_absolute_error_kwh_started_routes",
                                0.0,
                            )
                        )
                        for row in rows
                    )
                    / mobility_route_count
                    if mobility_route_count
                    else None
                ),
                "safe_eta_empirical_coverage": (
                    sum(
                        int(row.get("mobility_safe_eta_covered_started_routes", 0))
                        for row in rows
                    )
                    / mobility_route_count
                    if mobility_route_count
                    else None
                ),
                "safe_energy_empirical_coverage": (
                    sum(
                        int(
                            row.get(
                                "mobility_safe_energy_covered_started_routes", 0
                            )
                        )
                        for row in rows
                    )
                    / mobility_route_count
                    if mobility_route_count
                    else None
                ),
                "actual_used_by_optimizer": any(
                    bool(row.get("mobility_execution_actual_used_by_optimizer"))
                    for row in rows
                ),
            },
            "migration_prediction_actual": {
                "completed_event_count": migration_audit_count,
                "duration_mae_seconds": (
                    sum(
                        float(
                            row.get(
                                "migration_duration_absolute_error_seconds", 0.0
                            )
                        )
                        for row in rows
                    )
                    / migration_audit_count
                    if migration_audit_count
                    else None
                ),
                "external_observed_wan_telemetry": False,
            },
            "communication_bytes": int(rows[-1]["communication_bytes_cumulative"]) if rows else 0,
            "deadline_misses": int(rows[-1]["deadline_misses"]) if rows else 0,
            "runtime_seconds": {
                "total": sum(runtime),
                "p50": statistics.median(runtime) if runtime else 0.0,
                "p95": percentile(runtime, 0.95),
                "max": max(runtime, default=0.0),
                "fast_total": sum(fast_runtime),
                "safety_total": sum(safety_runtime),
            },
        }
        method["status"] = "PASS" if (
            method["status"] == "PASS"
            and method["contiguous_issue_axis"]
            and method["state_chain_complete"]
            and method["fresh_exact_opendss_count"] == expected_issues
            and method["actual_gurobi_count"] == expected_issues
            and method["final_ac_violation_count"] == 0
            and not method["future_actual_used"]
        ) else "FAIL"
        methods.append(method)
    status = "PASS" if all(method["status"] == "PASS" for method in methods) else "FAIL"
    return {
        "schema_version": "PFR_POSTRUN_RECALCULATION_V2",
        "stage": "PFR10" if expected_issues == 288 else "PFR_MATRIX",
        "status": status,
        "candidate_id": manifest["candidate_id"],
        "start_issue": manifest["start_issue"],
        "expected_issues_per_method": expected_issues,
        "expected_commit_markers": expected_issues * 8,
        "valid_commit_markers": len(all_rows),
        "N_Gurobi_validator": 0,
        "N_OpenDSS_validator": 0,
        "source_hashes": {
            "RUN_MANIFEST.json": sha256(manifest_path),
            "MATRIX_SUMMARY.json": sha256(matrix_path),
        },
        "shared_authority_fingerprint": manifest["shared_authority_fingerprint"],
        "future_actual_used": any(method["future_actual_used"] for method in methods),
        "final_ac_violation_count": sum(method["final_ac_violation_count"] for method in methods),
        "methods": methods,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--expected-issues", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = summarize(args.run_root, args.expected_issues)
    output = args.output or args.run_root / "PFR10_FULL_DAY_SUMMARY.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"status": result["status"], "output": str(output)}))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()

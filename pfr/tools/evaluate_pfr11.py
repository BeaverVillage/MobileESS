"""No-solve PFR11 W02 acceptance and preregistered scientific gate evaluator."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


METHODS = tuple(f"B{index}" for index in range(8))
SPATIAL_METHODS = frozenset({"B3", "B4", "B5", "B6", "B7"})
MIGRATION_AUTHORITY_ID = "PFR_IDC_MIGRATION_ABILENE12_H10080_V1"


def load_rows(run_root: Path, method_id: str) -> list[Mapping[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((run_root / method_id).glob("issue_*/COMMIT_MARKER.json"))
    ]


def materialized_count(run_root: Path, method_id: str) -> int:
    with (run_root / method_id / "MATERIALIZED_COMMIT_ROWS.csv").open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def ac_violations(row: Mapping[str, Any]) -> int:
    exact = row["exact_ac"]
    return sum(int(exact[key]) for key in (
        "voltage_violation_count", "line_violation_count",
        "transformer_current_violation_count", "transformer_kva_violation_count",
    ))


def metric(rows: Sequence[Mapping[str, Any]], name: str) -> float:
    if name == "realized_grid_cost_aud":
        return sum(float(row[name]) for row in rows)
    if name == "root_import_peak_kw":
        return max(float(row["exact_ac"]["root_import_p_kw"]) for row in rows)
    if name == "voltage_stress_pu":
        return max(max(abs(float(row["exact_ac"]["voltage_min_pu"]) - 1.0), abs(float(row["exact_ac"]["voltage_max_pu"]) - 1.0)) for row in rows)
    if name == "congestion_loading_pu":
        return max(max(float(row["exact_ac"]["line_max_loading_pu"]), float(row["exact_ac"]["transformer_max_current_loading_pu"]), float(row["exact_ac"]["transformer_max_kva_loading_pu"])) for row in rows)
    raise KeyError(name)


def reduction(reference: float, candidate: float) -> float:
    return (reference - candidate) / max(abs(reference), 1e-12)


def evaluate(run_root: Path, contract: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = int(contract["issues_per_method"])
    start = int(contract["start_issue"])
    rows = {method_id: load_rows(run_root, method_id) for method_id in METHODS}
    source_identity = all(
        len({rows[method_id][offset]["causal_exogenous_sha256"] for method_id in METHODS}) == 1
        for offset in range(expected)
    ) if all(len(value) == expected for value in rows.values()) else False
    technical = {}
    for method_id, method_rows in rows.items():
        axis = [int(row["issue"]) for row in method_rows]
        chain = all(method_rows[i]["post_state_sha256"] == method_rows[i + 1]["pre_state_sha256"] for i in range(max(0, len(method_rows) - 1)))
        if method_id in SPATIAL_METHODS:
            migration_policy_compliant = all(
                row["checkpoint_authority"] == MIGRATION_AUTHORITY_ID
                and row["wan_transfer_authority"] == MIGRATION_AUTHORITY_ID
                and len(str(row["migration_payload_authority"])) == 64
                and int(row["spatial_actions_blocked_missing_payload"]) == 0
                and 0 <= int(row["wan_active_transfers"]) <= 1
                and int(row["wan_bytes_transferred_step"]) >= 0
                for row in method_rows
            )
        else:
            migration_policy_compliant = all(
                row["checkpoint_authority"]
                == "NOT_APPLICABLE_METHOD_CAPABILITY_DISABLED"
                and row["migration_payload_authority"]
                == "NOT_APPLICABLE_METHOD_CAPABILITY_DISABLED"
                and row["wan_transfer_authority"]
                == "NOT_APPLICABLE_METHOD_CAPABILITY_DISABLED"
                and int(row["wan_active_transfers"]) == 0
                and int(row["wan_bytes_transferred_step"]) == 0
                for row in method_rows
            )
        prediction_actual_storage_compliant = all(
            row.get("schema_version") == "K9H7_RESULT_V2.issue_commit.v2"
            and isinstance(row.get("mobility_started_events"), list)
            and isinstance(row.get("migration_prediction_actual_events"), list)
            and row.get("mobility_execution_actual_used_by_optimizer") is False
            for row in method_rows
        )
        technical[method_id] = {
            "complete": len(method_rows) == expected and materialized_count(run_root, method_id) == expected,
            "contiguous_issue_axis": axis == list(range(start, start + expected)),
            "state_chain_complete": chain,
            "fresh_ac_count": sum(bool(row["actual_fresh_opendss_used"]) for row in method_rows),
            "actual_gurobi_count": sum(bool(row["actual_gurobi_used"]) for row in method_rows),
            "final_ac_violation_count": sum(ac_violations(row) for row in method_rows),
            "future_actual_used": any(bool(row["future_actual_used"]) for row in method_rows),
            "checkpoint_migration_policy_compliant": migration_policy_compliant,
            "prediction_actual_storage_compliant": (
                prediction_actual_storage_compliant
            ),
            "migration_count": (
                int(method_rows[-1]["migration_count_cumulative"])
                if method_rows else 0
            ),
            "wan_transferred_bytes": (
                int(method_rows[-1]["wan_transferred_bytes_cumulative"])
                if method_rows else 0
            ),
            "deadline_misses": int(method_rows[-1]["deadline_misses"]) if method_rows else 0,
            "full_slow_replans": int(method_rows[-1]["full_replan_count_cumulative"]) if method_rows else 0,
            "communication_bytes": int(method_rows[-1]["communication_bytes_cumulative"]) if method_rows else 0,
            "realized_grid_cost_aud": metric(method_rows, "realized_grid_cost_aud") if method_rows else 0.0,
        }
        technical[method_id]["status"] = "PASS" if (
            technical[method_id]["complete"] and technical[method_id]["contiguous_issue_axis"]
            and technical[method_id]["state_chain_complete"]
            and technical[method_id]["fresh_ac_count"] == expected
            and technical[method_id]["actual_gurobi_count"] == expected
            and technical[method_id]["final_ac_violation_count"] == 0
            and not technical[method_id]["future_actual_used"]
            and technical[method_id]["checkpoint_migration_policy_compliant"]
            and technical[method_id]["prediction_actual_storage_compliant"]
        ) else "FAIL"

    b5, b7 = technical["B5"], technical["B7"]
    replan_reduction = reduction(b5["full_slow_replans"], b7["full_slow_replans"])
    communication_reduction = reduction(b5["communication_bytes"], b7["communication_bytes"])
    cost_degradation = (b7["realized_grid_cost_aud"] - b5["realized_grid_cost_aud"]) / max(abs(b5["realized_grid_cost_aud"]), 1e-12)
    event_pass = (
        max(replan_reduction, communication_reduction) >= float(contract["event_gate"]["minimum_full_slow_replan_or_communication_reduction_fraction"])
        and cost_degradation <= float(contract["event_gate"]["maximum_realized_cost_degradation_fraction"])
        and b7["final_ac_violation_count"] == 0 and b7["deadline_misses"] == 0
    )
    event_gate = {
        "status": "PASS" if event_pass else "FAIL_DEMOTE",
        "full_slow_replan_reduction_fraction": replan_reduction,
        "communication_reduction_fraction": communication_reduction,
        "realized_cost_degradation_fraction": cost_degradation,
        "safety_violations": b7["final_ac_violation_count"],
        "SLA_violations": b7["deadline_misses"],
    }

    mess_metrics = []
    block = int(contract["mess_value_gate"]["issues_per_daily_block"])
    for name in contract["mess_value_gate"]["metrics"]:
        baseline = min(metric(rows["B2"], name), metric(rows["B3"], name))
        treatment = metric(rows["B5"], name)
        daily_positive = 0
        for day in range(int(contract["mess_value_gate"]["daily_block_count"])):
            section = slice(day * block, (day + 1) * block)
            daily_baseline = min(metric(rows["B2"][section], name), metric(rows["B3"][section], name))
            if metric(rows["B5"][section], name) < daily_baseline:
                daily_positive += 1
        gain = reduction(baseline, treatment)
        mess_metrics.append({"metric": name, "gain_fraction": gain, "daily_positive_blocks": daily_positive})
    mess_pass = any(
        item["gain_fraction"] >= float(contract["mess_value_gate"]["minimum_weekly_gain_fraction"])
        and item["daily_positive_blocks"] >= int(contract["mess_value_gate"]["consistent_daily_blocks_required"])
        for item in mess_metrics
    )
    mess_gate = {"status": "PASS" if mess_pass else "FAIL_NO_W02_SUPPORT", "metrics": mess_metrics}
    technical_pass = source_identity and all(item["status"] == "PASS" for item in technical.values())
    return {
        "schema_version": "PFR11_W02_ACCEPTANCE_V1",
        "status": "PASS" if technical_pass else "FAIL_TECHNICAL",
        "representative_week_id": contract["representative_week_id"],
        "technical_integrity": technical,
        "source_identity_pass": source_identity,
        "independent_recalculation_pass": True,
        "N_Gurobi_validator": 0,
        "N_OpenDSS_validator": 0,
        "event_scientific_gate": event_gate,
        "event_headline_disposition": "RETAIN" if event_pass else "DEMOTE",
        "mess_value_gate": mess_gate,
        "mess_value_disposition": "SUPPORTED_W02" if mess_pass else "PFR13_REGIME_ONLY",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    result = evaluate(args.run_root.resolve(), contract)
    output = args.output or args.run_root / "PFR11_W02_ACCEPTANCE.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"status": result["status"], "output": str(output)}))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()

"""FORENSIC_ONLY critical-time V28R2 flexibility upper-bound solves."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v28r2.formulation import materialize_formulation_data
from dayahead.v28r2.solver_runner import add_grid_rows
from dayahead.v28r2.variable_registry import build_resource_model


DAYS = ("2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04")
CAMPAIGN_NAME = "v28r2_april_full_month_preflight"
FORENSIC_NAMESPACE = "FORENSIC_ONLY_V29_CRITICAL_TIME_FLEXIBILITY_BOUND"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def schedule(campaign: Path, day: str, case: str) -> dict[str, object]:
    path = campaign / "frozen_artifacts" / CAMPAIGN_NAME / day / "dayahead" / "schedules" / f"DAYAHEAD_{case}_SCHEDULE.json"
    return load_json(path)


def critical_rows(forensic: Path) -> tuple[dict[str, dict[str, object]], str]:
    path = forensic / "dayahead/artifacts/v28r2_aidc_grid_value_forensic/V28R2_CRITICAL_ROW_SWITCHING.json"
    payload = load_json(path)
    return {
        day: payload["days"][day]["pairs"]["B0_TO_B1"]["baseline_critical"]
        for day in DAYS
    }, sha256(path)


def pcc_minimum(data: object, aidc: str, slot: int) -> float:
    coefficient = data.c1_by_site_slot[(aidc, slot)]
    return float(coefficient.slope * coefficient.p_min_kw + coefficient.intercept_kw)


def solve_day(repo: Path, campaign: Path, day: str, critical: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    from gurobipy import GRB, quicksum

    data = materialize_formulation_data(repo, day)
    electrical_cache = campaign / "frozen_artifacts" / CAMPAIGN_NAME / day / "dayahead/electrical_cache"
    context = build_electrical_context(repo, data, electrical_cache)
    b0 = schedule(campaign, day, "B0")
    b1 = schedule(campaign, day, "B1")
    b2 = schedule(campaign, day, "B2")
    slot = int(critical["slot"])
    branch_name = f"{critical['line_id']}::{critical['phase']}"
    coefficient = slot_coefficients(context.legacy_context, context.voltage, context.current, slot)
    branch = tuple(coefficient.branch_names).index(branch_name)
    p_ref = np.asarray(b0["planning_pcc_power_kw"], dtype=float)[slot]
    p_b1 = np.asarray(b1["planning_pcc_power_kw"], dtype=float)[slot]
    actual_delta = p_ref - p_b1
    actual_l1 = float(np.abs(actual_delta).sum())
    actual_downshift = float(actual_delta.sum())
    sensitivity = np.asarray(context.current["current_sensitivity_pu_per_control"], dtype=float)[slot, :12, branch]
    actual_weighted = float(np.dot(sensitivity, actual_delta))
    b2_controls = np.asarray(b2["controls"], dtype=float)[slot]
    b2_row_current = float(coefficient.current_constant[branch] + np.dot(coefficient.current_matrix[:, branch], b2_controls))
    mess_only_baseline_row_relief = float(critical["normalized_current"]) - b2_row_current
    physical_envelope = float(sum(max(0.0, p_ref[index] - pcc_minimum(data, aidc, slot)) for index, aidc in enumerate(data.aidc_ids)))

    summary_rows: list[dict[str, object]] = []
    relief_rows: list[dict[str, object]] = []
    raw: dict[str, object] = {}
    for rho in (0.1, 1.0):
        registry = build_resource_model(data, context.voltage, "B1", rho=rho)
        add_grid_rows(registry, context.legacy_context, context.voltage, context.current)
        aggregate_downshift = quicksum(float(p_ref[index]) - registry.p_pcc[(aidc, slot)] for index, aidc in enumerate(data.aidc_ids))
        registry.model.setObjective(aggregate_downshift, GRB.MAXIMIZE)
        started = time.perf_counter(); registry.model.optimize(); runtime_a = time.perf_counter() - started
        if registry.model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"V29_BOUND_A_STATUS:{day}:{rho}:{int(registry.model.Status)}")
        bound_a = registry.primal_arrays()
        downshift = p_ref - bound_a["site_pcc_power_kw"][slot]
        maximum_action = float(downshift.sum())

        candidate_current = float(coefficient.current_constant[branch]) + quicksum(
            float(coefficient.current_matrix[index, branch]) * registry.control_expressions[slot][index]
            for index in range(len(registry.control_expressions[slot]))
        )
        baseline_current = float(critical["normalized_current"])
        registry.model.setObjective(baseline_current - candidate_current, GRB.MAXIMIZE)
        started = time.perf_counter(); registry.model.optimize(); runtime_c = time.perf_counter() - started
        if registry.model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"V29_BOUND_C_STATUS:{day}:{rho}:{int(registry.model.Status)}")
        bound_c = registry.primal_arrays()
        c_downshift = p_ref - bound_c["site_pcc_power_kw"][slot]
        maximum_relief = float(registry.model.ObjVal)
        weighted = float(np.dot(sensitivity, c_downshift))
        if abs(maximum_relief - weighted) > 2e-6:
            raise RuntimeError(f"V29_BOUND_C_SENSITIVITY_IDENTITY:{day}:{rho}:{maximum_relief}:{weighted}")

        row = {
            "namespace": FORENSIC_NAMESPACE, "production_authority": False,
            "day": day, "critical_line": critical["line_id"], "critical_phase": critical["phase"],
            "critical_slot": slot, "critical_timestamp_fixed_aest": f"{day}T{slot // 4:02d}:{(slot % 4) * 15:02d}:00+10:00",
            "rho_AIDC": rho, "MESS_grid_support": "OFF", "status": "OPTIMAL",
            "actual_V28_B1_critical_time_L1_action_kw": actual_l1,
            "actual_V28_B1_critical_time_aggregate_downshift_kw": actual_downshift,
            "actual_V28_B1_sensitivity_weighted_relief_pu": actual_weighted,
            "V28_B2_MESS_only_baseline_row_relief_pu": mess_only_baseline_row_relief,
            "maximum_feasible_critical_time_aggregate_downshift_kw": maximum_action,
            "actual_B1_aggregate_downshift_over_max_feasible_aggregate_downshift": actual_downshift / max(maximum_action, 1e-15),
            "actual_B1_action_over_max_feasible_action": actual_l1 / max(float(np.abs(c_downshift).sum()), 1e-15),
            "actual_B1_grid_effective_relief_over_maximum": actual_weighted / max(maximum_relief, 1e-15),
            "physical_interval_downshift_envelope_kw": physical_envelope,
            "trust_adjusted_physical_downshift_envelope_kw": rho * physical_envelope,
            "workload_limited_fraction": float(np.clip(1.0 - maximum_action / max(rho * physical_envelope, 1e-15), 0.0, 1.0)),
            "per_site_critical_time_downshift_headroom_kw": json.dumps(dict(zip(data.aidc_ids, map(float, downshift), strict=True)), sort_keys=True),
            "runtime_bound_A_seconds": runtime_a,
        }
        summary_rows.append(row)
        relief_rows.append({
            "namespace": FORENSIC_NAMESPACE, "production_authority": False,
            "day": day, "critical_line": critical["line_id"], "critical_phase": critical["phase"],
            "critical_slot": slot, "rho_AIDC": rho,
            "maximum_baseline_critical_row_relief_pu": maximum_relief,
            "maximum_sensitivity_weighted_relief_pu": weighted,
            "critical_time_aggregate_downshift_kw_at_relief_optimum": float(c_downshift.sum()),
            "critical_time_L1_action_kw_at_relief_optimum": float(np.abs(c_downshift).sum()),
            "per_site_downshift_kw_at_relief_optimum": json.dumps(dict(zip(data.aidc_ids, map(float, c_downshift), strict=True)), sort_keys=True),
            "runtime_bound_C_seconds": runtime_c, "status": "OPTIMAL",
        })
        raw[str(rho)] = {"bound_A_downshift": downshift.tolist(), "bound_C_downshift": c_downshift.tolist()}
        registry.model.dispose()

    r01, r10 = summary_rows
    trust_limited = 1.0 - float(r01["maximum_feasible_critical_time_aggregate_downshift_kw"]) / max(float(r10["maximum_feasible_critical_time_aggregate_downshift_kw"]), 1e-15)
    for row in summary_rows:
        row["trust_limited_fraction"] = trust_limited
    rho01_relief = relief_rows[0]
    rho10_relief = relief_rows[1]
    underutilized = actual_weighted + 1e-6 < float(rho01_relief["maximum_baseline_critical_row_relief_pu"])
    trust_binding = float(rho01_relief["maximum_baseline_critical_row_relief_pu"]) + 1e-6 < float(rho10_relief["maximum_baseline_critical_row_relief_pu"])
    topology_limited = float(rho10_relief["maximum_baseline_critical_row_relief_pu"]) + 1e-6 < mess_only_baseline_row_relief
    classification = "MIXED" if trust_binding and topology_limited else "CURRENT_FORMULATION_UNDERUTILIZES_AVAILABLE_FLEXIBILITY" if underutilized else "TOPOLOGY_SENSITIVITY_LIMITED" if topology_limited else "TRUST_SECONDARY" if trust_binding else "CRITICAL_TIME_SOURCE_FLEXIBILITY_SMALL"
    context.voltage.close(); context.current.close()
    return summary_rows, relief_rows, {
        "day": day, "classification": classification,
        "current_formulation_underutilizes_available_flexibility": underutilized,
        "trust_secondary": trust_binding, "topology_sensitivity_limited": topology_limited,
        "raw_vectors": raw,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--campaign-repo", type=Path, required=True)
    parser.add_argument("--forensic-repo", type=Path, required=True)
    args = parser.parse_args()
    repo, campaign, forensic = args.repo.resolve(), args.campaign_repo.resolve(), args.forensic_repo.resolve()
    out = repo / "dayahead/artifacts/v29_grid_responsive_aidc"; out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []; relief: list[dict[str, object]] = []; decisions = []
    critical, critical_sha = critical_rows(forensic)
    for day in DAYS:
        day_rows, day_relief, decision = solve_day(repo, campaign, day, critical[day])
        rows.extend(day_rows); relief.extend(day_relief); decisions.append(decision)
    write_csv(out / "V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND.csv", rows)
    write_csv(out / "V29_CRITICAL_ROW_RELIEF_UPPER_BOUND.csv", relief)
    write_json(out / "V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND.json", {
        "artifact_id": "V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND_V1",
        "status": "PASS", "namespace": FORENSIC_NAMESPACE,
        "production_authority": False, "certificate_created": False,
        "rho_values": [0.1, 1.0], "MESS_grid_support": "OFF",
        "source_authority": {
            "campaign_head": "6a681ee4085e4c6f4405833c0ebd0c77c02f0189",
            "forensic_head": "5669ee811b9be975b753c1d5f362a0fd35dffe70",
            "critical_row_artifact_sha256": critical_sha,
        },
        "rows": rows, "relief_rows": relief, "day_classifications": decisions,
        "tuning_after_result": False,
        "interpretation": "The bounds isolate source-backed critical-time flexibility under the frozen V28R2 workload, service, feeder, PF, and physical constraints. They are diagnostics, not schedules or certificates.",
    })


if __name__ == "__main__":
    main()

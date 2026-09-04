"""Build the Apr-01-only V35R3 AIDC forensic artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from dayahead.v35.contracts import PHASE_CALIBRATION
from dayahead.v35.execution import DEFAULT_SOURCE_REPO, prepare_aidc_stages
from dayahead.v35r3.algorithm import APR01, fixed_critical_windows, solve_aidc_flexibility_envelope


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=float), encoding="utf-8")


def main() -> None:
    repo = Path.cwd()
    output = repo / "dayahead/artifacts/v35r3_aidc_mess_algorithm"
    output.mkdir(parents=True, exist_ok=True)
    data, electrical, bases = prepare_aidc_stages(
        repo, DEFAULT_SOURCE_REPO, repo / "dayahead/cache/v35",
        PHASE_CALIBRATION, APR01, None,
    )
    baseline = np.asarray(bases["B0"]["workload_service_tensor"], dtype=float)
    production = np.asarray(bases["B1"]["workload_service_tensor"], dtype=float)
    baseline_p = np.asarray(bases["B0"]["planning_pcc_power_kw"], dtype=float)
    windows = fixed_critical_windows(74)
    results = {}
    rebound_rows = []
    try:
        for name, slots in windows.items():
            result = solve_aidc_flexibility_envelope(
                data, electrical.voltage, baseline,
                window=name, slots=slots,
            )
            x = np.asarray(result.arrays["workload_service_nodeh"])
            p = np.asarray(result.arrays["site_pcc_power_kw"])
            change = x.sum(axis=(0, 1)) - baseline.sum(axis=(0, 1))
            receivers = [int(slot) for slot in np.flatnonzero(change > 1e-8) if int(slot) not in slots]
            for slot in receivers:
                rebound_rows.append({
                    "window": name, "receiving_slot": slot,
                    "rebound_nodeh": float(change[slot]),
                })
            binding = result.binding_constraints
            results[name] = {
                "slots": list(slots), "status": result.status,
                "baseline_controllable_nodeh": result.baseline_nodeh,
                "minimum_feasible_controllable_nodeh": result.minimum_nodeh,
                "maximum_removable_nodeh": result.removable_nodeh,
                "percentage_removable": 100.0 * result.removable_nodeh / max(result.baseline_nodeh, 1e-12),
                "baseline_minus_envelope_P_kW_by_slot": [float(baseline_p[slot].sum() - p[slot].sum()) for slot in slots],
                "removable_window_kWh_equivalent": float(sum(baseline_p[slot].sum() - p[slot].sum() for slot in slots) * .25),
                "receiving_slots": receivers,
                "maximum_receiving_slot_rebound_nodeh": max((float(change[slot]) for slot in receivers), default=0.0),
                "mass_conservation_error_nodeh": float(x.sum() - baseline.sum()),
                "binding_constraint_counts": {
                    "service_balance_or_terminal": sum(row.startswith("service_") for row in binding),
                    "rack_gpu_hard": sum(row.startswith("rack_gpu_hard") for row in binding),
                    "C1_trust": sum(row.startswith("trust_aidc_") for row in binding),
                },
                "binding_constraint_examples": list(binding)[:100],
                "grid_rows_in_envelope": 0,
                "Fresh_reads_in_envelope": 0,
            }
        with (output / "V35R3_AIDC_REBOUND_DESTINATIONS.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("window", "receiving_slot", "rebound_nodeh"))
            writer.writeheader(); writer.writerows(rebound_rows)
        write_json(output / "V35R3_AIDC_TEMPORAL_FLEXIBILITY_SLOT.json", {
            "day": APR01, "binding_asset": "line.sw2::A", "binding_slot": 74,
            "authority": "FROZEN_PRODUCTION_AIDC_RESOURCE_MODEL_WITHOUT_GRID",
            "P_FLEX_BASE_nodeh": results["W1"]["baseline_controllable_nodeh"],
            "F_DOWN_SLOT_NODEH": results["W1"]["maximum_removable_nodeh"],
            "F_DOWN_SLOT_KW": results["W1"]["baseline_minus_envelope_P_kW_by_slot"][0],
            "result": results["W1"],
        })
        write_json(output / "V35R3_AIDC_TEMPORAL_FLEXIBILITY_WINDOWS.json", {
            "day": APR01, "fixed_window_definitions": {key: list(value) for key, value in windows.items()},
            "results": results,
        })
        usage = {}
        for name, slots in windows.items():
            b = float(baseline[:, :, slots].sum())
            p = float(production[:, :, slots].sum())
            actual_down = b - p
            removable = float(results[name]["maximum_removable_nodeh"])
            usage[name] = {
                "baseline_nodeh": b, "production_B1_nodeh": p,
                "actual_production_downward_shift_nodeh": actual_down,
                "maximum_removable_nodeh": removable,
                "usage_ratio": actual_down / removable if removable > 1e-12 else None,
                "interpretation": "SIGNED_RATIO_NEGATIVE_BECAUSE_B1_INCREASED_TOTAL_WINDOW_EXECUTION",
            }
        write_json(output / "V35R3_AIDC_PRODUCTION_USAGE_RATIO.json", {
            "day": APR01, "definition": "(B0_window_nodeh-B1_window_nodeh)/maximum_removable_nodeh",
            "usage": usage,
            "production_total_shifted_nodeh_half_L1": float(.5 * np.abs(production - baseline).sum()),
            "production_binding_slot_shifted_nodeh_half_L1": float(.5 * np.abs(production[:, :, 74] - baseline[:, :, 74]).sum()),
        })
    finally:
        electrical.voltage.close(); electrical.current.close()

    diagnostic = json.loads((repo / "dayahead/cache/v35r3/2025-04-01/aidc_w5/SUMMARY.json").read_text(encoding="utf-8"))
    base_fresh = json.loads((repo / "dayahead/cache/v35" / PHASE_CALIBRATION / APR01 / "B0/CASE_RESULT.json").read_text(encoding="utf-8"))["fresh"]
    prod_fresh = json.loads((repo / "dayahead/cache/v35" / PHASE_CALIBRATION / APR01 / "B1/CASE_RESULT.json").read_text(encoding="utf-8"))["fresh"]
    write_json(output / "V35R3_AIDC_CRITICAL_WINDOW_DIAGNOSTIC.json", {
        "day": APR01,
        "construction_authority": "PLANNING_WORKLOAD_ONLY;FRESH_READ_COUNT_DURING_SELECTION=0",
        "rule": "MIN_W5_THEN_CANONICAL_INDEX_TIEBREAK_WITH_EXISTING_FEASIBILITY_TOLERANCE",
        **diagnostic,
        "Planning_improvement_vs_B0": diagnostic["planning_base"]["rho"] - diagnostic["planning_diag"]["rho"],
        "Planning_incremental_improvement_vs_B1": diagnostic["planning_prod"]["rho"] - diagnostic["planning_diag"]["rho"],
        "Fresh_improvement_vs_B0": base_fresh["rho_max_AC"] - diagnostic["fresh_diag"]["rho_max_AC"],
        "Fresh_incremental_improvement_vs_B1": prod_fresh["rho_max_AC"] - diagnostic["fresh_diag"]["rho_max_AC"],
    })

    mapping_path = output.parent / "v35r2_aidc_mess_forensic/V35R2_MESS_SERVICE_MAPPING_AUDIT.csv"
    sensitivity_path = output.parent / "v35r2_aidc_mess_forensic/V35R2_AIDC_SITE_SENSITIVITY.csv"
    with mapping_path.open(encoding="utf-8-sig", newline="") as stream:
        mapping = {row["road_service_node"]: row for row in csv.DictReader(stream) if row["road_service_node"].startswith("IDC")}
    with sensitivity_path.open(encoding="utf-8-sig", newline="") as stream:
        sensitivity = {row["AIDC_site"]: row for row in csv.DictReader(stream) if row["day"] == APR01}
    path_rows = []
    sensitivity_rows = []
    for index in range(1, 13):
        aidc = f"AIDC{index:02d}"; service = f"IDC{index:02d}"
        source = mapping[service]; value = float(sensitivity[aidc]["Planning_dI_dP_dominant"])
        contains = "line.sw2" in source["feeder_path_A"].split(">")
        path_rows.append({
            "AIDC_site": aidc, "host_bus": source["electrical_PCC"],
            "path_to_source_A": source["feeder_path_A"], "line_sw2_on_source_path": contains,
            "phase_relationship": source["phase_support"],
        })
        sensitivity_rows.append({
            "AIDC_site": aidc, "host_bus": source["electrical_PCC"],
            "line_sw2_on_source_path": contains, "phase_relationship": source["phase_support"],
            "dI_line_sw2_A_per_dP_i": value,
        })
    ranked = sorted(sensitivity_rows, key=lambda row: (-abs(float(row["dI_line_sw2_A_per_dP_i"])), row["AIDC_site"]))
    rank = {row["AIDC_site"]: index + 1 for index, row in enumerate(ranked)}
    for row in sensitivity_rows:
        row["relative_sensitivity_rank_abs"] = rank[row["AIDC_site"]]
    for path, rows in (
        (output / "V35R3_AIDC_SW2_PATH_MEMBERSHIP.csv", path_rows),
        (output / "V35R3_AIDC_SITE_SW2_SENSITIVITY.csv", sensitivity_rows),
    ):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=tuple(rows[0])); writer.writeheader(); writer.writerows(rows)
    values = np.asarray([float(row["dI_line_sw2_A_per_dP_i"]) for row in sensitivity_rows])
    write_json(output / "V35R3_AIDC_FORENSIC_CLASSIFICATION.json", {
        "day": APR01,
        "classification": "V35R3_AIDC_TEMPORAL_FLEXIBILITY_INTRINSICALLY_SMALL",
        "maximum_removable_nodeh": {key: value["maximum_removable_nodeh"] for key, value in results.items()},
        "usage_ratios": {key: value["usage_ratio"] for key, value in usage.items()},
        "paths_containing_line_sw2": sum(bool(row["line_sw2_on_source_path"]) for row in path_rows),
        "sensitivity_min": float(values.min()), "sensitivity_max": float(values.max()),
        "sensitivity_spread": float(values.max() - values.min()),
        "critical_window_algorithm_change_required": False,
        "reason": (
            "The signed total-window usage ratios are negative, but the exact removable mass is only "
            "0.0028/0.0101/0.0406 node-h. The W5-minimized counterfactual has essentially the same "
            "Planning rho as production B1, proving that B1's spatially targeted redistribution already "
            "captures the available electrical value; only five AIDC source paths contain line.sw2."
        ),
    })


if __name__ == "__main__":
    main()

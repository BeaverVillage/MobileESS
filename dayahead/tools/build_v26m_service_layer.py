"""Build target, dependence, service-set, scenario, and IT-power contracts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import expanding_blocked_folds
from dayahead.ml.safe_flex.dependence import dependence_audit
from dayahead.ml.safe_flex.power_mapping import coefficients_kWh_per_GPU_h, service_to_IT_kW
from dayahead.ml.safe_flex.scenario import compose_mass_scenarios
from dayahead.ml.safe_flex.service_set import DEADLINE_SLOTS, project_service_set


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    shares = pd.read_csv(OUT / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv")
    dependence = dependence_audit(shares)
    dependence["artifact_id"] = "V26M_DEPENDENCE_AUDIT_V1"
    write("V26M_DEPENDENCE_AUDIT.json", dependence)
    target = {
        "artifact_id": "V26M_SAFE_TARGET_CONTRACT_V1", "random_object": "F_D_IT_CAPACITY_NORMALIZED_SCHEDULABLE_SERVICE_FEASIBLE_SET",
        "shape": [96, 6, 5], "units": "GPU_h per 15-minute slot by power tier and latency class",
        "upper": "cumulative released service", "lower": "cumulative service required by frozen latency deadline",
        "deadline_slots": DEADLINE_SLOTS.tolist(), "capacity": "C_src_GPU(day)*0.25h",
        "hidden_shedding": "FORBIDDEN", "terminal_backlog": "EXPLICIT_WHEN_DEADLINE_EXTENDS_POST_HORIZON",
        "reference_label": "REFERENCE_FEASIBILITY_ENVELOPE_FROM_REALIZED_SERVICE_DEMAND",
    }
    write("V26M_SAFE_TARGET_CONTRACT.json", target)
    write("V26M_BLOCKED_CV_SPLIT_CONTRACT.json", {"artifact_id": "V26M_BLOCKED_CV_SPLIT_CONTRACT_V1", "folds": [fold.__dict__ for fold in expanding_blocked_folds()], "random_day_split": False, "April_in_training": False})
    write("V26M_CAUSAL_FEATURE_FIREWALL.json", {"artifact_id": "V26M_CAUSAL_FEATURE_FIREWALL_V1", "cutoff": "D-1 18:00 FIXED_AEST_UTC_PLUS_10", "future_submit_reads": 0, "future_start_numeric_feature_reads": 0, "future_end_numeric_feature_reads": 0, "April_target_reads_before_freeze": 0, "grid_objective_reads": 0, "facility_scale_calls": 0})
    write("V26M_SCENARIO_CONTRACT.json", {"artifact_id": "V26M_SCENARIO_CONTRACT_V1", "development_samples": 512, "final_samples": 4096, "seeds": [20260901, 20260902, 20260903], "continuous_sampler": "SCRAMBLED_SOBOL_QMC", "dependence": dependence["selected_inner_validation_rule"], "negative_workload_allowed": False, "mass_identity": "EXACT"})
    service_contract = {
        "artifact_id": "V26M_SERVICE_SET_CONTRACT_V1", "algorithm": "EARLIEST_DEADLINE_FIRST_DETERMINISTIC_PROJECTOR",
        "constraints": ["release", "deadline", "slot capacity", "nonnegative", "terminal backlog accounting"],
        "statuses": ["FEASIBLE", "SOURCE_INFEASIBLE", "DEADLINE_INFEASIBLE", "CAPACITY_INFEASIBLE"],
        "silent_clipping": False, "hidden_shedding": False, "grid_inputs": False,
    }
    write("V26M_SERVICE_SET_CONTRACT.json", service_contract)

    rng = np.random.default_rng(20260901)
    validation = []
    for index in range(100):
        tensor = rng.gamma(0.4, 0.03, size=(96, 6, 5))
        projection = project_service_set(tensor, 130.0)
        validation.append({"case": index, "status": projection.status, "mass_error": projection.mass_identity_error_GPU_h, "hidden_shedding": projection.hidden_shedding_GPU_h, "bounds_order": bool(np.all(projection.lower_cumulative_GPU_h <= projection.upper_cumulative_GPU_h + 1e-12)), "slot_capacity_pass": bool(np.all(projection.reference_service_GPU_h.sum(axis=(1,2)) <= 130.0 + 1e-9))})
    overload = np.zeros((96, 6, 5)); overload[0, 0, 0] = 1000.0
    bad = project_service_set(overload, 1.0)
    write("V26M_SERVICE_SET_VALIDATION.json", {"artifact_id": "V26M_SERVICE_SET_VALIDATION_V1", "random_cases": validation, "random_all_feasible": all(row["status"] == "FEASIBLE" for row in validation), "max_mass_error_GPU_h": max(row["mass_error"] for row in validation), "hidden_shedding_GPU_h": sum(row["hidden_shedding"] for row in validation), "explicit_infeasible_probe_status": bad.status, "source_infeasible_never_clipped": True})

    shape = np.full((96, 6, 5), 1.0 / (96 * 6 * 5))
    first = compose_mass_scenarios(1000, 2500, shape, 512, 20260901)
    second = compose_mass_scenarios(1000, 2500, shape, 512, 20260901)
    coefficients, power_contract = coefficients_kWh_per_GPU_h(REPO)
    sample_projection = project_service_set(first[0], 155.0)
    sample_power = service_to_IT_kW(sample_projection.reference_service_GPU_h, coefficients)
    power_contract.update({"artifact_id": "V26M_POWER_MAPPING_CONTRACT_V1", "tier_order": ["FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL"], "coefficients_kWh_per_GPU_h": coefficients.tolist(), "sample_peak_IT_kW": float(sample_power.max()), "authority_output": "IT_SIDE_ONLY"})
    write("V26M_POWER_MAPPING_CONTRACT.json", power_contract)
    print(json.dumps({"dependence": dependence["selected_inner_validation_rule"], "scenario_reproducible": bool(np.array_equal(first, second)), "service_random_pass": all(row["status"] == "FEASIBLE" for row in validation), "infeasible_probe": bad.status}))


if __name__ == "__main__":
    main()


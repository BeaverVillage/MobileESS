"""Fail-closed V17 V3R2 transfer, D-1 causality, and activation decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .v17_v3r2_eagle_forensic import write_json, zero_counters


PRIMARY_CLASSIFICATION = "V17_AIDC_POWER_V3R2_G_MARGINAL_POWER_NOT_IDENTIFIABLE"
ACTIVE_BOUNDARY = "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY"


def _base(schema: str, status: str) -> dict[str, Any]:
    return {"schema": schema, "status": status, **zero_counters()}


def _load(output: Path, name: str) -> dict[str, Any]:
    return json.loads((output / name).read_text(encoding="utf-8"))


def build(output: Path) -> list[Path]:
    marginal = _load(output, "V17_EAGLE_SHARED_MARGINAL_POWER_VALIDATION.json")
    energy = _load(output, "V17_V3R2_KESTREL_U2_ENERGY_IDENTIFIABILITY.json")
    reproduction = _load(output, "V17_V3R2_KESTREL_U2_REPRODUCTION.json")
    prior = _load(output, "V17_AIDC_POWER_V3R1_ZENODO_FINAL_REVIEW.json")
    if marginal["EAGLE_SHARED_MARGINAL_CLASSIFICATION"] != "EAGLE_SHARED_MARGINAL_D_NOT_IDENTIFIABLE":
        raise RuntimeError("V17_V3R2_UNEXPECTED_EAGLE_GATE_STATE")
    if energy["classification"] != "KESTREL_NODE_ENERGY_NOT_IDENTIFIABLE":
        raise RuntimeError("V17_V3R2_UNEXPECTED_KESTREL_ENERGY_GATE_STATE")

    transfer_acceptance = {
        **_base("V17_AIDC_POWER_V3R2_TRANSFER_ACCEPTANCE_CONTRACT_V1", "FAIL_CLOSED_NO_TRANSFER_THRESHOLD_WITHOUT_SHARED_MARGINAL_RESPONSE"),
        "minted_before_transfer_result_evaluation": True,
        "required_evidence": [
            "Eagle shared-state repeatability envelope",
            "Dataset312 V1 validation envelope",
            "H100 cross-dataset dimensionless variation",
            "measurement uncertainty",
        ],
        "available_shared_Eagle_samples": marginal["co_resident_sample_count"],
        "defensible_numerical_threshold_constructed": False,
        "reason": "Eagle contains no source-identifiable co-resident state, so no shared-response repeatability distribution exists from which to set a prospective transfer threshold.",
        "effect_or_grid_outcome_used": False,
    }
    transfer = {
        **_base("V17_V3R2_V100_TO_H100_RESPONSE_TRANSFER_AUDIT_V1", "FAIL_CLOSED_UPSTREAM_EAGLE_SHARED_RESPONSE_ABSENT"),
        "Eagle_hardware": "2 x NVIDIA Tesla V100 PCIe",
        "H100_sources": ["Dataset312 frozen absolute kappa", "Scientific Data H100", "EuroSys Zenodo H100"],
        "Eagle_absolute_kW_to_H100_authorized": False,
        "candidate_dimensionless_equation": "g_shared(X)=P_dynamic(X)/P_dynamic(full-GPU reference)",
        "candidate_dimensionless_response_identified": False,
        "cross_hardware_heldout_transfer_evaluation_performed": False,
        "V100_TO_H100_TRANSFER_CLASSIFICATION": "V100_TO_H100_TRANSFER_NOT_AUTHORIZED_UPSTREAM_MARGINAL_FAILURE",
        "Dataset312_kappa_changes": 0,
    }
    d1 = {
        **_base("V17_AIDC_POWER_V3R2_D1_CAUSALITY_AUDIT_V1", "FAIL_CLOSED_D1_SHARED_STATE_NOT_IDENTIFIABLE"),
        "historical_ex_post_U2_state": {
            "jobs": energy["reconstructable_ex_post_jobs"],
            "node_equivalent_hours": energy["reconstructable_ex_post_node_equivalent_hours"],
        },
        "future_physical_node_ID_available": False,
        "future_measured_utilization_available": False,
        "existing_logical_pool_axes": "latency/resource arrival aggregates; no future physical placement or source-defined co-residency state",
        "SHARED_OCCUPANCY_CLASS_defined": False,
        "reason": "Kestrel shared_job_count is an ex-post consequence of physical scheduler placement, not a causal D-1 observable under the current logical pools.",
        "POWER_RESPONSE_MODEL_IDENTIFIABLE": False,
        "DAY_AHEAD_ACTUATOR_STATE_IDENTIFIABLE": False,
    }
    cohort = {
        **_base("V17_AIDC_POWER_V3R2_COHORT_IDENTIFIABILITY_V1", "FAIL_CLOSED_NO_NEW_SOURCE_BACKED_COHORT"),
        "U1_CLASSIFICATION": "V17_V3_U1_NOT_IDENTIFIABLE",
        "U2_CLASSIFICATION": "V17_V3_U2_NOT_IDENTIFIABLE",
        "U3_CLASSIFICATION": "V17_V3_U3_NOT_IDENTIFIABLE",
        "reasons": {
            "U1": "Eagle partial-allocation total power is observed, but held-out marginal response is unreliable and V100-to-H100 transfer is not authorized.",
            "U2": "Kestrel native energy has no positive U2 observations; Eagle contains no exact co-resident samples; D-1 shared state is unavailable.",
            "U3": "No source-backed marginal response or H100 transfer supports unsupported full-node counts.",
        },
        "U2A": {"predicate": None, "jobs": 0, "node_equivalent_hours": 0.0},
        "U2B": {
            "predicate": "historically reconstructable only",
            "jobs": energy["reconstructable_ex_post_jobs"],
            "node_equivalent_hours": energy["reconstructable_ex_post_node_equivalent_hours"],
        },
        "U2C": {
            "jobs": reproduction["U2"]["jobs"] - energy["reconstructable_ex_post_jobs"],
            "node_equivalent_hours": reproduction["U2"]["node_equivalent_hours"] - energy["reconstructable_ex_post_node_equivalent_hours"],
        },
        "U2A_U2B_U2C_disjoint": True,
        "active_new_support_node_equivalent_hours": 0.0,
    }
    model_contract = {
        **_base("V17_AIDC_POWER_MODEL_V3R2_CONTRACT_V1", "V17_AIDC_POWER_MODEL_V3R2_NOT_MINTED"),
        "candidate_name": "V17_AIDC_POWER_MODEL_V3R2_EAGLE_BRIDGE",
        "minted": False,
        "preferred_equation_if_all_gates_passed": "P_H100(state)=kappa_V1(reference_class)*g_Eagle_normalized(X_COMMON)",
        "active_equation": None,
        "failed_gates": ["Eagle shared marginal identification", "V100-to-H100 transfer", "D-1 causal-state representation"],
        "V1_kappa_modified": False,
        "hybrid_support_activated": False,
        "ACTIVE_BOUNDARY": ACTIVE_BOUNDARY,
    }
    model_validation = {
        **_base("V17_AIDC_POWER_MODEL_V3R2_VALIDATION_V1", "FAIL_CLOSED_V3R2_NOT_AUTHORIZED"),
        "primary_classification": PRIMARY_CLASSIFICATION,
        "KESTREL_NATIVE_ENERGY_CLASSIFICATION": energy["classification"],
        "EAGLE_SHARED_MARGINAL_CLASSIFICATION": marginal["EAGLE_SHARED_MARGINAL_CLASSIFICATION"],
        "V100_TO_H100_TRANSFER_CLASSIFICATION": transfer["V100_TO_H100_TRANSFER_CLASSIFICATION"],
        "D1_CAUSAL_STATE_CLASSIFICATION": "D1_SHARED_STATE_NOT_IDENTIFIABLE",
        "heldout_Eagle_metrics": marginal["heldout_total_power_metrics"],
        "heldout_Eagle_marginal_metrics": marginal["heldout_natural_transition_metrics"],
        "active_point_authority": False,
    }
    semantic = reproduction["semantic_flexible"]
    v1 = reproduction["V1_modelable"]
    coverage = {
        **_base("V17_AIDC_POWER_V1_V3R2_COVERAGE_COMPARISON_V1", "PASS_NO_INCREMENTAL_ACTIVE_COVERAGE"),
        "semantic_flexible": semantic,
        "V1_modelable": v1,
        "V3R2_modelable": v1,
        "newly_recovered": {
            "U1": {"jobs": 0, "node_equivalent_hours": 0.0},
            "U2A": {"jobs": 0, "node_equivalent_hours": 0.0},
            "U3": {"jobs": 0, "node_equivalent_hours": 0.0},
        },
        "V1_job_fraction": v1["jobs"] / semantic["jobs"],
        "V1_node_equivalent_hour_fraction": v1["node_equivalent_hours"] / semantic["node_equivalent_hours"],
        "V3R2_job_fraction": v1["jobs"] / semantic["jobs"],
        "V3R2_node_equivalent_hour_fraction": v1["node_equivalent_hours"] / semantic["node_equivalent_hours"],
        "incremental_coverage": 0.0,
        "remaining_unmodeled_node_equivalent_hours": semantic["node_equivalent_hours"] - v1["node_equivalent_hours"],
    }
    decision = {
        **_base("V17_AIDC_POWER_V3R2_ACTIVATION_DECISION_V1", "V17_AIDC_POWER_V3R2_NOT_AUTHORIZED"),
        "primary_classification": PRIMARY_CLASSIFICATION,
        "ACTIVE_BOUNDARY": ACTIVE_BOUNDARY,
        "V3R2_authority_minted": False,
        "RCMQT_V3R2_required": False,
        "RCMQT_V3R2_performed": False,
        "same_7day_regression_required": False,
        "same_7day_regression_performed": False,
        "READY_FOR_APRIL_RESUME": bool(prior["READY_FOR_APRIL_RESUME"]),
        "resume_basis": "V1 and all prechange authority remain untouched; rejected V3R2 changes no active behavior.",
    }
    payloads = {
        "V17_AIDC_POWER_V3R2_TRANSFER_ACCEPTANCE_CONTRACT.json": transfer_acceptance,
        "V17_V3R2_V100_TO_H100_RESPONSE_TRANSFER_AUDIT.json": transfer,
        "V17_AIDC_POWER_V3R2_D1_CAUSALITY_AUDIT.json": d1,
        "V17_AIDC_POWER_V3R2_COHORT_IDENTIFIABILITY.json": cohort,
        "V17_AIDC_POWER_MODEL_V3R2_CONTRACT.json": model_contract,
        "V17_AIDC_POWER_MODEL_V3R2_VALIDATION.json": model_validation,
        "V17_AIDC_POWER_V1_V3R2_COVERAGE_COMPARISON.json": coverage,
        "V17_AIDC_POWER_V3R2_ACTIVATION_DECISION.json": decision,
    }
    paths: list[Path] = []
    for name, payload in payloads.items():
        path = output / name
        write_json(path, payload)
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in build(args.output):
        print(path)


if __name__ == "__main__":
    main()

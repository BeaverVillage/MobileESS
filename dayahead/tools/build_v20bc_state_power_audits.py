"""Materialize V20B D-1 state and V20C partial-node power audits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def main() -> None:
    schema_path = "dayahead/artifacts/v18r1_aidc_physical_coherence_repair/V18R1_KESTREL_GPU_ACCOUNTING_SCHEMA_AUDIT.json"
    oracle_path = "dayahead/artifacts/v18r1_aidc_physical_coherence_repair/V18R1_D1_RETROSPECTIVE_QUEUE_ORACLE.json"
    power_audit_path = "dayahead/artifacts/v17_candidate/V17_AIDC_PARTIAL_NODE_SOURCE_AUDIT.json"
    power_id_path = "dayahead/artifacts/v17_candidate/V17_AIDC_PARTIAL_NODE_POWER_IDENTIFIABILITY.json"
    schema = json.loads((ROOT / schema_path).read_text(encoding="utf-8"))
    oracle = json.loads((ROOT / oracle_path).read_text(encoding="utf-8"))
    fields = schema["source"]["schema_union"]

    discovery = {
        "artifact_id": "V20B_D1_STATE_SOURCE_DISCOVERY_V1",
        "sources_searched": ["repository scripts/artifacts/logs/manifests", "Kestrel zip schema/member inventory",
                             "Dataset312 archive schema audits", "Eagle source audits"],
        "Kestrel_source_sha256": schema["source"]["source_sha256"],
        "available_fields": fields,
        "prospective_snapshot_artifacts_found": [],
        "searched_terms": ["squeue", "scheduler snapshot", "pending jobs", "queue dump", "slurmctld",
                           "jobcomp", "eligible_time", "requeue", "suspend", "reservation", "QOS",
                           "priority", "reason", "alloc/start events"],
        "snapshot_fields_present": False,
        "state_transition_history_present": False,
        "explicit_requeue_field_present": False,
        "explicit_suspend_or_hold_timestamps_present": False,
        "source_schema_sha256": sha(schema_path),
    }
    write("V20B_D1_STATE_SOURCE_DISCOVERY.json", discovery)

    queue = {
        "artifact_id": "V20B_D1_QUEUE_RECONSTRUCTABILITY_AUDIT_V1",
        "candidate_rule": "submit_time <= cutoff < start_time",
        "rule_semantics": "retrospectively identifies jobs that eventually started after cutoff",
        "strength": "RESTRICTED_RETROSPECTIVE_SUBSET_ONLY",
        "complete_queue_membership_supported": False,
        "blocking_gaps": ["no cutoff snapshot", "no cancellation time", "no hold/release history",
                          "no requeue history", "final state is not a cutoff-state transition log"],
        "eventually_started_subset_is_full_queue_claim": False,
        "future_actual_feature_injection_count": 0,
        "main_authority_eligible": False,
    }
    write("V20B_D1_QUEUE_RECONSTRUCTABILITY_AUDIT.json", queue)

    running = {
        "artifact_id": "V20B_D1_RUNNING_RECONSTRUCTABILITY_AUDIT_V1",
        "candidate_rule": "start_time <= cutoff < end_time",
        "end_timestamp_use": "RETROSPECTIVE_RECONSTRUCTION_ONLY",
        "complete_running_membership_supported": False,
        "blocking_gaps": ["no cutoff snapshot", "no suspend/resume transition history",
                          "no requeue transition history", "requested GPU is not AllocTRES/GRES allocation"],
        "request_walltime_bounds": {"allowed": True, "authority": "BOUND_DIAGNOSTIC_ONLY",
                                    "not_used_as_realized_end": True},
        "future_actual_feature_injection_count": 0,
        "main_authority_eligible": False,
    }
    write("V20B_D1_RUNNING_RECONSTRUCTABILITY_AUDIT.json", running)

    contract = {
        "artifact_id": "V20B_RETROSPECTIVE_CAUSAL_STATE_DATASET_CONTRACT_V1",
        "status": "DEFINED_FAIL_CLOSED_NOT_ACTIVATED",
        "level_A": "NOT_AVAILABLE",
        "level_B": "NOT_SUPPORTED_FOR_COMPLETE_STATE",
        "level_C": "AVAILABLE_DIAGNOSTIC_ONLY",
        "allowed_research_dataset": {
            "name": "EVENTUALLY_EXECUTED_RETROSPECTIVE_SUBSET",
            "fields": ["job_id_hash", "cutoff", "submit_time", "start_time", "end_time",
                       "gpus_requested", "requested_walltime", "subset_membership"],
            "label": "NON_CAUSAL_ORACLE_DIAGNOSTIC",
            "prohibited_as_feature": ["future start", "future end", "future final state", "future job identity"],
        },
        "activation_gate": "archived scheduler snapshots or complete timestamped state-transition log",
        "FORECAST_NEW_ONLY_main_policy": "REMAINS_VALID",
        "future_actual_feature_injection_count": 0,
    }
    write("V20B_RETROSPECTIVE_CAUSAL_STATE_DATASET_CONTRACT.json", contract)

    b_review = {
        "artifact_id": "V20B_D1_STATE_FINAL_REVIEW_V1", "classification": "B3_ONLY_NONCAUSAL_ORACLE_SUPPORTED",
        "exact_snapshot_available": False, "retrospective_complete_causal_state_supported": False,
        "queued_GPU_h": None, "running_GPU_h": None,
        "level_C_preserved_oracle": {"path": oracle_path, "sha256": sha(oracle_path),
                                     "seven_day_queued_GPU_h": oracle["totals"]["queued_oracle_GPU_h"],
                                     "seven_day_running_GPU_h": oracle["totals"]["running_oracle_GPU_h"],
                                     "authority_role": "NONE"},
        "D1_STATE_EXTENSION_READY": False, "FORECAST_NEW_ONLY_main_policy": "VALID",
        "future_actual_feature_injection_count": 0,
    }
    write("V20B_D1_STATE_FINAL_REVIEW.json", b_review)
    (OUT / "V20B_D1_STATE_FINAL_REVIEW.md").write_text(
        "# V20B D-1 state final review\n\n"
        "**B3 — ONLY_NONCAUSAL_ORACLE_SUPPORTED**\n\n"
        "실제 cutoff snapshot과 상태 전이 이력이 없으므로 전체 queue/running 상태를 Level B로 복구할 수 없다. "
        "기존 7일 합계(queued 6621.642222 GPU-h, running 5303.617222 GPU-h)는 Level C 사후 진단이며 입력·스케일·최적화 권한이 아니다. "
        "따라서 `FORECAST_NEW_ONLY` 정책을 유지한다.\n", encoding="utf-8")

    old_audit = json.loads((ROOT / power_audit_path).read_text(encoding="utf-8"))
    source_audit = {
        "artifact_id": "V20C_PARTIAL_NODE_POWER_SOURCE_AUDIT_V1",
        "Dataset312_source": old_audit["source"], "raw_member_counts": old_audit["raw_member_counts"],
        "available": old_audit["available_fields"],
        "additional_sources_reviewed": ["Kestrel job accounting", "Eagle V100 energy telemetry",
                                        "external H100/B200 parameter-support audit", "EuroSys GPU-sharing archive"],
        "main_gate": {"H100_compatible": True, "workload_dependent": True,
                      "partial_occupancy_directly_measured": False, "idle_subtraction_clear": False,
                      "packing_semantics_clear": False},
        "source_audit_sha256": sha(power_audit_path),
    }
    write("V20C_PARTIAL_NODE_POWER_SOURCE_AUDIT.json", source_audit)

    packing = {
        "artifact_id": "V20C_PARTIAL_NODE_PACKING_IDENTIFIABILITY_V1",
        "per_GPU_board_power_available": True, "per_GPU_active_count_available": False,
        "partial_GPU_occupancy_experiment_available": False, "MIG_state_available": False,
        "multi_job_sharing_mechanism_identified": False, "powered_idle_GPU_state_identified": False,
        "host_idle_baseline_identified": False, "packing_semantics": "NOT_IDENTIFIABLE",
        "fullnode_to_partial_interpolation_allowed": False,
    }
    write("V20C_PARTIAL_NODE_PACKING_IDENTIFIABILITY.json", packing)

    admissibility = {
        "artifact_id": "V20C_PARTIAL_NODE_CPU_HOST_ADMISSIBILITY_V1",
        "candidates": [
            {"source": "Dataset312 RAPL", "H100_compatible": True, "workload_dependent": True,
             "partial_direct": False, "idle_clear": False, "packing_clear": False, "admitted": False},
            {"source": "Eagle V100", "H100_compatible": False, "workload_dependent": True,
             "partial_direct": False, "idle_clear": "uncertain", "packing_clear": False, "admitted": False},
            {"source": "GPU TDP/nameplate", "H100_compatible": "not_measurement",
             "workload_dependent": False, "partial_direct": False, "idle_clear": False,
             "packing_clear": False, "admitted": False},
        ],
        "admitted_CPU_host_increment_kW_per_GPU": None,
        "arbitrary_host_multiplier_count": 0, "partial_CPU_double_count": 0,
        "Eagle_V100_to_H100_scaling_count": 0, "TDP_as_measurement_count": 0,
    }
    write("V20C_PARTIAL_NODE_CPU_HOST_ADMISSIBILITY.json", admissibility)

    bounds = {
        "artifact_id": "V20C_PARTIAL_NODE_POWER_BOUND_CONTRACT_V1",
        "lower_bound_kW_per_GPU": 0.48563611660901085,
        "lower_bound_boundary": "GPU_BOARD_INCREMENT_Q50",
        "CPU_host_increment_kW_per_GPU": None,
        "total_partial_node_interval_kW_per_GPU": {"lower": 0.48563611660901085, "upper": None},
        "finite_upper_bound_supported": False,
        "prohibited": ["full-node CPU / 4", "TDP bound", "V100-to-H100 direct scaling", "result tuning"],
        "PUE_application": "once after IT decomposition; unchanged",
    }
    write("V20C_PARTIAL_NODE_POWER_BOUND_CONTRACT.json", bounds)

    c_review = {
        "artifact_id": "V20C_PARTIAL_NODE_POWER_FINAL_REVIEW_V1",
        "classification": "C3_GPU_BOARD_LOWER_BOUND_REMAINS_ONLY",
        "new_main_authority_found": False, "current_lower_bound_remains": True,
        "partial_node_kW_per_GPU": 0.48563611660901085,
        "CPU_increment": None, "finite_interval_supported": False,
        "PARTIAL_NODE_POWER_UPGRADE_READY": False,
        "prior_identifiability_sha256": sha(power_id_path),
        "firewall": {"power_coefficient_tuning_calls": 0, "arbitrary_host_multiplier": 0,
                     "partial_CPU_double_count": 0, "PUE_application_count_per_bridge": 1},
    }
    write("V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.json", c_review)
    (OUT / "V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.md").write_text(
        "# V20C partial-node power final review\n\n"
        "**C3 — GPU_BOARD_LOWER_BOUND_REMAINS_ONLY**\n\n"
        "H100 호환 부분점유 직접 측정, 명확한 idle 차감, packing 의미를 함께 만족하는 자료가 없다. "
        "따라서 기존 0.48563611660901085 kW/GPU GPU-board Q50 하한을 유지하며 CPU/host increment와 유한 상한은 null이다.\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()

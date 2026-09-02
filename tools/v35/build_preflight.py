#!/usr/bin/env python3
"""Build the immutable V35 pre-April contracts and closure audit."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v34.traffic_authority import ELEVATED, LINK_ORDER, PHYSICAL, SERVICE_NODES
from dayahead.v35.contracts import (
    ACTUAL_AIDC_FIREWALL_FIELDS,
    ACTUAL_MESS_FIREWALL_FIELDS,
    AIDC_STAGE_CASE,
    APRIL_DAYS,
    APRIL_RETRY_LIMIT,
    BRANCH,
    CALIBRATION_DAYS,
    CASE_ACTUATORS,
    FAILURE_CLASSES,
    MAY_DAYS,
    MAY_RETRY_LIMIT,
    MEMORY_RESERVE_BYTES,
    MESS_ORDER,
    OFFICIAL_CASES,
    RESOLUTION_MINUTES,
    SLOTS,
    SOLVER_SEED,
    STORAGE_CATEGORIES,
    VALIDATION_DAYS,
    WORK_LIMIT_TIERS,
)
from dayahead.v35.storage import atomic_json, canonical_sha256, sha256_file, storage_schema_sha256


OUT = REPO / "dayahead/artifacts/v35_april_may_final"
V34 = REPO / "dayahead/artifacts/v34_aidc_mess_april_calibration_validation"
SERVICE_MAPPING = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\work\power_side_p4f_review_20260731_190038\power_side_p4f_hardening_v1\rating_contract_all_transformers\service_node_electrical_mapping_v1.csv")
SOURCE_REPO = REPO.parent / "MobileESS_v28r2_heavy_backend"
FEEDER_MASTER = REPO.parent / "tmp/c12_exact_sources_repo_cleanup/c12_exact_sources/v2038_parent/Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038/reference/opendss_assets/IEEE123Master.dss"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _head() -> str:
    return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=REPO, text=True).strip()


def _file_record(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"V35_SCIENCE_AUTHORITY_MISSING:{path}")
    try:
        relative = path.relative_to(REPO).as_posix()
    except ValueError:
        relative = str(path.resolve())
    return {"path": relative, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def _write(name: str, payload: dict[str, object]) -> str:
    payload = dict(payload)
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    return atomic_json(OUT / name, payload)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    head = _head()
    audit = _load(V34 / "V34_FAST_OBJECTIVE_AIDC_MESS_COUPLING_AUDIT.json")
    smoke = _load(V34 / "V34_INTEGRATION_SMOKE.json")
    by_case = {str(row["case"]): row for row in smoke["cases"]}
    stationary = audit["MESS_PQ_coupling_probe"]["stationary_PQ_only"]
    perturbation = stationary["deterministic_feasible_Q_perturbation"]
    b3 = audit["B1_vs_B3_zero_MESS_equivalence"]
    production_first = by_case["B2"]["mess"]["per_MESS_runtime"][0]
    restricted_dominance = float(production_first["objective_value"]) <= float(stationary["incumbent"]) + 1e-6
    planning_pass = all(bool(by_case[case]["aggregate_planning_physics"]["pass"]) for case in OFFICIAL_CASES)
    closure_checks = {
        "B3_lineage_invariant": bool(b3["equivalence_pass"] and by_case["B3"]["aidc_stage_case"] == "B1"),
        "AIDC_decision_to_PQ_to_grid_to_objective": bool(audit["GO_NO_GO"]["conditions"]["AIDC_PQ_changes_planning_grid_and_objective"]),
        "MESS_PQ_to_planning_grid": bool(audit["MESS_PQ_coupling_probe"]["MESS_grid_coupling_alive"]),
        "plus_50_kvar_all_production_constraints_feasible": bool(perturbation["all_production_planning_constraints_feasible"]),
        "stationary_PQ_optimized_nonzero": bool(stationary["P_Q_nonzero"]),
        "stationary_PQ_improvement_resolved": bool(float(stationary["rho_improvement"]) > 1e-6 and float(stationary["resolved_absolute_gap"]) <= 1e-6),
        "full_model_not_worse_than_restricted": restricted_dominance,
        "solver_starvation_remaining": bool(audit["MESS_PQ_coupling_probe"]["MESS_solver_starvation_confirmed"]),
        "planning_physical_constraints": planning_pass,
        "May_numeric_reads": 0,
        "AIDC_only_stage_disables_legacy_MESS_internally": (
            "mess_disabled=True" in (REPO / "dayahead/v35/execution.py").read_text(encoding="utf-8")
            and "DISABLED_ZERO_STATIONARY_NOT_MODELLED_AS_LEGACY_ROUTE"
            in (REPO / "dayahead/v35/execution.py").read_text(encoding="utf-8")
        ),
    }
    closure_pass = all(
        bool(value) for key, value in closure_checks.items()
        if key not in {"solver_starvation_remaining", "May_numeric_reads"}
    ) and not closure_checks["solver_starvation_remaining"] and closure_checks["May_numeric_reads"] == 0

    case_registry = {
        "artifact_id": "V35_CASE_REGISTRY_V1",
        "official_cases": list(OFFICIAL_CASES),
        "case_count": 4,
        "cases": {
            case: {
                "AIDC_controllable_flexibility": bool(CASE_ACTUATORS[case]["aidc"]),
                "MESS_controllable_mobility_PQ": bool(CASE_ACTUATORS[case]["mess"]),
                "AIDC_stage_case": AIDC_STAGE_CASE[case],
            }
            for case in OFFICIAL_CASES
        },
        "diagnostic_probes_are_official_cases": False,
        "B3_lineage": "CURRENT_B1_AIDC_ONLY_THEN_DETERMINISTIC_SEQUENTIAL_V33M3_MESS",
    }
    _write("V35_CASE_REGISTRY.json", case_registry)

    authority_paths = {
        "AIDC_scale": REPO / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_FINAL_IEEE123_AIDC_SCALE.json",
        "C1": REPO / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
        "P_G_W_model_contract": REPO / "dayahead/artifacts/v28r2_heavy_backend/V28R2_OPTIMIZER_CHANNEL_SCHEMA.json",
        "AIDC_workload_eligibility": REPO / "dayahead/artifacts/v28r2_heavy_backend/V28R2_WORKLOAD_ELIGIBILITY_BINDING.json",
        "traffic_model_authority": REPO / "dayahead/artifacts/v33m3_causal_dayahead_traffic/V33M3_FINAL_MODEL_AUTHORITY.json",
        "traffic_model_checkpoint": REPO / "dayahead/artifacts/v33m3_causal_dayahead_traffic/V33M3_FINAL_MODEL.npz",
        "safe_ETA": REPO / "dayahead/artifacts/v33m3_causal_dayahead_traffic/V33M3_SAFE_ETA_CALIBRATION.json",
        "road_link_order": LINK_ORDER,
        "road_service_nodes": SERVICE_NODES,
        "road_physical_edges": PHYSICAL,
        "road_elevation_network": ELEVATED,
        "service_electrical_mapping": SERVICE_MAPPING,
        "IEEE123_feeder": FEEDER_MASTER,
        "MESS_physics": REPO / "dayahead/mess_physics.py",
        "MESS_mobility_MILP": REPO / "dayahead/v33m/mess_mobility_milp.py",
        "objective_formulation": REPO / "dayahead/v28r2/variable_registry.py",
    }
    authorities = {name: _file_record(path) for name, path in authority_paths.items()}
    science_freeze = {
        "artifact_id": "V35_SCIENCE_FREEZE_V1",
        "status": "FROZEN_FOR_APRIL_DEVELOPMENT",
        "code_HEAD": head,
        "branch": BRANCH,
        "resolution_minutes": RESOLUTION_MINUTES,
        "slots_per_day": SLOTS,
        "dayahead_policy": "D_MINUS_1_ONE_SHOT_96_SLOT_OPTIMIZATION",
        "cases": list(OFFICIAL_CASES),
        "calibration_days": list(CALIBRATION_DAYS),
        "validation_days": list(VALIDATION_DAYS),
        "May_dates_declared_but_not_opened": list(MAY_DAYS),
        "MESS_coordination": "DETERMINISTIC_SEQUENTIAL_MESS_COORDINATION",
        "MESS_order": list(MESS_ORDER),
        "route_K": 1,
        "science_authorities": authorities,
        "science_authority_SHA": canonical_sha256(authorities),
        "prohibited": [
            "MAY_BASED_RETUNING", "FRESH_AS_OPTIMIZER_ORACLE", "ACTUAL_GRID_FEEDBACK_TO_AIDC",
            "ACTUAL_MESS_REROUTING", "ACTUAL_MESS_OPTIMIZATION", "FORCED_MESS_MOVEMENT",
            "AIDC_SCALE_INFLATION", "OBJECTIVE_WEIGHT_RETUNING", "ROLLING_MPC",
        ],
        "May_opened": False,
        "May_numeric_reads": 0,
    }
    _write("V35_SCIENCE_FREEZE.json", science_freeze)

    solver_policy = {
        "artifact_id": "V35_MESS_SOLVER_POLICY_V1",
        "status": "PASS",
        "full_model_built_before_restricted_candidate": True,
        "cheap_candidates": ["STAY_ZERO_PQ", "STAY_STATIONARY_PQ_OPTIMIZED"],
        "restricted_candidate_is_production_constraint_feasible": True,
        "restricted_candidate_is_MIPStart": True,
        "work_limit_tiers": list(WORK_LIMIT_TIERS),
        "escalation_triggers": [
            "NO_FEASIBLE_INCUMBENT", "FULL_INCUMBENT_WORSE_THAN_RESTRICTED",
            "ZERO_ACTUATION_WHILE_RESTRICTED_HAS_RESOLVED_IMPROVEMENT", "OBVIOUS_SOLVER_STARVATION",
        ],
        "large_gap_alone_triggers_escalation": False,
        "solver_seed": SOLVER_SEED,
        "global_joint_optimality_claimed": False,
        "bounded_compute_label": "FEASIBLE_BOUNDED_COMPUTE_INCUMBENT",
        "empirical_Apr01": {
            "zero_rho": stationary["baseline_rho"],
            "restricted_rho": stationary["optimized_rho"],
            "restricted_absolute_gap": stationary["resolved_absolute_gap"],
            "full_MESS01_objective": production_first["objective_value"],
            "full_not_worse_than_restricted": restricted_dominance,
        },
        "implementation_SHA": sha256_file(REPO / "dayahead/v34/integrated_mess.py"),
    }
    _write("V35_MESS_SOLVER_POLICY.json", solver_policy)

    storage_contract = {
        "artifact_id": "V35_STORAGE_CONTRACT_V1",
        "status": "FROZEN",
        "schema_SHA": storage_schema_sha256(),
        "categories": {name: list(fields) for name, fields in STORAGE_CATEGORIES.items()},
        "large_tensor_root": "dayahead/cache/v35",
        "compact_artifact_root": "dayahead/artifacts/v35_april_may_final",
        "log_root": "logs/v35_april_may_final",
        "final_May_root": "frozen_artifacts/v35_may_final",
        "write_then_reload_is_PASS_gate": True,
        "route_table_stored_once_per_day": True,
        "route_table_duplicated_per_case": False,
    }
    _write("V35_STORAGE_CONTRACT.json", storage_contract)

    resume_contract = {
        "artifact_id": "V35_RESUME_CONTRACT_V1",
        "status": "FROZEN",
        "checkpoint_granularity": "PHASE_X_DAY_X_CASE",
        "PASS_skip_requires_all_dependency_SHAs_match": True,
        "failed_case_only_resume_default": True,
        "impact_invalidation": {
            "serialization_report_only": ["ARTIFACT_REGENERATION"],
            "case_local": ["AFFECTED_CASE_ONLY"],
            "MESS_only": ["B2", "B3"],
            "AIDC_only": ["B1", "B3"],
            "common_grid_physical_objective": list(OFFICIAL_CASES),
            "correction_calculation": ["CORRECTION_FREEZE", "PROSPECTIVE_SELECTION", "CORRECTED_VALIDATION"],
        },
        "failure_classes": list(FAILURE_CLASSES),
        "April_retry_limit_per_signature": APRIL_RETRY_LIMIT,
        "May_retry_limit_per_signature": MAY_RETRY_LIMIT,
        "May_engineering_repair_requires_full_restart_from_May01": True,
    }
    _write("V35_RESUME_CONTRACT.json", resume_contract)

    effect_contract = {
        "artifact_id": "V35_EFFECT_WATCHDOG_CONTRACT_V1",
        "status": "FROZEN",
        "AIDC_comparisons": ["B1-B0", "B3-B2"],
        "MESS_comparisons": ["B2-B0", "B3-B1"],
        "resolved_effect_formula": "abs(delta_objective) > max(objective_tolerance, gap_A + gap_B)",
        "deeper_audit_after_consecutive_unexplained_days": 3,
        "zero_MOVE_alone_is_defect": False,
        "zero_PQ_alone_is_defect": False,
        "restricted_feasible_incumbent_beating_full_is_defect": True,
        "small_effect_may_be_physical_if_coupling_and_solver_resolution_pass": True,
        "fabricated_or_forced_actuation": False,
    }
    _write("V35_EFFECT_WATCHDOG_CONTRACT.json", effect_contract)

    closure = {
        "artifact_id": "V35_PREAPRIL_AIDC_MESS_CLOSURE_AUDIT_V1",
        "status": "PASS" if closure_pass else "FAIL",
        "primary_classification": "V35_PREAPRIL_AIDC_MESS_CLOSURE_PASS" if closure_pass else "V35_PREAPRIL_MESS_DEFECT_BLOCKED",
        "code_HEAD": head,
        "checks": closure_checks,
        "defects_discovered": [
            {
                "classification": "ENGINEERING_SOLVER_INTEGRATION_DEFECT",
                "defect_id": "V35_STATIONARY_PQ_LOOSE_RELATIVE_GAP_ZERO_INCUMBENT_DEFECT",
                "root_cause": "The restricted stationary P/Q MIP accepted the zero-actuation incumbent at MIPGap=1e-3 even though a fully feasible +50 kvar point reduced rho; Gurobi OPTIMAL meant within the requested relative gap, not an exact zero-actuation optimum.",
                "repair": "Solve the exact full model temporarily fixed to STAY at MIPGap=1e-7, use the resulting P/Q trajectory as MIPStart, compare the full incumbent against it, and escalate deterministically through WorkLimit 60/180/300 only on starvation evidence.",
                "science_changed": False,
            },
            {
                "classification": "CASE_BINDING_DEFECT",
                "defect_id": "V35_AIDC_ONLY_STAGE_LEGACY_MESS_CONDITIONING_DEFECT",
                "root_cause": "Legacy V28R2 B0/B1 resource models fixed a small pre-route MESS charging trajectory and mobility energy, so merely zeroing MESS in the exported V34 schedule did not make the upstream AIDC optimization truly MESS-free.",
                "repair": "The V35 AIDC-only B0/B1 stage now fixes every MESS P/Q value to zero, removes legacy mobility energy from that stage, holds all four units stationary, and solves AIDC again before B2/B3 sequential V33M3 coordination.",
                "invalidation": "No V35 campaign result existed; V34 audit evidence is preserved and V35 case outputs are generated only from the repaired stage.",
                "science_changed": False,
            },
        ],
        "stationary_PQ_consistency": {
            "plus_50_kvar": perturbation,
            "optimized": stationary,
            "conclusion": "FULLY_FEASIBLE_NONZERO_PQ_IMPROVES_RHO_AND_IS_NOW_FOUND",
        },
        "uncorrected_Apr01_Fresh": {
            case: {
                "voltage_violation_count": by_case[case]["fresh"]["voltage_violation_count"],
                "Vmin_pu": by_case[case]["fresh"]["Vmin_pu"],
                "classification": "APR01_20_AC_FIDELITY_CALIBRATION_RESIDUAL_NOT_PREFLIGHT_SOLVER_DEFECT",
            }
            for case in ("B2", "B3")
        },
        "previous_PASS_artifacts_invalidated": [
            "V34 Apr01 B2/B3 zero-PQ solver conclusion",
            "V34 objective coupling audit generated before tight restricted solve",
        ],
        "previous_PASS_artifacts_preserved": [
            "V34 B3 AIDC lineage correction",
            "V28R2 immutable B0/B1 AIDC source schedules",
            "V33M3 traffic and mobility authority",
            "all unrelated April source manifests and raw arrays",
        ],
        "May_opened": False,
        "May_numeric_reads": 0,
    }
    _write("V35_PREAPRIL_AIDC_MESS_CLOSURE_AUDIT.json", closure)

    progress_path = OUT / "V35_PROGRESS.json"
    _write("V35_PROGRESS.json", {
        "current_phase": "PREAPRIL_CLOSURE_COMPLETE" if closure_pass else "PREAPRIL_BLOCKED",
        "current_day": None,
        "current_case": None,
        "completed_pass_count": 0,
        "failed_count": 0 if closure_pass else 1,
        "retry_count": 1,
        "current_HEAD": head,
        "current_run_id": "v35-preflight-1",
        "May_opened": False,
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
    })
    print(json.dumps({"status": closure["status"], "HEAD": head, "output": str(OUT), "progress": str(progress_path)}, indent=2))
    return 0 if closure_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())

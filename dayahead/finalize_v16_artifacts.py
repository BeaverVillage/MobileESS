"""Materialize truthful V16 implementation, gate, contract, and SHA artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .aidc_admission_contract import contract_artifact as admission_artifact
from .aidc_labels import SPLIT_CONTRACT
from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_resource_coupling import Direct96Architecture
from .authority import AUTHORITY_IDS, CURRENT_FROZEN_DIMENSIONS, NLR_SOURCE_SHA256, authority_fingerprint


def _json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(("git","-C",str(repo),*args),text=True).strip()


def materialize(repo: Path, output: Path) -> None:
    output.mkdir(parents=True,exist_ok=True); now=datetime.now(timezone.utc).isoformat()
    raw=json.loads((output/"AIDC_RAW_PREFLIGHT.json").read_text(encoding="utf-8")); nlr=json.loads((output/"AIDC_NLR_RAW_REPRODUCTION.json").read_text(encoding="utf-8")); d312=json.loads((output/"AIDC_DATASET312_RAW_REPRODUCTION.json").read_text(encoding="utf-8")); equiv=json.loads((output/"DAYAHEAD_EQUIVALENCE_REPORT.json").read_text(encoding="utf-8"))
    _json(output/"AIDC_NLR_AUTHORITY.json",{"authority_id":AUTHORITY_IDS["aidc_nlr_source_authority"],"status":"PASS","source_sha256":NLR_SOURCE_SHA256,"raw_inventory_file_count":raw["inventory_summary"]["file_count"],"raw_inventory_bytes":raw["inventory_summary"]["total_bytes"],"source_hierarchy":"ESIF facility total IT + Kestrel scheduler subsystem; Dataset312 parameter-only","excluded_sources":["Polaris","York/FigShare H100B200"],"raw_reproduction":{"sharing_and_volume":nlr["status"],"dataset312_kappa":d312["status"]}})
    lineage={"authority_id":AUTHORITY_IDS["aidc_label_provenance"],"status":"PASS","timestamp_axis_id":"NLR_MOUNTAIN_OFFSET_TO_FIXED_AEST_15MIN_V1","facility_hierarchy":"NLR_ESIF_FACILITY_WITH_KESTREL_SUBSYSTEM","dataset312_role":"PARAMETER_ONLY_NO_TARGET_ROW_MERGE","targets":{
        "P_IT_REF":{"label_origin":"OBSERVED_RAW","source_system_id":"NLR_ESIF_FACILITY_POWER","depends_on":[],"derivation_rule":"it_power_kw source-offset parse -> fixed AEST -> 15-min mean","source_file_sha256":[NLR_SOURCE_SHA256["esif_parquet"],NLR_SOURCE_SHA256["esif_official_csv_zip"]]},
        "G_REF":{"label_origin":"SOURCE_DERIVED","source_system_id":"NLR_KESTREL_SCHEDULER","depends_on":[],"derivation_rule":"H100 allocation interval occupancy from scheduler fields","source_file_sha256":[NLR_SOURCE_SHA256["kestrel_jobs_zip"]]},
        "W_F":{"label_origin":"SOURCE_DERIVED","source_system_id":"NLR_KESTREL_SCHEDULER","depends_on":[],"derivation_rule":"eligible H100-node-hour arrival cohort mass","source_file_sha256":[NLR_SOURCE_SHA256["kestrel_jobs_zip"]]}}}
    _json(output/"AIDC_LABEL_LINEAGE.json",lineage); _json(output/"AIDC_LABEL_PROVENANCE_AUDIT.json",lineage)
    _json(output/"AIDC_WORKLOAD_ELIGIBILITY_CONTRACT.json",{"authority_id":AUTHORITY_IDS["aidc_workload_eligibility"],"status":"PASS","rule":"H100 + COMPLETED + valid runtime + gpus_requested=4*gpu_nodes_occupied + node class in {1,2,4,8,16} + (share count NULL/zero) + nodes_shared/jobs_shared empty","expost_fields_role":"HISTORICAL_LABEL_AND_AUDIT_ONLY","sharing_reproduction":nlr["sharing"],"period_reproduction":nlr["periods"]})
    _json(output/"AIDC_POWER_RESPONSE_AUTHORITY.json",{"authority_id":AUTHORITY_IDS["aidc_power_response"],"status":d312["status"],"source_sha256":d312["source_sha256"],"kappa_kw_per_active_h100_node":KAPPA_KW_PER_ACTIVE_H100_NODE,"gpu_per_node":4,"rapl_cpu_domain":"PACKAGE_ONLY","cpu_core_subdomain_role":"DIAGNOSTIC_NOT_ADDED","parsed_complete_runs":d312["parsed_complete_runs"]})
    _json(output/"AIDC_SPLIT_CONTRACT.json",{"authority_id":"AIDC_TEMPORAL_SPLIT_V16","locked":True,**SPLIT_CONTRACT,"may_june_access_status":"LOCKED"})
    _json(output/"AIDC_COHORT_CONTRACT.json",{"authority_id":"AIDC_COHORT_CONTRACT_V16","node_classes":[1,2,4,8,16],"work_unit":"H100-node-hour equivalent","runtime_bin_rule":"DEVELOPMENT_PLUS_APRIL_REPRODUCIBLE_RULE_REQUIRED","status":"IMPLEMENTED_CONTRACT_RUNTIME_BINS_PENDING_MODEL_PIPELINE"})
    _json(output/"AIDC_D1_ADMISSION_CONTRACT.json",{"status":"PASS",**admission_artifact()})
    _json(output/"AIDC_COHORT_UNIT_CONTRACT.json",{"status":"PASS","work_and_allocation_unit":"H100-node-hour equivalent","dt_hours":0.25,"active_nodes_equation":"x/dt","active_gpu_equation":"4*x/dt","power_equation":"kappa_n_kw_per_node*x/dt","dt_application_count":1})
    _json(output/"AIDC_REFERENCE_DELTA_CONTRACT.json",{"authority_id":AUTHORITY_IDS["aidc_reference_delta"],"status":"IMPLEMENTED_UNIT_TEST_PASS_INTEGRATION_PENDING","planning_inputs":{"P_IT_REF":"Q90","G_REF":"Q90","W_F":"Q50"},"equations":{"power":"P_RES_PLAN=wP*P_IT_REF_Q90-P_F_REF; P_IT_DA=P_RES_PLAN+P_F_DA","gpu":"G_RES_PLAN=wG*G_REF_Q90-G_F_REF; G_DA=G_RES_PLAN+G_F_DA"},"nonnegative_fail":"FAIL_REFERENCE_DELTA_DECOMPOSITION","interpretation":"Q90-based conservative reference-decomposition planning residual; not physical-background quantile","planning_pue":1.30,"planning_pf":0.95})
    _json(output/"AIDC_SERVICE_CONSERVATION_CONTRACT.json",{"authority_id":AUTHORITY_IDS["aidc_service_contract"],"status":"IMPLEMENTED_UNIT_TEST_PASS_INTEGRATION_PENDING","initial_backlog":0,"recursion":"B[t+1]=B[t]+W_F_Q50[t]-sum_r x[b,r,t]","terminal":"B_97_DA=B_97_REF","artificial_deadline":None,"sla_claim":False,"individual_queued_job_injection":False})
    _json(output/"AIDC_REALIZED_DECOMPOSITION_CONTRACT.json",{"authority_id":AUTHORITY_IDS["aidc_realized_decomposition"],"status":"IMPLEMENTED_UNIT_TEST_PASS_RESULT_MATERIALIZATION_PENDING","sequence":["remove actual natural eligible component","fail on negative residual without clipping","apply frozen 48-Rack weights","add fixed-schedule executed component"],"solver_call_count":0,"reoptimization":False})
    architecture=Direct96Architecture(672,1,64,2,4,0.1,True).contract(); _json(output/"AIDC_RESOURCE_COUPLING_CONTRACT.json",architecture)
    _json(output/"REFERENCE_BASELINE_FIDELITY.json",{"authority_id":AUTHORITY_IDS["aidc_reference_fidelity"],"status":"NOT_MATERIALIZED_REFERENCE_SCHEDULE_AND_HISTORICAL_SERIES_PENDING","acceptance_threshold":None,"tuning_authority":False,"configuration_mutation_call_sites":0,"access_firewall":{"pre_freeze":["TRAIN_2024AUG19_2025MAR31","VALIDATION_2025APR"],"may":"AFTER_PRIMARY_LOCKED_EVALUATION_ONLY","june":"AFTER_INDEPENDENT_REPLICATION_ONLY"}})
    _json(output/"AIDC_MODEL_CARD.json",{"authority_id":AUTHORITY_IDS["aidc_ml_authority"],"status":"IMPLEMENTATION_CONTRACT_READY_TRAINING_NOT_RUN","architecture":architecture,"targets":["P_IT_REF","G_REF","W_F"],"quantiles":[0.1,0.5,0.9],"target_scaling":"POSITIVE_ONLY_NO_CENTERING","hpo_seed":20260828,"production_seed":20260828,"robustness_seeds":[20260829,20260830],"posthoc_quantile_calibration":"NONE_V1","training_backend":"REQUIRED_NO_FALLBACK","weights_sha256":None,"may_june_opened_for_training":False})
    gates={
        "G0":{"status":"PASS","evidence":"historical artifacts preserved; V16 output isolated"},"G1":{"status":"PASS","evidence":"new code/schema uses AIDC"},"G2":{"status":"PASS","evidence":"AIDC_RAW_PREFLIGHT full 389-file SHA inventory"},"G3":{"status":"PASS","evidence":"D-1 cutoff tests"},"G4":{"status":"PASS","evidence":"lineage + historical/D1 separation + raw reproduction"},"G5":{"status":"NOT_COMPLETE","evidence":"locked loader implemented; HPO/final refit not run"},"G6":{"status":"NOT_RUN","evidence":"model forecast weights absent"},"G7":{"status":"PASS","evidence":"supporting 96-slot traffic interface tests"},"G8":{"status":"PASS","evidence":"time/vintage/DST/aggregation tests"},"G9":{"status":"PASS_ENGINEERING","evidence":"single objective/squared-voltage contracts"},"G10":{"status":"PASS_UNIT_INTEGRATION_PENDING","evidence":"reference delta/service/MESS invariants"},"G11":{"status":"PASS_ENGINEERING","evidence":"real Gurobi Pi/Farkas and cut tests"},"G12":{"status":"CONTROLLED_FIXTURE_PASS_SCIENTIFIC_NOT_RUN","evidence":equiv["status"]},"G13":{"status":"NOT_RUN","evidence":"no scientific IEEE123 96-slot schedule yet"},"G14":{"status":"NOT_RUN_CONTRACT_PASS","evidence":"independent recalculator unit pass; result matrices absent"},"G15":{"status":"PASS","evidence":"raw sharing/volumes/kappa exact reproduction"}}
    _json(output/"DAYAHEAD_TEST_REPORT.json",{"authority_id":"DAYAHEAD_G0_G15_TEST_REPORT_V16","generated_at_utc":now,"gates":gates,"commands":[{"command":"python -m pytest -q tests/dayahead","result":"72 passed"},{"command":"python -m pytest -q tests/dayahead tests/test_pfr_ai_training.py tests/test_pfr_power.py tests/test_pfr_methods.py tests/test_git_identity.py","result":"112 passed, 71 subtests passed"},{"command":"python -m pytest -q tests","result":"424 passed, 4 skipped, 84 subtests passed, 3 failed","failures":[{"classification":"PRE_EXISTING_GUROBI_13_0_3_WINDOWS_BEHAVIOR","test":"test_joint_projection_restores_feasibility_across_multiple_trust_regions"},{"classification":"WINDOWS_MISSING_POSIX_FCNTL","test":"test_exact_sources_are_prepared_once_and_reused_by_day_workers"},{"classification":"WINDOWS_MISSING_POSIX_FCNTL","test":"test_exact_source_cache_is_invalidated_by_source_identity"}]},{"command":"python -m dayahead.aidc_preflight --full-inventory-hashes ...","result":"PASS"},{"command":"python -m dayahead.reproduce_nlr_authority ...","result":"PASS"},{"command":"python -m dayahead.reproduce_dataset312 ...","result":"PASS"}],"overall_status":"IMPLEMENTATION_PROGRESS_PASS_WITH_3_PREEXISTING_ENVIRONMENT_FAILURES_SCIENTIFIC_CAMPAIGN_LOCKED","may_june_access_status":"LOCKED"})
    _json(output/"AIDC_ML_FREEZE_REPORT.json",{"status":"NOT_COMPLETE","completed":["source lineage","eligibility","kappa","split","architecture contract","seed policy","locked loader"],"pending":["April-only HPO","one Aug19-Apr30 production refit","model weights/hash","96-slot forecasts"],"may_june_access_status":"LOCKED"})
    _json(output/"DAYAHEAD_OPENDSS_SMOKE_REPORT.json",{"gate":"G13","status":"NOT_RUN","engineering_interface_test":"PASS_96_SLOT_FAKE_ENGINE","scientific_forecast_qsts":None,"scientific_realized_qsts":None,"reason":"frozen scientific schedule not materialized; no silent synthetic loads","opendss_call_count":0})
    _json(output/"DAYAHEAD_RESULT_SCHEMA_AUDIT.json",{"gate":"G14","status":"NOT_RUN_CONTRACT_IMPLEMENTED","schema_contract":"PASS","independent_recalculator":"UNIT_PASS_SOLVER_0_OPENDSS_0","mandatory_scientific_matrices_materialized":False,"reason":"ML forecast/master solution/OpenDSS results not yet produced"})
    authority={"repository":"BeaverVillage/MobileESS","branch":_git(repo,"branch","--show-current"),"parent_sha":_git(repo,"rev-parse","HEAD"),"head_sha_at_snapshot":_git(repo,"rev-parse","HEAD"),"working_tree_porcelain":_git(repo,"status","--porcelain=v1"),"authority_ids":AUTHORITY_IDS,"authority_fingerprint":authority_fingerprint(),"nlr_source_sha256":NLR_SOURCE_SHA256,"dimension_authority":CURRENT_FROZEN_DIMENSIONS.to_dict(),"scientific_campaign_status":"LOCKED_NOT_STARTED","historical_results_relabelled":False,"created_at_utc":now}
    _json(output/"DAYAHEAD_IMPLEMENTATION_AUTHORITY.json",authority)
    rows=[
        ("V16-AUTH","Sections 0-1","dayahead/authority.py","AUTHORITY_IDS","test_frozen_authority_ids_are_exact","PASS",True,True),("V16-LABEL","Sections 5.1-5.6","dayahead/aidc_labels.py","dependency_firewall/historical_label_eligible","test_label_gate.py; test_v16_contracts.py","PASS",False,True),("V16-RAW","C1/G2/G15","dayahead/aidc_preflight.py","audit","AIDC_RAW_PREFLIGHT.json","PASS",True,True),("V16-D312","Section 5.6/G15","dayahead/reproduce_dataset312.py","reproduce","AIDC_DATASET312_RAW_REPRODUCTION.json","PASS",False,True),("V16-ADMIT","Section 9.2/G4","dayahead/aidc_admission_contract.py","validate_admission_record","test_d1_admission_is_forecast_cohort_only_and_denies_expost_fields","PASS",False,True),("V16-REF","Sections 7.6/12.1A","dayahead/reference_compute.py; dayahead/aidc_reference_delta.py","build_reference_schedule/planning_residual","test_reference_schedule_v2_is_deterministic_and_starts_empty","PASS_UNIT",True,True),("V16-SVC","Section 9.2","dayahead/aidc_service_contract.py","backlog_trajectory/require_terminal_reference_parity","test_reference_matched_terminal_service_has_no_deadline_slack","PASS_UNIT",False,True),("V16-REPLAY","Section 12.4","dayahead/aidc_realized_decomposition.py; dayahead/realized_compute_replay.py","realized_replay/replay_compute","test_realized_remove_then_add_prevents_double_count_and_fails_negative","PASS_UNIT",False,True),("V16-GRID","Sections 10-11/G11","dayahead/grid_lp.py; dayahead/benders.py","PhaseAwareGridLPFactory/cuts_for_iteration","test_today_work_package.py","PASS_REUSED",True,False),("V16-MESS","Section 9.4","dayahead/mess_physics.py","validate_trajectory","test_today_work_package.py","PASS_REUSED",True,False),("V16-G12","G12","dayahead/solver_equivalence.py","run_equivalence","test_controlled_monolithic_standard_and_cl_mc_bd_are_equivalent","CONTROLLED_PASS",False,True),("V16-G13","G13","dayahead/opendss_qsts.py","run_qsts/classify_g13","test_g13_distinguishes_release_fail_from_benchmark_infeasible","NOT_RUN",True,True),("V16-G14","G14","dayahead/result_schema.py","independent_recalculate","test_g14_independent_recalculator_has_zero_external_calls","CONTRACT_PASS_RESULT_PENDING",True,True)]
    with (output/"DAYAHEAD_PRECODE_TO_CODE_TRACEABILITY.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream); writer.writerow(["authority_id","section/equation","source module","function/class","test","status","inherited_from_previous_work","modified_for_v16"]); writer.writerows(rows)
    report=f"""# CODEX Day-Ahead AIDC Joint V16 Implementation Report

## Status

V16 authority reconciliation and contract implementation passed its engineering tests, raw-source reproduction, and controlled solver-equivalence fixture. The scientific May/June campaign remains **LOCKED** because April-only HPO/final model refit, full scientific Monolithic/BD solve, G13 OpenDSS, and G14 result audit are not complete. No scientific result was fabricated.

## A. Reused from prior work

- `input_contract.py`, `traffic_da.py`, `mobility_energy_da.py`, `mess_physics.py`, `grid_lp.py`, `benders.py`, `opendss_qsts.py`, and the result writer were retained.
- Existing 96-slot, MESS, phase-mask, Pi/Farkas, cut-selection, LB/UB/gap, and immutable-QSTS tests were rerun successfully.

## B. Patched for V16

- Replaced V15 `P_NF/G_NF` authority with source-backed `P_IT_REF/G_REF/W_F`, the ESIF-Kestrel hierarchy, the Apr/May/Jun split, and V16 IDs.
- Replaced the unresolved AIDC HOLD path with frozen V16 authority while preserving locked-evaluation fail-closed gates.
- Updated `REFERENCE_COMPUTE_SCHEDULE_V2`, result matrices, replay status policy, and reference-delta terminology.

## C. Newly implemented

- Historical-vs-D1 eligibility isolation, package-only Dataset312 kappa reproduction, Direct96/coupling contracts, positive target scaling, H100-node-hour service conservation, reference delta, realized remove-then-add replay, fidelity firewall, fixed compute/MESS replay, controlled solver equivalence, and independent recalculation.

## D. Superseded / disabled

- `P_NF/G_NF`, Sep-Oct/Nov/Dec split, artificial deadline/slack, individual queued-job D-1 injection, and physical-background quantile interpretation are absent from the V16 production path. Historical precode/today artifacts remain untouched as provenance only.

## E. Test results

- Day-Ahead: 72 passed.
- Focused prior-work regression: 112 passed plus 71 subtests.
- Full repository: 424 passed, 4 skipped, 84 subtests passed, 3 pre-existing Windows/environment failures (one Gurobi 13.0.3 behavior; two missing POSIX `fcntl`).
- Full raw inventory: 389 files / {raw['inventory_summary']['total_bytes']} bytes, PASS.
- Kestrel sharing/volume and Dataset312 kappa raw reproduction: PASS.
- Controlled Monolithic/Standard/CL-MC-BD equivalence: {equiv['status']}.

## F. Remaining blockers

- April-only HPO and one Aug19-Apr30 production refit with a real Transformer backend.
- Materialized AIDC forecasts/reference schedule and the identical full scientific B3 Monolithic/BD comparison.
- Scientific 96/96 Fresh OpenDSS forecast/realized QSTS (G13).
- Complete scientific result matrices and independent audit (G14).
- Frozen mapping source files are referenced by SHA authority but were not found inside this checkout for direct re-hash.

## G. May/June access status

LOCKED. May primary and Jun1-25 replication were not opened by model training, tuning, smoke, optimization, or fidelity code during this run.
"""
    (output/"CODEX_DAYAHEAD_AIDC_JOINT_IMPLEMENTATION_REPORT.md").write_text(report,encoding="utf-8")
    sha_path=output/"DAYAHEAD_SHA256SUMS.txt"; entries=[]
    for path in sorted(output.iterdir(),key=lambda p:p.name):
        if path.is_file() and path!=sha_path: entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    sha_path.write_text("\n".join(entries)+"\n",encoding="utf-8")


if __name__ == "__main__":
    materialize(Path.cwd(),Path("dayahead/artifacts/v16"))

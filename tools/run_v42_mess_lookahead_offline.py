"""Read immutable PR221 candidate evidence; offline metrics, no new UB/solve."""
import argparse
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.mess_minimax_lookahead import candidate_metrics,duplicate_groups,offline_outcome_scope

PR221="a874df15b9a306a7d769a60622b40fb76de3ffcc"
REFERENCE="4624039ca376db7aeae1e08709441d545b350eeb"
PREFIX="docs/v42_b2_adaptive_perf_v3/"
BASE=ROOT/"docs/v42_unified_aidc_mess_research_20261014"
OUT=BASE/"D0_STATE_CONDITIONED_PLANNING_20261015"
RUNTIME=ROOT/"runtime/D0_MESS_BEAM_OFFLINE_20261015"


def write_new(path,value):
    if Path(path).exists():raise ValueError("D0_MESS_EVIDENCE_ALREADY_EXISTS:"+str(path))
    _write(path,value)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--finish-reports-only",action="store_true");args=p.parse_args()
    if args.finish_reports_only:
        scope=json.loads((OUT/"MESS_BEAM_LOOKAHEAD_OFFLINE_STATUS.json").read_text(encoding="utf8"))
        return finish_reports(scope)
    RUNTIME.mkdir(parents=True,exist_ok=False);OUT.mkdir(parents=True,exist_ok=True);sources={}
    def extract(name):
        raw=subprocess.check_output(["git","show",PR221+":"+PREFIX+name],cwd=ROOT)
        target=RUNTIME/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        sources[name]=dict(git_ref=PR221+":"+PREFIX+name,**file_record(target))
        return raw
    source_csv=list(csv.DictReader(io.StringIO(extract("V3_CANDIDATE_SCORE_SELECTION_AND_JOINT_OUTCOME.csv").decode("utf-8-sig"))))
    outcomes=list(csv.DictReader(io.StringIO(extract("V3_POOL_PREDICTION_VS_JOINT_UB.csv").decode("utf-8-sig"))))
    state=json.loads(extract("FINAL_STATE.json"));relation=json.loads(extract("SCORE_RESULT_RELATION.json"))
    native=list(csv.DictReader(io.StringIO(extract("ALL_NATIVE_SOLVER_METRICS.csv").decode("utf-8-sig"))))
    bykey={}
    for r in source_csv:
        if r["formulation"]=="DIRECT":bykey[int(r["epoch"]),r["unit"],r["path_signature"]]=r
    metrics=[];pool_summary=[]
    for epoch in range(1001,1013):
        diag=json.loads(extract(f"CANDIDATE_DIAGNOSTICS_{epoch}.json"));rows=diag["critical_rows"]
        if not diag["PASS"] or not diag["all96_slot_coverage"] or {r["slot"] for r in rows}!=set(range(96)):
            raise ValueError("ORIGINAL_PR221_ALL96_CRITICAL_CONTEXT_REQUIRED")
        current=[]
        for c in diag["candidates"]:
            m=candidate_metrics(c,rows);m.update(epoch=epoch,pool_signature=diag["pool_signature"])
            native_row=bykey[epoch,m["unit"],m["path_signature"]]
            m.update(actual_DIRECT_selected_lambda=float(native_row["selected_lambda"]),
                pool_level_actual_joint_FULL_UB=float(native_row["joint_pool_FULL_UB"]),
                original_FULL_passed=int(next(r["FULL_PASS"] for r in state["v3_iterations"] if r["epoch"]==epoch and r["formulation"]=="DIRECT")),
                existing_terminal_SOC_heuristic=float(native_row["terminal_SOC"]),
                actual_individual_forced_route_UB_observed=False)
            metrics.append(m);current.append(m)
        pool_summary.append(dict(epoch=epoch,records=len(current),unit_count=len({r["unit"] for r in current}),
            positive_rebound_routes=sum(m["maximum_positive_rebound"]>1e-9 for m in current),
            existing_path_charge_rebound_routes=sum(m["existing_path_charge_rebound_max"]>1e-9 for m in current),
            near_critical_arrival_late_routes=sum(m["near_critical_rows_before_destination_connect"]>0 for m in current),
            predicted_critical_switch_routes=sum(m["critical_asset_phase_slot_switch"] for m in current),
            existing_minimax_score_min=min(m["existing_Minimax_score"] for m in current),
            existing_minimax_score_max=max(m["existing_Minimax_score"] for m in current),
            actual_joint_FULL_UB=current[0]["pool_level_actual_joint_FULL_UB"],
            individual_forced_route_FULL_UB=None,new_UB=None,Native_optimize_calls=0))
    path=OUT/"MESS_BEAM_OFFLINE_CANDIDATE_METRICS.csv"
    if path.exists():raise ValueError("D0_BEAM_NEW_METRICS_ALREADY_EXISTS")
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(metrics[0]));w.writeheader()
        for r in metrics:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
    outcome_scope=offline_outcome_scope(outcomes);duplicates=duplicate_groups(metrics)
    scope=dict(status="DIAGNOSTIC_ONLY",source_scope="IMMUTABLE_ORIGINAL_PR221_4X24_NOT_NEW_D0",
        original_PR221_commit=PR221,metrics=file_record(path),literal_source_files=sources,
        pool_summary=pool_summary,duplicate_analysis=duplicates,outcome_scope=outcome_scope,
        actual_improved_Beam_Joint_run="NOT_RUN",new_FULL_UB=None,new_UB_improvement=None,
        original_signed_PQ_multi_critical_SOC_rebound_reused=True,
        minimax_lateness_rebound_and_asset_switch_are_offline_diagnostics=True,
        experimental_rank_is_opt_in_and_not_connected_to_official_generator=True,
        route_conditional_LP_candidate_selector="ALREADY_PRESENT_PR222_JOINT_DISPATCH_SCORE;NO_NEW_NATIVE_REPETITION",
        new_ranking_will_require_same_case_joint_run_and_original_FULL_raw_validation=True,
        correlation_with_independent_route_FULL_UB="NOT_CERTIFIED_NO_INDIVIDUAL_LABELS",
        source_predecessor_relation=relation,Native_optimize_calls=0)
    write_new(OUT/"MESS_BEAM_LOOKAHEAD_OFFLINE_STATUS.json",scope)
    finish_reports(scope)


def finish_reports(scope):
    sources=scope["literal_source_files"];duplicates=scope["duplicate_analysis"];outcome_scope=scope["outcome_scope"]
    for name in ("FINAL_STATE.json","ALL_NATIVE_SOLVER_METRICS.csv"):
        actual=file_record(sources[name]["path"])
        if actual["sha256"]!=sources[name]["sha256"]:raise ValueError("PR221_FINISH_LITERAL_SOURCE_BYTES_DRIFT")
    state=json.loads(Path(sources["FINAL_STATE.json"]["path"]).read_text(encoding="utf8"))
    native=list(csv.DictReader(io.StringIO(Path(sources["ALL_NATIVE_SOLVER_METRICS.csv"]["path"]).read_text(encoding="utf-8-sig"))))
    core=["v42_integration/m_engine.py","v42_integration/m_candidates.py","v42_integration/mess_scaling.py"]
    unchanged=subprocess.run(["git","diff","--exit-code",REFERENCE,"--",*core],cwd=ROOT,capture_output=True).returncode==0
    if not unchanged:raise ValueError("MESS_OFFICIAL_BASELINE_CORE_CHANGED")
    historical=dict(case_sha="34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292",
        UB=float(state["BEST_GLOBAL_UB"]["UB"]),K48_Global_LB=float(state["Global_LB"]),
        Global_Gap_percent=float(state["Global_Gap_percent"]),scope="ORIGINAL_EXACT_HISTORICAL_CASE_ONLY")
    audit=dict(status="PASS",Official_UB_algorithm="Adaptive Beam -> 4-MESS Joint MILP -> Original FULL validation -> Incumbent Registry",
        Official_Global_LB_algorithm="K48 -> Certified same-stage/source/case Global LB",
        vehicles=4,candidate_nodes=24,slots=96,STAY_single_multiple_MOVE_and_P_Q_SOC_rebound_preserved=True,
        default_Direct_Compact_Joint_MILP=True,experimental_grid_compression_enabled=False,
        DW_replaces_official_UB_or_K48=False,S1_full_MILP_replaces_official_algorithm=False,
        exact_baseline_reference=REFERENCE,baseline_core_unchanged=unchanged,core_sources=[file_record(ROOT/p) for p in core],
        existing_BEST_FULL_incumbent_preserved=True,new_incumbent_registry_insertions=0,
        historical_reference=historical,new_D0_MESS_UB=None,new_D0_K48_Global_LB=None,new_D0_Global_Gap=None,
        actual_new_D0_M1_M2="NOT_RUN",candidate_metric_uses_no_FULL_UB_or_Global_LB_claim=True,
        archived_source_evidence=sources,Native_optimize_calls=0)
    write_new(OUT/"MESS_OFFICIAL_ALGORITHM_AUDIT.json",audit)
    comparison=[]
    for epoch in range(1001,1013):
        actual=next(r for r in state["v3_iterations"] if r["epoch"]==epoch and r["formulation"]=="DIRECT")
        timing=next(r for r in native if r["epoch"]==str(epoch) and r["formulation"]=="DIRECT")
        comparison.append(dict(variant="HISTORICAL_PR221_DIRECT_JOINT",epoch=epoch,source_scope="ORIGINAL_HISTORICAL_CASE",
            actual_joint_FULL_UB=actual["ObjVal"],Original_FULL_PASS=actual["FULL_PASS"],Native_Runtime=actual["Native_Runtime"],
            worker_wall_seconds=timing["Worker_wall"],native_model_build_wall_seconds=timing["model_build_wall"],
            restricted_ObjBound=actual["restricted_ObjBound"],restricted_bound_is_Global_LB=False,new_UB_improvement=0.,
            new_Beam_offline_rank_UB="",new_D0_UB="",status="PASS_HISTORICAL_ONLY"))
    comparison.append({k:"" for k in comparison[0]});comparison[-1].update(variant="NEW_OFFLINE_LOOKAHEAD_ONLY",source_scope="DIAGNOSTIC_ONLY",
        status="NO_NEW_UB_NOT_RUN",restricted_bound_is_Global_LB=False)
    with (OUT/"BEAM_JOINT_UB_COMPARISON.csv").open("x",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(comparison[0]));w.writeheader();w.writerows(comparison)
    lb=dict(status="NOT_CERTIFIED_NEW_D0_BOUND_NOT_RUN",Official_Global_LB_method="K48",K48_preserved_as_default=True,
        historical_original_4x24_reference=historical,new_D0_K48_Global_LB=None,new_D0_Global_Gap=None,
        S1_scope="REDUCED_HISTORICAL_2_UNITS_5_NODES_FULL96_ONLY",S1_valid_bound=0.609063011458436,
        S1_bound_transferred_to_original4x24_or_D0=False,new_valid_bound_improvement=None,
        existing_root_diagnosis=file_record(OUT/"S1_ACTUAL_ROOT_LITERAL_DIAGNOSIS.json"),
        controlled_fixation_experiments=file_record(OUT/"S1_ROUTE_MODE_SOC_EXPERIMENTS.json"),
        Route_Mode_gap_dominant_cause="NOT_CERTIFIED_B_C_D_NOT_RUN",
        new_strengthening_selected="DEFER_UNTIL_CAUSAL_FIXATION_RESULTS_AND_COST_EVIDENCE",
        research_candidates=["SOURCE_VALID_ROUTE_SOC_MODE_INTEGER_HULL","FULL_VEHICLE_SCHEDULE_DW","COMPLETE_ORIGINAL_DOMAIN_PRICING","VALID_K48_INEQUALITIES"],
        DW_is_only_research=True,DW_pricing_or_dual_certificate="NOT_RUN",
        route_only_flow_DW_is_not_new_integer_hull_strength=True,
        finite_Beam_or_restricted_master_objective_is_Global_LB=False,
        require_all_original_route_SOC_binary_Mode_P_Q_domain_and_independent_dual_certificate=True,
        previous_Mode384_and_SOC384_experiments_repeated=False,same_pool_compression_or_cache_timing_repeated=False,
        Native_optimize_calls=0)
    write_new(OUT/"K48_GLOBAL_LB_RESEARCH_STATUS.json",lb)
    print(json.dumps(dict(status="PASS",Native_optimize_calls=0,candidates=duplicates["candidate_records"],
        unique_unit_paths=duplicates["unique_exact_unit_paths"],repeated_exact_occurrences=duplicates["repeated_exact_path_occurrences"],
        actual_pool_UB_variation=outcome_scope["distinct_joint_FULL_UBs"],new_UB=None,output=str(OUT)),indent=2))


if __name__=="__main__":main()

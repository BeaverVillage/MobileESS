"""Fresh Native0 cache/S1 receipts; never overwrite historical evidence."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import shutil
import sys
from time import perf_counter

import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record,matrix_sha,domain_sha,vector_sha
from v42_integration.mess_scaling import checked,validate_stay_physics
from v42_integration.mess_joint_compression import compress_joint_packet,replay_same_pool_rows
from v42_integration.mess_verified_packet_cache import seal_verified_packet,restore_verified_packet
from v42_integration.mess_s1_research import soc_route_hull_rows,full_vehicle_dw_plan
from v42_integration.unified_contract import digest
from tools.audit_v42_original_beam_joint import load_packet
from tools.audit_v42_s1_fractionality import original_authority

OUT=ROOT/"docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP"
BASE=ROOT/"runtime/v42_unified/MESS_EXACT_COMPRESSION_COMPARE01"


def read(path):return json.loads(Path(path).read_text(encoding="utf8"))


def write_new(path,document):
    if Path(path).exists():raise ValueError("MESS_CONTINUATION_HISTORICAL_EVIDENCE_CANNOT_BE_OVERWRITTEN:"+str(path))
    _write(path,document)


def original_application_replay(domain,point,manifest,source_physical):
    """Call unchanged Original validators on literal Raw and fixed source Q."""
    from v42_native.mess import RouteArc,Battery,validate
    from v42_bootstrap.attribution import supplemental_physical
    before=vector_sha(point);battery=Battery(**manifest["original_battery"]);battery.validate()
    table=read_route_table(manifest)
    records=[];seen=set()
    for index in manifest["original_route_record_indices"]:
        row=table["routes"][index]
        physical=(row["origin_service_id"],row["departure_slot_15"],row["destination_service_id"],
                  row["departure_slot_15"]+row["connection_ready_slots_15min"],row["energy_safe_kwh"])
        if physical in seen:continue
        seen.add(physical)
        route=RouteArc(f"{physical[0]}:{physical[2]}:{physical[1]}",physical[0],physical[2],physical[1],
            physical[1]+row["travel_slots_15min"],physical[3],physical[4],digest(row))
        route.validate(96);records.append(route)
    values=dict(zip(map(str,domain["names"]),map(float,point)));sites=manifest["charging_sites"]
    units=manifest["optimization_units"]
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[
        (r.source,r.depart,r.destination,r.connect,r) for r in records]
    discrete=point[domain["types"]!="C"]
    if not np.all(discrete==np.rint(discrete)):raise ValueError("MESS_S1_LITERAL_RAW_INTEGER_PATTERN_REQUIRED")
    selected={}
    for u in units:
        for k in range(len(arcs)):values.setdefault(f"arc[{u},{k}]",0.)
        selected[u]=[k for k in range(len(arcs)) if values[f"arc[{u},{k}]"]==1.]
        for s in sites:
            for t in range(96):
                for prefix in ("Pch","Pdis","Q"):values.setdefault(f"{prefix}[{u},{s},{t}]",0.)
    plan=dict(values=values,chosen_arcs=selected,mode="MILP",
        initial_sites={u:manifest["original_initial_sites"][u] for u in units})
    physical=validate(plan,sites,records,battery,96);mode=supplemental_physical(plan,sites,battery)
    # The inactive source is a literal four-unit STAY anchor; replay it again,
    # including its Q, instead of copying the old PASS certificate.
    stay=read(checked(manifest["inactive_stay_source"]))
    inactive=validate_stay_physics(stay,tuple(table["service_ids"]),[],battery,manifest["original_initial_sites"])
    moved={u:[dict(route_id=arcs[k][-1].route_id,energy_kwh=arcs[k][-1].energy_kwh,
        depart=arcs[k][1],connect=arcs[k][3]) for k in selected[u] if arcs[k][-1] is not None] for u in units}
    return dict(PASS=bool(source_physical["PASS"] and physical["PASS"] and mode["charge_mode_and_connection_PASS"] and inactive["PASS"]),
        active_original_route_SOC_PCS=physical,active_original_mode_connection=mode,
        inactive_literal_STAY_Q_source_replayed=inactive,active_selected_MOVE_arcs=moved,
        literal_integer_axis=True,Raw_SHA_before=before,Raw_SHA_after=vector_sha(point),
        Raw_unchanged=before==vector_sha(point),zero_constants_only_for_original_reachability_removed_columns=True,
        Original_4x24_grid_certificate_transferred=False,current_C1_application_acceptance=False,
        source_scope="HISTORICAL_S1_FIXED_AIDC_ANCHOR_DIAGNOSTIC_NOT_CURRENT_C1",Native_optimize_calls=0)


def read_route_table(manifest):
    return json.loads(gzip.decompress(checked(manifest["original_route_source"]).read_bytes()))


def fresh_original_csr_raw_replay(attempt):
    import psutil
    if psutil.virtual_memory().available<8*1024**3:raise RuntimeError("MESS_S1_FRESH_RAW_PRELOAD_8GB_RAM_GATE")
    cert=read(ROOT/"docs/v42_unified_aidc_mess_research_20261014/MEASURED_MESS_FULL96/FULL96_COMPRESSION_CERTIFICATE.json")
    oracle=read(OUT/"MESS_S1_INTEGER_ORACLE_CONTINUATION_01.json")
    began=perf_counter()
    with np.load(checked(cert["original_full_native_domain"]),allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    A=sparse.load_npz(checked(cert["original_full_native_CSR"])).tocsr()
    if domain_sha(d)!=cert["original_domain_sha"] or matrix_sha(A)!=cert["captured_original_matrix_sha"]:
        raise ValueError("MESS_S1_FRESH_ORIGINAL_CSR_DOMAIN_SHA_DRIFT")
    with np.load(checked(oracle["Raw"]),allow_pickle=False) as z:point=z["point"].copy()
    before=vector_sha(point)
    from v42_m1_research.check_ub import matrix_replay
    replay=matrix_replay(A,d,point)
    if not replay["PASS"] or not replay["integer_pattern_exact"] or before!=vector_sha(point):
        raise ValueError("MESS_S1_FRESH_ORIGINAL_ALL_ROW_LITERAL_RAW_REPLAY_REJECTED")
    record=dict(status="PASS",source_scope="HISTORICAL_S1_FIXED_AIDC_ANCHOR_DIAGNOSTIC_NOT_CURRENT_C1",
        source_identity=cert["identity"],original_CSR=cert["original_full_native_CSR"],
        original_domain=cert["original_full_native_domain"],original_grid_and_physical_all_row_replay=replay,
        Raw=oracle["Raw"],Raw_unchanged=True,Raw_vector_sha=before,numeric_repairs=0,
        fresh_CSR_domain_load_hash_and_all_row_validation_wall_seconds=perf_counter()-began,
        Original_4x24_Global_LB=None,Native_optimize_calls=0)
    target=OUT/f"MESS_CONTINUATION_20324_ATTEMPT{attempt:02d}"/"S1_ORIGINAL_CSR_FRESH_RAW_REPLAY.json"
    write_new(target,record)
    plan=full_vehicle_dw_plan(d,cert["identity"],read(BASE/"S1_SELECTION_AND_SOURCE.json")["optimization_units"])
    write_new(target.parent/"S1_FULL_VEHICLE_DW_RESEARCH_PLAN.json",plan)
    print(json.dumps(dict(status="PASS",rows=replay["rows"],variables=replay["columns"],
        residual=replay["maximum_observed_row_violation"],wall=record["fresh_CSR_domain_load_hash_and_all_row_validation_wall_seconds"],
        Native_optimize_calls=0,report=str(target)),indent=2))


def finalize_current_drafts(attempt):
    """Finish only this continuation's three new drafts before Git delivery."""
    detail=OUT/f"MESS_CONTINUATION_20324_ATTEMPT{attempt:02d}"
    fresh=read(detail/"S1_ORIGINAL_CSR_FRESH_RAW_REPLAY.json")
    if fresh["status"]!="PASS":raise ValueError("MESS_FINAL_NEW_DRAFT_FRESH_RAW_REPLAY_REQUIRED")
    oracle=read(OUT/"MESS_S1_INTEGER_ORACLE_CONTINUATION_01.json")
    saved={}
    sources={"INTEGER_ORACLE_RAW.npz":Path(oracle["Raw"]["path"]),
        "INTEGER_ORACLE_NATIVE_GUROBI.log":ROOT/"runtime/MESS_CONTINUATION_20324/S1_INTEGER_ORACLE_ATTEMPT01/NATIVE.log",
        "INTEGER_ORACLE_NATIVE0_READBACK.json":ROOT/"runtime/MESS_CONTINUATION_20324/S1_INTEGER_ORACLE_ATTEMPT01/NATIVE0_READBACK.json",
        "INTEGER_ORACLE_SOURCE_SPECIFICATION.json":Path(oracle["specification"]["path"]),
        "FRACTIONAL_SOURCE_ROOT_RAW.npz":ROOT/"runtime/FOLLOWUP_S1_LP_30S/LP_POINT.npz",
        "INITIAL_SAME_POOL_COMPRESSION_CERTIFICATE.json":ROOT/f"runtime/MESS_CONTINUATION_20324/NATIVE0_ATTEMPT{attempt:02d}/INDEPENDENT_PROOF/JOINT_GRID_COMPRESSION_CERTIFICATE.json"}
    for name,source in sources.items():
        target=detail/name
        if target.exists():raise ValueError("MESS_CURRENT_DRAFT_RAW_MUST_NOT_REPLACE_EXISTING_EVIDENCE")
        shutil.copyfile(source,target)
        saved[name]=dict(**file_record(target),literal_source=file_record(source))
        if saved[name]["sha256"]!=saved[name]["literal_source"]["sha256"]:raise ValueError("MESS_RAW_COPY_BYTE_DRIFT")
    write_new(detail/"PRESERVED_NEW_RAW_AND_NATIVE_EVIDENCE.json",saved)
    initial=read(detail/"INITIAL_SAME_POOL_COMPRESSION_CERTIFICATE.json")
    write_new(detail/"PRESERVED_INITIAL_ROW_PROOF_EVIDENCE.json",dict(status="PASS",
        certificate=file_record(detail/"INITIAL_SAME_POOL_COMPRESSION_CERTIFICATE.json"),
        removed_row_witness=file_record(ROOT/f"runtime/MESS_CONTINUATION_20324/NATIVE0_ATTEMPT{attempt:02d}/INDEPENDENT_PROOF/JOINT_REMOVED_ROW_WITNESSES.npz"),
        large_witness_kept_in_runtime=True,existing_standard_row_witness_cache_hit=initial["cache_hit"],
        all_deleted_rows_independently_reverified=initial["independently_verified"]["all_removed_rows_proven"],Native_optimize_calls=0))
    global_path=OUT/"MESS_GLOBAL_LB_RESEARCH_STATUS.json";lb=read(global_path)
    if lb["new_method"]!="ORIGINAL_ROUTE_MODE_SOC_DISJUNCTIVE_INTEGER_HULL":raise ValueError("MESS_FINALIZE_CURRENT_CONTINUATION_DRAFT_ONLY")
    lb.update(fresh_original_CSR_all_row_raw_replay=file_record(detail/"S1_ORIGINAL_CSR_FRESH_RAW_REPLAY.json"),
        preserved_literal_RAW_and_Native_evidence=file_record(detail/"PRESERVED_NEW_RAW_AND_NATIVE_EVIDENCE.json"),
        next_selected_method="FULL_VEHICLE_SCHEDULE_DANTZIG_WOLFE",next_selected_method_status="NOT_RUN",
        next_selected_method_plan=file_record(detail/"S1_FULL_VEHICLE_DW_RESEARCH_PLAN.json"),
        actual_root_diagnosis=dict(fractional_route_Arcs=4307,fractional_Mode=192,multiple_location_vehicle_slots=187,
            simultaneous_charge_discharge_vehicle_slots=192,S1_integer_gap_percent=oracle["MIPGap"]*100),
        next_selected_method_reason="Observed fractional route/location and joint SOC/Mode/PQ coupling motivate the full vehicle schedule hull. Actual SOC candidate inequalities are slack; no LB gain or successful pricing is claimed.",
        next_research_gate="Each active vehicle needs complete original route/SOC/binaryMode/PQ pricing under one master dual and independently verified outward dual feasibility. Route-only flow columns and finite or restricted Beam pricing cannot certify Global LB.",
        research_module_source=file_record(ROOT/"v42_integration/mess_s1_research.py"),
        route_only_DW_strengthens_network_flow=False,complete_DW_pricing_and_dual_certificate="NOT_RUN")
    _write(global_path,lb)
    cache_path=OUT/"MESS_BEAM_COMPRESSION_FOLLOWUP.json";cache=read(cache_path)
    cache.update(measured_reuse_samples=1,
        first_independent_proof_plus_complete_seal_wall_seconds=cache["initial_independent_proof_wrapper_wall_seconds"]+cache["first_cache_creation_IO_and_hash_wall_seconds"],
        complete_reuse_includes="Actual original source CSR/domain/lift/Start/proof/pool hashing, external manifest seal, all compressed packet byte hashing, compressed packet restore and numeric identity checks",
        first_build_includes="Fresh independent same-pool row proof plus complete NPZ packet writing and sealing; original source packet restore measured separately",
        old_Native_plus_new_cache_is_not_a_fresh_total_performance_benchmark=True,
        initial_standard_row_witness_cache_reused=initial["cache_hit"],initial_all_row_theorem_independently_reverified=True,
        cold_new_pool_row_proof_construction_wall="NOT_RUN",
        initial_verified_row_proof_evidence=file_record(detail/"PRESERVED_INITIAL_ROW_PROOF_EVIDENCE.json"),
        cache_module_source=file_record(ROOT/"v42_integration/mess_verified_packet_cache.py"))
    _write(cache_path,cache)
    print(json.dumps(dict(status="PASS",current_new_drafts_finalized=True,Native_optimize_calls=0,
        preserved_literal_files=list(saved)),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--attempt",type=int,default=1)
    parser.add_argument("--raw-replay-only",action="store_true")
    parser.add_argument("--finalize-current-drafts",action="store_true")
    args=parser.parse_args()
    if args.raw_replay_only and args.finalize_current_drafts:parser.error("Choose one Native0 operation")
    if args.finalize_current_drafts:finalize_current_drafts(args.attempt);return
    if args.raw_replay_only:fresh_original_csr_raw_replay(args.attempt);return
    runtime=ROOT/f"runtime/MESS_CONTINUATION_20324/NATIVE0_ATTEMPT{args.attempt:02d}"
    runtime.mkdir(parents=True,exist_ok=False)
    detail=OUT/f"MESS_CONTINUATION_20324_ATTEMPT{args.attempt:02d}"
    if detail.exists():raise ValueError("MESS_CONTINUATION_REPORT_ATTEMPT_ALREADY_EXISTS")
    detail.mkdir()
    import psutil
    if psutil.virtual_memory().available<8*1024**3:raise RuntimeError("MESS_NATIVE0_CACHE_SOURCE_PRELOAD_8GB_RAM_GATE")
    historical_csv=list(csv.DictReader((OUT/"MESS_COMPRESSION_TOTAL_WALL.csv").open(encoding="utf8")))
    source=read(OUT/"MESS_4X24_NATIVE_COMPARISON.json");identity=source["identity"]
    began=perf_counter();original,spec=load_packet(ROOT/"runtime/FOLLOWUP_ORIGINAL_BEAM_JOINT/ORIGINAL")
    source_restore_wall=perf_counter()-began
    proof_begin=perf_counter()
    compressed=compress_joint_packet(original,identity=identity,cache_dir=ROOT/"runtime/FOLLOWUP_ORIGINAL_BEAM_JOINT/CACHE",
        output=runtime/"INDEPENDENT_PROOF")
    proof_wrapper_wall=perf_counter()-proof_begin
    seal=seal_verified_packet(original,compressed,identity=identity,folder=runtime/"SEALED_SAME_POOL_PACKET")
    # Keep this external approved SHA receipt outside the sealed packet folder.
    # Reuse below reads that retained receipt, not an untrusted local manifest.
    write_new(detail/"EXTERNAL_APPROVED_PACKET_SEAL.json",seal)
    del compressed
    approved=read(detail/"EXTERNAL_APPROVED_PACKET_SEAL.json")
    restored,reuse=restore_verified_packet(original,identity=identity,folder=runtime/"SEALED_SAME_POOL_PACKET",
        approved_manifest_sha=approved["approved_manifest"]["sha256"])
    replay_begin=perf_counter()
    start_replay=dict(original=replay_same_pool_rows(original,restored,original[3]),
        compressed=replay_same_pool_rows(restored,restored,original[3]))
    replay_wall=perf_counter()-replay_begin
    if not start_replay["original"]["PASS"] or not start_replay["compressed"]["PASS"]:
        raise ValueError("MESS_SEALED_SAME_POOL_START_RAW_REPLAY_REJECTED")
    write_new(detail/"SAME_POOL_PACKET_RESTORE.json",dict(status="PASS",source_identity=identity,
        source_restore_wall_seconds=source_restore_wall,first_independent_compression_wrapper_wall_seconds=proof_wrapper_wall,
        initial_seal=seal,reuse=reuse,raw_start_original_and_compressed_replay=start_replay,
        raw_start_replay_wall_seconds=replay_wall,Native_optimize_calls=0))
    # Free the 4x24 packet before loading the reduced source domain.
    del restored,original
    cert=read(ROOT/"docs/v42_unified_aidc_mess_research_20261014/MEASURED_MESS_FULL96/FULL96_COMPRESSION_CERTIFICATE.json")
    manifest=read(BASE/"S1_SELECTION_AND_SOURCE.json")
    with np.load(checked(cert["original_full_native_domain"]),allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    if domain_sha(d)!=cert["original_domain_sha"]:raise ValueError("MESS_S1_ORIGINAL_DOMAIN_SHA_DRIFT")
    physical,_,_,_,authority=original_authority(d,manifest)
    with np.load(ROOT/"runtime/FOLLOWUP_S1_LP_30S/LP_POINT.npz",allow_pickle=False) as z:point=z["point"].copy()
    diag=soc_route_hull_rows(physical,d,point,source_integer_authority=authority)
    diag.update(original_source_authority=authority,source_identity=cert["identity"],
        actual_root_receipt=file_record(OUT/"S1_ROOT_FRACTIONALITY.json"),
        actual_saved_LP_raw=file_record(ROOT/"runtime/FOLLOWUP_S1_LP_30S/LP_POINT.npz"),
        decision="DO_NOT_RUN_NONVIOLATED_SOC_HULL_CUTS",Native_optimize_calls=0)
    write_new(detail/"S1_SOC_ROUTE_HULL_ACTUAL_ROOT_SEPARATION.json",diag)
    oracle_path=OUT/"MESS_S1_INTEGER_ORACLE_CONTINUATION_01.json"
    oracle=read(oracle_path)
    with np.load(checked(oracle["Raw"]),allow_pickle=False) as z:integer=z["point"].copy()
    replay=original_application_replay(d,integer,manifest,authority)
    replay.update(original_grid_physical_all_row_replay=oracle["original_grid_physical_row_replay"],
        original_CSR=cert["original_full_native_CSR"],original_domain=cert["original_full_native_domain"],
        Raw=file_record(oracle["Raw"]["path"]),same_S1_ObjVal=oracle["ObjVal"],same_S1_full_domain_ObjBound=oracle["same_S1_full_domain_ObjBound"])
    if not replay["PASS"] or not replay["Raw_unchanged"] or not oracle["original_grid_physical_row_replay"]["PASS"]:
        raise ValueError("MESS_S1_ORACLE_UNMODIFIED_ORIGINAL_APPLICATION_RAW_REPLAY_REJECTED")
    write_new(detail/"S1_INTEGER_ORACLE_ORIGINAL_APPLICATION_RAW_REPLAY.json",replay)
    previous={r["variant"]:float(r["measured_same_pool_wall_excluding_shared_packet_creation"]) for r in historical_csv}
    frozen_history=[file_record(OUT/name) for name in ("MESS_4X24_NATIVE_COMPARISON.json","MESS_COMPRESSION_TOTAL_WALL.csv",
        "JOINT_GRID_COMPRESSION_CERTIFICATE.json","ORIGINAL_BEAM_FULL_RAW_REPLAY.json","S1_MODE_HULL_LP_COMPARISON.json")]
    compression=dict(status="DIAGNOSTIC_ONLY",method="EXTERNAL_SHA_SEALED_COMPLETE_SAME_POOL_PACKET_RESTORE",
        exact_original_4x24_same_pool=True,source_identity=identity,historical_measured_total_wall_seconds=previous,
        historical_evidence_preserved=frozen_history,initial_independent_proof_wrapper_wall_seconds=proof_wrapper_wall,
        first_cache_creation_IO_and_hash_wall_seconds=seal["first_seal_IO_and_hash_wall_seconds"],
        complete_cache_reuse_wall_seconds=reuse["cache_reuse_wall_seconds"],source_packet_restore_wall_seconds=source_restore_wall,
        reuse_stage_speedup_vs_prior_9_24321110000892_second_proof_only=9.24321110000892/reuse["cache_reuse_wall_seconds"],
        new_source_case_pool_reuse_allowed=False,unchanged_same_pool_integer_and_LP_domain=True,
        Original_FULL_vs_restricted_joint_domain_equality_claimed=False,external_approved_seal=file_record(detail/"EXTERNAL_APPROVED_PACKET_SEAL.json"),
        new_Native_solver_timing="NOT_RUN",new_total_Beam_iteration_timing="NOT_RUN",new_FULL_UB=None,
        total_solver_or_Beam_speedup="NOT_CERTIFIED",compression_default_enabled=False,
        protected_original_FULL_UB=0.5398310226338695,Native_optimize_calls=0)
    diversity=dict(status="NOT_RUN",original_operation="Adaptive Beam -> 4-MESS Joint MILP -> Original FULL validator -> Incumbent Registry",
        source_identity=identity,all_physical_vehicles=4,candidate_nodes=24,slots=96,
        fixed_per_vehicle_pool_counts={u:len(p) for u,p in spec["pools"].items()},
        source_scope="ORIGINAL_HISTORICAL_FIXED_POOL;NOT_NEW_CURRENT_C1",
        experimental_selector_source=file_record(ROOT/"v42_integration/mess_beam_diversity.py"),
        STAY_and_current_and_previous_moving_paths_protected=True,
        exploration="ALL_VEHICLES_DESTINATIONS_DEPARTURE_BANDS_SINGLE_MULTIPLE_MOVE_REBOUND_SOC_P_Q_PCS",
        scoring="EXISTING_SIGNED_JOINT_MULTI_CRITICAL_P_Q_SCORE;HEURISTIC_RANKING_ONLY",
        original_IEEE123_signed_electrical_response_preserved=True,
        proof_based_SOC_necessary_rejections_separated_from_fixed_heuristic_candidate_cap=True,
        actual_original4x24_diversified_Beam_generation="NOT_RUN",actual_new_Beam_joint_MILP="NOT_RUN",
        new_FULL_validated_UB=None,new_UB_improvement=None,total_Beam_iteration_performance="NOT_CERTIFIED",
        historical_FULL_UB=0.5398310226338695,registry_insertion_calls=0,Native_optimize_calls=0,
        reason="CURRENT_C1_NEW_BOUNDARY_NOT_CERTIFIED_AND_SHARED_NATIVE_BUDGET_RESERVED_FOR_S1_EXACT_FULL_DOMAIN_DIAGNOSTIC",
        default_selector_enabled=False)
    lb=dict(status="NOT_CERTIFIED",source_scope="HISTORICAL_S1_FIXED_AIDC_ANCHOR_DIAGNOSTIC_NOT_CURRENT_C1",
        same_S1_source_identity=cert["identity"],actual_saved_root_LP=0.6090630116056528,
        new_S1_integer_oracle_receipt=file_record(oracle_path),oracle_Native_Runtime=oracle["Native_Runtime"],
        bounded_full_domain_reference=dict(method="ORIGINAL_S1_FULL_ROUTE_INTEGER_BRANCH_AND_BOUND",cap_seconds=40.,
            same_S1_original_domain_preserved=True,restricted_Beam_pool_used=False,NodeCount=oracle["NodeCount"],
            native_status=oracle["native_status"],same_S1_UB=oracle["ObjVal"],same_S1_ObjBound=oracle["same_S1_full_domain_ObjBound"],
            MIPGap=oracle["MIPGap"],integer_optimum=None,integer_optimum_certified=False),
        unmodified_original_application_raw_replay=file_record(detail/"S1_INTEGER_ORACLE_ORIGINAL_APPLICATION_RAW_REPLAY.json"),
        new_method="ORIGINAL_ROUTE_MODE_SOC_DISJUNCTIVE_INTEGER_HULL",
        actual_root_candidate_rows=diag["candidate_count"],actual_robust_root_violations=diag["robustly_violated_count"],
        maximum_raw_root_violation=diag["maximum_raw_root_violation"],integer_domain_preserved_theorem=diag["integer_validity_theorem"],
        new_method_root_separation=file_record(detail/"S1_SOC_ROUTE_HULL_ACTUAL_ROOT_SEPARATION.json"),
        new_cut_Native_experiment="NOT_RUN_NONVIOLATED_ACTUAL_ROOT",previous_384_aggregate_mode_hull_repeated=False,
        numerical_S1_LB_improvement_over_base_root=oracle["same_S1_full_domain_ObjBound"]-0.6090630116056528,
        meaningful_S1_LB_improvement=False,new_DW_or_column_global_certificate="NOT_CERTIFIED",
        Original_4x24_Global_LB=None,new_Current_C1_Global_LB=None,new_Global_LB_improvement=None,
        historical_original4x24_reference_only=dict(UB=0.5398310226338695,Global_LB=0.46498486997548166,
            gap_percent=13.864737209,scope="ORIGINAL_EXACT_HISTORICAL_CASE_ONLY"),
        original4x24_bound_transfer=False,original_operational_algorithm_replaced=False,
        next_selected_method="FULL_VEHICLE_SCHEDULE_DANTZIG_WOLFE",next_selected_method_status="NOT_RUN",
        next_selected_method_reason="Actual4307fractionalArcs/187multipleLocations and5.0218percentS1integergap remain after zero SOC hull violations; joint full-vehicle schedule disjunction targets route/SOC/Mode/PQ coupling.",
        next_research_gate="Complete original-domain full-vehicle route/SOC/binaryMode/PQ pricing and independently verified outward dual certificate; finite Beam or route-only columns cannot certify the global LB.")
    write_new(OUT/"MESS_BEAM_COMPRESSION_FOLLOWUP.json",compression)
    write_new(OUT/"MESS_BEAM_DIVERSITY_STATUS.json",diversity)
    write_new(OUT/"MESS_GLOBAL_LB_RESEARCH_STATUS.json",lb)
    print(json.dumps(dict(status="PASS",Native_optimize_calls=0,cache_reuse_seconds=reuse["cache_reuse_wall_seconds"],
        seal_creation_seconds=seal["first_seal_IO_and_hash_wall_seconds"],first_independent_proof_seconds=proof_wrapper_wall,
        source_restore_seconds=source_restore_wall,S1_actual_SOC_hull_violations=diag["robustly_violated_count"],
        S1_original_application_RAW_replay=replay["PASS"],reports=str(detail)),indent=2))


if __name__=="__main__":main()

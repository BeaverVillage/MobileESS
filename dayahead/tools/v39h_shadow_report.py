"""Assembly-only V39H recovery and review. NEVER calls a solver."""
import argparse
from datetime import datetime
import inspect
import math
from pathlib import Path
import sys
import numpy as np
import pandas as pd
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39h_shadow as h

def stats(values):
    x=np.array(values,dtype=float)
    return {"n":len(x),"total":float(x.sum()),**{k:float(np.quantile(x,q)) if len(x) else None for k,q in [("median",.5),("P75",.75),("P90",.9),("P95",.95),("P99",.99),("max",1)]}}

def equivalent_formulation():
    before=h.read(h.ROOT/"V39H_PRE_ASSEMBLY_FORMULATION_SHA.json")
    for name,value in before["unchanged_formulation_function_SHA"].items():assert h.digest(inspect.getsource(getattr(h,name)))==value,name
    assert h.grid.sha(Path(h.grid.__file__))==before["grid_helper_SHA"]
    assert h.grid.sha(Path(h.v39g.__file__))==before["V39G_helper_SHA"]
    return before

def migration_authority_equivalence(day):
    """Bind saved minimum-migration proof to the unchanged production model."""
    from dayahead.v38.authority import canonical_sha256
    from dayahead.v39e.contracts import RACK_AUTHORITY_PATH, RACK_AUTHORITY_SHA256, CAPACITY_FILE_SHA256
    preflight_path=h.BASE/"V39E_FULL_PREFLIGHT.json"
    old=h.read(preflight_path);fp=old["implementation_fingerprint_inputs"]
    assert canonical_sha256(fp)==old["final_implementation_fingerprint_sha256"]
    source={name:h.grid.sha(h.REPO/"dayahead/v39e"/name) for name in fp["source_SHA256"]}
    assert source==fp["source_SHA256"]
    initial_path=h.REPO/"dayahead/artifacts/v39e_rw_anchored_initial_state_fast_validation/V39E_COMMON_INITIAL_STATE_AUDIT.json"
    assert h.grid.sha(initial_path)==fp["initial_authority_SHA256"]
    assert h.grid.sha(h.REPO/RACK_AUTHORITY_PATH)==fp["Rack_authority_SHA256"]==RACK_AUTHORITY_SHA256
    assert fp["site_capacity_SHA256"]==CAPACITY_FILE_SHA256
    cap,_=h._load_capacity(h.REPO)  # frozen file/canonical SHA and capacity/rack checks only
    original=next(r for r in h.read(initial_path)["days"] if r["operating_day"]==day)
    hashes={};decisions={}
    for case in ("B0","B1","B2","B3"):
        path=h.BASE/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_{case}.json"
        f=h.read(path);d=f["decision"];decisions[case]=d
        assert canonical_sha256(d)==f["DA_decision_SHA256"]
        assert f["SHA_created_before_Actual_namespace"] and d["status"]=="PASS"
        assert d["common_initial_RUNNING_AIDC_state"]==original["initial_rows"]
        assert canonical_sha256(d["common_initial_RUNNING_AIDC_state"])==d["common_initial_state_SHA256"]==original["initial_state_SHA256"]
        schedule_path=h.REPO/f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}/V37_R4A_{d['temporal_mode']}_SCHEDULE.parquet"
        assert h.grid.sha(schedule_path)==d["temporal_schedule_SHA256"]
        hashes[case]={"file_SHA256":h.grid.sha(path),"DA_decision_SHA256":f["DA_decision_SHA256"],"temporal_file_SHA256":d["temporal_schedule_SHA256"]}
    for key in ("temporal_schedule","AIDC_assignments","site_GPU_trajectory","site_IT_power_trajectory","site_PCC_power_trajectory","migration_state"):
        assert decisions["B1"][key]==decisions["B3"][key],key
    result={"status":"PASS","day":day,"canonical_DA_hashes_verified":hashes,
        "production_model_file_SHAs_identical_to_saved_preflight":source,
        "saved_preflight_fingerprint":old["final_implementation_fingerprint_sha256"],
        "saved_preflight_file_SHA256":h.grid.sha(preflight_path),
        "original_initial_authority_SHA256":fp["initial_authority_SHA256"],
        "rack_authority_SHA256":RACK_AUTHORITY_SHA256,"site_capacity_SHA256":CAPACITY_FILE_SHA256,
        "site_capacity_vector":dict(cap.site_capacity),"B1_B3_DA_and_migration_identity":True,
        "original_base_RSP_file_SHA_verified":True,"new_optimization_calls":0,
        "scope":"Existing V39E migration certificate reuse only; no production refreeze or new 31-day readiness assertion."}
    h.atomic(h.ROOT/"days"/day/"V39H_MIGRATION_SHA_MODEL_AUTHORITY_EQUIVALENCE.json",result)
    return result

def assemble_day(day):
    """Recover completed proofs after reporting-only errors, no optimization."""
    out=h.ROOT/"days"/day;equivalence=equivalent_formulation();a,_,hashes=h.inputs(day)
    inp=h.read(out/"V39H_INPUT_AUTHORITY.json")
    for p,value in inp["input_SHA"].items():assert h.grid.sha(Path(p))==value,p
    fingerprint=h.digest({"model_SHA":h.model_hash(),"day":day,"input_SHA":hashes})
    decision=h.read(h.BASE/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json")["decision"]
    common={"day":day,"input_model_SHA":fingerprint,"existing_migration_count":h.BASE_COUNTS[day],"RUNNING_migration_calls_in_temporal_shadow":0,"Threads":4,"Seed":h.SEED,"MIPGap":0,"sidecar":False,"reporting_reassembled_without_solver_calls":True}
    previous={}
    if (out/"V39H_SHADOW_A_RESULT.json").exists():
        previous=h.read(out/"V39H_SHADOW_A_RESULT.json")
        common={**previous,**common}
    iis=out/"V39H_SHADOW_A_IIS_SUMMARY.json"
    lex=out/"V39H_EXACT_LEX_CERTIFICATES.json"
    if iis.exists() and not lex.exists():
        assert (out/"V39H_SHADOW_A_IIS.ilp").exists()
        assert h.read(iis)["full_shadow_infeasibility_proven"]
        migration_authority_equivalence(day)
        confirmation=h.migration_confirmation(day,a,out)
        result={**common,"base_RSP_status":"INFEASIBLE","shadow_status":"INFEASIBLE","classification":"TEMPORAL_REPAIR_INSUFFICIENT","temporal_repair_sufficient":False,"post_candidate_migration_count":confirmation["solver_proven_minimum_migrations"],"infeasibility_proof":"SAVED_SOLVER_IIS"}
        h.save_day(a,h.retained_schedule(a,decision),out,result,decision)
    elif lex.exists():
        assert h.read(lex)["all_stages_optimal"]
        b=pd.read_parquet(out/"V39H_SHADOW_SCHEDULE.parquet")
        for col in a.columns:assert np.array_equal(a[col].fillna("<NA>"),b[col].fillna("<NA>")),col
        cap,_=h._load_capacity(h.REPO)
        with np.load(out/"V39G_C1_INTEGER_TABLES.npz") as z:tables={s:z[s].copy() for s in cap.aidc_ids}
        bundle={"capacity":cap,"sites":tuple(cap.aidc_ids),"tables":tables}
        if previous.get("audit",{}).get("all_hard_constraints_pass") and (out/"V39H_WITNESS.npz").exists():
            # The completed worker's independent audit already covers this
            # witness. Bind it to the current schedule without re-evaluating
            # thousands of unchanged grid inequalities.
            occ=np.zeros((int((b.latest_start+b.duration_slots).max()),12),dtype=int)
            for row in b.itertuples(index=False):
                occ[row.scheduled_start_slot:row.scheduled_end_slot,bundle["sites"].index(row.AIDC)]+=int(row.requested_gpus)
            pcc=np.asarray([[tables[s][t,occ[t+24,i]] for i,s in enumerate(bundle["sites"])] for t in range(96)])
            with np.load(out/"V39H_WITNESS.npz") as witness:
                assert np.array_equal(occ,witness["GPU_complete"])
                assert np.array_equal(pcc,witness["PCC_target"])
            audit=previous["audit"]
            common["completed_independent_grid_audit_reused_same_witness"]=True
        else:
            cs,nodes=h.grid.load_coefficients(out);bundle.update(coefficients=cs,nodes=nodes)
            audit,occ,pcc=h.cloned_v39g(out).audit_schedule(b,bundle)
        assert audit["all_hard_constraints_pass"]
        cert=h.read(out/"V39H_OBJECTIVE_CERTIFICATES.json")["stages"]
        assert all(r["optimal"] for r in cert)
        assert [r["objective"] for r in cert]==[0,float(b.occupancy_deviation_GPU_slots.sum()),float(b.start_delay_slots.ne(0).sum()),float((b.requested_gpus*b.start_delay_slots).sum())]
        if not decision.get("AIDC_assignments"):
            # Reference only, never an input to the temporal model. May17 has
            # no production migration solution but V39F has a base placement.
            ref=h.REPO/"dayahead/artifacts/v39f_day17_rsp_temporal_grid_diagnostic/V39F_DAY17_FROZEN_RSP_SITE_ONLY_ASSIGNMENTS.parquet"
            if day=="2025-05-17":decision={**decision,"AIDC_assignments":pd.read_parquet(ref).to_dict("records")}
        result={**common,"base_RSP_status":"INFEASIBLE","shadow_status":"OPTIMAL","classification":"TEMPORAL_REPAIR_SUFFICIENT","temporal_repair_sufficient":True,"post_candidate_migration_count":0,"stages":cert,"audit":audit}
        h.save_day(a,b,out,result,decision,bundle)
    else:raise RuntimeError(f"NO_COMPLETED_PROOF:{day}")
    h.atomic(out/"V39H_ASSEMBLY_EQUIVALENCE.json",{"status":"PASS","input_files_unchanged":True,"all_decision_relevant_function_SHA_unchanged":True,"formulation_SHA_evidence":equivalence,
        "reporting_change":"RW bound is checked on every MOVED/eligible job; pre-existing noneligible base lateness is separately exposed, never changed.","new_solver_calls":0,"current_input_model_SHA":fingerprint})
    p=h.read(out/"V39H_DAY_PROGRESS.json");p.pop("error",None);h.atomic(out/"V39H_DAY_PROGRESS.json",p)

def claim_status(r):
    """Annotate aggregate views without rewriting the 11 completed day files."""
    r=dict(r)
    if r["temporal_repair_sufficient"]:
        primary=r["stages"][1];integer_value=r["symmetric_occupancy_deviation_GPU_slots"]
        # Integer objective: a lower bound strictly above k-1 certifies k.
        # Preserve the saved May24 floating bound 107.9999999999996 unchanged.
        assert primary["optimal"] and primary["gap"]==0 and primary["objective"]==integer_value and math.ceil(primary["bound"])==integer_value
        r.setdefault("PRIMARY_TEMPORAL_INTERVENTION_OPTIMUM",r["stages"][1]["objective"])
        r.setdefault("PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL","YES")
        r.setdefault("SECONDARY_CHANGED_JOB_OPTIMALITY","YES")
        r.setdefault("TERTIARY_DELAY_OPTIMALITY","YES")
        r.setdefault("exact_full_lex",True)
    else:
        r.update(PRIMARY_TEMPORAL_INTERVENTION_OPTIMUM=None,PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL="INFEASIBLE_PROVEN",SECONDARY_CHANGED_JOB_OPTIMALITY="NOT_APPLICABLE",TERTIARY_DELAY_OPTIMALITY="NOT_APPLICABLE",exact_full_lex=False)
    return r

def aggregate():
    results=[claim_status(h.read(h.ROOT/"days"/d/"V39H_SHADOW_A_RESULT.json")) for d in h.DAYS]
    assert all(r["shadow_status"] in ("OPTIMAL","INFEASIBLE","PRIMARY_OPTIMAL_FEASIBLE") for r in results)
    success=[r for r in results if r["temporal_repair_sufficient"]];fail=[r for r in results if not r["temporal_repair_sufficient"]]
    remaining=sum(r["post_candidate_migration_count"] for r in results);freed=[r["day"] for r in success if r["existing_migration_count"]]
    remain=[r["day"] for r in fail if r["post_candidate_migration_count"]]
    pattern="MIGRATION_ELIMINATED_IN_AFFECTED_SET" if remaining==0 else "MIGRATION_REMAINS_SUBSTANTIAL" if len(remain)>2 else "MIGRATION_BECOMES_RARE"
    migration={"baseline_migration_days":12,"baseline_min_migrations":105,"affected_days":13,"temporal_repair_only_days":len(success),"previous_migration_days_eliminated":len(freed),"remaining_migration_days":len(remain),"remaining_min_migrations":remaining,"migration_reduction":105-remaining,"percentage_reduction":(105-remaining)/105*100,"migration_free_previous_dates":freed,"still_requires_migration_dates":remain,"classification":pattern,
        "classification_is_descriptive_not_scientific_threshold":True,"pattern_rationale":f"{len(remain)} dates and {remaining} solver-proven migrations remain.","new_migration_MILP_calls":0,
        "successful_temporal_days_migration_calls":0,"partially_repaired_input_to_migration":False,
        "per_day":[{k:r[k] for k in ("day","existing_migration_count","post_candidate_migration_count","classification")} for r in results]}
    h.atomic(h.ROOT/"V39H_MIGRATION_105_TO_POSTREPAIR_AUDIT.json",migration)
    delays=[x for r in results for x in r["delay_minutes"]];slacks=[x for r in results for x in r["slack_consumed_ratios"]]
    eligible=sum(r["eligible_standby_jobs"] for r in results);changed=sum(r["changed_jobs"] for r in results)
    thresholds=(30,60,120,240,480,720,1440)
    def bins(values):return {str(t):{"count":sum(v>t for v in values),"fraction_of_changed_jobs":sum(v>t for v in values)/len(values) if values else 0} for t in thresholds}
    delay={"eligible_standby_jobs":eligible,"changed_jobs":changed,"changed_fraction_all_eligible":changed/eligible,"delay_minutes_changed_jobs":stats(delays),"delay_threshold_minutes":bins(delays),"slack_consumed_ratio_changed_jobs":stats(slacks),
        "RW_completion_noninferiority_violations_moved_jobs":sum(r["RW_completion_noninferiority_violations"] for r in results),
        "base_existing_noneligible_completion_lateness_caveat":"Frozen RSP can already finish some noneligible jobs later than RW. They are NOT changed by this policy and NOT invented as new violations.",
        "base_existing_completion_later_than_RW_jobs":sum(r["base_RSP_existing_completion_later_than_RW_jobs"] for r in results),
        "per_day":{r["day"]:{"eligible":r["eligible_standby_jobs"],"changed":r["changed_jobs"],"delay":stats(r["delay_minutes"]),"thresholds":bins(r["delay_minutes"]),"slack_consumed_ratio":stats(r["slack_consumed_ratios"])} for r in results}}
    assert delay["RW_completion_noninferiority_violations_moved_jobs"]==0
    h.atomic(h.ROOT/"V39H_DELAY_REALISM_AUDIT.json",delay)
    margins=[h.read(h.ROOT/"days"/r["day"]/"V39H_GRID_MARGIN_AUDIT.json") for r in success]
    grid_audit={"successful_days":len(success),"minimum_upper_voltage_headroom_pu":min(r["upper_voltage_headroom_pu"] for r in margins),
        "upper_headroom_bins":{str(t):{"days":sum(r["upper_voltage_headroom_pu"]<t for r in margins),"dates":[r["day"] for r in margins if r["upper_voltage_headroom_pu"]<t]} for t in (1e-6,1e-5,1e-4,1e-3)},
        "all_voltage_line_transformer_constraints_pass":all(r["pass"] for r in margins),"bins_are_diagnostic_not_safety_thresholds":True,"per_day":margins}
    h.atomic(h.ROOT/"V39H_GRID_MARGIN_AUDIT.json",grid_audit)
    works={d:h.read(h.ROOT/"days"/d/"V39H_WORK_PRESERVATION_AUDIT.json") for d in h.DAYS}
    work={"status":"PASS","safe_GPU_h_before":sum(x["safe_GPU_h_before"] for x in works.values()),"safe_GPU_h_after":sum(x["safe_GPU_h_after"] for x in works.values()),
        "all_exact_per_job_preserved":all(x["safe_duration_slots_equal"] and x["safe_seconds_equal"] and x["GPU_requests_equal"] and x["job_set_equal"] for x in works.values()),"modeled_reservation_not_measured_computation":True,"per_day":works}
    assert work["all_exact_per_job_preserved"] and work["safe_GPU_h_before"]==work["safe_GPU_h_after"]
    h.atomic(h.ROOT/"V39H_WORK_CONSERVATION_AUDIT.json",work)
    summary=[]
    keys=["day","shadow_status","classification","eligible_standby_jobs","changed_jobs","changed_fraction","existing_migration_count","post_candidate_migration_count","symmetric_occupancy_deviation_GPU_slots","symmetric_occupancy_deviation_GPU_h","one_way_relocated_occupancy_GPU_h","sum_start_delay_minutes","GPU_weighted_start_delay_slots","max_added_delay_min","maximum_simultaneous_load_restored_GPU","maximum_simultaneous_load_removed_GPU","PENDING_initial_placement_changes","PENDING_initial_placement_comparable_jobs","Vmax","Vmin","upper_voltage_headroom_pu","safe_GPU_h_before","safe_GPU_h_after","outside_site_grid_domain_GPU_h_before","outside_site_grid_domain_GPU_h_after","scope_warning","RW_completion_noninferiority_violations","base_RSP_existing_completion_later_than_RW_jobs"]
    keys += ["base_RSP_status","PRIMARY_TEMPORAL_INTERVENTION_OPTIMUM","PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL","SECONDARY_CHANGED_JOB_OPTIMALITY","TERTIARY_DELAY_OPTIMALITY","exact_full_lex","selected_witness","selection_caveat"]
    for r in results:
        row={k:r.get(k) for k in keys};row.update({f"delay_{k}":v for k,v in stats(r["delay_minutes"]).items() if k!="n"});summary.append(row)
    pd.DataFrame(summary).to_csv(h.ROOT/"V39H_13DAY_SUMMARY.csv",index=False,encoding="utf-8-sig")
    general={"status":"COMPLETE","dates_evaluated":h.DAYS,"successful_dates":[r["day"] for r in success],"insufficient_dates":[r["day"] for r in fail],"exact_universal_rule_same_all_dates":True,
        "prescreen_voltage_used":False,"PENDING_site_freedom_preserved":True,"new_migration_solves":0,"sidecar_solves":0,
        "total_symmetric_GPU_slots":sum(r["symmetric_occupancy_deviation_GPU_slots"] for r in results),"total_symmetric_GPU_h":sum(r["symmetric_occupancy_deviation_GPU_h"] for r in results),
        "total_one_way_GPU_h":sum(r["one_way_relocated_occupancy_GPU_h"] for r in results),"GPU_weighted_start_delay_slots":sum(r["GPU_weighted_start_delay_slots"] for r in results),
        "scope_warning_dates":[r["day"] for r in results if r["scope_warning"]],"PENDING_spatial_changes":sum(r["PENDING_initial_placement_changes"] for r in results)}
    general.update(primary_optimal_feasible_days=len(success),rigorously_infeasible_days=len(fail),primary_outcome_certified_days=len(results),
        secondary_exact_proof_required=False,tertiary_exact_proof_required=False,
        claim_boundary="Only the primary intervention minimum is globally optimal on every feasible date. May25/26 tie-breaks are not claimed globally optimal unless separately certified.",
        per_day_optimality=[{k:r[k] for k in ("day","PRIMARY_TEMPORAL_INTERVENTION_OPTIMUM","PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL","SECONDARY_CHANGED_JOB_OPTIMALITY","TERTIARY_DELAY_OPTIMALITY","exact_full_lex")} for r in results])
    h.atomic(h.ROOT/"V39H_TEMPORAL_REPAIR_GENERALIZATION_AUDIT.json",general)
    preview={"production_authorization":"NOT_GRANTED_BY_V39H","production_science_changed":False,"May01_05_invalidated":False,
        "after_future_approved_refreeze_expensive_recompute_candidates":[r["day"] for r in success if r["changed_jobs"]],
        "unchanged_base_RSP_plus_migration_reuse_candidates":remain,"other_18_dates_not_solved":True,
        "minimum_safe_recomputation_policy":["Recompute expensive DA/downstream only for dates whose approved temporal layer actually changes DA.","Reuse unchanged base-RSP and solver-proven migration dates after input/model/authority/SHA equivalence.","May01-05 Actual/Fresh may be reused only after temporal-repair call=0 and DA/downstream equivalence are proven in a separate authorized audit.","31-day readiness is SHA/authority/loader/certificate/provenance assembly, not optimization rerun."],
        "current_31day_production_readiness_claim":"NOT_EVALUATED_NOT_REFROZEN","full_preflight_calls":0,"campaign_calls":0,"Actual_Fresh_result_reuse_authorized_now":False}
    h.atomic(h.ROOT/"V39H_CHANGE_IMPACT_PREVIEW.json",preview)
    return results,migration,delay,grid_audit,work,general

def finalize():
    results,mig,delay,grid,work,general=aggregate()
    start=h.read(h.ROOT/"V39H_START_STATE.json");assert start["production_source_SHA256"]==h.v39g.source_hashes()
    assert start["preserved_artifact_metadata"]==h.preserved_metadata()
    tests=h.read(h.ROOT/"V39H_TEST_REPORT.json");assert tests["status"]=="PASS"
    provenance={"starting_HEAD":start["starting_HEAD"],"final_HEAD":h.v39g.git("rev-parse","HEAD"),"starting_branch":start["starting_branch"],"branch":h.v39g.git("branch","--show-current"),"dirty_state":h.v39g.git("status","--porcelain"),
        "production_source_files_byte_verified":len(start["production_source_SHA256"]),"production_science_mutation_count":0,"V39E_F_G_artifact_metadata_entries_preserved":len(start["preserved_artifact_metadata"]),
        "May01_05_results_touched":False,"preservation_method":start["preservation_method"],"max_day_workers":4,"Gurobi_threads_per_model":4,"Seed":h.SEED,"MIPGap":0,
        "migration_MILP_re_solves":0,"full_preflight_calls":0,"May_campaign_calls":0,"Actual_Fresh_outcome_decision_inputs":0,"sidecar_solves":0,"push":False,"PR":False,"local_commit":False,
        "source_SHA":{str(p.relative_to(h.REPO)):h.grid.sha(p) for p in [Path(h.__file__),Path(h.grid.__file__),Path(__file__),h.REPO/"dayahead/tools/v39h_relaxed_iis.py",h.REPO/"tests/dayahead/test_v39h_shadow.py"]},"finished_at":h.now()}
    h.atomic(h.ROOT/"V39H_DIAGNOSTIC_PROVENANCE.json",provenance)
    maxdelay=int(delay["delay_minutes_changed_jobs"]["max"] or 0);minmargin=grid["minimum_upper_voltage_headroom_pu"]
    flags={"V39H_DIAGNOSTIC_COMPLETE":"YES","AFFECTED_DAYS_EVALUATED":"13/13","TEMPORAL_REPAIR_SUFFICIENT_DAYS":mig["temporal_repair_only_days"],"TEMPORAL_REPAIR_INSUFFICIENT_DAYS":len(mig["still_requires_migration_dates"]),"BASELINE_MIGRATION_DAYS":12,"BASELINE_MIN_MIGRATIONS":105,"POST_CANDIDATE_MIGRATION_DAYS":mig["remaining_migration_days"],"POST_CANDIDATE_MIN_MIGRATIONS":mig["remaining_min_migrations"],"MIGRATION_REDUCTION":mig["migration_reduction"],"MIGRATION_PATTERN_CLASSIFICATION":mig["classification"],"RW_COMPLETION_NONINFERIORITY_PASS":"YES","FROZEN_SAFE_RUNTIME_PRESERVED":"YES","MAX_ADDED_DELAY_MIN":maxdelay,"MIN_UPPER_VOLTAGE_HEADROOM_PU":minmargin,"PRODUCTION_SCIENCE_CHANGED":"NO","FULL_PREFLIGHT_RERUN":"NO","MAY_RESTARTED":"NO","MAY01_05_RESULTS_TOUCHED":"NO"}
    flags.update(PRIMARY_OPTIMALITY_CERTIFIED_DAYS=f"{mig['temporal_repair_only_days']}/13",PRIMARY_OUTCOME_CERTIFIED_DAYS="13/13",
        SECONDARY_EXACT_PROOF_REQUIRED="NO",TERTIARY_EXACT_PROOF_REQUIRED="NO",NEWLY_INTRODUCED_RW_COMPLETION_VIOLATIONS=delay["RW_completion_noninferiority_violations_moved_jobs"],
        MIGRATION_REDUCTION_PERCENT=mig["percentage_reduction"])
    h.atomic(h.ROOT/"V39H_FINAL_STATUS.json",flags)
    qs=[f"Q1. Beyond May17, the exact standby rule succeeds on {mig['previous_migration_days_eliminated']} previous migration dates. No per-day retuning or eligibility expansion.",
        f"Q2. {mig['previous_migration_days_eliminated']}/12 previous migration days become temporal-repair-only: {', '.join(mig['migration_free_previous_dates'])}.",
        f"Q3. {mig['remaining_migration_days']} migration days remain.",
        f"Q4. 105 → {mig['remaining_min_migrations']}; reduction {mig['migration_reduction']} ({mig['percentage_reduction']:.4f}%). May17 was previously unresolved and is not subtracted from the original 105.",
        f"Q5. Still requiring migration: {', '.join(mig['still_requires_migration_dates'])}.",
        f"Q6. {mig['classification']}. This is descriptive: {mig['pattern_rationale']} No minimum migration count or scientific threshold was imposed.",
        "Q7. Changed standby jobs per day: "+", ".join(f"{r['day']}: {r['changed_jobs']}" for r in results)+". Infeasible days retain the original RSP with zero temporal changes.",
        f"Q8. Total delay {delay['delay_minutes_changed_jobs']['total']} min; median {delay['delay_minutes_changed_jobs']['median']}, P95 {delay['delay_minutes_changed_jobs']['P95']}, max {maxdelay} min among changed jobs.",
        f"Q9. Delays >8h / >12h / >24h: {delay['delay_threshold_minutes']['480']['count']} / {delay['delay_threshold_minutes']['720']['count']} / {delay['delay_threshold_minutes']['1440']['count']}. Full bins and fractions are in the delay audit.",
        "Q10. Every moved job finishes no later than its own RW modeled completion; zero violations. Existing noneligible baseline RSP lateness is separately reported, not mislabeled as a new shadow violation.",
        f"Q11. Smallest upper-voltage headroom is {minmargin:.12g} pu. Per-day critical bus/phase/slot and all voltage/line/transformer margins are in the margin audit.",
        "Q12. Upper-headroom bins: "+", ".join(f"<{k} pu: {v['days']} days" for k,v in grid['upper_headroom_bins'].items())+". These are numerical descriptions, not a claim of danger or new limit.",
        "Q13. Every successful temporal shadow passes all frozen voltage, line, transformer phase-current and apparent-power/inner-polygon constraints. Infeasible dates retain their existing passing migration witness.",
        f"Q14. Exact frozen safe-runtime preservation per job, GPU request and job set; total {work['safe_GPU_h_before']} modeled reservation GPU-h before and after. Not measured or realized computation.",
        "Q15. No successful temporal-repair day uses RUNNING migration; no migration solver is called. PENDING initial-placement changes are counted separately.",
        "Q16. All standby-insufficient dates reuse the original solver-proven minimum migration count after exact frozen-RSP, authority and saved-witness verification. No migration MILP was re-solved and no partially repaired schedule was used.",
        "Q17. The evidence supports further review of the conservative Base RSP → minimum standby repair → original minimum migration hierarchy. It does not approve production. Review delay outliers, slack consumed, operating-day-only spatial scope and voltage headroom; later approved changes should use selective recomputation and certificate assembly."]
    text="# V39H final review — 13-day shadow only\n\n"+"\n\n".join(qs)+"\n\n## Scope and runtime\n\nPrescreens use only irrecoverable resource contradictions, never fixed-only voltage. Every PENDING initial site remains free. Four isolated workers × four solver threads; no migration re-solves. Completed exact witnesses were reused after equivalence checks. The other 18 dates and May01–05 results were not rerun. No production refreeze or readiness claim. Optional sidecars were not run.\n\n## Final status\n\n```text\n"+"\n".join(f"{k} = {v}" for k,v in flags.items())+"\n```\n"
    text+="\n## FAST-CLOSE scientific claim boundary\n\nThe user explicitly waived unfinished secondary/tertiary global optimality proofs. All feasible days retain their globally certified primary intervention optimum; infeasible dates have rigorous infeasibility proofs and no finite primary optimum. PRIMARY_OPTIMALITY_CERTIFIED_DAYS counts feasible primary optima only, while PRIMARY_OUTCOME_CERTIFIED_DAYS includes infeasibility certificates. No interrupted tie-break is labeled OPTIMAL.\n\n"
    text+="| Day | Base RSP | Primary optimum GPU-slots | Primary status | Changed jobs | Secondary status | Tertiary status |\n|---|---|---:|---|---:|---|---|\n"
    for r in results:text+=f"| {r['day']} | {r['base_RSP_status']} | {r['PRIMARY_TEMPORAL_INTERVENTION_OPTIMUM']} | {r['PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL']} | {r['changed_jobs']} | {r['SECONDARY_CHANGED_JOB_OPTIMALITY']} | {r['TERTIARY_DELAY_OPTIMALITY']} |\n"
    text+="\nMay25 uses the saved primary-optimal 15-job witness because the in-memory 14-job incumbent was not serialized by the original strict worker. This is the explicitly authorized fallback, not the best known changed-job count. Its secondary minimum is not claimed. May26 preserves the certified 8-job minimum; its chosen GPU-weighted delay is feasible but not globally certified. No unique or full global lexical optimum is claimed for either date.\n"
    (h.ROOT/"V39H_FINAL_REVIEW.md").write_text(text,encoding="utf-8")
    elapsed=(datetime.fromisoformat(h.now())-datetime.fromisoformat(start["start_time"])).total_seconds()
    h.atomic(h.ROOT/"progress/V39H_PROGRESS.json",{"phase":"COMPLETE","start_time":start["start_time"],"last_update":h.now(),"elapsed":elapsed,"elapsed_seconds":elapsed,"completed_days":h.DAYS,"running_days":[],"pending_days":[],"failed_days":{},"worker_PIDs":{},"per_day":{r["day"]:{k:r.get(k) for k in ("base_RSP_status","shadow_status","changed_jobs","Vmax","temporal_repair_sufficient","existing_migration_count","post_candidate_migration_count")} for r in results},"baseline_migrations":105,"current_postrepair_migrations":mig["remaining_min_migrations"],"temporal_repair_only_days":mig["temporal_repair_only_days"],"remaining_migration_days":mig["remaining_migration_days"],"resumable":True})
    # Certificate assembly only: digest required outputs without re-solving.
    required=["V39H_MODEL_CONTRACT.md","V39H_AFFECTED_DATE_SET.json","V39H_13DAY_SUMMARY.csv","V39H_TEMPORAL_REPAIR_GENERALIZATION_AUDIT.json","V39H_MIGRATION_105_TO_POSTREPAIR_AUDIT.json","V39H_DELAY_REALISM_AUDIT.json","V39H_GRID_MARGIN_AUDIT.json","V39H_WORK_CONSERVATION_AUDIT.json","V39H_CHANGE_IMPACT_PREVIEW.json","V39H_TEST_REPORT.json","V39H_DIAGNOSTIC_PROVENANCE.json","V39H_FINAL_REVIEW.md","V39H_FINAL_STATUS.json"]
    for r in results:
        names=["V39H_SHADOW_A_RESULT.json","V39H_CHANGED_JOBS.csv","V39H_SHADOW_SCHEDULE.parquet","V39H_GRID_MARGIN_AUDIT.json","V39H_WORK_PRESERVATION_AUDIT.json","V39H_ASSEMBLY_EQUIVALENCE.json"]
        if r["temporal_repair_sufficient"]:
            names += ["V39H_OBJECTIVE_CERTIFICATES.json", "V39H_EXACT_LEX_CERTIFICATES.json" if r["exact_full_lex"] else "V39H_FAST_CLOSE_WITNESS_CERTIFICATE.json"]
        else:names += ["V39H_SHADOW_A_IIS.ilp","V39H_SHADOW_A_IIS_SUMMARY.json","V39H_EXISTING_MIGRATION_CONFIRMATION.json","V39H_MIGRATION_SHA_MODEL_AUTHORITY_EQUIVALENCE.json"]
        required.extend(f"days/{r['day']}/{n}" for n in names)
    h.atomic(h.ROOT/"V39H_REQUIRED_ARTIFACT_SHA_MANIFEST.json",{"status":"PASS","required_file_count":len(required),"SHA256":{n:h.grid.sha(h.ROOT/n) for n in required},"optimization_calls":0,"scope":"13-day diagnostic assembly, not 31-day production readiness"})
    print("\n".join(f"{k} = {v}" for k,v in flags.items()))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--assemble-day",choices=h.DAYS);p.add_argument("--aggregate",action="store_true");args=p.parse_args()
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=4):
        assemble_day(args.assemble_day) if args.assemble_day else aggregate() if args.aggregate else finalize()

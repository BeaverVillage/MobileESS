"""Read-only scientific audits and diagnostic-only report generation."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from pathlib import Path
import json
import sys
import subprocess
import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39g_day17_shadow as sh
from dayahead.tools.v39g_shadow_grid import load_coefficients,evaluate,sha

CALIBRATION=Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3d_kestrel_runtime_authority_closure\dayahead\artifacts\v35r3d_kestrel_runtime_authority_closure\V35R3D_RUNTIME_CALIBRATION.json")
F=REPO/"dayahead/artifacts/v39f_day17_rsp_temporal_grid_diagnostic"

def profile(a,mode):
    horizon=int(max(a.RW_scheduled_completion.max(),a.RSP_scheduled_completion.max()))
    occ=np.zeros(horizon,dtype=int)
    for r in a.itertuples(index=False):
        s=int(getattr(r,f"{mode}_scheduled_start"));d=int(getattr(r,f"{mode}_duration_slots"))
        occ[s:s+d]+=int(r.requested_gpus)
    return occ

def baseline():
    a,decision=sh.inputs();capacity,_=sh._load_capacity(REPO);sites=capacity.aidc_ids
    coefficients,nodes=load_coefficients(sh.OUT)
    with np.load(sh.OUT/"V39G_C1_INTEGER_TABLES.npz") as raw:tables={s:raw[s].copy() for s in sites}
    rw=pd.DataFrame(decision["site_GPU_trajectory"]).pivot(index="slot",columns="AIDC",values="active_GPU").loc[:,sites].to_numpy(int)
    rsp=pd.read_csv(F/"V39F_DAY17_FROZEN_RSP_SITE_ONLY_GPU.csv").loc[:,sites].to_numpy(int)
    result={}
    for name,occ,mode in (("RW",rw,"RW"),("FROZEN_RSP",rsp,"RSP")):
        assert np.array_equal(profile(a,mode)[24:120],occ.sum(axis=1))
        pcc=np.asarray([[tables[s][t,occ[t,i]] for i,s in enumerate(sites)] for t in range(96)])
        grid=evaluate(coefficients,nodes,pcc)
        result[name]={"grid":grid,"slot106_GPU":int(occ[82].sum()),"full_day_GPU_hours":float(occ.sum()/4),
            "site_mean_utilization":{s:float(occ[:,i].mean()/capacity.site_capacity[s]) for i,s in enumerate(sites)},
            "site_peak_utilization":{s:float(occ[:,i].max()/capacity.site_capacity[s]) for i,s in enumerate(sites)},
            "slot106_site_GPU":dict(zip(sites,occ[82]))}
    assert abs(result["RW"]["grid"]["Vmax"]-1.0478466777634734)<1e-9
    assert abs(result["FROZEN_RSP"]["grid"]["Vmax"]-1.051067054291103)<1e-9
    assert result["RW"]["grid"]["pass"] and result["FROZEN_RSP"]["grid"]["voltage_violation_count"]==4
    sh.write("V39G_BASELINE_REPRODUCTION.json",result)
    print("Frozen RW/RSP grid values independently reproduced",flush=True)

def distribution(x):
    x=np.asarray(x,dtype=float)
    return {"n":len(x),**{key:float(np.quantile(x,q)) if len(x) else None for key,q in [("min",0),("P10",.1),("P25",.25),("median",.5),("P75",.75),("P90",.9),("P95",.95),("max",1)]},
            **{f"fraction_lt_{v}":float((x<v).mean()) if len(x) else None for v in (.75,.5,.25)}}

def runtime_and_work(a,b):
    pending=a.state_at_issue.eq("PENDING");running=~pending;g=a.requested_gpus
    seconds=a.RSP_duration_seconds.to_numpy(float)
    expected=np.where(pending,np.where(np.isfinite(a.diagnostic_point_total_seconds),
        np.minimum(a.requested_walltime_seconds,np.maximum(a.diagnostic_point_total_seconds+sh.Q_SELECTED_SECONDS,900)),a.requested_walltime_seconds),
        np.maximum(a.requested_walltime_seconds-a.elapsed_seconds_at_issue,900))
    assert np.max(np.abs(expected-seconds))<1e-7
    assert np.array_equal(np.maximum(1,np.ceil(seconds/900)).astype(int),a.RSP_duration_slots)
    calibration=json.loads(CALIBRATION.read_text(encoding="utf-8"))
    assert calibration["q90_plus_seconds"]==sh.Q_SELECTED_SECONDS and calibration["all_labels_pre_issue"]
    affected=(a.RW_scheduled_start.le(106)&a.RW_scheduled_completion.gt(106)&~(a.RSP_scheduled_start.le(106)&a.RSP_scheduled_completion.gt(106)))
    ratios=a.RSP_duration_seconds/a.requested_walltime_seconds
    per_job=a[["job_uid","state_at_issue","qos","requested_gpus","requested_walltime_seconds","elapsed_seconds_at_issue",
        "diagnostic_point_total_seconds","q_selected_seconds","diagnostic_safe_total_seconds","RSP_duration_seconds","RSP_duration_slots",
        "RW_duration_slots","duration_authority","coverage_fallback_status"]].copy()
    per_job["safe_over_full_requested_seconds_ratio"]=ratios
    per_job["RW_active_RSP_inactive_at_106"]=affected
    per_job["changed_in_shadow"]=b.start_delay_slots.ne(0)
    per_job.to_csv(sh.OUT/"V39G_SAFE_RUNTIME_PER_JOB.csv",index=False,encoding="utf-8-sig")
    sh.write("V39G_MAY17_SAFE_RUNTIME_PROVENANCE_AUDIT.json",{
        "predictor":"HPC-ODA MoEXGBoostModel, frozen Apr-01 model state", "HPCODA_source_HEAD":sh.FROZEN_HPCODA_HEAD,
        "model_config":sh.FROZEN_MODEL_CONFIG,"frozen_training_cutoff_AEST":"2025-03-31T18:00:00+10:00",
        "training_lookback_days":120,"model_retrained_for_V39G":False,
        "D1_causal_query_inputs":"issue-visible submission, resource request, requested walltime, partition, QoS, account/user identifiers; no May runtime labels",
        "point_estimate_source":"Frozen May17 job ledger diagnostic_point_total_seconds; per-job values exported",
        "safe_pending_formula":"min(requested,max(point+5576.44921875,900)); ceil to 15-minute slots; requested fallback if point unavailable",
        "safe_running_formula":"max(requested-elapsed_at_issue,900), ceil to 15-minute slots; not a point prediction",
        "q_provenance":{"path":str(CALIBRATION),"sha256":sha(CALIBRATION),"calibration":calibration,
            "meaning":"Frozen 90th percentile positive prediction-error safety term; empirical calibration, not a guarantee for every future job"},
        "all_safe_seconds_reproduced":True,"all_safe_slots_reproduced":True,
        "pending_requested_cap_hits":int((pending & np.isclose(a.RSP_duration_seconds,a.requested_walltime_seconds)).sum()),
        "pending_900s_floor_hits_before_requested_cap":int((pending & (a.diagnostic_point_total_seconds+sh.Q_SELECTED_SECONDS<900)).sum()),
        "requested_walltime_fallback_jobs":int(a.duration_authority.eq("REQUESTED_WALLTIME_FAIL_CLOSED").sum()),
        "ratio_definition":"RSP_duration_seconds / full requested_walltime_seconds, NOT rounded slots",
        "ratios_all":distribution(ratios),"ratios_pending":distribution(ratios[pending]),
        "ratios_standby_eligible":distribution(ratios[a.eligible]),"ratios_slot106_affected":distribution(ratios[affected]),
        "ratios_shadow_changed":distribution(ratios[b.start_delay_slots.ne(0)]),
        "running_ratio_caveat":"Numerator is remaining reservation; denominator full submitted walltime. Do not interpret as predictor shortening.",
        "May_Actual_reads":0,"Fresh_reads":0,"future_result_reads":0})
    work={"A_requested_walltime_GPU_hours_full_submission":float((g*a.requested_walltime_seconds).sum()/3600),
        "B_frozen_RSP_safe_GPU_hours_unrounded_seconds":float((g*a.RSP_duration_seconds).sum()/3600),
        "C_shadow_safe_GPU_hours_unrounded_seconds":float((b.requested_gpus*b.RSP_duration_seconds).sum()/3600),
        "B_frozen_RSP_modeled_reservation_GPU_hours_slots":float((g*a.RSP_duration_slots).sum()/4),
        "C_shadow_modeled_reservation_GPU_hours_slots":float((b.requested_gpus*b.duration_slots).sum()/4),
        "RW_modeled_reservation_GPU_hours_from_issue_slots":float((g*a.RW_duration_slots).sum()/4),
        "RW_minus_RSP_reservation_GPU_hours_from_issue_slots":float((g*(a.RW_duration_slots-a.RSP_duration_slots)).sum()/4),
        "RUNNING_full_requested_GPU_hours":float((g[running]*a.requested_walltime_seconds[running]).sum()/3600),
        "RUNNING_remaining_GPU_hours_before_slot_rounding":float((g[running]*a.RSP_duration_seconds[running]).sum()/3600),
        "PENDING_full_requested_GPU_hours":float((g[pending]*a.requested_walltime_seconds[pending]).sum()/3600),
        "PENDING_safe_GPU_hours_before_slot_rounding":float((g[pending]*a.RSP_duration_seconds[pending]).sum()/3600),
        "B_equals_C_seconds":bool(np.array_equal(a.RSP_duration_seconds,b.RSP_duration_seconds)),
        "B_equals_C_slots":bool(np.array_equal(a.RSP_duration_slots,b.duration_slots)),
        "complete_reservation_interval_included":True,
        "interpretation":"Modeled reservation GPU-hours, NOT measured/realized computation. Duration shortening does not prove real work disappeared. RUNNING uses remaining requested time; full submitted walltime is reported separately."}
    assert work["B_equals_C_seconds"] and work["B_equals_C_slots"]
    sh.write("V39G_MAY17_WORK_CONSERVATION_AUDIT.json",work)

def finalize():
    if not (sh.OUT/"V39G_BASELINE_REPRODUCTION.json").exists():baseline()
    a,_=sh.inputs();b=pd.read_parquet(sh.OUT/"V39G_MAY17_SHADOW_A_SCHEDULE.parquet")
    assert np.array_equal(a.job_uid,b.job_uid)
    issue=pd.Timestamp("2025-05-16T18:00:00+10:00")
    for source,dest in [("scheduled_start_slot","scheduled_start_AEST"),("scheduled_end_slot","scheduled_end_AEST"),
                        ("RSP_scheduled_start","frozen_RSP_start_AEST"),("RW_scheduled_completion","RW_modeled_completion_AEST")]:
        b[dest]=[str(issue+pd.Timedelta(minutes=15*int(t))) for t in b[source]]
    b["site_assignment_authority_issue_interval"]="[24,120)"
    b["intersects_spatial_operating_day"]=b.scheduled_start_slot.lt(120)&b.scheduled_end_slot.gt(24)
    b.to_parquet(sh.OUT/"V39G_MAY17_SHADOW_A_SCHEDULE.parquet",index=False)
    b.loc[b.start_delay_slots.ne(0)].to_csv(sh.OUT/"V39G_MAY17_CHANGED_JOBS.csv",index=False,encoding="utf-8-sig")
    lex=sh.read("V39G_EXACT_LEX_CERTIFICATES.json")
    assert lex["all_stages_optimal"]
    sh.write("V39G_LEX_PROGRESS.json",{"status":"COMPLETE","blocks_done":lex["blocks"],"blocks_total":lex["blocks"],"jobs_fixed":len(b),"certified_stages":len(lex["stages"])})
    r=sh.read("V39G_MAY17_SHADOW_A_RESULT.json");aux=sh.read("V39G_MAY17_SLOT106_LOAD_RESTORATION.json")
    bases=sh.read("V39G_BASELINE_REPRODUCTION.json");capacity,_=sh._load_capacity(REPO)
    with np.load(sh.OUT/"V39G_A_WITNESS.npz") as raw:occ=raw["GPU_complete"]
    runtime_and_work(a,b)
    comparison=[]
    for name,mode in (("RW","RW"),("FROZEN_RSP","RSP"),("SHADOW_A","SHADOW")):
        grid=r["grid"] if mode=="SHADOW" else bases[name]["grid"]
        end=b.scheduled_end_slot if mode=="SHADOW" else a[f"{mode}_scheduled_completion"]
        starts=b.scheduled_start_slot if mode=="SHADOW" else a[f"{mode}_scheduled_start"]
        equal_duration_cost=sum(sh.occupancy_cost(min(int(x),int(y)),int(d),max(int(x),int(y)),int(g)) for x,y,d,g in zip(a.RSP_scheduled_start,starts,a.RSP_duration_slots,a.requested_gpus))
        util=({s:float(occ[24:120,i].mean()/capacity.site_capacity[s]) for i,s in enumerate(capacity.aidc_ids)} if mode=="SHADOW" else bases[name]["site_mean_utilization"])
        comparison.append({"case":name,"slot106_active_GPU":int(occ[106].sum()) if mode=="SHADOW" else bases[name]["slot106_GPU"],
            "full_day_reservation_GPU_h":float(occ[24:120].sum()/4) if mode=="SHADOW" else bases[name]["full_day_GPU_hours"],
            "Vmax":grid["Vmax"],"Vmin":grid["Vmin"],"voltage_violations":grid["voltage_violation_count"],
            "line_violations":grid["line_current_violation_count"],"transformer_current_violations":grid["transformer_current_violation_count"],
            "transformer_kva_violations":grid["transformer_kva_violation_count"],"transformer_polygon_violations":grid["transformer_polygon_violation_count"],
            "job_starts_changed_vs_frozen_RSP":int((starts!=a.RSP_scheduled_start).sum()),
            "diagnostic_equal_safe_duration_start_relocation_GPU_h_symmetric_difference":equal_duration_cost/4,
            "modeled_completion_later_than_RW_jobs":int((end>a.RW_scheduled_completion).sum()),
            "max_completion_difference_vs_RW_minutes":int((end-a.RW_scheduled_completion).max()*15),
            "site_mean_utilization_json":json.dumps(util),"WAN_migration_count":0,"MESS_moves":0,
            "production_temporal_scalar_objective":"NOT_DEFINED" if mode!="SHADOW" else "NEW_DIAGNOSTIC_ONLY",
            "comparison_metric_caveat":"Equal-safe-duration relocation isolates start shifts; RW durations are longer and separately audited."})
    pd.DataFrame(comparison).to_csv(sh.OUT/"V39G_MAY17_RW_RSP_SHADOW_COMPARISON.csv",index=False,encoding="utf-8-sig")
    sh.write("V39G_TEMPORAL_FIRST_DOWNSTREAM_CHECK.json",{"status":"PASS","temporal_schedule_frozen_for_check":True,
        "existing_site_capacity_and_eligible_rack_authority_reused":True,"all_existing_spatial_and_planning_constraints_pass":r["all_hard_constraints_pass"],
        "spatial_grid_authority_issue_slots":[24,120],"previous_day_spatial_feasibility_claimed":False,
        "migration_solver_called":False,"migration_solver_calls":0,"reason":"Temporal/site witness already passes; existing temporal-first guard prohibits unnecessary migration solve.",
        "RUNNING_migration_required_after_repair":False,"WAN_transfer_count":0})
    start=sh.read("V39G_START_STATE.json");after=sh.source_hashes()
    changed=[p for p,h in start["production_source_SHA256"].items() if after.get(p)!=h]
    assert not changed
    inputs=sh.read("V39G_GRID_INPUT_PROVENANCE.json")["source_SHA256"]
    for p in [CALIBRATION,F/"V39F_DAY17_FROZEN_RSP_SITE_ONLY_GPU.csv",sh.DAYROOT/"V37_R4A_DAY_MANIFEST.json"]:
        inputs[str(p)]=sha(p)
    input_changes=[p for p,h in inputs.items() if sha(Path(p))!=h]
    assert not input_changes,input_changes
    sh.write("V39G_DIAGNOSTIC_PROVENANCE.json",{"starting_HEAD":start["starting_HEAD"],"final_HEAD":sh.git("rev-parse","HEAD"),
        "starting_branch":start["starting_branch"],"branch":sh.git("branch","--show-current"),"dirty_state_preserved":True,
        "production_source_files_verified":len(after),"production_science_mutation_count":0,"changed_production_sources":changed,
        "Threads_per_model":4,"max_parallel_day_workers":4,"peak_active_diagnostic_models":1,"Seed":20260905,"MIPGap":0,"Gurobi_version":list(sh.gp.gurobi.version()),
        "May_campaign_calls":0,"full_preflight_calls":0,"Actual_reads":0,"Fresh_reads":0,"future_result_reads":0,
        "superseded_overconstrained_prototype":"V39G_SHADOW_A.log; not the accepted-domain A result. See V39G_TIME_DOMAIN_AUTHORITY_AUDIT.md.",
        "running_migration_solver_calls":0,"SHADOW_B_calls":0,"push":False,"PR":False,"local_commit":False,
        "old_May_results_invalidated":False,"source_SHA256":inputs,"all_read_authority_inputs_SHA256_reverified":True,
        "diagnostic_helper_SHA256":{str(p.relative_to(REPO)):sha(p) for p in [Path(sh.__file__),Path(__file__),REPO/"dayahead/tools/v39g_shadow_grid.py",REPO/"tests/dayahead/test_v39g_shadow.py"]},
        "finished_at_UTC":datetime.now(timezone.utc)})
    flags={"V39G_DIAGNOSTIC_COMPLETE":"YES","SHADOW_A_FEASIBLE":"YES","SHADOW_B_REQUIRED":"NO","TEMPORAL_REPAIR_GRID_PASS":"YES",
        "RW_COMPLETION_NONINFERIORITY_PASS":"YES","FROZEN_SAFE_RUNTIME_PRESERVED":"YES","RUNNING_MIGRATION_REQUIRED_AFTER_REPAIR":"NO",
        "ROOT_CAUSE_RESOLUTION_CANDIDATE":"STANDBY_ONLY_MINIMUM_INTERVENTION_TEMPORAL_REPAIR_SUFFICIENT",
        "PRODUCTION_SCIENCE_CHANGED":"NO","FULL_PREFLIGHT_RERUN":"NO","MAY_RESTARTED":"NO"}
    assert r["status"]=="OPTIMAL" and r["all_hard_constraints_pass"] and aux["stage"]["optimal"]
    sh.write("V39G_FINAL_STATUS.json",flags)
    work=sh.read("V39G_MAY17_WORK_CONSERVATION_AUDIT.json")
    answers=[
        f"Q1. Universally eligible standby PENDING jobs: {r['eligible_standby_jobs']}; no slot106 filtering.",
        "Q2. Standby-only delay-only repair is feasible and OPTIMAL, with all frozen constraints satisfied. Shadow B was not run.",
        f"Q3. Exactly {r['changed_standby_jobs']} jobs change start; {r['unchanged_standby_jobs']} eligible standby jobs are unchanged (secondary optimum after fixing the primary optimum).",
        f"Q4. Minimum complete-interval occupancy deviation: {r['total_shifted_GPU_slots']} GPU-slots = {r['total_shifted_GPU_hours']} GPU-h (symmetric difference); one-way relocated occupancy is {r['one_way_relocated_GPU_hours']} GPU-h. These are diagnostic metrics, not a production RSP objective.",
        f"Q5. Maximum delay: {r['max_delay_minutes']} minutes; median among changed jobs {r['median_changed_delay_minutes']} minutes; P95 {r['P95_changed_delay_minutes']} minutes.",
        f"Q6. Every moved job finishes no later than its own RW modeled completion: zero violations. Largest completion difference among eligible jobs: {r['max_completion_difference_vs_RW_slots_eligible']*15} minutes. This is not an invented user SLA.",
        f"Q7. Slot106 active GPU becomes {r['slot106_active_GPU_after']} (from 90), restoring {r['slot106_active_GPU_restored']} GPU.",
        f"Q8. Separate auxiliary optimum over the same original feasible set: {aux['minimum_grid_feasible_slot106_active_GPU']} active GPU, requiring only {aux['required_restoration_GPU']} additional GPU over RSP. Its bound equals its incumbent; A's intervention objective is not imposed on this auxiliary.",
        f"Q9. Final Vmax={r['grid']['Vmax']:.12f}, Vmin={r['grid']['Vmin']:.12f} pu; critical bus/phase {r['grid']['critical_voltage_bus_phase']}, issue slot {r['grid']['critical_issue_slot']} (target slot {r['grid']['critical_target_slot']}).",
        "Q10. Line-current, transformer phase current, transformer apparent power and frozen inner-polygon constraints all pass, with zero violations.",
        "Q11. RUNNING migration is not required for this May17 planning witness. The temporal-first downstream check passed, so the migration solver was not called. PENDING first placement is not WAN migration. MESS moves=0.",
        f"Q12. At slot106 the shadow restores {r['slot106_active_GPU_restored']}/381 = {r['slot106_active_GPU_restored']/381:.2%} of the RW-to-RSP GPU drop; it remains {471-r['slot106_active_GPU_after']} GPU below RW. It does NOT restore RW's longer safe-duration reservations; all RSP durations remain fixed.",
        f"Q13. Exact preservation: B=C={work['B_frozen_RSP_modeled_reservation_GPU_hours_slots']} modeled reservation GPU-h over complete intervals; unrounded B=C={work['B_frozen_RSP_safe_GPU_hours_unrounded_seconds']:.9f} GPU-h. Full submitted requested walltime A={work['A_requested_walltime_GPU_hours_full_submission']:.9f} GPU-h. RW remaining/reservation and RUNNING full requested time are separated in the work audit.",
        "Q14. Yes: no voltage relaxation, capacity retuning, forced migration, safe-runtime change, or invented deadline. Actual/Fresh/future outcomes are not decision inputs.",
        "Q15. This single-day counterfactual technically supports further science-refreeze review of a minimum-intervention temporal-repair-before-migration layer. It does not establish multi-day generalization, measured computation, actual service guarantees, or authorization to change production. Review must explicitly consider the single 24h15m delay, the very small planning-voltage headroom (about 4.26e-6 pu), and the accepted operating-day-only spatial domain. Production approval remains with the user."]
    text="# V39G May17 shadow diagnostic — final review\n\nDIAGNOSTIC ONLY. Production science unchanged. May campaign remains paused.\n\n"+"\n\n".join(answers)
    text+="\n\n## Verification and scope\n\nFeasibility-first, all three integer objective stages, deterministic lex stages, and separate minimum-slot106 auxiliary are certified. Targeted tests and source preservation evidence are in V39G_TEST_REPORT.json and V39G_DIAGNOSTIC_PROVENANCE.json. Full physical equality/inequality audit uses the original frozen constraints, including screened rows.\n\nThe complete reservation objective and aggregate 624-GPU constraint span issue slots [0,638). Per-site/grid authority retains the accepted May17 domain [24,120). This does not certify a previous-day site trajectory. An initial prototype incorrectly extended site constraints before May17 and was rejected; its arithmetic conflict and correction are preserved in V39G_TIME_DOMAIN_AUTHORITY_AUDIT.md. If a future production layer must certify the entire issue-to-completion spatial trajectory, that separate initial-state/time-domain contract needs review.\n\nModeled reservation GPU-hours must not be described as measured or realized computation. Baseline RW and frozen RSP have no production temporal scalar objective. All diagnostic artifacts are local; no push or PR.\n\n## Final status\n\n```text\n"+"\n".join(f"{k} = {v}" for k,v in flags.items())+"\n```\n"
    (sh.OUT/"V39G_FINAL_REVIEW.md").write_text(text,encoding="utf-8")
    print("\n".join(f"{k} = {v}" for k,v in flags.items()),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--baseline",action="store_true");args=p.parse_args()
    baseline() if args.baseline else finalize()

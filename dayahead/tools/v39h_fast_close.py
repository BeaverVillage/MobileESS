"""User-authorized primary-only closure; never constructs an optimizer."""
import json
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from dayahead.tools import run_v39h_shadow as h
from dayahead.tools import v39h_shadow_report as report

def verify(day):
    assert day in ("2025-05-25","2025-05-26")
    out=h.ROOT/"days"/day
    protected=h.read(h.ROOT/"V39H_FAST_CLOSE_PROTECTED_CHECKPOINTS.json")["saved"][day]
    existing=out/"V39H_FAST_CLOSE_WITNESS_CERTIFICATE.json"
    if existing.exists():
        cert=h.read(existing)
        assert cert["independent_verifier_pass"]
        assert h.grid.sha(out/"V39H_SHADOW_SCHEDULE.parquet")==cert["final_schedule_SHA256"]
        print(day,"REUSED_VERIFIED_FAST_CLOSE_WITNESS",flush=True);return
    equivalence=report.equivalent_formulation();a,_,hashes=h.inputs(day)
    for p,sha in h.read(out/"V39H_INPUT_AUTHORITY.json")["input_SHA"].items():assert h.grid.sha(Path(p))==sha,p
    source=Path(protected["saved_witness"]);assert h.grid.sha(source)==protected["witness_SHA256"]
    assert h.grid.sha(out/"V39H_OBJECTIVE_CERTIFICATES.json")==protected["objective_certificate_SHA256"]
    b=pd.read_parquet(source)
    for col in a.columns:assert np.array_equal(a[col].fillna("<NA>"),b[col].fillna("<NA>")),col
    stages=h.read(out/"V39H_OBJECTIVE_CERTIFICATES.json")["stages"]
    primary=stages[1]
    assert primary["optimal"] and primary["objective"]==primary["bound"]==protected["primary"]
    actual_primary=sum(h.v39g.occupancy_cost(int(r.RSP_scheduled_start),int(r.RSP_duration_slots),int(r.scheduled_start_slot),int(r.requested_gpus)) for r in b.itertuples(index=False))
    assert actual_primary==protected["primary"]==int(b.occupancy_deviation_GPU_slots.sum())
    if day=="2025-05-26":assert stages[2]["optimal"] and stages[2]["objective"]==stages[2]["bound"]==int(b.start_delay_slots.ne(0).sum())==8
    assert (b.scheduled_start_slot>=b.RSP_scheduled_start).all()
    assert (b.scheduled_start_slot<=b.latest_start).all()
    assert np.array_equal(b.scheduled_end_slot-b.scheduled_start_slot,a.RSP_duration_slots)
    cap,_=h._load_capacity(h.REPO);cs,nodes=h.grid.load_coefficients(out)
    with np.load(out/"V39G_C1_INTEGER_TABLES.npz") as z:tables={s:z[s].copy() for s in cap.aidc_ids}
    bundle={"capacity":cap,"sites":tuple(cap.aidc_ids),"coefficients":cs,"nodes":nodes,"tables":tables}
    h.status(out,"FAST_CLOSE_INDEPENDENT_VERIFICATION",error=None)
    print(day,"INDEPENDENT_VERIFIER_START_NO_OPTIMIZATION",flush=True)
    audit,occ,pcc=h.cloned_v39g(out).audit_schedule(b,bundle)
    assert audit["all_hard_constraints_pass"] and audit["grid"]["Vmax"]<=1.05 and audit["grid"]["Vmin"]>=.95
    assert audit["RUNNING_migration_calls"]==audit["WAN_transfer_count"]==0
    interrupts=[]
    for line in (out/"V39H_WORKER_STDOUT.log").read_text(encoding="utf-8",errors="replace").splitlines():
        if line.startswith('{"stage":'):
            row=json.loads(line)
            if row.get("status")==11:interrupts.append(row)
    assert interrupts and not interrupts[-1]["optimal"]
    fingerprint=h.digest({"model_SHA":h.model_hash(),"day":day,"input_SHA":hashes})
    result={"day":day,"input_model_SHA":fingerprint,"existing_migration_count":h.BASE_COUNTS[day],"base_RSP_status":"INFEASIBLE",
        "shadow_status":"PRIMARY_OPTIMAL_FEASIBLE","classification":"TEMPORAL_REPAIR_SUFFICIENT","temporal_repair_sufficient":True,"post_candidate_migration_count":0,
        "PRIMARY_TEMPORAL_INTERVENTION_OPTIMUM":actual_primary,"PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL":"YES",
        "SECONDARY_CHANGED_JOB_OPTIMALITY":"YES" if day=="2025-05-26" else "BEST_FEASIBLE_NOT_GLOBALLY_CERTIFIED",
        "TERTIARY_DELAY_OPTIMALITY":"BEST_FEASIBLE_NOT_GLOBALLY_CERTIFIED" if day=="2025-05-26" else "NOT_REQUIRED",
        "exact_full_lex":False,"fast_close_primary_only":True,"stages":stages,"interrupted_tie_break_stages":interrupts,
        "selected_witness":"SAVED_SECONDARY_OPTIMAL_WITNESS" if day=="2025-05-26" else "FALLBACK_TO_SAVED_PRIMARY_OPTIMAL_WITNESS",
        "selection_caveat":"May25 in-memory 14-job incumbent was not serialized by the original strict worker. Its saved 15-job primary-optimal witness is the user-authorized fallback, not the best known changed-job count." if day=="2025-05-25" else "Saved witness has certified minimum 8 changed jobs; its delay equals the interrupted tertiary incumbent value but no global tertiary optimum is claimed.",
        "RUNNING_migration_calls_in_temporal_shadow":0,"new_primary_optimization_calls":0,"new_migration_optimization_calls":0,
        "Threads":4,"Seed":h.SEED,"MIPGap":0,"secondary_exact_proof_required":False,"tertiary_exact_proof_required":False,"sidecar":False,"audit":audit}
    np.savez_compressed(out/"V39H_WITNESS.npz",GPU_complete=occ,PCC_target=pcc)
    decision=h.read(h.BASE/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json")["decision"]
    h.save_day(a,b,out,result,decision,bundle)
    b["schedule_class"]="TEMPORAL_SHADOW_PRIMARY_OPTIMAL_FEASIBLE_NOT_FULL_LEX_CERTIFIED"
    b.to_parquet(out/"V39H_SHADOW_SCHEDULE.parquet",index=False)
    b.loc[b.start_delay_slots.ne(0)].to_csv(out/"V39H_CHANGED_JOBS.csv",index=False,encoding="utf-8-sig")
    certificate={"status":"PASS_PRIMARY_OPTIMAL_FEASIBLE","day":day,"independent_verifier_pass":True,
        "saved_witness_SHA256":protected["witness_SHA256"],"final_schedule_SHA256":h.grid.sha(out/"V39H_SHADOW_SCHEDULE.parquet"),
        "primary_certificate_SHA256":protected["objective_certificate_SHA256"],"certified_primary":actual_primary,"complete_primary_recomputed_from_intervals":actual_primary,
        "newly_introduced_RW_completion_violations":0,"exact_full_lex":False,"new_optimization_calls":0,
        "Actual_Fresh_future_reads":0,"stage_statuses":{k:result[k] for k in ("PRIMARY_TEMPORAL_INTERVENTION_OPTIMAL","SECONDARY_CHANGED_JOB_OPTIMALITY","TERTIARY_DELAY_OPTIMALITY")},"audit":audit}
    h.atomic(existing,certificate)
    h.atomic(out/"V39H_ASSEMBLY_EQUIVALENCE.json",{"status":"PASS","input_files_unchanged":True,"all_decision_relevant_function_SHA_unchanged":True,
        "formulation_SHA_evidence":equivalence,"new_solver_calls":0,"fast_close_authority":"User PRIMARY OPTIMALITY ONLY correction","current_input_model_SHA":fingerprint,
        "completed_primary_certificate_unchanged":True,"witness_certificate_SHA256":h.grid.sha(existing)})
    p=h.read(out/"V39H_DAY_PROGRESS.json");p.pop("error",None);h.atomic(out/"V39H_DAY_PROGRESS.json",p)
    print(day,"PASS",actual_primary,"changed",result["changed_jobs"],"Vmax",result["Vmax"],flush=True)

if __name__=="__main__":
    with threadpool_limits(limits=4):
        for day in ("2025-05-25","2025-05-26"):verify(day)

"""Exact monotone integer threshold search on the unchanged primary-optimal face."""
from __future__ import annotations
import argparse
from collections import Counter
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import FunctionType
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from dayahead.tools import run_v39i_minmax as i
h=i.h
ROOT=i.ROOT


def build(a,out,day,upper):
    ns=dict(h.build_model.__globals__);original=h.candidate_options
    def options(cohort,sites):
        yield from ((site,start) for site,start in original(cohort,sites) if start-cohort["lo"]<=upper)
    ns.update(atomic=i.atomic,candidate_options=options)
    builder=FunctionType(h.build_model.__code__,ns,h.build_model.__name__,h.build_model.__defaults__)
    bundle=builder(a,out,"V39I_THRESHOLD_FEASIBILITY");m=bundle["model"]
    row=m.addConstr(bundle["objectives"][0]==i.PRIMARY[day],name="CERTIFIED_PRIMARY_EXACT_EQUALITY")
    m.setObjective(0,h.GRB.MINIMIZE);m.update()
    assert row.Sense=="=" and row.RHS==i.PRIMARY[day]
    return bundle


def warm_start(bundle,witness,threshold):
    cs=bundle["cohorts"];which={uid:k for k,c in enumerate(cs) for uid in c["members"]}
    counts=Counter((which[r.job_uid],r.AIDC,int(r.scheduled_start_slot)) for r in witness.itertuples(index=False))
    invalid={k for k,site,start in counts if start-cs[k]["lo"]>threshold}
    for (k,site,start),var in bundle["variables"].items():
        var.UB=len(cs[k]["members"]) if start-cs[k]["lo"]<=threshold else 0
        var.Start=h.GRB.UNDEFINED if k in invalid else counts[k,site,start]
    return {"source_witness_max_delay_slots":int(witness.start_delay_slots.max()),
        "fully_valid_at_threshold":not invalid,"cohorts_with_partial_start_released":len(invalid),
        "note":"Warm starts are hints, not site/time restrictions. Cohorts whose old delay exceeds T have all start hints released."}


def check_schedule(b,day,threshold):
    assert int(b.occupancy_deviation_GPU_slots.sum())==i.PRIMARY[day]
    assert int(b.start_delay_slots.max())<=threshold
    assert b.job_uid.is_unique and (b.start_delay_slots>=0).all()
    assert (b.scheduled_start_slot<=b.latest_start).all()
    assert (b.loc[~b.eligible,"start_delay_slots"]==0).all()


def worker(day):
    out=ROOT/"days"/day;(out/"temp").mkdir(exist_ok=True)
    os.environ["TEMP"]=str(out/"temp");os.environ["TMP"]=str(out/"temp")
    for name in ("V39I_D_MAX_SOLVER_CERTIFICATE.json","V39I_INPUT_EQUIVALENCE.json","V39I_MINMAX_FORMULATION.json"):
        dst=out/name.replace("V39I_","V39I_DIRECT_",1)
        if (out/name).exists() and not dst.exists():shutil.copy2(out/name,dst)
    a,old,input_fp=i.prepare(day,out)
    fingerprint=h.digest({"input_fingerprint":input_fp,"threshold_source_SHA256":h.grid.sha(Path(__file__)),"engine":"MONOTONE_INTEGER_THRESHOLD_FEASIBILITY"})
    eq=h.read(out/"V39I_INPUT_EQUIVALENCE.json");eq.update(fingerprint=fingerprint,engine="MONOTONE_INTEGER_THRESHOLD_FEASIBILITY")
    i.atomic(out/"V39I_INPUT_EQUIVALENCE.json",eq)
    final=out/"V39I_MINMAX_DELAY_RESULT.json"
    if final.exists() and h.read(final).get("fingerprint")==fingerprint:
        i.progress(out,"COMPLETE",reused=True);return
    upper=int(old.start_delay_slots.max());lower=-1;best=old.copy()
    direct=h.read(out/"V39I_DIRECT_D_MAX_SOLVER_CERTIFICATE.json")
    # Valid global lower bound from interrupted direct D_MAX solve. Final proof
    # still requires an explicitly solved adjacent infeasible threshold.
    if "bound" in direct:lower=max(lower,math.ceil(direct["bound"])-1)
    i.progress(out,"BUILD_THRESHOLD_FEASIBILITY",initial_infeasible_bound=lower,initial_feasible_upper=upper)
    bundle=build(a,out,day,upper);m=bundle["model"]
    i.atomic(out/"V39I_MINMAX_FORMULATION.json",{"primary_equality_RHS":i.PRIMARY[day],"primary_constraint_sense":"=",
        "objective":"CONSTANT_ZERO_FEASIBILITY_ONLY","engine":"MONOTONE_INTEGER_THRESHOLD_FEASIBILITY",
        "threshold_definition":"All original allocation variables with start-lo>T have UB=0; every original legal option at delay<=T retains its original cohort UB and constraints.",
        "monotonicity_proof":"For integer T1<=T2, F(T1) is a subset of F(T2). Only an upper bound on eligible added delay changes. Voltage itself is not prescreened or presumed monotone in load.",
        "incumbent_D_MAX_upper_bound_slots":upper,"primary_reoptimization_calls":0,"secondary_changed_job_equality_added":False,
        "warm_start_from_V39H":True,"fixed_V39H_eligibility_site_grid_C1_resource_constraints":True,
        "exact_certificate_required":"T* FEASIBLE and T*-1 INFEASIBLE, plus independent final witness verification",
        "D_MAX_direct_objective_continued":False,"no_primary_or_migration_MILP_rerun":True})
    history=[];best_cert=None

    def query(threshold,witness):
        directory=out/"thresholds"/f"T{threshold:04d}";directory.mkdir(parents=True,exist_ok=True)
        cert_path=directory/"V39I_THRESHOLD_CERTIFICATE.json";schedule=directory/"V39I_THRESHOLD_FEASIBLE_SCHEDULE.parquet"
        if cert_path.exists():
            cert=h.read(cert_path);assert cert["fingerprint"]==fingerprint
            if cert["outcome"] in ("FEASIBLE","INFEASIBLE"):
                b=pd.read_parquet(schedule) if cert["outcome"]=="FEASIBLE" else None
                if b is not None:
                    assert h.grid.sha(schedule)==cert["schedule_SHA256"];check_schedule(b,day,threshold)
                return cert,b
        start_info=warm_start(bundle,witness,threshold)
        m.Params.LogFile=str(directory/"V39I_THRESHOLD_SOLVER.log")
        m.ModelName=f"V39I_{day}_T{threshold}_PRIMARY_FIXED";m.update()
        i.progress(out,"THRESHOLD_FEASIBILITY_SOLVE",threshold_slots=threshold,lower_infeasible=lower,upper_feasible=upper)
        stage=h.cloned_v39g(out).solve_stage(m,0,f"FEASIBILITY_PRIMARY_FIXED_DELAY_LE_{threshold}")
        cert={"day":day,"threshold_slots":threshold,"threshold_minutes":threshold*15,"fingerprint":fingerprint,
            "stage":stage,"model_fingerprint":int(m.Fingerprint),"primary_exact_equality":i.PRIMARY[day],
            "warm_start":start_info,"completed_at":h.now(),"outcome":"UNKNOWN"}
        b=None
        if m.SolCount:
            b=h.cloned_v39g(out).expanded(a,bundle);check_schedule(b,day,threshold)
            b.to_parquet(schedule,index=False)
            cert.update(outcome="FEASIBLE",actual_max_delay_slots=int(b.start_delay_slots.max()),schedule_SHA256=h.grid.sha(schedule))
        elif m.Status==h.GRB.INFEASIBLE:cert.update(outcome="INFEASIBLE",globally_infeasible=True)
        i.atomic(cert_path,cert)
        assert cert["outcome"]!="UNKNOWN",cert
        return cert,b

    while upper-lower>1:
        threshold=(upper+lower)//2;cert,b=query(threshold,best);history.append(cert)
        if b is not None:
            best=b;best_cert=cert;upper=int(b.start_delay_slots.max())
        else:lower=threshold
        i.atomic(out/"V39I_THRESHOLD_SEARCH_PROGRESS.json",{"fingerprint":fingerprint,"history":history,
            "lower_infeasible_threshold":lower,"upper_feasible_threshold":upper,"last_update":h.now()})
    assert upper>=1  # Both reused primary optima are strictly positive.
    adjacent,b=query(upper-1,best)
    assert b is None and adjacent["outcome"]=="INFEASIBLE"
    if not any(c["threshold_slots"]==upper-1 for c in history):history.append(adjacent)
    check_schedule(best,day,upper)
    schedule_path=out/"V39I_MINMAX_DELAY_SCHEDULE.parquet";best.to_parquet(schedule_path,index=False)
    i.progress(out,"INDEPENDENT_VERIFIER",exact_D_MAX_slots=upper)
    audit,occ,pcc=h.cloned_v39g(out).audit_schedule(best,bundle)
    assert audit["all_hard_constraints_pass"] and audit["grid"]["Vmax"]<=1.05 and audit["grid"]["Vmin"]>=.95
    assert np.array_equal(a.RSP_duration_seconds,best.RSP_duration_seconds) and np.array_equal(a.requested_gpus,best.requested_gpus)
    np.savez_compressed(out/"V39I_VERIFIED_WITNESS.npz",GPU_complete=occ,PCC_target=pcc)
    i.atomic(out/"V39I_GRID_VERIFICATION.json",{"status":"PASS","day":day,**audit,"upper_voltage_headroom_pu":1.05-audit["grid"]["Vmax"],
        "lower_voltage_headroom_pu":audit["grid"]["Vmin"]-.95,"site_grid_domain_issue_slots":[24,120],"Actual_reads":0,"Fresh_reads":0})
    feasible={"threshold_slots":upper,"outcome":"FEASIBLE","actual_max_delay_slots":int(best.start_delay_slots.max()),
        "schedule_SHA256":h.grid.sha(schedule_path),"independently_verified":True,
        "source_threshold_certificate":best_cert,"source":"FEASIBLE_THRESHOLD_WITNESS" if best_cert else "REUSED_V39H_UPPER_BOUND_WITNESS",
        "proof":"The saved full witness satisfies every hard constraint, exact primary equality, and every delay <= T*. Its actual maximum is exactly T*."}
    exact={"status":"EXACT_BY_ADJACENT_THRESHOLDS","day":day,"T_star_slots":upper,"T_star_minutes":upper*15,
        "T_star_FEASIBLE":feasible,"T_star_minus_1_INFEASIBLE":adjacent,"primary_equality":i.PRIMARY[day],
        "D_MAX_exact_optimality":True,"proof":"F(T) nested in integer T; feasible at T* and globally infeasible at T*-1 imply exact minimum D_MAX=T*.",
        "Threads":4,"Seed":h.SEED,"MIPGap_setting":0,"integer_exactness":True,
        "synthetic_direct_objective_gap_reported":False,"fingerprint":fingerprint}
    i.atomic(out/"V39I_D_MAX_SOLVER_CERTIFICATE.json",exact)
    result={"status":"OPTIMAL_BY_ADJACENT_THRESHOLDS_AND_INDEPENDENTLY_VERIFIED","day":day,"fingerprint":fingerprint,
        "certified_primary_optimum":i.PRIMARY[day],"primary_equality_exact":True,"D_MAX_slots":upper,"D_MAX_minutes":upper*15,
        "D_MAX_exact_optimality":True,"solver_certificate":exact,"schedule_SHA256":h.grid.sha(schedule_path),
        "deterministic_witness_selection":"Fixed Seed/Threads, cached threshold witnesses and sorted UID/cohort expansion; no additional lexical or changed-count optimization.",
        "changed_job_optimality_claim":False,"secondary_optimization_calls":0,"primary_optimization_reruns":0,"migration_MILP_reruns":0,
        "full_preflight_calls":0,"May_campaign_calls":0,"Actual_reads":0,"Fresh_reads":0,"audit":audit,
        "safe_runtime_exactly_preserved":True,"threshold_history":history,"threshold_optimization_calls":len(history),
        "direct_minmax_attempt_interrupted_not_restarted":True,"completed_at":h.now()}
    i.atomic(final,result);m.dispose();i.progress(out,"COMPLETE",D_MAX_minutes=upper*15,certificate="ADJACENT_THRESHOLDS")
    print(day,"EXACT_THRESHOLD_MINMAX_PASS",upper*15,flush=True)


def orchestrate():
    running={};done=[];failed={}
    for day in i.DAYS:
        out=ROOT/"days"/day;log=(out/"V39I_THRESHOLD_WORKER_STDOUT.log").open("ab")
        p=subprocess.Popen([sys.executable,"-u",str(Path(__file__).resolve()),"--day",day],cwd=REPO,stdout=log,stderr=subprocess.STDOUT,
            env=dict(os.environ,OPENBLAS_NUM_THREADS="4",OMP_NUM_THREADS="4",MKL_NUM_THREADS="4"),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        running[day]=(p,log)
    while running:
        for day,(p,log) in list(running.items()):
            if p.poll() is not None:
                log.close();running.pop(day)
                if p.returncode==0:done.append(day)
                else:failed[day]=p.returncode
        i.atomic(ROOT/"V39I_PROGRESS.json",{"phase":"THRESHOLD_SEARCH_RUNNING" if running else "SOLVES_COMPLETE" if not failed else "NEEDS_DIAGNOSIS",
            "engine":"MONOTONE_INTEGER_THRESHOLD_FEASIBILITY","completed_days":done,"running_days":list(running),
            "worker_PIDs":{day:p.pid for day,(p,log) in running.items()},"failed_days":failed,"last_update":h.now(),"max_workers":2,"Threads_per_model":4})
        if running:time.sleep(5)
    assert not failed,failed


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--day",choices=i.DAYS);args=parser.parse_args()
    with threadpool_limits(limits=4):worker(args.day) if args.day else orchestrate()

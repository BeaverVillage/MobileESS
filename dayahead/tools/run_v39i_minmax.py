"""Two-day min-max diagnostic on immutable V39H primary-optimal faces."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import inspect
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
from dayahead.tools import run_v39h_shadow as h
from dayahead.tools import v39h_shadow_report as hr

ROOT=REPO/"dayahead/artifacts/v39i_may25_26_primary_optimal_minmax_delay"
DAYS=("2025-05-25","2025-05-26")
PRIMARY={"2025-05-25":29568,"2025-05-26":13086}
MAX_PARALLEL_DAY_WORKERS=2
GUROBI_THREADS_PER_MODEL=4
LABELS=["PRIMARY_OPTIMAL_MINIMUM_MAX_DELAY_DIAGNOSTIC","NOT_PRODUCTION_SCIENCE","NO_PRIMARY_OR_MIGRATION_REOPTIMIZATION"]

def atomic(path,data):h.atomic(path,{"labels":LABELS,**data})
def metadata(root):
    result={}
    for p in Path("\\\\?\\"+str(root)).rglob("*"):
        if p.is_file():
            st=p.stat();result[str(p.relative_to(Path("\\\\?\\"+str(root))))]=[st.st_size,st.st_mtime_ns]
    return result

def initialize():
    ROOT.mkdir(parents=True,exist_ok=True);path=ROOT/"V39I_START_STATE.json"
    if path.exists():return
    manifest=h.read(h.ROOT/"V39H_REQUIRED_ARTIFACT_SHA_MANIFEST.json")
    assert h.read(h.ROOT/"V39H_FINAL_STATUS.json")["V39H_DIAGNOSTIC_COMPLETE"]=="YES"
    assert all(h.grid.sha(h.ROOT/n)==s for n,s in manifest["SHA256"].items())
    atomic(path,{"start_time":h.now(),"starting_HEAD":h.v39g.git("rev-parse","HEAD"),"starting_branch":h.v39g.git("branch","--show-current"),
        "starting_dirty_state":h.v39g.git("status","--porcelain"),"production_source_SHA256":h.v39g.source_hashes(),
        "V39E_F_G_metadata":h.preserved_metadata(),"V39H_metadata":metadata(h.ROOT),"V39H_required_SHA256":manifest["SHA256"],
        "Gurobi_version":h.gp.gurobi.version(),"max_day_workers":2,"Threads_per_model":4,"Seed":h.SEED,"MIPGap":0,
        "process_state":subprocess.check_output(["powershell","-NoProfile","-Command","Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],text=True,encoding="utf-8",errors="replace")})

def progress(out,phase,**kwargs):atomic(out/"V39I_DAY_PROGRESS.json",{"day":out.name,"PID":os.getpid(),"phase":phase,"last_update":h.now(),**kwargs})

def prepare(day,out):
    assert day in DAYS;out.mkdir(parents=True,exist_ok=True)
    equivalence=hr.equivalent_formulation();a,_,hashes=h.inputs(day)
    old_root=h.ROOT/"days"/day;old_path=old_root/"V39H_SHADOW_SCHEDULE.parquet";old=pd.read_parquet(old_path)
    cert_path=old_root/"V39H_OBJECTIVE_CERTIFICATES.json";cert=h.read(cert_path)["stages"][1]
    assert cert["optimal"] and cert["objective"]==cert["bound"]==PRIMARY[day]
    assert int(old.occupancy_deviation_GPU_slots.sum())==PRIMARY[day]
    assert h.read(old_root/"V39H_SHADOW_A_RESULT.json")["audit"]["all_hard_constraints_pass"]
    for column in a:assert np.array_equal(a[column].fillna("<NA>"),old[column].fillna("<NA>")),column
    hashes.update({str(old_path):h.grid.sha(old_path),str(cert_path):h.grid.sha(cert_path)})
    for name in ("V39G_FROZEN_GRID_COEFFICIENTS.npz","V39G_C1_INTEGER_TABLES.npz"):
        src=old_root/name;dst=out/name
        if not dst.exists():shutil.copy2(src,dst)
        assert h.grid.sha(src)==h.grid.sha(dst);hashes[str(src)]=h.grid.sha(src)
    fingerprint=h.digest({"primary":PRIMARY[day],"input_SHA256":hashes,"model_file_SHA256":h.grid.sha(Path(__file__))})
    atomic(out/"V39I_INPUT_EQUIVALENCE.json",{"status":"PASS","day":day,"input_SHA256":hashes,"fingerprint":fingerprint,
        "V39H_scientific_formulation_equivalence":equivalence,"certified_primary_stage":cert,
        "V39H_source_witness_SHA256":h.grid.sha(old_path),"primary_reoptimization_calls":0,"migration_reoptimization_calls":0})
    return a,old,fingerprint

def add_minmax(bundle,primary,upper):
    """Exact shared delay-threshold encoding; only `upper` binary variables.

    z[t] is a binary prefix, D_MAX=sum(z). Any selected option with delay d
    forces z[d]=1 and therefore every z[1..d]=1, exactly D_MAX >= d.
    All original allocations remain integer/cohort-count variables.
    """
    m=bundle["model"];vs=bundle["variables"];cs=bundle["cohorts"]
    primary_row=m.addConstr(bundle["objectives"][0]==primary,name="CERTIFIED_PRIMARY_EXACT_EQUALITY")
    dmax=m.addVar(vtype=h.GRB.INTEGER,lb=0,ub=upper,name="D_MAX")
    z=m.addVars(range(1,upper+1),vtype=h.GRB.BINARY,name="DELAY_THRESHOLD")
    m.addConstr(dmax==z.sum(),name="D_MAX_EQUALS_THRESHOLD_PREFIX_LENGTH")
    for t in range(1,upper):m.addConstr(z[t]>=z[t+1],name=f"threshold_prefix[{t}]")
    by_delay=defaultdict(list)
    for (k,site,start),v in vs.items():
        delay=start-cs[k]["lo"]
        if delay:
            assert cs[k]["eligible"] and 0<delay<=upper
            by_delay[k,delay].append(v)
    for (k,d),variables in by_delay.items():
        m.addConstr(h.gp.quicksum(variables)<=len(cs[k]["members"])*z[d],name=f"selected_delay_requires_D_MAX[{k},{d}]")
    for k,c in enumerate(cs):
        if c["eligible"]:
            terms=[d*h.gp.quicksum(variables) for (group,d),variables in by_delay.items() if group==k]
            m.addConstr(h.gp.quicksum(terms)<=len(c["members"])*dmax,name=f"valid_average_delay_bound[{k}]")
    m.update();assert primary_row.Sense=="=" and primary_row.RHS==primary
    return dmax,z

def build(a,old,out,day):
    upper=int(old.start_delay_slots.max());ns=dict(h.build_model.__globals__)
    original_options=h.candidate_options
    def bounded_options(c,sites):
        for site,start in original_options(c,sites):
            if start-c["lo"]<=upper:yield site,start
    ns.update(atomic=atomic,candidate_options=bounded_options)
    builder=FunctionType(h.build_model.__code__,ns,h.build_model.__name__,h.build_model.__defaults__)
    bundle=builder(a,out,"V39I_MINMAX_DELAY");m=bundle["model"]
    dmax,z=add_minmax(bundle,PRIMARY[day],upper)
    which={uid:k for k,c in enumerate(bundle["cohorts"]) for uid in c["members"]}
    counts=Counter((which[r.job_uid],r.AIDC,int(r.scheduled_start_slot)) for r in old.itertuples(index=False))
    assert all(key in bundle["variables"] for key in counts)
    for key,v in bundle["variables"].items():v.Start=counts[key]
    dmax.Start=upper
    for t,v in z.items():v.Start=1
    m.setObjective(dmax,h.GRB.MINIMIZE);m.update()
    atomic(out/"V39I_MINMAX_FORMULATION.json",{"primary_equality_RHS":PRIMARY[day],"primary_constraint_sense":"=","objective":"MINIMIZE_D_MAX_SLOTS",
        "encoding":"Shared binary prefix with integer cohort/start activation; exactly D_MAX >= every selected eligible delay.",
        "incumbent_D_MAX_upper_bound_slots":upper,"worse_than_known_feasible_D_MAX_options_eliminated":True,
        "upper_bound_proof":"Saved independently verified primary-optimal witness establishes a feasible upper bound; options with larger delay cannot belong to a min-max optimum.",
        "D_MAX_binary_threshold_variables":len(z),"primary_reoptimization_calls":0,"secondary_changed_job_equality_added":False,
        "warm_start_from_V39H":True,"fixed_V39H_eligibility_site_grid_C1_resource_constraints":True})
    bundle.update(dmax=dmax,z=z);return bundle

def worker(day):
    out=ROOT/"days"/day;out.mkdir(parents=True,exist_ok=True);(out/"temp").mkdir(exist_ok=True)
    os.environ["TEMP"]=str(out/"temp");os.environ["TMP"]=str(out/"temp")
    progress(out,"INPUT_EQUIVALENCE");a,old,fingerprint=prepare(day,out)
    final=out/"V39I_MINMAX_DELAY_RESULT.json"
    if final.exists() and h.read(final).get("fingerprint")==fingerprint:
        progress(out,"COMPLETE",reused=True);return
    progress(out,"BUILD_PRIMARY_FIXED_MINMAX");bundle=build(a,old,out,day);m=bundle["model"]
    progress(out,"EXACT_D_MAX_OPTIMIZATION",primary_fixed=PRIMARY[day])
    stage=h.cloned_v39g(out).solve_stage(m,bundle["dmax"],"PRIMARY_FIXED_MINIMUM_MAX_DELAY")
    atomic(out/"V39I_D_MAX_SOLVER_CERTIFICATE.json",stage)
    assert stage["optimal"] and stage["gap"]==0 and stage["objective"]==math.ceil(stage["bound"])
    optimum=int(round(m.ObjVal));b=h.cloned_v39g(out).expanded(a,bundle)
    assert int(b.start_delay_slots.max())==optimum
    assert int(b.occupancy_deviation_GPU_slots.sum())==PRIMARY[day]
    b.to_parquet(out/"V39I_MINMAX_DELAY_SCHEDULE.parquet",index=False)
    # This already-feasible fixed-seed incumbent also satisfies D_MAX=D_MAX*.
    # Add the exact face equality; do not solve an unnecessary secondary stage.
    m.addConstr(bundle["dmax"]==optimum,name="CERTIFIED_D_MAX_EXACT_EQUALITY");m.update()
    progress(out,"INDEPENDENT_VERIFIER",exact_D_MAX_slots=optimum)
    audit,occ,pcc=h.cloned_v39g(out).audit_schedule(b,bundle)
    assert audit["all_hard_constraints_pass"] and audit["grid"]["Vmax"]<=1.05 and audit["grid"]["Vmin"]>=.95
    assert (b.scheduled_start_slot<=b.latest_start).all()
    assert np.array_equal(a.RSP_duration_seconds,b.RSP_duration_seconds)
    assert np.array_equal(a.requested_gpus,b.requested_gpus)
    np.savez_compressed(out/"V39I_VERIFIED_WITNESS.npz",GPU_complete=occ,PCC_target=pcc)
    atomic(out/"V39I_GRID_VERIFICATION.json",{"status":"PASS","day":day,**audit,"upper_voltage_headroom_pu":1.05-audit["grid"]["Vmax"],
        "lower_voltage_headroom_pu":audit["grid"]["Vmin"]-.95,"site_grid_domain_issue_slots":[24,120],"Actual_reads":0,"Fresh_reads":0})
    result={"status":"OPTIMAL_AND_INDEPENDENTLY_VERIFIED","day":day,"fingerprint":fingerprint,"certified_primary_optimum":PRIMARY[day],
        "primary_equality_exact":True,"D_MAX_slots":optimum,"D_MAX_minutes":optimum*15,"D_MAX_exact_optimality":True,"solver_certificate":stage,
        "schedule_SHA256":h.grid.sha(out/"V39I_MINMAX_DELAY_SCHEDULE.parquet"),"deterministic_witness_selection":"Fixed model/order/Seed/Threads; sorted UID/cohort expansion of the certified incumbent. No extra full lexical or changed-count optimization.",
        "changed_job_optimality_claim":False,"secondary_optimization_calls":0,"primary_optimization_reruns":0,"migration_MILP_reruns":0,"full_preflight_calls":0,"May_campaign_calls":0,
        "Actual_reads":0,"Fresh_reads":0,"audit":audit,"safe_runtime_exactly_preserved":True,"completed_at":h.now()}
    atomic(final,result);m.dispose();progress(out,"COMPLETE",D_MAX_minutes=optimum*15)
    print(day,"EXACT_MINMAX_PASS",optimum*15,flush=True)

def orchestrate():
    initialize();running={};completed=[];failed={}
    for day in DAYS:
        out=ROOT/"days"/day;out.mkdir(parents=True,exist_ok=True);handle=(out/"V39I_WORKER_STDOUT.log").open("ab")
        p=subprocess.Popen([sys.executable,"-u",str(Path(__file__).resolve()),"--day",day],cwd=REPO,stdout=handle,stderr=subprocess.STDOUT,
            env=dict(os.environ,OPENBLAS_NUM_THREADS="4",OMP_NUM_THREADS="4",MKL_NUM_THREADS="4"),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        running[day]=(p,handle)
    while running:
        for day,(p,handle) in list(running.items()):
            code=p.poll()
            if code is not None:
                handle.close();running.pop(day)
                if code==0:completed.append(day)
                else:failed[day]=code
        atomic(ROOT/"V39I_PROGRESS.json",{"phase":"RUNNING" if running else "SOLVES_COMPLETE" if not failed else "NEEDS_DIAGNOSIS","last_update":h.now(),
            "completed_days":completed,"running_days":list(running),"worker_PIDs":{d:p.pid for d,(p,f) in running.items()},"failed_days":failed,"max_workers":2,"Threads_per_model":4})
        if running:time.sleep(5)
    assert not failed,failed

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--init",action="store_true");p.add_argument("--day",choices=DAYS);args=p.parse_args()
    with threadpool_limits(limits=4):
        initialize() if args.init else worker(args.day) if args.day else orchestrate()

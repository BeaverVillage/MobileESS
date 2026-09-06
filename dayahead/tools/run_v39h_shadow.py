"""Exactly 13 independent V39H day diagnostics. No campaign/preflight entry point."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from types import FunctionType,SimpleNamespace
import traceback
import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
from threadpoolctl import threadpool_limits

REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39g_day17_shadow as v39g
from dayahead.tools import v39h_shadow_grid as grid
from dayahead.v39a.spatial import production_activity
from dayahead.v39d.evaluate import _load_capacity
from dayahead.v39e.full_spatial import _compatible_sites

ROOT=REPO/"dayahead/artifacts/v39h_13day_temporal_repair_migration_shadow"
BASE=REPO/"dayahead/artifacts/v39e_full_may_2025"
BASE_COUNTS={"2025-05-06":12,"2025-05-08":2,"2025-05-10":10,"2025-05-11":7,"2025-05-17":None,"2025-05-18":6,"2025-05-19":22,"2025-05-21":2,"2025-05-22":15,"2025-05-23":4,"2025-05-24":2,"2025-05-25":8,"2025-05-26":15}
DAYS=tuple(BASE_COUNTS)
MAX_PARALLEL_DAY_WORKERS=4
GUROBI_THREADS_PER_MODEL=4
SEED=20260905
LABELS=["MULTI_DAY_SHADOW_DIAGNOSTIC_ONLY","NOT_PRODUCTION_SCIENCE","NO_CAMPAIGN_OR_PREFLIGHT"]

def now():return datetime.now(timezone.utc).isoformat()
def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(v39g.clean({"labels":LABELS,**data}),ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    for attempt in range(100):
        try:os.replace(tmp,path);return
        except PermissionError:time.sleep(.02)
    raise RuntimeError(f"ATOMIC_REPLACE_FAILED:{path}")
def read(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def digest(data):return hashlib.sha256(json.dumps(v39g.clean(data),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def preserved_metadata():
    result={}
    for directory in (BASE,REPO/"dayahead/artifacts/v39f_day17_rsp_temporal_grid_diagnostic",v39g.OUT):
        # Preserve long-name regression fixtures without Windows MAX_PATH loss.
        long_directory=Path("\\\\?\\"+str(directory))
        for p in long_directory.rglob("*"):
            if p.is_file():
                s=p.stat();key=directory.relative_to(REPO)/p.relative_to(long_directory)
                result[str(key)]=[s.st_size,s.st_mtime_ns]
    return result

def model_hash():
    paths=[Path(__file__),Path(grid.__file__),Path(v39g.__file__),REPO/"dayahead/tools/v39g_shadow_grid.py"]
    return digest({str(p.relative_to(REPO)):grid.sha(p) for p in paths})

def initialize():
    ROOT.mkdir(parents=True,exist_ok=True)
    path=ROOT/"V39H_START_STATE.json"
    if not path.exists():
        processes=subprocess.check_output(["powershell","-NoProfile","-Command","Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -or $_.CommandLine -like '*v39e*campaign*' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],text=True,encoding="utf-8",errors="replace")
        reflog=v39g.git("reflog","-1","--format=%gs")
        starting_branch=reflog.split("checkout: moving from ",1)[1].split(" to ",1)[0] if reflog.startswith("checkout: moving from ") else v39g.git("branch","--show-current")
        atomic(path,{"starting_HEAD":v39g.git("rev-parse","HEAD"),"starting_branch":starting_branch,"current_diagnostic_branch":v39g.git("branch","--show-current"),"branch_transition_reflog":reflog,
            "starting_dirty_state":v39g.git("status","--porcelain"),"process_state":processes,"start_time":now(),
            "production_source_SHA256":v39g.source_hashes(),"preserved_artifact_metadata":preserved_metadata(),
            "preservation_method":"File-name/size/mtime_ns inventory; does not read May01-05 Actual/Fresh result contents."})
    atomic(ROOT/"V39H_AFFECTED_DATE_SET.json",{"dates":DAYS,"baseline_per_day_migrations":BASE_COUNTS,"baseline_migration_days":12,"baseline_min_migrations":105,"other_18_days_solved":False})

def inputs(day):
    assert day in DAYS
    dr=REPO/f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}"
    a=pd.read_parquet(dr/"V37_R4A_JOB_LEDGER.parquet");a["job_uid"]=a.job_id.astype(str);a=a.sort_values("job_uid").reset_index(drop=True)
    ss=pd.read_parquet(dr/"V37_R4A_D1_SNAPSHOT.parquet");ss["job_uid"]=ss.id.astype(str)
    exclusions=pd.read_parquet(dr/"V37_R4A_EXCLUSIONS.parquet")
    excluded=set(exclusions.job_id.astype(str)) if len(exclusions) else set()
    assert a.job_uid.is_unique and ss.job_uid.is_unique and not set(a.job_uid)&excluded
    assert set(a.job_uid)|excluded==set(ss.job_uid)
    ss=ss.set_index("job_uid").loc[a.job_uid]
    issue=pd.Timestamp(day,tz=timezone(timedelta(hours=10)))-pd.Timedelta(hours=6)
    visible=pd.to_datetime(ss.submit_time,utc=True)<=issue.tz_convert("UTC")
    assert visible.all() and set(ss.issue_time_fixed_AEST)=={issue.isoformat()}
    assert np.array_equal(ss.qos.astype(str),a.qos.astype(str)) and np.array_equal(ss.state_at_issue,a.state_at_issue)
    a["D1_visible"]=visible.to_numpy()
    a["eligible"]=v39g.eligible_mask(a)
    a["latest_start"]=np.where(a.eligible,a.RW_scheduled_completion-a.RSP_duration_slots,a.RSP_scheduled_start).astype(int)
    assert np.array_equal(a.RSP_scheduled_start+a.RSP_duration_slots,a.RSP_scheduled_completion)
    assert np.array_equal(a.RW_scheduled_start+a.RW_duration_slots,a.RW_scheduled_completion)
    f=BASE/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B0.json";dec=read(f)["decision"]
    initial={r["job_uid"]:r["initial_AIDC"] for r in dec["common_initial_RUNNING_AIDC_state"]}
    assert set(initial)==set(a.loc[a.state_at_issue.eq("RUNNING"),"job_uid"])
    a["initial_AIDC"]=a.job_uid.map(initial).fillna("")
    files=[dr/name for name in ("V37_R4A_JOB_LEDGER.parquet","V37_R4A_D1_SNAPSHOT.parquet","V37_R4A_RSP_SCHEDULE.parquet","V37_R4A_RW_SCHEDULE.parquet","V37_R4A_DAY_MANIFEST.json","V37_R4A_EXCLUSIONS.parquet")]+[f]
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v28r2.source_cache import day_root
    files.extend([day_root(SOURCE_DATA_REPOSITORY,day)/n for n in ("aemo_forecast.json","gfs_d1_weather.parquet")])
    files.extend([REPO/f"dayahead/cache/v37_may_locked_final/electrical/{day}/data/D1_AC_ANCHOR_{kind}_{day}.npz" for kind in ("SENSITIVITY","CURRENT_SENSITIVITY")])
    files.append(REPO/"dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    hashes={str(p):grid.sha(p) for p in files}
    return a,dec,hashes

def cloned_v39g(out):
    # Reuse the exact V39G objective/cohort expansion/lex algorithm in an
    # isolated function namespace. No module globals or files are mutated.
    ns=dict(v39g.__dict__);ns["OUT"]=out
    ns["write"]=lambda name,data:atomic(out/name.replace("V39G","V39H"),data)
    for name in ("solve_stage","exact_tie","expanded","audit_schedule"):
        fn=getattr(v39g,name);ns[name]=FunctionType(fn.__code__,ns,name,fn.__defaults__)
    return SimpleNamespace(**{n:ns[n] for n in ("solve_stage","exact_tie","expanded","audit_schedule")})

def status(out,phase,**more):
    old=read(out/"V39H_DAY_PROGRESS.json") if (out/"V39H_DAY_PROGRESS.json").exists() else {}
    atomic(out/"V39H_DAY_PROGRESS.json",{**old,"day":out.name,"worker_PID":os.getpid(),"phase":phase,"last_update":now(),**more})

def configure(m,out,name):
    m.Params.Threads=4;m.Params.Seed=SEED;m.Params.MIPGap=0;m.Params.MIPGapAbs=0
    m.Params.FeasibilityTol=1e-8;m.Params.IntFeasTol=1e-9;m.Params.LogFile=str(out/f"{name}.log")
    m.Params.LogToConsole=0

def capacity_relaxation(a,out):
    """Deletion of eligible load is a capacity relaxation, NOT a voltage one.

    If this necessary subsystem is infeasible, the FULL Shadow A feasible set
    is empty. This proof allows no approximation or false successful repair.
    """
    cap,_=_load_capacity(REPO);cs=v39g.cohorts(a.loc[~a.eligible]);m=gp.Model("V39H_FIXED_JOB_NECESSARY_SUBSYSTEM");configure(m,out,"V39H_FIXED_JOB_NECESSARY_SUBSYSTEM")
    variables={};active=[c for c in cs if c["lo"]<120 and c["lo"]+c["d"]>24]
    for k,c in enumerate(active):
        legal=_compatible_sites(cap,c["g"],c["fixed_site"] or None)
        for site in legal:variables[k,site]=m.addVar(vtype=GRB.INTEGER,ub=len(c["members"]),name=f"cohort[{k},{site}]")
        m.addConstr(gp.quicksum(variables[k,s] for s in legal)==len(c["members"]),name=f"fixed_jobs[{k}]")
    for t in range(24,120):
        for s in cap.aidc_ids:
            m.addConstr(gp.quicksum(c["g"]*variables[k,s] for k,c in enumerate(active) if (k,s) in variables and c["lo"]<=t<c["lo"]+c["d"])<=cap.site_capacity[s],name=f"site_capacity[{s},{t}]")
    m.setObjective(0);m.optimize()
    result={"status":"INFEASIBLE" if m.Status==GRB.INFEASIBLE else "OPTIMAL" if m.Status==GRB.OPTIMAL else str(m.Status),"solver_status":m.Status,"runtime_seconds":m.Runtime,
        "proof_scope":"Necessary noneligible-fixed-job capacity subsystem; eligible load deleted, no grid constraints asserted on the deleted-load profile.",
        "eligible_jobs_omitted_as_nonnegative_load":int(a.eligible.sum()),"site_grid_constraint_time_domain":[24,120],"Threads":4,"Seed":SEED,"MIPGap":0,
        "planning_voltage_used_in_prescreen":False,"PENDING_initial_sites_remain_free":True,"RUNNING_initial_sites_frozen":True,
        "monotone_proof":"Adding nonnegative eligible occupancy cannot decrease the fixed jobs' per-site resource requirement. Every legal PENDING site assignment is retained. An infeasible necessary capacity subsystem is irrecoverable by standby temporal decisions."}
    if m.Status==GRB.INFEASIBLE:
        m.computeIIS();m.write(str(out/"V39H_SHADOW_A_IIS.ilp"))
        names=[c.ConstrName for c in m.getConstrs() if c.IISConstr]
        cohort_indices=sorted({int(n.split("[")[1][:-1]) for n in names if n.startswith("fixed_jobs[")})
        atomic(out/"V39H_SHADOW_A_IIS_SUMMARY.json",{**result,"IIS_minimal":bool(m.IISMinimal),"constraints":names,
            "constraint_families":dict(Counter(n.split("[")[0] for n in names)),"fixed_cohorts":{str(k):active[k] for k in cohort_indices},
            "full_shadow_infeasibility_proven":True,"base_RSP_infeasibility_also_proven":True,
            "interpretation":"Standby timing cannot repair a packing contradiction already present with ALL eligible standby removed. Frozen RUNNING and fixed noneligible PENDING placement cause the blocker."})
    elif m.Status!=GRB.OPTIMAL:raise RuntimeError(result)
    m.dispose();atomic(out/"V39H_FIXED_SUBSYSTEM_RESULT.json",result);return result

def candidate_options(c,sites):
    for start in range(c["lo"],c["hi"]+1):
        # Outside the accepted site domain, site has no consumer. The exact
        # lex optimum always selects the smallest legal site for that interval.
        options=sites if start<120 and start+c["d"]>24 else sites[:1]
        for site in options:yield site,start

def build_model(a,out,name):
    cap,_=_load_capacity(REPO);sites=tuple(cap.aidc_ids);cs=v39g.cohorts(a)
    assert [cap.site_capacity[s] for s in sites]==[64,32,64,32,80,64,32,64,32,64,32,64]
    horizon=max(120,int((a.latest_start+a.RSP_duration_slots).max()))
    m=gp.Model(name);configure(m,out,name);vs={};events=defaultdict(list);siteevents=defaultdict(list);objs=[gp.LinExpr(),gp.LinExpr(),gp.LinExpr()]
    for k,c in enumerate(cs):
        legal=_compatible_sites(cap,c["g"],c["fixed_site"] or None);group=[]
        for site,start in candidate_options(c,legal):
            v=m.addVar(vtype=GRB.INTEGER,ub=len(c["members"]),name=f"n[{k},{site},{start}]");vs[k,site,start]=v;group.append(v)
            events[start].append((c["g"],v));events[start+c["d"]].append((-c["g"],v))
            if start<120 and start+c["d"]>24:
                siteevents[max(start,24),site].append((c["g"],v));siteevents[min(start+c["d"],120),site].append((-c["g"],v))
            delta=start-c["lo"]
            for obj,weight in zip(objs,(v39g.occupancy_cost(c["lo"],c["d"],start,c["g"]),int(delta>0),c["g"]*delta)):obj.addTerms(weight,v)
        m.addConstr(gp.quicksum(group)==len(c["members"]),name=f"cohort_all_jobs[{k}]")
    # Exact sparse difference representation of the same interval sums, with
    # O(options+horizon) nonzeros instead of O(options*duration).
    total=m.addVars(horizon,lb=0,ub=624,name="complete_total_GPU")
    for t in range(horizon):
        terms=events[t];delta=gp.LinExpr([w for w,v in terms],[v for w,v in terms])
        m.addConstr(total[t]==(total[t-1] if t else 0)+delta,name=f"complete_aggregate_recurrence[{t}]")
    gpu={}
    for s in sites:
        for t in range(24,120):
            gpu[t,s]=m.addVar(vtype=GRB.INTEGER,lb=0,ub=cap.site_capacity[s],name=f"site_GPU[{s},{t}]")
            terms=siteevents[t,s];delta=gp.LinExpr([w for w,v in terms],[v for w,v in terms])
            m.addConstr(gpu[t,s]==(gpu[t-1,s] if t>24 else 0)+delta,name=f"site_recurrence[{s},{t}]")
    coeff,nodes=grid.load_coefficients(out)
    with np.load(out/"V39G_C1_INTEGER_TABLES.npz") as raw:tables={s:raw[s].copy() for s in sites}
    assert all(np.all(np.diff(v,axis=1)>0) for v in tables.values())
    screen=[]
    for t,c in enumerate(coeff):
        aa,bb,names=grid.inequalities(c);lo=np.array([tables[s][t,0] for s in sites]);hi=np.array([tables[s][t,-1] for s in sites])
        box=np.maximum(aa,0)@hi+np.minimum(aa,0)@lo;keep=box>bb-1e-10
        if keep.any():
            pcc=m.addMVar(12,lb=lo,ub=hi,name=f"PCC[{t}]")
            for i,s in enumerate(sites):m.addGenConstrPWL(gpu[t+24,s],pcc[i].item(),list(range(cap.site_capacity[s]+1)),tables[s][t].tolist(),name=f"C1[{t},{s}]")
            m.addMConstr(aa[keep],pcc,"<",bb[keep],name=np.array(names)[keep].tolist())
        screen.append({"slot":t,"all":len(bb),"kept":int(keep.sum()),"min_redundant_margin":float((bb-box)[~keep].min()) if (~keep).any() else None})
    m.update();atomic(out/f"{name}_ALGEBRA.json",{"allocation_variables":len(vs),"cohorts":len(cs),"reservation_objective_time_domain":[0,horizon],"site_grid_constraint_time_domain":[24,120],"exact_event_recurrence":True,"outside_domain_site_elimination":"smallest compatible site; exact lexical projection", "grid_screening_proof":screen,"RUNNING_migration_variables":0,"site_capacities":[cap.site_capacity[s] for s in sites]})
    return {"model":m,"variables":vs,"cohorts":cs,"objectives":objs,"capacity":cap,"sites":sites,"coefficients":coeff,"nodes":nodes,"tables":tables}

def migration_confirmation(day,a,out):
    path=BASE/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json";f=read(path);dec=f["decision"]
    audit_path=BASE/"V39E_TEMPORAL_FIRST_MIGRATION_AUDIT.json";record=next(r for r in read(audit_path)["days"] if r["operating_day"]==day)
    expected=BASE_COUNTS[day];assert expected is not None
    rows=dec["AIDC_assignments"];selected=[r for r in rows if r.get("migration_selected")]
    assert record["solver_proven_minimum_RUNNING_migrations"]==expected==len(selected)==dec["migration_state"]["WAN_transfer_count"]
    assert dec["status"]=="PASS" and dec["migration_state"]["status"]=="PASS" and dec["planning_feasibility"]["planning_pass"]
    assert not dec["Fresh_used_as_DA_decision_oracle"]
    temporal=pd.DataFrame(dec["temporal_schedule"]);temporal["job_uid"]=temporal.job_id.astype(str)
    saved=temporal.set_index("job_uid").loc[a.job_uid]
    assert np.array_equal(saved.scheduled_start_slot,a.RSP_scheduled_start) and np.array_equal(saved.scheduled_end_slot,a.RSP_scheduled_completion)
    for r in selected:
        assert r["state_at_issue"]=="RUNNING" and r["source_AIDC"]!=r["destination_AIDC"]
        assert r["migration_checkpoint_slot"]<=r["WAN_transfer_complete_slot"]<r["destination_READY_slot"]<=r["restart_complete_slot"]
        assert r["fixed_WAN_path_id"] and r["fixed_WAN_path_links"]
    result={"status":"CONFIRMED_FROM_UNCHANGED_FROZEN_SOLVER_WITNESS","day":day,"solver_proven_minimum_migrations":expected,
        "solver_certificate_row":record,"source_SHA256":{str(path):grid.sha(path),str(audit_path):grid.sha(audit_path)},
        "original_frozen_RSP_starts_ends_exact":True,"migration_state":dec["migration_state"],"planning_feasibility":dec["planning_feasibility"],
        "current_migration_solver_calls":0,"loaded_existing_solution":True,"partially_repaired_schedule_used":False,
        "checkpoint_WAN_READY_restart_order_verified":True,"PENDING_placement_counted_as_migration":False}
    atomic(out/"V39H_EXISTING_MIGRATION_CONFIRMATION.json",result);return result

def daily_metrics(a,b,bundle,decision,success):
    diff=b.start_delay_slots.to_numpy(int);changed=diff>0;deltas=diff[changed]*15
    slack=(a.latest_start-a.RSP_scheduled_start).to_numpy(int)
    frac=diff[changed]/slack[changed] if changed.any() else np.array([])
    horizon=max(120,int((a.latest_start+a.RSP_duration_slots).max()));before=np.zeros(horizon,int);after=np.zeros(horizon,int)
    for r in b.itertuples(index=False):
        before[r.RSP_scheduled_start:r.RSP_scheduled_completion]+=int(r.requested_gpus)
        after[r.scheduled_start_slot:r.scheduled_end_slot]+=int(r.requested_gpus)
    prior={r["job_uid"]:r["destination_AIDC"] for r in decision.get("AIDC_assignments",[]) if r["state_at_issue"]=="PENDING"}
    comparable=b.state_at_issue.eq("PENDING")&b.job_uid.isin(prior)&b.scheduled_start_slot.lt(120)&b.scheduled_end_slot.gt(24)
    placement_changes=int((b.loc[comparable,"AIDC"]!=b.loc[comparable,"job_uid"].map(prior)).sum()) if success else 0
    out_before=int(before[:24].sum()+before[120:].sum());out_after=int(after[:24].sum()+after[120:].sum())
    return {"eligible_standby_jobs":int(a.eligible.sum()),"changed_jobs":int(changed.sum()),"changed_fraction":float(changed.sum()/a.eligible.sum()) if a.eligible.any() else 0,
        "delay_minutes":deltas.tolist(),"slack_consumed_ratios":frac.tolist(),"sum_start_delay_minutes":int(deltas.sum()),"max_added_delay_min":int(deltas.max()) if len(deltas) else 0,
        "GPU_weighted_start_delay_slots":int((b.requested_gpus*b.start_delay_slots).sum()),"symmetric_occupancy_deviation_GPU_slots":int(b.occupancy_deviation_GPU_slots.sum()),
        "symmetric_occupancy_deviation_GPU_h":float(b.occupancy_deviation_GPU_slots.sum()/4),"one_way_relocated_occupancy_GPU_h":float(b.occupancy_deviation_GPU_slots.sum()/8),
        "maximum_simultaneous_load_restored_GPU":int((after-before).max()),"maximum_simultaneous_load_removed_GPU":int((before-after).max()),
        "PENDING_initial_placement_changes":placement_changes,"PENDING_initial_placement_comparable_jobs":int(comparable.sum()),
        "PENDING_placement_reference":"Existing frozen RSP initial-placement witness (migration-allowed route when applicable); unknown/out-of-domain placements excluded.",
        "reservation_objective_time_domain":[0,horizon],"site_grid_constraint_time_domain":[24,120],
        "outside_site_grid_domain_GPU_h_before":out_before/4,"outside_site_grid_domain_GPU_h_after":out_after/4,
        "outside_site_grid_domain_GPU_h_change":(out_after-out_before)/4,"scope_warning":bool(out_after),
        "scope_warning_text":"Complete reservation accounting extends outside certified operating-day spatial domain; no off-day site/grid feasibility claim." if out_after else None,
        "RW_completion_noninferiority_violations":int((b.start_delay_slots.gt(0)&b.scheduled_end_slot.gt(b.RW_scheduled_completion)).sum()),
        "eligible_RW_completion_bound_violations":int((b.eligible&b.scheduled_end_slot.gt(b.RW_scheduled_completion)).sum()),
        "base_RSP_existing_completion_later_than_RW_jobs":int(a.RSP_scheduled_completion.gt(a.RW_scheduled_completion).sum()),
        "after_all_jobs_completion_later_than_RW_jobs":int(b.scheduled_end_slot.gt(b.RW_scheduled_completion).sum()),
        "safe_GPU_h_before":float((a.requested_gpus*a.RSP_duration_slots).sum()/4),"safe_GPU_h_after":float((b.requested_gpus*b.duration_slots).sum()/4),
        "safe_seconds_GPU_h_before":float((a.requested_gpus*a.RSP_duration_seconds).sum()/3600),"safe_seconds_GPU_h_after":float((b.requested_gpus*b.RSP_duration_seconds).sum()/3600)}

def save_day(a,b,out,result,decision,bundle=None):
    success=result["temporal_repair_sufficient"]
    metrics=daily_metrics(a,b,bundle,decision,success);result.update(metrics)
    b["admissible_delay_window_slots"]=b.latest_start-b.RSP_scheduled_start
    b["slack_consumed_ratio"]=np.where(b.admissible_delay_window_slots.gt(0),b.start_delay_slots/b.admissible_delay_window_slots,0)
    b["operating_day"]=out.name;b["schedule_class"]="TEMPORAL_SHADOW_OPTIMAL" if success else "ORIGINAL_RSP_RETAINED_NO_FEASIBLE_TEMPORAL_SHADOW"
    issue=pd.Timestamp(out.name,tz=timezone(timedelta(hours=10)))-pd.Timedelta(hours=6)
    b["scheduled_start_AEST"]=[(issue+pd.Timedelta(minutes=15*int(s))).isoformat() for s in b.scheduled_start_slot]
    b.to_parquet(out/"V39H_SHADOW_SCHEDULE.parquet",index=False)
    b.loc[b.start_delay_slots.ne(0)].to_csv(out/"V39H_CHANGED_JOBS.csv",index=False,encoding="utf-8-sig")
    work={k:v for k,v in metrics.items() if k.startswith("safe_")}
    work.update(job_set_equal=set(a.job_uid)==set(b.job_uid),GPU_requests_equal=np.array_equal(a.requested_gpus,b.requested_gpus),safe_duration_slots_equal=np.array_equal(a.RSP_duration_slots,b.duration_slots),safe_seconds_equal=np.array_equal(a.RSP_duration_seconds,b.RSP_duration_seconds),modeled_not_realized_computation=True)
    assert all(work[k] for k in ("job_set_equal","GPU_requests_equal","safe_duration_slots_equal","safe_seconds_equal"))
    assert metrics["RW_completion_noninferiority_violations"]==0
    atomic(out/"V39H_WORK_PRESERVATION_AUDIT.json",work)
    if success:
        g=result["audit"]["grid"];margin={**g,"upper_voltage_headroom_pu":1.05-g["Vmax"],"lower_voltage_headroom_pu":g["Vmin"]-.95,
            "line_current_margin":1-g["max_line_loading"],"transformer_current_margin":1-g["max_transformer_current_loading"],"transformer_apparent_power_margin":1-g["max_transformer_kva_loading"],
            "transformer_polygon_margin":1-g["max_transformer_polygon_loading"],"day":out.name,"status":"PASS"}
        margin.pop("slot106_Vmax",None);result["Vmax"]=g["Vmax"];result["Vmin"]=g["Vmin"];result["upper_voltage_headroom_pu"]=margin["upper_voltage_headroom_pu"]
    else:margin={"status":"NOT_APPLICABLE_NO_FEASIBLE_TEMPORAL_SHADOW","day":out.name,"existing_migration_grid_status":"PASS"}
    atomic(out/"V39H_GRID_MARGIN_AUDIT.json",margin)
    result["completed_at"]=now();atomic(out/"V39H_SHADOW_A_RESULT.json",result)
    status(out,"COMPLETE",base_RSP_status=result["base_RSP_status"],shadow_status=result["shadow_status"],changed_jobs=result["changed_jobs"],Vmax=result.get("Vmax"),temporal_repair_sufficient=success,existing_migration_count=BASE_COUNTS[out.name],post_candidate_migration_count=result["post_candidate_migration_count"])

def retained_schedule(a,decision):
    b=a.copy();prior={r["job_uid"]:r["destination_AIDC"] for r in decision.get("AIDC_assignments",[])}
    b["AIDC"]=b.job_uid.map(prior).fillna("OUTSIDE_OPERATING_DAY_UNASSIGNED")
    b["scheduled_start_slot"]=b.RSP_scheduled_start;b["scheduled_end_slot"]=b.RSP_scheduled_completion;b["duration_slots"]=b.RSP_duration_slots
    b["start_delay_slots"]=0;b["start_delay_minutes"]=0;b["occupancy_deviation_GPU_slots"]=0
    return b

def worker(day):
    assert day in DAYS
    out=ROOT/"days"/day;out.mkdir(parents=True,exist_ok=True);(out/"temp").mkdir(exist_ok=True)
    os.environ["TEMP"]=str(out/"temp");os.environ["TMP"]=str(out/"temp")
    status(out,"INPUT_VERIFICATION",start_time=now())
    a,_,hashes=inputs(day);fingerprint=digest({"model_SHA":model_hash(),"day":day,"input_SHA":hashes})
    existing=out/"V39H_SHADOW_A_RESULT.json"
    if existing.exists() and read(existing).get("input_model_SHA")==fingerprint:
        status(out,"COMPLETE",reused_matching_SHA=True);return
    atomic(out/"V39H_INPUT_AUTHORITY.json",{"day":day,"input_model_SHA":fingerprint,"model_SHA":model_hash(),"input_SHA":hashes,"eligible_job_uids":a.loc[a.eligible,"job_uid"].tolist(),"universal_eligibility_rule_reused":True})
    decision=read(BASE/f"V39E_DAYAHEAD_DECISION_FREEZE_{day}_B1.json")["decision"]
    common={"day":day,"input_model_SHA":fingerprint,"existing_migration_count":BASE_COUNTS[day],"RUNNING_migration_calls_in_temporal_shadow":0,"Threads":4,"Seed":SEED,"MIPGap":0,"sidecar":False}
    status(out,"BASE_RSP_NECESSARY_CAPACITY_CHECK")
    necessary=capacity_relaxation(a,out)
    if necessary["status"]=="INFEASIBLE":
        atomic(out/"V39H_BASE_RSP_GRID_CHECK.json",{"status":"INFEASIBLE","proof":"Full base RSP includes the solver-proven infeasible fixed-job capacity subsystem.","planning_constraints_cannot_rescue_capacity_infeasibility":True})
        confirm=migration_confirmation(day,a,out)
        save_day(a,retained_schedule(a,decision),out,{**common,"base_RSP_status":"INFEASIBLE","shadow_status":"INFEASIBLE","classification":"TEMPORAL_REPAIR_INSUFFICIENT","temporal_repair_sufficient":False,"infeasibility_proof":"NECESSARY_FIXED_JOB_CAPACITY_IIS","post_candidate_migration_count":confirm["solver_proven_minimum_migrations"]},decision)
        return
    status(out,"FROZEN_GRID_PREPARATION")
    gp_path=out/"V39H_GRID_INPUT_PROVENANCE.json"
    if not gp_path.exists():atomic(gp_path,grid.prepare_grid(REPO,out,day))
    reuse=cloned_v39g(out)
    base=a.copy();base["eligible"]=False;base["latest_start"]=base.RSP_scheduled_start
    status(out,"BASE_RSP_GRID_CHECK")
    bundle=build_model(base,out,"V39H_BASE_RSP");m=bundle["model"];stage=reuse.solve_stage(m,0,"BASE_RSP_GRID_CHECK")
    atomic(out/"V39H_BASE_RSP_GRID_CHECK.json",stage)
    if m.Status==GRB.OPTIMAL:
        b=reuse.expanded(base,bundle);audit,_,_=reuse.audit_schedule(b,bundle)
        atomic(out/"V39H_BASE_RSP_UNEXPECTED_PASS.json",{"stage":stage,"audit":audit});m.dispose()
        raise RuntimeError("BASE_RSP_UNEXPECTED_PASS_REQUIRES_DIAGNOSIS")
    assert m.Status==GRB.INFEASIBLE; m.dispose()
    status(out,"SHADOW_FEASIBILITY",base_RSP_status="INFEASIBLE")
    bundle=build_model(a,out,"V39H_SHADOW_A");m=bundle["model"];stages=[reuse.solve_stage(m,0,"feasibility_first")]
    if m.Status==GRB.INFEASIBLE:
        status(out,"SHADOW_IIS");m.computeIIS();m.write(str(out/"V39H_SHADOW_A_IIS.ilp"))
        names=[c.ConstrName for c in m.getConstrs() if c.IISConstr]
        atomic(out/"V39H_SHADOW_A_IIS_SUMMARY.json",{"IIS_minimal":bool(m.IISMinimal),"constraints":names,"constraint_families":dict(Counter(n.split("[")[0] for n in names)),"full_shadow_infeasibility_proven":True})
        m.dispose();confirm=migration_confirmation(day,a,out)
        save_day(a,retained_schedule(a,decision),out,{**common,"base_RSP_status":"INFEASIBLE","shadow_status":"INFEASIBLE","classification":"TEMPORAL_REPAIR_INSUFFICIENT","temporal_repair_sufficient":False,"stages":stages,"post_candidate_migration_count":confirm["solver_proven_minimum_migrations"]},decision);return
    assert m.Status==GRB.OPTIMAL
    for i,(obj,label) in enumerate(zip(bundle["objectives"],("complete_occupancy_deviation","changed_jobs","GPU_start_delay"))):
        status(out,f"SHADOW_OBJECTIVE_{i+1}")
        stage=reuse.solve_stage(m,obj,label);stages.append(stage);assert stage["optimal"]
        optimum=round(m.ObjVal);assert abs(m.ObjVal-optimum)<1e-5
        b=reuse.expanded(a,bundle);b.to_parquet(out/f"V39H_STAGE_{i+1}_SCHEDULE.parquet",index=False)
        atomic(out/"V39H_OBJECTIVE_CERTIFICATES.json",{"stages":stages})
        m.addConstr(obj==optimum,name=f"exact_lex_fix_{i}");m.update()
    status(out,"EXACT_LEX_TIE");selected=reuse.exact_tie(bundle);b=reuse.expanded(a,bundle,selected)
    status(out,"INDEPENDENT_VERIFICATION");audit,occ,pcc=reuse.audit_schedule(b,bundle)
    if not audit["all_hard_constraints_pass"]:
        atomic(out/"V39H_VERIFIER_MISMATCH.json",audit);raise RuntimeError("TEMPORAL_REPAIR_IMPLEMENTATION_OR_VERIFIER_MISMATCH")
    np.savez_compressed(out/"V39H_WITNESS.npz",GPU_complete=occ,PCC_target=pcc)
    save_day(a,b,out,{**common,"base_RSP_status":"INFEASIBLE","shadow_status":"OPTIMAL","classification":"TEMPORAL_REPAIR_SUFFICIENT","temporal_repair_sufficient":True,"stages":stages,"audit":audit,"post_candidate_migration_count":0},decision,bundle)
    m.dispose()

def orchestrate():
    initialize();running={};pending=list(DAYS);completed=[];failed={};start=time.time()
    while pending or running:
        while pending and len(running)<MAX_PARALLEL_DAY_WORKERS:
            day=pending.pop(0);out=ROOT/"days"/day;out.mkdir(parents=True,exist_ok=True)
            handle=(out/"V39H_WORKER_STDOUT.log").open("ab")
            env=dict(os.environ,OPENBLAS_NUM_THREADS="4",OMP_NUM_THREADS="4",MKL_NUM_THREADS="4")
            proc=subprocess.Popen([sys.executable,"-u",str(Path(__file__).resolve()),"--day",day],cwd=out,stdout=handle,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            running[day]=(proc,handle)
        for day,(proc,handle) in list(running.items()):
            code=proc.poll()
            if code is None:continue
            handle.close();running.pop(day)
            if code==0:completed.append(day)
            else:failed[day]=code
        perday={}
        for day in DAYS:
            path=ROOT/"days"/day/"V39H_DAY_PROGRESS.json"
            if path.exists():perday[day]=read(path)
        results=[read(ROOT/"days"/d/"V39H_SHADOW_A_RESULT.json") for d in completed]
        atomic(ROOT/"progress/V39H_PROGRESS.json",{"phase":"RUNNING" if running or pending else "PRIMARY_COMPLETE" if not failed else "NEEDS_DIAGNOSIS",
            "start_time":datetime.fromtimestamp(start,timezone.utc).isoformat(),"last_update":now(),"elapsed_seconds":time.time()-start,"completed_days":sorted(completed),"running_days":sorted(running),"pending_days":pending,"failed_days":failed,
            "worker_PIDs":{d:p.pid for d,(p,h) in running.items()},"per_day":perday,"baseline_migrations":105,
            "current_postrepair_migrations_completed_days_only":sum(r["post_candidate_migration_count"] for r in results),"temporal_repair_only_days":sum(r["temporal_repair_sufficient"] for r in results),
            "remaining_migration_days_completed_only":sum(r["post_candidate_migration_count"]>0 for r in results),"resumable":True,"max_parallel_day_workers":4,"Threads_per_model":4})
        if running:time.sleep(2)
    if failed:raise RuntimeError(f"DAY_FAILURES:{failed}")
    print("13 primary days completed",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--init",action="store_true");p.add_argument("--day",choices=DAYS);args=p.parse_args()
    try:
        with threadpool_limits(limits=4):
            initialize() if args.init else worker(args.day) if args.day else orchestrate()
    except Exception:
        if args.day:status(ROOT/"days"/args.day,"FAILED",error=traceback.format_exc())
        raise

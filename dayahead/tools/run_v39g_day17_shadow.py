"""V39G counterfactual only. Never imports a campaign/preflight execution path."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB

REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path: sys.path.insert(0,str(REPO))
from dayahead.tools.v39g_shadow_grid import sha,prepare_grid,load_coefficients,inequalities,evaluate
from dayahead.v39d.evaluate import _load_capacity
from dayahead.v39e.full_spatial import _compatible_sites
from dayahead.v37.aidc_materializer import FROZEN_HPCODA_HEAD,FROZEN_MODEL_CONFIG,Q_SELECTED_SECONDS

DAY="2025-05-17"
OUT=REPO/"dayahead/artifacts/v39g_day17_standby_temporal_repair_shadow"
DAYROOT=REPO/f"dayahead/artifacts/v37_r4a_per_day_aidc/days/{DAY}"
FREEZE=REPO/f"dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_{DAY}_B0.json"
LABELS=["DIAGNOSTIC_ONLY","NOT_PRODUCTION_AUTHORITY","NOT_SCIENCE_REFREEZE"]

def clean(v):
    if isinstance(v,dict): return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [clean(x) for x in v]
    if isinstance(v,np.generic): return clean(v.item())
    if isinstance(v,float) and not np.isfinite(v): return None
    if isinstance(v,(datetime,pd.Timestamp)): return v.isoformat()
    return v

def write(name,data):
    (OUT/name).write_text(json.dumps(clean({"labels":LABELS,**data}),indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")

def read(name): return json.loads((OUT/name).read_text(encoding="utf-8"))
def git(*args): return subprocess.check_output(["git",*args],cwd=REPO,text=True,encoding="utf-8").strip()
def source_hashes():
    return {n:sha(REPO/n) for n in git("ls-files","-z").split("\0") if n.endswith((".py",".ps1",".toml",".yaml",".yml")) and (REPO/n).is_file()}

def occupancy_cost(start0,duration,start,gpu):
    assert start>=start0 and duration>0
    return 2*gpu*min(start-start0,duration)

def eligible_mask(a,tiers=("standby",)):
    return (a.D1_visible & a.state_at_issue.eq("PENDING") & a.qos.isin(tiers)
            & a.duration_authority.eq("SAFE_CAUSAL_RUNTIME_PENDING")
            & a.RSP_duration_slots.gt(0) & a.RW_scheduled_completion.notna()
            & a.RSP_scheduled_start.le(a.RW_scheduled_completion-a.RSP_duration_slots))

def inputs():
    a=pd.read_parquet(DAYROOT/"V37_R4A_JOB_LEDGER.parquet")
    a["job_uid"]=a.job_id.astype(str)
    a=a.sort_values("job_uid").reset_index(drop=True)
    snapshot=pd.read_parquet(DAYROOT/"V37_R4A_D1_SNAPSHOT.parquet")
    # Source id is the unique array-task identity. Source job_id is shared
    # by array tasks and must never collapse 2,281 reservations to 528 jobs.
    snapshot["job_uid"]=snapshot.id.astype(str)
    assert snapshot.job_uid.is_unique and a.job_uid.is_unique
    assert set(snapshot.job_uid)==set(a.job_uid)
    ss=snapshot.set_index("job_uid").loc[a.job_uid]
    visible=pd.to_datetime(ss.submit_time,utc=True)<=pd.Timestamp("2025-05-16T08:00:00Z")
    assert visible.all() and set(ss.issue_time_fixed_AEST)=={"2025-05-16T18:00:00+10:00"}
    assert np.array_equal(ss.qos.astype(str),a.qos.astype(str))
    assert np.array_equal(ss.state_at_issue,a.state_at_issue)
    a["D1_visible"]=visible.to_numpy()
    assert np.array_equal(a.RSP_scheduled_completion,a.RSP_scheduled_start+a.RSP_duration_slots)
    assert np.array_equal(a.RW_scheduled_completion,a.RW_scheduled_start+a.RW_duration_slots)
    assert np.array_equal(a.requested_gpus,a.requested_gpus.astype(int))
    decision=json.loads(FREEZE.read_text(encoding="utf-8"))["decision"]
    initial={r["job_uid"]:r["initial_AIDC"] for r in decision["common_initial_RUNNING_AIDC_state"]}
    assert set(initial)==set(a.loc[a.state_at_issue.eq("RUNNING"),"job_uid"])
    a["initial_AIDC"]=a.job_uid.map(initial).fillna("")
    a["eligible"]=eligible_mask(a)
    a["latest_start"]=np.where(a.eligible,a.RW_scheduled_completion-a.RSP_duration_slots,a.RSP_scheduled_start).astype(int)
    return a,decision

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if not (OUT/"V39G_START_STATE.json").exists():
        write("V39G_START_STATE.json",{"starting_HEAD":git("rev-parse","HEAD"),
            "starting_branch":"codex/v39f-day17-rsp-temporal-grid-diagnostic",
            "starting_branch_evidence":"Read via git branch --show-current before diagnostic branch creation in this task.",
            "diagnostic_branch":git("branch","--show-current"),"status_at_diagnostic_start":git("status","--porcelain"),
            "production_source_SHA256":source_hashes(),"captured_at":datetime.now(timezone.utc)})
    a,_=inputs()
    write("V39G_MAY17_ELIGIBILITY_AUDIT.json",{"jobs":len(a),"eligible_standby":int(a.eligible.sum()),
        "rule":"ALL D1_VISIBLE PENDING authoritative standby, frozen safe duration and RW completion, s_RSP <= C_RW-d_safe",
        "slot106_membership_used_for_eligibility":False,"normal_temporal_variables":0,
        "positive_slack":int((a.eligible & a.latest_start.gt(a.RSP_scheduled_start)).sum()),
        "zero_slack":int((a.eligible & a.latest_start.eq(a.RSP_scheduled_start)).sum()),
        "noneligible_jobs":int((~a.eligible).sum()),"all_D1_visible":bool(a.D1_visible.all()),
        "eligible_job_uids":a.loc[a.eligible,"job_uid"].tolist(),
        "complete_reservation_horizon_right_exclusive":int((a.latest_start+a.RSP_duration_slots).max())})
    a.to_parquet(OUT/"V39G_MODEL_JOB_INPUTS.parquet",index=False)
    if not (OUT/"V39G_GRID_INPUT_PROVENANCE.json").exists():
        print("Preparing frozen grid",flush=True)
        prov=prepare_grid(REPO,OUT,DAY)
        prov["source_SHA256"].update({str(p):sha(p) for p in [FREEZE,DAYROOT/"V37_R4A_JOB_LEDGER.parquet",DAYROOT/"V37_R4A_D1_SNAPSHOT.parquet",DAYROOT/"V37_R4A_MANIFEST.json"] if p.exists()})
        write("V39G_GRID_INPUT_PROVENANCE.json",prov)
    print("Preparation complete",flush=True)

def cohorts(a):
    result=[]; groups={}
    for r in a.itertuples(index=False):
        key=(r.state_at_issue,r.initial_AIDC,int(r.requested_gpus),int(r.RSP_duration_slots),int(r.RSP_scheduled_start),int(r.latest_start),bool(r.eligible))
        if key not in groups:
            groups[key]=len(result)
            result.append({"state":key[0],"fixed_site":key[1],"g":key[2],"d":key[3],"lo":key[4],"hi":key[5],"eligible":key[6],"members":[]})
        result[groups[key]]["members"].append(r.job_uid)
    return result

def build_model(a,name):
    cap,_=_load_capacity(REPO); sites=tuple(cap.aidc_ids)
    assert [cap.site_capacity[s] for s in sites]==[64,32,64,32,80,64,32,64,32,64,32,64]
    cs=cohorts(a); horizon=int((a.latest_start+a.RSP_duration_slots).max())
    m=gp.Model(name)
    m.Params.Threads=4;m.Params.Seed=20260905;m.Params.MIPGap=0;m.Params.MIPGapAbs=0
    m.Params.FeasibilityTol=1e-8;m.Params.IntFeasTol=1e-9
    m.Params.LogFile=str(OUT/f"{name}.log")
    load=[[gp.LinExpr() for _ in sites] for _ in range(horizon)]
    variables={};primary=gp.LinExpr();secondary=gp.LinExpr();third=gp.LinExpr()
    for k,c in enumerate(cs):
        legal=_compatible_sites(cap,c["g"],c["fixed_site"] or None)
        assert legal
        vs=[]
        for site in legal:
            si=sites.index(site)
            for start in range(c["lo"],c["hi"]+1):
                v=m.addVar(vtype=GRB.INTEGER,lb=0,ub=len(c["members"]),name=f"n[{k},{site},{start}]")
                variables[k,site,start]=v;vs.append(v)
                for t in range(start,start+c["d"]): load[t][si]+=c["g"]*v
                delta=start-c["lo"]
                primary+=occupancy_cost(c["lo"],c["d"],start,c["g"])*v
                secondary+=int(delta>0)*v;third+=c["g"]*delta*v
        m.addConstr(gp.quicksum(vs)==len(c["members"]),name=f"cohort_all_jobs[{k}]")
    for t in range(horizon):
        m.addConstr(gp.quicksum(load[t])<=624,name=f"full_reservation_aggregate_capacity[{t}]")
    # Reuse the accepted spatial domain exactly: 96 operating-day slots.
    # Complete reservation intervals apply to temporal capacity and objective,
    # not invented previous-day site constraints on the synthetic initial state.
    for t in range(24,120):
        for si,site in enumerate(sites): m.addConstr(load[t][si]<=cap.site_capacity[site],name=f"site_capacity[{site},{t}]")
    coefficients,nodes=load_coefficients(OUT)
    with np.load(OUT/"V39G_C1_INTEGER_TABLES.npz") as raw: tables={s:raw[s].copy() for s in sites}
    assert all(np.all(np.diff(table,axis=1)>0) for table in tables.values())
    pcc=m.addMVar((96,12),lb=np.stack([tables[s][:,0] for s in sites],axis=1),ub=np.stack([tables[s][:,-1] for s in sites],axis=1),name="PCC")
    screen=[]
    for t in range(96):
        aa,bb,nn=inequalities(coefficients[t])
        lower=np.array([tables[s][t,0] for s in sites]);upper=np.array([tables[s][t,-1] for s in sites])
        maxbox=np.maximum(aa,0)@upper+np.minimum(aa,0)@lower
        keep=maxbox>bb-1e-10
        # Exact dominance screening over a SUPERSET of every possible PCC.
        # Removed rows are independently evaluated in the schedule audit.
        if keep.any():
            for si,site in enumerate(sites):
                active=m.addVar(vtype=GRB.INTEGER,lb=0,ub=cap.site_capacity[site],name=f"GPU[{t},{site}]")
                m.addConstr(active==load[t+24][si])
                m.addGenConstrPWL(active,pcc[t,si].item(),list(range(cap.site_capacity[site]+1)),tables[site][t].tolist(),name=f"C1_exact_integer[{t},{site}]")
            m.addMConstr(aa[keep],pcc[t],"<",bb[keep],name=np.asarray(nn)[keep].tolist())
        # If EVERY grid row is provably redundant, PCC/C1 has no objective or
        # remaining constraint consumer. Eliminate that equality existentially:
        # every legal integer load has its unique exact C1 PCC witness, which
        # the independent audit reconstructs. No feasible allocation is added.
        screen.append({"slot":t,"all":len(bb),"kept":int(keep.sum()),"provably_redundant":int((~keep).sum()),
                       "minimum_redundant_margin":float((bb-maxbox)[~keep].min()) if (~keep).any() else None})
    m.update()
    write(f"{name}_MODEL_ALGEBRA_AUDIT.json",{"cohorts":len(cs),"allocation_integer_variables":len(variables),"full_reservation_horizon":[0,horizon],
        "exact_cohort_reduction":"Identical duration, GPU, window, state and fixed site; count integral; each expanded job gets one contiguous interval at one compatible site.",
        "site_capacity_sole_additive_authority":True,"rack_capacity_addition":False,"C1_exact_integer_PWL":True,
        "site_and_grid_authority_issue_slots":[24,120],"aggregate_capacity_and_objective_issue_slots":[0,horizon],
        "grid_box_redundancy_proof":screen,"MESS_variables":0,"migration_variables":0,
        "Threads":m.Params.Threads,"Seed":m.Params.Seed,"MIPGap":m.Params.MIPGap,"MIPGapAbs":m.Params.MIPGapAbs})
    return {"model":m,"cohorts":cs,"variables":variables,"load":load,"objectives":[primary,secondary,third],"sites":sites,"capacity":cap,"coefficients":coefficients,"nodes":nodes,"tables":tables}

def solve_stage(m,obj,name,sense=GRB.MINIMIZE,quiet=False):
    m.setObjective(obj,sense)
    if quiet:m.Params.OutputFlag=0
    m.optimize()
    r={"stage":name,"status":m.Status,"runtime_seconds":m.Runtime,"solutions":m.SolCount,
       "optimal":m.Status==GRB.OPTIMAL,"Threads":m.Params.Threads,"MIPGap_setting":m.Params.MIPGap}
    if m.SolCount:r.update(objective=m.ObjVal,bound=m.ObjBound,gap=m.MIPGap)
    if not quiet:print(json.dumps(r),flush=True)
    return r

def exact_tie(bundle):
    """True job_uid/site/slot lex order, using exact small-integer solves.

    Jobs interchangeable within a cohort. For the next contiguous UID block,
    find its smallest feasible (site,start), then maximize the number of this
    block using that option. Fix only that prefix; repeat. This is equivalent
    to individual-job lex optimization, without positional big weights.
    """
    m=bundle["model"];vs=bundle["variables"];cs=bundle["cohorts"]
    which={uid:k for k,c in enumerate(cs) for uid in c["members"]}
    ordered=sorted(which);blocks=[]
    for uid in ordered:
        k=which[uid]
        if blocks and blocks[-1][0]==k:blocks[-1][1].append(uid)
        else:blocks.append((k,[uid]))
    assigned=defaultdict(int);schedule={};cert=[]
    for bi,(k,uids) in enumerate(blocks):
        choices=sorted([key for key in vs if key[0]==k],key=lambda x:(x[1],x[2]))
        todo=list(uids)
        while todo:
            options=[key for key in choices if vs[key].UB-assigned[key]>=1-1e-7]
            if len(options)==1:
                chosen=options[0];n=len(todo)
            else:
                # Pick ONE next UID with exact bounded rank; no giant weights.
                z=m.addVars(len(options),vtype=GRB.BINARY,name=f"lex_pick_{bi}")
                cc=[m.addConstr(z.sum()==1)]
                cc.extend(m.addConstr(vs[key]>=assigned[key]+z[i]) for i,key in enumerate(options))
                r=solve_stage(m,gp.quicksum(i*z[i] for i in range(len(options))),f"lex_first_{bi}",quiet=True)
                if not r["optimal"]:raise RuntimeError(f"LEX_PICK_NOT_OPTIMAL:{r}")
                pick=round(m.ObjVal);chosen=options[pick];cert.append(r)
                m.remove(cc);m.remove(list(z.values()));m.update()
                for key in options[:pick]:vs[key].UB=assigned[key]
                vs[chosen].LB=assigned[chosen]+1
                if len(todo)==1:n=1
                else:
                    q=m.addVar(vtype=GRB.INTEGER,lb=1,ub=len(todo),name=f"lex_count_{bi}")
                    con=m.addConstr(q<=vs[chosen]-assigned[chosen])
                    r=solve_stage(m,q,f"lex_count_{bi}",GRB.MAXIMIZE,quiet=True)
                    if not r["optimal"]:raise RuntimeError(f"LEX_COUNT_NOT_OPTIMAL:{r}")
                    n=round(m.ObjVal);cert.append(r)
                    m.remove(con);m.remove(q);m.update()
                    if n<len(todo):vs[chosen].UB=assigned[chosen]+n
            for uid in todo[:n]:schedule[uid]=(chosen[1],chosen[2])
            todo=todo[n:];assigned[chosen]+=n;vs[chosen].LB=assigned[chosen];m.update()
        if bi%10==0:
            print(f"Exact lex tie block {bi+1}/{len(blocks)}, fixed {len(schedule)} jobs",flush=True)
            write("V39G_LEX_PROGRESS.json",{"blocks_done":bi+1,"blocks_total":len(blocks),"jobs_fixed":len(schedule),"certified_stages":len(cert)})
    for key,v in vs.items():v.LB=assigned[key];v.UB=assigned[key]
    r=solve_stage(m,0,"lex_final_fixed_witness",quiet=True);cert.append(r)
    assert r["optimal"] and len(schedule)==len(which)
    write("V39G_EXACT_LEX_CERTIFICATES.json",{"order":"job_uid UTF-8 ascending; site ascending; issue-relative slot ascending","blocks":len(blocks),"stages":cert,"all_stages_optimal":True,"giant_positional_weights":False})
    write("V39G_LEX_PROGRESS.json",{"status":"COMPLETE","blocks_done":len(blocks),"blocks_total":len(blocks),"jobs_fixed":len(schedule),"certified_stages":len(cert)})
    return schedule

def expanded(a,bundle,selected=None):
    if selected is None:
        selected={}
        for k,c in enumerate(bundle["cohorts"]):
            options=[]
            for key,v in sorted(bundle["variables"].items()):
                if key[0]==k: options.extend([(key[1],key[2])]*round(v.X))
            assert len(options)==len(c["members"])
            selected.update(zip(sorted(c["members"]),options))
    b=a.copy()
    b["AIDC"]=[selected[u][0] for u in b.job_uid]
    b["scheduled_start_slot"]=[selected[u][1] for u in b.job_uid]
    b["duration_slots"]=b.RSP_duration_slots.astype(int)
    b["scheduled_end_slot"]=b.scheduled_start_slot+b.duration_slots
    b["start_delay_slots"]=b.scheduled_start_slot-b.RSP_scheduled_start
    b["start_delay_minutes"]=b.start_delay_slots*15
    b["occupancy_deviation_GPU_slots"]=[occupancy_cost(r.RSP_scheduled_start,r.duration_slots,r.scheduled_start_slot,int(r.requested_gpus)) for r in b.itertuples(index=False)]
    b["logical_Rack_compatibility_label"]=[sorted(x.rack_pool_id for x in bundle["capacity"].eligible_racks(r.AIDC,int(r.requested_gpus)))[0] for r in b.itertuples(index=False)]
    return b

def audit_schedule(b,bundle):
    sites=bundle["sites"];cap=bundle["capacity"]
    horizon=int((b.latest_start+b.duration_slots).max());occ=np.zeros((horizon,12),dtype=int)
    for r in b.itertuples(index=False):occ[r.scheduled_start_slot:r.scheduled_end_slot,sites.index(r.AIDC)]+=int(r.requested_gpus)
    pcc=np.asarray([[bundle["tables"][s][t,occ[t+24,i]] for i,s in enumerate(sites)] for t in range(96)])
    grid=evaluate(bundle["coefficients"],bundle["nodes"],pcc)
    violations={"site_capacity_violations":int((occ[24:120]>np.array([cap.site_capacity[s] for s in sites])).sum()),
        "aggregate_capacity_violations":int((occ.sum(axis=1)>624).sum()),"gang_splits":0 if b.job_uid.is_unique else 1,
        "rack_compatibility_failures":sum(not cap.eligible_racks(r.AIDC,int(r.requested_gpus)) for r in b.itertuples(index=False)),
        "noneligible_time_changes":int((~b.eligible & (b.start_delay_slots.ne(0)|b.duration_slots.ne(b.RSP_duration_slots))).sum()),
        "negative_delays":int(b.start_delay_slots.lt(0).sum()),
        "RW_completion_noninferiority_violations":int((b.eligible & b.scheduled_end_slot.gt(b.RW_scheduled_completion)).sum()),
        "safe_duration_changes":int(b.duration_slots.ne(b.RSP_duration_slots).sum()),
        "RUNNING_site_changes":int((b.state_at_issue.eq("RUNNING") & b.AIDC.ne(b.initial_AIDC)).sum())}
    assert not any(violations.values()),violations
    return {**violations,"grid":grid,"all_hard_constraints_pass":grid["pass"],"RUNNING_migration_calls":0,"WAN_transfer_count":0,"MESS_moves":0},occ,pcc

def run():
    prepare();a,_=inputs();bundle=build_model(a,"V39G_SHADOW_A_ACCEPTED_DOMAIN");m=bundle["model"]
    stages=[solve_stage(m,0,"feasibility_first")]
    write("V39G_SOLVE_PROGRESS.json",{"stages":stages})
    if m.Status==GRB.INFEASIBLE:
        m.computeIIS();m.write(str(OUT/"V39G_MAY17_SHADOW_A_IIS.ilp"))
        write("V39G_MAY17_SHADOW_A_RESULT.json",{"status":"INFEASIBLE","stages":stages})
        raise RuntimeError("SHADOW_A_PROVEN_INFEASIBLE: diagnose IIS before considering B")
    assert m.Status==GRB.OPTIMAL
    for i,(obj,label) in enumerate(zip(bundle["objectives"],["complete_occupancy_deviation","changed_jobs","GPU_start_delay"])):
        stage=solve_stage(m,obj,label);stages.append(stage)
        assert stage["optimal"],stage
        optimum=round(m.ObjVal);assert abs(m.ObjVal-optimum)<1e-5
        b=expanded(a,bundle);b.to_parquet(OUT/f"V39G_STAGE_{i+1}_SCHEDULE.parquet",index=False)
        write("V39G_SOLVE_PROGRESS.json",{"stages":stages})
        m.write(str(OUT/f"V39G_STAGE_{i+1}.sol"))
        m.addConstr(obj==optimum,name=f"exact_lex_fix_{i}");m.update()
    # Plain MPS is portable on Windows; compressed output may require a
    # compression executable not present on the research runtime.
    m.write(str(OUT/"V39G_A_THREE_OBJECTIVES_FIXED.mps"))
    selected=exact_tie(bundle);b=expanded(a,bundle,selected)
    result,occ,pcc=audit_schedule(b,bundle);assert result["all_hard_constraints_pass"]
    changed=b.loc[b.start_delay_slots.ne(0)].copy();delay=changed.start_delay_minutes.to_numpy()
    result.update(status="OPTIMAL",eligible_standby_jobs=int(b.eligible.sum()),changed_standby_jobs=len(changed),
        unchanged_standby_jobs=int(b.eligible.sum())-len(changed),
        total_shifted_GPU_slots=int(b.occupancy_deviation_GPU_slots.sum()),
        total_shifted_GPU_hours=float(b.occupancy_deviation_GPU_slots.sum()/4),
        one_way_relocated_GPU_hours=float(b.occupancy_deviation_GPU_slots.sum()/8),
        sum_start_delay_minutes=int(delay.sum()),median_changed_delay_minutes=float(np.median(delay)) if len(delay) else 0,
        P95_changed_delay_minutes=float(np.quantile(delay,.95)) if len(delay) else 0,max_delay_minutes=int(delay.max()) if len(delay) else 0,
        max_completion_difference_vs_RW_slots_eligible=int((b.scheduled_end_slot-b.RW_scheduled_completion)[b.eligible].max()),
        slot106_active_GPU_before=90,slot106_active_GPU_after=int(occ[106].sum()),slot106_active_GPU_restored=int(occ[106].sum()-90),
        slot106_site_GPU=dict(zip(bundle["sites"],occ[106])),stages=stages,SHADOW_B_required=False,
        exact_deterministic_lex_tie="CERTIFIED",temporal_objective_label="MINIMUM_INTERVENTION_TEMPORAL_REPAIR_DIAGNOSTIC_OBJECTIVE")
    result.update({f"jobs_delayed_gt_{minutes}min":int((delay>minutes).sum()) for minutes in (30,60,120,240,480)})
    write("V39G_MAY17_SHADOW_A_RESULT.json",result)
    b.to_parquet(OUT/"V39G_MAY17_SHADOW_A_SCHEDULE.parquet",index=False)
    changed.to_csv(OUT/"V39G_MAY17_CHANGED_JOBS.csv",index=False,encoding="utf-8-sig")
    np.savez_compressed(OUT/"V39G_A_WITNESS.npz",GPU_complete=occ,PCC_target=pcc)
    m.dispose()
    auxiliary()

def auxiliary():
    a,_=inputs();bundle=build_model(a,"V39G_SLOT106_AUXILIARY");m=bundle["model"]
    stage=solve_stage(m,gp.quicksum(bundle["load"][106]),"minimum_slot106_GPU_same_original_feasible_set")
    assert stage["optimal"]
    b=expanded(a,bundle);result,occ,pcc=audit_schedule(b,bundle)
    assert result["all_hard_constraints_pass"]
    write("V39G_MAY17_SLOT106_LOAD_RESTORATION.json",{"RSP_baseline_slot106_GPU":90,"RW_slot106_GPU":471,
        "minimum_grid_feasible_slot106_active_GPU":int(occ[106].sum()),"required_restoration_GPU":int(occ[106].sum()-90),
        "slot106_site_GPU":dict(zip(bundle["sites"],occ[106])),"stage":stage,"audit":result,
        "same_original_feasible_set_as_A":True,"A_primary_secondary_tertiary_optima_NOT_fixed":True})
    b.to_parquet(OUT/"V39G_SLOT106_MINIMUM_WITNESS.parquet",index=False)
    m.dispose()

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--phase",choices=("prepare","solve","auxiliary"),default="solve")
    args=parser.parse_args()
    {"prepare":prepare,"solve":run,"auxiliary":auxiliary}[args.phase]()

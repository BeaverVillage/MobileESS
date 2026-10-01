"""Unchanged complete-option binary model, streamed sparse resource columns.

This is not the preregistered compact/factorized fallback. Every authorized
complete option still has its own binary, and no option is dropped to fit.
"""
import pickle
from dataclasses import asdict
from collections import defaultdict
from time import perf_counter
import numpy as np
from v42_native.voltage import PLANNING_LOWER_SQUARED, PLANNING_UPPER_SQUARED
import gurobipy as gp
from .common import *
from v42_temporal.native import load_power
from v42_temporal.service import bind_forecast,objective_order
from v42_final.workload import ForecastBook
from v42_final.reserve import risk_exposure,bind_headroom
from v42_native.grid import GridAuthority,add_grid
from v42_native.contracts import digest
from v42_native.supervision import atomic
from v42_may01.prepare import native_coefficients
from v42_job_capability import validate,resources_used,resource_limit

def planning_grid(m,bundle,known,risk):
    e=pd.read_csv(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv');k=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
    day=pd.Timestamp('2025-05-01T00:00:00+10:00').timestamp();book=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),day)
    timing=bind_forecast(m,book,pd.Timestamp(bundle['issue_time']).timestamp(),k,e.Q10,e.Q90)
    caps=bundle['capacities'];anon={};target={}
    for t in range(96):
        for s in caps:
            anon[s,t+24]=m.addVar(lb=0,name=f'anonymous_GPU[{s},{t}]')
            target[s,t+24]=m.addVar(lb=0,name=f'arrival_target_GPU[{s},{t}]')
        m.addConstr(gp.quicksum(anon[s,t+24] for s in caps)==timing['nominal']['gpu'][t],name='CC4_site_nominal_partition')
        m.addConstr(gp.quicksum(target[s,t+24] for s in caps)==timing['reserve']['gpu'][t],name='CC4_site_reserve_partition')
    reserve=bind_headroom(m,known,anon,target,risk,caps,range(24,120))
    cert,power,idle,swing=load_power(bundle);coeff=native_coefficients(cert)
    authority=GridAuthority(sha(Path(cert['input_identity']['identity']['inputs']['OpenDSS_master']['path'])),
        digest(caps),sha(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),digest(bundle['battery']),PLANNING_LOWER_SQUARED,PLANNING_UPPER_SQUARED,True)
    controls=[]
    for t,c in enumerate(coeff):
        row=[]
        for name in c.control_names:
            site=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):
                p=power[site,t];row.append(p.slope*(idle*caps[site]+swing*(known[site,t+24]+anon[site,t+24]))+p.intercept_kw)
            else:row.append(0.) # Canonical A1 initial MESS P/Q=0; M1 follows only accepted A1.
        controls.append(row)
    rho=add_grid(m,coeff,controls,authority)
    return [('rho',rho),('reserve_shortfall',reserve['CC4_shortfall']+reserve['runtime_shortfall'])],timing,controls

def solve(context):
    started=perf_counter();seal=read(GEN/'DOMAIN_ARTIFACT.json');require(sha(seal['path'])==seal['sha256'],'DOMAIN_ARTIFACT_HASH')
    with Path(seal['path']).open('rb') as f:bundle,jobs,windows,seconds,r,raw,domains,g=pickle.load(f)
    require(len(domains)==1499 and read(OUT/'MAY01_RESOURCE_RECHECK.json')['PASS'],'COMPLETE_DOMAIN_RESOURCE_GATES')
    loaded=perf_counter();m=gp.Model('V42_BOUNDARY_A1_COMPLETE_OPTIONS');m.Params.OutputFlag=0
    try:
        H=r.control_end;tail=max(b.latest_completion for b in windows.values());known={};gpurow={};risk={};riskrow={}
        fixedrisk=defaultdict(float)
        for uid,row in raw.items():
            if uid not in jobs:
                for key,x in risk_exposure(row['GPU_gang'],row['risk_nominal_completion_issue_slot'],row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():
                    fixedrisk[key]+=bundle['runtime_reserve_gamma']*x
        for s,cap in r.capacities.items():
            for t in range(tail):
                known[s,t]=m.addVar(lb=0,ub=cap,name=f'known_GPU[{s},{t}]')
                gpurow[s,t]=m.addConstr(known[s,t]==r.fixed_gpu.get((s,t),0),name=f'known_balance[{s},{t}]')
            for t in range(24,120):
                risk[s,t]=m.addVar(lb=0,name=f'runtime_target[{s},{t}]')
                riskrow[s,t]=m.addConstr(risk[s,t]==fixedrisk[s,t],name=f'runtime_target_balance[{s},{t}]')
        wanrow={(link,t):m.addConstr(gp.LinExpr()<=rate-r.fixed_wan.get((link,t),0),name=f'WAN[{link},{t}]') for (link,t),rate in r.wan_capacities.items()}
        activerow={t:m.addConstr(gp.LinExpr()<=r.max_active_transfers-r.fixed_transfers.get(t,0),name=f'WAN_ACTIVE[{t}]') for t in range(H)}
        choose={u:m.addConstr(gp.LinExpr()==1,name=f'choose_one[{u}]') for u in jobs}
        costs={n:m.addVar(lb=0,name=n) for n in ('migration_count','shift_slots','prestart_changes','tie')}
        costrows={n:m.addConstr(v==0,name=n+'_balance') for n,v in costs.items()}
        primary,timing,controls=planning_grid(m,bundle,known,risk)
        obj=objective_order(primary,timing['deviation'],list(costs.items()));m.update();basevars=m.NumVars
        prepared=perf_counter();nvars=0;completed=0;lastreport=0
        atomic(context.folder/'build_phase.json',dict(phase='MODEL_CONSTRUCTION',domain_complete=True,
            authorized_options=sum(map(len,domains.values())),data_load_seconds=loaded-started,grid_and_rows_seconds=prepared-loaded,
            initial_continuous_count=basevars,initial_constraints=m.NumConstrs))
        for uid,d in sorted(domains.items()):
            j=jobs[uid];source=raw[uid]
            for index,o in enumerate(d):
                context.check();cons=[choose[uid]];coef=[1.]
                for site,a,b in o.segments:
                    cons.extend(gpurow[site,t] for t in range(a,b));coef.extend([-j.gpu]*(b-a))
                for link,t,amount in o.wan:cons.append(wanrow[link,t]);coef.append(amount)
                if o.migrated:
                    for t in range(o.transfer_start,o.transfer_end):cons.append(activerow[t]);coef.append(1.)
                end=int(source['risk_nominal_completion_issue_slot']+o.segments[-1][2]-source['reference_end'])
                for key,x in risk_exposure(j.gpu,end,o.segments[-1][0],bundle['runtime_survival_kernel'],range(24,120)).items():
                    cons.append(riskrow[key]);coef.append(-bundle['runtime_reserve_gamma']*x)
                metrics=(int(o.migrated),o.start-j.reference_start,int(o.initial_site!=j.reference_site),index+1)
                for name,value in zip(costs,metrics):
                    if value:cons.append(costrows[name]);coef.append(-value)
                m.addVar(vtype=gp.GRB.BINARY,name=f'z[{uid},{index}]',column=gp.Column(coef,cons));nvars+=1
                if nvars%10000==0:
                    m.update()
                    if perf_counter()-lastreport>=2:
                        context.progress(dict(phase='MODEL_CONSTRUCTION',domain_complete=True,model_complete=False,
                            jobs_modelled=completed,total_jobs=len(jobs),current_job=uid,complete_option_binaries_added=nvars,
                            total_authorized_complete_options=sum(map(len,domains.values())),partial_binary_count=m.NumBinVars,
                            partial_continuous_count=m.NumVars-m.NumIntVars,partial_constraints=m.NumConstrs,partial_nonzeros=m.NumNZs,
                            elapsed_seconds=perf_counter()-started,model_construction_seconds=perf_counter()-prepared,optimizer_called=False))
                        lastreport=perf_counter()
            completed+=1
        m.update();atomic(context.folder/'MODEL_COMPLETE.json',dict(binary_count=m.NumBinVars,continuous_count=m.NumVars-m.NumIntVars,
            constraints=m.NumConstrs,nonzeros=m.NumNZs,build_seconds=perf_counter()-started,all_options=nvars))
        m.Params.MIPGap=.001;m.Params.Threads=1;m.Params.Seed=20260929;passes=[]
        def callback(model,where):
            if context.remaining<=0:model.terminate()
            if where==gp.GRB.Callback.MIPSOL:
                context.progress(dict(phase='OPTIMIZE',objective_level=obj[len(passes)][0],elapsed_seconds=perf_counter()-started,
                    incumbent=model.cbGet(gp.GRB.Callback.MIPSOL_OBJ),bound=model.cbGet(gp.GRB.Callback.MIPSOL_OBJBND),nodes=model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT)))
        for name,expr in obj:
            context.check();m.setObjective(expr);m.Params.TimeLimit=min(600.,context.remaining);m.optimize(callback)
            row=dict(level=name,status=m.Status,solve_seconds=m.Runtime,incumbent=m.ObjVal if m.SolCount else None,
                best_bound=m.ObjBound,gap=m.MIPGap if m.SolCount else None,nodes=m.NodeCount)
            passes.append(row);atomic(context.folder/'solve_receipt.json',dict(passes=passes))
            if not m.SolCount:return
            if m.Status!=gp.GRB.OPTIMAL:break
            m.addConstr(expr<=m.ObjVal+(1e-7 if name=='rho' else 1e-8),name='lock_'+name)
        # Never publish raw assignments as native truth. Independently validate
        # all physical schedules and resource totals before supervisor acceptance.
        selected={};use=defaultdict(float)
        for v in m.getVars():
            if v.VarName.startswith('z[') and v.X>.5:
                uid,index=v.VarName[2:-1].split(',');o=domains[uid].option(int(index))
                require(uid not in selected,'ONE_OPTION_PER_JOB');validate(jobs[uid],o,windows[uid],r)
                selected[uid]=asdict(o)
                for key,x in resources_used(jobs[uid],o).items():use[key]+=x
        require(set(selected)==set(jobs) and all(x<=resource_limit(key,r)+1e-5 for key,x in use.items()),'PHYSICAL_INCUMBENT_VALIDATION')
        require(m.MaxVio<=1e-5,'FULL_LINEAR_CONSTRAINT_VALIDATION')
        candidate=dict(stage='A1',accepted_native_plan=True,selected=selected,full_linear_max_violation=m.MaxVio,
            physical_audit=dict(PASS=True),domain_sha=read(GEN/'DOMAIN_COMPLETE.json')['domain_sha'],passes=passes)
        context.publish(candidate)
    finally:m.dispose()

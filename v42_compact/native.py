"""Reusable A1/A2 compact job binding to the unchanged native Planning grid."""
from collections import Counter,defaultdict
from time import perf_counter
from dataclasses import asdict
from v42_native.voltage import PLANNING_LOWER_SQUARED, PLANNING_UPPER_SQUARED
import gurobipy as gp
from .common import *
from .graph import GraphFactory,reconstruct
from .formulation import add_job,values,intervention
from v42_boundary.boundaries import load_native
from v42_boundary.model import planning_grid as frozen_a1_grid
from v42_final.reserve import risk_exposure,bind_headroom
from v42_native.supervision import atomic

def completion_risk(j,row,site,end,bundle):
    adjusted=int(row['risk_nominal_completion_issue_slot']+end-row['reference_end'])
    return {key:bundle['runtime_reserve_gamma']*x for key,x in risk_exposure(j.gpu,adjusted,site,bundle['runtime_survival_kernel'],range(24,120)).items()}

def grid(m,bundle,known,risk,mess_p=None,mess_q=None):
    if mess_p is None and mess_q is None:return frozen_a1_grid(m,bundle,known,risk)
    # Exact same CC4/reserve/power/grid functions; A2 accepts fixed M1 anchors.
    from v42_temporal.service import bind_forecast
    from v42_final.workload import ForecastBook
    from v42_temporal.native import load_power
    from v42_may01.prepare import native_coefficients
    from v42_native.grid import GridAuthority,add_grid
    from v42_native.contracts import digest
    e=pd.read_csv(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv');kernel=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
    book=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),pd.Timestamp('2025-05-01T00:00:00+10:00').timestamp())
    timing=bind_forecast(m,book,pd.Timestamp(bundle['issue_time']).timestamp(),kernel,e.Q10,e.Q90)
    caps=bundle['capacities'];anon={};target={}
    for t in range(96):
        for s in caps:
            anon[s,t+24]=m.addVar(lb=0);target[s,t+24]=m.addVar(lb=0)
        m.addConstr(gp.quicksum(anon[s,t+24] for s in caps)==timing['nominal']['gpu'][t])
        m.addConstr(gp.quicksum(target[s,t+24] for s in caps)==timing['reserve']['gpu'][t])
    reserve=bind_headroom(m,known,anon,target,risk,caps,range(24,120))
    cert,power,idle,swing=load_power(bundle);coeff=native_coefficients(cert)
    authority=GridAuthority(sha(Path(cert['input_identity']['identity']['inputs']['OpenDSS_master']['path'])),digest(caps),sha(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),digest(bundle['battery']),PLANNING_LOWER_SQUARED,PLANNING_UPPER_SQUARED,True)
    controls=[]
    for t,c in enumerate(coeff):
        row=[]
        for name in c.control_names:
            s=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):
                p=power[s,t];row.append(p.slope*(idle*caps[s]+swing*(known[s,t+24]+anon[s,t+24]))+p.intercept_kw)
            elif name.startswith('mess_p_kw'):row.append((mess_p or {}).get((s,t),0.))
            else:row.append((mess_q or {}).get((s,t),0.))
        controls.append(row)
    return [('rho',add_grid(m,coeff,controls,authority)),('reserve_shortfall',reserve['CC4_shortfall']+reserve['runtime_shortfall'])],timing,controls

def prepare(context):
    started=perf_counter();bundle,jobs,bounds,seconds,r,raw=load_native();loaded=perf_counter()
    factory=GraphFactory(r,max(b.latest_completion for b in bounds.values()));graphs={};rows=[]
    for uid,j in sorted(jobs.items()):
        context.check();g=factory.graph(j,bounds[uid]);graphs[uid]=g
        rows.append(dict(job_id=uid,fixed=g.fixed is not None,counts=g.counts(),sha=g.sha))
    counts=Counter()
    for row in rows:
        if not row['fixed']:counts.update(row['counts'])
    result=dict(all_jobs=len(jobs),fixed_jobs=sum(row['fixed'] for row in rows),family_counts=dict(counts),
        unique_graphs=len(factory.templates),graph_cache_hits=factory.hits,domain_enumeration=False,
        data_prep_seconds=loaded-started,graph_seconds=perf_counter()-loaded,
        all_index_sets_complete=True,rows=rows)
    atomic(context.folder/'graph_index.json',result)
    return bundle,jobs,bounds,r,raw,graphs,result

def build(context,data,*,mess_p=None,mess_q=None):
    bundle,jobs,bounds,r,raw,graphs,prep=data;started=perf_counter()
    m=gp.Model('V42_COMPACT_STATE_AIDC');m.Params.OutputFlag=0
    tail=max(b.latest_completion for b in bounds.values());known={};risk={};gpurows={};riskrows={}
    fixedrisk=defaultdict(float)
    for uid,row in raw.items():
        if uid not in jobs:
            for key,x in risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():fixedrisk[key]+=bundle['runtime_reserve_gamma']*x
    for site,cap in r.capacities.items():
        for t in range(tail):
            known[site,t]=m.addVar(lb=0,ub=cap,name=f'known[{site},{t}]')
            gpurows[site,t]=m.addConstr(known[site,t]==r.fixed_gpu.get((site,t),0))
        for t in range(24,120):
            risk[site,t]=m.addVar(lb=0,name=f'risk[{site},{t}]')
            riskrows[site,t]=m.addConstr(risk[site,t]==fixedrisk[site,t])
    wanrows={(l,t):m.addConstr(gp.LinExpr()<=rate-r.fixed_wan.get((l,t),0)) for (l,t),rate in r.wan_capacities.items()}
    active={t:m.addConstr(gp.LinExpr()<=r.max_active_transfers-r.fixed_transfers.get(t,0)) for t in range(r.control_end)}
    primary,timing,controls=grid(m,bundle,known,risk,mess_p,mess_q);m.update();grid_seconds=perf_counter()-started
    other_cont=m.NumVars-m.NumIntVars;allvars={};counts=Counter();metrics=[gp.LinExpr() for _ in range(3)];tie=gp.LinExpr();rank=0
    fixed_add_gpu=defaultdict(float);fixed_add_risk=defaultdict(float)
    import psutil
    process=psutil.Process();peak=process.memory_info().rss
    for index,(uid,j) in enumerate(sorted(jobs.items())):
        context.check();g=graphs[uid];v=add_job(m,j,g);allvars[uid]=v
        if not g.fixed:counts.update(g.counts())
        for family in ('r0','r1'):
            for key,var in v[family].items():
                if g.fixed:fixed_add_gpu[key]+=j.gpu*var
                else:m.chgCoeff(gpurows[key],var,-j.gpu)
        for family in ('f0','f1'):
            for (site,end),var in v[family].items():
                for key,x in completion_risk(j,raw[uid],site,end,bundle).items():
                    if g.fixed:fixed_add_risk[key]+=x*var
                    else:m.chgCoeff(riskrows[key],var,-x)
        for key,var in v['w'].items():
            tr=g.transfers[key]
            for l,t,n in tr.wan:m.chgCoeff(wanrows[l,t],var,n)
            for t in range(key[2],tr.end):m.chgCoeff(active[t],var,1.)
        for a,x in zip(metrics,intervention(j,v)):a+=x
        if not g.fixed:
            for family in ('y','q','w','f0','f1'):
                for key,x in sorted(v[family].items()):rank+=1;tie+=rank*x
        if index%10==0:
            m.update();peak=max(peak,process.memory_info().rss)
            context.progress(dict(phase='COMPACT_MODEL_CONSTRUCTION',jobs_complete=index+1,jobs_required=len(jobs),family_counts=dict(counts),
                binaries=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,constraints=m.NumConstrs,nonzeros=m.NumNZs,
                grid_seconds=grid_seconds,build_seconds=perf_counter()-started,peak_observed_RSS_bytes=peak,optimizer_called=False))
    for key,n in fixed_add_gpu.items():gpurows[key].RHS=r.fixed_gpu.get(key,0)+n
    for key,n in fixed_add_risk.items():riskrows[key].RHS=fixedrisk[key]+n
    m.update();peak=max(peak,process.memory_info().rss)
    stats=dict(all_jobs_complete=True,jobs_complete=len(jobs),family_counts=dict(counts),other_continuous=other_cont,
        binaries=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,constraints=m.NumConstrs,nonzeros=m.NumNZs,
        data_prep_seconds=prep['data_prep_seconds'],graph_seconds=prep['graph_seconds'],grid_seconds=grid_seconds,
        model_build_seconds=perf_counter()-started,peak_observed_RSS_bytes=peak,optimizer_called=False,
        COMPLETE_OPTION_ENUMERATION_IN_COMPACT_MODEL=False)
    atomic(context.folder/'MODEL_COMPLETE.json',stats)
    objectives=primary+[('CC4_reference_deviation',timing['deviation'])]+list(zip(('migration_count','shift_slots','prestart_changes'),metrics))+[('physical_event_tie',tie)]
    return m,allvars,objectives,controls

"""PR99 native grid/objective binding copied verbatim; local job binder changed."""
from collections import Counter,defaultdict
from time import perf_counter
import gurobipy as gp
from .common import *
from . import factor
from v42_compact.formulation import add_job,intervention
from v42_compact.native import grid,completion_risk
from v42_final.reserve import risk_exposure
def build(context,data,formulation):
    bundle,jobs,bounds,r,raw,graphs,original,prep=data;started=perf_counter()
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
    primary,timing,controls=grid(m,bundle,known,risk);m.update();grid_seconds=perf_counter()-started
    other_cont=m.NumVars-m.NumIntVars;allvars={};counts=Counter();metrics=[gp.LinExpr() for _ in range(3)];tie=gp.LinExpr();rank=0
    fixed_add_gpu=defaultdict(float);fixed_add_risk=defaultdict(float)
    import psutil
    process=psutil.Process();peak=process.memory_info().rss
    for index,(uid,j) in enumerate(sorted(jobs.items())):
        context.check();g=graphs[uid];v=factor.add_job(m,j,g,r) if formulation=='F2' else add_job(m,j,g);allvars[uid]=v
        for family in ('r0','r1'):
            for key,var in v[family].items():
                if g.fixed:fixed_add_gpu[key]+=j.gpu*var
                else:m.chgCoeff(gpurows[key],var,-j.gpu)
        for family in ('f0','f1'):
            for (site,end),var in v[family].items():
                for key,x in completion_risk(j,raw[uid],site,end,bundle).items():
                    if g.fixed:fixed_add_risk[key]+=x*var
                    else:m.chgCoeff(riskrows[key],var,-x)
        if 'pair' in v:
            for key,var in v['link_bytes'].items():
                if key in wanrows:m.chgCoeff(wanrows[key],var,1.)
                else:m.addConstr(var<=-r.fixed_wan.get(key,0))
            for t,var in v['wan_active'].items():m.chgCoeff(active[t],var,1.)
        else:
            for key,var in v['w'].items():
                tr=g.transfers[key]
                for l,t,n in tr.wan:m.chgCoeff(wanrows[l,t],var,n)
                for t in range(key[2],tr.end):m.chgCoeff(active[t],var,1.)
        for a,x in zip(metrics,intervention(j,v)):a+=x
        if not g.fixed:
            expr,rank=factor.tie_expression(m,j,original[uid],g,v,rank);tie+=expr
            counts.update({n:len(items) for n,items in v.items()})
        if index%10==0:
            m.update();peak=max(peak,process.memory_info().rss)
            context.progress(dict(phase='COMPACT_MODEL_CONSTRUCTION',jobs_complete=index+1,jobs_required=len(jobs),family_counts=dict(counts),
                binaries=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,constraints=m.NumConstrs,nonzeros=m.NumNZs,
                grid_seconds=grid_seconds,build_seconds=perf_counter()-started,peak_observed_RSS_bytes=peak,optimizer_called=False))
    for key,n in fixed_add_gpu.items():gpurows[key].RHS=r.fixed_gpu.get(key,0)+n
    for key,n in fixed_add_risk.items():riskrows[key].RHS=fixedrisk[key]+n
    m.update();peak=max(peak,process.memory_info().rss)
    stats=dict(formulation=formulation,integers=m.NumIntVars-m.NumBinVars,quadratic_constraints=m.NumQConstrs,quadratic_objective=m.NumQNZs,SOS=m.NumSOS,general_constraints=m.NumGenConstrs,all_jobs_complete=True,jobs_complete=len(jobs),family_counts=dict(counts),other_continuous=other_cont,
        binaries=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,constraints=m.NumConstrs,nonzeros=m.NumNZs,
        data_prep_seconds=prep['data_prep_seconds'],graph_seconds=prep['graph_seconds'],grid_seconds=grid_seconds,
        model_build_seconds=perf_counter()-started,peak_observed_RSS_bytes=peak,optimizer_called=False,
        COMPLETE_OPTION_ENUMERATION_IN_COMPACT_MODEL=False)
    atomic(context.folder/(formulation+'_MODEL_COMPLETE.json'),stats)
    objectives=primary+[('CC4_reference_deviation',timing['deviation'])]+list(zip(('migration_count','shift_slots','prestart_changes'),metrics))+[('physical_event_tie',tie)]
    return m,allvars,objectives,controls,dict(known=known,risk=risk,timing=timing)

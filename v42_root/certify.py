"""Independent individual/native checks from a dense solver snapshot."""
import numpy as np
import gurobipy as gp
from .common import *
from .native import reconstruct
from v42_exact.validation import check
from v42_native.voltage import Stage
from v42_compact.native import completion_risk
from v42_final.reserve import risk_exposure
from collections import defaultdict

def dense_value(x,dense):
    if isinstance(x,gp.Var):return float(dense[x.index])
    if isinstance(x,gp.LinExpr):return float(x.getConstant()+sum(x.getCoeff(i)*dense[x.getVar(i).index] for i in range(x.size())))
    return float(x)

def certificate(m,units,data,controls,bindings,levels,dense,solver_max_violation):
    start=time.perf_counter();bundle,jobs,bounds,r,raw,graphs,old,prep=data
    def numeric_units():
        for unit in units:
            yield dict(unit,v={n:{key:dense_value(x,dense) for key,x in items.items()} for n,items in unit['v'].items()})
    selected=reconstruct(numeric_units(),data)
    control_values=[[dense_value(x,dense) for x in row] for row in controls]
    names=m.getAttr('VarName');global_values={name:float(dense[i]) for i,name in enumerate(names) if name.startswith(('CC4_','RT_reserve[','RT_shortfall[','rho_max'))};del names
    rho=dense_value(levels[0][1],dense);cert=check(selected,data,control_values,global_values,rho,stage=Stage.A1)
    known_vio=max(abs(dense_value(x,dense)-(r.fixed_gpu.get((k,t),0)+sum(jobs[u].gpu for u,o in selected.items() for site,a,b in o['segments'] if site==k and a<=t<b))) for (k,t),x in bindings['known'].items())
    expected=defaultdict(float)
    for u,o in selected.items():
        endsite,_,end=o['segments'][-1]
        for key,n in completion_risk(jobs[u],raw[u],endsite,end,bundle).items():expected[key]+=n
    for u,row in raw.items():
        if u not in jobs:
            for key,n in risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():expected[key]+=bundle['runtime_reserve_gamma']*n
    risk_vio=max(abs(dense_value(x,dense)-expected[key]) for key,x in bindings['risk'].items())
    if not hasattr(m,'_root_reserve_row_indices'):
        m._root_reserve_row_indices=[i for i,name in enumerate(m.getAttr('ConstrName')) if name in ('nominal_and_compute_headroom','CC4_reserve_target','RT_reserve_target')]
    constraints=m.getConstrs();linear_vio=0.
    for i in m._root_reserve_row_indices:
        c=constraints[i];lhs=dense_value(m.getRow(c),dense);v=lhs-c.RHS if c.Sense=='<' else c.RHS-lhs if c.Sense=='>' else abs(lhs-c.RHS);linear_vio=max(linear_vio,v)
    cert.update(independent_known_GPU_max_violation=known_vio,independent_Runtime_binding_max_violation=risk_vio,independent_reserve_headroom_max_violation=linear_vio,solver_max_violation=float(solver_max_violation),P1_rho=rho,validation_seconds=time.perf_counter()-start,artificial_physical_slack=0)
    cert['model_defined_scientific_objective_snapshot']={name:dense_value(expr,dense) for name,expr in levels[:6]}
    cert['artificial_scientific_slack']=0
    cert['reserve_shortfall_semantics']='P2 is the inherited model-defined reserve shortfall quantity, not an introduced feasibility-relaxation slack; unoptimized level snapshots are not claimed lexicographic optima'
    cert['PASS']=cert['PASS'] and max(known_vio,risk_vio,linear_vio,solver_max_violation)<=1e-5
    return cert,selected,control_values,global_values

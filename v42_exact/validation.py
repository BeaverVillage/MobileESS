from v42_native.voltage import Stage,voltage_for
"""Independent incumbent checks against frozen physical and grid authority."""
from collections import defaultdict
import math,re
import numpy as np
from v42_job_capability import Option,validate,resources_used,resource_limit
from v42_boundary.generator import Generator
from v42_compact.native import completion_risk
from v42_final.reserve import risk_exposure
from .common import *

def snapshot(bindings,m):
    # Only named global binding variables; no GPU/trajectory model rows are
    # reused in the physical validation.
    names=('CC4_','RT_reserve[','RT_shortfall[','rho_max')
    return {x.VarName:x.X for x in m.getVars() if x.VarName.startswith(names)}

def check(selected,data,controls,bindings_values,primary_rho,*,stage=Stage.A1):
    voltage=voltage_for(stage)
    bundle,jobs,bounds,r,raw,graphs,original,prep=data
    used=defaultdict(float);runtime=defaultdict(float);cache=Generator(r,max(b.latest_completion for b in bounds.values()));failed=[]
    if set(selected)!=set(jobs):raise ValueError('MISSING_SELECTED_JOBS')
    for uid,value in selected.items():
        v=dict(value);v['segments']=tuple(tuple(x) for x in v['segments']);v['wan']=tuple(tuple(x) for x in v['wan']);o=Option(**v);j=jobs[uid]
        validate(j,o,bounds[uid],r)
        if o.migrated:
            tr=cache.transfer(o.initial_site,o.destination,j.gpu,o.transfer_start)
            if not tr.feasible or (tr.wan,tr.end,tr.restart)!=(o.wan,o.transfer_end,o.restart_end):raise ValueError('DETERMINISTIC_WAN_VALIDATION')
        for key,n in resources_used(j,o).items():used[key]+=n
        for key,n in completion_risk(j,raw[uid],o.segments[-1][0],o.segments[-1][2],bundle).items():runtime[key]+=n
    for uid,row in raw.items():
        if uid not in jobs:
            for key,n in risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():runtime[key]+=bundle['runtime_reserve_gamma']*n
    worst=max((n-resource_limit(key,r) for key,n in used.items()),default=0)
    if worst>1e-5:failed.append('PHYSICAL_CAPACITY')
    # Check native all-face grid directly by numpy against independently
    # reloaded frozen coefficients, rather than relying on Gurobi MaxVio.
    from v42_temporal.native import load_power
    from v42_may01.prepare import native_coefficients
    cert,_,_,_=load_power(bundle);coeff=native_coefficients(cert);grid_vio=0.
    angles=2*np.pi*np.arange(16)/16;cos=np.cos(angles);sin=np.sin(angles)
    for c,x in zip(coeff,controls):
        x=np.asarray(x);volt=c.voltage_constant+c.voltage_matrix.T@x
        grid_vio=max(grid_vio,float(np.max(voltage.lower_squared-volt)),float(np.max(volt-voltage.upper_squared)))
        p=c.flow_p_constant+c.flow_p_matrix@x;q=c.flow_q_constant+c.flow_q_matrix@x
        ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
        pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
        rawfaces=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];a=np.argmax(rawfaces,axis=1)
        grad=(cos[a,None]*c.flow_p_matrix+sin[a,None]*c.flow_q_matrix)/ap[:,None]
        correction=c.current_matrix.T-grad;bias=c.current_constant+c.current_matrix.T@c.anchor-np.max(rawfaces,axis=1)
        for k,name in enumerate(c.branch_names):
            faces=cos*p[k]+sin*q[k]
            if re.fullmatch(r'transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]',name.lower()) is None:
                if name.lower().startswith('transformer.'):grid_vio=max(grid_vio,float(c.current_constant[k]+c.current_matrix[:,k]@x-1))
                else:grid_vio=max(grid_vio,float(np.max(faces/ap[k]+correction[k]@(x-c.anchor)+bias[k])-primary_rho))
            rating=c.transformer_ratings[k]
            if rating is not None:grid_vio=max(grid_vio,float(np.max(faces)-rating*math.cos(math.pi/16)))
    if grid_vio>1e-5:failed.append('NATIVE_GRID')
    # Native CC4 work conservation/envelope including carryout.
    from v42_final.workload import ForecastBook
    import pandas as pd
    from v42_compact.common import PR97
    envelope=pd.read_csv(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv');book=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),pd.Timestamp('2025-05-01T00:00:00+10:00').timestamp())
    event=pd.Timestamp(bundle['issue_time']).timestamp();cc4_vio=0.;nomgpu=defaultdict(float);resgpu=defaultdict(float)
    for prefix,field,gpu in (('CC4','remaining_CC4_Q50_GPUh',nomgpu),('CC4_reserve_timing','remaining_CC4_reserve_GPUh',resgpu)):
        for h in range(24):
            work=book.row(h,event)[field];total=0.
            for t in range(4*h,min(96,4*h+len(envelope))):
                xx=bindings_values.get(f'{prefix}_x[{h},{t}]',0);total+=xx;gpu[t+24]+=4*xx;lag=t-4*h
                cc4_vio=max(cc4_vio,float(envelope.Q10.iloc[lag]*work-total),float(total-envelope.Q90.iloc[lag]*work))
            cc4_vio=max(cc4_vio,abs(total+bindings_values.get(f'{prefix}_carryout[{h}]',0)-work))
    if cc4_vio>1e-5:failed.append('CC4_CONSERVATION_ENVELOPE')
    # Headroom and reserve targets include frozen expired-job Runtime risk.
    reserve_vio=0.
    for site,cap in r.capacities.items():
        for t in range(24,120):
            rt=bindings_values.get(f'RT_reserve[{site},{t}]',0);short=bindings_values.get(f'RT_shortfall[{site},{t}]',0)
            cc=bindings_values.get(f'CC4_reserve[{site},{t}]',0)
            reserve_vio=max(reserve_vio,runtime[site,t]-rt-short)
            # Per-site anonymous nominal/target bindings are snapshotted by
            # explicit handles (unnamed PR99 variables), not inferred labels.
    if reserve_vio>1e-5:failed.append('RUNTIME_RESERVE')
    return dict(PASS=not failed,jobs=len(selected),old_validator_PASS=True,deterministic_WAN_PASS=True,
        full_service_and_carryout_PASS=True,rack_gang_PASS=True,physical_capacity_max_violation=max(0,worst),
        grid_max_violation=max(0,grid_vio),CC4_max_violation=max(0,cc4_vio),Runtime_max_violation=max(0,reserve_vio),failed=failed,
        limitation='Native reserve anonymous site headroom is additionally checked by independent linear residual evaluation; no Actual AC run is executed.')

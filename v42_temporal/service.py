"""Linear aggregate service decisions. GPUh variables are never job identities."""
import numpy as np
import gurobipy as gp
from .common import require

def validate_envelope(lower,upper):
    lo,hi=map(lambda x:np.asarray(x,float),(lower,upper))
    require(lo.ndim==hi.ndim==1 and lo.shape==hi.shape and len(lo)>0,'ENVELOPE_AXES')
    require(np.isfinite(lo).all() and np.isfinite(hi).all() and np.all((0<=lo)&(lo<=hi)&(hi<=1)),'ENVELOPE_ORDER')
    require(np.all(np.diff(lo)>=0) and np.all(np.diff(hi)>=0),'ENVELOPE_MONOTONIC')
    return lo,hi

def bind_service(model,work,kernel,lower,upper,*,begin=0,end=96,prefix='CC4',served_before=None):
    """Remaining per-hour mass on day-origin slots; historical service accounted
    explicitly on mid-hour replans. ForecastBook already expires closed hours.
    Default prior service is zero only when no positive-mass cohort predates begin.
    """
    lo,hi=validate_envelope(lower,upper);work=np.asarray(work,float);k=np.asarray(kernel,float)
    require(work.ndim==1 and np.isfinite(work).all() and np.all(work>=0),'NONNEGATIVE_WORK')
    require(k.ndim==1 and np.isfinite(k).all() and np.all(k>=0) and abs(k.sum()-1)<1e-9,'FROZEN_KERNEL_MASS')
    require(type(begin) is int and type(end) is int and 0<=begin<end,'ACTIVE_HORIZON')
    x={};carry={};deviations=[];cumulative={}
    prior=served_before or {}
    for h,w in enumerate(work):
        if not w:continue
        origin=4*h
        require(origin>=begin or h in prior,'MID_COHORT_REPLAN_REQUIRES_SERVICE_HISTORY')
        old=float(prior.get(h,0.));require(np.isfinite(old) and old>=0,'SERVICE_HISTORY')
        total=w+old
        carry[h]=model.addVar(lb=0,name=f'{prefix}_carryout[{h}]')
        cumulative[h]=gp.LinExpr(old)
        for t in range(max(begin,origin),min(end,origin+len(lo))):
            lag=t-origin;x[h,t]=model.addVar(lb=0,name=f'{prefix}_x[{h},{t}]')
            cumulative[h]+=x[h,t]
            model.addConstr(cumulative[h]>=lo[lag]*total,name=f'{prefix}_CDF_L[{h},{lag}]')
            model.addConstr(cumulative[h]<=hi[lag]*total,name=f'{prefix}_CDF_U[{h},{lag}]')
            reference=total*(k[lag] if lag<len(k) else 0.)
            plus=model.addVar(lb=0,name=f'{prefix}_dplus[{h},{t}]')
            minus=model.addVar(lb=0,name=f'{prefix}_dminus[{h},{t}]')
            model.addConstr(plus>=x[h,t]-reference,name=prefix+'_deviation_positive')
            model.addConstr(minus>=reference-x[h,t],name=prefix+'_deviation_negative')
            deviations.append(plus+minus)
        model.addConstr(gp.quicksum(v for (c,t),v in x.items() if c==h)+carry[h]==w,name=f'{prefix}_work_conservation[{h}]')
    gpu={t:4*gp.quicksum(v for (h,s),v in x.items() if s==t) for t in range(begin,end)}
    return dict(x=x,carryout=carry,gpu=gpu,deviation=gp.quicksum(deviations)/max(float(work.sum()),1e-12),work=work)

def bind_forecast(model,book,event_time,kernel,lower,upper,*,begin=0,end=96,served_before=None,reserve_served_before=None):
    rows=[book.row(h,event_time) for h in range(24)]
    nominal=bind_service(model,[r['remaining_CC4_Q50_GPUh'] for r in rows],kernel,lower,upper,
                         begin=begin,end=end,served_before=served_before)
    reserve=bind_service(model,[r['remaining_CC4_reserve_GPUh'] for r in rows],kernel,lower,upper,
                         begin=begin,end=end,prefix='CC4_reserve_timing',served_before=reserve_served_before)
    return dict(nominal=nominal,reserve=reserve,deviation=nominal['deviation']+reserve['deviation'],
                reserve_is_realized_load=False,depletion_rows=rows)

def objective_order(primary,deviation,later):
    require([n for n,_ in primary]==['rho','reserve_shortfall'],'P1_P2_ORDER')
    return primary+[('CC4_reference_deviation',deviation)]+later

def slot_minima(lower,upper):
    lo,hi=validate_envelope(lower,upper)
    return np.maximum(0.,lo-np.r_[0.,hi[:-1]])

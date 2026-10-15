"""Empirical Planning-only overrun headroom, never a duration predictor."""
import numpy as np
from .common import require


def survival(actual_seconds,q50_seconds,horizon_slots=96):
    y,q=map(lambda a:np.asarray(a,float),(actual_seconds,q50_seconds))
    require(y.shape==q.shape and y.size>0 and np.isfinite(y).all() and np.isfinite(q).all() and (y>=0).all() and (q>=0).all(),'RUNTIME_SECONDS')
    residual=np.sort(np.maximum(y-q,0.))
    s=1.-np.searchsorted(residual,np.arange(horizon_slots)*900,side='right')/len(residual)
    return np.minimum.accumulate(s)


def risk_exposure(gpu,nominal_end_slot,site,kernel,slots,current_hard_slot=None):
    require(gpu>0 and int(gpu)==gpu and type(nominal_end_slot) is int,'RISK_RESOURCE_UNITS')
    result={}
    for t in slots:
        lag=t-nominal_end_slot
        if 0<=lag<len(kernel) and t!=current_hard_slot:result[site,t]=gpu*float(kernel[lag])
    return result


def calibrate(observed,predicted,*,role,event_times,prediction_available_times,observation_cutoff,epsilon=1e-12):
    require(role=='CAL','ONLY_CAL_SETS_GAMMA')
    require(epsilon==1e-12,'FROZEN_NUMERICAL_EPSILON')
    require(len(observed)==len(predicted)==len(event_times)==len(prediction_available_times),'CAL_TIME_AXIS')
    require(all(a<=t for a,t in zip(prediction_available_times,event_times)),'FUTURE_CALIBRATION_STATE')
    require(all(t<observation_cutoff for t in event_times),'UNOBSERVED_CAL_EVENT')
    o,h=map(lambda a:np.asarray(a,float),(observed,predicted))
    require(o.ndim==h.ndim==1 and o.shape==h.shape and o.size>0 and np.isfinite(o).all() and np.isfinite(h).all() and (o>=0).all() and (h>=0).all(),'FINITE_CAL_REPLAY')
    # Epsilon cannot manufacture support. A positive demand with zero exposure
    # means the proposed single-scale form cannot cover that event at any scale.
    require(not np.any((h<=epsilon)&(o>0)),'POSITIVE_OVERRUN_WITH_ZERO_EXPOSURE')
    gamma=float(np.quantile(o/np.maximum(h,epsilon),.90,method='higher'))
    return dict(gamma_90=gamma,coverage=float((o<=gamma*h+1e-9).mean()),target=.90,
        slot_count=len(o),epsilon=epsilon,quantile_method='higher',reserve_GPU_slots=float(np.sum(gamma*h)))


def bind_headroom(model,known_gpu,unknown_nominal,cc4_target,runtime_target,capacities,slots):
    """Targets may be linear selected-option expressions. Report both P2 parts."""
    import gurobipy as gp
    cc={};rt={};xi_cc={};xi_rt={}
    for site,cap in capacities.items():
        for t in slots:
            k=(site,t)
            cc[k]=model.addVar(lb=0,ub=cap,name=f'CC4_reserve[{site},{t}]')
            rt[k]=model.addVar(lb=0,ub=cap,name=f'RT_reserve[{site},{t}]')
            xi_cc[k]=model.addVar(lb=0,name=f'CC4_shortfall[{site},{t}]')
            xi_rt[k]=model.addVar(lb=0,name=f'RT_shortfall[{site},{t}]')
            model.addConstr(known_gpu.get(k,0)+unknown_nominal.get(k,0)+cc[k]+rt[k]<=cap,name='nominal_and_compute_headroom')
            model.addConstr(xi_cc[k]>=cc4_target.get(k,0)-cc[k],name='CC4_reserve_target')
            model.addConstr(xi_rt[k]>=runtime_target.get(k,0)-rt[k],name='RT_reserve_target')
    return dict(CC4_shortfall=gp.quicksum(xi_cc.values()),runtime_shortfall=gp.quicksum(xi_rt.values()),
        CC4_achieved=cc,runtime_achieved=rt,reserve_is_electrical_load=False,
        objective_layer='P2_ONLY',P1_modified=False)

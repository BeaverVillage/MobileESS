"""Current CC4 same-hour nominal/uncertainty envelope, with explicit P2.

Known admitted service is never slack. Unknown aggregate is never a job, a
queue, or a movable backlog. Electrical readiness requires a bound callback.
"""
import gurobipy as gp
from .contracts import require


def bind(model,forecast,issue_time,known_gpu,capacities,electrical_readiness):
    forecast.validate(issue_time)
    require(callable(electrical_readiness),'RESERVE_ELECTRICAL_AUTHORITY_MISSING')
    nominal={};headroom={};reserve={};shortfall=[]
    for h in range(24):
        for site,cap in capacities.items():
            nominal[site,h]=model.addVar(lb=0,name=f'unknown_nominal[{site},{h}]')
            headroom[site,h]=model.addVar(lb=0,name=f'uncertainty_headroom[{site},{h}]')
            for k in range(4):
                model.addConstr(known_gpu.get((site,4*h+k),0)+nominal[site,h]+headroom[site,h]<=cap,name='known_nominal_reserve_GPU')
        spread=forecast.q90[h]-forecast.q50[h]
        model.addConstr(gp.quicksum(nominal[s,h] for s in capacities)==forecast.q50[h],name='same_hour_nominal')
        reserve[h]=model.addVar(lb=0,ub=spread,name=f'absorbable_reserve[{h}]')
        model.addConstr(reserve[h]==gp.quicksum(headroom[s,h] for s in capacities),name='reserve_resource_binding')
        shortfall.append(spread-reserve[h])
    receipt=electrical_readiness(model,nominal,headroom)
    require(receipt.get('nominal_physics') is True and receipt.get('incremental_readiness_physics') is True
        and len(receipt.get('authority_sha256',''))==64,'RESERVE_ELECTRICAL_CERTIFICATE')
    return dict(shortfall=gp.quicksum(shortfall),nominal=nominal,headroom=headroom,reserve=reserve)

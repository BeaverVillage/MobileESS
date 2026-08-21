#!/usr/bin/env python3
from __future__ import annotations
import json, math
import gurobipy as gp
from gurobipy import GRB

DT=5.0/60.0
ETA_CH=ETA_DIS=0.95

def solve(label:str,scale:float):
    m=gp.Model(label);m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Seed=0
    m.Params.MIPGap=0.0;m.Params.NumericFocus=2;m.Params.ScaleFlag=2
    mode=m.addVar(vtype=GRB.BINARY,name='mode')
    pdis=m.addVar(lb=0.0,ub=550.0/scale,name='Pdis')
    pchg=m.addVar(lb=0.0,ub=550.0/scale,name='Pchg')
    q=m.addVar(lb=-700.0/scale,ub=700.0/scale,name='Q')
    e1=m.addVar(lb=440.0/scale,ub=1080.0/scale,name='E1')
    debt1=m.addVar(lb=0.0,ub=1080.0/scale,name='DE1')
    repay=m.addVar(lb=0.0,name='repay')
    m.addConstr(pdis<=550.0/scale*mode)
    m.addConstr(pchg<=550.0/scale*(1.0-mode))
    m.addConstr(q==100.0/scale)
    m.addQConstr((pdis-pchg)*(pdis-pchg)+q*q<=(700.0/scale)**2)
    route=(20.0+3.0)/scale
    m.addConstr(e1==700.0/scale+ETA_CH*DT*pchg-DT*pdis/ETA_DIS-route)
    discharge=DT*pdis/ETA_DIS;charge=ETA_CH*DT*pchg
    m.addConstr(repay<=charge);m.addConstr(repay<=15.0/scale+discharge)
    m.addConstr(debt1==15.0/scale+discharge-repay)
    # Convert model power back to the frozen external kW objective.
    m.setObjective(0.12*scale*(pchg-pdis)+0.007*mode+0.002*scale*debt1,GRB.MINIMIZE)
    m.optimize()
    if m.Status!=GRB.OPTIMAL or m.SolCount<=0:raise RuntimeError(label+' did not solve')
    return {
        'objective':float(m.ObjVal),'mode':float(mode.X),'Pdis_kW':scale*float(pdis.X),
        'Pchg_kW':scale*float(pchg.X),'Q_kvar':scale*float(q.X),
        'E1_kWh':scale*float(e1.X),'DE1_kWh':scale*float(debt1.X),
        'ConstrVio':float(m.ConstrVio),'BoundVio':float(m.BoundVio),'IntVio':float(m.IntVio),
        'ScaleFlag':int(m.Params.ScaleFlag),'NumericFocus':int(m.Params.NumericFocus),
    }

native=solve('C5R4R1_NATIVE_KW_KWH',1.0)
normalized=solve('C5R4R1_NORMALIZED_MW_MWH',1000.0)
keys=('objective','mode','Pdis_kW','Pchg_kW','Q_kvar','E1_kWh','DE1_kWh')
diff={k:abs(native[k]-normalized[k]) for k in keys}
limits={k:(1e-7 if k in ('objective','mode') else 1e-6) for k in keys}
passed=all(math.isfinite(v) and v<=limits[k] for k,v in diff.items())
passed=passed and all(x['ConstrVio']<=1e-7 and x['BoundVio']<=1e-8 and x['IntVio']<=1e-8 for x in (native,normalized))
out={'status':'PASS' if passed else 'FAIL','PASS':passed,'native':native,'normalized':normalized,
     'absolute_differences':diff,'acceptance_limits':limits,
     'scientific_feasible_set_changed':False,'objective_changed':False}
print(json.dumps(out,indent=2,sort_keys=True))
raise SystemExit(0 if passed else 2)

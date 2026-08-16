#!/usr/bin/env python3
from __future__ import annotations
import json, math
import gurobipy as gp
from gurobipy import GRB

m=gp.Model('C5R4_FIXED_INTEGER_POLISH_SMOKE')
m.Params.OutputFlag=0
m.Params.Threads=1
b=m.addVar(vtype=GRB.BINARY,name='decision')
p=m.addVar(lb=0.0,ub=0.55,name='P_MW')
q=m.addVar(lb=-0.7,ub=0.7,name='Q_Mvar')
e=m.addVar(lb=0.44,ub=1.08,name='E_MWh')
m.addConstr(p<=0.55*b)
m.addConstr(e==0.60+0.95*(5.0/60.0)*p)
m.addQConstr(p*p+q*q<=0.49)
m.setObjective(-10.0*p+0.01*q,GRB.MINIMIZE)
m.optimize()
if m.Status!=GRB.OPTIMAL or m.SolCount<=0:raise RuntimeError('smoke MIP did not solve')
pre=float(m.ObjVal);bz=float(round(b.X));pre_qrows=int(m.NumQConstrs)
fm=m.fixed();fm.Params.OutputFlag=0;fm.Params.Threads=1
if fm.IsMIP!=0 or fm.NumIntVars!=0 or fm.NumBinVars!=0:raise RuntimeError('Model.fixed() polish model not continuous')
if int(fm.NumQConstrs)!=pre_qrows:raise RuntimeError('Model.fixed() did not retain QCP rows')
fm.Params.Method=2;fm.Params.NumericFocus=3;fm.Params.ScaleFlag=2
fm.Params.FeasibilityTol=1e-9;fm.Params.OptimalityTol=1e-9;fm.Params.BarQCPConvTol=1e-10
fm.optimize()
if fm.Status!=GRB.OPTIMAL or fm.SolCount<=0:raise RuntimeError('smoke Model.fixed() polish did not solve')
post=float(fm.ObjVal);fb=fm.getVarByName('decision')
try:int_vio=float(fm.IntVio);int_vio_source='GUROBI_ATTRIBUTE'
except Exception:int_vio=abs(float(fb.X)-bz);int_vio_source='FIXED_INTEGER_VALUE_ERROR'
out={
    'status':'PASS','PASS':True,'pre_objective':pre,'post_objective':post,
    'objective_not_worse':bool(post<=pre+1e-9),'fixed_integer_value':float(fb.X),
    'model_fixed_api_used':True,'qcp_rows_retained':int(fm.NumQConstrs),
    'ScaleFlag':int(fm.Params.ScaleFlag),'NumericFocus':int(fm.Params.NumericFocus),
    'num_int_vars':int(fm.NumIntVars),'num_bin_vars':int(fm.NumBinVars),'is_mip':int(fm.IsMIP),
    'ConstrVio':float(fm.ConstrVio),'BoundVio':float(fm.BoundVio),'IntVio':int_vio,'IntVio_source':int_vio_source,
}
out['PASS']=bool(out['objective_not_worse'] and abs(out['fixed_integer_value']-bz)<=1e-9 and out['ConstrVio']<=1e-6 and out['BoundVio']<=1e-7)
out['status']='PASS' if out['PASS'] else 'FAIL'
print(json.dumps(out,indent=2,sort_keys=True))
raise SystemExit(0 if out['PASS'] else 2)

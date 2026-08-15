#!/usr/bin/env python3
"""User-runtime smoke for the exact C1 Gurobi lifecycle pattern.
No project data, no Stage-1 state, no physical commit.  This validates that a
pristine continuous convex-QCP authority can be copied, while a separate primal
MIP is mutated/solved, and child copies still expose Pi/RC/QCPi with QCPDual=1.
"""
import json,math,time
try:
 import gurobipy as gp
 from gurobipy import GRB
except Exception as e:
 print(json.dumps({'status':'FAIL_IMPORT','error':repr(e)},indent=2));raise

def solve_dual(model,label):
 model.Params.OutputFlag=0;model.Params.QCPDual=1;model.Params.Method=2;model.Params.BarConvTol=1e-10
 model.optimize()
 if model.Status!=GRB.OPTIMAL: raise RuntimeError(f'{label} status={model.Status}')
 if model.NumIntVars or model.NumBinVars or model.IsMIP: raise RuntimeError(f'{label} not continuous')
 pis=[float(c.Pi) for c in model.getConstrs()]
 qpis=[float(q.QCPi) for q in model.getQConstrs()]
 rcs=[float(v.RC) for v in model.getVars()]
 if not (all(math.isfinite(x) for x in pis+qpis+rcs)): raise RuntimeError(f'{label} nonfinite dual/RC')
 return {'label':label,'objective':float(model.ObjVal),'linear_pi_count':len(pis),'qcp_pi_count':len(qpis),'rc_count':len(rcs),'is_mip':int(model.IsMIP),'num_int_vars':int(model.NumIntVars),'num_bin_vars':int(model.NumBinVars)}

t0=time.time()
m=gp.Model('B6C1_CONTINUOUS_AUTHORITY_SMOKE')
x=m.addVar(lb=0.0,ub=2.0,name='x');y=m.addVar(lb=0.0,ub=2.0,name='y')
m.setObjective(x+2*y,GRB.MINIMIZE)
m.addConstr(x+y>=1.0,name='demand')
m.addQConstr(x*x+y*y<=4.0,name='circle')
m.update()
# Capture pristine continuous authority before any primal integrality mutation.
authority=m.copy()
root=solve_dual(authority.copy(),'authority_root_copy')
# Mutate only a separate primal copy into a MIP and solve it.
primal=m.copy();primal.getVarByName('x').VType=GRB.BINARY;primal.update();primal.Params.OutputFlag=0;primal.optimize()
if not primal.IsMIP: raise RuntimeError('separate primal copy did not become MIP')
# Child originates from pristine continuous authority, not from primal.relax().
child=authority.copy();child.getVarByName('x').UB=0.75;child.update()
childres=solve_dual(child,'authority_child_copy')
out={'status':'PASS','root':root,'child':childres,'separate_primal_is_mip':bool(primal.IsMIP),
     'post_mip_relax_used':False,'elapsed_s':time.time()-t0,'stage1_state_touched':False}
print(json.dumps(out,indent=2,sort_keys=True))

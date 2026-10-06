"""Construct the explicit original/reduced monolith, with unchanged names."""
import numpy as np
import gurobipy as gp
from v42_degen.common import POLICY
def build(A,d,keep=None,env=None):
 keep=np.arange(A.shape[0]) if keep is None else np.asarray(keep,int)
 model=gp.Model('EXACT_REDUCED_4MESS_M1' if len(keep)<A.shape[0] else 'ORIGINAL_4MESS_M1',env=env)
 model.Params.OutputFlag=0
 variables=model.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],obj=d['objective'])
 variables.VarName=d['names'].tolist();model.ObjCon=float(d['constant'])
 constraints=model.addMConstr(A[keep],variables,d['sense'][keep],d['rhs'][keep])
 constraints.ConstrName=d['row_names'][keep].tolist()
 for k,v in POLICY.items():model.setParam(k,v)
 model.update();return model

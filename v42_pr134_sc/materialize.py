"""Native candidate presolve census; no optimization is permitted here."""
import json
import time
import gurobipy as gp
import numpy as np
import scipy.sparse as sp
from .common import *
from .build import census

def model(name,*,day=None):
    a=sp.load_npz(LOCAL/(name+'_MATRIX.npz'));z=attributes(name)
    m=gp.Model('CURRENT_PR134_'+name);m.Params.OutputFlag=0
    if day is not None:
        from v42_a_stage_domain_v2.execution import tag_model_for_day
        tag_model_for_day(m,day)
    x=m.addMVar(a.shape[1],lb=z['lb'],ub=z['ub'],vtype=z['vtype'])
    m.addMConstr(a,x,z['sense'],z['rhs'])
    ex=gp.LinExpr()
    for j in np.flatnonzero(z['obj']):ex+=float(z['obj'][j])*x[int(j)].item()
    m.setObjective(ex);m.update()
    if (m.NumVars,m.NumConstrs,m.NumNZs)!=(a.shape[1],a.shape[0],a.nnz):raise ValueError('NATIVE_CANDIDATE_MATRIX_CENSUS')
    actual=m.getA();delta=actual-a;delta.eliminate_zeros()
    for key in ('RHS','Sense','VType','Obj'):
        expected={'RHS':'rhs','Sense':'sense','VType':'vtype','Obj':'obj'}[key]
        if not np.array_equal(np.array(m.getAttr(key)),z[expected]):raise ValueError('NATIVE_'+key+'_AXIS_DRIFT')
    for key in ('LB','UB'):
        got=np.array(m.getAttr(key));got=np.where(got>=1e100,np.inf,np.where(got<=-1e100,-np.inf,got))
        if not np.array_equal(got,z[key.lower()]):raise ValueError('NATIVE_'+key+'_DOMAIN_DRIFT')
    if delta.nnz:raise ValueError('NATIVE_MATRIX_COEFFICIENT_DRIFT')
    write(name+'_MATERIALIZATION_AUDIT.json',dict(PASS=True,coefficient_differences=0,all_row_axes_equal=True,all_column_bounds_types_objective_equal=True,
          optimization_calls=0,original_matrix=record(LOCAL/(name+'_MATRIX.npz')),native_fingerprint=m.Fingerprint))
    m.Params.Threads=1;m.Params.Method=1;m.Params.Seed=20260929;m.Params.MIPGap=.005
    return m

def run():
    for name in ('A1R','A2SC'):
        proof=json.loads((OUT/(name+'_INDEPENDENT_VERIFICATION.json')).read_text())
        if not proof['PASS']:raise PermissionError('EXACT_MATRIX_PROOF_REQUIRED')
        start=time.perf_counter();m=model(name)
        m.Params.LogFile=str(LOCAL/(name+'_PRESOLVE.log'));m.Params.OutputFlag=1
        built=time.perf_counter();p=m.presolve();c=census(p)
        c.update(model_load_wall_seconds=built-start,presolve_wall_seconds=time.perf_counter()-built,
                 optimization_calls=0,presolve_mapping_available=False,discovery_only=True)
        write(name+'_PRESOLVE_CENSUS.json',c)
        print(name,'presolve',c,flush=True)
        p.dispose();m.dispose()

if __name__=='__main__':run()

"""Independent structural replay of the actual solver LP, no optimization."""
import numpy as np
import gurobipy as gp
from .common import *
from .audit import model,mask
from .canonical import from_model,digest_arrays
from .engine import Recourse

def run():
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();results=[]
    for kind in ['full','B3']:
        m=model(env,kind=='B3');can=from_model(m,None if kind=='full' else mask())
        lp=Recourse(can,env,objective=kind=='full');actual=lp.model.getA();diff=actual-can.A
        matrix_equal=not diff.nnz or np.all(diff.data==0)
        assert matrix_equal
        assert np.array_equal(lp.model.getAttr('RHS'),can.b)
        assert set(lp.model.getAttr('Sense'))=={'<'}
        assert lp.model.NumIntVars==lp.model.NumQConstrs==lp.model.NumSOS==lp.model.NumGenConstrs==0
        assert np.array_equal(lp.model.getAttr('Obj'),can.c if kind=='full' else np.zeros(len(can.yi)))
        assert all(v<=-gp.GRB.INFINITY for v in lp.model.getAttr('LB'))
        assert all(v>=gp.GRB.INFINITY for v in lp.model.getAttr('UB'))
        with np.load(ROOT/'docs/v42_m1_late_window_certificate_mipstart/MIP_START_EXACT.npz') as z:start=z['values']
        lp.rows.RHS=can.rhs(start[can.xi]);lp.model.update()
        assert np.array_equal(lp.model.getAttr('RHS'),can.rhs(start[can.xi]))
        results.append(dict(kind=kind,PASS=True,actual_solver_rows=lp.model.NumConstrs,
            actual_solver_columns=lp.model.NumVars,actual_solver_nonzeros=lp.model.NumNZs,
            expected_nonzeros=can.A.nnz,coefficient_difference=0,RHS_after_fixed_x_exact=True,
            mixed_senses_and_bounds_already_canonical=True,actual_solver_LP=True,
            actual_matrix_hash=digest_arrays(actual.indptr,actual.indices,actual.data),optimize_calls=0))
        lp.close();m.dispose();print(kind,'ACTUAL SOLVER MATRIX PASS',flush=True)
    env.dispose();dump('ACTUAL_SOLVER_RECOURSE_MATRIX_AUDIT.json',dict(PASS=True,checks=results,optimize_calls=0))

if __name__=='__main__':run()

"""Construct actual large native LPs and compare API matrices; never optimize."""
import time
import numpy as np
import gurobipy as gp
from .common import *
from .representation import from_model

def run():
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();records=[]
    from v42_benders.audit import mask
    try:
        for label in ['full','B3']:
            source=gp.read(str(ROOT.parent/'THRESHOLD_LOCAL/F3.mps'),env=env)
            if label=='B3':source.addConstr(source.getVarByName('rho_max')<=.5732125039436496,name='exact_B3_threshold');source.update()
            n=from_model(source,None if label=='full' else mask())
            start=time.perf_counter();lp=gp.Model('V2_BUILD_ONLY_'+label,env=env)
            y=lp.addMVar(len(n.yi),lb=n.lower,ub=n.upper,vtype='C');lp.addMConstr(n.A,y,n.sense,n.b)
            lp.setObjective(n.c@y+n.objective_constant);lp.update();elapsed=time.perf_counter()-start
            A=lp.getA().tocsr();delta=A-n.A;equal=delta.nnz==0 or np.all(delta.data==0)
            lb=np.asarray(lp.getAttr('LB'));ub=np.asarray(lp.getAttr('UB'))
            lb=np.where(lb<=-gp.GRB.INFINITY,-np.inf,lb);ub=np.where(ub>=gp.GRB.INFINITY,np.inf,ub)
            passed=equal and np.array_equal(lp.getAttr('RHS'),n.b) and np.array_equal(lp.getAttr('Sense'),n.sense) and np.array_equal(lb,n.lower) and np.array_equal(ub,n.upper) and np.array_equal(lp.getAttr('Obj'),n.c)
            assert passed and lp.NumIntVars==0 and lp.NumQConstrs==lp.NumSOS==lp.NumGenConstrs==0
            records.append(dict(partition=label,PASS=True,build_seconds=elapsed,rows=lp.NumConstrs,columns=lp.NumVars,
                nonzeros=lp.NumNZs,coefficient_difference=0,sense_bitwise_equal=True,RHS_bitwise_equal=True,
                native_bounds_equal=True,objective_bitwise_equal=True,optimize_calls=0,
                timing_is_build_only_not_same_x_recourse=True))
            lp.dispose();source.dispose();print(label,'ACTUAL LP MATRIX PASS; NO OPTIMIZE',flush=True)
    finally:env.dispose()
    dump('ACTUAL_NATIVE_LP_MATRIX_AUDIT.json',dict(PASS=True,records=records,optimize_calls=0))

if __name__=='__main__':run()

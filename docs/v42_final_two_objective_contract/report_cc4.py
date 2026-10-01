"""Evaluate true fixed-timing deviation after solves, without optimization.

Recreate only the identical native global-variable prefix. Verify controls and
prefix size against the executed full model before reading cohort variables.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import v42_two
from v42_root.common import *
from v42_root.data import prepare
from v42_compact.native import grid
from v42_root.certify import dense_value
from v42_compact.common import OLD
import gurobipy as gp,numpy as np,pandas as pd

def main():
    data=prepare();bundle,jobs,bounds,r,*_=data;m=gp.Model();m.Params.OutputFlag=0
    tail=max(b.latest_completion for b in bounds.values());known={};risk={}
    for site,cap in r.capacities.items():
        for t in range(tail):known[site,t]=m.addVar(lb=0,ub=cap,name=f'known[{site},{t}]')
        for t in range(24,120):risk[site,t]=m.addVar(lb=0,name=f'risk[{site},{t}]')
    _,timing,controls=grid(m,bundle,known,risk);m.update()
    expected=read(LOCAL/'replay/F2-CRA_MODEL_COMPLETE.json')['global_variables']
    assert m.NumVars==expected
    kernel=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy();results=[]
    for mode in ['diagnostic','replay']:
        dense=np.load(LOCAL/mode/'FINAL_X.npy');ctrl=np.asarray(read(LOCAL/mode/'CONTROLS.json'))
        recovered=np.asarray([[dense_value(x,dense) for x in row] for row in controls])
        error=float(np.max(np.abs(recovered-ctrl)));assert error<1e-6
        metrics={}
        for name in ['nominal','reserve']:
            service=timing[name];numerator=sum(abs(dense[x.index]-service['work'][h]*(kernel[t-4*h] if t-4*h<len(kernel) else 0.)) for (h,t),x in service['x'].items())
            metrics[name]=float(numerator/max(float(np.sum(service['work'])),1e-12))
        metrics['total']=metrics['nominal']+metrics['reserve']
        target=OUT/('P2_DIAGNOSTIC.json' if mode=='diagnostic' else 'TWO_OBJECTIVE_A1_OPTIMIZATION.json')
        receipt=read(target);receipt['CC4_fixed_timing_reference_deviation']=metrics;receipt['CC4_deviation_is_unoptimized_auxiliary']=True;dump(target.name,receipt)
        results.append(dict(mode=mode,PASS=True,global_prefix_columns=m.NumVars,control_alignment_max_error=error,metrics=metrics,optimized=False,solver_calls=0))
    dump('CC4_FIXED_TIMING_REPORT.json',dict(PASS=True,results=results,method='Post-solve arithmetic on identical native global prefix; no solve, no decision changes',source_sha256=sha(__file__)))
    m.dispose();print('FIXED TIMING CC4 REPORT PASS')

if __name__=='__main__':main()

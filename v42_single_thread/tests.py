"""Post-heavy pytest in one process; enforce Threads=1 on test optimizers."""
import json
import os
from datetime import datetime,timezone
from .common import ENV,OUT,write,sha
from .resources import exclusive_gate,snapshot

def run(arguments):
    os.environ.update(ENV)
    os.environ.pop('V42_ROOT_OUTPUT',None)
    os.environ.pop('V42_ROOT_LOCAL',None)
    exclusive_gate('pytest_before_start')
    import gurobipy as gp
    import pytest
    gp.setParam('Threads',1)
    original=gp.Model.optimize;calls=[];active=[False]
    def optimize(m,*args,**kwargs):
        if active[0]:raise RuntimeError('OVERLAPPING_TEST_OPTIMIZATION_FORBIDDEN')
        m.Params.Threads=1
        entry=dict(Threads=m.Params.Threads,model_name=m.ModelName,rows=m.NumConstrs,columns=m.NumVars,start_UTC=datetime.now(timezone.utc).isoformat())
        calls.append(entry)
        active[0]=True
        try:return original(m,*args,**kwargs)
        finally:
            active[0]=False
            entry['end_UTC']=datetime.now(timezone.utc).isoformat()
    gp.Model.optimize=optimize
    try:
        from threadpoolctl import threadpool_limits
        with threadpool_limits(limits=1):code=pytest.main(arguments)
    finally:gp.Model.optimize=original
    write('PYTEST_EXECUTION_'+('SEMANTIC' if any('v42_single_thread' in s for s in arguments) else 'FULL')+'.json',dict(exit_code=code,one_pytest_process=True,xdist_used=False,environment=ENV,test_optimization_calls=calls,all_test_Gurobi_Threads_one=all(c['Threads']==1 for c in calls),overlapping_optimizer_calls=False,scientific_model_solve_calls=0,post_test_snapshot=snapshot()))
    return code

if __name__=='__main__':
    import sys
    raise SystemExit(run(sys.argv[1:] or ['-q']))

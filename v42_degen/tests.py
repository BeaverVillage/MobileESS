"""Only after the scientific worker ends: one pytest process, sequential Threads=1."""
import os
from datetime import datetime,timezone
from .common import ENV,write
from .resources import gate
from v42_single_thread.resources import snapshot

def run(arguments):
    os.environ.update(ENV);os.environ.pop('V42_ROOT_OUTPUT',None);os.environ.pop('V42_ROOT_LOCAL',None)
    before=gate('pytest_before_start')
    import gurobipy as gp
    import pytest
    gp.setParam('Threads',1);original=gp.Model.optimize;calls=[];active=[False]
    def optimize(m,*args,**kwargs):
        if active[0]:raise RuntimeError('OVERLAPPING_TEST_OPTIMIZATION')
        m.Params.Threads=1
        row=dict(Threads=m.Params.Threads,model_name=m.ModelName,rows=m.NumConstrs,columns=m.NumVars,start_UTC=datetime.now(timezone.utc).isoformat());calls.append(row);active[0]=True
        try:return original(m,*args,**kwargs)
        finally:active[0]=False;row['end_UTC']=datetime.now(timezone.utc).isoformat()
    gp.Model.optimize=optimize
    try:
        from threadpoolctl import threadpool_limits
        with threadpool_limits(limits=1):code=pytest.main(arguments)
    finally:gp.Model.optimize=original
    label='SEMANTIC' if any('v42_degen' in v for v in arguments) else 'FULL'
    write('PYTEST_EXECUTION_'+label+'.json',dict(exit_code=code,one_pytest_process=True,xdist_used=False,environment=ENV,before_snapshot=before,after_snapshot=snapshot(),test_optimization_calls=calls,all_test_Gurobi_Threads_one=all(r['Threads']==1 for r in calls),observed_test_calls_nonoverlapping=all(a['end_UTC']<=b['start_UTC'] for a,b in zip(calls,calls[1:])),scientific_full_model_retries=0))
    return code
if __name__=='__main__':
    import sys
    raise SystemExit(run(sys.argv[1:] or ['-q']))

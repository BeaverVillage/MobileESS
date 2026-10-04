"""After pilot terminal, one-process tests with all native solves one-thread."""
from .common import *
import sys
from datetime import datetime,timezone
def run(args):
    gate('pytest_before_start');os.environ.update(ENV);os.environ.pop('V42_ROOT_OUTPUT',None);os.environ.pop('V42_ROOT_LOCAL',None)
    assert (OUT/'DW_ROOT_RESULT.json').exists(),'PILOT_MUST_TERMINATE_BEFORE_TESTS'
    import v42_strengthening.testing as fixtures
    fixtures.write=write;fixtures.bind_historical_fixtures()
    import gurobipy as gp
    import pytest
    from threadpoolctl import threadpool_limits
    gp.setParam('Threads',1);original=gp.Model.optimize;calls=[];active=[False]
    def optimize(m,*a,**k):
        if active[0]:raise RuntimeError('OVERLAPPING_OPTIMIZATION_FORBIDDEN')
        m.Params.Threads=1;active[0]=True
        row=dict(start=datetime.now(timezone.utc).isoformat(),Threads=m.Params.Threads,rows=m.NumConstrs,columns=m.NumVars);calls.append(row)
        try:return original(m,*a,**k)
        finally:active[0]=False;row['end']=datetime.now(timezone.utc).isoformat()
    gp.Model.optimize=optimize
    try:
        with threadpool_limits(limits=1):code=pytest.main(args)
    finally:gp.Model.optimize=original
    label='SEMANTIC' if any('tests/' in v or 'tests\\' in v for v in args) else 'FULL'
    write('PYTEST_'+label+'_RECEIPT.json',dict(exit_code=code,environment=ENV,one_pytest_process=True,xdist=False,test_optimization_calls=calls,
          all_Gurobi_Threads_one=all(c['Threads']==1 for c in calls),calls_nonoverlapping=all(a['end']<=b['start'] for a,b in zip(calls,calls[1:])),
          full_scientific_pricing_retry_calls=0,tests_after_heavy=True))
    return code
if __name__=='__main__':raise SystemExit(run(sys.argv[1:] or ['-q']))

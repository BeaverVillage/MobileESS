from .common import *
import sys
from datetime import datetime,timezone
def run(args):
    gate('pytest');assert (OUT/'DW_FINAL_RESULT.json').exists(),'HEAVY_MUST_TERMINATE'
    os.environ.pop('V42_ROOT_OUTPUT',None);os.environ.pop('V42_ROOT_LOCAL',None)
    import v42_strengthening.testing as fixtures
    fixtures.write=write;fixtures.bind_historical_fixtures()
    import pytest,gurobipy as gp
    from threadpoolctl import threadpool_limits
    gp.setParam('Threads',1);original=gp.Model.optimize;calls=[];active=[False]
    def optimize(m,*a,**k):
        assert not active[0];active[0]=True;m.Params.Threads=1
        r=dict(start=datetime.now(timezone.utc).isoformat(),Threads=m.Params.Threads,rows=m.NumConstrs,columns=m.NumVars);calls.append(r)
        try:return original(m,*a,**k)
        finally:active[0]=False;r['end']=datetime.now(timezone.utc).isoformat()
    gp.Model.optimize=optimize
    try:
        with threadpool_limits(limits=1):code=pytest.main(args)
    finally:gp.Model.optimize=original
    label='SEMANTIC' if any('tests/' in a or 'tests\\' in a for a in args) else 'FULL'
    write('PYTEST_'+label+'_RECEIPT.json',dict(exit_code=code,arguments=args,one_worker=True,after_heavy=True,environment=ENV,all_Gurobi_Threads_one=all(r['Threads']==1 for r in calls),calls_nonoverlapping=all(a['end']<=b['start'] for a,b in zip(calls,calls[1:])),test_optimization_calls=calls))
    return code
if __name__=='__main__':raise SystemExit(run(sys.argv[1:] or ['-q']))

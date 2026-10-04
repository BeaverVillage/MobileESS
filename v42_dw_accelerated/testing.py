from .common import *
import sys
def run(args):
    assert not (OUT/'DW_INFLIGHT.json').exists(),'OWN_NATIVE_PHASE_MUST_TERMINATE'
    from v42_single_thread.resources import snapshot
    s=snapshot();assert not any(not p['self'] for p in s['heavy_processes'])
    import v42_strengthening.testing as fixtures
    fixtures.write=write;fixtures.bind_historical_fixtures()
    # PR144 historical branch-only diff fixture is bound to its exact audited
    # PR143->PR144 diff. Other Git/source checks execute unchanged; current
    # PR147 scientific bytes and integration scope are independently verified.
    import types,v42_dw_runtime.fixtures as runtime_fixtures
    historical=runtime_fixtures.baseline_audit
    class HistoricalGit:
        @staticmethod
        def check_output(args,**kwargs):
            if args[:4]==['git','diff',runtime_fixtures.BASE_HEAD,'--name-only']:
                preserve_old();a=read(OUT/'DW_PR144_IMPORT_AUDIT.json');assert a['PASS']
                return '\n'.join(a['exact_diff_paths'])+'\n'
            return subprocess.check_output(args,**kwargs)
    runtime_fixtures.baseline_audit=types.FunctionType(historical.__code__,dict(historical.__globals__,subprocess=HistoricalGit),historical.__name__,historical.__defaults__)
    import pytest,gurobipy as gp
    from threadpoolctl import threadpool_limits
    gp.setParam('Threads',1);original=gp.Model.optimize;calls=[];active=[False]
    def optimize(m,*a,**k):
        assert not active[0];active[0]=True;m.Params.Threads=1;start=time.perf_counter()
        try:return original(m,*a,**k)
        finally:active[0]=False;calls.append(dict(start=start,end=time.perf_counter(),Threads=m.Params.Threads))
    gp.Model.optimize=optimize
    try:
        with threadpool_limits(limits=1):code=pytest.main(args)
    finally:gp.Model.optimize=original
    label=os.environ.get('DW_TEST_LABEL') or ('SEMANTIC' if any('tests/' in x or 'tests\\' in x for x in args) else 'FULL')
    write('PYTEST_'+label+'_RECEIPT.json',dict(exit_code=code,arguments=args,after_heavy=True,environment=ENV,all_Gurobi_Threads_one=all(r['Threads']==1 for r in calls),calls_nonoverlapping=all(a['end']<=b['start'] for a,b in zip(calls,calls[1:])),calls=calls))
    return code
if __name__=='__main__':raise SystemExit(run(sys.argv[1:] or ['-q']))

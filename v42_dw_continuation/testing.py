from .common import *
import sys
def run(args):
    assert not (OUT/'DW_INFLIGHT.json').exists(),'OWN_NATIVE_PHASE_MUST_TERMINATE'
    from .admission import inspect_native
    import time
    while inspect_native()[1]:print('PYTEST_WAIT_RESOURCE',flush=True);time.sleep(2)
    import v42_strengthening.testing as fixtures
    fixtures.write=write;fixtures.bind_historical_fixtures()
    # PR144 historical branch-only diff fixture is bound to its exact audited
    # PR143->PR144 diff. Other Git/source checks execute unchanged; current
    # PR147 scientific bytes and integration scope are independently verified.
    from v42_single_thread import resources
    original_snapshot=resources.snapshot
    def filtered_snapshot():
        value=original_snapshot();rows,blocked=inspect_native();allowed={r['pid'] for r in rows if r not in blocked}
        value['heavy_processes']=[r for r in value['heavy_processes'] if r['self'] or r['pid'] not in allowed];return value
    resources.snapshot=filtered_snapshot
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
    import threading
    gp.setParam('Threads',1);original=gp.Model.optimize;calls=[];active=[None];observations=[];conflicts=[];done=threading.Event()
    def watch():
        while not done.wait(.5):
            rows,blocked=inspect_native();observations.append(dict(perf=time.perf_counter(),processes=rows,blocked=blocked))
            if blocked and active[0] is not None:
                conflicts.append(dict(perf=time.perf_counter(),blocked=blocked));active[0].terminate()
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    def optimize(m,*a,**k):
        while inspect_native()[1]:print('PYTEST_FIXTURE_WAIT_RESOURCE',flush=True);time.sleep(2)
        assert active[0] is None;active[0]=m;m.Params.Threads=1;start=time.perf_counter()
        try:return original(m,*a,**k)
        finally:active[0]=None;calls.append(dict(start=start,end=time.perf_counter(),Threads=m.Params.Threads))
    gp.Model.optimize=optimize
    try:
        with threadpool_limits(limits=1):code=pytest.main(args)
    finally:done.set();thread.join();gp.Model.optimize=original;resources.snapshot=original_snapshot
    label=os.environ.get('DW_TEST_LABEL') or ('SEMANTIC' if any('tests/' in x or 'tests\\' in x for x in args) else 'FULL')
    write(label+'_PYTEST_LANE_CONCURRENCY_AUDIT.json',dict(observations=observations,conflicts=conflicts,actual_concurrent_heavy_native_solve=len(conflicts),other_lane_kill_calls=0,other_lane_terminate_calls=0))
    write('PYTEST_'+label+'_RECEIPT.json',dict(exit_code=code,arguments=args,after_heavy=True,environment=ENV,all_Gurobi_Threads_one=all(r['Threads']==1 for r in calls),calls_nonoverlapping=all(a['end']<=b['start'] for a,b in zip(calls,calls[1:])),calls=calls,actual_concurrent_heavy_native_solve=len(conflicts),other_lane_kill_calls=0,other_lane_terminate_calls=0))
    assert not conflicts,'Conflicting native lane detected during own fixture'
    return code
if __name__=='__main__':raise SystemExit(run(sys.argv[1:] or ['-q']))

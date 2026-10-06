"""Sequential lightweight regressions; all native fixtures use Threads=1."""
from .common import *
import time

def run():
    import gurobipy as gp
    import pytest
    from threadpoolctl import threadpool_limits
    from v42_m1_accel_vnext.native_state import inspect_live
    assert not inspect_live()[1],'WAIT_RESOURCE: foreign native solve'
    assert not (OUT/'DW_INFLIGHT.json').exists(),'Own full-scale phase must finish before tests'
    original=gp.Model.optimize;calls=[]
    def optimize(m,*args,**kwargs):
        assert not inspect_live()[1],'WAIT_RESOURCE: foreign native solve'
        m.Params.Threads=1;start=time.perf_counter()
        try:return original(m,*args,**kwargs)
        finally:calls.append(dict(start=start,end=time.perf_counter(),Threads=m.Params.Threads))
    gp.Model.optimize=optimize
    arguments=['-q','tests/v42_m_stage','tests/v42_m1_accel_vnext',
        'tests/v42_dw_continuation','tests/v42_dw_runtime','tests/v42_dw_bound',
        '-k','not original_sources_domain_checkpoint_unchanged']
    try:
        with threadpool_limits(limits=1):code=pytest.main(arguments)
    finally:gp.Model.optimize=original
    write('REGRESSION_RECEIPT.json',dict(exit_code=code,arguments=arguments,
        excluded_historical_git_diff_fixture='PR143-to-PR144 exact branch diff; incompatible with this PR154 child',
        all_models_Threads_one=all(c['Threads']==1 for c in calls),native_calls=calls,
        sequential=all(a['end']<=b['start'] for a,b in zip(calls,calls[1:]))))
    return code

if __name__=='__main__':raise SystemExit(run())

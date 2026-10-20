import contextvars
import threading
from types import SimpleNamespace
from contextlib import contextmanager
import pytest

from v44_recovery_r026 import thread_policy as policy


def synthetic_constructor(coefficients):
    arrays={'current':{'rating_a':3}}
    from v42_thermal.planning import bind_coefficient
    return [bind_coefficient(c,arrays['current']['rating_a']) for c in coefficients]


def test_four_independent_build_threads_preserve_order_and_context(monkeypatch):
    import v42_thermal.authority as authority
    import v42_thermal.planning as planning
    owner=threading.get_ident();warm=[];ids=set();barrier=threading.Barrier(4)
    active=contextvars.ContextVar('thread_test_case');active.set('EXACT_CASE')
    monkeypatch.setattr(authority,'current_authority',lambda:warm.append(threading.get_ident()))
    def bind(c,rating):
        assert active.get()=='EXACT_CASE'
        if c<4:barrier.wait(timeout=10)
        return (c,rating)
    monkeypatch.setattr(planning,'bind_coefficient',bind)
    result=policy.coefficient_reader(synthetic_constructor,ids)(list(range(12)))
    assert result==[(c,3) for c in range(12)]
    assert len(ids)==4 and owner not in ids
    assert warm==[owner]


def test_worker_exception_is_not_suppressed(monkeypatch):
    import v42_thermal.authority as authority
    import v42_thermal.planning as planning
    monkeypatch.setattr(authority,'current_authority',lambda:None)
    def bind(c,rating):raise ValueError('PHYSICS_FAILURE')
    monkeypatch.setattr(planning,'bind_coefficient',bind)
    with pytest.raises(ValueError,match='PHYSICS_FAILURE'):
        policy.coefficient_reader(synthetic_constructor,set())([1])


def test_thread_limits_are_real_and_restore_on_failure():
    import numpy
    from threadpoolctl import threadpool_info
    before=[(p['filepath'],p['num_threads']) for p in threadpool_info() if p['user_api']=='blas']
    for count in [1,4]:
        with pytest.raises(RuntimeError):
            with policy.numerical_threads(count) as pools:
                assert pools
                assert all(p['num_threads']==count for p in pools if p['user_api']=='blas')
                raise RuntimeError('test')
    assert [(p['filepath'],p['num_threads']) for p in threadpool_info() if p['user_api']=='blas']==before


def test_source_shape_drift_fails_closed():
    def changed():return []
    with pytest.raises(ValueError,match='BOUNDARY_DRIFT'):policy.coefficient_reader(changed,set())


def test_all_campaign_arms_metadata_preserves_solver_thread_counts(monkeypatch):
    from v44 import worker,campaign
    original=campaign.stage_request
    fake=lambda case,stage:dict(case,stage=stage,Threads=4 if stage in ('M1','M2') else 1)
    monkeypatch.setattr(campaign,'stage_request',fake)
    monkeypatch.setattr(worker,'actual',lambda request,*a,**k:'B2_UNCHANGED')
    with policy.install():
        for arm in ['B0','B1','B2','B3']:
            for stage in ['A1','A2','M1','M2','ACTUAL']:
                row=campaign.stage_request({'arm':arm},stage)
                assert row['Threads']==(4 if stage in ('M1','M2') else 1)
                assert row['Actual_numerical_threads']==1 and row['model_build_threads']==4
    assert campaign.stage_request is fake

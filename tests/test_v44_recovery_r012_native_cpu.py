from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from v44_recovery_r012 import native_cpu as native


@pytest.mark.parametrize('method',['optimize','presolve'])
@pytest.mark.parametrize('threads',[1,4])
def test_exact_native_call_boundary_preserves_thread_count_and_arguments(monkeypatch,method,threads):
    state={'mask':'original'};calls=[];marker=object()
    @contextmanager
    def placement():
        state['mask']='P';metadata={}
        try:yield metadata
        finally:state['mask']='original';metadata['restored']=True
    monkeypatch.setattr(native,'actual_cpu_scope',placement)
    model=SimpleNamespace(Params=SimpleNamespace(Threads=threads,TimeLimit=123.,MIPGap=.005))
    def original(received,*args,**kwargs):
        assert received is model and args==(marker,) and kwargs=={'test':7}
        assert model.Params.Threads==threads and model.Params.TimeLimit==123. and model.Params.MIPGap==.005
        calls.append(state['mask']);return marker
    context={'stage':'A1','calls':[]};token=native._stage.set(context)
    try:assert native.native_wrapper(original,method)(model,marker,test=7) is marker
    finally:native._stage.reset(token)
    assert calls==(['P'] if threads==1 else ['original']) and state['mask']=='original'
    assert len(context['calls'])==(1 if threads==1 else 0)
    if threads==1:assert context['calls'][0]['placement']['restored']


def test_failure_restores_affinity_and_preserves_original_exception(monkeypatch):
    state=[]
    @contextmanager
    def placement():
        state.append('P');row={}
        try:yield row
        finally:state.append('RESTORE');row['restored']=True
    monkeypatch.setattr(native,'actual_cpu_scope',placement)
    def denied(model):raise PermissionError('NATIVE_ZERO_PREFLIGHT_OPTIMIZE_DENIED')
    wrapped=native.native_wrapper(denied,'optimize');context={'stage':'A2','calls':[]}
    token=native._stage.set(context)
    try:
        assert wrapped.__name__=='denied'
        with pytest.raises(PermissionError,match='NATIVE_ZERO_PREFLIGHT_OPTIMIZE_DENIED'):
            wrapped(SimpleNamespace(Params=SimpleNamespace(Threads=1)))
    finally:native._stage.reset(token)
    assert state==['P','RESTORE'] and context['calls'][0]['placement']['restored']


def test_outside_case_stage_never_changes_affinity(monkeypatch):
    def forbidden():raise AssertionError('no stage placement allowed')
    monkeypatch.setattr(native,'actual_cpu_scope',forbidden)
    assert native.native_wrapper(lambda model:42,'optimize')(object())==42


def test_real_gurobi_parameters_native0_and_real_os_affinity():
    import gurobipy as gp
    import psutil
    from v44_recovery_r012.cpu_placement import physical_candidates,windows_cpu_sets
    process=psutil.Process();before=process.cpu_affinity();expected=[physical_candidates(windows_cpu_sets(),before)[0]['logical']]
    for threads in [1,4]:
        with gp.Model() as model:
            model.Params.OutputFlag=0;model.Params.Threads=threads;model.Params.TimeLimit=123.
            model.Params.MIPGap=.03;model.Params.Method=2
            context={'stage':'A2','calls':[]};token=native._stage.set(context)
            def native0(m):
                assert process.cpu_affinity()==(expected if threads==1 else before)
                assert (m.Params.Threads,m.Params.TimeLimit,m.Params.MIPGap,m.Params.Method)==(threads,123.,.03,2)
                return 'NO_NATIVE_OPTIMIZATION'
            try:assert native.native_wrapper(native0,'optimize')(model)=='NO_NATIVE_OPTIMIZATION'
            finally:native._stage.reset(token)
            assert process.cpu_affinity()==before


def test_stage_binding_rejected_before_native(monkeypatch):
    from v44 import execution,worker
    monkeypatch.setattr(execution,'assert_current',lambda:{'request':dict(case_root='correct',day='d',arm='B1',source_sha='s')})
    with native.install():
        with pytest.raises(PermissionError,match='CASE_STAGE_BINDING'):
            worker.a_stage(dict(stage='A1',case_root='wrong',day='d',arm='B1',source_sha='s'))


def test_native_zero_remains_authoritative_inside_install():
    import gurobipy as gp
    from v42_may_campaign_native90.preflight import native_zero
    original=gp.Model.optimize
    with native.install():
        with native_zero() as attempts:
            assert gp.Model.optimize.__name__=='denied'
            with gp.Model() as model:
                with pytest.raises(PermissionError,match='NATIVE_ZERO_PREFLIGHT_OPTIMIZE_DENIED'):model.optimize()
        assert len(attempts)==1
    assert gp.Model.optimize is original

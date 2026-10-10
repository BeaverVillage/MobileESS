"""External diagnostics-only seam tests, not production admission qualification."""
from copy import deepcopy
from types import SimpleNamespace
import math

import pytest

from pdhg_observer import ScopedObserver, FIELDS, UNKNOWN


class DataUnavailable(Exception):
    pass


class Model:
    def __init__(self, values=None, counters=None):
        self.values = values or {}
        self.counters = counters or {}
        self.queries = []
    def cbGet(self, code):
        self.queries.append(('callback_scalar', code))
        value = self.values.get(code, DataUnavailable('missing scalar'))
        if isinstance(value, Exception):
            raise value
        return value
    def __getattr__(self, name):
        if name in ('PDHGIterCount','IterCount','BarIterCount'):
            self.queries.append(('post_Native_scalar', name))
            value = self.counters.get(name, DataUnavailable('missing counter'))
            if isinstance(value, Exception):
                raise value
            return value
        raise AssertionError('DIAGNOSTIC_CANNOT_READ_OR_MUTATE:' + name)


@pytest.fixture
def fixture():
    names = ['RUNTIME','POLLING','MESSAGE',*FIELDS,*(name for row in FIELDS.values() for name in row)]
    codes = SimpleNamespace(**{name:i+1 for i,name in enumerate(dict.fromkeys(names))})
    model = Model({getattr(codes,name):float(i+1) for i,name in enumerate(names)},
                  {'PDHGIterCount':17.,'IterCount':0.,'BarIterCount':0.})
    publications = []
    authority_calls = []
    elapsed = [0.]
    def authority():
        authority_calls.append(True)
    observer = ScopedObserver(model,codes,DataUnavailable,1e100,
        assert_authority=authority,binding={'case':'case','source':'current','attempt':'fresh','call_index':1},
        publish=publications.append,clock=lambda:elapsed[0])
    return SimpleNamespace(model=model,codes=codes,publications=publications,authority=authority_calls,
                           elapsed=elapsed,observer=observer)


def known_call(**kwargs):
    return dict(entered_native=True,status='FINISHED',runtime_unavailable=False,
                Native_Runtime=300.9,Native_status=11,**kwargs)


def test_pdhg_event_records_only_diagnostics_not_bounds(fixture):
    f=fixture
    f.observer(f.model,f.codes.PDHG)
    value=f.observer.snapshot()
    row=value['last_observation_by_phase']['PDHG']
    assert set(row['fields']) == set(FIELDS['PDHG'])
    assert value['current_observed_callback_phase'] == 'PDHG'
    assert value['phase_callback_counts'] == {'PDHG':1}
    assert value['Native_accounting_authority'] is False
    assert value['certified_LB_UB_or_Gap_authority'] is False
    assert value['Native_Pi_observed'] is False
    assert not any(kind=='post_Native_scalar' for kind,_ in f.model.queries)


@pytest.mark.parametrize('phase', list(FIELDS))
def test_phase_fields_and_counts_are_separate(fixture,phase):
    f=fixture
    f.observer(f.model,getattr(f.codes,phase))
    value=f.observer.snapshot()
    assert value['phase_callback_counts']=={phase:1}
    assert set(value['last_observation_by_phase'][phase]['fields'])==set(FIELDS[phase])


@pytest.mark.parametrize('phase', ['MESSAGE','POLLING'])
def test_unrecognized_callback_does_not_invent_progress_or_query(fixture,phase):
    f=fixture
    f.observer(f.model,getattr(f.codes,phase))
    assert f.observer.snapshot()['current_observed_callback_phase']==UNKNOWN
    assert f.model.queries==[] and f.publications==[]


@pytest.mark.parametrize('value',[math.nan,math.inf,-math.inf,True,None,'invalid',1e100,-1e100])
def test_nonfinite_unavailable_scalars_remain_unknown(fixture,value):
    f=fixture
    f.model.values[f.codes.PDHG_PRIMINF]=value
    f.observer(f.model,f.codes.PDHG)
    assert f.observer.snapshot()['last_observation_by_phase']['PDHG']['fields']['PDHG_PRIMINF']==UNKNOWN


@pytest.mark.parametrize('field', FIELDS['PDHG'])
def test_query_error_is_recorded_without_fake_zero(fixture,field):
    f=fixture
    f.model.values[getattr(f.codes,field)]=DataUnavailable('unavailable')
    f.observer(f.model,f.codes.PDHG)
    value=f.observer.snapshot()
    assert value['last_observation_by_phase']['PDHG']['fields'][field]==UNKNOWN
    assert value['observation_errors'][0]['kind']=='UNAVAILABLE_SCALAR'


def test_wrong_model_and_closed_scope_rejected_before_query(fixture):
    f=fixture
    other=Model()
    with pytest.raises(PermissionError,match='OWNED_MODEL'):
        f.observer(other,f.codes.PDHG)
    assert other.queries==[]
    f.observer.finish(None)
    with pytest.raises(PermissionError,match='OPEN_SCOPE'):
        f.observer(f.model,f.codes.PDHG)
    assert f.model.queries==[]


def test_caller_authority_failure_propagates_before_diagnostic_queries(fixture):
    f=fixture
    def fail():
        raise PermissionError('CURRENT_SOURCE_MODEL_CALL_DRIFT')
    f.observer.authority=fail
    with pytest.raises(PermissionError,match='CURRENT_SOURCE'):
        f.observer(f.model,f.codes.PDHG)
    assert f.model.queries==[] and f.publications==[]


def test_original_budget_callback_occurs_first_and_cap_accounting_is_unchanged(fixture):
    f=fixture
    events=[]
    immutable_call=known_call()
    captured=deepcopy(immutable_call)
    def original_budget_callback(model,where):
        events.append('original_Runtime_cap_ledger_progress')
        return f.observer(model,where)
    original_budget_callback(f.model,f.codes.PDHG)
    assert events==['original_Runtime_cap_ledger_progress']
    assert immutable_call==captured
    value=f.observer.finish(immutable_call)
    assert value['original_accounting_record']==captured
    assert value['post_Native_scalar_counters']['PDHGIterCount']==17


def test_original_callback_exception_propagates_without_diagnostic_work(fixture):
    f=fixture
    def original(*args):
        raise RuntimeError('ORIGINAL_RUNTIME_UNKNOWN_OR_GUARD_FAILURE')
    f.observer.original_callback=original
    with pytest.raises(RuntimeError,match='ORIGINAL_RUNTIME_UNKNOWN'):
        f.observer(f.model,f.codes.PDHG)
    assert f.model.queries==[]


@pytest.mark.parametrize('record', [None,{},dict(entered_native=False,status='ADMISSION_DENIED',runtime_unavailable=False,Native_Runtime=0.),
    dict(entered_native=True,status='IN_FLIGHT',runtime_unavailable=False,Native_Runtime=300.),
    dict(entered_native=True,status='FAILED',runtime_unavailable=True,Native_Runtime=None),
    dict(entered_native=True,status='FINISHED',runtime_unavailable=False,Native_Runtime=math.nan)])
def test_unknown_or_unentered_native_never_queries_post_native_counters(fixture,record):
    f=fixture
    value=f.observer.finish(record)
    assert value['original_call_completion_receipt_supplied'] is False
    assert set(value['post_Native_scalar_counters'].values())=={UNKNOWN}
    assert f.model.queries==[]
    assert value['original_accounting_record']==record


def test_missing_post_native_counters_stay_unknown(fixture):
    f=fixture
    f.model.counters={}
    value=f.observer.finish(known_call())
    assert set(value['post_Native_scalar_counters'].values())=={UNKNOWN}
    assert len(value['observation_errors'])==3


def test_publication_coalescing_preserves_all_event_counts_without_solver_sleep(fixture):
    f=fixture
    for _ in range(20):
        f.observer(f.model,f.codes.PDHG)
    assert len(f.publications)==1 and f.observer.phase_counts['PDHG']==20
    f.elapsed[0]=1.
    f.observer(f.model,f.codes.PDHG)
    assert len(f.publications)==2 and f.observer.phase_counts['PDHG']==21


def test_publication_io_failure_remains_diagnostic_and_does_not_touch_call(fixture):
    f=fixture
    def fail(value):
        raise OSError('OWNED_DIAGNOSTIC_ONLY_IO_UNAVAILABLE')
    f.observer.publish=fail
    record=known_call()
    before=deepcopy(record)
    f.observer(f.model,f.codes.PDHG)
    value=f.observer.finish(record)
    assert value['observation_errors'][0]['kind']=='OBSERVATION_PUBLICATION_FAILED'
    assert record==before and value['original_accounting_record']==before


def test_snapshot_binding_is_detached_from_publication_consumer(fixture):
    f=fixture
    snapshot=f.observer.snapshot()
    snapshot['binding']['source']='foreign'
    assert f.observer.snapshot()['binding']['source']=='current'

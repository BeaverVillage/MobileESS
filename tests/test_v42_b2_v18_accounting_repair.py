from contextlib import nullcontext
import json
import pytest
from test_v42_b2_seed_policy import Clock,Model
from v42_b2_seed_recovery_v18r2 import budget as b,execution,policy,native_diagnostics
from v42_b2_seed_recovery_v18r2.common import atomic
from v42_b2_seed_recovery_v18r2.common import record

@pytest.fixture
def ports(monkeypatch):
    monkeypatch.setattr(execution,'current',lambda:dict(request=dict(arm='B2',day='2025-05-01')))
    monkeypatch.setattr(b,'native_scope',lambda *a:nullcontext())
    monkeypatch.setattr(b,'guard',lambda *a:None)

def test_duplicate_diagnostic_keys_do_not_drop_measured_runtime(tmp_path,ports):
    clock=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=clock)
    model=Model(clock,18.673,1)
    budget.native_optimize(model,component='FEASIBILITY_LP',track='M_START',requested_seconds=120)
    value=json.loads(budget.path.read_text())
    assert value['measured_Native_Runtime']==18.673
    assert len(value['calls'])==1 and value['inflight'] is None
    assert value['calls'][0]['SolCount']==1
    assert value['calls'][0]['Native_first_incumbent_Runtime']=='UNKNOWN'
    assert value['calls'][0]['effective_TimeLimit']==120

def test_optional_diagnostic_failure_cannot_erase_runtime(tmp_path,ports,monkeypatch):
    def failed(*a):raise TypeError('optional diagnostic failed')
    monkeypatch.setattr(native_diagnostics,'finished',failed)
    clock=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=clock)
    model=Model(clock,18.673,1)
    budget.native_optimize(model,component='FEASIBILITY_LP',track='M_START',requested_seconds=120)
    value=json.loads(budget.path.read_text())
    assert value['measured_Native_Runtime']==18.673 and value['calls'][0]['Native_Runtime']==18.673
    assert 'diagnostic failed' in value['calls'][0]['diagnostic_error']

def test_failed_progress_after_return_still_has_durable_runtime(tmp_path,ports):
    def progress(value):
        if value.get('Native_Runtime_completed',0)>0:raise RuntimeError('monitor transport failed')
    clock=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=clock,progress=progress)
    with pytest.raises(RuntimeError,match='monitor transport'):
        budget.native_optimize(Model(clock,18.673,1),component='FEASIBILITY_LP',requested_seconds=120)
    assert json.loads(budget.path.read_text())['measured_Native_Runtime']==18.673

def test_unknown_runtime_is_quarantined_with_remaining_unknown(tmp_path,ports):
    clock=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=clock);budget.charge(3300.)
    with pytest.raises(RuntimeError,match='QUARANTINE'):
        budget.native_optimize(Model(clock,None,0),component='FEASIBILITY_LP',requested_seconds=120)
    value=json.loads(budget.path.read_text())
    assert value['calls'][0]['runtime_unavailable'] and value['measured_Native_Runtime']==3300.
    assert budget.snapshot()['Native_Runtime'] is None
    assert budget.snapshot()['native_remaining_seconds'] is None
    with pytest.raises(RuntimeError,match='QUARANTINE'):
        budget.native_optimize(Model(clock,1.,1),requested_seconds=120)

def test_actual_overhead_is_charged_before_ceiling_exception(tmp_path,ports):
    clock=Clock();budget=b.DateBudget(tmp_path/'ledger.json',clock=clock);budget.charge(5390)
    with pytest.raises(b.BudgetStop):
        budget.native_optimize(Model(clock,10.25,1),component='FEASIBILITY_LP',requested_seconds=120)
    value=json.loads(budget.path.read_text())
    assert value['measured_Native_Runtime']==5400.25
    assert value['calls'][0]['effective_TimeLimit']==10
    assert value['calls'][0]['SolCount']==1

def test_quarantined_date_cannot_be_restarted_or_carried_as_zero(tmp_path):
    atomic(tmp_path/'QUARANTINE_V18_DATES.json',dict(dates={'2025-05-02':{}}))
    with pytest.raises(PermissionError,match='QUARANTINE'):
        policy.prior_runtime({},root=tmp_path,day='2025-05-02')
    with pytest.raises(PermissionError,match='QUARANTINED'):
        policy.verify_request(dict(root=str(tmp_path),day='2025-05-02'))

def recovery_receipt(root):
    day='2025-05-02';old=root/'dates/B2'/day/'attempts/old';old.mkdir(parents=True)
    atomic(old/'request.json',dict(day=day,arm='B2'))
    atomic(old/'RESULT.json',dict(identity=dict(day=day,arm='B2'),Native_Runtime=3285.426))
    atomic(old/'ledger.json',dict(inflight=None,calls=[],measured_Native_Runtime=3285.426,prior_attempt=dict(Native_Runtime=3285.426)))
    known=dict(ledger=record(old/'ledger.json'),result=record(old/'RESULT.json'),request=record(old/'request.json'),Native_Runtime=3285.426)
    failed=old.parent/'failed';failed.mkdir()
    atomic(failed/'ledger.json',dict(inflight=None,calls=[],measured_Native_Runtime=3285.426,wall_seconds=404.843))
    atomic(failed/'error.json',dict(error="multiple values for keyword argument 'SolCount'"))
    atomic(failed/'result.json',{});atomic(failed/'progress.json',{})
    atomic(failed/'request.json',dict(day=day,Threads=1))
    history={k:record(failed/(k+'.json')) for k in ('ledger','error','result','progress')}
    history['known_prior_Native_Runtime']=3285.426
    atomic(root/'QUARANTINE_V18_DATES.json',dict(dates={day:history}))
    return dict(budget_basis='CONSERVATIVE_LOST_CALL_WINDOW',user_authorized_restart=True,
        authorized_attempt=policy.ATTEMPT,quarantine=record(root/'QUARANTINE_V18_DATES.json'),
        failed_attempt=history,failed_request=record(failed/'request.json'),known_measured_prior=known,
        lost_call_reserved_seconds=406,Native_Runtime=3691.426,actual_cumulative_Native_Runtime='UNKNOWN')

def test_authorized_conservative_carry_never_resets_or_invents_runtime(tmp_path,monkeypatch):
    receipt=recovery_receipt(tmp_path)
    assert policy.prior_runtime(receipt,root=tmp_path,day='2025-05-02')==3691.426
    monkeypatch.setattr(execution,'current',lambda:dict(request=dict(arm='B2',day='2025-05-02',root=str(tmp_path)),manifest=dict(prior_attempts={'2025-05-02':receipt})))
    budget=b.DateBudget(tmp_path/'new.json',clock=Clock())
    assert budget.remaining()==pytest.approx(1708.574)
    assert budget.snapshot()['Native_Runtime'] is None
    assert json.loads(budget.path.read_text())['measured_Native_Runtime'] is None

@pytest.mark.parametrize('field,value',[('lost_call_reserved_seconds',0),('user_authorized_restart',False),('Native_Runtime',3285.426)])
def test_conservative_receipt_rejects_undercharge_and_missing_authority(tmp_path,field,value):
    receipt=recovery_receipt(tmp_path);receipt[field]=value
    with pytest.raises(PermissionError):policy.prior_runtime(receipt,root=tmp_path,day='2025-05-02')

def test_conservative_receipt_rejects_modified_failed_window(tmp_path):
    receipt=recovery_receipt(tmp_path)
    atomic(receipt['failed_attempt']['ledger']['path'],dict(wall_seconds=1))
    with pytest.raises(PermissionError,match='SHA_DRIFT'):
        policy.prior_runtime(receipt,root=tmp_path,day='2025-05-02')

def test_separate_initialization_benchmark_starts_at_zero(tmp_path,monkeypatch):
    monkeypatch.setattr(execution,'current',lambda:dict(request=dict(arm='B2',day='2025-05-02'),
        manifest=dict(benchmark_initialization_only=True,prior_attempts={})))
    budget=b.DateBudget(tmp_path/'benchmark.json',clock=Clock())
    assert budget.used()==0 and budget.remaining()==5400 and budget.prior_attempt is None

def test_initialization_benchmark_accepts_full_point_without_adaptive(tmp_path,monkeypatch):
    import numpy as np
    from types import SimpleNamespace as NS
    from v42_b2_seed_recovery_v18r2 import benchmark
    from v42_b2_seed_recovery_v18 import m_stage,seed_policy
    from v42_may_campaign_native90 import m_stage as original
    point=np.array([1.,0.,.64])
    case=NS(point=point,output=tmp_path,case_sha='case',identity={'model':'unchanged'})
    monkeypatch.setattr(m_stage,'prepare',lambda *a:case)
    def forbidden(*a):raise AssertionError('Validated LP must skip seed MILP and Adaptive')
    monkeypatch.setattr(seed_policy,'seed_integer',forbidden)
    monkeypatch.setattr(original,'run',forbidden)
    monkeypatch.setattr(original,'_strict_ub',lambda *a:dict(PASS=True,Global_UB=.64,exact_Global_UB='16/25'))
    monkeypatch.setattr(execution,'current',lambda:None)
    budget=b.DateBudget(tmp_path/'ledger.json',clock=Clock())
    value=benchmark.run({},budget,lambda v:None)
    assert value['PASS'] and value['UB']==.64 and value['seed_MILP_calls']==0
    assert not value['Adaptive_entered'] and value['Global_Gap'] is None

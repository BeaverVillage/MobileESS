"""User handoff must not mistake pending, reused or two-minute solves for PASS."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import verify_svr11_b2_first3 as verifier
from v42_pr134_b1.common import atomic,record


@pytest.fixture
def campaign(tmp_path,monkeypatch):
    root=tmp_path/'campaign';days=('2025-05-01','2025-05-02','2025-05-03')
    manifest=dict(execution_SHA='source',algorithm_version='V42_COMMON_MESS_U4_THEN_FULL_MILP_V2')
    monkeypatch.setattr(verifier,'verify',lambda path:manifest)
    monkeypatch.setattr(verifier,'live',lambda peer:False)
    monkeypatch.setattr(verifier,'audit_date',lambda *args:dict(PASS=True,evidence=[]))
    ledger=dict(dates={})
    for day in days:
        attempt=root/'dates/B2'/day/'attempts/attempt_01'
        atomic(attempt/'request.json',dict(retry_starts_from_native_zero=True))
        atomic(attempt/'native.json',dict(inflight=None,calls=[dict(entered_native=True,
            runtime_unavailable=False,Native_Runtime=1800.,effective_TimeLimit=1800.)]))
        science=dict(native_runtime_limit_seconds=1800,error=None,global_gap_certified=False,
            certified_Global_LB=None,certified_gap=None,initial_exact_verified_UB='1',exact_Global_UB='1',
            verified_UB=1.,initial_verified_UB=1.,termination_reason='NATIVE_1800_SECONDS_EXHAUSTED',
            Phase2_started=True,Phase2_calls=1)
        atomic(attempt/'RESULT.json',dict(source_SHA='source',scientific=science,Native_Runtime=1800.,
            request=record(attempt/'request.json'),native_ledgers=[dict(receipt=record(attempt/'native.json'))]))
        ledger['dates']['B2/'+day]=dict(status='PASS',result=str(attempt/'RESULT.json'))
    atomic(root/'CAMPAIGN_LEDGER.json',ledger)
    return root,ledger


def test_first3_require_independent_new_runs_and_full_budget(campaign):
    root,ledger=campaign
    assert verifier.run(root)['PASS'] is True


@pytest.mark.parametrize('failure',['pending','reused','early_runtime','bound_misclassified','ub_regression'])
def test_false_handoff_is_rejected(campaign,failure):
    root,ledger=campaign;row=ledger['dates']['B2/2025-05-01']
    if failure=='pending':row['status']='RUNNING'
    elif failure=='reused':row['reused']=True
    else:
        path=Path(row['result']);result=verifier.read(path)
        if failure=='early_runtime':
            native=path.parent/'native.json';v=verifier.read(native);v['calls'][0]['Native_Runtime']=113.
            atomic(native,v);result['native_ledgers'][0]['receipt']=record(native);result['Native_Runtime']=113.
        elif failure=='bound_misclassified':result['scientific']['certified_Global_LB']=.98
        else:result['scientific']['exact_Global_UB']='2'
        atomic(path,result)
    atomic(root/'CAMPAIGN_LEDGER.json',ledger)
    assert verifier.run(root)['PASS'] is False

"""A queued performance release cannot dispatch while old science runs."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_svr11_epoch13 as handoff
from verify_svr11_handoff37 import audit_date
from v42_pr134_b1.common import atomic,sha

def test_finish_waits_for_healthy_workers(monkeypatch):
    monkeypatch.setattr(handoff,'validate_proof',lambda:None)
    monkeypatch.setattr(handoff,'origin_workers',lambda:[{'PID':1234}])
    monkeypatch.setattr(handoff,'release_exact',lambda:pytest.fail('cannot release during predecessor work'))
    assert handoff.finish() is False

@pytest.mark.parametrize('direct_actual',[True,False])
def test_no_physical_receipts_cannot_be_admitted(tmp_path,direct_actual):
    result=tmp_path/'dates/B0/2025-05-01/attempts/attempt_01/RESULT.json'
    atomic(result,dict(PASS=True,status='PASS',source_SHA='immutable',
        identity=dict(arm='B0',day='2025-05-01',run_id='campaign'),
        Actual_PQ_repair=0,Actual_reoptimization=0,metrics=dict(evidence=[])))
    row=dict(arm='B0',day='2025-05-01',result=str(result),result_SHA=sha(result))
    m=dict(execution_SHA='immutable',run_id='campaign',postoptimization_DayAhead_Fresh_AC=not direct_actual)
    with pytest.raises(ValueError,match='HANDOFF_FROZEN_FRESH_NAMESPACE_CONTRACT'):
        audit_date(tmp_path,m,row)

def test_pending_transition_rejects_other_campaign():
    with pytest.raises(AssertionError):handoff.pending_release(Path('D:/other_campaign'))

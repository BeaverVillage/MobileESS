from pathlib import Path
import pytest
from tools import b1_only_v4 as ops, b1_raw_rejection_audit as check

RESULT=Path(r'D:\v42_b1_only_may_20261012_03\dates\B1\2025-05-01\attempts\attempt_01\RESULT.json')

def test_integrity_and_unknown_implementation_errors_still_block():
    r={'source_global_integrity_block':True,'scientific':{'classification':'IMPLEMENTATION_FAILURE','error':"ValueError('PHASE_I_RAW_REPLAY_FAIL')"}}
    assert ops.blocked_result(r,RESULT)
    assert ops.blocked_result({'scientific':{'classification':'IMPLEMENTATION_FAILURE','error':'UNRELATED_VERIFIER_BUG'}},RESULT)
    assert ops.blocked_result({'scientific':{'classification':'IMPLEMENTATION_FAILURE','error':"ValueError('PHASE_I_RAW_REPLAY_FAIL')"}})

@pytest.mark.skipif(not RESULT.exists(),reason='Requires preserved real Source18r Native canary evidence')
def test_real_native_rejection_audit_never_promotes_or_changes_original_fail():
    before=ops.record(RESULT);result=ops.read(RESULT);proof=check.audit(RESULT)
    assert proof['PASS'] and proof['primal_PASS'] is False and proof['dual_PASS'] is True
    assert proof['exact_witnesses'][0]['exact_violation']>proof['primal_original_tolerance']
    assert proof['additional_Native_calls']==0 and proof['Planning_Freeze_allowed'] is False
    assert ops.record(RESULT)==before and result['PASS'] is False
    assert result['scientific']['classification']=='IMPLEMENTATION_FAILURE'

@pytest.mark.skipif(not RESULT.exists(),reason='Requires preserved real Source18r Native canary evidence')
def test_failed_compiler_and_source_drift_cannot_be_qualified(monkeypatch):
    original_read=check.read
    def damaged_receipt(path):
        v=original_read(path)
        if Path(path).name=='INDEPENDENT_COMPILED_MODEL_VERIFICATION.json':return dict(v,PASS=False)
        return v
    monkeypatch.setattr(check,'read',damaged_receipt)
    with pytest.raises(AssertionError):check.audit(RESULT)
    monkeypatch.setattr(check,'read',original_read)
    monkeypatch.setattr(check,'source_files',lambda:{})
    with pytest.raises(AssertionError):check.audit(RESULT)

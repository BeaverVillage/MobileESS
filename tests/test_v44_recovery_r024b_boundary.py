from pathlib import Path
import pytest
from v44_recovery_r024b.handover import boundary


@pytest.mark.parametrize('status,passed',[('COMPLETE',True),('FAILED',False),('BLOCKED_DEPENDENCY',False)])
def test_handover_accepts_any_natural_terminal_result(tmp_path,monkeypatch,status,passed):
    from v44.common import atomic
    from v44_recovery_r024b import handover
    atomic(tmp_path/'RESULT.json',dict(status=status,PASS=passed))
    monkeypatch.setattr(handover,'alive',lambda identity:False)
    guard=dict(protected_case_root=str(tmp_path),protected_worker={},protected_coordinator={})
    assert boundary(guard,lease={},workers=[])


def test_running_worker_is_protected_even_if_result_exists(tmp_path,monkeypatch):
    from v44.common import atomic
    from v44_recovery_r024b import handover
    atomic(tmp_path/'RESULT.json',dict(status='COMPLETE',PASS=True))
    monkeypatch.setattr(handover,'alive',lambda identity:False)
    guard=dict(protected_case_root=str(tmp_path),protected_worker={},protected_coordinator={})
    assert not boundary(guard,lease={},workers=[{'pid':123}])

import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v44_recovery_r023 import handover


@pytest.mark.parametrize('workers,lease_live,worker_live,coordinator_live,status,expected',[
    ([{'pid':1}],False,False,False,'COMPLETE',False),
    ([],True,False,False,'COMPLETE',False),
    ([],False,True,False,'COMPLETE',False),
    ([],False,False,True,'COMPLETE',False),
    ([],False,False,False,None,False),
    ([],False,False,False,'RUNNING',False),
    ([],False,False,False,'COMPLETE',True),
    ([],False,False,False,'FAILED',True),
])
def test_entire_case_and_natural_exit_are_both_required(tmp_path,workers,lease_live,worker_live,coordinator_live,status,expected):
    guard=dict(protected_case_root=str(tmp_path),protected_worker={'pid':2},protected_coordinator={'pid':3})
    # A finished Actual substage alone must never release the case boundary.
    (tmp_path/'ACTUAL').mkdir();(tmp_path/'ACTUAL/RESULT.json').write_text('{"status":"COMPLETE"}')
    if status:(tmp_path/'RESULT.json').write_text(json.dumps({'status':status}))
    states={1:lease_live,2:worker_live,3:coordinator_live}
    with patch.object(handover,'alive',side_effect=lambda row:states[row['pid']]):
        assert handover.boundary(guard,lease={'pid':1},workers=workers) is expected


def test_new_coordinator_entry_denied_while_protected_case_runs(tmp_path):
    import v44_recovery_r023.operations as ops
    guard={'protected_case_root':str(tmp_path),'protected_worker':{'pid':2},'protected_coordinator':{'pid':3}}
    def read(path):return guard if path.name=='R023_HANDOVER_GUARD.json' else {'pid':1}
    with patch.object(handover,'read',side_effect=read),patch.object(handover,'alive',return_value=False),patch.object(ops,'workers',return_value=[{'pid':2}]):
        with pytest.raises(PermissionError,match='ENTIRE_CASE_NOT_FINISHED'):handover.require_boundary()


def test_live_r023_worker_admitted_under_existing_r023_owner():
    guard={'protected_case_root':'D:/protected'}
    with patch.object(handover,'read',side_effect=[guard,{'pid':1}]),patch.object(handover,'alive',return_value=True),patch('psutil.Process',return_value=SimpleNamespace(cmdline=lambda:['python','-m','v44_recovery_r023.operations','--coordinator'])):
        assert handover.require_boundary() is guard

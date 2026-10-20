from pathlib import Path
from unittest.mock import patch
import inspect
import pytest
from v44_recovery_r041 import preparation as p,operations as op

def test_actual_fence_rejects_every_call():
    with pytest.raises(PermissionError,match='MUST_NEVER_EXECUTE_ACTUAL'):p.deny_actual({},None,None)

def test_missing_static_directory_is_created_before_original_exclusive_dump(tmp_path):
    target=tmp_path/'A1/OUTPUT/STATIC/P1_CLOSED_STATE.pkl.gz';data=b'original bytes'
    def original(path,state):
        with path.open('xb') as f:f.write(state)
    p.dump_with_parent(original,tmp_path)(target,data)
    assert target.read_bytes()==data
    with pytest.raises(FileExistsError):p.dump_with_parent(original,tmp_path)(target,data)

def test_state_dump_cannot_create_parent_in_another_case(tmp_path):
    with pytest.raises(PermissionError,match='OUTSIDE_OWN_CASE'):p.dump_with_parent(lambda *a:None,tmp_path/'own')(tmp_path/'other/file',{})

def test_preparation_install_fences_worker_actual_and_replaces_wall_resume(tmp_path):
    from v44 import worker
    from v44_recovery_r029 import wall_resume
    before=worker.actual
    with p.install(dict(case_root=str(tmp_path))):
        assert worker.actual is p.deny_actual and wall_resume.run is p.reuse_a1_case
        with pytest.raises(PermissionError):worker.actual({},None,None)
    assert worker.actual is before

def test_reused_a1_preparation_contains_no_actual_call():
    body=inspect.getsource(p.reuse_a1_case)
    assert 'prepare_actual(' in body and 'worker.actual(' not in body and 'Actual_started=False' in body

def test_all_actual_process_launches_are_blocked():
    with pytest.raises(PermissionError,match='NO_LAUNCH'):op.launch(Path('any'),'actual')

def test_user_actual_hold_is_unconditional_after_preparation_loop():
    body=inspect.getsource(op.run)
    assert "state['phase']='PRE_ACTUAL_USER_HOLD'" in body
    assert "return\\n" in body

def test_worker_rejects_actual_even_with_other_valid_authority(tmp_path):
    from v44.common import atomic,record
    f=tmp_path/'request.json';a=tmp_path/'auth.json';atomic(a,{})
    atomic(f,dict(R041_authorization=record(a),R041_sources=[],r038_phase='ACTUAL_PARALLEL'))
    with patch.object(op,'AMENDMENT',a),patch.object(op,'authority'),patch.object(op.previous,'authorize'),pytest.raises(PermissionError,match='ONLY_PREPARATION'):op.worker(f)

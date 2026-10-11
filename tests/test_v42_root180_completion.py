"""Root completion must be demonstrated by the actual objective log."""
import importlib.util
from pathlib import Path
import pytest
import hashlib

path=Path(__file__).resolve().parents[1]/'tools/root180_completion.py'
spec=importlib.util.spec_from_file_location('root180_completion',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_complete_objective_root():
    result=module.completion('Root relaxation: objective 5.321e-01, 12 iterations, 180.21 seconds (12 work units)')
    assert result['completed'] and result['completed_seconds']==180.21

@pytest.mark.parametrize('text',[
    'Root relaxation: time limit, 79764 iterations, 532.16 seconds (831.30 work units)',
    'Root relaxation: interrupted, 12 iterations, 180.21 seconds (12 work units)',
    'Root relaxation: infeasible, 12 iterations, 180.21 seconds (12 work units)',
    'Root relaxation: unbounded, 12 iterations, 180.21 seconds (12 work units)',
    'Presolve time: 180.21s',
    'Root relaxation: objective 1, 12 iterations, 180.21 seconds\nRoot relaxation: time limit, 1 iterations, 2 seconds',
])
def test_incomplete_messages_are_not_root_completion(text):
    result=module.completion(text)
    assert not result['completed'] and result['completed_seconds'] is None

def test_time_limit_cannot_release_even_with_reported_pass(tmp_path):
    path=tmp_path/'native.log'
    path.write_text('Root relaxation: time limit, 2 iterations, 120.00 seconds',encoding='utf-8')
    report=dict(PASS=True,root180_validated=True,full=dict(Root_LP_seconds=120,
        native_log=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
    with pytest.raises(PermissionError,match='ROOT_NOT_COMPLETED'):module.require_completed(report)

def test_log_drift_cannot_release(tmp_path):
    path=tmp_path/'native.log';path.write_text('Root relaxation: objective 1, 2 iterations, 180.00 seconds')
    with pytest.raises(PermissionError,match='LOG_BYTE_DRIFT'):
        module.require_completed(dict(full=dict(Root_LP_seconds=180,native_log=dict(path=str(path),sha256='0'*64))))

def test_timer_drift_cannot_release(tmp_path):
    path=tmp_path/'native.log';path.write_text('Root relaxation: objective 1, 2 iterations, 180.00 seconds')
    with pytest.raises(PermissionError,match='TIMER_LOG_DRIFT'):
        module.require_completed(dict(full=dict(Root_LP_seconds=120,
            native_log=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))))

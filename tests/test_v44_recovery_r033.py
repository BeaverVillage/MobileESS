from pathlib import Path
from unittest.mock import patch
import pytest
from v44_recovery_r033 import operations as op


@pytest.mark.parametrize('entry', ['v44_recovery_r029.operations', 'v44_recovery_r030.operations',
                                 'v44_recovery_r031.operations', 'v44_recovery_r032.operations'])
def test_dispatch_changes_entry_without_changing_worker_request(entry):
    original = ['python', '-u', '-m', entry, '--worker', 'sealed_request.json']
    result = op.command(original)
    assert result[3] == op.ENTRY
    assert result[4:6] == ['--worker', 'sealed_request.json']
    assert original[3] == entry
    assert result[-2:] == ['--algorithm', op.ALGORITHM]


def test_other_subprocess_commands_are_preserved():
    args = ['python', '-u', '-m', 'other_module', '--worker', 'request']
    assert op.command(args) == args


def test_running_worker_always_prevents_handover():
    with patch.object(op.base, 'workers', return_value=[{'pid': 42}]), patch.object(op, 'read') as read:
        assert not op.ready()
        read.assert_not_called()


def test_live_coordinator_without_worker_also_prevents_handover():
    with patch.object(op.base, 'workers', return_value=[]), patch.object(op, 'read', return_value={'pid': 2}), patch.object(op, 'alive', return_value=True):
        assert not op.ready()


def test_r033_sources_include_encoder_outside_package():
    assert any(Path(row['path']).name == 'v44_actual_audit_encoding.py' for row in op.sources())


def test_inherited_request_authorization_and_parent_guards_are_preserved():
    def record(path):
        return {'path': str(path)}
    valid = dict(R032_CC4_date_repair=record(op.previous.AMENDMENT),
                 R033_exact_audit_encoding=record(op.AMENDMENT),
                 fresh_a2_parent=str(op.previous.PARENT))
    with patch.object(op.previous.model, 'authorize') as inherited, patch.object(op, 'record', record):
        op.authorize(valid)
        inherited.assert_called_once_with(valid)
        with pytest.raises(PermissionError, match='CC4_AUTHORIZATION'):
            op.authorize(dict(valid, R032_CC4_date_repair=None))
        with pytest.raises(PermissionError, match='EXACT_M1_PARENT'):
            op.authorize(dict(valid, fresh_a2_parent='D:/wrong_parent'))
        with pytest.raises(PermissionError, match='ENCODING_AUTHORIZATION'):
            op.authorize(dict(valid, R033_exact_audit_encoding=None))


def test_encoder_installation_restores_previous_runtime_on_exit():
    from v44_recovery_r029 import current_ac_performance as module
    original = module.ExactAuditEncoding
    with op.install():
        assert module.ExactAuditEncoding is op.ExactImmutableEncoding
    assert module.ExactAuditEncoding is original

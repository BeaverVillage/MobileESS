from pathlib import Path
from unittest.mock import patch
import pytest
from v44_recovery_r034 import operations as op


@pytest.mark.parametrize('n',range(29,34))
def test_dispatch_preserves_arguments(n):
    args=['python','-u','-m',f'v44_recovery_r{n:03d}.operations','--worker','sealed_request.json']
    result=op.command(args)
    assert result[3]==op.ENTRY
    assert result[4:6]==args[4:6]
    assert result[-2:]==['--algorithm',op.ALGORITHM]


def test_authorization_delegates_all_inherited_guards():
    with patch.object(op.previous,'authorize') as inherited,patch.object(op,'record',return_value={'seal':1}):
        request={'R034_lightweight_audit':{'seal':1}}
        op.authorize(request);inherited.assert_called_once_with(request)
        with pytest.raises(PermissionError,match='LIGHTWEIGHT_AUTHORIZATION'):
            op.authorize({})


def test_running_worker_blocks_handover():
    with patch.object(op.base,'workers',return_value=[{'pid':42}]):assert not op.ready()


def test_install_preserves_encoder_and_restores_hooks():
    from v44_recovery_r029 import history,current_ac_performance as perf
    from v44_actual_audit_encoding import ExactImmutableEncoding
    original=(history.scope,perf.bank_reader,perf.ExactAuditEncoding)
    with op.install():
        assert history.scope is not original[0] and perf.bank_reader is not original[1]
        assert perf.ExactAuditEncoding is ExactImmutableEncoding
    assert (history.scope,perf.bank_reader,perf.ExactAuditEncoding)==original


def test_seals_include_every_active_helper():
    names={Path(row['path']).name for row in op.sources()}
    assert {'v44_actual_bank_gate.py','v44_actual_control_key.py'}<=names
    assert 'v44_actual_audit_light.py' not in names

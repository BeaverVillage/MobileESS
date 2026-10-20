from unittest.mock import patch
import pytest
from v44_recovery_r037 import operations as op

def test_explicit_user_review_hold_always_blocks_dispatch(tmp_path):
    (tmp_path/'STOP_AUTONOMY.json').write_text('{"user_dispatch_pause":true}')
    with patch.object(op,'OPS',tmp_path):
        with pytest.raises(PermissionError,match='NO_DISPATCH'):op.require_user_resume()

def test_authorization_keeps_every_inherited_guard():
    with patch.object(op.previous,'authorize') as inherited,patch.object(op,'record',return_value={'seal':1}):
        request={'R037_row_shared_storage':{'seal':1}};op.authorize(request);inherited.assert_called_once_with(request)
        with pytest.raises(PermissionError):op.authorize({})

def test_removing_stop_file_alone_cannot_override_user_review_pause(tmp_path):
    (tmp_path/'USER_STORAGE_REVIEW_AUTHORIZATION.json').write_text('{}')
    with patch.object(op,'OPS',tmp_path):
        with pytest.raises(PermissionError,match='EXPLICIT_USER_RESUME'):op.require_user_resume()

def test_writer_installation_is_lazy_and_restores_all_hooks(tmp_path):
    from v44_recovery_r029 import current_ac_performance as p
    original=p.audit_writer
    with patch.object(op,'RAW_ROOT',tmp_path):
        with op.install():
            assert p.audit_writer is not original
            assert not (tmp_path/'RAW_CHUNKS_V1').exists()
    assert p.audit_writer is original

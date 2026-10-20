from pathlib import Path
from unittest.mock import patch
import json
import pytest
from v44_recovery_r035 import operations as op

@pytest.mark.parametrize('n',range(29,35))
def test_dispatch_keeps_worker_input(n):
    args=['python','-u','-m',f'v44_recovery_r{n:03d}.operations','--worker','sealed.json']
    result=op.command(args)
    assert result[3]==op.ENTRY and result[4:6]==args[4:6]

def test_live_worker_forbids_cleanup_before_even_reading_case():
    with patch.object(op,'ready',return_value=False),patch.object(op,'read') as read,patch.object(op,'cleanup_raw') as cleanup:
        with pytest.raises(PermissionError,match='LIVE_WORKER_FORBIDDEN'):op.cleanup_after_case()
        read.assert_not_called();cleanup.assert_not_called()

def test_nonterminal_case_cannot_start_cleanup():
    with patch.object(op,'ready',return_value=True),patch.object(op,'read',return_value={'stage':'ACTUAL'}),patch.object(op,'cleanup_raw') as cleanup:
        with pytest.raises(PermissionError,match='TERMINAL_RESULT_REQUIRED'):op.cleanup_after_case()
        cleanup.assert_not_called()

def test_completed_boundary_runs_cleanup_once_and_preserves_receipt(tmp_path):
    case=tmp_path/'case';ops=tmp_path/'ops';case.mkdir();ops.mkdir()
    (case/'RESULT.json').write_text(json.dumps({'PASS':True}))
    with patch.object(op,'ready',return_value=True),patch.object(op,'CLEANUP_CASE',case),patch.object(op,'OPS',ops),patch.object(op,'cleanup_raw',return_value={'PASS':True,'shared_files':4}) as cleanup:
        result=op.cleanup_after_case();assert result['unique_raw_records_deleted']==0
        assert op.cleanup_after_case()==result
        cleanup.assert_called_once()

def test_authorization_and_lazy_installation_preserve_inherited_guards(tmp_path):
    from v44_recovery_r029 import current_ac_performance as p
    from v44_actual_record_light import SharedControlEncoding
    original=p.audit_writer
    with patch.object(op.previous,'authorize') as inherited,patch.object(op,'record',return_value={'seal':1}):
        request={'R035_exact_storage':{'seal':1}};op.authorize(request);inherited.assert_called_once_with(request)
        with pytest.raises(PermissionError):op.authorize({})
    with patch.object(op,'RAW_ROOT',tmp_path):
        with op.install():
            assert p.ExactAuditEncoding is SharedControlEncoding and p.audit_writer is not original
            assert not (tmp_path/'EXACT_RAW_CONTENT.sqlite3').exists()
    assert p.audit_writer is original

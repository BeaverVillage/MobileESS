from unittest.mock import patch
import pytest
import v44_storage_review_hold as hold

def test_live_case_never_starts_cleanup_or_scheduler():
    with patch.object(hold,'held',return_value=True),patch.object(hold.op,'ready',return_value=False),patch.object(hold.op.previous,'cleanup_after_case') as cleanup,patch.object(hold.op.base,'watchdog') as scheduler:
        assert hold.step()=='WAITING_FOR_MAY02_B3_AND_FRESH'
        cleanup.assert_not_called();scheduler.assert_not_called()

def test_changed_user_control_is_preserved():
    with patch.object(hold,'held',return_value=False),patch.object(hold.op,'ready') as ready:
        assert hold.step()=='OTHER_CONTROL_PRESERVED';ready.assert_not_called()

def test_terminal_cleanup_retains_dispatch_hold_and_never_calls_scheduler(tmp_path):
    case=tmp_path/'case';case.mkdir();(case/'RESULT.json').write_text('{"PASS":true}')
    ops=tmp_path/'ops';ops.mkdir();(ops/'R035_EXISTING_RAW_CLEANUP.json').write_text('{"PASS":true}')
    with patch.object(hold,'held',return_value=True),patch.object(hold.op,'ready',return_value=True),patch.object(hold.op,'CLEANUP_CASE',case),patch.object(hold.op,'OPS',ops),patch.object(hold.op.previous,'cleanup_after_case',return_value={'PASS':True}),patch.object(hold.op.base,'watchdog') as scheduler:
        assert hold.step()=='CLEANED_WAITING_FOR_EXPLICIT_USER_RESUME'
        assert (ops/'USER_STORAGE_REVIEW_CLEANUP_COMPLETE.json').exists()
        scheduler.assert_not_called()

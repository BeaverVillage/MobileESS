from unittest.mock import patch
import pytest
import v44_recovery_r048a as fix


def test_reference_original_captured_before_runtime_patch():
    from v43_arms import reference
    original=fix.reference_helper._original_project
    assert original is not fix.op.project
    with patch.object(reference,'project',fix.op.project):
        assert fix.reference_helper._original_project is original
        assert fix.reference_helper._original_project is not reference.project


def test_new_request_compilation_contains_new_attempt_and_fix_sources():
    fn=fix.request_function()
    assert '_r048a_root' in fn.__code__.co_names
    assert 'R048a_authorization' in fn.__code__.co_consts


def test_continuation_retains_original_month_and_main_queue_loop():
    fn=fix.continuation()
    assert 'acquire_main' in fn.__code__.co_names
    assert 'collect' in fn.__code__.co_names
    assert 'publish' in fn.__code__.co_names


def test_fix_authority_is_mandatory():
    with patch.object(fix,'authority',return_value={}),patch.object(fix,'record',return_value={'path':'fix'}),pytest.raises(PermissionError):
        fix.authorize_case(dict(arm='B0'))

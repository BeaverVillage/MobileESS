"""Equivalent cache migration cannot turn physical FAIL into a lucky rerun."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from preserve_svr11_terminal_failures import retry_technical

@pytest.mark.parametrize('result,attempts,expected',[
    ({'retryable_technical_error':True},['old'],True),
    ({'retryable_pre_native_technical_error':True},['old'],True),
    ({'retryable_technical_error':True,'physical_failures':[{'reason':'VOLTAGE_VIOLATION'}]},['old'],False),
    ({'retryable_technical_error':True,'source_global_integrity_block':True},['old'],False),
    ({'retryable_technical_error':True},['one','two','three'],False),
    ({'optimization_status':'TIME_LIMIT_FEASIBLE_ACCEPTED'},['old'],False),
    ({'physical_failures':[{'reason':'OVERLOAD'}]},['old'],False),
])
def test_bounded_technical_only_recovery(result,attempts,expected):
    assert retry_technical(result,attempts)==expected

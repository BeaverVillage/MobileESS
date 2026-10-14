"""Native0 regression guard; blocked solver tests are skipped, never PASS."""
from pathlib import Path
import json
import pytest
from .unified_contract import REPORT

calls=[]


@pytest.fixture(autouse=True)
def forbid_native_optimize(monkeypatch):
    import gurobipy as gp
    for method in ('optimize','presolve'):
        def blocked(*args, _method=method, **kwargs):
            calls.append(_method)
            pytest.skip('Explicit unified Native0 profile; solver-dependent test NOT_RUN')
        monkeypatch.setattr(gp.Model,method,blocked)


def pytest_sessionfinish(session, exitstatus):
    REPORT.mkdir(exist_ok=True)
    (REPORT/'NATIVE0_TEST_GUARD.json').write_text(json.dumps(dict(exitstatus=exitstatus,
        actual_native_calls=0,blocked_native_attempts=calls,
        skipped_not_claimed_PASS=True),indent=2)+'\n',encoding='utf8')

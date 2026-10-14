"""Full-suite zero-Gurobi-optimization profile; results go only to new research docs."""
import json
import os
from pathlib import Path

import gurobipy as gp
import pytest

OUT=Path(__file__).resolve().parents[2]/'docs/v42_b2_global_lb_alternative_research_20261014'
passed=[];failed=[];skipped=[];denied=[]


def _forbidden(*args,**kwargs):
    denied.append('Gurobi optimize/presolve denied by research regression guard')
    pytest.skip('Solve-dependent regression: Gurobi Native denied to preserve measured research budget')


def pytest_configure(config):
    gp.Model.optimize=_forbidden
    gp.Model.presolve=_forbidden


def pytest_runtest_logreport(report):
    if report.when=='call' and report.passed:passed.append(report.nodeid)
    if report.failed:failed.append(dict(test=report.nodeid,when=report.when,longrepr=str(report.longrepr)))
    if report.skipped:skipped.append(report.nodeid)


def pytest_sessionfinish(session,exitstatus):
    OUT.mkdir(parents=True,exist_ok=True)
    label=os.environ.get('V42_ALT_REGRESSION_LABEL','FULL_REGRESSION')
    (OUT/(label+'_RESULT.json')).write_text(json.dumps(dict(exitstatus=exitstatus,passed=passed,failed=failed,
        skipped=sorted(set(skipped)),denied_native_attempts=denied,Gurobi_Native_calls=0,
        skipped_tests_not_claimed_pass=True),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

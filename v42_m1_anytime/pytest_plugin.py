"""Separate new-run regression receipt; actual Native calls are forbidden."""
import os
from pathlib import Path
import pytest
import gurobipy as gp
from .core import write,REPORTS
passed=[];skipped=[];failed=[];originals={};denied=[]
def pytest_runtest_setup(item):
    for name in ('optimize','presolve'):
        originals[name]=getattr(gp.Model,name)
        def forbidden(*args,_test=item.nodeid,_method=name,**kwargs):
            denied.append(dict(test=_test,method=_method));pytest.skip('Anytime regression Native=0')
        setattr(gp.Model,name,forbidden)
def pytest_runtest_teardown(item,nextitem):
    for name,method in originals.items():setattr(gp.Model,name,method)
def pytest_runtest_logreport(report):
    if report.when=='call' and report.passed:passed.append(report.nodeid)
    if report.skipped:skipped.append(report.nodeid)
    if report.failed:failed.append(dict(test=report.nodeid,when=report.when))
def pytest_sessionfinish(session,exitstatus):
    write(Path(os.environ.get('V42_ANYTIME_TEST_REPORT',str(REPORTS/'PRE_NATIVE_REGRESSION.json'))),
        dict(PASS=exitstatus==0,passed=passed,skipped=sorted(set(skipped)),failed=failed,Native_optimize_calls=0,denied=denied,SKIP_not_PASS=True))

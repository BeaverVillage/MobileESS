"""Replay the PR189 required test IDs under an optimize-denying scope."""
import pytest
import argparse
from .common import *

def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--attempt',default='002')
    parser.add_argument('--failed-only',action='store_true')
    options=parser.parse_args()
    from v42_may_campaign_native90.preflight import native_zero
    authority=HIST.parents[3]/'candidate_20261009_implementation01/EXISTING_ZERO_NATIVE_REGRESSION.json'
    # HIST: campaign / dates / B1 / day. Inputs authority is its sibling.
    authority=Path('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/EXISTING_ZERO_NATIVE_REGRESSION.json')
    nodes=read(authority)['passed']
    if options.failed_only:nodes=[r['test'] for r in read(DOC/'REQUIRED_REGRESSION001.json')['failed']]
    class Results:
        def __init__(self): self.passed=[];self.failed=[]
        def pytest_runtest_logreport(self,report):
            if report.when=='call' and report.passed:self.passed.append(report.nodeid)
            if report.failed:self.failed.append(dict(test=report.nodeid,when=report.when,error=str(report.longrepr)))
    results=Results()
    args=nodes+['tests/test_v42_native90_policy.py','tests/test_v42_native90_coordinator.py',
        'tests/test_v42_campaign_monitor.py','tests/test_v42_native90_maintenance.py',
        '-q','--tb=short','--basetemp',str(ROOT/'runtime/v43_test_temp'/('required'+options.attempt)),
        '--junitxml',str(DOC/('REQUIRED_REGRESSION'+options.attempt+'.xml'))]
    with native_zero() as attempts:
        code=pytest.main(args,plugins=[results])
    missing=sorted(set(nodes)-set(results.passed))
    atomic(DOC/('REQUIRED_REGRESSION'+options.attempt+'.json'),dict(PASS=code==0 and not attempts and not missing,
        passed=len(results.passed),historical_required_passes=len(nodes),failed=results.failed,
        historical_missing=missing,Native_calls=0,denied_optimize_attempts=attempts,authority=record(authority),UTC=now()))
    raise SystemExit(code)

if __name__=='__main__':run()

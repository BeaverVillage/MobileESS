import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pytest
from v42_may_campaign_native90.preflight import native_zero
from v42_may_campaign_native90.common import atomic,now
root=Path(r'D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01')
old=root.parent/'candidate_20261009_implementation01'
prior=json.loads((old/'EXISTING_ZERO_NATIVE_REGRESSION.json').read_text(encoding='utf-8-sig'))
nodes=prior['passed']
class Results:
 def __init__(self):self.passed=[];self.failed=[];self.errors=[]
 def pytest_runtest_logreport(self,report):
  if report.when=='call' and report.passed:self.passed.append(report.nodeid)
  if report.failed:self.failed.append(dict(test=report.nodeid,when=report.when,error=str(report.longrepr)))
results=Results()
with native_zero() as attempts:
 code=pytest.main(nodes+['tests/test_v42_native90_policy.py','tests/test_v42_native90_coordinator.py','tests/test_v42_campaign_monitor.py','tests/test_v42_native90_maintenance.py','-q',
   '--basetemp',str(root/'validation/pytest_required'), '--junitxml',str(root/'validation/REQUIRED_REGRESSION_JUNIT.xml')],plugins=[results])
missing=sorted(set(nodes)-set(results.passed))
atomic(root/'validation/REQUIRED_REGRESSION.json',dict(PASS=code==0 and not attempts and not missing,
 passed=len(results.passed),historical_required_passes=len(nodes),failed=results.failed,historical_missing=missing,
 Native_calls=0,denied_optimize_attempts=attempts,UTC=now()))
raise SystemExit(code)

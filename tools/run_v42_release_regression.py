"""Run every frozen 640 test ID plus release repairs with Native forbidden."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASE='490ff3ef7821705fc82c3823242d79093eb480b9'
OLD='docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015/REGRESSION_FINAL/REGRESSION_TESTS.xml'
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/REGRESSION'


def main():
    if OUT.exists():raise FileExistsError('RELEASE_REGRESSION_RECEIPT_MUST_NOT_OVERWRITE')
    OUT.mkdir(parents=True)
    raw=subprocess.check_output(['git','show',BASE+':'+OLD],cwd=ROOT)
    nodes=[r.attrib['classname'].replace('.','/')+'.py::'+r.attrib['name'] for r in ET.fromstring(raw).iter('testcase')]
    assert len(nodes)==len(set(nodes))==640
    new=['tests/test_v42_release_actual.py','tests/test_v42_release_budget.py',
        'tests/test_v42_release_campaign.py','tests/test_v42_release_preservation.py']
    assert all((ROOT/n).is_file() for n in new)
    import pytest
    attempts=[]
    class Guard:
        @pytest.fixture(autouse=True)
        def no_native(self,monkeypatch):
            import gurobipy as gp
            for method in ('optimize','presolve','computeIIS'):
                def blocked(*args,_method=method,**kwargs):
                    attempts.append(_method);pytest.fail('RELEASE_REGRESSION_NATIVE_FORBIDDEN:'+_method)
                monkeypatch.setattr(gp.Model,method,blocked)
    start=time.perf_counter()
    code=int(pytest.main(['-q','-p','no:cacheprovider','--junitxml='+str(OUT/'TESTS.xml'),*nodes,*new],plugins=[Guard()]))
    tests=list(ET.parse(OUT/'TESTS.xml').getroot().iter('testcase'))
    failures=[r.attrib for r in tests if r.find('failure') is not None or r.find('error') is not None]
    skipped=[r.attrib for r in tests if r.find('skipped') is not None]
    result=dict(status='PASS' if not(code or failures or skipped or attempts) else 'FAIL',baseline_IDs_preserved=640,
        baseline_XML_SHA=hashlib.sha256(raw).hexdigest(),tests=len(tests),new_tests=len(tests)-640,
        failures=failures,skipped=skipped,blocked_native_attempts=attempts,Native_calls=0,wall_seconds=time.perf_counter()-start)
    (OUT/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result,indent=2));return code


if __name__=='__main__':raise SystemExit(main())

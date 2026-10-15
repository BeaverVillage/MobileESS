"""Preserve all 624 prior test IDs; forbid new Gurobi native entrypoints."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASE='89b4ee6b63ca7847dd6f2cbd2720052f66949d39'
OLD='docs/v42_unified_aidc_mess_research_20261014/D0_STATE_CONDITIONED_PLANNING_20261015/REGRESSION01/REGRESSION_TESTS.xml'
REPORT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/ISOLATED_UNKNOWN_C0_C1_20261015'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args();out=REPORT/('BASELINE624' if args.baseline else 'REGRESSION_FINAL')
    if out.exists():raise FileExistsError('ISOLATED_REGRESSION_OUTPUT_MUST_NOT_BE_OVERWRITTEN')
    out.mkdir(parents=True)
    raw=subprocess.check_output(['git','show',BASE+':'+OLD],cwd=ROOT)
    nodes=[r.attrib['classname'].replace('.','/')+'.py::'+r.attrib['name'] for r in ET.fromstring(raw).iter('testcase')]
    assert len(nodes)==len(set(nodes))==624
    new=[] if args.baseline else ['tests/test_v42_isolated_unknown.py',
        'tests/test_v42_isolated_frozen_tracks_audit.py']
    import pytest
    attempts=[]
    class Guard:
        @pytest.fixture(autouse=True)
        def forbid_native(self,monkeypatch):
            import gurobipy as gp
            for method in ('optimize','presolve','computeIIS'):
                def blocked(*args,_method=method,**kwargs):
                    attempts.append(_method);pytest.fail('ISOLATED_NO_NATIVE:'+_method)
                monkeypatch.setattr(gp.Model,method,blocked)
    began=time.perf_counter()
    code=int(pytest.main(['-q','-p','no:cacheprovider','--junitxml='+str(out/'REGRESSION_TESTS.xml'),*nodes,*new],plugins=[Guard()]))
    actual=list(ET.parse(out/'REGRESSION_TESTS.xml').getroot().iter('testcase'))
    failures=[r.attrib for r in actual if r.find('failure') is not None or r.find('error') is not None]
    skipped=[r.attrib for r in actual if r.find('skipped') is not None]
    result=dict(status='PASS' if code==0 and not failures and not skipped and not attempts else 'FAIL',
        baseline_commit=BASE,baseline_IDs_preserved=624,total=len(actual),new_tests=len(actual)-624,
        passed=len(actual)-len(failures)-len(skipped),failures=failures,skipped=skipped,
        Gurobi_Native_calls=0,blocked_attempts=attempts,wall_seconds=time.perf_counter()-began,
        baseline_XML_SHA=hashlib.sha256(raw).hexdigest(),exitstatus=code)
    (out/'REGRESSION_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2));return code


if __name__=='__main__':raise SystemExit(main())

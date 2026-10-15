"""Preserve the exact 555 baseline IDs and forbid native calls in all new tests."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
COMMIT='4624039ca376db7aeae1e08709441d545b350eeb'
SOURCE='docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP/RECOVERY_01/REGRESSION_TESTS.xml'
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/D0_STATE_CONDITIONED_PLANNING_20261015/REGRESSION01'


def main():
    if OUT.exists():raise FileExistsError('D0_REGRESSION_RECEIPT_MUST_NOT_BE_OVERWRITTEN')
    OUT.mkdir(parents=True)
    raw=subprocess.check_output(['git','show',COMMIT+':'+SOURCE],cwd=ROOT)
    nodes=[r.attrib['classname'].replace('.','/')+'.py::'+r.attrib['name']
        for r in ET.fromstring(raw).iter('testcase')]
    assert len(nodes)==len(set(nodes))==555
    new=['tests/test_v42_d0_a_planning.py','tests/test_v42_d0_supervisor.py',
        'tests/test_v42_d0_actual_inputs.py','tests/test_v42_mess_root_diagnosis.py',
        'tests/test_v42_mess_minimax_lookahead.py']
    if any(not (ROOT/p).is_file() for p in new):raise FileNotFoundError('D0_ALL_NEW_TEST_MODULES_REQUIRED')
    (OUT/'EXACT_BASELINE555_NODE_IDS.json').write_text(json.dumps(nodes,indent=2)+'\n',encoding='utf8')
    import pytest
    attempts=[]
    class Guard:
        @pytest.fixture(autouse=True)
        def forbid_native(self,monkeypatch):
            import gurobipy as gp
            for method in ('optimize','presolve','computeIIS'):
                def blocked(*args,_method=method,**kwargs):
                    attempts.append(_method);pytest.fail('D0_NATIVE0_FORBIDDEN:'+_method)
                monkeypatch.setattr(gp.Model,method,blocked)
    began=time.perf_counter()
    code=int(pytest.main(['-q','-p','no:cacheprovider','--junitxml='+str(OUT/'REGRESSION_TESTS.xml'),
        *nodes,*new],plugins=[Guard()]))
    actual=list(ET.parse(OUT/'REGRESSION_TESTS.xml').getroot().iter('testcase'))
    failed=[c.attrib for c in actual if c.find('failure') is not None or c.find('error') is not None]
    skipped=[c.attrib for c in actual if c.find('skipped') is not None]
    result=dict(status='PASS' if code==0 and not failed and not skipped and not attempts else 'FAIL',
        baseline_commit=COMMIT,baseline_tests=555,baseline_node_IDs_preserved=True,
        new_tests=len(actual)-555,total=len(actual),passed=len(actual)-len(failed)-len(skipped),
        failed=failed,skipped=skipped,actual_native_calls=0,blocked_attempts=attempts,
        exitstatus=code,wall_seconds=time.perf_counter()-began,
        exact_baseline_xml_sha256=hashlib.sha256(raw).hexdigest(),
        test_source_modules=new,old_tests_changed=False,old_outputs_overwritten=False)
    (OUT/'REGRESSION_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2));return code


if __name__=='__main__':raise SystemExit(main())

"""Exact PR230 baseline 451 plus meaningful resumed contract/physics tests."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from time import perf_counter
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = '22c644b10a1bfae344cfb86274262719bbe5f412'
NEW_TESTS = ('tests/test_v42_aidc_followup.py', 'tests/test_v42_followup_contract.py',
             'tests/test_v42_mess_joint_compression.py', 'tests/test_v42_mess_beam_diversity.py',
             'tests/test_v42_mess_mode_hull.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
        default=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP')
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    xml = 'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_REGRESSION_TESTS.xml'
    raw = subprocess.check_output(['git','show',BASE+':'+xml],cwd=ROOT)
    nodes = [r.attrib['classname'].replace('.','/')+'.py::'+r.attrib['name']
             for r in ET.fromstring(raw).iter('testcase')]
    if len(nodes) != 451 or len(set(nodes)) != 451:
        raise ValueError('EXACT_ORIGINAL_451_REGRESSION_BASELINE_REQUIRED')
    if any(not (ROOT/name).is_file() for name in NEW_TESTS):
        raise ValueError('FOLLOWUP_NEW_REGRESSION_MODULE_MISSING')
    import pytest
    attempts = []
    class Native0:
        @pytest.fixture(autouse=True)
        def forbid_native(self, monkeypatch):
            import gurobipy as gp
            for method in ('optimize','presolve','computeIIS'):
                def forbidden(*a, _method=method, **kw):
                    attempts.append(_method)
                    pytest.fail('FOLLOWUP_NATIVE0_FORBIDDEN_SOLVER_CALL:'+_method)
                monkeypatch.setattr(gp.Model,method,forbidden)
    started=perf_counter()
    status=int(pytest.main(['-q','-p','no:cacheprovider',
        '--junitxml='+str(out/'UNIFIED_REGRESSION_TESTS.xml'),*nodes,*NEW_TESTS],plugins=[Native0()]))
    cases=list(ET.parse(out/'UNIFIED_REGRESSION_TESTS.xml').getroot().iter('testcase'))
    failed=[r.attrib for r in cases if r.find('failure') is not None or r.find('error') is not None]
    skipped=[r.attrib for r in cases if r.find('skipped') is not None]
    baseline_keys={(r.attrib['classname'],r.attrib['name']) for r in ET.fromstring(raw).iter('testcase')}
    observed_keys={(r.attrib['classname'],r.attrib['name']) for r in cases}
    result=dict(status='PASS' if status==0 and not failed and not skipped and not attempts and
        baseline_keys.issubset(observed_keys) else 'FAIL', baseline_commit=BASE,
        baseline_tests_preserved=baseline_keys.issubset(observed_keys),baseline_count=451,
        total=len(cases),passed=len(cases)-len(failed)-len(skipped),failed=failed,skipped=skipped,
        added_tests=len(cases)-451,actual_native_calls=0,blocked_native_attempts=attempts,
        wall_seconds=perf_counter()-started,original_baseline_xml_sha=hashlib.sha256(raw).hexdigest(),
        new_test_modules=list(NEW_TESTS),command='python -B -X utf8 tools/run_v42_followup_regression.py')
    (out/'UNIFIED_REGRESSION_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2),flush=True)
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':
    main()

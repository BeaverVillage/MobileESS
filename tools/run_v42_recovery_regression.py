"""Preserve all 522 PR230 tests, adding boundary recovery Native0 checks."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from time import perf_counter
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASE='20324fd7144866cdcfaf0831511b4e35ac1f8ea8'
NEW_TESTS=('tests/test_v42_recovery_source_contract.py',
    'tests/test_v42_may01_boundary_reconciliation.py',
    'tests/test_v42_mess_verified_packet_cache.py','tests/test_v42_mess_s1_research.py')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,
        default=ROOT/'docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP/RECOVERY_01')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    original='docs/v42_unified_aidc_mess_research_20261014/FOLLOWUP/UNIFIED_REGRESSION_TESTS.xml'
    raw=subprocess.check_output(['git','show',BASE+':'+original],cwd=ROOT)
    baseline=list(ET.fromstring(raw).iter('testcase'))
    nodes=[r.attrib['classname'].replace('.','/')+'.py::'+r.attrib['name'] for r in baseline]
    if len(nodes)!=522 or len(set(nodes))!=522:
        raise ValueError('EXACT_ORIGINAL_522_REGRESSION_BASELINE_REQUIRED')
    if any(not(ROOT/name).is_file() for name in NEW_TESTS):
        raise ValueError('RECOVERY_NEW_REGRESSION_MODULE_MISSING')
    import pytest
    attempts=[]
    class Native0:
        @pytest.fixture(autouse=True)
        def prohibit_native(self,monkeypatch):
            import gurobipy as gp
            for method in ('optimize','presolve','computeIIS'):
                def forbidden(*a,_method=method,**kw):
                    attempts.append(_method)
                    pytest.fail('RECOVERY_NATIVE0_FORBIDDEN_SOLVER_CALL:'+_method)
                monkeypatch.setattr(gp.Model,method,forbidden)
    began=perf_counter()
    code=pytest.main(['-q','-p','no:cacheprovider','--junitxml='+str(out/'REGRESSION_TESTS.xml'),
        *nodes,*NEW_TESTS],plugins=[Native0()])
    cases=list(ET.parse(out/'REGRESSION_TESTS.xml').getroot().iter('testcase'))
    failed=[r.attrib for r in cases if r.find('failure') is not None or r.find('error') is not None]
    skipped=[r.attrib for r in cases if r.find('skipped') is not None]
    keys={(r.attrib['classname'],r.attrib['name']) for r in cases}
    retained={(r.attrib['classname'],r.attrib['name']) for r in baseline}<=keys
    result=dict(status='PASS' if code==0 and not failed and not skipped and not attempts and retained else 'FAIL',
        baseline_commit=BASE,baseline_count=522,baseline_tests_preserved=retained,
        total=len(cases),passed=len(cases)-len(failed)-len(skipped),failed=failed,skipped=skipped,
        added_tests=len(cases)-522,actual_native_calls=0,blocked_native_attempts=attempts,
        wall_seconds=perf_counter()-began,baseline_xml_sha=hashlib.sha256(raw).hexdigest(),
        new_test_modules=list(NEW_TESTS),prior_outputs_overwritten=False)
    (out/'REGRESSION_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2),flush=True)
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':
    main()

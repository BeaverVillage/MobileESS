"""Preserve all 682 committed RC01 test IDs and add RC02/RC03 checks."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASE='6a12d503a'
OLD='docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/REGRESSION/TESTS.xml'
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC03/REGRESSION'


def main():
    if OUT.exists():raise FileExistsError('REGRESSION_RECEIPT_MUST_NOT_OVERWRITE')
    OUT.mkdir(parents=True)
    raw=subprocess.check_output(['git','show',BASE+':'+OLD],cwd=ROOT)
    nodes=[r.attrib['classname'].replace('.','/')+'.py::'+r.attrib['name'] for r in ET.fromstring(raw).iter('testcase')]
    assert len(nodes)==len(set(nodes))==682
    old_files={n.split('::')[0] for n in nodes}
    new=[]
    for pattern in ('test_v42_release_*.py','test_v42_rc02_*.py','test_v42_research_presite_*.py'):
        new.extend(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob(pattern)
                   if p.relative_to(ROOT).as_posix() not in old_files)
    new=sorted(set(new));assert new
    import pytest
    attempts=[]
    import gurobipy as gp
    originals={name:getattr(gp.Model,name) for name in ('optimize','presolve','computeIIS')}
    def forbid_collection(*args,**kwargs):
        attempts.append('COLLECTION_OR_CAPTURED_NATIVE');pytest.fail('RC03_ACTUAL_NATIVE_FORBIDDEN_BEFORE_COLLECTION')
    # Install before collection as well as per test: an imported module must
    # not capture a real native entrypoint before the autouse fixture runs.
    for name in originals:setattr(gp.Model,name,forbid_collection)
    ledger_paths=[ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json',
        ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json']
    before=[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in ledger_paths]
    class Guard:
        @pytest.fixture(autouse=True)
        def actual_native_forbidden(self,monkeypatch):
            import gurobipy as gp
            for method in ('optimize','presolve','computeIIS'):
                def forbidden(*args,_method=method,**kwargs):
                    attempts.append(_method);pytest.fail('RC03_ACTUAL_NATIVE_FORBIDDEN:'+_method)
                monkeypatch.setattr(gp.Model,method,forbidden)
    began=time.perf_counter()
    try:
        code=int(pytest.main(['-q','-p','no:cacheprovider','--junitxml='+str(OUT/'TESTS.xml'),*nodes,*new],plugins=[Guard()]))
    finally:
        for name,method in originals.items():setattr(gp.Model,name,method)
    after=[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in ledger_paths]
    tests=list(ET.parse(OUT/'TESTS.xml').getroot().iter('testcase'))
    failures=[r.attrib for r in tests if r.find('failure') is not None or r.find('error') is not None]
    skipped=[r.attrib for r in tests if r.find('skipped') is not None]
    report=dict(status='PASS' if not(code or failures or skipped or attempts or before!=after) else 'FAIL',
        baseline_IDs_preserved=682,baseline_commit=BASE,baseline_XML_SHA=hashlib.sha256(raw).hexdigest(),
        tests=len(tests),new_tests=len(tests)-682,new_test_files=new,failures=failures,skipped=skipped,
        blocked_actual_native_attempts=attempts,actual_Native_calls=0,
        historical_Native_ledgers_before=before,historical_Native_ledgers_after=after,
        historical_Native_ledgers_byte_preserved=before==after,
        simulated_fixture_model_calls_are_not_Native=True,wall_seconds=time.perf_counter()-began)
    (OUT/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2));return code


if __name__=='__main__':raise SystemExit(main())

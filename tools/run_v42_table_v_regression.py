"""Preserve 682 RC01 IDs and test Table V; R2 expansion is excluded."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
from time import perf_counter
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASE='6a12d503a'
OLD='docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01/REGRESSION/TESTS.xml'

def main(output):
    if output.exists():raise FileExistsError('REGRESSION_EVIDENCE_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True)
    raw=subprocess.check_output(['git','show',BASE+':'+OLD],cwd=ROOT)
    nodes=[r.attrib['classname'].replace('.','/')+'.py::'+r.attrib['name'] for r in ET.fromstring(raw).iter('testcase')]
    if len(nodes)!=len(set(nodes)) or len(nodes)!=682:raise ValueError('682_BASELINE_IDS_REQUIRED')
    old_files={n.split('::')[0] for n in nodes}
    new=sorted(set(p.relative_to(ROOT).as_posix() for pattern in ('test_v42_table_v*.py','test_v42_tablev*.py',
        'test_v42_preparation_performance.py','test_v42_a_control_numeric_messages.py','test_v42_source18r_phase.py')
        for p in (ROOT/'tests').glob(pattern) if p.relative_to(ROOT).as_posix() not in old_files))
    import pytest
    import gurobipy as gp
    attempts=[]
    original={n:getattr(gp.Model,n) for n in ('optimize','presolve','computeIIS')}
    def forbidden(*args,**kwargs):
        attempts.append('ACTUAL_NATIVE_ENTRYPOINT');pytest.fail('TABLE_V_REGRESSION_REAL_NATIVE_FORBIDDEN')
    for name in original:setattr(gp.Model,name,forbidden)
    class Guard:
        @pytest.fixture(autouse=True)
        def prevent_real_native(self,monkeypatch):
            for name in original:monkeypatch.setattr(gp.Model,name,forbidden)
    from v42_integration.table_v_run import HISTORY
    def records():return [dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HISTORY]
    before=records();began=perf_counter()
    try:
        code=int(pytest.main(['-q','-p','no:cacheprovider','--junitxml='+str(output/'TESTS.xml'),*nodes,*new],plugins=[Guard()]))
    finally:
        for name,method in original.items():setattr(gp.Model,name,method)
    after=records();tests=list(ET.parse(output/'TESTS.xml').getroot().iter('testcase'))
    failures=[r.attrib for r in tests if r.find('failure') is not None or r.find('error') is not None]
    skipped=[r.attrib for r in tests if r.find('skipped') is not None]
    report=dict(status='PASS' if not(code or failures or skipped or attempts or before!=after) else 'FAIL',
        baseline_IDs_preserved=682,baseline_commit=BASE,baseline_XML_SHA=hashlib.sha256(raw).hexdigest(),
        tests=len(tests),new_tests=len(tests)-682,new_test_files=new,failures=failures,skipped=skipped,
        blocked_real_native_attempts=attempts,Native_optimize_calls=0,
        historical_ledgers_before=before,historical_ledgers_after=after,historical_ledgers_byte_preserved=before==after,
        R2_expansion_implemented_modified_executed_validated=False,R2_new_research_test_modules_selected=False,
        original_running_checkpoint_WAN_regression_is_not_R2_pending_transfer_extension=True,
        named_fixture_calls_are_not_Native=True,wall_seconds=perf_counter()-began)
    (output/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2),flush=True)
    return code

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    raise SystemExit(main(p.parse_args().output))

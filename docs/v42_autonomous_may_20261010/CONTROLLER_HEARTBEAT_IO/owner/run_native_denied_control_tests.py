"""Control-only tests; retain actual fault bytes and deny all real model/Native entry."""
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
import contextlib,hashlib,io,json,time,sys,xml.etree.ElementTree as ET
import gurobipy as gp
import pytest
REPO=Path('D:/MobileESS_v42_autonomous');ROOT=Path('D:/v42_may_restart_20261010_02');OUT=Path(__file__).parent
sys.path.insert(0,str(REPO))
OWNED=('v42_autonomous/recovery.py','v42_autonomous/supervisor.py','tests/test_v42_autonomous_recovery.py','tests/test_v42_autonomous_supervisor.py')
def rec(path,data=None):
    path=Path(path);data=path.read_bytes() if data is None else data
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def snapshot(path,name):
    data=Path(path).read_bytes();target=OUT/name
    with target.open('xb') as stream:stream.write(data)
    return dict(source=rec(path,data),snapshot=rec(target,data),source_read_count=1)
raw_error=snapshot(ROOT/'SUPERVISOR_ERROR.json','ORIGINAL_SUPERVISOR_ERROR_RAW.json')
raw_cp=snapshot(ROOT/'SUPERVISOR_STATE.json','PRE_TEST_SUPERVISOR_STATE_RAW.json')
raw_process=snapshot(ROOT/'SUPERVISOR_PROCESS.json','PRE_TEST_SUPERVISOR_PROCESS_RAW.json')
before={name:rec(REPO/name) for name in OWNED}
manifest=json.loads((ROOT/'B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json').read_text(encoding='utf-8-sig'))
science_names={**manifest['builder_original_sources'],**manifest['execution_sources']}
science_before={name:rec(REPO/name) for name in science_names}
assert all(science_before[name]['sha256']==sha for name,sha in science_names.items())
attempts=[]
def model_denied(*args,**kwargs):attempts.append('model');raise AssertionError('REAL_NATIVE_MODEL_CONSTRUCTION_DENIED')
def optimize_denied(*args,**kwargs):attempts.append('optimize');raise AssertionError('REAL_NATIVE_OPTIMIZE_DENIED')
output=io.StringIO();start=time.perf_counter();cpu=time.process_time()
junit=OUT/'FULL_NATIVE_DENIED_TESTS.xml'
with patch.object(gp.Model,'__init__',model_denied),patch.object(gp.Model,'optimize',optimize_denied),contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
    exit_code=pytest.main(['-q',str(REPO/OWNED[2]),str(REPO/OWNED[3]),'--basetemp',str(OUT/'pytest_full_native_denied'),'--junitxml',str(junit)])
wall=time.perf_counter()-start;cpu=time.process_time()-cpu
capture=OUT/'FULL_NATIVE_DENIED_OUTPUT.txt';capture.write_text(output.getvalue(),encoding='utf-8')
after={name:rec(REPO/name) for name in OWNED};science_after={name:rec(REPO/name) for name in science_names}
suite=ET.parse(junit).getroot().find('testsuite')
report=dict(schema='V42_CONTROL_OWNED_HEARTBEAT_IO_NATIVE_MODEL_DENIED_TEST_RECEIPT',UTC=datetime.now(timezone.utc).isoformat(),
    PASS=exit_code==0 and not attempts and before==after and science_before==science_after,
    exit_code=int(exit_code),tests=int(suite.attrib['tests']),failures=int(suite.attrib['failures']),errors=int(suite.attrib['errors']),skipped=int(suite.attrib['skipped']),wall_seconds=wall,CPU_seconds=cpu,
    source_start_end_identical=before==after,source_files_start=before,source_files_end=after,
    source32_original1007_and_execution98_unchanged=science_before==science_after,
    Source32_execution_SHA=manifest['execution_SHA'],declared_science_file_count=len(science_before),
    Native_optimize_calls=0,real_Native_model_constructions=0,denied_entry_attempts=attempts,
    synthetic_test_receipt_Native_numbers_are_not_real_Native_measurements=True,
    actual_Windows_exclusive_share_test_executed=any(x.attrib.get('name','').startswith('test_actual_windows_exclusive_heartbeat_lock') and x.find('skipped') is None for x in suite.findall('testcase')),
    failure_scope='Original PermissionError13 heartbeat read killed coordinator. Atomic replacement cause remains plausible, not proven by the saved traceback. New temporary Windows lock repro verifies deferral/recovery only.',
    actual_fault_snapshot=raw_error,pre_test_process_snapshot=raw_process,pre_test_controller_snapshot=raw_cp,
    output=rec(capture),junit=rec(junit),test_runner=rec(__file__),
    production_immutable_queue_manifest_changes_by_test_owner=0,process_actions=0,git_mutations=0,final_date_PASS_not_claimed=True)
target=OUT/'FULL_NATIVE_DENIED_TEST_RECEIPT.json'
with target.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(dict(PASS=report['PASS'],receipt=rec(target),tests=report['tests'],failures=report['failures'],errors=report['errors'],wall_seconds=wall,Native=0,models=0,attempts=attempts),ensure_ascii=False))

"""Only the authorized isolated controller tests; science and production remain read-only."""
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

AUDIT = Path(__file__).resolve().parent
REPO = Path('D:/MobileESS_v42_autonomous')
PRIOR = Path('D:/v42_source32_independent_review_20261010_01/SOURCE32_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_02.json')
FILES = ['v42_autonomous/recovery.py', 'v42_autonomous/supervisor.py',
    'tests/test_v42_autonomous_recovery.py', 'tests/test_v42_autonomous_supervisor.py']
TESTS = FILES[2:]
def record(path):
    p = Path(path); h = hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return dict(path=str(p.resolve()), sha256=h.hexdigest(), bytes=p.stat().st_size)
def records(names): return {n:record(REPO/n) for n in sorted(names)}
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
class Capture:
    def __init__(self): self.collected=0; self.passed=[]; self.failed=[]; self.skipped=[]
    def pytest_collection_finish(self, session): self.collected=len(session.items)
    def pytest_runtest_logreport(self, report):
        if report.when=='call' and report.passed: self.passed.append(report.nodeid)
        if report.failed: self.failed.append(dict(nodeid=report.nodeid, when=report.when, longrepr=str(report.longrepr)))
        if report.skipped: self.skipped.append(report.nodeid)
r = dict(schema='V42_OWNED_LIVE_HEARTBEAT_WINDOWS_IO_INDEPENDENT_NATIVE_DENIED_REVIEW', PASS=False,
    started_UTC=datetime.now(timezone.utc).isoformat(), code_root=str(REPO), commitpending=True,
    Native_optimize_calls=0, real_Native_model_constructions=0, modelattempts=[], nativeattempts=[],
    no_production_runtime_queue_process_or_source_edits=True,
    actual_scientific_solver_performance_or_final_PASS_claimed=False)
try:
    os.chdir(REPO); sys.path.insert(0,str(REPO)); sys.dont_write_bytecode=True
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    prior=json.loads(PRIOR.read_text(encoding='utf-8'))
    start=records(FILES); science_start=records(prior['source_file_records'])
    assert all(science_start[n]['sha256']==v['sha256'] for n,v in prior['source_file_records'].items())
    execution={n:science_start[n]['sha256'] for n in prior['execution_sources']}
    assert digest(execution)==prior['execution_SHA']
    diff=subprocess.run(['git','diff','--',*FILES],check=True,capture_output=True,encoding='utf-8').stdout
    (AUDIT/'CONTROLLER_FOUR_FILE_DIFF.patch').write_text(diff,encoding='utf-8')
    loaded=[]
    for name in ['v42_autonomous_b2.pricing_cache','v42_autonomous_b2.rmp_presolve','v42_autonomous_b2.worker','v42_autonomous_b2.f1_basis', 'v42_autonomous.recovery','v42_autonomous.supervisor']:
        importlib.import_module(name); loaded.append(name)
    import gurobipy as gp
    retained_model=gp.Model; retained_init=retained_model.__init__; retained_optimize=retained_model.optimize
    def denied_model(*a,**k):
        r['modelattempts'].append(dict(entry='gp.Model',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('CONTROLLER_REVIEW_REAL_MODEL_CONSTRUCTOR_DENIED')
    def denied_init(*a,**k):
        r['modelattempts'].append(dict(entry='retained_real_Model.__init__',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('CONTROLLER_REVIEW_RETAINED_REAL_MODEL_INIT_DENIED')
    def denied_native(*a,**k):
        r['nativeattempts'].append(dict(entry='retained_real_Model.optimize',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('CONTROLLER_REVIEW_REAL_NATIVE_OPTIMIZE_DENIED')
    import pytest
    capture=Capture(); wall=time.perf_counter()
    basetemp=AUDIT/'pytest_tmp'; assert not basetemp.exists()
    args=['-q','-p','no:cacheprovider','--basetemp',str(basetemp),*TESTS]
    with (AUDIT/'CONTROL_NATIVE_DENIED_TEST_OUTPUT.log').open('w',encoding='utf-8') as log:
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            with patch.object(retained_model,'__init__',denied_init),patch.object(retained_model,'optimize',denied_native),patch.object(gp,'Model',denied_model):
                exit_code=int(pytest.main(args,plugins=[capture]))
    end=records(FILES); science_end=records(prior['source_file_records'])
    execution_end={n:science_end[n]['sha256'] for n in prior['execution_sources']}
    actual_windows_passed=any('test_actual_windows_exclusive_heartbeat_lock' in n for n in capture.passed)
    r.update(control_source_file_records=start,control_source_file_records_end=end,
        source_start_end_identical=start==end,test_start_end_identical=all(start[n]==end[n] for n in TESTS),
        source_file_records=science_start,source_file_records_end=science_end,scientific_source_file_count=len(science_start),
        scientific_Source32_1105_unchanged=science_start==science_end,
        execution_sources=execution,execution_sources_end=execution_end,execution_SHA=digest(execution),execution_start_end_identical=execution==execution_end,
        prior_Source32_scientific_validation=record(PRIOR),protected_preloads_before_real_Model_denial=loaded,
        real_Model_constructor_init_optimize_denied=True,pytest_args=args,exit_code=exit_code,cases_collected=capture.collected,
        tests_passed=len(capture.passed),passed_test_nodeids=capture.passed,test_failures=capture.failed,skipped_test_nodeids=capture.skipped,
        actual_Windows_exclusive_share_fixture_passed=actual_windows_passed,test_wall_seconds=time.perf_counter()-wall,
        actual_failure_snapshot=record(AUDIT/'ACTUAL_SUPERVISOR_ERROR_20261010_063835.json'),
        actual_failure_original_path='D:/v42_may_restart_20261010_02/SUPERVISOR_ERROR.json',
        candidate_diff=record(AUDIT/'CONTROLLER_FOUR_FILE_DIFF.patch'),test_output=record(AUDIT/'CONTROL_NATIVE_DENIED_TEST_OUTPUT.log'),
        corrected_static_review_finding='Missing/no-read heartbeat cannot resolve prior EACCES observation; only explicit sealed matching real-read marker may resolve the current observation, with history retained.')
    r['PASS']=bool(exit_code==0 and capture.collected>0 and len(capture.passed)==capture.collected and not capture.failed and not capture.skipped
        and actual_windows_passed and not r['modelattempts'] and not r['nativeattempts']
        and r['source_start_end_identical'] and r['test_start_end_identical'] and r['scientific_Source32_1105_unchanged'] and r['execution_start_end_identical'])
except BaseException as error: r.update(error=repr(error),traceback=traceback.format_exc())
r['finished_UTC']=datetime.now(timezone.utc).isoformat()
p=AUDIT/'INDEPENDENT_CONTROLLER_IO_NATIVE_DENIED_REVIEW_RECEIPT.json'
p.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=record(p),cases=r.get('cases_collected'),passed=r.get('tests_passed'),modelattempts=r['modelattempts'],nativeattempts=r['nativeattempts'],error=r.get('error')),indent=2))
raise SystemExit(0 if r['PASS'] else 1)

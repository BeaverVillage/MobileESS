"""Authorized isolated control tests; immutable Source32 science binding."""
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
SCIENCE = Path('D:/v42run32')
PRIOR = Path('D:/v42_source32_independent_review_20261010_01/SOURCE32_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_02.json')
OWNER = Path('D:/v42_controller_duplicate_startup_repair_20261010_01')
FILES = ['v42_autonomous/recovery.py', 'v42_autonomous/supervisor.py',
    'tests/test_v42_autonomous_recovery.py', 'tests/test_v42_autonomous_supervisor.py']
EXPECTED = dict(zip(FILES, [
    'bb779f4aa198001bf859225328d0f9dcc9d2249f71edab9a6596e3aea2d1fcb8',
    '4ad79721ca02272e6471fe56e1637b60b9f38a48748da5cd39d6a2adf5f45f92',
    '2f8c9c35d25f2642d4176cf2b41f972721403c8fede677ab06ccffb1526b9b9a',
    'c29ecd845a90b8f91f5db67280f4887f667eef6bd78aa69521242274c6068137']))
TESTS = FILES[2:]

def record(path):
    p = Path(path); h = hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return dict(path=str(p.resolve()), sha256=h.hexdigest(), bytes=p.stat().st_size)
def records(root, names): return {n:record(root/n) for n in sorted(names)}
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
class Capture:
    def __init__(self): self.collected=0; self.passed=[]; self.failed=[]; self.skipped=[]
    def pytest_collection_finish(self, session): self.collected=len(session.items)
    def pytest_runtest_logreport(self, report):
        if report.when=='call' and report.passed: self.passed.append(report.nodeid)
        if report.failed: self.failed.append(dict(nodeid=report.nodeid, when=report.when, longrepr=str(report.longrepr)))
        if report.skipped: self.skipped.append(report.nodeid)

r = dict(schema='V42_VERIFIED_DUPLICATE_CONTROLLER_STARTUP_INDEPENDENT_NATIVE_DENIED_REVIEW', PASS=False,
    started_UTC=datetime.now(timezone.utc).isoformat(), code_root=str(REPO), scientific_source_root=str(SCIENCE), commitpending=True,
    Native_optimize_calls=0, real_Native_model_constructions=0, modelattempts=[], nativeattempts=[],
    production_source_runtime_queue_process_git_changes=0,
    isolated_fixture_child_launch_and_termination_only=True,
    actual_scientific_solver_performance_or_final_PASS_claimed=False)
try:
    os.chdir(REPO); sys.path.insert(0,str(REPO)); sys.dont_write_bytecode=True
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    prior=json.loads(PRIOR.read_text(encoding='utf-8'))
    assert prior['PASS'] is True
    start=records(REPO, FILES); science_start=records(SCIENCE, prior['source_file_records'])
    assert len(science_start)==1105 and len(prior['execution_sources'])==98
    assert all(start[n]['sha256']==EXPECTED[n] for n in FILES)
    assert all(science_start[n]['sha256']==v['sha256'] and science_start[n]['bytes']==v['bytes'] for n,v in prior['source_file_records'].items())
    execution={n:science_start[n]['sha256'] for n in prior['execution_sources']}
    assert digest(execution)==prior['execution_SHA']=='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'
    diff=subprocess.run(['git','diff','--ignore-space-at-eol','--',*FILES],check=True,capture_output=True,encoding='utf-8').stdout
    (AUDIT/'CONTROLLER_NORMALIZED_DIFF.patch').write_text(diff,encoding='utf-8')
    owner_receipt=json.loads((OWNER/'FULL_NATIVE_DENIED_TEST_RECEIPT.json').read_text(encoding='utf-8'))
    assert owner_receipt['PASS'] is True and owner_receipt['tests']==142
    assert owner_receipt['source_start_end_identical'] is True
    fault=OWNER/'ORIGINAL_SUPERVISOR_ERROR_RAW_FULL.json'
    raw=fault.read_bytes(); (AUDIT/fault.name).write_bytes(raw)
    assert record(fault)['sha256']==owner_receipt['actual_fault_snapshot']['snapshot']['sha256']
    loaded=[]
    for name in ['v42_autonomous_b2.pricing_cache','v42_autonomous_b2.rmp_presolve','v42_autonomous_b2.worker','v42_autonomous_b2.f1_basis','v42_autonomous.recovery','v42_autonomous.supervisor']:
        importlib.import_module(name); loaded.append(name)
    import gurobipy as gp
    retained_model=gp.Model; retained_init=retained_model.__init__; retained_optimize=retained_model.optimize
    def denied_model(*a,**k):
        r['modelattempts'].append(dict(entry='gp.Model',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('STARTUP_REVIEW_REAL_MODEL_CONSTRUCTOR_DENIED')
    def denied_init(*a,**k):
        r['modelattempts'].append(dict(entry='retained_real_Model.__init__',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('STARTUP_REVIEW_RETAINED_REAL_MODEL_INIT_DENIED')
    def denied_native(*a,**k):
        r['nativeattempts'].append(dict(entry='retained_real_Model.optimize',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('STARTUP_REVIEW_REAL_NATIVE_OPTIMIZE_DENIED')
    import pytest
    capture=Capture(); wall=time.perf_counter()
    basetemp=AUDIT/'pytest_tmp'; assert not basetemp.exists()
    args=['-q','-p','no:cacheprovider','--basetemp',str(basetemp),*TESTS]
    with (AUDIT/'CONTROL_NATIVE_DENIED_TEST_OUTPUT.log').open('w',encoding='utf-8') as log:
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            with patch.object(retained_model,'__init__',denied_init),patch.object(retained_model,'optimize',denied_native),patch.object(gp,'Model',denied_model):
                exit_code=int(pytest.main(args,plugins=[capture]))
    end=records(REPO, FILES); science_end=records(SCIENCE, prior['source_file_records'])
    execution_end={n:science_end[n]['sha256'] for n in prior['execution_sources']}
    proof_paths=list(basetemp.rglob('REAL_WINDOWS_STARTUP_DUPLICATE_NATIVE_DENIED_PROOF.json'))
    assert len(proof_paths)==1
    actual_proof=json.loads(proof_paths[0].read_text(encoding='utf-8'))
    assert actual_proof['PASS'] is True and actual_proof['fixture_only'] is True
    assert actual_proof['Native_optimize_calls']==actual_proof['real_Native_model_constructions']==0
    assert actual_proof['production_process_actions']==0
    actual_windows_passed=any('test_actual_windows_owned_supervisor_mutex_duplicate' in n for n in capture.passed)
    heartbeat_windows_passed=any('test_actual_windows_exclusive_heartbeat_lock' in n for n in capture.passed)
    r.update(control_source_file_records=start,control_source_file_records_end=end,
        source_start_end_identical=start==end,test_start_end_identical=all(start[n]==end[n] for n in TESTS),
        source_file_records=science_start,source_file_records_end=science_end,scientific_source_file_count=len(science_start),
        scientific_Source32_1105_unchanged=science_start==science_end,
        execution_sources=execution,execution_sources_end=execution_end,execution_SHA=digest(execution),execution_start_end_identical=execution==execution_end,
        prior_Source32_scientific_validation=record(PRIOR),protected_preloads_before_real_Model_denial=loaded,
        real_Model_constructor_init_optimize_denied=True,pytest_args=args,exit_code=exit_code,cases_collected=capture.collected,
        tests_passed=len(capture.passed),passed_test_nodeids=capture.passed,test_failures=capture.failed,skipped_test_nodeids=capture.skipped,
        actual_Windows_owned_mutex_duplicate_fixture_passed=actual_windows_passed,
        actual_Windows_exclusive_heartbeat_share_fixture_passed=heartbeat_windows_passed,
        isolated_actual_Windows_fixture_proof=record(proof_paths[0]),isolated_actual_Windows_fixture_evidence=actual_proof,
        test_wall_seconds=time.perf_counter()-wall, actual_failure_snapshot=record(AUDIT/fault.name),
        actual_failure_original_path=owner_receipt['actual_fault_snapshot']['source']['path'],
        owner_test_receipt=record(OWNER/'FULL_NATIVE_DENIED_TEST_RECEIPT.json'),
        owner_actual_fixture_proof=record(OWNER/'ACTUAL_ISOLATED_WIN_MUTEX_DUPLICATE_PROOF_RECEIPT.json'),
        candidate_diff=record(AUDIT/'CONTROLLER_NORMALIZED_DIFF.patch'),test_output=record(AUDIT/'CONTROL_NATIVE_DENIED_TEST_OUTPUT.log'),
        test_runner=record(__file__),
        static_review_facts={
            'supervisor.py:559-590':'Only win32 exact canonical LockBusy/expected global path with EACCES/EAGAIN/EDEADLK OSError cause; owner proof reads strict; exact live PID/create/command/cwd/exe and matching heartbeat age 0..60s.',
            'supervisor.py:591-607':'Exclusive new immutable rejection event; no existing public error/CP/worker/Native file writes, no lock removal.',
            'supervisor.py:611-619':'Catch surrounds only global lock __enter__; acquired body errors propagate and original exit executes.',
            'supervisor.py:622-650':'Manifest fixed 3/1 validation precedes lock; verified duplicate returns before CP adoption or any controller/worker write; existing body and __main__ error path preserved.',
            'test_v42_autonomous_supervisor.py:447-554':'Strict wrong lock/type/errno/no cause, stale/future/mismatched/dead owner, missing/corrupt/access-denied owner reads and body LockBusy; real isolated canonical Windows owner mutex preserves original error/CP/three request+ledger fixture bytes.'})
    r['PASS']=bool(exit_code==0 and capture.collected==142 and len(capture.passed)==142 and not capture.failed and not capture.skipped
        and actual_windows_passed and heartbeat_windows_passed and not r['modelattempts'] and not r['nativeattempts']
        and r['source_start_end_identical'] and r['test_start_end_identical'] and r['scientific_Source32_1105_unchanged'] and r['execution_start_end_identical'])
except BaseException as error: r.update(error=repr(error),traceback=traceback.format_exc())
r['finished_UTC']=datetime.now(timezone.utc).isoformat()
p=AUDIT/'INDEPENDENT_CONTROLLER_STARTUP_NATIVE_DENIED_REVIEW_RECEIPT.json'
p.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=record(p),cases=r.get('cases_collected'),passed=r.get('tests_passed'),modelattempts=r['modelattempts'],nativeattempts=r['nativeattempts'],error=r.get('error')),indent=2))
raise SystemExit(0 if r['PASS'] else 1)

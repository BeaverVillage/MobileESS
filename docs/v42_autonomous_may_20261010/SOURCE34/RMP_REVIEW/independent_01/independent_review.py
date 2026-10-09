"""Source34 selected tests with real model and Native entry denied."""
import contextlib
from datetime import datetime,timezone
import hashlib,importlib,json,os
from pathlib import Path
import subprocess,sys,time,traceback
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=Path('D:/MobileESS_v42_autonomous')
MANIFEST=Path('D:/v42_may_restart_20261010_02/B2_V33_ZERO_START_DEPLOYMENT_MANIFEST.json')
OWNER=Path('D:/v42_rmp_current_start34_tests_20261010_02/SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json')
PRIOR=Path('D:/v42_source33_independent_review_20261010_01/SOURCE33_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')
TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_basis.py',
    'tests/test_v42_autonomous_b2_f1_state.py','tests/test_v42_autonomous_b2_rmp_presolve.py']
SOURCE='v42_autonomous_b2/rmp_presolve.py'
def rec(path):
    p=Path(path);h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return dict(path=str(p.resolve()),sha256=h.hexdigest(),bytes=p.stat().st_size)
def records(names):return {n:rec(REPO/n) for n in sorted(names)}
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
class Capture:
    def __init__(self):self.collected=0;self.passed=[];self.failed=[];self.skipped=[]
    def pytest_collection_finish(self,session):self.collected=len(session.items)
    def pytest_runtest_logreport(self,report):
        if report.when=='call' and report.passed:self.passed.append(report.nodeid)
        if report.failed:self.failed.append(dict(nodeid=report.nodeid,when=report.when,longrepr=str(report.longrepr)))
        if report.skipped:self.skipped.append(report.nodeid)
r=dict(schema='V42_SOURCE34_RMP_CURRENT_START_INDEPENDENT_NATIVE_DENIED_REVIEW',PASS=False,
    started_UTC=datetime.now(timezone.utc).isoformat(),code_root=str(REPO),commitpending=True,
    Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
    scientific_solver_performance_or_actual_final_PASS_claimed=False,source_runtime_queue_process_Git_or_production_changes=0)
try:
    os.chdir(REPO);sys.path.insert(0,str(REPO));sys.dont_write_bytecode=True
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    manifest=read(MANIFEST);owner=read(OWNER);prior=read(PRIOR)
    assert owner['PASS'] is True and owner['tests_passed']==244 and prior['PASS'] is True
    names=sorted(set(manifest['builder_original_sources'])|set(manifest['execution_sources']))
    source_start=records(names);tests_start=records(TESTS)
    assert len(source_start)==1105 and len(manifest['execution_sources'])==98
    assert source_start[SOURCE]['sha256']=='e588518a24348741f26704bc9de9a053858c63a8c494d6cd0e687735c1bc839f'
    assert tests_start[TESTS[-1]]['sha256']=='6a9dac43025f1a412fbb1fc8a7ffec429d65b9884f0af2af2cb99ab24a53bd7e'
    original_match=all(source_start[n]['sha256']==v for n,v in manifest['builder_original_sources'].items())
    unchanged_97=all(source_start[n]['sha256']==v for n,v in manifest['execution_sources'].items() if n!=SOURCE)
    assert original_match and unchanged_97
    execution={n:source_start[n]['sha256'] for n in manifest['execution_sources']}
    assert execution==owner['execution_sources'] and digest(execution)==owner['execution_SHA']=='dd14a820e9b65f35e13827d89143bca22e656abd10365fe5b96dd04b40160016'
    assert all(source_start[n]==v for n,v in owner['source_file_records'].items())
    assert all(tests_start[n]==owner['source_and_test_records_before'][n] for n in TESTS)
    diff=subprocess.run(['git','diff','--ignore-space-at-eol','--',SOURCE,TESTS[-1]],check=True,capture_output=True,encoding='utf-8').stdout
    (OUT/'SOURCE34_TWO_FILE_NORMALIZED_DIFF.patch').write_text(diff,encoding='utf-8')
    loaded=[]
    for name in ['v42_autonomous_b2.pricing_cache','v42_autonomous_b2.rmp_presolve','v42_autonomous_b2.worker','v42_autonomous_b2.f1_basis','v42_autonomous_b2.f1_state']:
        importlib.import_module(name);loaded.append(name)
    import gurobipy as gp
    actual_model=gp.Model;actual_init=actual_model.__init__;actual_optimize=actual_model.optimize
    def deny_model(*a,**k):
        r['modelattempts'].append(dict(entry='gp.Model',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('SOURCE34_INDEPENDENT_REAL_MODEL_CONSTRUCTOR_DENIED')
    def deny_init(*a,**k):
        r['modelattempts'].append(dict(entry='retained_real_Model.__init__',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('SOURCE34_INDEPENDENT_RETAINED_REAL_MODEL_INIT_DENIED')
    def deny_optimize(*a,**k):
        r['nativeattempts'].append(dict(entry='retained_real_Model.optimize',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('SOURCE34_INDEPENDENT_REAL_NATIVE_OPTIMIZE_DENIED')
    import pytest
    capture=Capture();basetemp=REPO/'tmp/pytest_v34_independent_20261010_01';assert not basetemp.exists()
    args=['-q','-p','no:cacheprovider','--basetemp',str(basetemp),*TESTS]
    started=time.perf_counter()
    with (OUT/'SOURCE34_NATIVE_DENIED_OUTPUT.log').open('w',encoding='utf-8') as log:
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            with patch.object(gp,'Model',deny_model),patch.object(actual_model,'__init__',deny_init),patch.object(actual_model,'optimize',deny_optimize):
                exit_code=int(pytest.main(args,plugins=[capture]))
    source_end=records(names);tests_end=records(TESTS)
    execution_end={n:source_end[n]['sha256'] for n in execution}
    r.update(source_file_records=source_start,source_file_records_end=source_end,source_file_count=len(source_start),
        execution_sources=execution,execution_sources_end=execution_end,execution_SHA=digest(execution),execution_source_count=len(execution),
        source_start_end_identical=source_start==source_end,execution_start_end_identical=execution==execution_end,
        test_file_records_start=tests_start,test_file_records_end=tests_end,test_start_end_identical=tests_start==tests_end,
        all1007_original_source_SHA_match=original_match,all97_other_execution_sources_match_Source33=unchanged_97,
        original_Source33_manifest=rec(MANIFEST),prior_Source33_independent_review=rec(PRIOR),owner_review=rec(OWNER),
        protected_original_preloads_before_denial=loaded,retained_real_constructor_init_optimize_and_gp_Model_denied=True,
        pytest_arguments=args,cases_collected=capture.collected,tests_passed=len(capture.passed),passed_nodeids=capture.passed,
        failures=capture.failed,skipped=capture.skipped,exit_code=exit_code,test_wall_seconds=time.perf_counter()-started,
        candidate_diff=rec(OUT/'SOURCE34_TWO_FILE_NORMALIZED_DIFF.patch'),output=rec(OUT/'SOURCE34_NATIVE_DENIED_OUTPUT.log'),runner=rec(__file__),
        original_single_RMP_30_total5400_Threads1_precision_unchanged=True,
        original_Source33_F1_basis_worker_cache_and_1007_math_unchanged=True,
        carried_unchanged_cache120_and_original_Source33_selected214_are_historical_not_rerun=True,
        actual_Native_Pi_or_basis_start_use_or_UB_Global_LB_gain_proved=False,
        static_review_facts={
            'rmp_presolve.py:77-151':'Retained original code/type/delegate/closure guards are extended with immutable warm helpers, vector_sha and own weak-bound plan; original single Native accounting delegate remains.',
            'rmp_presolve.py:154-300':'Hashes current selected-case CSR/all domains/decomposition/request/catalog and same current point; strict original full replay gates eligibility. First actual current per-unit saved seed is byte/vector/axis checked; complete PStart=current nonunit values plus first seed lambda1 and others0, complete finite computational zero DStart. Original and scaled residuals are separately diagnostic.',
            'rmp_presolve.py:301-320':'Eligible own-model start is installed and exact readback verified before Native; ineligible plan changes no starts. Original Crossover and cold LPWarmStart preserved.',
            'rmp_presolve.py:406-545':'Source/request/ledger/raw model/row pullback guards remain before and after the exact one30s Method1 Presolve0 call with original precision/Threads1. After Native, verification never writes starts or updates or reads PStart/DStart; final accounting preserves unknown runtime.',
            'rmp_presolve.py:568-580':'Failure after original builder returns but before original run disposal scope disposes only the owned RMP model; normal disposal stays original dw.run finally.',
            'original dw.py:84-119':'Original row Pi read/pullback/sign handling/no-Pi result/finally disposal unchanged. Computational DStart is never substituted for absent Native Pi.',
            'tests':'New cases cover extra catalog lambda0, cold invalid/missing/partial/undefined input, scaled residual diagnostic, source/point/seed/catalog/readonly/delegate drift, install/readback faults and original UNKNOWN quarantine, no post-Native setters/update/readback, owned disposal and absent Native Pi.'})
    r['PASS']=bool(exit_code==0 and capture.collected==244 and len(capture.passed)==244 and not capture.failed and not capture.skipped
        and not r['modelattempts'] and not r['nativeattempts'] and source_start==source_end and tests_start==tests_end and execution==execution_end)
except BaseException as error:r.update(error=repr(error),traceback=traceback.format_exc())
r['finished_UTC']=datetime.now(timezone.utc).isoformat()
p=OUT/'SOURCE34_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json'
p.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=rec(p),cases=r.get('cases_collected'),passed=r.get('tests_passed'),
    execution_SHA=r.get('execution_SHA'),modelattempts=r['modelattempts'],nativeattempts=r['nativeattempts'],error=r.get('error')),indent=2))
raise SystemExit(0 if r['PASS'] else 1)

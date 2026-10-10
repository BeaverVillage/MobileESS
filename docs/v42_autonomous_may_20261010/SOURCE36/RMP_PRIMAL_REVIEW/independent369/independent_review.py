"""Selected Source36 tests with protected preloads and real Model/Native denial."""
import contextlib, hashlib, importlib, json, os, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
REPO=Path('D:/MobileESS_v42_autonomous')
FROZEN=Path('D:/v42run35')
MANIFEST=Path('D:/v42_may_restart_20261010_02/B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json')
PRIOR=Path('D:/v42_source35_independent_review_20261010_01/SOURCE35_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json')
TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_state.py',
       'tests/test_v42_autonomous_b2_f1_basis.py','tests/test_v42_autonomous_b2_rmp_presolve.py',
       'tests/test_v42_autonomous_b2_f1_price_seed.py']
CHANGED='v42_autonomous_b2/rmp_presolve.py'
EXPECTED_RMP='720a2bd58c13476b0020b572cf0618f3d8fe13fc22b1b7c4f1b8ea7ddd2f424e'
EXPECTED_TEST='0107ce5aa65c524ba903f77cd134c76a305ec610c6c70a351fa833c0ff07ba80'

def rec(path):
    p=Path(path).resolve(); h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def records(names,root=REPO):return {name:rec(root/name) for name in sorted(names)}
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
class Capture:
    def __init__(self):self.collected=0;self.by_file={};self.passed=[];self.failed=[];self.skipped=[]
    def pytest_collection_finish(self,session):
        self.collected=len(session.items)
        for item in session.items:
            name=Path(str(item.path)).name;self.by_file[name]=self.by_file.get(name,0)+1
    def pytest_runtest_logreport(self,report):
        if report.when=='call' and report.passed:self.passed.append(report.nodeid)
        if report.failed:self.failed.append(dict(nodeid=report.nodeid,when=report.when,longrepr=str(report.longrepr)))
        if report.skipped:self.skipped.append(report.nodeid)

r=dict(schema='SOURCE36_INDEPENDENT_CURRENT_START_METHOD_NATIVE_DENIED_REVIEW',PASS=False,
       started_UTC=datetime.now(timezone.utc).isoformat(),code_root=str(REPO),commitpending=True,
       Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
       source_runtime_queue_process_Git_or_production_changes=0,
       actual_performance_or_final_scientific_PASS_claimed=False)
try:
    sys.dont_write_bytecode=True;os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    os.chdir(REPO);sys.path.insert(0,str(REPO))
    manifest=read(MANIFEST);prior=read(PRIOR)
    assert rec(PRIOR)['sha256']=='cb5b009e1f1b0fefdbe064f3c45dd3bc56a30b5e1c683dd9cb915374f4c1547c'
    assert prior['PASS'] is True and prior['tests_passed']==335
    execution_names=sorted(manifest['execution_sources'])
    names=sorted(set(manifest['builder_original_sources'])|set(execution_names))
    assert len(names)==1106 and len(execution_names)==99 and len(manifest['builder_original_sources'])==1007
    source_start=records(names);test_start=records(TESTS);frozen=records(names,FROZEN)
    assert source_start[CHANGED]['sha256']==EXPECTED_RMP and test_start[TESTS[3]]['sha256']==EXPECTED_TEST
    originals=all(source_start[n]['sha256']==sha==frozen[n]['sha256'] for n,sha in manifest['builder_original_sources'].items())
    unchanged98=all(source_start[n]['sha256']==sha==frozen[n]['sha256'] for n,sha in manifest['execution_sources'].items() if n!=CHANGED)
    changed=[n for n in execution_names if source_start[n]['sha256']!=frozen[n]['sha256']]
    assert originals and unchanged98 and changed==[CHANGED]
    assert all(test_start[n]==prior['test_file_records_start'][n] for n in TESTS if n!=TESTS[3])
    execution_start={n:source_start[n]['sha256'] for n in execution_names}
    expected_execution=digest(execution_start)
    loaded=[]
    for name in ('v42_autonomous_b2.pricing_cache','v42_autonomous_b2.rmp_presolve',
                 'v42_autonomous_b2.worker','v42_autonomous_b2.f1_basis',
                 'v42_autonomous_b2.f1_state','v42_autonomous_b2.dw_native',
                 'v42_autonomous_b2.f1_price_seed'):
        importlib.import_module(name);loaded.append(name)
    import gurobipy as gp
    retained_model=gp.Model;retained_init=retained_model.__init__;retained_optimize=retained_model.optimize
    def deny_model(*args,**kwargs):
        r['modelattempts'].append(dict(entry='gp.Model',args_count=len(args),keywords=sorted(kwargs)))
        raise AssertionError('SOURCE36_INDEPENDENT_REAL_MODEL_CONSTRUCTOR_DENIED')
    def deny_init(*args,**kwargs):
        r['modelattempts'].append(dict(entry='retained_real_Model.__init__',args_count=len(args),keywords=sorted(kwargs)))
        raise AssertionError('SOURCE36_INDEPENDENT_RETAINED_REAL_MODEL_INIT_DENIED')
    def deny_optimize(*args,**kwargs):
        r['nativeattempts'].append(dict(entry='retained_real_Model.optimize',args_count=len(args),keywords=sorted(kwargs)))
        raise AssertionError('SOURCE36_INDEPENDENT_REAL_NATIVE_OPTIMIZE_DENIED')
    import pytest
    capture=Capture();basetemp=REPO/'tmp/pytest_v36_independent_20261010_01';assert not basetemp.exists()
    xml=OUT/'SOURCE36_NATIVE_DENIED_TESTS_01.xml';log=OUT/'SOURCE36_NATIVE_DENIED_TEST_OUTPUT_01.log'
    args=['-q','-p','no:cacheprovider','--basetemp',str(basetemp),'--junitxml',str(xml),*TESTS]
    started=time.perf_counter()
    with log.open('w',encoding='utf-8') as stream:
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            with patch.object(gp,'Model',deny_model),patch.object(retained_model,'__init__',deny_init),patch.object(retained_model,'optimize',deny_optimize):
                exit_code=int(pytest.main(args,plugins=[capture]))
    source_end=records(names);test_end=records(TESTS)
    execution_end={n:source_end[n]['sha256'] for n in execution_names}
    r.update(source_file_records=source_start,source_file_records_end=source_end,source_file_count=len(names),
        execution_sources=execution_start,execution_sources_end=execution_end,execution_source_count=len(execution_start),execution_SHA=expected_execution,
        source_start_end_identical=source_start==source_end,execution_start_end_identical=execution_start==execution_end,
        test_file_records_start=test_start,test_file_records_end=test_end,test_start_end_identical=test_start==test_end,
        all1007_original_source_SHA_match_immutable_Source35=originals,all98_other_execution_sources_match_Source35=unchanged98,
        changed_execution_sources_vs_Source35=changed,Source35_manifest=rec(MANIFEST),prior_Source35_independent_review=rec(PRIOR),
        protected_original_preloads_before_denial=loaded,retained_real_constructor_init_optimize_and_gp_Model_denied=True,
        pytest_arguments=args,cases_collected=capture.collected,cases_by_file=capture.by_file,tests_passed=len(capture.passed),
        passed_nodeids=capture.passed,failures=capture.failed,skipped=capture.skipped,exit_code=exit_code,
        test_wall_seconds=time.perf_counter()-started,runner=rec(__file__),output=rec(log),junit_xml=rec(xml),
        carried_unchanged_cache120_historical_not_rerun=True,
        original_F1_fullLP_caps120_300_and_RMP30_total5400_Threads1_precision_unchanged=True,
        original_full_math_and_Pi_and_LB_checker_unchanged=True,
        source35_price_seed_and_worker_and_original1007_unchanged=True)
    r['PASS']=bool(exit_code==0 and capture.collected==369 and len(capture.passed)==369
        and capture.by_file.get(Path(TESTS[3]).name)==136 and not capture.failed and not capture.skipped
        and not r['modelattempts'] and not r['nativeattempts'] and source_start==source_end and test_start==test_end
        and execution_start==execution_end and digest(execution_end)==expected_execution)
except BaseException as error:r.update(error=repr(error),traceback=traceback.format_exc())
r['finished_UTC']=datetime.now(timezone.utc).isoformat()
receipt=OUT/'SOURCE36_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json'
assert not receipt.exists()
receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=rec(receipt),cases=r.get('cases_collected'),passed=r.get('tests_passed'),
                     by_file=r.get('cases_by_file'),execution_SHA=r.get('execution_SHA'),
                     modelattempts=r['modelattempts'],nativeattempts=r['nativeattempts'],error=r.get('error')),indent=2))
raise SystemExit(0 if r['PASS'] else 1)

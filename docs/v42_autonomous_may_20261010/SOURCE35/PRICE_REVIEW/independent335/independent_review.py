"""Source35 five selected test modules under protected-preload Native denial."""
import contextlib,hashlib,importlib,json,os,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=Path(r'D:\MobileESS_v42_autonomous')
MANIFEST=Path(r'D:\v42_may_restart_20261010_02\B2_V34_ZERO_START_DEPLOYMENT_MANIFEST.json')
PRIOR=Path(r'D:\v42_source34_independent_review_20261010_01\SOURCE34_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')
TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_state.py',
       'tests/test_v42_autonomous_b2_f1_basis.py','tests/test_v42_autonomous_b2_rmp_presolve.py',
       'tests/test_v42_autonomous_b2_f1_price_seed.py']
NEW='v42_autonomous_b2/f1_price_seed.py';WORKER='v42_autonomous_b2/worker.py'
EXPECTED_EXECUTION='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'

def rec(path):
    p=Path(path);h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=h.hexdigest())
def records(names):return {n:rec(REPO/n) for n in sorted(names)}
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
r=dict(schema='SOURCE35_INDEPENDENT_PRODUCTION_PRICE_SEED_NATIVE_DENIED_REVIEW',PASS=False,
       started_UTC=datetime.now(timezone.utc).isoformat(),code_root=str(REPO),commitpending=True,
       Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
       source_runtime_queue_process_Git_or_production_changes=0,actual_performance_or_final_scientific_PASS_claimed=False)
try:
    sys.dont_write_bytecode=True;os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    os.chdir(REPO);sys.path.insert(0,str(REPO))
    manifest=read(MANIFEST);prior=read(PRIOR)
    assert prior['PASS'] is True and prior['tests_passed']==244
    execution_names=sorted(set(manifest['execution_sources'])|{NEW})
    names=sorted(set(manifest['builder_original_sources'])|set(execution_names))
    source_start=records(names);test_start=records(TESTS)
    assert len(names)==1106 and len(execution_names)==99 and len(manifest['builder_original_sources'])==1007
    expected={NEW:'758f9dfc7b7ff0d81130a9515df7b843d26c6b1c87f04d3fa1527df5d8f0f754',
              WORKER:'ff42dcb94488a57817b545d2badb15c0da1faef05755a2ec06fafe3a96a8104c',
              TESTS[0]:'df8ddfab571584a4d521afa5a769638017fdbe8092506212c3e05a4b234da119',
              TESTS[-1]:'63797cc4a716fde4d12e35ab0d7080ef0bd35981c2f6a482b2f8c393249f1256'}
    assert all((source_start if n in source_start else test_start)[n]['sha256']==s for n,s in expected.items())
    originals=all(source_start[n]['sha256']==s for n,s in manifest['builder_original_sources'].items())
    unchanged97=all(source_start[n]['sha256']==s for n,s in manifest['execution_sources'].items() if n!=WORKER)
    assert originals and unchanged97
    assert all(test_start[n]==prior['test_file_records_start'][n] for n in TESTS[1:4])
    execution_start={n:source_start[n]['sha256'] for n in execution_names}
    assert digest(execution_start)==EXPECTED_EXECUTION
    loaded=[]
    for name in ('v42_autonomous_b2.pricing_cache','v42_autonomous_b2.rmp_presolve',
                 'v42_autonomous_b2.worker','v42_autonomous_b2.f1_basis',
                 'v42_autonomous_b2.f1_state','v42_autonomous_b2.dw_native',
                 'v42_autonomous_b2.f1_price_seed'):
        importlib.import_module(name);loaded.append(name)
    import gurobipy as gp
    retained_model=gp.Model;retained_init=retained_model.__init__;retained_optimize=retained_model.optimize
    def deny_model(*a,**k):
        r['modelattempts'].append(dict(entry='gp.Model',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('SOURCE35_INDEPENDENT_REAL_MODEL_CONSTRUCTOR_DENIED')
    def deny_init(*a,**k):
        r['modelattempts'].append(dict(entry='retained_real_Model.__init__',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('SOURCE35_INDEPENDENT_RETAINED_REAL_MODEL_INIT_DENIED')
    def deny_optimize(*a,**k):
        r['nativeattempts'].append(dict(entry='retained_real_Model.optimize',args_count=len(a),keywords=sorted(k)))
        raise AssertionError('SOURCE35_INDEPENDENT_REAL_NATIVE_OPTIMIZE_DENIED')
    import pytest
    capture=Capture();basetemp=REPO/'tmp/pytest_v35_independent_20261010_01';assert not basetemp.exists()
    xml=OUT/'SOURCE35_NATIVE_DENIED_TESTS_01.xml'
    args=['-q','-p','no:cacheprovider','--basetemp',str(basetemp),'--junitxml',str(xml),*TESTS]
    started=time.perf_counter();log=OUT/'SOURCE35_NATIVE_DENIED_TEST_OUTPUT_01.log'
    with log.open('w',encoding='utf-8') as stream:
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            with patch.object(gp,'Model',deny_model),patch.object(retained_model,'__init__',deny_init),patch.object(retained_model,'optimize',deny_optimize):
                exit_code=int(pytest.main(args,plugins=[capture]))
    source_end=records(names);test_end=records(TESTS)
    execution_end={n:source_end[n]['sha256'] for n in execution_names}
    r.update(source_file_records=source_start,source_file_records_end=source_end,source_file_count=len(names),
        execution_sources=execution_start,execution_sources_end=execution_end,execution_source_count=len(execution_start),execution_SHA=digest(execution_start),
        source_start_end_identical=source_start==source_end,execution_start_end_identical=execution_start==execution_end,
        test_file_records_start=test_start,test_file_records_end=test_end,test_start_end_identical=test_start==test_end,
        all1007_original_source_SHA_match_immutable_Source34=originals,all97_other_execution_sources_match_Source34=unchanged97,
        Source35_changes_vs_Source34_execution_only_new_price_module_and_worker=True,
        Source34_F1_basis_RMP_cache_math_precision_caps_120_300_5400_Threads1_unchanged=True,
        Source34_manifest=rec(MANIFEST),prior_Source34_independent_review=rec(PRIOR),
        protected_original_preloads_before_denial=loaded,retained_real_constructor_init_optimize_and_gp_Model_denied=True,
        pytest_arguments=args,cases_collected=capture.collected,cases_by_file=capture.by_file,
        tests_passed=len(capture.passed),passed_nodeids=capture.passed,failures=capture.failed,skipped=capture.skipped,
        exit_code=exit_code,test_wall_seconds=time.perf_counter()-started,runner=rec(__file__),output=rec(log),junit_xml=rec(xml),
        carried_unchanged_cache120_historical_not_rerun=True,
        actual99_positive_constructor_factory_unmodified_source_authority_test_in_selected_suite=True,
        Root_four_lazy_hook_cases_in_selected_suite=True,
        native_pricing_performance_or_final_scientific_PASS_proved=False)
    r['PASS']=bool(exit_code==0 and capture.collected==335 and len(capture.passed)==335
        and capture.by_file.get(Path(TESTS[-1]).name)==87 and not capture.failed and not capture.skipped
        and not r['modelattempts'] and not r['nativeattempts'] and source_start==source_end and test_start==test_end
        and execution_start==execution_end and digest(execution_end)==EXPECTED_EXECUTION)
except BaseException as error:r.update(error=repr(error),traceback=traceback.format_exc())
r['finished_UTC']=datetime.now(timezone.utc).isoformat()
receipt=OUT/'SOURCE35_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json'
receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=rec(receipt),cases=r.get('cases_collected'),passed=r.get('tests_passed'),
                     by_file=r.get('cases_by_file'),execution_SHA=r.get('execution_SHA'),
                     modelattempts=r['modelattempts'],nativeattempts=r['nativeattempts'],error=r.get('error')),indent=2))
raise SystemExit(0 if r['PASS'] else 1)

from pathlib import Path
from datetime import datetime,timezone
import contextlib,io,json,re,sys,time,hashlib
from unittest.mock import patch
sys.path.insert(0,r'D:\MobileESS_v42_autonomous')
import gurobipy as gp
# Capture protected original descriptors before imposing the test denials.
from v42_autonomous_b2 import f1_basis,f1_state,pricing_cache,rmp_presolve,worker
import pytest

REPO=Path(r'D:\MobileESS_v42_autonomous')
OUT=Path(r'D:\v42_rmp_current_start34_tests_20261010_02')
TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_basis.py',
       'tests/test_v42_autonomous_b2_f1_state.py','tests/test_v42_autonomous_b2_rmp_presolve.py']
FILES=['v42_autonomous_b2/worker.py','v42_autonomous_b2/f1_basis.py',
       'v42_autonomous_b2/f1_state.py','v42_autonomous_b2/rmp_presolve.py',*TESTS]
MANIFEST=Path(r'D:\v42_may_restart_20261010_02\B2_V33_ZERO_START_DEPLOYMENT_MANIFEST.json')

def record(path):
 path=Path(path).resolve();data=path.read_bytes()
 return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

before={name:record(REPO/name) for name in FILES};execution=worker.sources()
manifest=json.loads(MANIFEST.read_bytes());names=sorted(set(execution)|set(manifest['builder_original_sources']))
all_before={name:record(REPO/name) for name in names}
original_equal=all(all_before[name]['sha256']==value for name,value in manifest['builder_original_sources'].items())
prior_execution_equal_except_rmp=all(execution.get(name)==value for name,value in manifest['execution_sources'].items()
 if name!='v42_autonomous_b2/rmp_presolve.py')
assert len(names)==1105 and len(execution)==98 and original_equal and prior_execution_equal_except_rmp
actual_model=gp.Model;constructors=[];optimizers=[]

def deny_model(*args,**kwargs):
 constructors.append(dict(args=repr(args),kwargs=repr(kwargs)))
 raise AssertionError('SOURCE34_REAL_GUROBI_MODEL_CONSTRUCTION_DENIED')

def deny_optimize(*args,**kwargs):
 optimizers.append(dict(args=repr(args),kwargs=repr(kwargs)))
 raise AssertionError('SOURCE34_REAL_NATIVE_OPTIMIZE_DENIED')

stdout=io.StringIO();stderr=io.StringIO();started=datetime.now(timezone.utc).isoformat()
args=TESTS+['-q','--basetemp',str(REPO/'tmp/pytest_v34_selected_final_01'),
 '--junitxml',str(OUT/'SOURCE34_NATIVE_DENIED_TEST_RESULT.xml'),'--tb=short']
start=time.perf_counter();cpu=time.process_time()
with patch.object(gp,'Model',deny_model),patch.object(actual_model,'__init__',deny_model),\
 patch.object(actual_model,'optimize',deny_optimize),\
 contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
 exit_code=int(pytest.main(args))
elapsed=time.perf_counter()-start;cpu_elapsed=time.process_time()-cpu
output=stdout.getvalue();error=stderr.getvalue()
for name,value in [('OWNER_STDOUT.txt',output),('OWNER_STDERR.txt',error)]:
 with (OUT/name).open('xb') as stream:stream.write(value.encode('utf8'))
after={name:record(REPO/name) for name in FILES};after_execution=worker.sources()
all_after={name:record(REPO/name) for name in names}
match=re.search(r'(\d+) passed',output)
doc=dict(schema='V42_SOURCE34_CURRENT_ATTEMPT_RMP_START_NATIVE_DENIED_TEST_RECEIPT_V1',
 UTC=datetime.now(timezone.utc).isoformat(),test_started_UTC=started,
 PASS=exit_code==0 and not constructors and not optimizers and before==after and execution==after_execution and all_before==all_after,
 exit_code=exit_code,failures=0 if exit_code==0 else None,errors=0 if exit_code==0 else None,
 tests_passed=int(match.group(1)) if match else None,pytest_arguments=args,
 wall_seconds=elapsed,CPU_seconds=cpu_elapsed,
 source_start_end_identical=all_before==all_after,
 execution_start_end_identical=execution==after_execution,
 test_start_end_identical=all(before[name]==after[name] for name in TESTS),
 execution_sources=execution,execution_SHA=worker.digest(execution),
 source_file_records=all_before,source_file_count=len(all_before),execution_source_count=len(execution),
 all1007_original_source_SHA_match=original_equal,
 all97_other_execution_sources_match_Source33=prior_execution_equal_except_rmp,
 reference_Source33_manifest=record(MANIFEST),source_and_test_records_before=before,
 source_and_test_records_after=after,
 Native_optimize_calls=0,real_Native_model_constructions=0,
 real_Model_constructor_attempts=constructors,real_Native_optimize_attempts=optimizers,
 attempts=constructors+optimizers,modelattempts=constructors,nativeattempts=optimizers,
 retained_real_backend_class_constructor_and_optimizer_descriptors_denied=True,
 protected_original_preloads_before_denial=True,fixture_runtime_is_not_actual_Native_runtime=True,
 production_changed_files=['v42_autonomous_b2/rmp_presolve.py','tests/test_v42_autonomous_b2_rmp_presolve.py'],
 immutable_or_worker_or_request_or_budget_or_queue_or_process_mutations=0,
 original_RMP_single_call_seconds=30,original_native_budget_seconds=5400,
 approved_entry_computational_parameters=dict(Method=1,Presolve=0,LPWarmStart=2,Threads=1,
 FeasibilityTol=1e-9,OptimalityTol=1e-9,NumericFocus=3,ScaleFlag=2,original_Crossover_preserved=True),
 start_policy='CURRENT_SAME_ATTEMPT_FULL_SEED_PROJECTION_AND_COMPLETE_COMPUTATIONAL_ZERO_DSTART',
 cold_fallback_before_any_start_setter=True,post_Native_start_setter_update_or_readback=False,
 Native_Pi_absence_not_filled_by_DStart=True,
 no_performance_or_Global_LB_or_final_day_PASS_claimed=True,
 stdout=record(OUT/'OWNER_STDOUT.txt'),stderr=record(OUT/'OWNER_STDERR.txt'),
 junit=record(OUT/'SOURCE34_NATIVE_DENIED_TEST_RESULT.xml'),runner=record(__file__),
 historical_test_expectation_failure=dict(raw_stdout=record(Path(r'D:\v42_rmp_current_start34_tests_20261010_01')/'INITIAL_UNKNOWN_EXPECTATION_FAILURE.txt'),
 junit=record(Path(r'D:\v42_rmp_current_start34_tests_20261010_01')/'INITIAL_UNKNOWN_EXPECTATION_FAILURE.xml'),
 reason='Synthetic test expected install exception; unchanged original budget reissues UNKNOWN-runtime quarantine and preserves original error in its ledger'))
target=OUT/'SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json'
with target.open('xb') as stream:stream.write((json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
print(json.dumps(dict(PASS=doc['PASS'],tests=doc['tests_passed'],wall_seconds=elapsed,CPU_seconds=cpu_elapsed,
 receipt=record(target),files=before,execution_SHA=doc['execution_SHA']),ensure_ascii=False,indent=2))
if not doc['PASS']:print(output);print(error);raise SystemExit(1)

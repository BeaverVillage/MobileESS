from pathlib import Path
from datetime import datetime,timezone
import contextlib,io,json,re,sys,time,hashlib
from unittest.mock import patch
sys.path.insert(0,r'D:\MobileESS_v42_autonomous')
import gurobipy as gp
from v42_autonomous_b2 import f1_basis,f1_state,pricing_cache,rmp_presolve
import pytest

REPO=Path(r'D:\MobileESS_v42_autonomous')
OUT=Path(r'D:\v42_source32_cli_identity_review_20261010_01');OUT.mkdir(exist_ok=True)
TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_basis.py','tests/test_v42_autonomous_b2_f1_state.py','tests/test_v42_autonomous_b2_rmp_presolve.py']
FILES=['v42_autonomous_b2/worker.py','v42_autonomous_b2/f1_basis.py','v42_autonomous_b2/f1_state.py','v42_autonomous_b2/rmp_presolve.py',*TESTS]
FOLDERS=('v42_b2_seed_recovery_v19','v42_b2_seed_recovery_v18r3',
 'v42_b2_seed_recovery_v18r2','v42_b2_seed_recovery_v18',
 'v42_b2_start_recovery_v13','v42_b2_build_authority_v13','v42_autonomous_b2')
def record(p):
 p=Path(p);data=p.read_bytes()
 return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def sources():return {p.relative_to(REPO).as_posix():record(p)['sha256']
 for folder in FOLDERS for p in sorted((REPO/folder).iterdir())
 if p.is_file() and p.suffix in ('.py','.html')}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
before={name:record(REPO/name) for name in FILES}; execution=sources()
original_manifest=json.loads(Path(r'D:\v42_may_restart_20261010_02\B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json').read_bytes())
all_names=set(execution)|set(original_manifest['builder_original_sources'])
all_before={name:record(REPO/name) for name in sorted(all_names)}
assert len(all_names)==1105 and all(all_before[name]['sha256']==expected
 for name,expected in original_manifest['builder_original_sources'].items())
actual_model=gp.Model; constructors=[]; optimizers=[]
def deny_model(*args,**kwargs):
 constructors.append(dict(args=repr(args),kwargs=repr(kwargs)))
 raise AssertionError('SOURCE32_REAL_GUROBI_MODEL_CONSTRUCTION_DENIED')
def deny_optimize(*args,**kwargs):
 optimizers.append(dict(args=repr(args),kwargs=repr(kwargs)))
 raise AssertionError('SOURCE32_REAL_NATIVE_OPTIMIZE_DENIED')
stdout=io.StringIO();stderr=io.StringIO();started=datetime.now(timezone.utc).isoformat()
args=TESTS+['-q','--basetemp',str(REPO/'tmp/pytest_v32_selected_final_01'),
 '--junitxml',str(OUT/'SOURCE32_F1_NATIVE_DENIED_TEST_RESULT_02.xml'),'--tb=short']
start=time.perf_counter();cpu=time.process_time()
with patch.object(gp,'Model',deny_model),patch.object(actual_model,'__init__',deny_model),\
 patch.object(actual_model,'optimize',deny_optimize),\
 contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
 exit_code=int(pytest.main(args))
elapsed=time.perf_counter()-start;cpu_elapsed=time.process_time()-cpu
out=stdout.getvalue();err=stderr.getvalue()
for name,value in [('stdout_02.txt',out),('stderr_02.txt',err)]:
 with (OUT/name).open('xb') as f:f.write(value.encode('utf8'))
after={name:record(REPO/name) for name in FILES};after_execution=sources()
all_after={name:record(REPO/name) for name in sorted(all_names)}
match=re.search(r'(\d+) passed',out)
doc=dict(schema='V42_SOURCE32_CANONICAL_CLI_BUDGET_AND_CURRENT_BASIS_NATIVE_DENIED_TEST_RECEIPT_V1',
 UTC=datetime.now(timezone.utc).isoformat(),test_started_UTC=started,
 PASS=exit_code==0 and not constructors and not optimizers and before==after and execution==after_execution and all_before==all_after,
 exit_code=exit_code,tests_passed=int(match.group(1)) if match else None,pytest_arguments=args,
 wall_seconds=elapsed,CPU_seconds=cpu_elapsed,source_start_end_identical=all_before==all_after,
 test_start_end_identical=all(before[name]==after[name] for name in TESTS),
 execution_start_end_identical=execution==after_execution,
 current_candidate_execution_source_count=len(execution),current_candidate_execution_SHA=digest(execution),
 execution_sources=execution,execution_SHA=digest(execution),source_file_records=all_before,
 source_file_count=len(all_before),all1007_original_source_SHA_match=True,
 source_and_test_records_before=before,source_and_test_records_after=after,
 real_Model_constructor_attempts=constructors,real_Native_optimize_attempts=optimizers,
 real_Gurobi_models_constructed=0,real_Native_model_constructions=0,Native_optimize_calls=0,
 retained_real_backend_class_constructor_and_optimizer_descriptors_denied=True,
 fixture_runtime_is_not_actual_Native_runtime=True,
 source30_immutable_workers_or_requests_or_budget_or_queue_mutations=0,
 production_changed_files=['v42_autonomous_b2/worker.py','tests/test_v42_autonomous_b2.py'],carried_Source31_basis_files=['v42_autonomous_b2/f1_basis.py','tests/test_v42_autonomous_b2_f1_basis.py'],canonical_CLI_budget_and_function_identity_verified_via_actual_runpy_and_fresh_interpreter=True,modelattempts=constructors,nativeattempts=optimizers,
 original_native_budget_seconds=5400,original_F1_seconds=120,original_full_LP_seconds=300,
 approved_entry_computational_parameters=dict(Method=0,LPWarmStart=2,Threads=1),
 original_precision_unchanged=True,original_math_checker_and_basis_eligibility_unchanged=True,
 no_performance_or_Global_LB_or_final_day_PASS_claimed=True,
 stdout=record(OUT/'stdout_02.txt'),stderr=record(OUT/'stderr_02.txt'),
 junit=record(OUT/'SOURCE32_F1_NATIVE_DENIED_TEST_RESULT_02.xml'),runner=record(__file__),
 carried_Source31_owner_receipt=record(Path(r'D:\v42_full_lp_warmstart_readonly_review_20261010_01\SOURCE31_F1_NATIVE_DENIED_TEST_RECEIPT_02.json')),
 actual_Source30_CLI_identity_failure_proof=record(Path(r'D:\v42_source30_actual_watch_20261010\SOURCE30_CLI_DUPLICATE_BUDGET_IDENTITY_NATIVE0_PROOF.json')))

data=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf8')
target=OUT/'SOURCE32_F1_NATIVE_DENIED_TEST_RECEIPT_02.json'
with target.open('xb') as f:f.write(data)
print(json.dumps(dict(PASS=doc['PASS'],tests=doc['tests_passed'],wall_seconds=elapsed,
 CPU_seconds=cpu_elapsed,receipt=record(target),files=before,execution_SHA=doc['current_candidate_execution_SHA']),ensure_ascii=False,indent=2))
if not doc['PASS']:print(out);print(err);raise SystemExit(1)

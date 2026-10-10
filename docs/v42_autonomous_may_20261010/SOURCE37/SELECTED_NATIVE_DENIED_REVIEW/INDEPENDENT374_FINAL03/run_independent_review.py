import os
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import ast,hashlib,importlib,json,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
from contextlib import redirect_stdout,redirect_stderr
from unittest.mock import patch
REPO=Path('D:/MobileESS_v42_autonomous')
ROOT=Path('D:/v42_may_restart_20261010_02')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO));os.chdir(REPO)
TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_state.py','tests/test_v42_autonomous_b2_f1_basis.py','tests/test_v42_autonomous_b2_rmp_presolve.py','tests/test_v42_autonomous_b2_f1_price_seed.py']
HISTORY=[Path('D:/v42_source37_independent_review_20261010_01/INITIAL_HARNESS_FAILURE_HISTORY.json'),Path('D:/v42_source37_independent_review_20261010_02/INITIAL_POSTTEST_METADATA_FAILURE_HISTORY.json'),Path('D:/v42_source37_owner_review_20261010_02/INITIAL_HARNESS_FAILURE_HISTORY.json')]
CONTROL=Path('D:/v42_first_sweep_zero_contract_independent_review_20261010_01/FIRST_SWEEP_ZERO_CONTRACT_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')
RELOAD=Path('D:/v42_first_sweep_zero_contract_independent_review_20261010_01/FIRST_SWEEP_ZERO_CONTRACT_RELOAD_HELPER_STATIC_INDEPENDENT_REVIEW.json')
def read(p):return json.loads(Path(p).read_bytes().decode('utf-8-sig'))
def record(p):
 p=Path(p).resolve();h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def save(name,document):
 p=HERE/name;assert not p.exists();p.write_bytes((json.dumps(document,ensure_ascii=False,indent=2)+chr(10)).encode('utf-8'));return record(p)
parsed=ast.parse(Path(__file__).read_text(encoding='utf-8-sig'))
assert all(not any(ord(ch)<32 for ch in node.value) for node in ast.walk(parsed) if isinstance(node,ast.Constant) and isinstance(node.value,str))
assert all(p.is_file() for p in [*HISTORY,CONTROL,RELOAD,ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json',*[REPO/name for name in TESTS]])
historical=[record(p) for p in HISTORY];control=record(CONTROL);reload=record(RELOAD)
preload=['v42_autonomous_b2.pricing_cache','v42_autonomous_b2.rmp_presolve','v42_autonomous_b2.worker','v42_autonomous_b2.f1_basis','v42_autonomous_b2.f1_state','v42_autonomous_b2.dw_native','v42_autonomous_b2.f1_price_seed']
for name in preload:importlib.import_module(name)
from v42_autonomous_b2 import worker
import gurobipy as gp
import pytest
manifest=read(ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json')
def state():
 ex=worker.sources();union=dict(manifest['builder_original_sources'],**ex)
 assert len(manifest['builder_original_sources'])==1007 and len(ex)==99 and len(union)==1106
 records={name:record(REPO/name) for name in sorted(union)}
 assert all(records[name]['sha256']==sha for name,sha in manifest['builder_original_sources'].items())
 frozen={}
 for version in ('35','36','37'):
  p=ROOT/('autonomous/V'+version+'_SPARSE_IMMUTABLE_FREEZE.json');d=read(p)
  expected={item['path']:item['sha256'] for item in d['source_files']}
  assert len(expected)==1111
  actual={name:record(name)['sha256'] for name in expected}
  assert expected==actual
  frozen[version]=dict(receipt=record(p),source_SHA=actual)
 return dict(execution_sources=ex,execution_SHA=worker.digest(ex),source_file_records=records,test_file_records={name:record(REPO/name) for name in TESTS},frozen=frozen)
before=state();before_record=save('SOURCE37_INDEPENDENT_PRETEST_FULL_SOURCE_SNAPSHOT.json',before)
changed=[name for name in before['execution_sources'] if before['execution_sources'][name]!=manifest['execution_sources'][name]]
assert changed==['v42_autonomous_b2/worker.py']
assert all(before['execution_sources'][name]==record(Path('D:/v42run37')/name)['sha256'] for name in before['execution_sources'])
models=[];native=[];real=gp.Model
def deny_model(*args,**kwargs):models.append('REAL_MODEL_CONSTRUCTION_DENIED');raise AssertionError('SOURCE37_REAL_MODEL_DENIED')
def deny_native(*args,**kwargs):native.append('REAL_NATIVE_OPTIMIZE_DENIED');raise AssertionError('SOURCE37_REAL_NATIVE_DENIED')
xml=HERE/'SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED.xml';rawlog=HERE/'SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED_OUTPUT.log'
assert not xml.exists() and not rawlog.exists()
begin=time.perf_counter()
with patch.object(real,'__init__',deny_model),patch.object(real,'optimize',deny_native),patch.object(gp,'Model',deny_model):
 with rawlog.open('w',encoding='utf-8',newline='') as stream:
  with redirect_stdout(stream),redirect_stderr(stream):
   exit_code=pytest.main([*TESTS,'-q','-p','no:cacheprovider','--basetemp',str(REPO/'tmp/source37_independent_selected_03'),'--junitxml',str(xml)])
elapsed=time.perf_counter()-begin
after=state();after_record=save('SOURCE37_INDEPENDENT_POSTTEST_FULL_SOURCE_SNAPSHOT.json',after)
counter_record=save('SOURCE37_INDEPENDENT_POSTTEST_DENIAL_COUNTERS.json',dict(modelattempts=models,nativeattempts=native,exit_code=exit_code,elapsed_seconds=elapsed))
suites=list(ET.parse(xml).getroot().iter('testsuite'))
counts={key:sum(int(s.get(key,'0')) for s in suites) for key in ('tests','failures','errors','skipped')}
failures=[dict(name=c.get('name'),message=e.get('message')) for c in ET.parse(xml).getroot().iter('testcase') for e in c if e.tag in ('failure','error')]
skipped=[c.get('name') for c in ET.parse(xml).getroot().iter('testcase') if c.find('skipped') is not None]
ok=exit_code==0 and counts==dict(tests=374,failures=0,errors=0,skipped=0) and before==after and models==native==[]
receipt=dict(schema='SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED_V1',PASS=ok,status='PASS' if ok else 'FAIL',UTC=datetime.now(timezone.utc).isoformat(),cases_collected=counts['tests'],tests_passed=counts['tests']-counts['failures']-counts['errors']-counts['skipped'],tests=counts['tests'],exit_code=exit_code,failures=failures,errors=counts['errors'],skipped=skipped,statistics=counts,modelattempts=models,nativeattempts=native,model_attempts=models,native_attempts=native,Native_optimize_calls=0,real_Native_model_constructions=0,source_start_end_identical=before['source_file_records']==after['source_file_records'],execution_start_end_identical=before['execution_sources']==after['execution_sources'],test_start_end_identical=before['test_file_records']==after['test_file_records'],immutable35_36_37_each1111_start_end_identical=before['frozen']==after['frozen'],execution_sources=before['execution_sources'],execution_SHA=before['execution_SHA'],source_file_records=before['source_file_records'],test_file_records=before['test_file_records'],original_source_count=1007,execution_source_count=99,source_file_count=1106,elapsed_seconds=elapsed,raw_xml=record(xml),raw_stdout_stderr=record(rawlog),full_pretest_snapshot=before_record,full_posttest_snapshot=after_record,denial_counters=counter_record,runner=record(__file__),AST_all_string_constants_control_character_free=True,all_literal_historical_paths_validated_before_tests=True,historical_harness_failures=historical,independent_control165_receipt=control,independent_reload_helper_static_receipt=reload,original1007_equal_Source36=True,other98_execution_equal_Source36=True,changed_execution_files=changed,tests_selected=TESTS,protected_science_preloads_before_real_descriptor_denial=preload,Native_model_or_optimize_or_casebuild_or_replay_or_production_ops_by_auditor=0,Git_mutations=0,limitations=['Selected tests use synthetic Native-denied fixtures; no actual Source37 performance or GlobalLB/date PASS claim.','Current Source36 workers continue using their own immutable source; no process, request, ledger, queue or lease mutation by reviewer.','Two external observer harness failures are preserved separately and are not production failures.'])
final=save('SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED_RECEIPT.json',receipt)
print(json.dumps(dict(PASS=ok,statistics=counts,receipt=final,execution_SHA=before['execution_SHA'],modelattempts=models,nativeattempts=native)))
raise SystemExit(0 if ok else 1)

import os
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import hashlib,json,os,sys,time
from pathlib import Path
from datetime import datetime,timezone
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout,redirect_stderr

REPO=Path(r'D:\MobileESS_v42_autonomous');HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO));os.chdir(REPO)
from v42_autonomous_b2 import worker,f1_state,f1_basis,pricing_cache,rmp_presolve,dw_native,f1_price_seed
import gurobipy as gp
import pytest

TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_state.py',
 'tests/test_v42_autonomous_b2_f1_basis.py','tests/test_v42_autonomous_b2_rmp_presolve.py',
 'tests/test_v42_autonomous_b2_f1_price_seed.py']
MANIFEST=Path(r'D:\v42_may_restart_20261010_02\B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json')
def record(path):
 p=Path(path).resolve();h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def state():
 m=json.loads(MANIFEST.read_text(encoding='utf-8'));s=worker.sources();union=dict(m['builder_original_sources'],**s)
 assert len(m['builder_original_sources'])==1007 and len(s)==99 and len(union)==1106
 for n,h in m['builder_original_sources'].items():assert record(REPO/n)['sha256']==h
 return dict(execution_sources=s,execution_SHA=worker.digest(s),
  source_file_records={n:record(REPO/n) for n in sorted(union)},test_file_records={n:record(REPO/n) for n in TESTS})
CAMPAIGN=Path(r'D:42_may_restart_20261010_02')
def immutable_full_state():
 result={}
 for version in ('35','36'):
  receipt=CAMPAIGN/('autonomous/V'+version+'_SPARSE_IMMUTABLE_FREEZE.json')
  freeze=json.loads(receipt.read_bytes())
  declared={item['path']:item['sha256'] for item in freeze['source_files']}
  assert len(declared)==1111
  actual={name:record(name)['sha256'] for name in declared}
  assert actual==declared
  result[version]=dict(declared=declared,actual=actual,freeze_receipt=record(receipt))
 return result
frozen_before=immutable_full_state()
before=state()
immutable=Path(r'D:\v42run36');immutable_map={n:record(immutable/n)['sha256'] for n in before['source_file_records']}
assert all(before['source_file_records'][n]['sha256']==immutable_map[n] for n in before['source_file_records'] if n not in before['execution_sources'])
changed=[n for n in before['execution_sources'] if before['execution_sources'][n]!=immutable_map[n]]
assert changed==['v42_autonomous_b2/worker.py'],changed
source35_comparison=dict(immutable_root=str(immutable),original1007_equal=True,other98_execution_equal=True,
 changed_execution_files=changed,original_source_count=1007,execution_source_count=99,
 original_worker_sha256=immutable_map[changed[0]],future_worker_sha256=before['execution_sources'][changed[0]])
models=[];native=[];real=gp.Model
def deny_model(*args,**kwargs):models.append('REAL_MODEL_CONSTRUCTION_DENIED');raise AssertionError('SOURCE37_REAL_MODEL_DENIED')
def deny_native(*args,**kwargs):native.append('REAL_NATIVE_OPTIMIZE_DENIED');raise AssertionError('SOURCE37_NATIVE_OPTIMIZE_DENIED')
real.__init__=deny_model;real.optimize=deny_native;gp.Model=deny_model
begin=time.perf_counter();xml=HERE/'SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED.xml'
rawlog=HERE/'SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED_OUTPUT.log'
with rawlog.open('w',encoding='utf-8',newline='') as stream:
 with redirect_stdout(stream),redirect_stderr(stream):
  result=pytest.main([*TESTS,'-q','-p','no:cacheprovider','--basetemp',str(REPO/'tmp/source37_independent_selected_01'),'--junitxml',str(xml)])
elapsed=time.perf_counter()-begin;after=state();frozen_after=immutable_full_state()
root=ET.parse(xml).getroot();suites=list(root.iter('testsuite'))
tests=sum(int(s.attrib.get('tests',0)) for s in suites);fails=sum(int(s.attrib.get('failures',0)) for s in suites);errors=sum(int(s.attrib.get('errors',0)) for s in suites)
payload=dict(schema='SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED_V1',UTC=datetime.now(timezone.utc).isoformat(),
 status='PASS' if result==0 and before==after and frozen_before==frozen_after and not models and not native else 'FAIL',
 PASS=result==0 and before==after and frozen_before==frozen_after and not models and not native,tests=tests,failures=fails,errors=errors,
 pytest_exit_code=result,raw_stdout_stderr=record(rawlog),elapsed_seconds=elapsed,Native_optimize_calls=0,real_Native_model_constructions=0,
 model_attempts=models,native_attempts=native,source_start_end_identical=before['source_file_records']==after['source_file_records'],
 execution_start_end_identical=before['execution_sources']==after['execution_sources'],
 test_start_end_identical=before['test_file_records']==after['test_file_records'],
 execution_sources=before['execution_sources'],execution_SHA=before['execution_SHA'],source_file_records=before['source_file_records'],
 test_file_records=before['test_file_records'],source_file_count=1106,execution_source_count=99,original_source_count=1007,
 original1007_equal_Source36=True,full_commit_pending=True,raw_xml=record(xml),runner=record(__file__),
 command='python -B -X utf8 '+str(Path(__file__).resolve()),tests_selected=TESTS,
 comparison_to_immutable_Source36=source35_comparison,frozen35_36_each1111_start_end_identical=frozen_before==frozen_after,immutable_source_files=frozen_before,operational_actions=0,Git_actions=0,independent_control165_receipt=record(Path(r'D:42_first_sweep_zero_contract_independent_review_20261010_01\FIRST_SWEEP_ZERO_CONTRACT_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')),independent_controller_reload_static_receipt=record(Path(r'D:42_first_sweep_zero_contract_independent_review_20261010_01\FIRST_SWEEP_ZERO_CONTRACT_RELOAD_HELPER_STATIC_INDEPENDENT_REVIEW.json')),historical_initial_owner_failure=record(Path(r'D:42_source37_owner_review_20261010_02\INITIAL_HARNESS_FAILURE_HISTORY.json')),limitations=['No actual pricing/performance/GlobalLB improvement asserted.','Synthetic producer/F1/backend fixtures do not measure actual Native work.',
 'Unchanged pricing cache/mathematics and Native algorithms; five new existing-authority preflight rejection tests.'])
path=HERE/'SOURCE37_INDEPENDENT_SELECTED_NATIVE_DENIED_RECEIPT.json';assert not path.exists();path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(PASS=payload['PASS'],tests=tests,failures=fails,errors=errors,elapsed_seconds=elapsed,receipt=record(path),execution_SHA=before['execution_SHA'],model_attempts=models,native_attempts=native)));raise SystemExit(0 if payload['PASS'] else 1)

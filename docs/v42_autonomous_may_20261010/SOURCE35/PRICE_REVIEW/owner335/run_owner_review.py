import hashlib,json,os,sys,time
from pathlib import Path
from datetime import datetime,timezone
import xml.etree.ElementTree as ET

REPO=Path(r'D:\MobileESS_v42_autonomous');HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO));os.chdir(REPO)
from v42_autonomous_b2 import worker,f1_state,f1_basis,pricing_cache,rmp_presolve,dw_native,f1_price_seed
import gurobipy as gp
import pytest

TESTS=['tests/test_v42_autonomous_b2.py','tests/test_v42_autonomous_b2_f1_state.py',
 'tests/test_v42_autonomous_b2_f1_basis.py','tests/test_v42_autonomous_b2_rmp_presolve.py',
 'tests/test_v42_autonomous_b2_f1_price_seed.py']
MANIFEST=Path(r'D:\v42_may_restart_20261010_02\B2_V34_ZERO_START_DEPLOYMENT_MANIFEST.json')
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
before=state();models=[];native=[];real=gp.Model
def deny_model(*args,**kwargs):models.append('REAL_MODEL_CONSTRUCTION_DENIED');raise AssertionError('SOURCE35_REAL_MODEL_DENIED')
def deny_native(*args,**kwargs):native.append('REAL_NATIVE_OPTIMIZE_DENIED');raise AssertionError('SOURCE35_NATIVE_OPTIMIZE_DENIED')
real.__init__=deny_model;real.optimize=deny_native;gp.Model=deny_model
begin=time.perf_counter();xml=HERE/'SOURCE35_OWNER_SELECTED_NATIVE_DENIED.xml'
result=pytest.main([*TESTS,'-q','--basetemp',str(REPO/'tmp/source35_owner_selected_01'),'--junitxml',str(xml)])
elapsed=time.perf_counter()-begin;after=state()
root=ET.parse(xml).getroot();suites=list(root.iter('testsuite'))
tests=sum(int(s.attrib.get('tests',0)) for s in suites);fails=sum(int(s.attrib.get('failures',0)) for s in suites);errors=sum(int(s.attrib.get('errors',0)) for s in suites)
payload=dict(schema='SOURCE35_OWNER_SELECTED_NATIVE_DENIED_V1',UTC=datetime.now(timezone.utc).isoformat(),
 status='PASS' if result==0 and before==after and not models and not native else 'FAIL',
 PASS=result==0 and before==after and not models and not native,tests=tests,failures=fails,errors=errors,
 pytest_exit_code=result,elapsed_seconds=elapsed,Native_optimize_calls=0,real_Native_model_constructions=0,
 model_attempts=models,native_attempts=native,source_start_end_identical=before['source_file_records']==after['source_file_records'],
 execution_start_end_identical=before['execution_sources']==after['execution_sources'],
 test_start_end_identical=before['test_file_records']==after['test_file_records'],
 execution_sources=before['execution_sources'],execution_SHA=before['execution_SHA'],source_file_records=before['source_file_records'],
 test_file_records=before['test_file_records'],source_file_count=1106,execution_source_count=99,original_source_count=1007,
 original1007_equal_Source34=True,full_commit_pending=True,raw_xml=record(xml),runner=record(__file__),
 command='python -B -X utf8 '+str(Path(__file__).resolve()),tests_selected=TESTS,
 limitations=['No actual pricing/performance/GlobalLB improvement asserted.','Synthetic producer/F1/backend fixtures do not measure actual Native work.',
 'Unchanged pricing_cache120 tests carried from same bytes Source34; not rerun in this selected command.'])
path=HERE/'SOURCE35_OWNER_SELECTED_NATIVE_DENIED_RECEIPT.json';path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record(path)));raise SystemExit(result)

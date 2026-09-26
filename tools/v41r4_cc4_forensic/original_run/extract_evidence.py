import hashlib,json,tarfile,time
import sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
ARCHIVE=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz')
EXPECTED='1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3'
NAMES=set('PHYSICAL_EXECUTION_DISPATCH.parquet DELAYED_JOBS.parquet ACTUAL_EXECUTION_DELAY_KPIS.json ACTUAL_JOB_REPLAY.json DISPATCH_PRIORITY_AUTHORITY.json ACTUAL_EXECUTION_FEASIBILITY.json ACTUAL_EXECUTION_RATE.json NAIVE_RUNTIME_CONTENTION.json ACTUAL_MIGRATION_CLOCKS.parquet ACTUAL_MIGRATION_REPLAY_AUDIT.json H4_OPTIMIZER_WINDOWS.parquet H4_WINDOW_PREDICTIONS.parquet H4_ACTUAL_WINDOW_EVALUATION.parquet H4_COMPLETE_WINDOW_RESULTS.parquet H4_RAW_VS_ACTIONABLE_COVERAGE.json ACTUAL_RESERVE_DIAGNOSTIC_AUTHORITY.json ACTUAL_RUNTIME_INPUTS.parquet ACTUAL_SOURCE_MANIFEST.json ACTUAL_WORKLOAD_CONTRIBUTORS.parquet FROZEN_JOINT_DECISION.json JOB_DECISIONS.parquet JOB_REQUEST_INPUTS.parquet JOB_CLASSES.parquet JOB_DECISION_PAYLOAD.json H4_SCORE.json DA_FRESH_INPUT_SNAPSHOT.json ML_SNAPSHOT.json GENERATION_INPUT_IDENTITY.json SCIENTIFIC_MANIFEST.json UNIT_SCIENTIFIC_MANIFEST.json ACCEPTANCE.json UPSTREAM_SNAPSHOT.json FINAL_EXECUTION_AUDIT.json ACTUAL_BOUNDARY_RECEIPT.json ACTUAL_RECEIPT.json READY.json REFERENCE.json JOBS.json PLANNING_RESULT.json AIDC_FIELD_AUTHORITY.json'.split())
class Reader:
 def __init__(self,f): self.f=f;self.h=hashlib.sha256()
 def read(self,n=-1):
  b=self.f.read(n);self.h.update(b);return b
def main():
 before=ARCHIVE.stat(); records={}; selected={};t=time.monotonic();last=t
 with ARCHIVE.open('rb') as f:
  reader=Reader(f)
  with tarfile.open(fileobj=reader,mode='r|gz') as tf:
   for m in tf:
    p=PurePosixPath(m.name)
    assert m.isfile() and not p.is_absolute() and '..' not in p.parts and ':' not in m.name
    records[m.name]={'bytes':m.size}
    choose=(p.name in NAMES or m.name.endswith('.py') or len(p.parts)==2) if len(sys.argv)==1 else p.name in ({'METHOD_FREEZE.json','METHOD_CODE_BINDING.json','EXECUTION_BINDING.json','CANDIDATE_RECEIPT.json','COMPLETE.json'} if sys.argv[1]=='method' else {'REALIZED_WORKLOAD.json','REALIZED_WORKLOAD_CONTRIBUTORS.parquet','FINAL_ACTUAL_PHYSICAL_KPIS.json','COMMON_BINDING_REGRESSION.json','SOURCE_MANIFEST.json','V1_COMMON_INPUT_REUSE.json','DAILY_DOMAIN_AUTHORITY.json'})
    if choose:
     data=tf.extractfile(m).read(); h=hashlib.sha256(data).hexdigest()
     dest=ROOT/'evidence'/Path(*p.parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
     selected[m.name]={'bytes':len(data),'sha256':h}
    if time.monotonic()-last>25:
     print(json.dumps({'files_scanned':len(records),'selected':len(selected),'seconds':round(time.monotonic()-t)}),flush=True);last=time.monotonic()
  while reader.read(4*1024*1024):pass
 after=ARCHIVE.stat();assert reader.h.hexdigest()==EXPECTED
 assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
 manifest=json.loads((ROOT/'evidence/V41R4_May2025_raw/FILE_MANIFEST.json').read_text())
 expected={x['path']:x for x in manifest}
 for name,rec in selected.items():
  rel=name.split('/',1)[1]
  if rel in expected: assert rec['sha256']==expected[rel]['sha256'],name
 (ROOT/'archive_inventory.json').write_text(json.dumps(records),encoding='utf-8')
 mf=ROOT/((sys.argv[1]+'_evidence_manifest.json') if len(sys.argv)>1 else 'extracted_evidence_manifest.json')
 mf.write_text(json.dumps(selected,indent=2),encoding='utf-8')
 result=dict(status='PASS',archive=str(ARCHIVE),sha256=reader.h.hexdigest(),bytes=before.st_size,mtime_ns=before.st_mtime_ns,archive_files=len(records),extracted_files=len(selected),extracted_bytes=sum(v['bytes'] for v in selected.values()),seconds=time.monotonic()-t,archive_unchanged=True)
 (ROOT/((sys.argv[1]+'_extraction_verification.json') if len(sys.argv)>1 else 'archive_verification.json')).write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result),flush=True)
if __name__=='__main__':main()

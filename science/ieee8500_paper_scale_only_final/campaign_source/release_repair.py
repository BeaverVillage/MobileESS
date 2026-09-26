"""Verify retained scientific state, archive the failure, release explicit resume."""
from pathlib import Path
import json,hashlib,time,shutil,difflib,subprocess,sys
H=Path(__file__).absolute().parent
O=H/'recovery_stall'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert read(O/'NUMERICAL_REPAIR_PROOF.json')['status']=='PASS'
rows=read(O/'PRE_REPAIR_CHECKPOINT_SHA.json')
for r in rows:assert sha(Path(r['path']))==r['sha256'],r['path']
assert sha(H/'mess_runtime.py')==sha(O/'original_code/mess_runtime.py')
subprocess.run([sys.executable,'-X','utf8','-B',str(H/'verify_pipeline.py')],check=True)
diffs=[];files=[]
for name in ['mess_worker.py','campaign_supervisor.py','verify_pipeline.py','numerical_repair.py']:
 p=H/name;old=O/'original_code'/name
 diffs.extend(difflib.unified_diff(old.read_text(encoding='utf-8').splitlines(True) if old.exists() else [],p.read_text(encoding='utf-8').splitlines(True),fromfile='before/'+name,tofile='after/'+name))
 files.append(dict(path=str(p),sha256=sha(p),before_sha256=sha(old) if old.exists() else None))
(O/'REPAIR.diff').write_text(''.join(diffs),encoding='utf-8')
archive=O/('failure_archive_'+str(time.time_ns()));archive.mkdir()
for name in ['B2_FAILURE.json','SUPERVISOR_FAILURE.json','SUPERVISOR_STATUS.json']:
 p=H/name
 if p.exists():shutil.move(str(p),str(archive/name))
receipt=dict(status='PASS',unix=time.time(),preserved_checkpoint_files=len(rows),files=files,proof_sha256=sha(O/'NUMERICAL_REPAIR_PROOF.json'),original_scientific_cache_context_unchanged=True,original_certificate_tolerance=1e-8,changed_only='Extra strict numerical solver retry after existing retry fails; explicit resume and preserved logs',resume_from='B2 MESS04 second parent, retaining stages 1-3 and first parent',failure_archive=str(archive))
(O/'REPAIR_RELEASE.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))

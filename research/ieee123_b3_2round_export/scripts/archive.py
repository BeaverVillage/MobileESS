"""Copy immutable selected files into a streaming tar.gz; verify every member."""
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
import os,json,hashlib,tarfile,time,io,collections,gzip
OUT=Path(__file__).parent;ROOT=OUT.parent;RUN=ROOT/'production_v4_corrected';DEL=OUT/'deliverables'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def physical(p):return Path(str(p).replace('C:\\codex_mobileess_workspace\\','D:\\codex_mobileess_workspace\\')).absolute()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
inventory={};excluded=[];members={}
def add(p,name,expected=None,role='corrected_campaign_output'):
 p=physical(p);key=str(p)
 if key in inventory:
  if expected:assert inventory[key].get('expected_sha256') in (None,expected)
  return
 assert p.is_file(),str(p)
 if name in members:name=str(PurePosixPath(name).parent/hashlib.sha256(key.encode()).hexdigest()[:12]/p.name)
 assert name not in members,name
 assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
 s=p.stat();inventory[key]=dict(source_path=key,archive_path=name,bytes=s.st_size,mtime_ns=s.st_mtime_ns,expected_sha256=expected,role=role);members[name]=key
SKIP_DIRS={'native','__pycache__','SLOT_START_CACHE','search_cache','node_modules','.git','.venv','venv','tmp','temp'}
def scan(root,prefix):
 for folder,dirs,files in os.walk(root,followlinks=False):
  for d in list(dirs):
   if d in SKIP_DIRS:
    excluded.append(dict(path=str(Path(folder)/d),reason='disposable cache/runtime scratch'));dirs.remove(d)
  for f in files:
   p=Path(folder)/f
   if p.suffix.lower() in ('.pyc','.tmp','.lock') or f.lower().startswith('nodefile'):
    excluded.append(dict(path=str(p),reason='temporary/compiled/nodefile'));continue
   add(p,prefix+'/'+p.relative_to(root).as_posix())
scan(RUN,'corrected_campaign')
for p in ROOT.glob('*.json'):
 if p.name in ['INVALIDATED_2ROUND_RUN_MANIFEST.json','M2_ROUND1_FINAL_BOUNDARY_FREEZE.json','ROUND1_VARIABLE_STATES.json','M1_TRAFFIC_AND_SETTINGS.json','AUTHORITY_INTAKE.json','PRESERVATION_VERIFICATION.json','PROTECTED_FILES_EXTENDED.json']:
  add(p,'audit/'+p.name,role='authority_or_provenance')
for p in (ROOT/'authority_recovery').glob('*.json'):add(p,'authority_recovery/'+p.name,role='authority_recovery_contract')
for p in (ROOT/'repair_03_compound_readback').iterdir():
 if p.is_file() and p.suffix in ('.json','.md'):add(p,'repair_history/May25/'+p.name,role='completed_solver_resume_evidence')
for day in [f'2025-05-{n:02}' for n in range(1,32)]:
 m=read(RUN/'runs'/day/'B3/dayahead/M1/M1_RESULT.json');search=physical(m['inherited_search_root'])
 for p in search.glob('*.json'):add(p,'M1_search_receipts/'+day+'/'+p.name,role='original_M1_search_identity_and_progress')
 excluded.append(dict(path=str(search/'search_cache'),reason='disposable route candidate cache; accepted fleet and search identity retained'))
coeff=read(ROOT/'authority_recovery/ORIGINAL_OPERATING_COEFFICIENTS_RECHECK.json')
assert coeff['output_files_verified']==124 and coeff['gradient_values_checked']==10285056 and coeff['unequal_gradient_values']==0
for day in coeff['days']:
 for kind,ref in day['output_files'].items():add(ref['path'],'original_operating_coefficients/'+day['day']+'/'+Path(ref['path']).name,ref['sha256'],'original_SHA_verified_operating_coefficient')
transitive=read(ROOT/'authority_recovery/TRANSITIVE_AUTHORITY_RECHECK.json');assert not transitive['failures']
for ref in transitive['matched']:
 p=physical(ref['resolved_path']);assert p.name not in ('V40E_CORRECTED_APRIL_FULL_BUS_PHASE_SENSITIVITY.parquet','V40E_CORRECTED_APRIL_LOCAL_SENSITIVITY.parquet')
 add(p,'authority_inputs/'+ref['sha256'][:16]+'/'+p.name,ref['sha256'],'original_transitive_authority_input')
ex=read(OUT/'EXTRACTION_MANIFEST.json')
for key,ref in ex['sources'].items():
 p=physical(key)
 # Diagnostic fixtures cited only as historical gate evidence are not raw production results.
 if 'corrected_model_diagnostic' in p.parts:
  excluded.append(dict(path=str(p),reason='diagnostic fixture; SHA is recorded by source manifest, not production raw'));continue
 add(p,'paper_source_artifacts/'+ref['sha256'][:16]+'/'+p.name,ref['sha256'],'raw_paper_source_or_authority_receipt')
for p in [OUT/'extract.py',OUT/'build_csv.mjs',OUT/'archive.py',OUT/'EXTRACTION_MANIFEST.json']:
 add(p,'export_provenance/'+p.name,role='read_only_extraction_and_packaging_provenance')
plan=dict(created_at=datetime.now(timezone.utc).isoformat(),files=list(inventory.values()),excluded=excluded,
 excluded_entire_scopes=['invalidated production_v1/v2/v3','incorrect MESS-OFF diagnostic runs','regenerated historical sensitivities','Python environments','Gurobi nodefiles','IEEE8500','whole source repository'],
 historical_lineage_complete=False,original_final_coefficient_files=124,planning_gradient_values=10285056)
(OUT/'ARCHIVE_PLAN.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
DEL.mkdir(exist_ok=True);archive=DEL/'IEEE123_B3_2ROUND_MAY2025_RAW_RESULTS.tar.gz'
assert not archive.exists(),'OUTPUT_ALREADY_EXISTS'
total=sum(r['bytes'] for r in inventory.values());print('ARCHIVE_PLAN',len(inventory),total,flush=True)
started=time.time();written=[]
class HashReader:
 def __init__(self,f):self.f=f;self.h=hashlib.sha256()
 def read(self,n=-1):
  data=self.f.read(n);self.h.update(data);return data
with tarfile.open(archive,'w:gz',compresslevel=1,format=tarfile.PAX_FORMAT,dereference=True) as tar:
 for n,r in enumerate(inventory.values(),1):
  p=Path(r['source_path']);before=p.stat();assert (before.st_size,before.st_mtime_ns)==(r['bytes'],r['mtime_ns'])
  info=tar.gettarinfo(str(p),arcname=r['archive_path']);info.uid=info.gid=0;info.uname=info.gname='';info.type=tarfile.REGTYPE;info.linkname=''
  with p.open('rb') as f:
   reader=HashReader(f);tar.addfile(info,reader);r['sha256']=reader.h.hexdigest()
  after=p.stat();assert (after.st_size,after.st_mtime_ns)==(r['bytes'],r['mtime_ns'])
  if r['expected_sha256']:assert r['sha256']==r['expected_sha256'],str(p)
  written.append(r)
  if n%2000==0:print('ARCHIVED',n,'/',len(inventory),flush=True)
 internal=dict(schema='RAW_ARCHIVE_MEMBER_SHA256_V1',files=written,exclusions=excluded,exclusion_scopes=plan['excluded_entire_scopes'],
  source_changes=0,source_commit=read(ROOT/'AUTHORITY_INTAKE.json')['source_commit'],campaign_authority=read(RUN/'EXECUTION_AUTHORIZATION.json'),
  timestamp=datetime.now(timezone.utc).isoformat(),historical_lineage_complete=False)
 data=json.dumps(internal,ensure_ascii=False,indent=2).encode('utf-8');info=tarfile.TarInfo('ARCHIVE_CONTENTS.json');info.size=len(data);info.mtime=int(time.time());tar.addfile(info,io.BytesIO(data))
print('ARCHIVE_WRITTEN_VERIFYING',archive.stat().st_size,flush=True)
expected={r['archive_path']:r for r in written};count=0;seen=set();internal_sha=hashlib.sha256(data).hexdigest()
# Full gzip stream is consumed, checking gzip CRC/trailer as well as every member hash.
with gzip.open(archive,'rb') as gz:
 with tarfile.open(fileobj=gz,mode='r|') as tar:
  for member in tar:
   assert member.isfile() and member.name not in seen;seen.add(member.name)
   assert not PurePosixPath(member.name).is_absolute() and '..' not in PurePosixPath(member.name).parts
   f=tar.extractfile(member);h=hashlib.sha256()
   while block:=f.read(8*1024*1024):h.update(block)
   if member.name=='ARCHIVE_CONTENTS.json':assert h.hexdigest()==internal_sha
   else:
    r=expected[member.name];assert member.size==r['bytes'] and h.hexdigest()==r['sha256'],member.name
   count+=1
   if count%4000==0:print('VERIFIED',count,flush=True)
 while gz.read(8*1024*1024):pass
assert count==len(written)+1
for r in written:
 s=Path(r['source_path']).stat();assert (s.st_size,s.st_mtime_ns)==(r['bytes'],r['mtime_ns'])
manifest=dict(schema='IEEE123_B3_2ROUND_MAY2025_ARCHIVE_V1',archive_filename=archive.name,sha256=sha(archive),total_size_bytes=archive.stat().st_size,
 included_file_count=count,source_file_count=len(written),uncompressed_source_bytes=total,creation_timestamp=datetime.now(timezone.utc).isoformat(),
 source_root_paths=[str(RUN),str(ROOT/'m4'),str(ROOT/'authority_recovery'),str(ROOT/'repair_03_compound_readback'),str(Path(r'D:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')),str(ROOT.parent/'v41r4_final_results_pr')],
 source_git_HEAD=read(ROOT/'AUTHORITY_INTAKE.json')['source_commit'],campaign_authority=read(RUN/'EXECUTION_AUTHORIZATION.json'),campaign_gate=read(RUN/'PRODUCTION_GATE.json')['status'],
 integrity_test=dict(status='PASS',full_gzip_CRC_checked=True,tar_headers_and_safe_paths_checked=True,member_SHA256_verified=count,archive_contents_sha256=internal_sha),
 source_authority_consistency='PASS',source_modification_check='PASS; before/after size and nanosecond mtime identical; archive hashes match captured/authority hashes',
 historical_lineage_complete=False,missing_historical_sensitivity_files=read(ROOT/'authority_recovery/RECOVERY_CONTRACT.json')['missing_historical_lineage'],
 exclusions=plan['excluded_entire_scopes'],member_inventory='ARCHIVE_CONTENTS.json inside archive',wall_seconds=time.time()-started)
(DEL/'IEEE123_B3_2ROUND_MAY2025_ARCHIVE_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
(OUT/'ARCHIVE_VERIFIED.json').write_text(json.dumps(dict(status='PASS',sha256=manifest['sha256'],bytes=manifest['total_size_bytes'],files=count),indent=2))
print('ARCHIVE_INTEGRITY_PASS',json.dumps(dict(sha256=manifest['sha256'],bytes=manifest['total_size_bytes'],files=count)),flush=True)

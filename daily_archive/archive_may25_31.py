"""Verified, restartable May25--31 export. Never deletes before full comparison."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,hashlib,os,time,zipfile,shutil,sys,psutil,threading
from . import common as a

BASE=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1')
EQ=Path('D:/MobileESS_V44/runtime/equipment_versions/V44_R043_MESS_TX825_THERMAL_V1')
DEST=a.DEST
HOME=Path('D:/MobileESS_V44/development/archive_may25_31_20261023')
REPORT=DEST/'V44_2025-05-25_31_VERIFICATION.json'
DAYS=tuple(f'2025-05-{n:02d}' for n in range(25,32))
a.AUDIT=HOME
LOCK=threading.RLock()

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def campaign(day):return BASE/('campaign006_may15_21' if day<='2025-05-21' else 'campaign007_may22_31')
def roots(day):return [campaign(day)/day]+sorted(p/day for p in EQ.iterdir() if p.is_dir() and (p/day).is_dir())
def checked(root,day):
 if day not in DAYS or root.name!=day or not root.is_dir():raise ValueError('EXACT_MAY25_31_DATE_DIRECTORY_REQUIRED')
 expected=roots(day)
 if root.resolve() not in [p.resolve() for p in expected]:raise ValueError('DELETE_ROOT_OUT_OF_SCOPE')
 if root.parent.resolve()!=campaign(day).resolve() and not root.parent.resolve().is_relative_to(EQ.resolve()):raise ValueError('DELETE_ROOT_ESCAPE')
 a.signature(root)

def live_check(day):
 registry=read('D:/MobileESS_V44/runtime/ACTIVE_EQUIPMENT_LEDGER.json')
 b2=registry.get('B2_state') or {}
 for j in registry.get('jobs',[]):
  if j['day']==day and j['status'] not in ('PASS','FAILED','ACTUAL_FAILED','EXCLUDED'):raise ValueError('TARGET_DATE_NOT_TERMINAL:'+str(j))
 for p in psutil.process_iter(['pid','cmdline']):
  try:
   args=p.info['cmdline'] or []
   if p.pid!=os.getpid() and any(x in args for x in ('--worker','--case')) and any(day in str(x) for x in args):raise PermissionError('LIVE_DATED_WORKER:'+str(p.pid))
  except (psutil.AccessDenied,psutil.NoSuchProcess):pass
 for root in roots(day):
  checked(root,day)
  for start in root.glob('*/attempt*/START.json'):
   who=read(start)
   try:
    if abs(psutil.Process(who['pid']).create_time()-who['process_created'])<.001:raise PermissionError('LIVE_TARGET_PROCESS:'+str(start))
   except (psutil.NoSuchProcess,KeyError):pass
 return b2

def pins():
 """Retain exact immutable authority inputs and B2 release-gate metadata."""
 selected={};seen=set();queue=list(Path('D:/').glob('v44*/AUTHORIZATION.json'))
 queue+=list((EQ/'campaign007_may22_31_B2_fixedB3_followup/CONTROLLERS').glob('*/AUTHORIZATION.json'))
 queue+=[Path('D:/MobileESS_V44/runtime/V44_iteration2/OPERATIONS/AUTHORIZATION.json')]
 targets=[p.resolve() for d in DAYS for p in roots(d)]
 def visit(value):
  if isinstance(value,dict):
   if all(k in value for k in ('path','bytes','sha256')):
    p=Path(value['path'])
    if p.is_file():
     if any(p.resolve().is_relative_to(r) for r in targets):selected[str(p.resolve())]=dict(path=str(p),bytes=value['bytes'],sha256=value['sha256'],reason='IMMUTABLE_AUTHORITY_RECEIPT')
     elif p.suffix.lower()=='.json' and p.stat().st_size<10*2**20 and (p.name=='AUTHORIZATION.json' or p.name.endswith('_MANIFEST.json') or p.name in ('BASE_BATCH_STATE.json','BASELINE_CATALOG.json','PRESERVED.json')):queue.append(p)
   for x in value.values():visit(x)
  elif isinstance(value,list):
   for x in value:visit(x)
 while queue:
  p=queue.pop();key=str(p.resolve())
  if key in seen or not p.is_file():continue
  seen.add(key)
  try:visit(read(p))
  except (ValueError,UnicodeError):continue
 # Safety.inspect_b2 must still inspect every preserved Native ledger and checkpoint.
 b2=EQ/'campaign007_may22_31_B2_fixedB3_followup'
 for d in DAYS:
  root=b2/d
  if not root.exists():continue
  for p in root.rglob('*.json'):
   if p.name in ('START.json','ACTUAL_START.json','RESULT.json','progress.json') or p.name.endswith('LEDGER.json') or p.name.endswith('STAGE_CHECKPOINT.json'):
    selected[str(p.resolve())]=dict(path=str(p),bytes=p.stat().st_size,sha256=a.digest_file(p),reason='LIVE_B2_AUTHORITY_AND_RELEASE_GATE')
 for r in selected.values():
  p=Path(r['path'])
  if p.stat().st_size!=r['bytes'] or a.digest_file(p)!=r['sha256']:raise ValueError('PIN_RECEIPT_DRIFT:'+str(p))
 result=dict(files=list(selected.values()),authority_roots_scanned=sorted(seen),UTC=a.now())
 a.atomic_json(HOME/'RETAINED_VALIDATION_METADATA.json',result);return result['files']

def save(report):
 with LOCK:
  report['days'].sort(key=lambda r:r['day']);a.atomic_json(REPORT,report);a.atomic_json(HOME/'verification_report.json',report)

def export(day,report,preserved):
 live_check(day);camp=campaign(day);source=camp/day;target=DEST/f'V44_IEEE123_{day}.zip';partial=target.with_suffix('.zip.partial')
 if target.exists():raise FileExistsError('EXISTING_FINAL_ARCHIVE_REQUIRES_VERIFIED_RESUME:'+str(target))
 inventories={};items=[];directories=[]
 for root in roots(day):
  checked(root,day);files,dirs=a.tree_inventory(root);inventories[str(root)]=(files,dirs)
  prefix=day if root==source else 'equipment_versions/'+root.relative_to(EQ.parent).as_posix()
  directories += [prefix+'/']+[prefix+'/'+d+'/' for d in sorted(dirs)]
  items += [(root/rel,prefix+'/'+rel,sig,True) for rel,sig in sorted(files.items())]
 # Freeze shared metadata at export time: the current campaign journals may advance.
 support=HOME/'support_snapshots'/day;support.mkdir(parents=True,exist_ok=True)
 supports=list(camp.glob('*.json'))+list((camp/'requests').glob(day+'*'))+list((camp/'B1_A1').glob(day+'*'))
 if (camp/'references'/day).is_dir():supports+=list((camp/'references'/day).rglob('*'))
 for p in sorted(set(supports)):
  if not p.is_file():continue
  rel=p.relative_to(camp);copy=support/rel;copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(p.read_bytes())
  items.append((copy,'campaign_support/'+rel.as_posix(),a.signature(copy),False))
 total=sum(sig[0] for _,_,sig,_ in items);a.emit('COMPRESS_START',day=day,files=len(items),bytes=total)
 records=[]
 if partial.exists():raise FileExistsError('PARTIAL_OUTPUT_REQUIRES_INSPECTION:'+str(partial))
 with a.StreamingOutput(partial) as output,zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
  for name in directories:z.writestr(name,b'')
  done=0
  for n,(p,name,sig,result) in enumerate(items,1):
   if a.signature(p)!=sig:raise ValueError('SOURCE_CHANGED_BEFORE_EXPORT:'+str(p))
   info=zipfile.ZipInfo.from_file(p,arcname=name);info.compress_type=zipfile.ZIP_STORED if p.suffix.lower() in ('.gz','.zip','.7z') else zipfile.ZIP_DEFLATED;info._compresslevel=1
   h=hashlib.sha256();size=0
   with p.open('rb') as incoming,z.open(info,'w',force_zip64=True) as out:
    for block in iter(lambda:incoming.read(a.CHUNK),b''):out.write(block);h.update(block);size+=len(block)
   if size!=sig[0] or a.signature(p)!=sig:raise ValueError('SOURCE_CHANGED_DURING_EXPORT:'+str(p))
   records.append(dict(path=name,logical_path=str(p) if result else None,bytes=size,mtime_ns=sig[1],sha256=h.hexdigest()));done+=size
   a.progress('COMPRESS',day,n,len(items),done,total)
  manifest=dict(version=2,day=day,created=a.now(),source=str(source),campaign=str(camp),source_roots=list(inventories),directories=directories,files=records,source_result_files=sum(len(v[0]) for v in inventories.values()),source_result_bytes=sum(s[0] for f,_ in inventories.values() for s in f.values()),total_uncompressed_bytes=total,scope='All original750 and equipment825 B0-B3 attempts; frozen support snapshots; no dates outside May25-31')
  z.writestr('_ARCHIVE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False))
 with partial.open('r+b') as f:os.fsync(f.fileno())
 a.emit('VERIFY_START',day=day,archive_bytes=partial.stat().st_size,files=len(items));done=0
 with zipfile.ZipFile(partial) as z:
  expected=set(directories)|{r['path'] for r in records}|{'_ARCHIVE_MANIFEST.json'}
  if len(z.namelist())!=len(expected) or set(z.namelist())!=expected:raise ValueError('ZIP_ENTRY_SET_DRIFT')
  if json.loads(z.read('_ARCHIVE_MANIFEST.json'))!=manifest:raise ValueError('ZIP_MANIFEST_DRIFT')
  for n,((p,name,sig,_),r) in enumerate(zip(items,records),1):
   if a.signature(p)!=sig:raise ValueError('SOURCE_CHANGED_BEFORE_VERIFY')
   h=hashlib.sha256();size=0
   with p.open('rb') as original,z.open(name) as archived:
    while True:
     before=original.read(a.CHUNK);after=archived.read(a.CHUNK)
     if before!=after:raise ValueError('ARCHIVE_BYTE_MISMATCH:'+str(p))
     if not before:break
     h.update(after);size+=len(after)
   if h.hexdigest()!=r['sha256'] or size!=r['bytes'] or a.signature(p)!=sig:raise ValueError('ARCHIVE_SHA_OR_SIZE_DRIFT:'+str(p))
   done+=size;a.progress('VERIFY',day,n,len(items),done,total)
 for name,old in inventories.items():
  if a.tree_inventory(Path(name))!=old:raise ValueError('SOURCE_INVENTORY_CHANGED:'+name)
 os.rename(partial,target);sha=a.digest_file(target)
 entry=dict(day=day,source=str(source),source_roots=list(inventories),archive=str(target),archive_bytes=target.stat().st_size,archive_sha256=sha,result_files=manifest['source_result_files'],result_bytes=manifest['source_result_bytes'],archived_total_files=len(items),archived_total_bytes=total,verified=a.now(),verification='Full byte comparison, per-file SHA256, ZIP CRC, full inventory unchanged',original_deleted=False,common_support_originals_retained=True)
 # Publish the archive location before any deletion, so all readers can reconnect.
 with LOCK:
  report['days'].append(entry);save(report)
  rows=[r for r in report['days'] if Path(r['source']).parent==camp]
  a.atomic_json(camp/'ARCHIVED_RESULTS_20250525_31.json',dict(status='VERIFIED_ARCHIVES',days=rows,verification_report=str(REPORT)))
 a.emit('VERIFIED_DELETE_HELD_UNTIL_CONNECTION_CHECK',day=day,archive_sha256=sha)
 # Verify this published archive and every original baseline receipt before deleting.
 from v44_iteration2.archives import Store
 from v44_iteration2 import config as c
 store=Store()
 try:
  for row in read(c.DOC/'BASELINE_CATALOG.json')['days']:
   for receipt in row['evidence']:
    actual=store.record(receipt['path'])
    if any(actual[k]!=receipt[k] for k in ('path','bytes','sha256')):raise ValueError('ARCHIVE_BASELINE_CONNECTION_DRIFT:'+receipt['path'])
  for item in manifest['files']:
   if item.get('logical_path') and not store.exists(item['logical_path']):raise ValueError('ARCHIVE_LOGICAL_MEMBER_NOT_CONNECTED')
 finally:store.close()
 a.atomic_json(HOME/(day+'_CONNECTION_READY.json'),dict(PASS=True,UTC=a.now(),all31_baseline_receipts_verified=True,archive_sha256=sha))
 live_check(day);deleted=kept_bytes=kept_files=0
 for name,(files,dirs) in inventories.items():
  root=Path(name);checked(root,day)
  if a.tree_inventory(root)!=(files,dirs):raise ValueError('SOURCE_CHANGED_IMMEDIATELY_BEFORE_DELETE:'+name)
  kept=[r for r in preserved if Path(r['path']).resolve().is_relative_to(root.resolve())]
  for r in kept:
   if Path(r['path']).stat().st_size!=r['bytes'] or a.digest_file(Path(r['path']))!=r['sha256']:raise ValueError('PIN_CHANGED_BEFORE_DELETE')
  a.emit('DELETE_START',day=day,exact_absolute_path=str(root.resolve()),retained_files=len(kept))
  a.delete_results_keep_validation(root,files,dirs,kept)
  if not a.check_remaining_metadata(root,kept):raise ValueError('DELETE_VERIFICATION_FAILED')
  kept_bytes+=sum(r['bytes'] for r in kept);kept_files+=len(kept);deleted+=sum(v[0] for v in files.values())-sum(r['bytes'] for r in kept)
 with LOCK:
  entry.update(original_deleted=True,deleted_at=a.now(),result_bytes_deleted=deleted,result_files_deleted=entry['result_files']-kept_files,retained_validation_bytes=kept_bytes,retained_validation_files=kept_files)
  save(report);rows=[r for r in report['days'] if Path(r['source']).parent==camp]
  a.atomic_json(camp/'ARCHIVED_RESULTS_20250525_31.json',dict(status='VERIFIED_RESULTS_ARCHIVED_REQUIRED_VALIDATION_METADATA_RETAINED',days=rows,verification_report=str(REPORT)))
 a.emit('DAY_COMPLETE',day=day,archive_bytes=entry['archive_bytes'],deleted_bytes=deleted,retained_validation_bytes=kept_bytes)

def main():
 HOME.mkdir(parents=True,exist_ok=True);DEST.mkdir(parents=True,exist_ok=True)
 if REPORT.exists():raise FileExistsError('EXISTING_REPORT_REQUIRES_INSPECTION')
 for day in DAYS:live_check(day)
 psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS);a.emit('RUN_START',scope='May25-31 only',workers=2)
 preserved=pins();report=dict(started=a.now(),status='RUNNING',destination=str(DEST),days=[],workers=2,retained_validation_metadata=str(HOME/'RETAINED_VALIDATION_METADATA.json'))
 save(report);errors=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  work={pool.submit(export,d,report,preserved):d for d in DAYS}
  for future in as_completed(work):
   try:future.result()
   except BaseException as error:
    row=dict(day=work[future],error=repr(error));errors.append(row);a.emit('DATE_ERROR',**row)
 report.update(status='ERROR' if errors else 'COMPLETE',errors=errors,finished=a.now(),total_archive_bytes=sum(r['archive_bytes'] for r in report['days']),total_result_bytes_deleted=sum(r.get('result_bytes_deleted',0) for r in report['days']),total_files_verified=sum(r['archived_total_files'] for r in report['days']))
 save(report);a.emit('ALL_COMPLETE' if not errors else 'ERROR',status=report['status'],days=len(report['days']),errors=errors)
 if errors:raise RuntimeError(errors)

if __name__=='__main__':main()

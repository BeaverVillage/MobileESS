"""Lossless read-only IEEE8500 workspace snapshot; no scientific execution."""
import json,tarfile,hashlib,time,io,datetime,os
from pathlib import Path
W=Path(r'D:\ChatGPT\Mobile ESS 2')
OUT=Path(__file__).resolve().parent.parent
DEST=OUT.parent
LIVE=W/'IEEE8500_B2_actual_availability_gating_20260912_r3'
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def status(stage,**k):write(OUT/'_work/EXPORT_STATUS.json',dict(stage=stage,time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**k))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
class Reader:
 def __init__(self,f):self.f=f;self.h=hashlib.sha256();self.n=0
 def read(self,n=-1):
  b=self.f.read(n);self.h.update(b);self.n+=len(b);return b
def main():
 state=json.loads((LIVE/'STATUS.json').read_text(encoding='utf-8'))
 if state.get('status') not in ['PASS','FAIL_CLOSE']:raise RuntimeError('B2 is not terminal; archive must wait')
 # Completed writer must have finished its final status/manifest before inventory.
 time.sleep(2)
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
 path=DEST/('IEEE8500_ALL_RAW_RESULTS_'+stamp+'.tar.gz')
 assert not path.exists()
 dirs=sorted(p for p in W.glob('IEEE8500*') if p.is_dir())
 files=sorted({p for d in dirs for p in d.rglob('*') if p.is_file()}|{p for p in W.glob('IEEE8500*') if p.is_file()})
 inventory=[];total=sum(p.stat().st_size for p in files)
 index=dict(scope='ALL_FILES_IN_ALL_IEEE8500_WORKSPACE_DIRECTORIES',directories=[p.name for p in dirs],source_file_count=len(files),source_bytes=total,B2_actual_terminal_state=state,final_DA={'B0':'IEEE8500_v41r4_production_20260911_r2/B0/FINAL.json','B1':'IEEE8500_v41r4_production_20260911_r2/B1/FINAL_AUTHORITY.json','B2':'IEEE8500_B2_physical_closure_20260912_r2/B2_RESTORED_ACCEPTANCE.json','B3':'IEEE8500_B3_production_20260912/B3/FINAL_AUTHORITY.json'},final_Actual={'B0':'IEEE8500_actual_20260912_r3/B0/COMPLETE.json','B1':'IEEE8500_actual_20260912_r3/B1/COMPLETE.json','B2':'IEEE8500_B2_actual_availability_gating_20260912_r3/FINAL_ACCEPTANCE.json','B3':'IEEE8500_actual_20260912_r3/B3/COMPLETE.json'},historical_evidence='All earlier failed/stopped/diagnostic/pre-binding attempts retained verbatim. They do not supersede final scope-specific authorities. Prior availability_gating_r2 STATUS may still say RUNNING; r3 STOPPED_PREVIOUS_RUN.json records its actual stop.',external_dependencies='References to external IEEE123/V41R4 source, workload and SUMO inputs are preserved in frozen manifests; this is an all-IEEE8500-raw-results archive, not a relocated self-contained software environment. External IEEE123 result campaigns are not copied.',scientific_execution_count_for_export=0)
 status('ARCHIVING',archive=str(path),source_files=len(files),source_bytes=total)
 with tarfile.open(path,'w:gz',compresslevel=1,format=tarfile.PAX_FORMAT) as tar:
  done=0
  for i,p in enumerate(files):
   before=p.stat();name=p.relative_to(W).as_posix()
   info=tar.gettarinfo(str(p),arcname=name)
   # Store file bytes even for a file symlink; directories were explicitly enumerated.
   info.type=tarfile.REGTYPE;info.linkname='';info.size=before.st_size
   with p.open('rb') as f:
    reader=Reader(f);tar.addfile(info,reader)
   after=p.stat()
   if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or reader.n!=before.st_size:raise RuntimeError('Source changed while archiving: '+str(p))
   inventory.append(dict(path=name,bytes=before.st_size,sha256=reader.h.hexdigest(),mtime_ns=before.st_mtime_ns))
   done+=before.st_size
   if i%250==0:status('ARCHIVING',archive=str(path),files_done=i+1,source_files=len(files),bytes_done=done,source_bytes=total)
  for name,obj in [('ARCHIVE_METADATA/AUTHORITY_INDEX.json',index),('ARCHIVE_METADATA/FILE_SHA256_MANIFEST.json',inventory)]:
   b=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf-8');ti=tarfile.TarInfo(name);ti.size=len(b);ti.mtime=time.time();tar.addfile(ti,io.BytesIO(b))
 status('VERIFYING_ARCHIVE',archive=str(path))
 lookup={r['path']:r for r in inventory};members=0;seen=set()
 with tarfile.open(path,'r|gz') as tar:
  for m in tar:
   if m.name in seen:raise RuntimeError('Duplicate tar member: '+m.name)
   seen.add(m.name);members+=1
   stream=tar.extractfile(m);h=hashlib.sha256();n=0
   for b in iter(lambda:stream.read(8*1024*1024),b''):h.update(b);n+=len(b)
   if m.name in lookup and (h.hexdigest()!=lookup[m.name]['sha256'] or n!=lookup[m.name]['bytes']):raise RuntimeError('Archive readback mismatch: '+m.name)
   if members%1000==0:status('VERIFYING_ARCHIVE',archive=str(path),members_verified=members)
 assert len(lookup)==len(files) and members==len(files)+2
 status('VERIFYING_SOURCE_PRESERVATION',archive=str(path))
 for i,r in enumerate(inventory):
  p=W/r['path'];s=p.stat()
  if s.st_size!=r['bytes'] or s.st_mtime_ns!=r['mtime_ns'] or sha(p)!=r['sha256']:raise RuntimeError('Source preservation check failed: '+str(p))
  if i%1000==0:status('VERIFYING_SOURCE_PRESERVATION',archive=str(path),files_verified=i+1)
 index.update(archive_path=str(path),archive_sha256=sha(path),archive_bytes=path.stat().st_size,member_count=members,source_preservation='ALL_SHA256_SIZE_MTIME_UNCHANGED',archive_readback='ALL_FILE_BYTES_SHA256_MATCH',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 write(Path(str(path)+'_INDEX.json'),index)
 write(Path(str(path)+'_FILE_MANIFEST.json'),inventory)
 Path(str(path)+'.sha256').write_text(index['archive_sha256']+'  '+path.name+'\n',encoding='ascii')
 write(OUT/'_work/ARCHIVE_READY.json',index)
 status('ARCHIVE_VERIFIED',archive=str(path),**{k:index[k] for k in ['archive_bytes','member_count','source_file_count','archive_sha256']})
 print(json.dumps(index,ensure_ascii=False),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:status('EXPORT_FAIL_CLOSE',error=repr(e));raise

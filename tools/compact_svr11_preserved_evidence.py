"""NTFS-compress closed evidence in place; never delete a path or alter bytes.

Only historical date JSON/CSV/logs are admitted. No raw data, model cache,
Source, May18 evidence, active date, shared inode or mutable campaign ledger.
The proof archive and every candidate's original digest precede compression.
"""
from pathlib import Path
import ctypes,hashlib,json,os,psutil,subprocess,time,zipfile

ROOTS=(Path(r'D:\v42_svr11_may_20261011_09'),Path(r'D:\v42_svr11_may_20261011_10'))
OUT=Path(r'D:\v42_svr11_planning_diagnostics_20261011\storage')

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def allocated(p):
    high=ctypes.c_ulong();fn=ctypes.windll.kernel32.GetCompressedFileSizeW
    fn.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)];fn.restype=ctypes.c_ulong
    low=fn(str(p),ctypes.byref(high))
    if low==0xffffffff:raise ctypes.WinError()
    return (high.value<<32)|low

def save(name,value):
    p=OUT/name
    if p.exists():raise RuntimeError('PRESERVED_PROOF_NEVER_OVERWRITE:'+str(p))
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');return p

def run():
    if os.name!='nt':raise RuntimeError('NTFS_REQUIRED')
    OUT.mkdir(parents=True,exist_ok=True)
    active=[]
    for process in psutil.process_iter(['pid','cmdline']):
        try:
            cmd=process.info['cmdline'] or []
            if 'v42_svr11.worker' in cmd:
                request=Path(cmd[-1]).resolve();active.append(request.parents[2])
        except (psutil.Error,OSError):continue
    evidence=[];summaries=[];candidates=[];skipped_shared=0
    for root in ROOTS:
        root=root.resolve()
        for name in ('CAMPAIGN_MANIFEST.json','CAMPAIGN_LEDGER.json','RAW_INPUT_RECEIPTS.json','RAW_INPUT_ORIGINS.json','IMMUTABLE_STORAGE_SHARING.json','DISPATCH_QUIESCENCE_FOR_PLANNING_MODEL_REPAIR.json'):
            p=root/name
            if p.is_file():evidence.append(p)
        evidence+=list((root/'hardware').glob('*.json'))
        ledger=json.loads((root/'CAMPAIGN_LEDGER.json').read_text(encoding='utf8'))
        for key,row in ledger['dates'].items():
            summaries.append(dict(root=str(root),key=key,status=row['status'],result=row.get('result'),result_SHA=row.get('result_SHA'),reason=row.get('reason')))
        for date in (root/'dates').glob('*/*'):
            if date.name=='2025-05-18' or any(date==p for p in active):continue
            results=list(date.glob('attempts/*/RESULT.json'))
            if not results:continue
            # Each admitted date has terminated all own Worker attempts.
            for p in date.rglob('*'):
                if not p.is_file():continue
                if p.name=='NATIVE_RUNTIME_LEDGER.json' or p.name=='RESULT.json':evidence.append(p)
                if p.suffix.lower() not in ('.json','.csv','.log') or p.stat().st_size<1024*1024:continue
                if p.stat().st_nlink>1:skipped_shared+=1;continue
                resolved=p.resolve()
                if not resolved.is_relative_to(root/'dates'):raise RuntimeError('PATH_ESCAPE')
                candidates.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size,
                    inode=p.stat().st_ino,links=p.stat().st_nlink,before_allocated=allocated(p)))
    save('DATE_STATUS_AND_CANDIDATES_BEFORE.json',dict(date_summaries=summaries,candidates=candidates,
        active_dates_excluded=list(map(str,active)),May18_excluded=True,shared_files_skipped=skipped_shared,
        disk_before=psutil.disk_usage('D:/')._asdict(),deleted_files=0))
    archive=OUT/'ESSENTIAL_EVIDENCE_BEFORE.zip'
    if archive.exists():raise RuntimeError('BACKUP_EXISTS')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(set(evidence)):
            z.write(p,p.relative_to(p.anchor).as_posix())
    with zipfile.ZipFile(archive) as z:
        for p in sorted(set(evidence)):
            if hashlib.sha256(z.read(p.relative_to(p.anchor).as_posix())).hexdigest()!=sha(p):raise RuntimeError('BACKUP_SHA_FAILURE')
    archive_sha=sha(archive);rows=[];start=time.perf_counter()
    for i,row in enumerate(candidates):
        p=Path(row['path'])
        if sha(p)!=row['sha256'] or p.stat().st_ino!=row['inode'] or p.stat().st_nlink!=1:raise RuntimeError('CANDIDATE_CHANGED')
        result=subprocess.run(['compact.exe','/C','/A','/Q',str(p)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError('COMPRESSION_FAILED:'+str(p)+':'+result.stdout+result.stderr)
        if sha(p)!=row['sha256'] or p.stat().st_size!=row['bytes']:raise RuntimeError('DECOMPRESSED_BYTES_CHANGED')
        rows.append(dict(row,after_allocated=allocated(p),SHA_reverified=True,path_preserved=True))
        if i%30==0:print(json.dumps(dict(compressed=i+1,total=len(candidates))),flush=True)
    if sha(archive)!=archive_sha:raise RuntimeError('ARCHIVE_CHANGED')
    receipt=dict(method='NTFS_IN_PLACE_COMPRESSION',deleted_files=0,compressed_files=len(rows),
        logical_bytes=sum(r['bytes'] for r in rows),allocated_space_freed=sum(r['before_allocated']-r['after_allocated'] for r in rows),
        essential_archive=dict(path=str(archive),sha256=archive_sha,bytes=archive.stat().st_size,all_entries_SHA_verified=True),
        disk_after=psutil.disk_usage('D:/')._asdict(),rows=rows,wall_seconds=time.perf_counter()-start,
        all_original_paths_and_decompressed_bytes_preserved=True,May18_details_untouched=True,
        Source_raw_models_mutable_ledgers_and_shared_files_untouched=True)
    save('STORAGE_COMPRESSION_RECEIPT.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='rows'}),flush=True)

if __name__=='__main__':run()

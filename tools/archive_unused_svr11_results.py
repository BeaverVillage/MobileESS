"""Archive closed historical arrays and remove byte-reconstructible slot duplicates.

Explicit old-root allowlist; no recursive deletion. Preserve current campaign,
raw/source/ledgers, all failed dates, May16/18 and every shared inode. A removed
array has a verified ZIP copy; a removed slot NPZ has a byte-identical recovery
recipe from its retained merged NPZ. Original historical path receipts stay
unchanged, and the archive map explicitly records that loose files were removed.
"""
from pathlib import Path
import argparse, ctypes, hashlib, io, json, os, psutil, sys, time, zipfile, zlib
import numpy as np

ROOTS=tuple(Path(f'D:/v42_svr11_may_20261011_{e:02}') for e in (6,8,9,10))
CURRENT=Path('D:/v42_svr11_may_20261011_12')
BASE=Path('D:/v42_svr11_planning_diagnostics_20261011/storage')
ARRAYS={'VOLTAGE_CONTROL_PLANNING_SLOTS.json','VOLTAGE_CONTROL_ACTUAL_SLOTS.json'}
PROTECTED_DAYS={'2025-05-16','2025-05-18'}

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def save(p,v):
    p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,p)

def allocated(p):
    high=ctypes.c_ulong();fn=ctypes.windll.kernel32.GetCompressedFileSizeW
    fn.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)];fn.restype=ctypes.c_ulong
    low=fn(str(p),ctypes.byref(high))
    if low==0xffffffff:raise ctypes.WinError()
    return (high.value<<32)|low

def safe(p):
    p=Path(p).resolve(strict=True)
    roots=[r.resolve(strict=True) for r in ROOTS]
    assert any(p.is_relative_to(r/'dates') or p.is_relative_to(r/'models') for r in roots),'PATH_ESCAPE'
    assert not p.is_relative_to(CURRENT.resolve()),'CURRENT_PATH'
    assert not PROTECTED_DAYS.intersection(p.parts),'PROTECTED_DIAGNOSTIC'
    assert p.is_file() and p.stat().st_nlink==1,'SHARED_OR_NONFILE'
    return p

def no_old_workers():
    active=[]
    for proc in psutil.process_iter(['pid','cmdline']):
        try:
            cmd=proc.info['cmdline'] or []
            if 'v42_svr11.worker' in cmd:
                if any(str(r).lower() in ' '.join(cmd).lower() for r in ROOTS):
                    raise RuntimeError('OLD_WORKER_ACTIVE:'+str(proc.pid))
                active.append(dict(PID=proc.pid,command=cmd))
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return active

def reconstruct(merged,t,recipe):
    fields={}
    for k,fortran in recipe:
        a=merged[k][t]
        fields[k]=np.asfortranarray(a) if fortran else np.ascontiguousarray(a)
    b=io.BytesIO();np.savez_compressed(b,**fields);return b.getvalue()

def slot_proof(p,merged):
    recipe=[];t=int(p.stem.split('_')[1])
    with np.load(p,allow_pickle=False) as original,zipfile.ZipFile(p) as z:
        for k in original.files:
            with z.open(k+'.npy') as f:
                version=np.lib.format.read_magic(f)
                shape,fortran,dtype=np.lib.format._read_array_header(f,version)
            assert np.array_equal(original[k],merged[k][t]),'MERGED_ARRAY_DIFFERENT'
            recipe.append((k,bool(fortran)))
    original_sha=sha(p)
    assert digest(reconstruct(merged,t,recipe))==original_sha,'RECONSTRUCTION_NOT_BYTE_IDENTICAL'
    return dict(slot=t,recipe=recipe,sha256=original_sha,byte_identical_recovery_verified=True)

def run(execute=False):
    if execute:raise RuntimeError('ARCHIVE_CREATION_SUPERSEDED_BY_USER_NO_BACKUP_INSTRUCTION')
    assert os.name=='nt'
    active=no_old_workers();before=psutil.disk_usage('D:/')._asdict()
    folder=BASE/('UNUSED_RESULTS_'+time.strftime('%Y%m%d_%H%M%S'))
    folder.mkdir(parents=True,exist_ok=False)
    candidates=[];essential=[];summaries=[];skips=[];merges={}
    for root in ROOTS:
        root=root.resolve(strict=True)
        for p in root.glob('*.json'):
            if p.stat().st_size<3*1024*1024:essential.append(p)
        essential.extend((root/'hardware').glob('*.json'))
        ledger=read(root/'CAMPAIGN_LEDGER.json')
        summaries.extend(dict(root=str(root),key=k,**v) for k,v in ledger['dates'].items())
        failed=set()
        for date in (root/'dates').glob('*/*'):
            results=list(date.glob('attempts/*/RESULT.json'))
            own=[p for p in results if p.is_file()]
            if not own or any(not read(p).get('PASS',False) for p in own):failed.add(date.name)
            essential.extend(own)
            essential.extend(date.rglob('NATIVE_RUNTIME_LEDGER.json'))
            essential.extend(p for p in date.rglob('*.csv') if p.stat().st_size<3*1024*1024)
            if date.name in PROTECTED_DAYS or date.name in failed:continue
            for p in date.rglob('*.json'):
                if p.name not in ARRAYS or p.stat().st_size<1024*1024:continue
                if p.stat().st_nlink!=1:skips.append(dict(path=str(p),reason='SHARED_INODE'));continue
                p=safe(p);s=p.stat()
                candidates.append(dict(kind='ARCHIVED_ARRAY',path=str(p),sha256=sha(p),
                    bytes=s.st_size,allocated=allocated(p),inode=s.st_ino))
        for day in (root/'models').glob('*'):
            if not day.is_dir() or day.name in PROTECTED_DAYS or day.name in failed:continue
            merged_path=day/'COEFFICIENTS.npz'
            slots=sorted(day.glob('SLOT_*.npz'))
            if not merged_path.is_file() or len(slots)!=96:continue
            merge_sha=sha(merged_path);merges[str(merged_path)]=merge_sha
            with np.load(merged_path,allow_pickle=False) as merged:
                # Load each large compressed merged field once per day.
                data={k:merged[k] for k in merged.files}
                for p in slots:
                    if p.stat().st_nlink!=1:skips.append(dict(path=str(p),reason='SHARED_INODE'));continue
                    p=safe(p);s=p.stat()
                    try:proof=slot_proof(p,data)
                    except (AssertionError,KeyError,ValueError) as exc:
                        skips.append(dict(path=str(p),reason=str(exc)));continue
                    candidates.append(dict(kind='MERGED_SLOT_DUPLICATE',path=str(p),**proof,
                        bytes=s.st_size,allocated=allocated(p),inode=s.st_ino,
                        retained_merged=str(merged_path),retained_merged_sha256=merge_sha))
            print(json.dumps(dict(proved_model_day=str(day),candidates=len(candidates))),flush=True)
    essential.append(Path('D:/v42_svr11_planning_diagnostics_20261011/EPOCH10_DRAIN_PRESERVATION.json'))
    essential=sorted(set(p.resolve(strict=True) for p in essential))
    plan=dict(method='VERIFIED_ARCHIVE_AND_BYTE_IDENTICAL_DUPLICATE_REMOVAL',
        numpy_version=np.__version__,python_version=sys.version,zlib_runtime=zlib.ZLIB_RUNTIME_VERSION,
        disk_before=before,active_workers=active,
        old_date_summaries=summaries,candidates=candidates,skipped=skips,
        retained_merged=merges,protected_days=sorted(PROTECTED_DAYS),
        current_raw_source_shared_failures_ledgers_native_and_performance_untouched=True,
        original_loose_path_receipts_not_rewritten=True,execute=execute)
    save(folder/'PLAN.json',plan)
    if not execute:
        print(json.dumps(dict(plan=str(folder/'PLAN.json'),candidates=len(candidates),
            eligible_allocated=sum(r['allocated'] for r in candidates))));return
    # Essential metadata and all array bytes are backed up and verified first.
    archive=folder/'PRESERVED_EVIDENCE_AND_ARRAYS.zip';records=[]
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in essential:
            name='essential/'+p.relative_to(p.anchor).as_posix()
            h=sha(p);z.write(p,name);records.append(dict(path=str(p),entry=name,sha256=h))
        z.write(folder/'PLAN.json','cleanup/PLAN.json')
        for i,row in enumerate(r for r in candidates if r['kind']=='ARCHIVED_ARRAY'):
            p=safe(row['path']);assert sha(p)==row['sha256']
            entry='arrays/'+p.relative_to(p.anchor).as_posix();z.write(p,entry)
            row['archive_entry']=entry;records.append(dict(path=str(p),entry=entry,sha256=row['sha256']))
            if i%20==0:print(json.dumps(dict(archived_arrays=i+1)),flush=True)
    with zipfile.ZipFile(archive) as z:
        for row in records:
            h=hashlib.sha256()
            with z.open(row['entry']) as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            assert h.hexdigest()==row['sha256'],'ARCHIVE_SHA_MISMATCH'
    archive_sha=sha(archive)
    for p,h in merges.items():assert sha(p)==h,'MERGED_BACKUP_CHANGED'
    no_old_workers()
    recovery=dict(archive=dict(path=str(archive),sha256=archive_sha,bytes=archive.stat().st_size,
        allocated=allocated(archive),all_entries_SHA_verified=True),entries=records,
        removed_path_recovery_map=candidates,numpy_version=np.__version__)
    save(folder/'RECOVERY_MAP.json',recovery)
    deleted=[]
    for i,row in enumerate(candidates):
        p=safe(row['path']);assert p.stat().st_ino==row['inode'] and sha(p)==row['sha256'],'CANDIDATE_CHANGED'
        p.unlink()  # exact checked single file; never a recursive deletion
        deleted.append(row)
        if i%100==0:save(folder/'DELETION_PROGRESS.json',dict(deleted=deleted,archive_sha256=archive_sha))
    assert sha(archive)==archive_sha
    for p,h in merges.items():assert sha(p)==h
    receipt=dict(deleted_files=len(deleted),archived_loose_arrays=sum(r['kind']=='ARCHIVED_ARRAY' for r in deleted),
        byte_reconstructible_slot_duplicates=sum(r['kind']=='MERGED_SLOT_DUPLICATE' for r in deleted),
        deleted_logical_bytes=sum(r['bytes'] for r in deleted),deleted_allocated_bytes=sum(r['allocated'] for r in deleted),
        archive=recovery['archive'],net_allocated_recovered=sum(r['allocated'] for r in deleted)-allocated(archive),
        disk_before=before,disk_after=psutil.disk_usage('D:/')._asdict(),
        recovery_map=dict(path=str(folder/'RECOVERY_MAP.json'),sha256=sha(folder/'RECOVERY_MAP.json')),
        essential_entries=len(essential),original_sha_bytes_verified_before_deletion=True,
        May16_May18_current_raw_source_shared_all_failed_dates_untouched=True,
        loose_array_paths_removed_not_claimed_preserved=True,old_campaigns_must_not_restart=True,
        current_workers_after=no_old_workers())
    save(folder/'CLEANUP_RECEIPT.json',receipt)
    save(BASE/'LATEST_UNUSED_RESULTS_CLEANUP.json',dict(path=str(folder/'CLEANUP_RECEIPT.json'),sha256=sha(folder/'CLEANUP_RECEIPT.json')))
    print(json.dumps(receipt,ensure_ascii=False),flush=True)

def restore(map_path,original):
    no_old_workers()
    receipt=read(Path(map_path).parent/'CLEANUP_RECEIPT.json')
    assert sha(map_path)==receipt['recovery_map']['sha256'],'RECOVERY_MAP_CHANGED'
    recovery=read(map_path)
    row=next(r for r in recovery['removed_path_recovery_map'] if r['path']==str(Path(original)))
    p=Path(row['path']).resolve()
    assert any(p.is_relative_to(r.resolve()/'dates') or p.is_relative_to(r.resolve()/'models') for r in ROOTS)
    assert not p.exists(),'NEVER_OVERWRITE'
    if row['kind']=='ARCHIVED_ARRAY':
        assert Path(recovery['archive']['path']).exists(),'OLD_DETAIL_INTENTIONALLY_DELETED_WITHOUT_BACKUP_BY_USER'
        assert sha(recovery['archive']['path'])==recovery['archive']['sha256']
        with zipfile.ZipFile(recovery['archive']['path']) as z:b=z.read(row['archive_entry'])
    else:
        assert sha(row['retained_merged'])==row['retained_merged_sha256']
        with np.load(row['retained_merged'],allow_pickle=False) as z:b=reconstruct(z,row['slot'],row['recipe'])
    assert digest(b)==row['sha256'],'RECOVERY_NOT_BYTE_IDENTICAL'
    with p.open('xb') as f:f.write(b)
    assert sha(p)==row['sha256'];print(json.dumps(dict(restored=str(p),sha256=sha(p))))

def purge_backups():
    """Latest explicit user authorization discards unneeded historical arrays.

    Essential metadata remain as SHA-verified loose originals. Do not interpret
    this as permission to remove raw data, source, failures or May18 evidence.
    """
    no_old_workers();index=read(BASE/'LATEST_UNUSED_RESULTS_CLEANUP.json')
    receipt=read(index['path']);folder=Path(index['path']).parent
    assert not (folder/'BACKUP_REMOVAL_RECEIPT.json').exists(),'NEVER_REPEAT_OR_OVERWRITE'
    recovery=read(receipt['recovery_map']['path'])
    assert sha(receipt['recovery_map']['path'])==receipt['recovery_map']['sha256']
    essential=[r for r in recovery['entries'] if r['entry'].startswith('essential/')]
    assert all(Path(r['path']).is_file() and sha(r['path'])==r['sha256'] for r in essential)
    previous=read(BASE/'STORAGE_COMPRESSION_RECEIPT.json')['essential_archive']
    archives=[receipt['archive'],previous]
    # Earlier essential ZIP is also wholly duplicated in retained loose files.
    with zipfile.ZipFile(previous['path']) as z:
        for name in z.namelist():
            original=Path('D:/')/name
            assert original.is_file() and sha(original)==digest(z.read(name)),'UNIQUE_ESSENTIAL_BACKUP'
    rows=[]
    for row in archives:
        p=Path(row['path']).resolve(strict=True)
        assert p.is_relative_to(BASE.resolve()) and p.suffix=='.zip' and p.stat().st_nlink==1
        assert sha(p)==row['sha256'],'BACKUP_CHANGED'
        rows.append(dict(path=str(p),sha256=row['sha256'],bytes=p.stat().st_size,allocated=allocated(p)))
    plan=dict(reason='EXPLICIT_USER_DELETE_UNNEEDED_OLD_VERSION_BACKUPS',archives=rows,
        essential_loose_records_SHA_verified=len(essential),old_essential_ZIP_all_loose_entries_identical=True,
        historical_PASS_detailed_arrays_intentionally_discarded_without_backup=True,
        May16_May18_current_raw_source_shared_failed_dates_and_ledgers_untouched=True,
        disk_before=psutil.disk_usage('D:/')._asdict())
    save(folder/'BACKUP_REMOVAL_PLAN.json',plan)
    for row in rows:
        p=Path(row['path']).resolve(strict=True)
        assert p.is_relative_to(BASE.resolve()) and sha(p)==row['sha256']
        p.unlink()
    result=dict(plan,deleted_archives=len(rows),additional_allocated_recovered=sum(r['allocated'] for r in rows),
        total_cleanup_allocated_recovered=receipt['net_allocated_recovered']+sum(r['allocated'] for r in rows),
        archived_array_restore_available=False,retained_merged_slot_reconstruction_still_available=True,
        disk_after=psutil.disk_usage('D:/')._asdict(),current_workers_after=no_old_workers())
    save(folder/'BACKUP_REMOVAL_RECEIPT.json',result)
    save(BASE/'LATEST_BACKUP_REMOVAL.json',dict(path=str(folder/'BACKUP_REMOVAL_RECEIPT.json'),
        sha256=sha(folder/'BACKUP_REMOVAL_RECEIPT.json')))
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    parser.add_argument('--purge-backups',action='store_true')
    parser.add_argument('--restore-map');parser.add_argument('--restore-path');args=parser.parse_args()
    if args.purge_backups:purge_backups()
    elif args.restore_map:restore(args.restore_map,args.restore_path)
    else:run(args.execute)

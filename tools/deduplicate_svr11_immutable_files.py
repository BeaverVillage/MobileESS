"""Share byte-identical frozen files without changing any path or SHA.

Only raw input receipts and admitted completed Forecast checkpoint archives
are eligible. Never touch a mutable progress, ledger, log, certificate, input
bundle or policy result. Existing evidence paths remain independently valid.
"""
from pathlib import Path
import sys,os,time,ctypes,json,uuid
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_common_campaign.authority import singleton

ROOT=Path(r'D:\v42_svr11_may_20261011_10')
OLD=Path(r'D:\v42_svr11_may_20261011_09')

def allocated_bytes(path):
    high=ctypes.c_ulong()
    call=ctypes.windll.kernel32.GetCompressedFileSizeW
    call.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)]
    call.restype=ctypes.c_ulong
    low=call(str(path),ctypes.byref(high))
    if low==0xffffffff and ctypes.get_last_error():raise ctypes.WinError()
    return (high.value<<32)|low

def same_identity(a,b):
    aa=a.stat();bb=b.stat()
    return aa.st_dev==bb.st_dev and aa.st_ino==bb.st_ino

def candidates():
    # Receipts are already frozen and verified during request admission.
    origin={Path(r['path']).relative_to(OLD/'raw'):r
        for refs in read(OLD/'RAW_INPUT_RECEIPTS.json').values() for r in refs}
    for refs in read(ROOT/'RAW_INPUT_RECEIPTS.json').values():
        for target in refs:
            rel=Path(target['path']).relative_to(ROOT/'raw')
            old=origin.get(rel)
            if old and (old['sha256'],old['bytes'])==(target['sha256'],target['bytes']):
                yield 'frozen_raw',old,target
    cp=ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json'
    if not cp.exists():return
    for day,value in read(cp)['days'].items():
        for slot,owned in value['slots'].items():
            p=ROOT/'models'/day/f'SLOT_{int(slot):02d}.json'
            if not p.exists():continue
            v=read(p);old=owned['original_data'];target=v['data']
            assert v['reused'] and v['generation_source_SHA']==owned['generation_source_SHA']
            assert (old['sha256'],old['bytes'])==(target['sha256'],target['bytes'])
            yield 'admitted_forecast_slot',old,target
        for name,old in value['forecast_anchor'].items():
            if not name.endswith('.npz'):continue
            p=ROOT/'models'/day/'FORECAST_ANCHOR'/name
            if p.exists():yield 'frozen_forecast_anchor',old,record(p)

def run():
    if os.name!='nt':raise RuntimeError('NTFS_HARDLINK_REQUIRED')
    assert ROOT.resolve()==ROOT and OLD.resolve()==OLD and ROOT.drive==OLD.drive
    with singleton(ROOT/'IMMUTABLE_STORAGE_SHARING.lock'):
        rows=[];freed=logical=0
        for kind,old,target in candidates():
            a=Path(old['path']);b=Path(target['path'])
            assert a.resolve().is_relative_to(OLD) and b.resolve().is_relative_to(ROOT)
            assert record(a)==old and record(b)==target
            if same_identity(a,b):state='ALREADY_SHARED';allocated=0
            else:
                allocated=allocated_bytes(b);temp=b.with_name(b.name+'.share-'+uuid.uuid4().hex)
                os.link(a,temp)
                try:
                    # Handle a concurrent reader's finite Windows file lock.
                    for attempt in range(6):
                        try:os.replace(temp,b);break
                        except PermissionError:
                            if attempt==5:raise
                            time.sleep(.1)
                finally:
                    if temp.exists():temp.unlink()
                assert same_identity(a,b)
                freed+=allocated;logical+=target['bytes'];state='SHARED'
            assert record(a)==old and record(b)==target
            rows.append(dict(kind=kind,original=old,current=target,status=state,
                same_file_identity=True,NTFS_link_count=b.stat().st_nlink,allocated_bytes_removed=allocated))
        prior=ROOT/'IMMUTABLE_STORAGE_SHARING.json'
        history=read(prior).get('runs',[]) if prior.exists() else []
        history.append(dict(UTC=now(),newly_shared=sum(r['status']=='SHARED' for r in rows),
            avoided_allocated_bytes=freed,avoided_logical_duplicate_bytes=logical))
        out=dict(PASS=True,root=str(ROOT),original_root=str(OLD),rows=rows,runs=history,
            files_verified=len(rows),all_original_and_current_paths_and_SHA_preserved=True,
            mutable_files_shared=0,original_results_or_ledgers_deleted=0,
            common_model_by_day_used_by=['B1','B2','B3'],
            policy_specific_optimization_models_and_results_reused=False,
            scope='SHA-identical frozen raw inputs and explicitly admitted completed Forecast archives only',UTC=now())
        atomic(prior,out)
        print(json.dumps({k:out[k] for k in ('PASS','files_verified','runs','mutable_files_shared')},ensure_ascii=False))

if __name__=='__main__':run()

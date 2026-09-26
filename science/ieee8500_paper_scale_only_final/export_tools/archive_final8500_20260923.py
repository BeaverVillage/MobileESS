"""Archive final IEEE8500 raw campaign without modifying scientific sources."""
import os, io, json, time, gzip, tarfile, hashlib, shutil
from pathlib import Path
from datetime import datetime

ROOT=Path(r'D:\ChatGPT\Mobile ESS 2')
H=ROOT/'IEEE8500_PAPER_SCALE_ONLY_20260920/full_production_paper_BG055200_AIDC240_MESS200'
DEST=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/결과 데이터')
STAMP=datetime.now().strftime('%Y%m%d_%H%M%S')
BASE='IEEE8500_FINAL_MAY01_BG0552_AIDC240_MESS200_RAW_'+STAMP
FINAL=DEST/(BASE+'.tar.gz')
PARTIAL=DEST/(BASE+'.tar.gz.partial')
INDEX=DEST/(BASE+'_INDEX.json')
VERIFY=DEST/(BASE+'_VERIFICATION.json')
STATE=ROOT/'IEEE8500_ARCHIVE_PROGRESS_20260923.json'
start=time.time();last=0

def progress(stage,**kwargs):
    d=dict(stage=stage,archive=str(FINAL),elapsed_seconds=time.time()-start,updated_unix=time.time())
    d.update(kwargs)
    STATE.write_text(json.dumps(d,indent=2),encoding='utf-8')
    print(json.dumps(d),flush=True)

class Reader:
    def __init__(self,f):self.f=f;self.digest=hashlib.sha256()
    def read(self,n=-1):
        b=self.f.read(n);self.digest.update(b);return b

def main():
    assert json.loads((H/'CAMPAIGN_STATUS.json').read_text())['status']=='COMPLETE'
    assert json.loads((H/'FINAL_CAMPAIGN_RESULT.json').read_text())['status']=='PASS'
    entries=[]
    for folder,prefix in [(H,'campaign'),(ROOT/'IEEE8500_scalability_20260910/source','native_feeder_source')]:
        for base,ds,fs in os.walk(folder):
            ds.sort()
            for name in sorted(fs):
                p=Path(base)/name
                if p.is_file():entries.append((p,BASE+'/'+prefix+'/'+p.relative_to(folder).as_posix()))
    # Include existing top-level paper restoration/regression evidence without diagnostics from other campaigns.
    for p in sorted(H.parent.iterdir()):
        if p.is_file():entries.append((p,BASE+'/paper_campaign_authority/'+p.name))
    total=sum(p.stat().st_size for p,_ in entries)
    assert shutil.disk_usage(DEST).free>total+2_000_000_000
    progress('COMPRESSING',total_files=len(entries),total_bytes=total,completed_files=0)
    records=[];done=0;last=time.time()
    with PARTIAL.open('xb') as raw:
        with gzip.GzipFile(filename='',mode='wb',compresslevel=1,fileobj=raw,mtime=0) as gz:
            with tarfile.open(mode='w|',fileobj=gz,format=tarfile.PAX_FORMAT,bufsize=4*1024*1024) as tf:
                for i,(p,name) in enumerate(entries,1):
                    before=p.stat();info=tf.gettarinfo(str(p),arcname=name)
                    assert info.isfile(),str(p)
                    with p.open('rb') as f:
                        reader=Reader(f);tf.addfile(info,reader)
                    after=p.stat();assert before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns,('Source changed',str(p))
                    records.append(dict(member=name,source_path=str(p),bytes=info.size,sha256=reader.digest.hexdigest()))
                    done+=info.size
                    if time.time()-last>20:
                        progress('COMPRESSING',completed_files=i,total_files=len(entries),completed_bytes=done,total_bytes=total,archive_bytes=raw.tell());last=time.time()
                manifest=dict(format='IEEE8500_FINAL_RAW_ARCHIVE_V1',campaign_status='COMPLETE_PASS',date='2025-05-01',BG_scale=.552,AIDC_absolute_scale=2.4,MESS_scale=2.0,source_campaign=str(H),created_local=datetime.now().isoformat(),files=records,total_source_bytes=total,source_file_count=len(records),includes_diagnostic_attempts=True,includes_native_feeder=True,notes='Completed production and original diagnostic files preserved. External repository references in source files retain original paths; this is a raw-results archive, not a promise of a self-contained installed execution environment.')
                payload=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
                ti=tarfile.TarInfo(BASE+'/ARCHIVE_MANIFEST.json');ti.size=len(payload);ti.mtime=int(time.time());tf.addfile(ti,io.BytesIO(payload))
    with INDEX.open('x',encoding='utf-8') as f:f.write(payload.decode('utf-8'))
    progress('VERIFYING_CONTENTS',total_files=len(records),archive_bytes=PARTIAL.stat().st_size)
    expected={r['member']:r for r in records};seen=set();verified_bytes=0;last=time.time()
    with tarfile.open(PARTIAL,'r|gz',bufsize=4*1024*1024) as tf:
        for member in tf:
            assert member.isfile() and member.name not in seen;seen.add(member.name)
            f=tf.extractfile(member)
            if member.name==BASE+'/ARCHIVE_MANIFEST.json':
                assert f.read()==payload;continue
            rec=expected[member.name];sha=hashlib.sha256();n=0
            while True:
                b=f.read(4*1024*1024)
                if not b:break
                sha.update(b);n+=len(b)
            assert n==rec['bytes'] and sha.hexdigest()==rec['sha256'],member.name
            verified_bytes+=n
            if time.time()-last>20:
                progress('VERIFYING_CONTENTS',verified_files=len(seen),total_files=len(records),verified_bytes=verified_bytes,total_bytes=total);last=time.time()
    assert len(seen)==len(records)+1 and verified_bytes==total
    progress('HASHING_ARCHIVE',archive_bytes=PARTIAL.stat().st_size)
    sha=hashlib.sha256()
    with PARTIAL.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):sha.update(b)
    digest=sha.hexdigest();assert not FINAL.exists();PARTIAL.rename(FINAL)
    with (DEST/(BASE+'.tar.gz.sha256')).open('x',encoding='utf-8') as f:f.write(digest+'  '+FINAL.name+'\n')
    verification=dict(status='PASS',archive=str(FINAL),archive_sha256=digest,archive_bytes=FINAL.stat().st_size,source_file_count=len(records),archive_member_count=len(seen),verified_source_bytes=total,all_member_sha256_match=True,embedded_manifest_matches_external_index=True,source_files_unchanged_during_read=True,elapsed_seconds=time.time()-start)
    with VERIFY.open('x',encoding='utf-8') as f:json.dump(verification,f,indent=2)
    progress('COMPLETE',**verification)

if __name__=='__main__':
    try:main()
    except Exception as e:
        progress('FAILED',error=repr(e));raise

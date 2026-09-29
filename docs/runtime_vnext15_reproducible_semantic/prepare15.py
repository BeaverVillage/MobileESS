from common15 import *
import csv
assert git('rev-parse','HEAD')==BASE
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
prior=read(R2/'V14R1_BASE_VERIFICATION.json')['files']
for r in git('ls-files',str(R2.relative_to(REPO))).splitlines():
    p=REPO/r
    assert sha(p)==hashlib.sha256(subprocess.check_output(['git','show',BASE+':'+r],cwd=REPO)).hexdigest()
    prior.append(dict(relative=r,bytes=p.stat().st_size,sha256=sha(p)))
for r in prior:assert sha(REPO/r['relative'])==r['sha256'],r['relative']
manifests=[]
for r in prior:
    if r['relative'].endswith('/DELIVERY_MANIFEST.json'):
        p=REPO/r['relative']
        for row in read(p)['files']:assert sha(p.parent/row['relative'])==row['sha256'],row['relative']
        manifests.append(rec(p))
local_inputs=read(R2/'V14R1_BASE_VERIFICATION.json')['local_inputs']+read(R2/'LOCAL_EVIDENCE_MANIFEST.json')['files']
for r in local_inputs:assert sha(r['path'])==r['sha256'],r['path']
raw_count=0
with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        p=Path(r['directory'])/r['filename'];st=Path('\\\\?\\'+str(p)).lstat()
        assert (st.st_size,st.st_mtime_ns)==(int(r['size_bytes']),int(r['mtime_ns'])),str(p)
        raw_count+=1
LOCAL.mkdir(exist_ok=True)
request=Path(r'C:\Users\kjw39\.codex\attachments\a567e472-8ec3-4215-96c3-0b29115afa9b\붙여넣은 텍스트.txt')
(ROOT/'USER_REQUEST.txt').write_bytes(request.read_bytes())
write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,branch=git('branch','--show-current'),
    tracked_files=prior,delivery_manifests=manifests,local_inputs=local_inputs,
    raw_size_mtime_verified=raw_count,private_RADDiT_search_reopened=False))
print('BASE VERIFIED',len(prior),len(manifests),len(local_inputs),raw_count,flush=True)

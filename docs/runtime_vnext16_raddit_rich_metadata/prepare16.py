from common16 import *
import csv
assert git('rev-parse','HEAD')==BASE and not git('diff','--name-only') and not git('diff','--cached','--name-only')
LOCAL.mkdir(exist_ok=True)
old=read(V15/'BASE_PRESERVATION_RECEIPT.json')
rows=list(old['tracked_files'])
for p in git('ls-files','docs/runtime_vnext15_reproducible_semantic','v42').splitlines():
    f=REPO/p;assert sha(f)==hashlib.sha256(subprocess.check_output(['git','show',BASE+':'+p],cwd=REPO)).hexdigest()
    rows.append(dict(relative=p,bytes=f.stat().st_size,sha256=sha(f)))
for r in rows:assert sha(REPO/r['relative'])==r['sha256'],r['relative']
local=old['local_inputs']+read(V15/'LOCAL_EVIDENCE_MANIFEST.json')['files']
for r in local:assert sha(r['path'])==r['sha256'],r['path']
manifest=read(V15/'DELIVERY_MANIFEST.json')
for r in manifest['files']:assert sha(V15/r['relative'])==r['sha256']
for r in manifest['repository_files']:assert sha(REPO/r['relative'])==r['sha256']
n=0
with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        p=Path(r['directory'])/r['filename'];st=Path('\\\\?\\'+str(p)).lstat()
        assert (st.st_size,st.st_mtime_ns)==(int(r['size_bytes']),int(r['mtime_ns'])),str(p);n+=1
write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,tracked_files=rows,local_inputs=local,raw_size_mtime_verified=n,V15_delivery_manifest=rec(V15/'DELIVERY_MANIFEST.json')))
request=Path(r'C:\Users\kjw39\.codex\attachments\15694889-06df-4ba8-95d5-2eddb362ebc1\붙여넣은 텍스트.txt')
(ROOT/'USER_REQUEST.txt').write_bytes(request.read_bytes())
write('AUDIT_PROTOCOL.json',dict(time=now(),before_new_model_metrics=True,preApril_cutoff='2025-04-01T00:00:00Z',
    native_folds=[dict(fold=i+1,valid_from=a,valid_to=b) for i,(a,b) in enumerate([('2024-09-01','2024-11-01'),('2024-11-01','2025-01-01'),('2025-01-01','2025-03-11')])],
    native_fit='All strictly earlier submissions whose end precedes VALID start; no CAL search; nonnegative finite wallclock_used_sec and end>=start>=submit',
    crosswalk='Reuse and independently check exact T0 EKEY2 unique ledger; extend historic to Kestrel with exact displayed submit/start/end, wallclock used/requested, nodes, processors; never fuzzy. Quarantine all duplicate keys and holdout conflicts.',
    diagnostic_only=True,May_decoding=False,source_authority_not_reopened=True))
print('BASE_PRESERVED',len(rows),len(local),n,flush=True)

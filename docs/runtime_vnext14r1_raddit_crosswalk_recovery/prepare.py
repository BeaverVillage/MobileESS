from common import *
import csv
assert git('rev-parse','HEAD')==BASE
files=[p for p in git('ls-files').splitlines() if re.match(r'docs/runtime_vnext(?:[6-9]|1[0-4])_',p)]
receipt=[]
for rel in files:
    p=REPO/rel
    blob=subprocess.check_output(['git','show',BASE+':'+rel],cwd=REPO)
    assert sha(p)==hashlib.sha256(blob).hexdigest(),rel
    receipt.append(dict(relative=rel,bytes=p.stat().st_size,sha256=sha(p)))
manifests=[]
for rel in files:
    if not rel.endswith('/DELIVERY_MANIFEST.json'):continue
    p=REPO/rel;m=read(p);checked=0
    for r in m['files']:
        q=p.parent/r['relative'];assert sha(q)==r['sha256'],str(q);checked+=1
    manifests.append(dict(relative=rel,verified_files=checked))
rawchecked=0
with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        p=Path(row['directory'])/row['filename'];st=Path('\\\\?\\'+str(p)).lstat()
        assert st.st_size==int(row['size_bytes']) and st.st_mtime_ns==int(row['mtime_ns']),str(p)
        rawchecked+=1
projection=V14/'.local/ORIGINAL_KESTREL_IDENTITY_PREAPRIL.parquet'
assert sha(projection)=='dbd8bb56f33c3e5657386a3b40fa8b83b1de0ecf9521487fdd3d4aec1489a241'
write('V14_BASE_VERIFICATION.json',dict(base=BASE,verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),V14_BASE_VERIFIED=True,tracked_files=len(files),manifests=manifests,raw_size_mtime_verified=rawchecked,files=receipt,reused_projection=dict(path=str(projection),sha256=sha(projection))))
write('PREREGISTRATION.json',dict(registered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),before_match_rates=True,NEW_ML_FITS=0,EKEY0=['submit_time','end_time'],EKEY1=['submit_time','end_time','wallclock_used_sec'],EKEY2=['submit_time','end_time','wallclock_used_sec','avg_power_per_node'],embedding_holdout=['start_time'],selection='Smallest unique contradiction-free source-authorized key; never maximize coverage',timestamp='Preserve microseconds and recorded offsets. UTC conversion only for aware timestamps. Naive embedding timezone UNRESOLVED until source authority. RAW_REPRESENTATION comparison retains wall-clock numbers, is diagnostic only. No inferred offset, no truncation.',float='Exact float64 numeric equality and binary equality audit; null keys never match; no tolerance',F0=['submit_time','start_time','end_time'],F1=['submit_time','start_time','end_time','wallclock_used_sec'],F2=['submit_time','start_time','end_time','wallclock_used_sec','wallclock_req_sec','nodes_req','processors_req'],F3='F2 plus memory only if source unit authority proven',F4='F3 plus QoS/partition only if token authority proven',excluded_identity=['raddit positional job_id','semantic search positional row_id'],negative_controls=dict(NC1='submit +1 second',NC2='permute requested walltime within UTC submit date',NC3='permute runtime within UTC submit date',seed=1401,fingerprint='F2'),stop='Stop Level2 if Level1 cannot be proven after exact shared-field and lineage audit; no fuzzy fallback',level1_proof='Unique exact linkage, zero shared-field conflicts, source-backed timestamps, fresh-process deterministic replay. A valid partial subset is allowed.',scope='Pre-April only; vectors never read; no training/inference/provider/queue/V42/April/May'))
print('BASE VERIFIED',len(files),len(manifests),rawchecked)

from common import *
import csv
assert git('rev-parse','HEAD')==BASE
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
prior=read(R1/'V14_BASE_VERIFICATION.json')['files']
files=git('ls-files','docs/runtime_vnext14r1_raddit_crosswalk_recovery').splitlines()
for r in files:
    p=REPO/r;blob=subprocess.check_output(['git','show',BASE+':'+r],cwd=REPO)
    assert sha(p)==hashlib.sha256(blob).hexdigest(),r
    prior.append(dict(relative=r,bytes=p.stat().st_size,sha256=sha(p)))
for r in prior:assert sha(REPO/r['relative'])==r['sha256'],r['relative']
manifests=[]
for r in prior:
    if not r['relative'].endswith('/DELIVERY_MANIFEST.json'):continue
    p=REPO/r['relative'];m=read(p)
    for row in m['files']:assert sha(p.parent/row['relative'])==row['sha256']
    manifests.append(dict(path=str(p),verified_files=len(m['files']),sha256=sha(p)))
local=[]
for parent in [V14,R1]:
    for r in read(parent/'LOCAL_EVIDENCE_MANIFEST.json')['files']:
        p=Path(r['path']) if 'path' in r else parent/r['relative'];assert sha(p)==r['sha256'],str(p);local.append(rec(p))
raw_count=0
with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        p=Path(r['directory'])/r['filename'];st=Path('\\\\?\\'+str(p)).lstat()
        assert (st.st_size,st.st_mtime_ns)==(int(r['size_bytes']),int(r['mtime_ns'])),str(p);raw_count+=1
write('V14R1_BASE_VERIFICATION.json',dict(base=BASE,verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),V14R1_BASE_VERIFIED=True,prior_tracked_files=len(prior),files=prior,delivery_manifests=manifests,local_inputs=local,raw_size_mtime_verified=raw_count))
write('PREREGISTRATION.json',dict(registered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),NEW_ML_FITS=0,base=BASE,T0='historic displayed local wallclock: tz_localize(None), reuse R1 exact ledgers',T1='historic tz_convert(UTC).tz_localize(None), numeric UTC projection already frozen in R1',EKEYS=read(R1/'PREREGISTRATION.json')|{'source':'V14R1 frozen registration'},approval='Match rate is not authority; timestamp transform must be source-backed and export/subset sufficient per USER_REQUEST section20. Approve no transform merely on counts.',DST_dates=['2023-11-05','2024-03-10','2024-11-03','2025-03-09'],DST_window_days_each_side=2,DST_sampling='First and last unique raw candidate per displayed date; UTC is diagnostic; missing dates explicit; no row pairing by nearest time',subset='Descriptive individual missingness/invalid order/resource categories and observed date envelope; no combinatorial filter fitting. Exact membership and independent source authority separate.',ambiguity='Only unused exact shared metadata; no row-order assignment, no vector read',replay='Fixed seed1402 chunk inventory shuffle then canonical filename sorting; fresh process and continuous T0/T1 hash replay from cached metadata',conditional_level2='Only if all seven Level1 criteria pass; then R1 F0-F2 and controls seed1401 permitted. No ML in any outcome.',stop='If timestamp/export authority remains unresolved after bounded local and official public search, finalize immediately after required diagnostics',scope='Only R2 output namespace; no model download, no runtime inference, no April/May payload, no V42 execution/change'))
print('BASE VERIFIED',len(prior),len(manifests),len(local),raw_count)

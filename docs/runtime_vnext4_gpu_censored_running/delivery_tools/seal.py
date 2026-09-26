"""Seal and verify scoped delivery; no scientific artifact changes."""
from pathlib import Path
import argparse,hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,x):
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def included(p):
    rel=p.relative_to(ROOT)
    return not ('cache' in rel.parts or '__pycache__' in rel.parts or p.suffix=='.pyc' or p.name in ['DELIVERY_MANIFEST.json','MEMBERSHIP.parquet','AFT.ubj'] or (rel.parts[0]=='fits' and p.name.endswith('.txt.gz')))
def verify():
    manifest=read(ROOT/'DELIVERY_MANIFEST.json')
    for r in manifest['files']:assert (ROOT/r['path']).stat().st_size==r['bytes'] and sha(ROOT/r['path'])==r['sha256'],r['path']
    assert {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and included(p)}=={r['path'] for r in manifest['files']}
    registration=read(ROOT/'REGISTRATION.json')
    for n,h in registration['code'].items():assert sha(ROOT/n)==h,n
    freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json');assert sha(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv')==freeze['selection_metrics_sha256']
    for n,h in read(ROOT/'FREEZE_BUNDLE.json')['frozen_files'].items():assert sha(ROOT/n)==h,n
    for parent in read(ROOT/'PARENT_PRESERVATION_END.json')['parents']:
        base=ROOT.parent/parent['folder'];assert sha(base/'DELIVERY_MANIFEST.json')==parent['manifest_sha256']
        for r in read(base/'DELIVERY_MANIFEST.json')['files']:assert sha(base/r['path'])==r['sha256'],r['path']
    for r in read(ROOT/'MODEL_CHECKPOINT_MANIFEST.json')['files']:
        p=ROOT/r['path']
        if p.exists():assert sha(p)==r['sha256'],r['path']
    assert read(ROOT/'VALIDATION.json')['PASS']
    assert read(ROOT/'PORTABLE_MEMBERSHIP_AUDIT.json')['PASS']
    assert read(ROOT/'INDEPENDENT_REVIEW.json')['PASS']
    assert read(ROOT/'TEST_RESULTS.json')['PASS']
    print('DELIVERY_VERIFY_PASS',len(manifest['files']),sum(r['bytes'] for r in manifest['files']),flush=True)
def seal():
    assert not (ROOT/'DELIVERY_MANIFEST.json').exists()
    models=[];full=[]
    for p in sorted((ROOT/'fits').glob('*/*/RECEIPT.json')):
        r=read(p)
        for name,digest in r['models'].items():
            m=p.parent/name;assert sha(m)==digest
            models.append({'path':m.relative_to(ROOT).as_posix(),'bytes':m.stat().st_size,'sha256':digest})
        m=p.parent/'MEMBERSHIP.parquet';assert sha(m)==r['membership_sha256']
        full.append({'path':m.relative_to(ROOT).as_posix(),'bytes':m.stat().st_size,'sha256':r['membership_sha256']})
    assert len(models)==236 and len(full)==118
    write(ROOT/'MODEL_CHECKPOINT_MANIFEST.json',{'time':now(),'retention':'local unchanged; omitted from Git; reproduce with pinned source/config/input/environment','files':models})
    write(ROOT/'FULL_LOCAL_MEMBERSHIP_MANIFEST.json',{'time':now(),'retention':'local unchanged; exact delivered representation is ROW_IDS.npz + PORTABLE_MEMBERSHIP.json + frozen parent source/algorithm','files':full})
    files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(ROOT.rglob('*')) if p.is_file() and included(p)]
    write(ROOT/'DELIVERY_MANIFEST.json',{'time':now(),'base_commit':'d078bdc3d849f62ccd12db8baee6f95e67c0d2be','scope':'docs/runtime_vnext4_gpu_censored_running','files':files})
    verify()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['seal','verify']);a=p.parse_args();globals()[a.stage]()

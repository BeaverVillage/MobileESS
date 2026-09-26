"""Manifest, byte verification and immutable parent preservation."""
from pathlib import Path
import argparse,hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def included(p):return '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='DELIVERY_MANIFEST.json'
def verify():
    m=read(ROOT/'DELIVERY_MANIFEST.json')
    for r in m['files']:assert sha(ROOT/r['path'])==r['sha256'] and (ROOT/r['path']).stat().st_size==r['bytes'],r['path']
    assert {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and included(p)}=={r['path'] for r in m['files']}
    registration=read(ROOT/'REGISTRATION.json');freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json');complete=read(ROOT/'EVALUATION_COMPLETE.json')
    for n,h in registration['code'].items():assert sha(ROOT/n)==h==freeze['code'][n]
    assert sha(ROOT/'SOURCE_FORECASTS.parquet')==registration['source_forecasts_sha256']
    assert sha(ROOT/'REGISTRATION.json')==freeze['registration_sha256']
    assert sha(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv')==freeze['metrics_sha256']
    assert sha(ROOT/'DEV_CAL_PREDICTIONS.parquet')==freeze['DEV_CAL_predictions_sha256']
    assert sha(ROOT/'PREDICTIONS.parquet')==complete['prediction_sha256']
    assert sha(ROOT/'FINAL_SELECTION_FREEZE.json')==complete['freeze_sha256']
    for parent in read(ROOT/'PARENT_PRESERVATION_END.json')['parents']:
        p=ROOT.parent/parent['parent'];assert sha(p/'DELIVERY_MANIFEST.json')==parent['manifest_sha256']
        for r in read(p/'DELIVERY_MANIFEST.json')['files']:assert sha(p/r['path'])==r['sha256']
    for n in ['TEST_RESULTS.json','VALIDATION.json','INDEPENDENT_REVIEW.json','VISUAL_QA.json']:assert read(ROOT/n)['PASS'],n
    print('DELIVERY_VERIFY_PASS',len(m['files']),sum(r['bytes'] for r in m['files']))
def seal():
    m=dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),base_commit='1702abdd14db3ad6e5a63211459b9b99d6a8a054',scope='docs/runtime_vnext5_r2_causal_calibration',files=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(ROOT.rglob('*')) if p.is_file() and included(p)])
    with (ROOT/'DELIVERY_MANIFEST.json').open('x',encoding='utf-8') as f:json.dump(m,f,indent=2,ensure_ascii=False)
    verify()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['seal','verify']);a=p.parse_args();globals()[a.stage]()

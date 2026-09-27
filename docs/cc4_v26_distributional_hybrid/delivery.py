"""Write-once evidence delivery, no scientific selection or forecast changes."""
from pathlib import Path
import argparse,hashlib,importlib.metadata,json,platform,sys
ROOT=Path(__file__).resolve().parent
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(n,v):
    with (ROOT/n).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False)
def verify():
    rows=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))['files']
    for r in rows:
        p=ROOT/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],r['path']
    print('DELIVERY PASS',len(rows))
def seal():
    assert not (ROOT/'DELIVERY_MANIFEST.json').exists()
    for n in ['VALIDATION.json','RESULT_REVIEW.json','REUSE_AUDIT.json','TEST_RESULTS.json','LEAKAGE_MATURITY_AUDIT.json']:
        assert json.loads((ROOT/n).read_text(encoding='utf-8'))['PASS']
    from study import guard,source_guard
    guard(True);source_guard()
    models=sorted((ROOT/'fits').rglob('*.txt.gz'));audit=json.loads((ROOT/'VALIDATION.json').read_text())
    assert len(models)==audit['checkpoint_replays']
    write('MODEL_CHECKPOINT_MANIFEST.json',dict(storage='local preserved; exact deterministic recipe/membership/digests in Git',files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in models]))
    write('ENVIRONMENT.json',dict(python=sys.version,executable=sys.executable,platform=platform.platform(),packages={n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','lightgbm','pyarrow','scikit-learn']},neural='reused original forecasts; environment authority in PR64'))
    rows=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or p in models or '__pycache__' in p.parts or p.suffix in ['.pyc','.pid']:continue
        rows.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size))
    write('DELIVERY_MANIFEST.json',dict(files=rows,checkpoints=len(models),scientific_decisions_unchanged=True));verify()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['seal','verify']);a=p.parse_args();globals()[a.stage]()

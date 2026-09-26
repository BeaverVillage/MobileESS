"""Delivery sealing / portable integrity verification; no model decisions."""
from pathlib import Path
import argparse,hashlib,json,sys,platform,importlib.metadata
ROOT=Path(__file__).resolve().parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,v):
 with (ROOT/p).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2,ensure_ascii=False)
def verify():
 m=json.loads((ROOT/'DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
 for r in m['files']:
  p=ROOT/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],r['path']
 print('PORTABLE DELIVERY PASS',len(m['files']),flush=True)
def seal():
 assert not (ROOT/'DELIVERY_MANIFEST.json').exists(),'ALREADY_SEALED'
 for name in ['VALIDATION.json','INDEPENDENT_AUDIT.json']:
  assert json.loads((ROOT/name).read_text(encoding='utf-8'))['PASS'],name
 from study import source_guard,code_guard
 source_guard();code_guard('FINAL_SELECTION_FREEZE.json')
 weights=sorted((ROOT/'fits').rglob('*.txt.gz'))
 write('MODEL_CHECKPOINT_MANIFEST.json',dict(storage='preserved locally; deterministic recipe reproduces; not in Git',files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in weights]))
 packages={n:importlib.metadata.version(n) for n in ['numpy','pandas','lightgbm','pyarrow','scikit-learn']}
 write('ENVIRONMENT.json',dict(python=sys.version,executable=sys.executable,platform=platform.platform(),packages=packages))
 files=[]
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts or p in weights or p.suffix in ['.pid','.pyc']:continue
  files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size))
 write('DELIVERY_MANIFEST.json',dict(files=files,checkpoints=len(weights),model_decisions_unchanged=True))
 verify()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['seal','verify']);a=p.parse_args();seal() if a.stage=='seal' else verify()

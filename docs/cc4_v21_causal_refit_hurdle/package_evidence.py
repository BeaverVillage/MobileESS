"""Delivery-only manifest. Does not fit, calibrate, select or change predictions."""
from common import *
import importlib.metadata,platform,sys,tarfile,gzip,io

def main():
 require(not (ROOT/'DELIVERY_MANIFEST.json').exists(),'DELIVERY_ALREADY_SEALED')
 require(json.loads((ROOT/'VALIDATION.json').read_text(encoding='utf-8'))['PASS'],'VALIDATION_NOT_PASSED')
 weights=[p for p in (ROOT/'fits').rglob('*') if p.is_file() and (p.name.endswith('.txt.gz') or p.name.endswith('.pkl.gz') or p.suffix=='.pt') and '.reuse-staging' not in str(p)]
 records=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(weights)]
 pd.DataFrame(records).to_csv(ROOT/'MODEL_CHECKPOINT_MANIFEST.csv',index=False)
 bundle_members=[];bundle=ROOT/'FIT_AUDIT_BUNDLE.tar.gz';cc=ROOT.name.startswith('cc4')
 if cc:
  excluded_weights=set(weights)
  with bundle.open('wb') as stream,gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as archive:
   for p in sorted((ROOT/'fits').rglob('*')):
    if not p.is_file() or p in excluded_weights or '.reuse-staging' in str(p):continue
    content=p.read_bytes();name=p.relative_to(ROOT).as_posix();entry=tarfile.TarInfo(name);entry.size=len(content);entry.mtime=0;entry.mode=0o644
    archive.addfile(entry,io.BytesIO(content));bundle_members.append(dict(path=name,sha256=hashlib.sha256(content).hexdigest(),bytes=len(content)))
  dump('FIT_AUDIT_BUNDLE_MEMBERS.json',dict(archive_sha256=sha(bundle),members=bundle_members))
 packages={}
 for name in ['numpy','pandas','pyarrow','lightgbm','torch','xgboost','scikit-learn','scipy','joblib','threadpoolctl']:
  try:packages[name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:pass
 dump('REPRODUCIBILITY_MANIFEST.json',dict(time=now(),python=sys.version,executable=sys.executable,platform=platform.platform(),packages=packages,
  checkpoint_files=len(records),checkpoint_bytes=sum(r['bytes'] for r in records),checkpoint_storage='preserved locally in fits; not committed to Git; deterministic scripts and exact membership reproduce predictions',
  source_data='frozen parent authority or raw archive with registered digest; see SOURCE_MANIFEST/PREPARATION_COMPLETE and common.py',
  delivery_only=True,model_selection_changed=False))
 excluded=set(weights);files=[]
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file():continue
  relative=p.relative_to(ROOT);parts=relative.parts
  if (cc and parts[0]=='fits') or p in excluded or any(s in ['cache','locks','__pycache__'] or '.reuse-staging' in s for s in parts) or p.suffix in ['.pyc','.pid']:continue
  if p.name=='DELIVERY_MANIFEST.json':continue
  files.append(dict(path=relative.as_posix(),sha256=sha(p),bytes=p.stat().st_size))
 dump('DELIVERY_MANIFEST.json',dict(time=now(),files=files,checkpoint_manifest_sha256=sha(ROOT/'MODEL_CHECKPOINT_MANIFEST.csv'),
  model_outputs_unchanged=True,production_modified=False,optimizer_or_grid_executions=0),exclusive=True)
 print('DELIVERY SEALED',len(files),'files; checkpoints',len(records),flush=True)

if __name__=='__main__':main()

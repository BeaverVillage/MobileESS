from common7 import *
import sys,platform,importlib.metadata,datetime

def main():
    assert read(ROOT/'VERIFICATION.json')['status']=='PASS'
    write('ENVIRONMENT_RECEIPT.json',dict(python=sys.version,platform=platform.platform(),packages={n:importlib.metadata.version(n) for n in ['pandas','numpy','pyarrow']},
      precision='UTC timestamps; no ML or accelerator package used; no dataset de-anonymization',created_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(part in {'.local','__pycache__'} for part in p.relative_to(ROOT).parts) or p.name=='DELIVERY_MANIFEST.json':continue
        files.append(dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write('DELIVERY_MANIFEST.json',dict(base_commit=BASE,scope='docs/runtime_vnext7_feature_authority_recovery only',files=files,excludes=['.local/','__pycache__/','DELIVERY_MANIFEST.json'],verification='VERIFICATION.json',frozen_contract='FEATURE_AUTHORITY_FREEZE.json'))
    print('DELIVERY',len(files),'files plus manifest',flush=True)
if __name__=='__main__':main()

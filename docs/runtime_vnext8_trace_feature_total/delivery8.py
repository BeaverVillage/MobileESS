from common8 import *
def main():
    assert read(ROOT/'VERIFICATION.json')['status']=='PASS'
    files=[]
    for p in sorted(ROOT.rglob('*')):
        rel=p.relative_to(ROOT)
        if not p.is_file() or '.local' in rel.parts or '__pycache__' in rel.parts or p.name=='DELIVERY_MANIFEST.json':continue
        files.append(dict(relative=rel.as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write('DELIVERY_MANIFEST.json',dict(base=BASE,scope='docs/runtime_vnext8_trace_feature_total only',files=files,excludes=['.local/','__pycache__/','DELIVERY_MANIFEST.json'],
      verified_negative_result=True,no_production_model=True,provider_bundle='RUNTIME_PROVIDER',verification='VERIFICATION.json'))
    print('DELIVERY',len(files),'files + manifest',sum(x['bytes'] for x in files),'bytes')
if __name__=='__main__':main()

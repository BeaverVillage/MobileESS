from common16 import *
import csv

def check_old():
    before=read(ROOT/'BASE_PRESERVATION_RECEIPT.json')
    for r in before['tracked_files']:
        p=REPO/r['relative'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
    for r in before['local_inputs']:
        p=Path(r['path']);assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
    manifest=read(V15/'DELIVERY_MANIFEST.json')
    for r in manifest['files']:assert sha(V15/r['relative'])==r['sha256'],r['relative']
    for r in manifest['repository_files']:assert sha(REPO/r['relative'])==r['sha256'],r['relative']
    n=0
    with (V14/'RAW_SOURCE_INVENTORY.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            p=Path(r['directory'])/r['filename'];st=Path('\\\\?\\'+str(p)).lstat()
            assert (st.st_size,st.st_mtime_ns)==(int(r['size_bytes']),int(r['mtime_ns'])),str(p);n+=1
    return dict(PASS=True,tracked_files=len(before['tracked_files']),prior_local_evidence=len(before['local_inputs']),raw_size_mtime_fingerprints=n,
        V15_delivery_manifest_unchanged=True,V42_previous_source_unchanged=True)

if __name__=='__main__':print(check_old(),flush=True)

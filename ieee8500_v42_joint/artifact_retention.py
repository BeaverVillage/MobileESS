"""Seal dense local archives without AC replay; publish reviewable evidence separately."""
from .run_ac import REPORT,HIGH,ROOT,receipt,read,write,sha
import gzip
import shutil
import hashlib


def run():
    manifest=REPORT/'LOCAL_DENSE_AC_RETENTION.json'
    if manifest.exists():return read(manifest)
    archives={}
    for report in (HIGH,REPORT):
        for p in sorted((report/'ac').glob('*/AC_96.npz')):
            archives[str(p.relative_to(ROOT))]=receipt(p)
    result=dict(schema='LOCAL_DENSE_AC_RETENTION_V1',files=archives,
        bytes=sum(v['bytes'] for v in archives.values()),
        scope='full dense AC arrays preserved in this checkout; excluded from Git transport to avoid multi-GB duplicate payload',
        committed_evidence='all slot CSV, raw PCC/customer/PV, focused phasor, axes, live parameter/control/port readback, receipts and verification',
        remote_clone_dense_AC_available=False,
        remote_verification_requires='restore these exact SHA archives; never substitute a summary for full-node thermal/voltage evidence',
        additional_AC_calls=0,Native_calls=0)
    write(manifest,result)
    return result


def package_json():
    path=REPORT/'JSON_TRANSPORT_MANIFEST.json'
    if path.exists():return read(path)
    files={}
    for report in (HIGH,REPORT):
        for name in ('AC_AXES.json','PARAMETER_SNAPSHOT.json'):
            for p in sorted((report/'ac').glob('*/'+name)):
                gz=p.with_suffix('.json.gz')
                if not gz.exists():
                    with p.open('rb') as src,gz.open('wb') as out,gzip.GzipFile(filename='',mode='wb',fileobj=out,mtime=0) as zipped:
                        shutil.copyfileobj(src,zipped)
                digest=hashlib.sha256()
                with gzip.open(gz,'rb') as restored:
                    for chunk in iter(lambda:restored.read(1024*1024),b''):digest.update(chunk)
                assert digest.hexdigest()==sha(p),'EXACT_GZIP_ROUNDTRIP_FAILURE'
                files[str(p.relative_to(ROOT))]=dict(original=receipt(p),gzip=receipt(gz),
                    decoded_SHA256_equal=True,restore='gzip decompress to exact original name; original files remain locally preserved')
    doc=dict(schema='EXACT_JSON_GZIP_TRANSPORT_V1',files=files,
        original_bytes=sum(r['original']['bytes'] for r in files.values()),
        transported_bytes=sum(r['gzip']['bytes'] for r in files.values()),
        additional_AC_calls=0,original_files_changed=0)
    write(path,doc)
    return doc


def verify_json_transport():
    manifest=REPORT/'JSON_TRANSPORT_MANIFEST.json';doc=read(manifest);verified={}
    for relative,entry in doc['files'].items():
        gz=ROOT/(relative+'.gz');digest=hashlib.sha256()
        with gzip.open(gz,'rb') as restored:
            for chunk in iter(lambda:restored.read(1024*1024),b''):digest.update(chunk)
        assert digest.hexdigest()==entry['original']['sha256'],'EXACT_GZIP_ROUNDTRIP_FAILURE'
        verified[relative]=dict(original_SHA256=entry['original']['sha256'],decoded_SHA256_equal=True)
    result=dict(manifest=receipt(manifest),files=verified,all_decoded_bytes_match=True,
        additional_AC_calls=0,original_files_changed=0)
    write(REPORT/'JSON_TRANSPORT_ROUNDTRIP_VERIFICATION.json',result)
    return result

if __name__=='__main__':
    import sys
    verify_json_transport() if '--verify-json' in sys.argv else package_json() if '--package-json' in sys.argv else run()

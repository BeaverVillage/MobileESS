"""Hash-only preservation verification. No historical performance ingestion."""
from electrical_engine import H,ROOT,BIND,read,save,record,sha
import time
def main():
    start=time.perf_counter()
    sources=[
      BIND/'RECONSTRUCTION_FREEZE_MANIFEST.json',
      BIND/'ORIGINAL_V41R4_SOURCE_SHA256.json',
      ROOT/'IEEE8500_production_20260911/PROTECTED_AUTHORITIES_BEFORE.json',
      ROOT/'IEEE8500_binding_audit_20260911/PRESERVED_PRODUCTION_SHA256.json',
    ]
    results=[];cache={}
    for manifest in sources:
        value=read(manifest);rows=value if isinstance(value,list) else value['files'];bad=[]
        for r in rows:
            p=r['path']
            if p not in cache:cache[p]=sha(p)
            if cache[p]!=r['sha256']:bad.append(dict(path=p,expected=r['sha256'],actual=cache[p]))
        results.append(dict(manifest=record(manifest),file_count=len(rows),mismatches=bad,status='PASS' if not bad else 'FAIL_CLOSE'))
        print('IMMUTABILITY',manifest.name,len(rows),len(bad),flush=True)
    out=dict(status='PASS' if all(r['status']=='PASS' for r in results) else 'FAIL_CLOSE',verification='SHA256 only; stopped production content not parsed, imported, or reused',manifests=results,wall_seconds=time.perf_counter()-start)
    save(H/'IMMUTABLE_AUTHORITIES_VERIFIED.json',out)
    assert out['status']=='PASS'
if __name__=='__main__':main()

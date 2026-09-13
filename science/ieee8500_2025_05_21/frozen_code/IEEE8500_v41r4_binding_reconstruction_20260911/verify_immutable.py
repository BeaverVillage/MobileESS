"""Hash-only verification of preserved evidence; no scientific reuse."""
import hashlib,json
from pathlib import Path
H=Path(__file__).absolute().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
cache={}
def sha(p):
    p=Path(p);key=str(p.resolve())
    if key not in cache:
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(8388608),b''):h.update(b)
        cache[key]=h.hexdigest()
    return cache[key]
checks=[]
for scope,p in [('STOPPED_NONAUTHORITATIVE_PRESERVED',H.parent/'IEEE8500_binding_audit_20260911/PRESERVED_PRODUCTION_SHA256.json'),('TOPOLOGY_PCC_ELECTRICAL_OPERATING_AUTHORITY_PRESERVED',H.parent/'IEEE8500_production_20260911/PROTECTED_AUTHORITIES_BEFORE.json'),('V41R4_AIDC_SOURCES_UNCHANGED',H.parent/'IEEE8500_binding_audit_20260911/READ_ONLY_SOURCE_SHA256.json')]:
    v=read(p);rows=v if isinstance(v,list) else v['files'];bad=[]
    for r in rows:
        if not Path(r['path']).exists():bad.append(dict(path=r['path'],reason='MISSING'))
        elif sha(r['path'])!=r['sha256']:bad.append(dict(path=r['path'],reason='SHA256_DRIFT'))
    checks.append(dict(scope=scope,files=len(rows),drift=bad,verification='HASH_ONLY_NO_RESULT_OR_CODE_REUSE'))
    print(scope,len(rows),len(bad),flush=True)
(H/'IMMUTABLE_AUTHORITY_VERIFICATION.json').write_text(json.dumps(dict(status='PASS' if not any(c['drift'] for c in checks) else 'FAIL_CLOSE',checks=checks),indent=2),encoding='utf-8')

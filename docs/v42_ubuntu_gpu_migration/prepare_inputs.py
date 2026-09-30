"""Resolve and seal exact PR102 authorities, not whole obsolete workspaces."""
import json,hashlib,csv,os,shutil,re
from pathlib import Path
HERE=Path(__file__).absolute().parent;ROOT=HERE.parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def norm(p):return str(p).replace('\\','/').rstrip('/')
recovery={norm(r['original']):r['resolved'] for r in read(ROOT/'docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json')['recovered']}
rows={};unresolved=[]
def add(path,expected=None,role='IMMUTABLE_AUTHORITY'):
    name=norm(path);p=Path(name)
    if not p.is_file() and name in recovery:p=Path(recovery[name]['path'])
    if not p.is_file():unresolved.append(dict(path=name,expected=expected,role=role));return
    h=sha(p)
    if expected and expected!=h:raise ValueError('HASH_DRIFT:'+name)
    logical=norm(p);parts=logical.split('/')
    if 'codex_mobileess_workspace' in parts:rel='/'.join(parts[parts.index('codex_mobileess_workspace')+1:])
    elif 'Mobile ESS 2' in parts:rel='/'.join(parts[parts.index('Mobile ESS 2')+1:])
    else:rel=h[:16]+'/'+p.name
    dest='/home/jaewon/mobileess_data/immutable_inputs/'+rel
    rows[name]=dict(source=str(p.absolute()),logical_source=name,destination=dest,bytes=p.stat().st_size,sha256=h,role=role,ubuntu_sha256='',hash_pass=False)
def walk(x,role):
    if isinstance(x,dict):
        if 'path' in x and 'sha256' in x:add(x['path'],x['sha256'],role)
        for v in x.values():walk(v,role)
    elif isinstance(x,list):
        for v in x:walk(v,role)
bundle=read(ROOT/'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
walk(bundle,'FINAL_NATIVE_BUNDLE_AUTHORITY')
certificate=bundle['electrical_certificate'];cert=read(certificate['path'])
walk(cert['outputs'],'NATIVE_ELECTRICAL_ARRAY')
inputs=cert['input_identity']['identity']['inputs']
for key in ('OpenDSS_master','PCC_mapping','service_PCC_mapping','weather','demand','PV','feeder_manifest','line_ratings','transformer_ratings','native_controls','background_mapping','AIDC_power_C1'):
    if key in inputs:walk(inputs[key],key)
for row in list(rows.values()):
    p=Path(row['source'])
    if p.suffix=='.py' and 'dayahead' in p.parts:
        i=p.parts.index('dayahead')
        for level in range(i,len(p.parts)-1):
            init=Path(*p.parts[:level+1])/'__init__.py'
            if init.exists():add(init,None,'EXACT_PACKAGE_PLUMBING')
root=Path('C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase')
for rel in ('dayahead/authority.py','dayahead/v28/forecast.py','dayahead/v28r2/authority.py','dayahead/v28/thermal.py','dayahead/v28r2/c1_affine.py','dayahead/v39a/contracts.py'):
    add(root/rel,None,'EXACT_TRANSITIVE_POWER_SOURCE')
with (HERE/'V42_DATA_MIGRATION_MANIFEST.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(next(iter(rows.values()))));w.writeheader();w.writerows(rows.values())
(HERE/'INPUT_DISCOVERY.json').write_text(json.dumps(dict(files=len(rows),bytes=sum(x['bytes'] for x in rows.values()),unresolved=unresolved),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('sealed',len(rows),'bytes',sum(x['bytes'] for x in rows.values()),'unresolved',len(unresolved))
for x in unresolved:print(x)

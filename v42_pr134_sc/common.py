import csv
import hashlib
import json
import os
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_a1_pr134_supercompact_exact_20261007'
LOCAL = ROOT / '.pr134_sc_local'
BASE = '52ef855a59144a7c561df44b81dc2ad265babdbd'
DAY = '2025-05-01'

def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k,v in x.items()}
    if isinstance(x, (list,tuple,np.ndarray)): return [clean(v) for v in x]
    if isinstance(x, np.generic): return clean(x.item())
    if isinstance(x, Path): return str(x)
    if isinstance(x, float) and not np.isfinite(x): return str(x)
    return x

def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT/name
    tmp = p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    os.replace(tmp,p)

def table(name, rows, fields=None):
    rows=list(rows); OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]),lineterminator='\n')
        w.writeheader(); w.writerows({k:json.dumps(clean(v)) if isinstance(v,(list,dict,tuple)) else v for k,v in r.items()} for r in rows)

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def record(p): return dict(path=str(Path(p).resolve()),sha256=sha(p),bytes=Path(p).stat().st_size)

def read_artifact(name):
    import gzip
    p=OUT/name
    value=json.loads(p.read_text(encoding='utf8'))
    if isinstance(value,dict) and value.get('lossless_gzip'):
        compressed=OUT/value['lossless_gzip']
        if sha(compressed)!=value['sha256']:raise ValueError('ARCHIVE_SHA_DRIFT')
        payload=gzip.decompress(compressed.read_bytes())
        if hashlib.sha256(payload).hexdigest()!=value['original_sha256']:raise ValueError('PAYLOAD_SHA_DRIFT')
        return json.loads(payload)
    return value

def attributes(name='A0'):
    """Immutable original attributes plus lossless dictionary-coded family axes."""
    p=LOCAL/(name+'_ATTRIBUTES.npz'); compact=LOCAL/(name+'_ATTRIBUTES_CODED.npz')
    if compact.exists():
        z=dict(np.load(compact))
        z['lb']=np.where(z['lb']<=-1e100,-np.inf,z['lb'])
        z['ub']=np.where(z['ub']>=1e100,np.inf,z['ub'])
        return z
    z=dict(np.load(p))
    for k in ('vf','rf'):
        if z[k].dtype.kind in 'US':
            labels,codes=np.unique(z[k],return_inverse=True)
            z[k]=codes.astype(np.uint16);z[k+'_names']=labels
    z['lb']=np.where(z['lb']<=-1e100,-np.inf,z['lb'])
    z['ub']=np.where(z['ub']>=1e100,np.inf,z['ub'])
    np.savez_compressed(compact,**z)
    return z

def proof_data(name):
    z=dict(np.load(LOCAL/(name+'_PROOF.npz')))
    for k in list(z):
        if k.endswith('_delta'):z[k[:-6]]=np.cumsum(z.pop(k),dtype=np.int64)
    return z

def process_inventory():
    import psutil
    result=[]
    for p in psutil.process_iter(['pid','create_time','cmdline','cpu_times']):
        try:
            a=p.info; cmd=a['cmdline'] or []
            if cmd and 'python' in Path(cmd[0]).name.lower() and any('benchmark' in s or 'worker' in s or 'canary' in s for s in cmd):
                result.append(dict(pid=p.pid,created=a['create_time'],command=cmd,cwd=p.cwd(),cpu_seconds=sum(a['cpu_times'][:2])))
        except (psutil.NoSuchProcess,psutil.AccessDenied): pass
    return result

import os
os.environ.update(dict.fromkeys(('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'),'1'))
from pathlib import Path
import json,csv,hashlib,math
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_supercompact_exact_20261006'
OLD=ROOT/'docs/v42_m1_exact_redundancy_audit_20261006'
BASE='8513a281615d9e0fd0af2b7cb3d36b6f8a1fb962'
REFERENCE='c7d808a315e04aefc1bcfc537b84cc38d895a9ab'
def write(n,x):
    OUT.mkdir(parents=True,exist_ok=True)
    def clean(v):
        if isinstance(v,float) and not math.isfinite(v):
            if math.isnan(v):raise ValueError('NaN scientific/evidence metadata is forbidden')
            return 'Infinity' if v>0 else '-Infinity'
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):return [clean(x) for x in v]
        return v
    (OUT/n).write_bytes((json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def prose(n,x):
    OUT.mkdir(parents=True,exist_ok=True);(OUT/n).write_bytes((x.rstrip()+'\n').encode())
def read(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def table(n,rows,fields):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/n).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

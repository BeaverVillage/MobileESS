from pathlib import Path
import json,csv,hashlib,math
import numpy as np
from scipy import sparse
from v42_supercompact.formulation import census,residual
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_ultracompact_exact_20261006'
PARENT=ROOT/'docs/v42_m1_supercompact_exact_20261006'
BASE='4f45f04d685d5d5e689463f953695fe40d52cf98'
OUT.mkdir(exist_ok=True)
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not math.isfinite(x):
        assert not math.isnan(x)
        return 'Infinity' if x>0 else '-Infinity'
    return x
def write(n,x): (OUT/n).write_bytes((json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))
def prose(n,x): (OUT/n).write_bytes(x.encode('utf-8'))
def read(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def table(n,rows,fields):
    with (OUT/n).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader()
        for r in rows:w.writerow({k:json.dumps(clean(v),ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list,tuple)) else v for k,v in r.items() if k in fields})
def load(label='C2'):
    p=PARENT if label=='C2' else OUT
    A=sparse.load_npz(p/(label+'_A.npz'))
    with np.load(p/(label+'_DATA.npz')) as z:d={k:z[k] for k in z.files}
    return A,d
def save(label,A,d):sparse.save_npz(OUT/(label+'_A.npz'),A);np.savez_compressed(OUT/(label+'_DATA.npz'),**d)
def family(n):return str(n).split('[')[0]

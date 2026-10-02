from pathlib import Path
import csv,gzip,hashlib,json,os,subprocess,time
import numpy as np
from scipy import sparse
from v42_benders_v2.representation import Native
from v42_benders.canonical import digest_arrays

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_benders_x0_certificate_repair'
PRIOR=ROOT/'docs/v42_mess_benders_v2_fullscale_loop'
BASE='e2d4779685fff6d0cf022c649733b2ca41fdfc08'
X0='5c8702f5d7cf2e1e278e195f89a9f034c7e5ffbb6440e0f0b4931a0ee9b6e3f3'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def stamp():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def read(name,directory=OUT):return json.loads((Path(directory)/name).read_text(encoding='utf8'))
def dump(name,value,directory=OUT):
    p=Path(directory)/name;p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('w',encoding='utf8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def table(name,rows,fields):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def load_x0():
    r=read('MASTER_X_000_RECEIPT.json',PRIOR)
    assert r['vector_sha256']==X0 and r['vector_length']==85744 and r['persisted_before_recourse']
    assert sha(PRIOR/'MASTER_X_000.npz')==r['npz_sha256'] and sha(PRIOR/'MASTER_X_000_AXIS.json')==r['axis_json_sha256']
    with np.load(PRIOR/'MASTER_X_000.npz') as z:
        x=z['values'];names=z['names'];indices=z['original_column_indices'];bits=z['bits']
    assert x.dtype==np.float64 and bits.dtype==np.uint8 and np.array_equal(bits,x) and np.isin(x,[0,1]).all()
    assert digest_arrays(x)==X0 and digest_arrays(names,indices)==r['axis_hash'] and digest_arrays(bits)==r['bits_sha256']
    return x,r
def load_native():
    receipt=read('RECOURSE_000_NATIVE_RAW_RECEIPT.json',PRIOR)
    journal=PRIOR/'native/raw_certificates.jsonl.gz'
    with gzip.open(journal,'rb') as f:payload=next(f).rstrip(b'\n')
    assert hashlib.sha256(payload).hexdigest()==receipt['persistence']['payload_sha256']
    raw=json.loads(payload);assert sha(PRIOR/'native/axis.npz')==raw['axis_npz_sha256']
    raw['persistence']=receipt['persistence']
    with np.load(PRIOR/'native/axis.npz') as z:
        A=sparse.csr_matrix((z['matrix_data'],z['matrix_indices'],z['matrix_indptr']),shape=(len(z['b']),len(z['lower'])))
        B=sparse.csr_matrix((z['B_data'],z['B_indices'],z['B_indptr']),shape=(len(z['b']),len(z['xi'])))
        n=Native(A,B,z['b'],z['row_senses'],z['lower'],z['upper'],np.zeros(len(z['yi'])),z['xi'],z['yi'],
            np.zeros(len(z['xi'])),np.ones(len(z['xi'])),z['original_names'],z['row_names'],0.,raw['source_hash'])
    x,r=load_x0()
    assert digest_arrays(n.names[n.xi],n.xi)==r['axis_hash'] and np.array_equal(raw['source_x'],x)
    assert np.array_equal(n.rhs(x),raw['solver_rhs'])
    return n,raw
def preserve():
    rows=read('PR117_BASE_RECEIPT.json')['files']
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in rows),'INHERITED_BYTES_CHANGED'
    return len(rows)

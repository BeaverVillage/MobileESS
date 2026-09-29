from pathlib import Path
import datetime, hashlib, json, os, sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
LOCAL=ROOT/'.local'
V13=REPO/'docs/runtime_vnext13_current_workload_state'
V9=REPO/'docs/runtime_vnext9_distributional_runtime'
BASE='0002f946aa0f8089eb5fbf18758b50e78d80bf16'
RAW_A=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터')
RAW_B=RAW_A/'데이터 센터'
CUTOFF=pd.Timestamp('2025-04-01T00:00:00Z')

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.ndarray):return clean(v.tolist())
    if hasattr(v,'item'):return clean(v.item())
    if isinstance(v,float) and not np.isfinite(v):return None
    return v
def write(name,v):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')

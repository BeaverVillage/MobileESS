from pathlib import Path
from datetime import timezone,datetime
import os,json,hashlib,subprocess
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dayahead/artifacts/v40r4_compound_gpuwork_arrival'
R3=Path('C:/codex_mobileess_workspace/MobileESS_v40r3_causal_gpuwork_arrival_ml')
OLD=R3/'dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml'
BASE='43710c96c36f7e66257885a56ef6df697b3c53bb'
SCI='6e2f0791952a9001d2fdd4a6564e0f699ec3fc90'
SEED=20260907
MAY=pd.Timestamp('2025-05-01',tz='UTC')
os.environ['GIT_OPTIONAL_LOCKS']='0'
def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd).decode('utf-8').strip()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def clean(x):
    if x is pd.NaT or x is pd.NA:return None
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,(Path,pd.Timestamp,datetime)):return str(x)
    if isinstance(x,(np.integer,np.bool_)):return x.item()
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    return x
def dump(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def old(name):return json.loads((OLD/name).read_text(encoding='utf-8'))
def stats(x):
    x=np.asarray(x,float);x=x[np.isfinite(x)]
    return {'N':len(x),'mean':np.mean(x) if len(x) else None,'variance':np.var(x,ddof=1) if len(x)>1 else None,
       'quantiles':dict(zip(['P50','P75','P90','P95','P97.5','P99','P99.5','max'],np.quantile(x,[.5,.75,.9,.95,.975,.99,.995,1]))) if len(x) else {}}
def data():
    a=np.load(OUT/'inputs/causal_dataset.npz');i=pd.read_parquet(OUT/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    j=pd.read_parquet(OUT/'inputs/GPU_related_candidates_preMay.parquet')
    masks={r:((i.role==r)&i.stage_maturity_eligible).to_numpy() for r in ['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']}
    return a,i,j,masks

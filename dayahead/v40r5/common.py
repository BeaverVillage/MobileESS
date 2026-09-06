from pathlib import Path
from datetime import datetime,timezone
import os,json,hashlib,subprocess
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'
R4=ROOT.parent/'MobileESS_v40r4_compound_gpuwork_arrival'
R3=ROOT.parent/'MobileESS_v40r3_causal_gpuwork_arrival_ml'
R4OUT=R4/'dayahead/artifacts/v40r4_compound_gpuwork_arrival'
R3OUT=R3/'dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml'
BASE='ff1fec3a7d8f80b3c2af496758747fafc04bad7b'
PR_HEAD='a2a21c904535125c66668a294f91d73a66f5d4a7'
SEED=20260907
STEP=900*10**9
MAY=pd.Timestamp('2025-05-01',tz='UTC')
os.environ['GIT_OPTIONAL_LOCKS']='0'
def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd).decode('utf-8').strip()
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def clean(x):
    if x is pd.NaT or x is pd.NA:return None
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,(np.integer,np.bool_)):return x.item()
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    if isinstance(x,(Path,pd.Timestamp,datetime)):return str(x)
    return x
def dump(name,obj):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def external(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def ns(series):return series.dt.as_unit('ns').astype('int64').to_numpy()
def statistics(x):
    x=np.asarray(x,float)
    return {'N':len(x),'mean':x.mean(),'variance':x.var(ddof=1),'variance_mean_ratio':x.var(ddof=1)/x.mean() if x.mean() else None,
      'zero_fraction':np.mean(x==0),'positive_fraction':np.mean(x>0),
      'quantiles':dict(zip(['P50','P75','P90','P95','P97.5','P99','max'],np.quantile(x,[.5,.75,.9,.95,.975,.99,1])))}
def allowed(path):return path.startswith(('dayahead/v40r5/','dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/')) or (path.startswith('tests/dayahead/test_v40r5_') and path.endswith('.py'))
def data():
    a=np.load(OUT/'data.npz');i=pd.read_parquet(OUT/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    m={r:np.repeat(((i.role==r)&i.stage_maturity_eligible).to_numpy(),96) for r in ['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']}
    return a,i,m
def authority():
    reg=read('V40R5_PREREGISTRATION.json');c=read('V40R5_PREREGISTRATION_COMMIT_RECEIPT.json')['commit']
    assert git('merge-base','--is-ancestor',c,'HEAD')==''
    b=subprocess.check_output(['git','show',c+':dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_PREREGISTRATION.json'],cwd=ROOT)
    assert hashlib.sha256(b).hexdigest()==sha(OUT/'V40R5_PREREGISTRATION.json')
    for p,h in reg['frozen_hashes'].items():assert sha(ROOT/p)==h,('FROZEN_AUTHORITY_CHANGED',p)
    return reg,c

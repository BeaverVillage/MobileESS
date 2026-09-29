from pathlib import Path
import datetime, hashlib, json, subprocess
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
LOCAL=ROOT/'.local'
V9=REPO/'docs/runtime_vnext9_distributional_runtime'
V13=REPO/'docs/runtime_vnext13_current_workload_state'
V16=REPO/'docs/runtime_vnext16_raddit_rich_metadata'
BASE='f60a6a43f08caf3d7fe3b338b7a9e47476a8f284'
ARMS={'V9_D1_ROLLING14':'D1__ROLLING14','V9_D2_NORMAL_1P5_NONE':'D2_normal_1.5__NONE','V9_D2_EXTREME_1P0_NONE':'D2_extreme_1.0__NONE','V9_D3_ROLLING14':'D3__ROLLING14','V13_EXPANDING_S4':'EXPANDING_S4','V9_D2_NORMAL_1P0_NONE':'D2_normal_1.0__NONE'}
PRIMARY=list(ARMS)[:5]
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(p):return dict(path=str(Path(p).resolve()),bytes=Path(p).stat().st_size,sha256=sha(p))
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.ndarray):return clean(v.tolist())
    if hasattr(v,'item'):return clean(v.item())
    if isinstance(v,float) and not np.isfinite(v):return None
    return v
def write(n,v):
    p=ROOT/n;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(v),indent=2,ensure_ascii=False,allow_nan=False,default=str)+'\n',encoding='utf-8')
def csv(n,rows):pd.DataFrame(rows).to_csv(ROOT/n,index=False)
def ids(f):return hashlib.sha256(('\n'.join(sorted(f.job_id.astype(str)))+'\n').encode()).hexdigest()
def metrics(f):
    y=f.runtime_seconds.to_numpy();a=float(y.sum())
    r=dict(N=len(f),zero_runtime_N=int((y==0).sum()),actual_seconds=a,Q50_MAE_seconds=float(abs(y-f.q50).mean()),Q50_MAE_hours=float(abs(y-f.q50).mean()/3600),Q90_coverage=float((y<=f.q90).mean()),TIME_RATIO_Q50=float(f.q50.sum()/a),TIME_RATIO_Q90=float(f.q90.sum()/a))
    for h in [4,12,24]:
        z=f[y>h*3600];r[f'GT{h}H_N']=len(z);r[f'GT{h}H_Q90_coverage']=float((z.runtime_seconds<=z.q90).mean()) if len(z) else None
    return r

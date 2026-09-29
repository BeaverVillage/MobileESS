from pathlib import Path
import datetime,hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
LOCAL=ROOT/'.local'
PR94=REPO/'docs/runtime_final_duration_calibration'
BASE='efc04829a4bfadfcf5a03998592c93ba86554701'
ARMS=['V9_D1_ROLLING14','V9_D2_NORMAL_1P5_NONE','V9_D2_EXTREME_1P0_NONE','V9_D3_ROLLING14','V13_EXPANDING_S4','V9_D2_NORMAL_1P0_NONE']
PRIMARY='V9_D2_EXTREME_1P0_NONE'
BUCKETS=[('GT0_LE15MIN',0,900),('GT15MIN_LE1H',900,3600),('GT1H_LE4H',3600,14400),('GT4H_LE12H',14400,43200),('GT12H_LE24H',43200,86400),('GT24H',86400,np.inf)]
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
    y=f.runtime_seconds.to_numpy();q=f.q50.to_numpy();n=len(y);total=float(y.sum())
    coverage=float(np.count_nonzero(y<=q)/n) if n else None
    return dict(N=n,zero_runtime_N=int((y==0).sum()),actual_seconds=total,predicted_Q50_seconds=float(q.sum()),
        Q50_MAE_seconds=float(abs(y-q).mean()) if n else None,Q50_MAE_hours=float(abs(y-q).mean()/3600) if n else None,
        Q50_coverage=coverage,Q50_calibration_error=abs(coverage-.5) if n else None,
        Q50_underprediction_fraction=float(np.count_nonzero(y>q)/n) if n else None,Q50_over_or_equal_fraction=coverage,
        Q50_time_ratio=float(q.sum()/total) if total>0 else None,
        Raw_Q90_coverage=float((y<=f.q90.to_numpy()).mean()) if n else None)
def ratios(f):
    z=f[f.runtime_seconds>0];r=z.q50.to_numpy()/z.runtime_seconds.to_numpy()
    return dict(N_positive=len(r),zero_runtime_excluded_N=int(f.runtime_seconds.eq(0).sum()),
        **{name:float(np.quantile(r,q)) if len(r) else None for name,q in [('Q10',.1),('Q25',.25),('median',.5),('Q75',.75),('Q90',.9),('Q95',.95)]},mean_diagnostic_only=float(r.mean()) if len(r) else None)

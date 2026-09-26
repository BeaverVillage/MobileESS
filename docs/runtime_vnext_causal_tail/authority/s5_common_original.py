from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime'
S4 = ROOT / 'dayahead/artifacts/v40s4_request_state_proxy_runtime_risk'
S3 = ROOT / 'dayahead/artifacts/v40s3_body_tail_runtime_risk'
S4ROOT = Path('C:/codex_mobileess_workspace/MobileESS_v40s4_request_state_proxy_runtime_risk')
BASE = 'ea9e5133657d417ce66c8436cac7e05f8634926b'
SCI4 = '7d83ea7385b8b4596efe7791a7aad6a60926dcb7'
SCI3 = '836dfa1008c6810d077582892745b1892210c029'
REC3 = 'bfeb9c3312b397fdd15a00dfc9eac37dd4b2b6aa'
SOURCE = Path('C:/codex_mobileess_workspace/MobileESS_v40s2_survival_occupancy_ml/dayahead/artifacts/v40q_regime_conditioned_tail/clean_execution_01/PREPARED_ROWS.parquet')
SOURCE_SHA = 'fed0270c4e90362bc97b3583d92bfc6e00d6083297ee502b098e08896e086df9'
PANEL_SHA = 'fbd99e403891139150441c7374640ae5607a8671e9c511cc52f92f3959e795b7'
CUTOFF = pd.Timestamp('2025-03-14T08:00:00Z')
ASSUMPTION = 'D1_SCHEDULER_REQUEST_STATE_PROXY_V1'
NUM = ['requested_seconds', 'num_gpus_req', 'num_nodes_req', 'num_cores_req', 'requested_memory_mib']
CAT = ['partition', 'qos']
CLOCK = ['submit_hour', 'submit_dow']
FEATURES = NUM + CAT + CLOCK
QUANTILES = [0.50, 0.90, 0.95, 0.99]
SEED = 4005
CONFIGS = {
    'L0': dict(num_leaves=15, learning_rate=.03, n_estimators=400, min_child_samples=50),
    'L1': dict(num_leaves=31, learning_rate=.03, n_estimators=600, min_child_samples=50),
    'L2': dict(num_leaves=31, learning_rate=.02, n_estimators=800, min_child_samples=100),
}
FIXED = dict(n_jobs=1, random_state=SEED, deterministic=True, force_col_wise=True,
             verbosity=-1, subsample=1., subsample_freq=0, colsample_bytree=1.,
             reg_alpha=0., reg_lambda=1., device_type='cpu', max_depth=-1,
             max_bin=255, min_child_weight=.001, min_split_gain=0.,
             data_random_seed=SEED, feature_fraction_seed=SEED, bagging_seed=SEED)
CANDIDATES = ['R0_CURRENT_RSP', 'R1_RECORDED_REQUESTED_WALLTIME', 'R2_Q90', 'R3_Q95', 'R4_Q99', 'R5_UARP_STYLE']
ROLES = ['TRAIN', 'DEVELOPMENT', 'CALIBRATION', 'EXPOSED_EVALUATION']
EXPECTED = dict(zip(ROLES, [1190, 4346, 2634, 2713]))
HOLDS = dict(production_q_seconds=5576.44921875, PF=.95, Q_control='NO', electrical='HOLD',
             electrical_B0_B3='NO', FULL_MAY='NO', optimizer_integration='NO')

def now(): return datetime.now(timezone.utc).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def file_sha(p): return sha(Path(p).read_bytes())
def git(*args, cwd=ROOT, binary=False):
    b = subprocess.check_output(['git', *args], cwd=cwd)
    return b if binary else b.decode('utf-8').rstrip('\r\n')
def ancestor(a,b):
    return subprocess.run(['git','merge-base','--is-ancestor',a,b], cwd=ROOT).returncode == 0
def read(name): return json.loads((OUT / f'V40S5_{name}.json').read_text(encoding='utf-8'))
def write(name, value):
    (OUT / f'V40S5_{name}.json').write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False,
        default=lambda v: v.item() if hasattr(v, 'item') else str(v)) + '\n', encoding='utf-8')
def ids(values): return sha(('\n'.join(sorted(map(str,values)))+'\n').encode())
def allowed(p):
    return p.startswith(('dayahead/v40s5/', 'dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime/')) or (p.startswith('tests/dayahead/test_v40s5_') and p.endswith('.py'))
def tree(commit): return {r.split('\t')[1]:r.split('\t')[0] for r in git('ls-tree','-r',commit).splitlines()}
def fields(track): return [c for c in FEATURES if track == 'P' or c != 'requested_seconds']
def numeric(s,c):
    v = pd.to_numeric(s, errors='coerce').astype(float)
    valid = np.isfinite(v) & (v >= 0 if c == 'requested_memory_mib' else v > 0)
    if c in NUM[1:4]: valid &= v == np.floor(v)
    return v.where(valid)
def categories(s):
    return s.map(lambda v: '__UNKNOWN__' if pd.isna(v) or str(v).strip().lower() in ('','nan','none','unknown') else str(v).strip())

class Preprocess:
    """No targets; each fitted map is restricted to its historical fit subset."""
    def __init__(self, track='P'): self.track = track
    def fit(self, f):
        assert f.end_time.lt(CUTOFF).all() and not f.job_uid.duplicated().any()
        self.columns = fields(self.track); self.medians = {}; self.vocab = {}; self.groups = []
        for c in self.columns:
            if c in NUM:
                v = numeric(f[c], c)
                if not v.notna().any(): raise ValueError('No historical numeric authority: '+c)
                self.medians[c] = float(v.median()); self.groups += [c,c]
        for c in CAT:
            self.vocab[c] = ['__UNKNOWN__'] + sorted(set(categories(f[c])) - {'__UNKNOWN__'})
            self.groups += [c] * len(self.vocab[c])
        self.groups += CLOCK
        self.fit_ids_sha256 = ids(f.job_uid); self.fit_N = len(f)
        self.max_fit_end = f.end_time.max().isoformat()
        return self
    def transform(self,f):
        a=[]
        for c,m in self.medians.items():
            v=numeric(f[c],c); a += [np.log1p(v.fillna(m).to_numpy()),v.isna().to_numpy(float)]
        for c,vocab in self.vocab.items():
            s=categories(f[c]); s=s.where(s.isin(vocab),'__UNKNOWN__')
            a += [s.eq(v).to_numpy(float) for v in vocab]
        a += [f[c].to_numpy(float) for c in CLOCK]
        x=np.column_stack(a); assert np.isfinite(x).all()
        return x
    def descriptor(self): return vars(self)

def temporal_split(f, fraction=.8):
    d=f.sort_values(['end_time','job_uid'],kind='mergesort').reset_index(drop=True)
    boundary=d.iloc[int(np.floor(len(d)*fraction))].end_time
    return d[d.end_time < boundary].copy(),d[d.end_time >= boundary].copy(),boundary

def temporal_folds(f):
    d=f.sort_values(['end_time','job_uid'],kind='mergesort').reset_index(drop=True)
    times=sorted(d.end_time.unique())
    # Six approximately equal row-count blocks, never splitting equal timestamps.
    bounds=[d.iloc[int(len(d)*k/6)].end_time for k in range(1,6)]
    assert len(set(bounds)) == 5
    for k,lo in enumerate(bounds):
        hi=bounds[k+1] if k<4 else CUTOFF
        yield k+1,d[d.end_time < lo].copy(),d[(d.end_time >= lo)&(d.end_time < hi)].copy()

def repair(raw):
    raw=np.asarray(raw,float); assert np.isfinite(raw).all()
    nonnegative=np.maximum(raw,0.)
    corrected=np.maximum.accumulate(nonnegative,axis=1)
    return corrected
def uarp(q99,sigma): return np.asarray(q99)+np.maximum(.2*np.asarray(q99),.5*np.asarray(sigma))
def candidates(f,q,sigma):
    return dict(zip(CANDIDATES,[f.reference_safe_sec.to_numpy(float),f.requested_seconds.to_numpy(float),q[:,1],q[:,2],q[:,3],uarp(q[:,3],sigma)]))
def pinball(y,p,a):
    e=np.asarray(y)-np.asarray(p); return float(np.mean(np.maximum(a*e,(a-1)*e)))
def distribution(values):
    v=np.asarray(values,float); v=v[np.isfinite(v)]
    if not len(v): return dict(N=0)
    return dict(N=len(v),min=float(v.min()),mean=float(v.mean()),median=float(np.median(v)),
                P90=float(np.quantile(v,.9)),P95=float(np.quantile(v,.95)),P99=float(np.quantile(v,.99)),max=float(v.max()))
def metrics(f,p):
    y=f.runtime_seconds.to_numpy(float);g=f.num_gpus_req.to_numpy(float);p=np.asarray(p,float)
    assert len(y) and np.isfinite(p).all() and (p>=0).all() and (g>0).all()
    under=np.maximum(y-p,0);over=np.maximum(p-y,0);a=np.abs(p-y);covered=y<=p
    slots=np.ceil(p/900)-np.ceil(y/900)
    m=dict(N=len(y),coverage=float(covered.mean()),GPU_coverage=float(np.average(covered,weights=g)),
      under_sec=float(under.sum()),GPU_under_sec=float(g@under),over_sec=float(over.sum()),GPU_over_h=float(g@over/3600),
      MAE=float(a.mean()),median_absolute_error=float(np.median(a)),P90_absolute_error=float(np.quantile(a,.9)),
      P95_absolute_error=float(np.quantile(a,.95)),P99_absolute_error=float(np.quantile(a,.99)),WAPE=float(a.sum()/y.sum()),
      bias=float((p-y).mean()),safe_actual_ratio=float(p.sum()/y.sum()),safe_actual_ratio_distribution=distribution(p/y),
      completion_slot_MAE=float(np.abs(slots).mean()),completion_slot_signed_error=float(slots.mean()),
      GPU_completion_slot_MAE=float(np.average(np.abs(slots),weights=g)),GPU_completion_slot_signed_error=float(np.average(slots,weights=g)),
      EXTREME_CONSERVATISM_WARNING=bool(covered.mean()>.995))
    for k in (1,4,8):
        m[f'ending_at_least_{k}_slots_early']=float((slots<=-k).mean())
        m[f'GPU_ending_at_least_{k}_slots_early']=float(np.average(slots<=-k,weights=g))
    return m
def daily_metrics(f,p):
    d=f.assign(_prediction=np.asarray(p)); out={}
    for day,part in d.groupby('issue_day'):
        v=metrics(part,part._prediction);v['major_day']=len(part)>=100
        v['daily_gate_pass']=bool(v['coverage']>=.88 and v['GPU_coverage']>=.88) if len(part)>=100 else None
        out[str(day)]=v
    return out
def gates(m,daily,rsp,request):
    checks=dict(coverage=m['coverage']>=.9,GPU_coverage=m['GPU_coverage']>=.9,
      major_days=all(v['daily_gate_pass'] for v in daily.values() if v['major_day']),
      GPU_under_below_RSP=m['GPU_under_sec']<rsp['GPU_under_sec'])
    safety=all(checks.values());efficiency=m['GPU_over_h']<request['GPU_over_h']
    return dict(checks=checks,safety=bool(safety),efficiency=bool(efficiency),eligible=bool(safety and efficiency))
def choose(results,gate_map,pinballs):
    eligible=[c for c in CANDIDATES[2:] if all(gate_map[r][c]['eligible'] for r in ROLES[1:3])]
    def key(c):
        cal=results['CALIBRATION'][c]; dev=results['DEVELOPMENT'][c]
        return (cal['GPU_over_h'],cal['GPU_under_sec'],cal['GPU_over_h']+dev['GPU_over_h'],pinballs[c],CANDIDATES.index(c))
    return min(eligible,key=key) if eligible else None
def guard_receipt(name):
    r=read(name); assert ancestor(r['commit'],git('rev-parse','HEAD'))
    for p,h in r['frozen_SHA256'].items():
        assert file_sha(ROOT/p)==h,p
        assert sha(git('show',f"{r['commit']}:{p}",binary=True))==h,p
    return r['commit']
def library():
    p=OUT/'V40S5_HISTORICAL_TRAINING_LIBRARY.parquet'
    assert file_sha(p)==read('HISTORICAL_TRAINING_LIBRARY_AUDIT')['library_SHA256']
    f=pd.read_parquet(p); assert f.end_time.lt(CUTOFF).all()
    return f
def panel(role):
    assert role in ROLES
    if role=='EXPOSED_EVALUATION': guard_receipt('PREEXPOSED_COMMIT_RECEIPT')
    p=S4/'V40S4_PENDING_ISSUE_PANEL.parquet';assert file_sha(p)==PANEL_SHA
    f=pd.read_parquet(p,filters=[('role','==',role)])
    assert len(f)==EXPECTED[role]
    f['job_uid']=f.job_id.astype(str)
    return f

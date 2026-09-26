"""Offline runtime study: no optimizer, grid, Actual or production imports."""
import os
if os.environ.get('RUNTIME_BASELINE_NATIVE_THREADS')!='1':
 for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import sys,json,hashlib,gzip,re,subprocess,time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
RAW=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
HPC=RAW.parents[1]/'NLR_scheduler_authority/07_hpc-oda-commons'
LEGACY=Path('D:/ChatGPT/Mobile ESS 2/MobileESS_v35r3d_kestrel_runtime_authority_closure/dayahead/cache/v35r3d_kestrel_runtime_authority_closure')
MODERN=Path('C:/codex_mobileess_workspace/MobileESS_v41r1_premay_voltage_security_margin/frozen_artifacts/v41r1_terminal/inputs')
SNAP=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v37_r4a_per_day_aidc/days')
sys.path[:0]=[str(HPC/'src'),str(REPO/'.runtime_deps'),'C:/codex_mobileess_workspace/v40s_runtime_dependencies/lightgbm_4_6_0']
NUM=['requested_seconds','num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib']
CAT=['partition','qos'];CLOCK=['submit_hour','submit_dow'];FEATURES=NUM+CAT+CLOCK
MOE_FEATURES=['requested_seconds','num_nodes_req','num_cores_req','num_gpus_req','requested_memory_mib','partition','qos','user','account']
TAUS=[.5,.9,.95,.99]
Q_OLD=5576.44921875
FIXED=dict(n_jobs=1,random_state=4005,deterministic=True,force_col_wise=True,verbosity=-1,subsample=1.,subsample_freq=0,
 colsample_bytree=1.,reg_alpha=0.,reg_lambda=1.,device_type='cpu',max_depth=-1,max_bin=255,min_child_weight=.001,min_split_gain=0.,
 data_random_seed=4005,feature_fraction_seed=4005,bagging_seed=4005,num_leaves=31,learning_rate=.02,n_estimators=800,min_child_samples=100)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ids(x):return hashlib.sha256(('\n'.join(sorted(map(str,x)))+'\n').encode()).hexdigest()
def now():return pd.Timestamp.now(tz='UTC').isoformat()
def require(c,m):
 if not c:raise AssertionError(m)
def dump(p,obj,exclusive=False):
 p=ROOT/p;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x' if exclusive else 'w',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,default=lambda v:v.item() if hasattr(v,'item') else str(v),allow_nan=False)
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def numeric(s,c):
 v=pd.to_numeric(s,errors='coerce').astype(float);valid=np.isfinite(v)&(v>=0 if c=='requested_memory_mib' else v>0)
 if c in NUM[1:4]:valid &=v==np.floor(v)
 return v.where(valid)
def categories(s):return s.map(lambda v:'__UNKNOWN__' if pd.isna(v) or str(v).strip().lower() in ('','nan','none','unknown') else str(v).strip())
class Preprocess:
 def __init__(self,cutoff,running=False):self.cutoff=pd.Timestamp(cutoff);self.running=running
 def fit(self,f):
  require(f.end_time.lt(self.cutoff).all(),'PREPROCESS_FUTURE_LABEL')
  self.medians={c:float(numeric(f[c],c).median()) for c in NUM}
  self.vocab={c:['__UNKNOWN__']+sorted(set(categories(f[c]))-{'__UNKNOWN__'}) for c in CAT}
  self.fit_ids_sha256=ids(f.job_id);return self
 def transform(self,f):
  a=[]
  for c in NUM:
   m=self.medians[c]
   v=numeric(f[c],c);a += [np.log1p(v.fillna(m).to_numpy()),v.isna().to_numpy(float)]
  for c in CAT:
   vocab=self.vocab[c]
   s=categories(f[c]);s=s.where(s.isin(vocab),'__UNKNOWN__');a += [s.eq(v).to_numpy(float) for v in vocab]
  a += [f[c].to_numpy(float) for c in CLOCK]
  if self.running:a += [np.log1p(f.elapsed_seconds.to_numpy(float))]
  x=np.column_stack(a);require(np.isfinite(x).all(),'NONFINITE_FEATURE');return x
 def descriptor(self):return {**vars(self),'cutoff':self.cutoff.isoformat()}
def memory(v):
 if v is None:return None
 m=re.match(r'^([\d.]+)([KMGTPkmgtp]?)[nN]?$',str(v).strip())
 return float(m[1])*{'K':1/1024,'M':1,'G':1024,'T':1024**2,'P':1024**3,'':1}[m[2].upper()] if m else None
def normalize(r):
 f=pd.DataFrame(index=r.index);f['job_id']=r.id.astype(str);f['job_uid']=f.job_id;f['submit_time']=pd.to_datetime(r.submit_time,utc=True)
 f['requested_seconds']=r.wallclock_req.dt.total_seconds().astype(float)
 for s,t in [('gpus_requested','num_gpus_req'),('nodes_req','num_nodes_req'),('processors_req','num_cores_req')]:f[t]=pd.to_numeric(r[s],errors='coerce')
 f['requested_memory_mib']=r.memory_req.map(memory)
 for c in ['partition','qos']:f[c]=r[c]
 f['submit_hour']=f.submit_time.dt.hour.astype(float);f['submit_dow']=f.submit_time.dt.dayofweek.astype(float)
 return f
def exact_moe(rate=.05,lookback=120):
 from hpc_oda_commons.models.job_runtime_moe_xgboost.model import MoEXGBoostConfig,MoEXGBoostModel
 return MoEXGBoostModel(MoEXGBoostConfig(n_windows=120,test_window_hours=6,training_lookback_days=lookback,
    enable_power_users=False,time_decay_rate=rate,objective='reg:absoluteerror'))

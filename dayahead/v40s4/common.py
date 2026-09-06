from pathlib import Path
import hashlib
import json
import subprocess
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dayahead/artifacts/v40s4_request_state_proxy_runtime_risk'
S3OUT=ROOT/'dayahead/artifacts/v40s3_body_tail_runtime_risk'
S3ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v40s3_body_tail_runtime_risk')
BASE='bfeb9c3312b397fdd15a00dfc9eac37dd4b2b6aa'
S3SCIENCE='836dfa1008c6810d077582892745b1892210c029'
SOURCE=Path('C:/codex_mobileess_workspace/MobileESS_v40s2_survival_occupancy_ml/dayahead/artifacts/v40q_regime_conditioned_tail/clean_execution_01/PREPARED_ROWS.parquet')
SOURCE_SHA='fed0270c4e90362bc97b3583d92bfc6e00d6083297ee502b098e08896e086df9'
ASSUMPTION='D1_SCHEDULER_REQUEST_STATE_PROXY_V1'
U=(4,6,8,12,24)
SEED=4003
NUM=['requested_seconds','num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib']
CAT=['partition','qos']
CLOCK=['submit_hour','submit_dow']
FEATURES=NUM+CAT+CLOCK
BOUNDS={'TRAIN':('2025-03-14T08:00Z','2025-03-22T08:00Z'),
 'DEVELOPMENT':('2025-03-22T08:00Z','2025-04-01T08:00Z'),
 'CALIBRATION':('2025-04-01T08:00Z','2025-04-08T08:00Z'),
 'EXPOSED_EVALUATION':('2025-04-08T08:00Z','2025-04-24T00:00Z')}
LGB=dict(n_estimators=100,num_leaves=7,max_depth=3,learning_rate=.05,min_child_samples=50,n_jobs=1,random_state=SEED,deterministic=True,force_col_wise=True,verbosity=-1)
XGB=dict(n_estimators=100,max_depth=3,learning_rate=.05,min_child_weight=20,n_jobs=1,random_state=SEED,tree_method='hist',device='cpu',subsample=1.,colsample_bytree=1.)
HOLDS=dict(production_q_seconds=5576.44921875,PF=.95,Q_control='NO',electrical='HOLD',B0_B1_B2_B3_electrical='NO',FULL_MAY='NO',optimizer_integration='NO',RUNNING_migration_change='NO',A1_migration_change='NO',terminal_contract_change='NO')


def now():return datetime.now(timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args,binary=False,cwd=ROOT):
    b=subprocess.check_output(['git',*args],cwd=cwd)
    return b if binary else b.decode('utf-8').rstrip('\r\n')
def get(name,s3=False):return json.loads(((S3OUT if s3 else OUT)/f"{'V40S3' if s3 else 'V40S4'}_{name}.json").read_text(encoding='utf-8'))
def write(name,x):
    (OUT/f'V40S4_{name}.json').write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False,default=lambda v:v.item() if hasattr(v,'item') else str(v))+'\n',encoding='utf-8')
def ids(f):return sha(('\n'.join(sorted(f.job_issue_uid))+'\n').encode())
def allowed(p):return p.startswith(('dayahead/v40s4/','dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/')) or (p.startswith('tests/dayahead/test_v40s4_') and p.endswith('.py'))
def selected_features(track):return [c for c in FEATURES if track=='P' or c!='requested_seconds']
def clean_category(s):
    return s.map(lambda v:'__UNKNOWN__' if pd.isna(v) or str(v).strip().lower() in ('','nan','none','unknown') else str(v).strip())
def numeric_valid(s,c):
    a=pd.to_numeric(s,errors='coerce').astype(float)
    valid=np.isfinite(a)&(a>=0 if c=='requested_memory_mib' else a>0)
    if c in ('num_gpus_req','num_nodes_req','num_cores_req'):valid &= a==np.floor(a)
    return a.where(valid)


class Preprocess:
    """Unsupervised TRAIN-only map; P-W removes only walltime and its indicator."""
    def __init__(self,track):self.track=track
    def fit(self,f):
        if set(f.role)!= {'TRAIN'}:raise ValueError('PREPROCESS_TRAIN_ONLY')
        self.fields=selected_features(self.track);self.medians={};self.vocab={};self.groups=[]
        for c in [v for v in self.fields if v in NUM]:
            v=numeric_valid(f[c],c)
            if not v.notna().any():raise ValueError('NO_TRAIN_NUMERIC_AUTHORITY:'+c)
            self.medians[c]=float(v.median());self.groups.extend([c,c])
        for c in CAT:
            self.vocab[c]=['__UNKNOWN__']+sorted(set(clean_category(f[c]))-{'__UNKNOWN__'})
            self.groups.extend([c]*len(self.vocab[c]))
        self.groups.extend(CLOCK);self.train_ids=ids(f)
        return self
    def transform(self,f):
        cols=[]
        for c,median in self.medians.items():
            a=numeric_valid(f[c],c);cols.extend([np.log1p(a.fillna(median).to_numpy()),a.isna().to_numpy(float)])
        for c,vocab in self.vocab.items():
            s=clean_category(f[c]);s=s.where(s.isin(vocab),'__UNKNOWN__')
            cols.extend([s.eq(v).to_numpy(float) for v in vocab])
        cols.extend([f[c].to_numpy(float) for c in CLOCK])
        x=np.column_stack(cols)
        if not np.isfinite(x).all():raise ValueError('NONFINITE_PREDICTOR')
        return x
    def descriptor(self):return dict(track=self.track,source_fields=self.fields,medians=self.medians,vocab=self.vocab,encoded_feature_groups=self.groups,train_ID_SHA256=self.train_ids)


def panel():
    p=OUT/'V40S4_PENDING_ISSUE_PANEL.parquet'
    assert sha(p.read_bytes())==get('POPULATION_AUDIT')['panel_SHA256']
    return pd.read_parquet(p)


def guard_prereg():
    c=get('PREREGISTRATION_COMMIT_RECEIPT')['commit']
    path='dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_PREREGISTRATION.json'
    assert git('show',f'{c}:{path}',binary=True)==(ROOT/path).read_bytes()
    for p,h in get('PREREGISTRATION_COMMIT_RECEIPT')['frozen_source_SHA256'].items():assert sha((ROOT/p).read_bytes())==h,p
    return c

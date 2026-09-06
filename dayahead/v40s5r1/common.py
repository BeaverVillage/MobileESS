from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import numpy as np
import pandas as pd
from dayahead.v40s5.common import (FEATURES,NUM,CAT,CLOCK,QUANTILES,FIXED,CONFIGS,SEED,
    CANDIDATES,ROLES,EXPECTED,HOLDS,ASSUMPTION,SOURCE,SOURCE_SHA,PANEL_SHA,
    numeric,categories,fields,repair,uarp,candidates,pinball,distribution,metrics,daily_metrics,gates)

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dayahead/artifacts/v40s5r1_rolling_origin_runtime'
S5=ROOT/'dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime'
S4=ROOT/'dayahead/artifacts/v40s4_request_state_proxy_runtime_risk'
S5ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v40s5_uncertainty_aware_direct_runtime')
BASE='fb541bb421a7313d6debf2c7f9c00c8a5c037a89'
S5SCIENCE='788832de4d622bf4ab95189cc8943769bd3b3eae'
PANEL=S4/'V40S4_PENDING_ISSUE_PANEL.parquet'
PREFIX='V40S5R1_'
LABELS=['start_time','end_time','runtime_seconds']
FEATURE_COLUMNS=['job_id','job_issue_uid','issue_time','issue_day','role','reference_safe_sec',*FEATURES]

def now():return datetime.now(timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def file_sha(p):return sha(Path(p).read_bytes())
def ids(v):return sha(('\n'.join(sorted(map(str,v)))+'\n').encode())
def ordered_ids(v):return sha(('\n'.join(map(str,v))+'\n').encode())
def git(*args,cwd=ROOT,binary=False):
    b=subprocess.check_output(['git',*args],cwd=cwd)
    return b if binary else b.decode('utf-8').rstrip('\r\n')
def ancestor(a,b):return subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=ROOT).returncode==0
def tree(c):return {r.split('\t')[1]:r.split('\t')[0] for r in git('ls-tree','-r',c).splitlines()}
def allowed(p):return p.startswith(('dayahead/v40s5r1/','dayahead/artifacts/v40s5r1_rolling_origin_runtime/')) or (p.startswith('tests/dayahead/test_v40s5r1_') and p.endswith('.py'))
def read(name):return json.loads((OUT/f'{PREFIX}{name}.json').read_text(encoding='utf-8'))
def s5(name):return json.loads((S5/f'V40S5_{name}.json').read_text(encoding='utf-8'))
def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x))+'\n',encoding='utf-8')
    temp.replace(path)
def write(name,obj):dump(OUT/f'{PREFIX}{name}.json',obj)
def key(t):return pd.Timestamp(t).strftime('%Y%m%dT%H%M%SZ')
def model_config():
    frozen=s5('HYPERPARAMETER_FREEZE')['selected'];pr=s5('PREREGISTRATION')
    assert CONFIGS[frozen]==pr['configs'][frozen] and FIXED==pr['fixed_parameters']
    return frozen,pr['configs'][frozen]
def guard(name):
    r=read(name);assert ancestor(r['commit'],git('rev-parse','HEAD'))
    for p,h in r['frozen_SHA256'].items():
        assert file_sha(ROOT/p)==h,p
        assert sha(git('show',f"{r['commit']}:{p}",binary=True))==h,p
    return r['commit']

class Preprocess:
    """Exact S5 transform, with the historical cutoff replaced by this origin."""
    def __init__(self,track,cutoff):self.track=track;self.cutoff=pd.Timestamp(cutoff)
    def fit(self,f):
        assert f.end_time.lt(self.cutoff).all() and not f.job_uid.duplicated().any()
        self.columns=fields(self.track);self.medians={};self.vocab={};self.groups=[]
        for c in self.columns:
            if c in NUM:
                v=numeric(f[c],c)
                if not v.notna().any():raise ValueError('No historical numeric authority: '+c)
                self.medians[c]=float(v.median());self.groups += [c,c]
        for c in CAT:
            self.vocab[c]=['__UNKNOWN__']+sorted(set(categories(f[c]))-{'__UNKNOWN__'})
            self.groups += [c]*len(self.vocab[c])
        self.groups += CLOCK;self.fit_ids_sha256=ids(f.job_uid);self.fit_N=len(f)
        self.max_fit_end=f.end_time.max().isoformat()
        return self
    def transform(self,f):
        a=[]
        for c,m in self.medians.items():
            v=numeric(f[c],c);a += [np.log1p(v.fillna(m).to_numpy()),v.isna().to_numpy(float)]
        for c,vocab in self.vocab.items():
            s=categories(f[c]);s=s.where(s.isin(vocab),'__UNKNOWN__')
            a += [s.eq(v).to_numpy(float) for v in vocab]
        a += [f[c].to_numpy(float) for c in CLOCK]
        x=np.column_stack(a);assert np.isfinite(x).all()
        return x
    def descriptor(self):return {**vars(self),'cutoff':self.cutoff.isoformat()}

def fold_count(n):return 5 if n>=250 else 3 if n>=100 else 0
def folds(f,cutoff):
    n=fold_count(len(f))
    if n==0:raise ValueError('INSUFFICIENT_SUPPORT_N_LT_100')
    d=f.sort_values(['end_time','job_uid'],kind='mergesort').reset_index(drop=True)
    bounds=[d.iloc[int(len(d)*k/(n+1))].end_time for k in range(1,n+1)]
    if len(set(bounds))!=n:raise ValueError('INSUFFICIENT_DISTINCT_TIMESTAMP_SUPPORT')
    for k,lo in enumerate(bounds):
        hi=bounds[k+1] if k<n-1 else pd.Timestamp(cutoff)
        a=d[d.end_time<lo].copy();b=d[(d.end_time>=lo)&(d.end_time<hi)].copy()
        assert len(a)>0 and len(b)>0 and a.end_time.max()<b.end_time.min()
        yield k+1,a,b

def choose(results,gate_map):
    eligible=[c for c in CANDIDATES[2:] if all(gate_map[r][c]['eligible'] for r in ['DEVELOPMENT','CALIBRATION'])]
    def rank(c):
        cal=results['CALIBRATION'][c];dev=results['DEVELOPMENT'][c]
        return cal['GPU_over_h'],cal['GPU_under_sec'],cal['GPU_over_h']+dev['GPU_over_h'],CANDIDATES.index(c)
    return min(eligible,key=rank) if eligible else None

def improvement(dc,dg,du):
    if dc>=.10 or dg>=.10:return 'ROLLING_UPDATE_MATERIALLY_IMPROVES_RUNTIME'
    if dc<0 and dg<0 and du>0:return 'ROLLING_UPDATE_DEGRADES_RUNTIME'
    if dc<=0 and dg<=0:return 'ROLLING_UPDATE_NO_GENERALIZATION_RECOVERY'
    return 'ROLLING_UPDATE_SMALL_EFFECT'

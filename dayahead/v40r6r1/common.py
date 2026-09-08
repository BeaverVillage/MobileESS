from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import os
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dayahead/artifacts/v40r6r1_risk_calibrated_rolling_gpuwork'
R6=ROOT/'dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork'
R5=ROOT/'dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'
BASE='2d6e22e2b448454bb4a860a07f38c20ad3ef834d'
SCIENCE='ea9b86e9f32808f255c14e498b895a6410d65fe3'
SELECTION='11ff08052da5231e2dc66eac5e28f064dfed83d2'
R51SCI='86f3bf3a588d0c31e109a14e97ec2efd122d4508'
R51REC='528716aa36b02bbe0ebff3cf9639984c6b2c535e'
HORIZONS={'H4':16,'H24':96}
CANDIDATES={'R85_B1':'B1','R85_B2':'B2_L0'}
SEED=20260907
HOLDS={'production_q_seconds':5576.44921875,'PF':.95,'Q_control':'NO','electrical':'HOLD',
       'electrical_B0_B3':'NO','FULL_MAY':'NO','optimizer_integration':'NO','production_ready':'NO'}
os.environ['GIT_OPTIONAL_LOCKS']='0'

def git(*args,cwd=ROOT): return subprocess.check_output(['git',*args],cwd=cwd).decode('utf-8').strip()
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def external(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def read(name): return external(OUT/('V40R6R1_'+name+'.json'))
def r6(name): return external(R6/('V40R6_'+name+'.json'))
def clean(x):
    if x is pd.NaT or x is pd.NA: return None
    if isinstance(x,dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)): return [clean(v) for v in x]
    if isinstance(x,(np.integer,np.bool_)): return x.item()
    if isinstance(x,(float,np.floating)): return float(x) if np.isfinite(x) else None
    if isinstance(x,(Path,pd.Timestamp,datetime)): return str(x)
    return x
def dump(name,x):
    p=OUT/('V40R6R1_'+name+'.json'); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(x),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def csv(name,x): pd.DataFrame(x).to_csv(OUT/('V40R6R1_'+name+'.csv'),index=False,lineterminator='\n')
def allowed(p): return p.startswith(('dayahead/v40r6r1/','dayahead/artifacts/v40r6r1_risk_calibrated_rolling_gpuwork/')) or (p.startswith('tests/dayahead/test_v40r6r1_') and p.endswith('.py'))
def snapshot():
    directories=['dayahead/v40r5','dayahead/v40r5r1','dayahead/v40r6',
        'dayahead/artifacts/v40r5_15min_selective_burst_gpuwork','dayahead/artifacts/v40r5r1_zero_inflation_gate_correction',
        'dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork']
    hashes={}
    for d in directories:
        for p in sorted((ROOT/d).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts: hashes[p.relative_to(ROOT).as_posix()]=sha(p)
    changed=git('diff',BASE,'--name-only').splitlines(); bad=[p for p in changed if not allowed(p)]
    assert not bad,bad
    return {'inherited_tree':git('rev-parse',BASE+'^{tree}'),'inherited_SHA256':hashes,'protected_diff':bad,
        'scope':'Full inherited Git diff plus byte hashes of materialized R5/R5R1/R6; no May/shadow scientific row queries'}
def verify_commit_file(commit,path):
    git('merge-base','--is-ancestor',commit,'HEAD')
    content=subprocess.check_output(['git','show',commit+':'+path.relative_to(ROOT).as_posix()],cwd=ROOT)
    assert hashlib.sha256(content).hexdigest()==sha(path),str(path)
def authority():
    commit=read('PREREGISTRATION_COMMIT_RECEIPT')['commit']
    verify_commit_file(commit,OUT/'V40R6R1_PREREGISTRATION.json'); reg=read('PREREGISTRATION')
    for p,h in reg['frozen_hashes'].items(): assert sha(ROOT/p)==h,('FROZEN_AUTHORITY_CHANGED',p)
    return reg,commit
def selection_authority():
    reg,pre=authority(); commit=read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit']
    verify_commit_file(commit,OUT/'V40R6R1_SELECTION_FREEZE.json'); freeze=read('SELECTION_FREEZE')
    for p,h in freeze['frozen_hashes'].items(): assert sha(ROOT/p)==h,('SELECTION_CHANGED',p)
    return reg,freeze,commit

def source_frame(include_exposed=False):
    """Exact frozen saved arrays; no model import, feature engineering or fit."""
    target=pd.read_parquet(R6/'V40R6_CUMULATIVE_TARGET.parquet')
    ledger=pd.read_parquet(R5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet').set_index('operating_day')
    dev=np.load(R6/'development_baselines.npz'); devq=np.load(R6/'fits/L0/development_q.npy')
    phases=[('DEVELOPMENT',{'row_ids':dev['row_ids'],'baseline':dev['predictions'],'q':devq})]
    phases.append(('CALIBRATION',np.load(R6/'calibration_predictions.npz')))
    if include_exposed: phases.append(('EXPOSED_EVALUATION',np.load(R6/'exposed_predictions.npz')))
    rows=[]
    for role,arrays in phases:
        ids=arrays['row_ids']; m=target.iloc[ids].horizon.isin(HORIZONS).to_numpy()
        f=target.iloc[ids[m]].copy(); assert (f.role==role).all() and f.stage_maturity_eligible.all()
        f['base_B1_Q50']=arrays['baseline'][m,1]; f['base_B1_Q90']=arrays['baseline'][m,2]
        f['base_B2_Q50']=arrays['q'][m,0]; f['base_B2_Q90']=arrays['q'][m,1]
        f['static_U2']=arrays['upper'][m] if 'upper' in arrays else np.nan
        f['target_day_end']=pd.to_datetime(f.day.map(ledger.target_end),utc=True)
        f['raw_label_available_at']=pd.to_datetime(f.day.map(ledger.target_label_available_at),utc=True)
        rows.append(f)
    result=pd.concat(rows,ignore_index=True).sort_values(['day','horizon','window_start_slot']).reset_index(drop=True)
    assert result.row_id.is_unique and result.horizon.isin(HORIZONS).all()
    return result

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import os
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork'
R5 = ROOT/'dayahead/artifacts/v40r5_15min_selective_burst_gpuwork'
R51 = ROOT/'dayahead/artifacts/v40r5r1_zero_inflation_gate_correction'
BASE = '528716aa36b02bbe0ebff3cf9639984c6b2c535e'
R5SCI = '488ca53a66e4babc4d3bd2ccca3f97dfb3433a0c'
R5REC = '5b2f6cea014110788147a3c0e2cf0d0a046c18b1'
R4REC = 'ff1fec3a7d8f80b3c2af496758747fafc04bad7b'
HORIZONS = {'H1':4, 'H4':16, 'H8':32, 'H24':96}
PRIMARY = ['H4','H24']
SECONDARY = ['H1','H8']
SEED = 20260907
CONFIGS = {
    'L0': dict(num_leaves=15, learning_rate=.03, n_estimators=400, min_child_samples=50),
    'L1': dict(num_leaves=31, learning_rate=.03, n_estimators=600, min_child_samples=50),
    'L2': dict(num_leaves=31, learning_rate=.02, n_estimators=800, min_child_samples=100)}
HOLDS = {'production_q_seconds':5576.44921875, 'PF':.95, 'Q_control':'NO', 'electrical':'HOLD',
    'electrical_B0_B3':'NO','FULL_MAY':'NO','optimizer_integration':'NO','production_ready':'NO'}
os.environ['GIT_OPTIONAL_LOCKS']='0'

def git(*args,cwd=ROOT):
    return subprocess.check_output(['git',*args],cwd=cwd).decode('utf-8').strip()

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def clean(x):
    if x is pd.NaT or x is pd.NA: return None
    if isinstance(x,dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)): return [clean(v) for v in x]
    if isinstance(x,(np.integer,np.bool_)): return x.item()
    if isinstance(x,(float,np.floating)): return float(x) if np.isfinite(x) else None
    if isinstance(x,(Path,pd.Timestamp,datetime)): return str(x)
    return x

def dump(name,x):
    p=OUT/('V40R6_'+name+'.json'); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(x),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def read(name): return external(OUT/('V40R6_'+name+'.json'))
def external(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def ns(s): return s.dt.as_unit('ns').astype('int64').to_numpy()
def utc(): return datetime.now(timezone.utc).isoformat()
def allowed(p): return p.startswith(('dayahead/v40r6/','dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/')) or (p.startswith('tests/dayahead/test_v40r6_') and p.endswith('.py'))

def snapshot():
    hashes={}
    for d in ['dayahead/v40r5','dayahead/v40r5r1','dayahead/artifacts/v40r5_15min_selective_burst_gpuwork','dayahead/artifacts/v40r5r1_zero_inflation_gate_correction']:
        for p in sorted((ROOT/d).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts: hashes[p.relative_to(ROOT).as_posix()]=sha(p)
    changed=git('diff',BASE,'--name-only').splitlines()
    bad=[p for p in changed if not allowed(p)]
    assert not bad, bad
    return {'inherited_tree':git('rev-parse',BASE+'^{tree}'),'R5_R5R1_SHA256':hashes,'protected_diff':bad,
        'scope':'Entire inherited Git tree; all materialized R5/R5R1 bytes; no scientific May/shadow query'}

def verify_commit_file(commit,p):
    git('merge-base','--is-ancestor',commit,'HEAD')
    blob=subprocess.check_output(['git','show',commit+':'+p.relative_to(ROOT).as_posix()],cwd=ROOT)
    assert hashlib.sha256(blob).hexdigest()==sha(p),str(p)

def authority():
    receipt=read('PREREGISTRATION_COMMIT_RECEIPT'); pre=receipt['commit']
    verify_commit_file(pre,OUT/'V40R6_PREREGISTRATION.json')
    reg=read('PREREGISTRATION')
    for p,h in reg['frozen_hashes'].items(): assert sha(ROOT/p)==h,('PREREGISTERED_FILE_CHANGED',p)
    return reg,pre

def selection_authority():
    reg,pre=authority(); receipt=read('SELECTION_FREEZE_COMMIT_RECEIPT'); commit=receipt['commit']
    verify_commit_file(commit,OUT/'V40R6_SELECTION_FREEZE.json')
    freeze=read('SELECTION_FREEZE')
    for p,h in freeze['frozen_hashes'].items(): assert sha(ROOT/p)==h,('SELECTION_CHANGED',p)
    return reg,freeze,commit

def data():
    frame=pd.read_parquet(OUT/'V40R6_CUMULATIVE_TARGET.parquet')
    arrays=np.load(OUT/'features.npz')
    return frame,arrays

def role_mask(frame,role): return (frame.analysis_role==role).to_numpy() & frame.stage_maturity_eligible.to_numpy()

def csv(name,rows):
    pd.DataFrame(rows).to_csv(OUT/('V40R6_'+name+'.csv'),index=False,lineterminator='\n')

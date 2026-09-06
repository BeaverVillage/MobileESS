from pathlib import Path
from datetime import timezone, timedelta
import hashlib, json, subprocess
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml'
START='37ac7b4ee4f9130fd8c65cfb40184502663a9e5f'
AEST=timezone(timedelta(hours=10))
MAY=pd.Timestamp('2025-05-01',tz='UTC')
STEP=30
K=48
SEED=20260906

def clean(x):
    if x is pd.NaT or x is pd.NA:return None
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,(Path,pd.Timestamp)):return str(x)
    if isinstance(x,np.integer):return int(x)
    if isinstance(x,np.bool_):return bool(x)
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    return x

def dump(name,obj):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(clean(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def read(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd).decode('utf-8').strip()
def blob(path):return subprocess.check_output(['git','show',START+':'+path],cwd=ROOT)
def day_contract(day):
    begin=pd.Timestamp(day,tz=AEST).tz_convert('UTC')
    return begin-pd.Timedelta(hours=6),begin,begin+pd.Timedelta(days=1)
def utc_ns(values):return pd.DatetimeIndex(values).as_unit('ns').asi8

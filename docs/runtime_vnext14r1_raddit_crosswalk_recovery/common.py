from pathlib import Path
import json, hashlib, datetime, subprocess, re
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
LOCAL=ROOT/'.local'
V14=REPO/'docs/runtime_vnext14_multisource_information_recovery'
RAW=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터')
RAD=RAW/'데이터 센터/RADDiT'
BASE='dbe906d6b211fcbb71d8b4c1c17a33ce492452ea'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if hasattr(x,'item'):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x
def write(n,x):
    p=ROOT/n;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n',encoding='utf-8')
def git(*args,cwd=REPO):return subprocess.check_output(['git',*args],cwd=cwd).decode('utf-8',errors='replace').strip()
def record(p):return dict(relative=str(Path(p).relative_to(ROOT)).replace('\\','/'),bytes=Path(p).stat().st_size,sha256=sha(p))

from pathlib import Path
import json,hashlib,datetime,subprocess,re
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1];LOCAL=ROOT/'.local'
R1=REPO/'docs/runtime_vnext14r1_raddit_crosswalk_recovery'
V14=REPO/'docs/runtime_vnext14_multisource_information_recovery'
RAW=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터')
RAD=RAW/'데이터 센터/RADDiT'
BASE='604aaefd8c6a23a68a34544411125c934144cb2e'
def timestamp_us(value):
    # Timestamp.value is nanoseconds even after as_unit('us').
    return int(pd.Timestamp(value).to_datetime64().astype('datetime64[us]').astype('int64'))
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
def md(n,s):(ROOT/n).write_text(s.rstrip()+'\n',encoding='utf-8')
def table(n,rows):
    # Strip display-only line-tail blanks in quoted evidence, not original sources.
    normalized=[{k:'\n'.join(line.rstrip(' \t') for line in v.split('\n')) if isinstance(v,str) else v for k,v in r.items()} for r in rows]
    pd.DataFrame(normalized).to_csv(ROOT/n,index=False)
def git(*args,cwd=REPO):return subprocess.check_output(['git',*args],cwd=cwd).decode('utf-8',errors='replace').strip()
def rec(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
def deliver_rec(p):return dict(relative=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p))

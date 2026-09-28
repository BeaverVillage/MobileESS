from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
WORK=REPO.parent
NATIVE=Path('C:/codex_mobileess_workspace')
OLD=WORK/'runtime_vnext_causal_tail_pr/docs/runtime_vnext_causal_tail'
RAW=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
HPC=RAW.parents[1]/'NLR_scheduler_authority/07_hpc-oda-commons'
V42=WORK/'v42_integrated_pr'
BASE_SHA='f084c4c82cc3873dbe32f350f4da87ececdf88ce'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if hasattr(v,'item'):return clean(v.item())
    if isinstance(v,Path):return str(v)
    return v
def write(name,value):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False,default=str)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(text+'\n')
def record(p):
    p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))

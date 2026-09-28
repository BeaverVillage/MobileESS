from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1];WORK=REPO.parent
RAWROOT=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터')
RAW=RAWROOT/'NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip'
AUTH=RAWROOT/'NLR_scheduler_authority';HPC=AUTH/'07_hpc-oda-commons'
NATIVE=Path('C:/codex_mobileess_workspace');LOCAL=ROOT/'.local'
BASE='ef87a5594a545911d46c4cc2a369358ef1f0339d'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if hasattr(x,'item'):return clean(x.item())
    if isinstance(x,Path):return str(x)
    return x
def write(name,value):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(clean(value),indent=2,ensure_ascii=False,allow_nan=False,default=str)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(data+'\n')
def record(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))

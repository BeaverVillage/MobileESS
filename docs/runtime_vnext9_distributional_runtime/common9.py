from pathlib import Path
import json,hashlib,datetime,sys
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1];WORK=REPO.parent
V8=REPO/'docs/runtime_vnext8_trace_feature_total';V7=REPO/'docs/runtime_vnext7_feature_authority_recovery';V6=REPO/'docs/runtime_vnext6_callable_total'
RAW=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
LOCAL=ROOT/'.local';BASE='159315d30449fd9599897b7dbce1436683cea26b'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if hasattr(x,'item'):return clean(x.item())
    if isinstance(x,Path):return str(x)
    return x
def write(name,x):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(clean(x),f,indent=2,ensure_ascii=False,allow_nan=False,default=str);f.write('\n')
def record(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
def ids(f):return hashlib.sha256(('\n'.join(sorted(f.job_id.astype(str)))+'\n').encode()).hexdigest()
def v8path():
    if str(V8) not in sys.path:sys.path.append(str(V8))

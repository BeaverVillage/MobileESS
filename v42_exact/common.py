from pathlib import Path
import csv, hashlib, json, math, os, time, uuid

ROOT = Path(__file__).absolute().parents[1]
OUT = ROOT / 'docs/v42_exact_wan_factorized_milp'
LOCAL = ROOT.parent / 'V42_EXACT_WAN_LOCAL'
BASE = '3309cd230cd8235201f5578d392241fa98e059bc'

def clean(x):
    if isinstance(x, float) and (not math.isfinite(x) or abs(x) >= 1e99): return None
    if isinstance(x, dict): return {str(k): clean(v) for k,v in x.items()}
    if isinstance(x, (list,tuple)): return [clean(v) for v in x]
    return x

def atomic(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf8',newline='\n') as f:
        json.dump(clean(value),f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n');f.flush();os.fsync(f.fileno())
    for attempt in range(12):
        try: os.replace(temp,path);return
        except PermissionError:
            if attempt==11: raise
            time.sleep(.02*(attempt+1))

def dump(name,value): atomic(OUT/name,value)
def read(path): return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
def table(name,rows):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        if rows:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

class Context:
    def __init__(self): self.folder=LOCAL;self.folder.mkdir(parents=True,exist_ok=True)
    def check(self): pass
    def progress(self,value): atomic(self.folder/'build_progress.json',value)
